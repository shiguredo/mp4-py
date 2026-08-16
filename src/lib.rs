//! shiguredo_mp4 の PyO3 バインディング (nanobind 版と全機能パリティを目指す)

use std::num::NonZeroU32;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use pyo3::create_exception;
use pyo3::exceptions::{PyRuntimeError, PyStopIteration, PyValueError};
use pyo3::prelude::*;
use pyo3::sync::MutexExt;
use pyo3::types::{PyBytes, PyString};

// 破損 MP4 データの検出エラーを Python 側で型分類できるようにするための例外。
// 基底を PyRuntimeError にすることで、既存の except RuntimeError との後方互換性を
// 維持する。
create_exception!(mp4.mp4_ext, Mp4Exception, PyRuntimeError);

use shiguredo_mp4::{
    FixedPointNumber, LanguageCode, TrackKind, Uint, Utf8String,
    boxes::{
        AudioSampleEntryFields, Av01Box, Av1cBox, Avc1Box, AvccBox, BoxRecord, DflaBox, DopsBox,
        EsdsBox, FlacBox, FlacMetadataBlock, FontRecord, FtabBox, Hev1Box, Hvc1Box, HvccBox,
        HvccNalUintArray, Mp4aBox, OpusBox, SampleEntry, StppBox, StyleRecord, Tx3gBox,
        VisualSampleEntryFields, Vp08Box, Vp09Box, VpccBox, VttCBox, WvttBox,
    },
    demux::{DemuxError, Input as DemuxInput, Mp4FileDemuxer as CoreDemuxer, RequiredInput},
    descriptors::{DecoderConfigDescriptor, DecoderSpecificInfo, EsDescriptor, SlConfigDescriptor},
    mux::{
        Mp4FileMuxer as CoreMuxer, Mp4FileMuxerOptions as CoreMuxerOptions,
        Sample as CoreMuxSample, TrackMetadata as CoreTrackMetadata,
        estimate_maximum_moov_box_size as core_estimate_moov,
    },
};

// nanobind 版と同じく、破損データ検出のための最大サンプルサイズ (1GB) を設ける
const MAX_SAMPLE_SIZE: u64 = 1u64 << 30;

// nanobind 版と同じく、handle_input が同じ位置を何度も要求してくる破損データの
// 無限ループを防ぐためのイテレーション上限
const MAX_FEED_ITERATIONS: usize = 10_000;

// ===== ユーティリティ =====

#[pyfunction]
fn library_version() -> &'static str {
    env!("SHIGUREDO_MP4_VERSION")
}

#[pyfunction]
#[pyo3(signature = (*sample_counts))]
fn estimate_maximum_moov_box_size(sample_counts: Vec<usize>) -> usize {
    core_estimate_moov(&sample_counts)
}

fn map_err<E: std::fmt::Display>(e: E) -> PyErr {
    PyRuntimeError::new_err(format!("mp4 error: {e}"))
}

// Mutex が Poisoned のとき、以前の Rust パニックで壊れた状態を Python 側にわかる
// 形で伝える。以前は `.unwrap()` で Rust パニックさせていたが、これは PyO3 の
// trampoline で SystemError に変換され原因が分かりにくかった。
fn poisoned_err(what: &str) -> PyErr {
    PyRuntimeError::new_err(format!("{what} state poisoned by previous panic"))
}

fn track_kind_to_str(kind: TrackKind) -> &'static str {
    match kind {
        TrackKind::Audio => "audio",
        TrackKind::Video => "video",
        TrackKind::Subtitle => "subtitle",
    }
}

fn str_to_track_kind(s: &str) -> PyResult<TrackKind> {
    match s {
        "audio" => Ok(TrackKind::Audio),
        "video" => Ok(TrackKind::Video),
        "subtitle" => Ok(TrackKind::Subtitle),
        other => Err(PyValueError::new_err(format!(
            "invalid track_kind: {other:?} (expected 'audio', 'video' or 'subtitle')"
        ))),
    }
}

// ビット幅を超える値がコアの Uint で黙って切り捨て・隣接ビットを汚染しないよう、
// SampleEntry コンストラクタで値域を検証するヘルパー。
// max は 2^bits - 1 (例: 4 ビットなら 0xF) を呼び出し側が指定する。
fn validate_range<T>(value: T, max: T, name: &str) -> PyResult<()>
where
    T: PartialOrd + std::fmt::LowerHex,
{
    if value > max {
        return Err(PyValueError::new_err(format!(
            "{name} must be 0..=0x{max:x}, got 0x{value:x}"
        )));
    }
    Ok(())
}

// Vp08 / Vp09 共通の vpcC 値域検証 (VpccBox のフィールド定義を一次資料とする)。
// ビット幅超の値は Uint::to_bits のシフトで次のいずれかの被害を起こす:
// - シフト結果が保持型からあふれる場合は折り返して黙って別の値に化ける
//   (例: bit_depth=17 は 17 << 4 が u8 をあふれ 16 になる)
// - あふれない場合は隣接フィールドのビット位置に混入する
//   (例: chroma_subsampling=8 は 8 << 1 が bit_depth の最下位ビットと OR される)
fn validate_vpcc_fields(bit_depth: u8, chroma_subsampling: u8) -> PyResult<()> {
    // vpcC のビット幅 (4 ビット / 3 ビット) を超える値を弾く
    validate_range(bit_depth, 0xF, "bit_depth")?;
    validate_range(chroma_subsampling, 0x7, "chroma_subsampling")?;
    // 意味論的検証は 10 進表記 (8 / 10 / 12 の列挙との整合のため)。
    // vpcC の bit_depth は 8 / 10 / 12 のみ (コアの doc コメントに明記)
    if !matches!(bit_depth, 8 | 10 | 12) {
        return Err(PyValueError::new_err(format!(
            "bit_depth must be 8, 10 or 12, got {bit_depth}"
        )));
    }
    Ok(())
}

fn default_visual(width: u16, height: u16) -> VisualSampleEntryFields {
    VisualSampleEntryFields {
        data_reference_index: VisualSampleEntryFields::DEFAULT_DATA_REFERENCE_INDEX,
        width,
        height,
        horizresolution: VisualSampleEntryFields::DEFAULT_HORIZRESOLUTION,
        vertresolution: VisualSampleEntryFields::DEFAULT_VERTRESOLUTION,
        frame_count: VisualSampleEntryFields::DEFAULT_FRAME_COUNT,
        compressorname: VisualSampleEntryFields::NULL_COMPRESSORNAME,
        depth: VisualSampleEntryFields::DEFAULT_DEPTH,
    }
}

fn default_audio(channel_count: u8, sample_rate: u16, sample_size: u16) -> AudioSampleEntryFields {
    AudioSampleEntryFields {
        data_reference_index: AudioSampleEntryFields::DEFAULT_DATA_REFERENCE_INDEX,
        channelcount: channel_count as u16,
        samplesize: sample_size,
        samplerate: FixedPointNumber::new(sample_rate, 0),
    }
}

// Python の bytes-like (bytes / bytearray / memoryview / buffer protocol 対応)、
// または 0-255 の int の iterable (list[int] 等) を Vec<u8> に変換する。
// 型ミスの int / bool は TypeError を返す。nanobind 版は Python の
// builtins.bytes(iterable) にフォールバックしていたが、PyO3 0.29 では PyBuffer
// 経由の方が変換経路が短い。
fn extract_bytes(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    // 高速パス: すでに bytes ならスライスをそのままコピー
    if let Ok(b) = obj.cast::<PyBytes>() {
        return Ok(b.as_bytes().to_vec());
    }
    // 汎用パス: buffer protocol 経由 (bytearray / memoryview / array.array 等)
    if let Ok(buf) = pyo3::buffer::PyBuffer::<u8>::get(obj) {
        return buf.to_vec(py);
    }
    // bytes(12345) が b"\x00" * 12345 を返す仕様をそのまま通さないよう、
    // int / bool は型ミスとして TypeError にする。bool は int のサブクラスなので
    // PyInt チェックで捕捉される (分岐を分ける必要はない)。int サブクラス
    // (__bytes__ の有無に関わらず) も捕捉されるが、型ミスとして扱う方針どおり。
    // float / str は bytes() が元々 TypeError を返すためチェック不要。
    if obj.is_instance_of::<pyo3::types::PyInt>() {
        let type_name = obj.get_type().name()?;
        return Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "expected bytes, bytearray, memoryview or an iterable of int (0-255), got {type_name}"
        )));
    }
    // 最終フォールバック: Python 側の bytes() で変換 (list[int] 等)
    let builtins = py.import("builtins")?;
    let bytes_type = builtins.getattr("bytes")?;
    let converted = bytes_type.call1((obj,))?;
    let b = converted.cast::<PyBytes>()?;
    Ok(b.as_bytes().to_vec())
}

// 入力が既に bytes ならその Py 参照を無コピーで保持し、それ以外はコピーして bytes 化する。
// Mp4MuxSample.data のように大きなペイロードを保持する場合の二重コピー削減に使う。
fn adopt_or_copy_bytes(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyBytes>> {
    if let Ok(b) = obj.cast::<PyBytes>() {
        return Ok(b.clone().unbind());
    }
    let v = extract_bytes(py, obj)?;
    Ok(PyBytes::new(py, &v).unbind())
}

fn extract_bytes_list(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<Vec<u8>>> {
    let mut out = Vec::new();
    for item in obj.try_iter()? {
        let item = item?;
        out.push(extract_bytes(py, &item)?);
    }
    Ok(out)
}

// ===== SampleEntry: Vp08 =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryVp08 {
    #[pyo3(get)]
    width: u16,
    #[pyo3(get)]
    height: u16,
    #[pyo3(get)]
    bit_depth: u8,
    #[pyo3(get)]
    chroma_subsampling: u8,
    #[pyo3(get)]
    video_full_range_flag: bool,
    #[pyo3(get)]
    colour_primaries: u8,
    #[pyo3(get)]
    transfer_characteristics: u8,
    #[pyo3(get)]
    matrix_coefficients: u8,
}

#[pymethods]
impl Mp4SampleEntryVp08 {
    #[new]
    #[pyo3(signature = (
        width,
        height,
        bit_depth = 8,
        chroma_subsampling = 0,
        video_full_range_flag = false,
        colour_primaries = 1,
        transfer_characteristics = 1,
        matrix_coefficients = 1,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        width: u16,
        height: u16,
        bit_depth: u8,
        chroma_subsampling: u8,
        video_full_range_flag: bool,
        colour_primaries: u8,
        transfer_characteristics: u8,
        matrix_coefficients: u8,
    ) -> PyResult<Self> {
        validate_vpcc_fields(bit_depth, chroma_subsampling)?;
        Ok(Self {
            width,
            height,
            bit_depth,
            chroma_subsampling,
            video_full_range_flag,
            colour_primaries,
            transfer_characteristics,
            matrix_coefficients,
        })
    }

    fn __repr__(&self) -> String {
        format!(
            "Mp4SampleEntryVp08(width={}, height={}, bit_depth={})",
            self.width, self.height, self.bit_depth
        )
    }
}

impl Mp4SampleEntryVp08 {
    fn to_sample_entry(&self) -> SampleEntry {
        let vpcc_box = VpccBox {
            profile: 0,
            level: 0,
            bit_depth: Uint::new(self.bit_depth),
            chroma_subsampling: Uint::new(self.chroma_subsampling),
            video_full_range_flag: Uint::new(u8::from(self.video_full_range_flag)),
            colour_primaries: self.colour_primaries,
            transfer_characteristics: self.transfer_characteristics,
            matrix_coefficients: self.matrix_coefficients,
            codec_initialization_data: Vec::new(),
        };
        SampleEntry::Vp08(Vp08Box {
            visual: default_visual(self.width, self.height),
            vpcc_box,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &Vp08Box) -> Self {
        Self {
            width: b.visual.width,
            height: b.visual.height,
            bit_depth: b.vpcc_box.bit_depth.get(),
            chroma_subsampling: b.vpcc_box.chroma_subsampling.get(),
            video_full_range_flag: b.vpcc_box.video_full_range_flag.get() != 0,
            colour_primaries: b.vpcc_box.colour_primaries,
            transfer_characteristics: b.vpcc_box.transfer_characteristics,
            matrix_coefficients: b.vpcc_box.matrix_coefficients,
        }
    }
}

// ===== SampleEntry: Vp09 =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryVp09 {
    #[pyo3(get)]
    width: u16,
    #[pyo3(get)]
    height: u16,
    #[pyo3(get)]
    profile: u8,
    #[pyo3(get)]
    level: u8,
    #[pyo3(get)]
    bit_depth: u8,
    #[pyo3(get)]
    chroma_subsampling: u8,
    #[pyo3(get)]
    video_full_range_flag: bool,
    #[pyo3(get)]
    colour_primaries: u8,
    #[pyo3(get)]
    transfer_characteristics: u8,
    #[pyo3(get)]
    matrix_coefficients: u8,
}

#[pymethods]
impl Mp4SampleEntryVp09 {
    #[new]
    #[pyo3(signature = (
        width,
        height,
        profile,
        level,
        bit_depth = 8,
        chroma_subsampling = 0,
        video_full_range_flag = false,
        colour_primaries = 1,
        transfer_characteristics = 1,
        matrix_coefficients = 1,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        width: u16,
        height: u16,
        profile: u8,
        level: u8,
        bit_depth: u8,
        chroma_subsampling: u8,
        video_full_range_flag: bool,
        colour_primaries: u8,
        transfer_characteristics: u8,
        matrix_coefficients: u8,
    ) -> PyResult<Self> {
        validate_vpcc_fields(bit_depth, chroma_subsampling)?;
        Ok(Self {
            width,
            height,
            profile,
            level,
            bit_depth,
            chroma_subsampling,
            video_full_range_flag,
            colour_primaries,
            transfer_characteristics,
            matrix_coefficients,
        })
    }
}

impl Mp4SampleEntryVp09 {
    fn to_sample_entry(&self) -> SampleEntry {
        let vpcc_box = VpccBox {
            profile: self.profile,
            level: self.level,
            bit_depth: Uint::new(self.bit_depth),
            chroma_subsampling: Uint::new(self.chroma_subsampling),
            video_full_range_flag: Uint::new(u8::from(self.video_full_range_flag)),
            colour_primaries: self.colour_primaries,
            transfer_characteristics: self.transfer_characteristics,
            matrix_coefficients: self.matrix_coefficients,
            codec_initialization_data: Vec::new(),
        };
        SampleEntry::Vp09(Vp09Box {
            visual: default_visual(self.width, self.height),
            vpcc_box,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &Vp09Box) -> Self {
        Self {
            width: b.visual.width,
            height: b.visual.height,
            profile: b.vpcc_box.profile,
            level: b.vpcc_box.level,
            bit_depth: b.vpcc_box.bit_depth.get(),
            chroma_subsampling: b.vpcc_box.chroma_subsampling.get(),
            video_full_range_flag: b.vpcc_box.video_full_range_flag.get() != 0,
            colour_primaries: b.vpcc_box.colour_primaries,
            transfer_characteristics: b.vpcc_box.transfer_characteristics,
            matrix_coefficients: b.vpcc_box.matrix_coefficients,
        }
    }
}

// ===== SampleEntry: Avc1 =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryAvc1 {
    #[pyo3(get)]
    width: u16,
    #[pyo3(get)]
    height: u16,
    #[pyo3(get)]
    avc_profile_indication: u8,
    #[pyo3(get)]
    avc_level_indication: u8,
    #[pyo3(get)]
    profile_compatibility: u8,
    #[pyo3(get)]
    length_size_minus_one: u8,
    sps_data: Vec<Vec<u8>>,
    pps_data: Vec<Vec<u8>>,
    #[pyo3(get)]
    chroma_format: Option<u8>,
    #[pyo3(get)]
    bit_depth_luma_minus8: Option<u8>,
    #[pyo3(get)]
    bit_depth_chroma_minus8: Option<u8>,
}

#[pymethods]
impl Mp4SampleEntryAvc1 {
    #[new]
    #[pyo3(signature = (
        width,
        height,
        avc_profile_indication,
        avc_level_indication,
        profile_compatibility,
        sps_data = None,
        pps_data = None,
        length_size_minus_one = 3,
        chroma_format = None,
        bit_depth_luma_minus8 = None,
        bit_depth_chroma_minus8 = None,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        width: u16,
        height: u16,
        avc_profile_indication: u8,
        avc_level_indication: u8,
        profile_compatibility: u8,
        sps_data: Option<&Bound<'_, PyAny>>,
        pps_data: Option<&Bound<'_, PyAny>>,
        length_size_minus_one: u8,
        chroma_format: Option<u8>,
        bit_depth_luma_minus8: Option<u8>,
        bit_depth_chroma_minus8: Option<u8>,
    ) -> PyResult<Self> {
        let sps = sps_data
            .map(|o| extract_bytes_list(py, o))
            .transpose()?
            .unwrap_or_default();
        let pps = pps_data
            .map(|o| extract_bytes_list(py, o))
            .transpose()?
            .unwrap_or_default();
        // avcC のビット幅 (2 ビット / 2 ビット / 3 ビット / 3 ビット) を超える値を弾く
        validate_range(length_size_minus_one, 0x3, "length_size_minus_one")?;
        if let Some(v) = chroma_format {
            validate_range(v, 0x3, "chroma_format")?;
        }
        if let Some(v) = bit_depth_luma_minus8 {
            validate_range(v, 0x7, "bit_depth_luma_minus8")?;
        }
        if let Some(v) = bit_depth_chroma_minus8 {
            validate_range(v, 0x7, "bit_depth_chroma_minus8")?;
        }
        Ok(Self {
            width,
            height,
            avc_profile_indication,
            avc_level_indication,
            profile_compatibility,
            length_size_minus_one,
            sps_data: sps,
            pps_data: pps,
            chroma_format,
            bit_depth_luma_minus8,
            bit_depth_chroma_minus8,
        })
    }

    #[getter]
    fn sps_data(&self, py: Python<'_>) -> Vec<Py<PyBytes>> {
        self.sps_data
            .iter()
            .map(|v| PyBytes::new(py, v).unbind())
            .collect()
    }

    #[getter]
    fn pps_data(&self, py: Python<'_>) -> Vec<Py<PyBytes>> {
        self.pps_data
            .iter()
            .map(|v| PyBytes::new(py, v).unbind())
            .collect()
    }
}

impl Mp4SampleEntryAvc1 {
    fn to_sample_entry(&self) -> SampleEntry {
        let avcc_box = AvccBox {
            avc_profile_indication: self.avc_profile_indication,
            profile_compatibility: self.profile_compatibility,
            avc_level_indication: self.avc_level_indication,
            length_size_minus_one: Uint::new(self.length_size_minus_one),
            sps_list: self.sps_data.clone(),
            pps_list: self.pps_data.clone(),
            chroma_format: self.chroma_format.map(Uint::new),
            bit_depth_luma_minus8: self.bit_depth_luma_minus8.map(Uint::new),
            bit_depth_chroma_minus8: self.bit_depth_chroma_minus8.map(Uint::new),
            sps_ext_list: Vec::new(),
        };
        SampleEntry::Avc1(Avc1Box {
            visual: default_visual(self.width, self.height),
            avcc_box,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &Avc1Box) -> Self {
        Self {
            width: b.visual.width,
            height: b.visual.height,
            avc_profile_indication: b.avcc_box.avc_profile_indication,
            avc_level_indication: b.avcc_box.avc_level_indication,
            profile_compatibility: b.avcc_box.profile_compatibility,
            length_size_minus_one: b.avcc_box.length_size_minus_one.get(),
            sps_data: b.avcc_box.sps_list.clone(),
            pps_data: b.avcc_box.pps_list.clone(),
            chroma_format: b.avcc_box.chroma_format.map(|v| v.get()),
            bit_depth_luma_minus8: b.avcc_box.bit_depth_luma_minus8.map(|v| v.get()),
            bit_depth_chroma_minus8: b.avcc_box.bit_depth_chroma_minus8.map(|v| v.get()),
        }
    }
}

// ===== SampleEntry: Hev1 / Hvc1 (共通のフィールドを持つので構造体は共通で) =====

#[derive(Clone)]
struct HevcCommon {
    width: u16,
    height: u16,
    general_profile_space: u8,
    general_tier_flag: u8,
    general_profile_idc: u8,
    general_profile_compatibility_flags: u32,
    general_constraint_indicator_flags: u64,
    general_level_idc: u8,
    chroma_format_idc: u8,
    bit_depth_luma_minus8: u8,
    bit_depth_chroma_minus8: u8,
    min_spatial_segmentation_idc: u16,
    parallelism_type: u8,
    avg_frame_rate: u16,
    constant_frame_rate: u8,
    num_temporal_layers: u8,
    temporal_id_nested: u8,
    length_size_minus_one: u8,
    // nanobind 版と同じく nalu_types と nalu_data を並列配列で持つ (nalu_types 1 個につき nalus 1 個)
    nalu_types: Vec<u8>,
    nalu_data: Vec<Vec<u8>>,
}

impl HevcCommon {
    fn to_hvcc(&self) -> HvccBox {
        let nalu_arrays: Vec<HvccNalUintArray> = self
            .nalu_types
            .iter()
            .zip(self.nalu_data.iter())
            .map(|(&t, d)| HvccNalUintArray {
                array_completeness: Uint::new(0),
                nal_unit_type: Uint::new(t),
                nalus: vec![d.clone()],
            })
            .collect();
        HvccBox {
            general_profile_space: Uint::new(self.general_profile_space),
            general_tier_flag: Uint::new(self.general_tier_flag),
            general_profile_idc: Uint::new(self.general_profile_idc),
            general_profile_compatibility_flags: self.general_profile_compatibility_flags,
            general_constraint_indicator_flags: Uint::new(self.general_constraint_indicator_flags),
            general_level_idc: self.general_level_idc,
            min_spatial_segmentation_idc: Uint::new(self.min_spatial_segmentation_idc),
            parallelism_type: Uint::new(self.parallelism_type),
            chroma_format_idc: Uint::new(self.chroma_format_idc),
            bit_depth_luma_minus8: Uint::new(self.bit_depth_luma_minus8),
            bit_depth_chroma_minus8: Uint::new(self.bit_depth_chroma_minus8),
            avg_frame_rate: self.avg_frame_rate,
            constant_frame_rate: Uint::new(self.constant_frame_rate),
            num_temporal_layers: Uint::new(self.num_temporal_layers),
            temporal_id_nested: Uint::new(self.temporal_id_nested),
            length_size_minus_one: Uint::new(self.length_size_minus_one),
            nalu_arrays,
        }
    }

    fn from_hvcc(width: u16, height: u16, b: &HvccBox) -> Self {
        // 各 nalu_array 内の全 NALU を展開する (nanobind 版と同じ扁平化)
        let mut nalu_types = Vec::new();
        let mut nalu_data = Vec::new();
        for arr in &b.nalu_arrays {
            for n in &arr.nalus {
                nalu_types.push(arr.nal_unit_type.get());
                nalu_data.push(n.clone());
            }
        }
        Self {
            width,
            height,
            general_profile_space: b.general_profile_space.get(),
            general_tier_flag: b.general_tier_flag.get(),
            general_profile_idc: b.general_profile_idc.get(),
            general_profile_compatibility_flags: b.general_profile_compatibility_flags,
            general_constraint_indicator_flags: b.general_constraint_indicator_flags.get(),
            general_level_idc: b.general_level_idc,
            chroma_format_idc: b.chroma_format_idc.get(),
            bit_depth_luma_minus8: b.bit_depth_luma_minus8.get(),
            bit_depth_chroma_minus8: b.bit_depth_chroma_minus8.get(),
            min_spatial_segmentation_idc: b.min_spatial_segmentation_idc.get(),
            parallelism_type: b.parallelism_type.get(),
            avg_frame_rate: b.avg_frame_rate,
            constant_frame_rate: b.constant_frame_rate.get(),
            num_temporal_layers: b.num_temporal_layers.get(),
            temporal_id_nested: b.temporal_id_nested.get(),
            length_size_minus_one: b.length_size_minus_one.get(),
            nalu_types,
            nalu_data,
        }
    }
}

// マクロで Hev1/Hvc1 の pyclass を展開する (差分はコンストラクタと to_sample_entry のバリアントのみ)
//
// [NOTE] rustfmt の既知のバグ (rust-lang/rustfmt#5489) により、
// macro_rules! 内のマルチライン属性 (`#[pyo3(signature = (...))]` など) の
// インデントが実行のたびに増加し続けて収束しない。
// このため本マクロ定義は `#[rustfmt::skip]` で rustfmt のフォーマット対象外にする。
// マクロ展開後のコード (Mp4SampleEntryHev1 / Mp4SampleEntryHvc1 の本体) は
// 通常の struct として rustfmt の対象になるため、フォーマット品質は保たれる。
#[rustfmt::skip]
macro_rules! hevc_pyclass {
    ($cls:ident, $box_ty:ident, $variant:ident) => {
        #[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
        #[derive(Clone)]
        struct $cls {
            inner: HevcCommon,
        }

        #[pymethods]
        impl $cls {
            #[new]
            #[pyo3(signature = (
                                width,
                                height,
                                general_profile_idc,
                                general_level_idc,
                                nalu_types = None,
                                nalu_data = None,
                                general_profile_space = 0,
                                general_tier_flag = 0,
                                general_profile_compatibility_flags = 0,
                                general_constraint_indicator_flags = 0,
                                chroma_format_idc = 1,
                                bit_depth_luma_minus8 = 0,
                                bit_depth_chroma_minus8 = 0,
                                min_spatial_segmentation_idc = 0,
                                parallelism_type = 0,
                                avg_frame_rate = 0,
                                constant_frame_rate = 0,
                                num_temporal_layers = 0,
                                temporal_id_nested = 0,
                                length_size_minus_one = 3,
                            ))]
            #[allow(clippy::too_many_arguments)]
            fn new(
                py: Python<'_>,
                width: u16,
                height: u16,
                general_profile_idc: u8,
                general_level_idc: u8,
                nalu_types: Option<&Bound<'_, PyAny>>,
                nalu_data: Option<&Bound<'_, PyAny>>,
                general_profile_space: u8,
                general_tier_flag: u8,
                general_profile_compatibility_flags: u32,
                general_constraint_indicator_flags: u64,
                chroma_format_idc: u8,
                bit_depth_luma_minus8: u8,
                bit_depth_chroma_minus8: u8,
                min_spatial_segmentation_idc: u16,
                parallelism_type: u8,
                avg_frame_rate: u16,
                constant_frame_rate: u8,
                num_temporal_layers: u8,
                temporal_id_nested: u8,
                length_size_minus_one: u8,
            ) -> PyResult<Self> {
                let types = if let Some(o) = nalu_types {
                    let mut v = Vec::new();
                    for item in o.try_iter()? {
                        v.push(item?.extract::<u8>()?);
                    }
                    v
                } else {
                    Vec::new()
                };
                let data = if let Some(o) = nalu_data {
                    extract_bytes_list(py, o)?
                } else {
                    Vec::new()
                };
                if types.len() != data.len() {
                    return Err(PyValueError::new_err(
                        "nalu_types and nalu_data must have the same length",
                    ));
                }
                // hvcC のビット幅を超える値が Uint で黙って切り捨て・
                // 隣接ビットを汚染しないよう、コンストラクタで検証する。
                validate_range(general_profile_space, 0x3, "general_profile_space")?;
                validate_range(general_tier_flag, 0x1, "general_tier_flag")?;
                validate_range(general_profile_idc, 0x1F, "general_profile_idc")?;
                validate_range(
                    general_constraint_indicator_flags,
                    0xFFFFFFFFFFFF,
                    "general_constraint_indicator_flags",
                )?;
                validate_range(chroma_format_idc, 0x3, "chroma_format_idc")?;
                validate_range(bit_depth_luma_minus8, 0x7, "bit_depth_luma_minus8")?;
                validate_range(bit_depth_chroma_minus8, 0x7, "bit_depth_chroma_minus8")?;
                validate_range(min_spatial_segmentation_idc, 0xFFF, "min_spatial_segmentation_idc")?;
                validate_range(parallelism_type, 0x3, "parallelism_type")?;
                validate_range(constant_frame_rate, 0x3, "constant_frame_rate")?;
                validate_range(num_temporal_layers, 0x7, "num_temporal_layers")?;
                validate_range(temporal_id_nested, 0x1, "temporal_id_nested")?;
                validate_range(length_size_minus_one, 0x3, "length_size_minus_one")?;
                for (i, &t) in types.iter().enumerate() {
                    // nal_unit_type は 6 ビット。超過値は上位ビット (reserved /
                    // array_completeness 相当) に混入して誤デコードされる
                    validate_range(t, 0x3F, &format!("nalu_types[{i}]"))?;
                }
                Ok(Self {
                    inner: HevcCommon {
                        width,
                        height,
                        general_profile_space,
                        general_tier_flag,
                        general_profile_idc,
                        general_profile_compatibility_flags,
                        general_constraint_indicator_flags,
                        general_level_idc,
                        chroma_format_idc,
                        bit_depth_luma_minus8,
                        bit_depth_chroma_minus8,
                        min_spatial_segmentation_idc,
                        parallelism_type,
                        avg_frame_rate,
                        constant_frame_rate,
                        num_temporal_layers,
                        temporal_id_nested,
                        length_size_minus_one,
                        nalu_types: types,
                        nalu_data: data,
                    },
                })
            }

            #[getter]
            fn width(&self) -> u16 {
                self.inner.width
            }
            #[getter]
            fn height(&self) -> u16 {
                self.inner.height
            }
            #[getter]
            fn general_profile_idc(&self) -> u8 {
                self.inner.general_profile_idc
            }
            #[getter]
            fn general_level_idc(&self) -> u8 {
                self.inner.general_level_idc
            }
            #[getter]
            fn nalu_types(&self) -> Vec<u8> {
                self.inner.nalu_types.clone()
            }
            #[getter]
            fn nalu_data(&self, py: Python<'_>) -> Vec<Py<PyBytes>> {
                self.inner
                    .nalu_data
                    .iter()
                    .map(|v| PyBytes::new(py, v).unbind())
                    .collect()
            }
        }

        impl $cls {
            fn to_sample_entry(&self) -> SampleEntry {
                SampleEntry::$variant($box_ty {
                    visual: default_visual(self.inner.width, self.inner.height),
                    hvcc_box: self.inner.to_hvcc(),
                    unknown_boxes: Vec::new(),
                })
            }

            fn from_box(b: &$box_ty) -> Self {
                Self {
                    inner: HevcCommon::from_hvcc(b.visual.width, b.visual.height, &b.hvcc_box),
                }
            }
        }
    };
}

hevc_pyclass!(Mp4SampleEntryHev1, Hev1Box, Hev1);
hevc_pyclass!(Mp4SampleEntryHvc1, Hvc1Box, Hvc1);

// ===== SampleEntry: Av01 =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryAv01 {
    #[pyo3(get)]
    width: u16,
    #[pyo3(get)]
    height: u16,
    #[pyo3(get)]
    seq_profile: u8,
    #[pyo3(get)]
    seq_level_idx_0: u8,
    #[pyo3(get)]
    seq_tier_0: u8,
    #[pyo3(get)]
    high_bitdepth: u8,
    #[pyo3(get)]
    twelve_bit: u8,
    #[pyo3(get)]
    monochrome: u8,
    #[pyo3(get)]
    chroma_subsampling_x: u8,
    #[pyo3(get)]
    chroma_subsampling_y: u8,
    #[pyo3(get)]
    chroma_sample_position: u8,
    #[pyo3(get)]
    initial_presentation_delay_present: bool,
    #[pyo3(get)]
    initial_presentation_delay_minus_one: u8,
    config_obus: Vec<u8>,
}

#[pymethods]
impl Mp4SampleEntryAv01 {
    #[new]
    #[pyo3(signature = (
        width,
        height,
        seq_profile,
        seq_level_idx_0,
        config_obus,
        seq_tier_0 = 0,
        high_bitdepth = 0,
        twelve_bit = 0,
        monochrome = 0,
        chroma_subsampling_x = 1,
        chroma_subsampling_y = 1,
        chroma_sample_position = 0,
        initial_presentation_delay_present = false,
        initial_presentation_delay_minus_one = 0,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        width: u16,
        height: u16,
        seq_profile: u8,
        seq_level_idx_0: u8,
        config_obus: &Bound<'_, PyAny>,
        seq_tier_0: u8,
        high_bitdepth: u8,
        twelve_bit: u8,
        monochrome: u8,
        chroma_subsampling_x: u8,
        chroma_subsampling_y: u8,
        chroma_sample_position: u8,
        initial_presentation_delay_present: bool,
        initial_presentation_delay_minus_one: u8,
    ) -> PyResult<Self> {
        // av1C のビット幅 (3 / 5 / 1 / 1 / 1 / 1 / 1 / 1 / 2 / 4 ビット) を超える値が
        // Uint で黙って切り捨て・隣接ビットを汚染しないよう、コンストラクタで検証する。
        validate_range(seq_profile, 0x7, "seq_profile")?;
        validate_range(seq_level_idx_0, 0x1F, "seq_level_idx_0")?;
        validate_range(seq_tier_0, 0x1, "seq_tier_0")?;
        validate_range(high_bitdepth, 0x1, "high_bitdepth")?;
        validate_range(twelve_bit, 0x1, "twelve_bit")?;
        validate_range(monochrome, 0x1, "monochrome")?;
        validate_range(chroma_subsampling_x, 0x1, "chroma_subsampling_x")?;
        validate_range(chroma_subsampling_y, 0x1, "chroma_subsampling_y")?;
        validate_range(chroma_sample_position, 0x3, "chroma_sample_position")?;
        // present が false ならコアに渡らないが、不正値は構築時に弾く (一貫した値域保証)
        validate_range(
            initial_presentation_delay_minus_one,
            0xF,
            "initial_presentation_delay_minus_one",
        )?;
        Ok(Self {
            width,
            height,
            seq_profile,
            seq_level_idx_0,
            seq_tier_0,
            high_bitdepth,
            twelve_bit,
            monochrome,
            chroma_subsampling_x,
            chroma_subsampling_y,
            chroma_sample_position,
            initial_presentation_delay_present,
            initial_presentation_delay_minus_one,
            config_obus: extract_bytes(py, config_obus)?,
        })
    }

    #[getter]
    fn config_obus(&self, py: Python<'_>) -> Py<PyBytes> {
        PyBytes::new(py, &self.config_obus).unbind()
    }
}

impl Mp4SampleEntryAv01 {
    fn to_sample_entry(&self) -> SampleEntry {
        let av1c_box = Av1cBox {
            seq_profile: Uint::new(self.seq_profile),
            seq_level_idx_0: Uint::new(self.seq_level_idx_0),
            seq_tier_0: Uint::new(self.seq_tier_0),
            high_bitdepth: Uint::new(self.high_bitdepth),
            twelve_bit: Uint::new(self.twelve_bit),
            monochrome: Uint::new(self.monochrome),
            chroma_subsampling_x: Uint::new(self.chroma_subsampling_x),
            chroma_subsampling_y: Uint::new(self.chroma_subsampling_y),
            chroma_sample_position: Uint::new(self.chroma_sample_position),
            initial_presentation_delay_minus_one: self
                .initial_presentation_delay_present
                .then_some(Uint::new(self.initial_presentation_delay_minus_one)),
            config_obus: self.config_obus.clone(),
        };
        SampleEntry::Av01(Av01Box {
            visual: default_visual(self.width, self.height),
            av1c_box,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &Av01Box) -> Self {
        Self {
            width: b.visual.width,
            height: b.visual.height,
            seq_profile: b.av1c_box.seq_profile.get(),
            seq_level_idx_0: b.av1c_box.seq_level_idx_0.get(),
            seq_tier_0: b.av1c_box.seq_tier_0.get(),
            high_bitdepth: b.av1c_box.high_bitdepth.get(),
            twelve_bit: b.av1c_box.twelve_bit.get(),
            monochrome: b.av1c_box.monochrome.get(),
            chroma_subsampling_x: b.av1c_box.chroma_subsampling_x.get(),
            chroma_subsampling_y: b.av1c_box.chroma_subsampling_y.get(),
            chroma_sample_position: b.av1c_box.chroma_sample_position.get(),
            initial_presentation_delay_present: b
                .av1c_box
                .initial_presentation_delay_minus_one
                .is_some(),
            initial_presentation_delay_minus_one: b
                .av1c_box
                .initial_presentation_delay_minus_one
                .map(|v| v.get())
                .unwrap_or(0),
            config_obus: b.av1c_box.config_obus.clone(),
        }
    }
}

// ===== SampleEntry: Opus =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryOpus {
    #[pyo3(get)]
    channel_count: u8,
    #[pyo3(get)]
    sample_rate: u16,
    #[pyo3(get)]
    sample_size: u16,
    #[pyo3(get)]
    pre_skip: u16,
    #[pyo3(get)]
    input_sample_rate: Option<u32>,
    #[pyo3(get)]
    output_gain: i16,
}

#[pymethods]
impl Mp4SampleEntryOpus {
    #[new]
    #[pyo3(signature = (
        channel_count,
        sample_rate,
        sample_size = 16,
        pre_skip = 0,
        input_sample_rate = None,
        output_gain = 0,
    ))]
    fn new(
        channel_count: u8,
        sample_rate: u16,
        sample_size: u16,
        pre_skip: u16,
        input_sample_rate: Option<u32>,
        output_gain: i16,
    ) -> Self {
        Self {
            channel_count,
            sample_rate,
            sample_size,
            pre_skip,
            input_sample_rate,
            output_gain,
        }
    }
}

impl Mp4SampleEntryOpus {
    fn to_sample_entry(&self) -> SampleEntry {
        let dops_box = DopsBox {
            output_channel_count: self.channel_count,
            pre_skip: self.pre_skip,
            input_sample_rate: self.input_sample_rate.unwrap_or(self.sample_rate as u32),
            output_gain: self.output_gain,
        };
        SampleEntry::Opus(OpusBox {
            audio: default_audio(self.channel_count, self.sample_rate, self.sample_size),
            dops_box,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &OpusBox) -> Self {
        Self {
            channel_count: b.audio.channelcount as u8,
            sample_rate: b.audio.samplerate.integer,
            sample_size: b.audio.samplesize,
            pre_skip: b.dops_box.pre_skip,
            input_sample_rate: Some(b.dops_box.input_sample_rate),
            output_gain: b.dops_box.output_gain,
        }
    }
}

// ===== SampleEntry: Mp4a =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryMp4a {
    #[pyo3(get)]
    channel_count: u8,
    #[pyo3(get)]
    sample_rate: u16,
    #[pyo3(get)]
    sample_size: u16,
    #[pyo3(get)]
    buffer_size_db: u32,
    #[pyo3(get)]
    max_bitrate: u32,
    #[pyo3(get)]
    avg_bitrate: u32,
    dec_specific_info: Vec<u8>,
}

#[pymethods]
impl Mp4SampleEntryMp4a {
    #[new]
    #[pyo3(signature = (
        channel_count,
        sample_rate,
        dec_specific_info,
        sample_size = 16,
        buffer_size_db = 0,
        max_bitrate = 0,
        avg_bitrate = 0,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        channel_count: u8,
        sample_rate: u16,
        dec_specific_info: &Bound<'_, PyAny>,
        sample_size: u16,
        buffer_size_db: u32,
        max_bitrate: u32,
        avg_bitrate: u32,
    ) -> PyResult<Self> {
        // esds の DecoderConfigDescriptor.buffer_size_db は 24 ビット。
        // 超過時は上位 8 ビットが黙って破棄されるため、コンストラクタで検証する。
        validate_range(buffer_size_db, 0xFFFFFF, "buffer_size_db")?;
        Ok(Self {
            channel_count,
            sample_rate,
            sample_size,
            buffer_size_db,
            max_bitrate,
            avg_bitrate,
            dec_specific_info: extract_bytes(py, dec_specific_info)?,
        })
    }

    #[getter]
    fn dec_specific_info(&self, py: Python<'_>) -> Py<PyBytes> {
        PyBytes::new(py, &self.dec_specific_info).unbind()
    }
}

impl Mp4SampleEntryMp4a {
    fn to_sample_entry(&self) -> SampleEntry {
        let object_type_indication =
            DecoderConfigDescriptor::OBJECT_TYPE_INDICATION_AUDIO_ISO_IEC_14496_3;
        let dec_config_descr = DecoderConfigDescriptor {
            object_type_indication,
            stream_type: DecoderConfigDescriptor::STREAM_TYPE_AUDIO,
            up_stream: DecoderConfigDescriptor::UP_STREAM_FALSE,
            buffer_size_db: Uint::new(self.buffer_size_db),
            max_bitrate: self.max_bitrate,
            avg_bitrate: self.avg_bitrate,
            dec_specific_info: Some(DecoderSpecificInfo {
                payload: self.dec_specific_info.clone(),
            }),
        };
        let esds_box = EsdsBox {
            es: EsDescriptor {
                es_id: EsDescriptor::MIN_ES_ID,
                stream_priority: EsDescriptor::LOWEST_STREAM_PRIORITY,
                depends_on_es_id: None,
                url_string: None,
                ocr_es_id: None,
                dec_config_descr,
                sl_config_descr: SlConfigDescriptor,
            },
        };
        SampleEntry::Mp4a(Mp4aBox {
            audio: default_audio(self.channel_count, self.sample_rate, self.sample_size),
            esds_box,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &Mp4aBox) -> Self {
        let dec_specific_info = b
            .esds_box
            .es
            .dec_config_descr
            .dec_specific_info
            .as_ref()
            .map(|i| i.payload.clone())
            .unwrap_or_default();
        Self {
            channel_count: b.audio.channelcount as u8,
            sample_rate: b.audio.samplerate.integer,
            sample_size: b.audio.samplesize,
            buffer_size_db: b.esds_box.es.dec_config_descr.buffer_size_db.get(),
            max_bitrate: b.esds_box.es.dec_config_descr.max_bitrate,
            avg_bitrate: b.esds_box.es.dec_config_descr.avg_bitrate,
            dec_specific_info,
        }
    }
}

// ===== SampleEntry: Flac =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryFlac {
    #[pyo3(get)]
    channel_count: u8,
    #[pyo3(get)]
    sample_rate: u16,
    #[pyo3(get)]
    sample_size: u16,
    streaminfo_data: Vec<u8>,
}

#[pymethods]
impl Mp4SampleEntryFlac {
    #[new]
    #[pyo3(signature = (
        channel_count,
        sample_rate,
        streaminfo_data,
        sample_size = 16,
    ))]
    fn new(
        py: Python<'_>,
        channel_count: u8,
        sample_rate: u16,
        streaminfo_data: &Bound<'_, PyAny>,
        sample_size: u16,
    ) -> PyResult<Self> {
        Ok(Self {
            channel_count,
            sample_rate,
            sample_size,
            streaminfo_data: extract_bytes(py, streaminfo_data)?,
        })
    }

    #[getter]
    fn streaminfo_data(&self, py: Python<'_>) -> Py<PyBytes> {
        PyBytes::new(py, &self.streaminfo_data).unbind()
    }
}

impl Mp4SampleEntryFlac {
    fn to_sample_entry(&self) -> SampleEntry {
        let dfla_box = DflaBox {
            metadata_blocks: vec![FlacMetadataBlock {
                last_metadata_block_flag: Uint::from(true),
                block_type: FlacMetadataBlock::BLOCK_TYPE_STREAMINFO,
                block_data: self.streaminfo_data.clone(),
            }],
        };
        SampleEntry::Flac(FlacBox {
            audio: default_audio(self.channel_count, self.sample_rate, self.sample_size),
            dfla_box,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &FlacBox) -> Self {
        let streaminfo_data = b
            .dfla_box
            .metadata_blocks
            .first()
            .map(|blk| blk.block_data.clone())
            .unwrap_or_default();
        Self {
            channel_count: b.audio.channelcount as u8,
            sample_rate: b.audio.samplerate.integer,
            sample_size: b.audio.samplesize,
            streaminfo_data,
        }
    }
}

// ===== SampleEntry: Stpp =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryStpp {
    #[pyo3(get)]
    namespace: String,
    #[pyo3(get)]
    schema_location: String,
    #[pyo3(get)]
    auxiliary_mime_types: String,
}

#[pymethods]
impl Mp4SampleEntryStpp {
    #[new]
    #[pyo3(signature = (namespace, schema_location = "", auxiliary_mime_types = ""))]
    fn new(namespace: &str, schema_location: &str, auxiliary_mime_types: &str) -> PyResult<Self> {
        // Utf8String は null を含む文字列を拒否する (None を返す) ため、
        // expect で panic に到達しないよう構築時に検証する。
        // Mp4TrackMetadata::to_core と同じ文言形式を使う。
        if namespace.contains('\0') {
            return Err(PyValueError::new_err(
                "namespace must not contain null characters",
            ));
        }
        if schema_location.contains('\0') {
            return Err(PyValueError::new_err(
                "schema_location must not contain null characters",
            ));
        }
        if auxiliary_mime_types.contains('\0') {
            return Err(PyValueError::new_err(
                "auxiliary_mime_types must not contain null characters",
            ));
        }
        Ok(Self {
            namespace: namespace.to_owned(),
            schema_location: schema_location.to_owned(),
            auxiliary_mime_types: auxiliary_mime_types.to_owned(),
        })
    }

    fn __repr__(&self) -> String {
        format!(
            "Mp4SampleEntryStpp(namespace={:?}, schema_location={:?})",
            self.namespace, self.schema_location
        )
    }
}

impl Mp4SampleEntryStpp {
    fn to_sample_entry(&self) -> SampleEntry {
        // Utf8String は null を含む文字列を拒否するが、Python 側の String は
        // null を含む Unicode 文字列を保持できるため、ここで変換すると panic し得る。
        // ただし new で null 文字を検証済みであり、from_box (demux 側) はコアの
        // Utf8String が null で読み止めるため null 文字入りにはならない。
        // いずれの経路でも expect は panic しない。
        let namespace =
            Utf8String::new(&self.namespace).expect("namespace must not contain null characters");
        let schema_location = Utf8String::new(&self.schema_location)
            .expect("schema_location must not contain null characters");
        let auxiliary_mime_types = Utf8String::new(&self.auxiliary_mime_types)
            .expect("auxiliary_mime_types must not contain null characters");
        SampleEntry::Stpp(StppBox {
            data_reference_index: StppBox::DEFAULT_DATA_REFERENCE_INDEX,
            namespace,
            schema_location,
            auxiliary_mime_types,
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &StppBox) -> Self {
        Self {
            namespace: b.namespace.get().to_owned(),
            schema_location: b.schema_location.get().to_owned(),
            auxiliary_mime_types: b.auxiliary_mime_types.get().to_owned(),
        }
    }
}

// ===== SampleEntry: Wvtt =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryWvtt {
    #[pyo3(get)]
    config: String,
}

#[pymethods]
impl Mp4SampleEntryWvtt {
    #[new]
    #[pyo3(signature = (config = "WEBVTT"))]
    fn new(config: &str) -> Self {
        Self {
            config: config.to_owned(),
        }
    }

    fn __repr__(&self) -> String {
        format!("Mp4SampleEntryWvtt(config={:?})", self.config)
    }
}

impl Mp4SampleEntryWvtt {
    fn to_sample_entry(&self) -> SampleEntry {
        SampleEntry::Wvtt(WvttBox {
            data_reference_index: WvttBox::DEFAULT_DATA_REFERENCE_INDEX,
            vttc_box: VttCBox {
                config: self.config.clone(),
            },
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &WvttBox) -> Self {
        Self {
            config: b.vttc_box.config.clone(),
        }
    }
}

// ===== SampleEntry: Tx3g =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4SampleEntryTx3g {
    #[pyo3(get)]
    display_flags: u32,
    #[pyo3(get)]
    horizontal_justification: i8,
    #[pyo3(get)]
    vertical_justification: i8,
    background_color_rgba: Vec<u8>,
    default_text_box: (i16, i16, i16, i16),
    default_style: (u16, u16, u16, u8, u8, Vec<u8>),
    font_table: Vec<(u16, Vec<u8>)>,
}

#[pymethods]
impl Mp4SampleEntryTx3g {
    #[new]
    #[pyo3(signature = (
        display_flags = 0,
        horizontal_justification = 0,
        vertical_justification = 0,
        background_color_rgba = None,
        default_text_box = None,
        default_style = None,
        font_table = None,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        display_flags: u32,
        horizontal_justification: i8,
        vertical_justification: i8,
        background_color_rgba: Option<Vec<u8>>,
        default_text_box: Option<(i16, i16, i16, i16)>,
        default_style: Option<(u16, u16, u16, u8, u8, Vec<u8>)>,
        font_table: Option<Vec<(u16, Vec<u8>)>>,
    ) -> PyResult<Self> {
        // 4 バイト固定フィールドは長さを検証する
        let background_color_rgba = background_color_rgba.unwrap_or_default();
        if background_color_rgba.len() != 4 {
            return Err(PyValueError::new_err(
                "background_color_rgba must be exactly 4 bytes",
            ));
        }
        // 既定のスタイル (3GPP TS 26.245 の StyleRecord) の 6 番目はテキスト色 RGBA 4 バイト
        let default_style = default_style.unwrap_or((0, 0, 0, 0, 0, vec![0, 0, 0, 0]));
        if default_style.5.len() != 4 {
            return Err(PyValueError::new_err(
                "default_style text_color_rgba must be exactly 4 bytes",
            ));
        }
        Ok(Self {
            display_flags,
            horizontal_justification,
            vertical_justification,
            background_color_rgba,
            default_text_box: default_text_box.unwrap_or((0, 0, 0, 0)),
            default_style,
            font_table: font_table.unwrap_or_default(),
        })
    }

    #[getter]
    fn background_color_rgba(&self, py: Python<'_>) -> Py<PyBytes> {
        PyBytes::new(py, &self.background_color_rgba).unbind()
    }

    #[getter]
    fn default_text_box(&self) -> (i16, i16, i16, i16) {
        self.default_text_box
    }

    #[getter]
    fn default_style(&self, py: Python<'_>) -> (u16, u16, u16, u8, u8, Py<PyBytes>) {
        (
            self.default_style.0,
            self.default_style.1,
            self.default_style.2,
            self.default_style.3,
            self.default_style.4,
            PyBytes::new(py, &self.default_style.5).unbind(),
        )
    }

    #[getter]
    fn font_table(&self, py: Python<'_>) -> Vec<(u16, Py<PyBytes>)> {
        self.font_table
            .iter()
            .map(|(font_id, font_name)| (*font_id, PyBytes::new(py, font_name).unbind()))
            .collect()
    }

    fn __repr__(&self) -> String {
        format!(
            "Mp4SampleEntryTx3g(display_flags={}, font_table_size={})",
            self.display_flags,
            self.font_table.len()
        )
    }
}

impl Mp4SampleEntryTx3g {
    fn to_sample_entry(&self) -> SampleEntry {
        // 4 バイト検証は new で実施済み。frozen でフィールドは不変のため
        // ここでは expect で安全に [u8; 4] へ変換できる
        let background_color_rgba: [u8; 4] = self
            .background_color_rgba
            .clone()
            .try_into()
            .expect("background_color_rgba is 4 bytes (validated in new)");
        let text_color_rgba: [u8; 4] = self
            .default_style
            .5
            .clone()
            .try_into()
            .expect("text_color_rgba is 4 bytes (validated in new)");
        let entries = self
            .font_table
            .iter()
            .map(|(font_id, font_name)| FontRecord {
                font_id: *font_id,
                font_name: font_name.clone(),
            })
            .collect();
        SampleEntry::Tx3g(Tx3gBox {
            data_reference_index: Tx3gBox::DEFAULT_DATA_REFERENCE_INDEX,
            display_flags: self.display_flags,
            horizontal_justification: self.horizontal_justification,
            vertical_justification: self.vertical_justification,
            background_color_rgba,
            default_text_box: BoxRecord {
                top: self.default_text_box.0,
                left: self.default_text_box.1,
                bottom: self.default_text_box.2,
                right: self.default_text_box.3,
            },
            default_style: StyleRecord {
                start_char: self.default_style.0,
                end_char: self.default_style.1,
                font_id: self.default_style.2,
                face_style_flags: self.default_style.3,
                font_size: self.default_style.4,
                text_color_rgba,
            },
            ftab_box: FtabBox { entries },
            unknown_boxes: Vec::new(),
        })
    }

    fn from_box(b: &Tx3gBox) -> Self {
        Self {
            display_flags: b.display_flags,
            horizontal_justification: b.horizontal_justification,
            vertical_justification: b.vertical_justification,
            background_color_rgba: b.background_color_rgba.to_vec(),
            default_text_box: (
                b.default_text_box.top,
                b.default_text_box.left,
                b.default_text_box.bottom,
                b.default_text_box.right,
            ),
            default_style: (
                b.default_style.start_char,
                b.default_style.end_char,
                b.default_style.font_id,
                b.default_style.face_style_flags,
                b.default_style.font_size,
                b.default_style.text_color_rgba.to_vec(),
            ),
            font_table: b
                .ftab_box
                .entries
                .iter()
                .map(|entry| (entry.font_id, entry.font_name.clone()))
                .collect(),
        }
    }
}

// ===== SampleEntry Union の Python ↔ Rust dispatch =====

// タグ付き Union を FromPyObject / IntoPyObject 双方に derive させることで、
// .pyi 生成時に sample_entry の型が Union[...9 種...] として出るようにする。
#[derive(FromPyObject, IntoPyObject)]
enum Mp4SampleEntryAny {
    Vp08(Py<Mp4SampleEntryVp08>),
    Vp09(Py<Mp4SampleEntryVp09>),
    Avc1(Py<Mp4SampleEntryAvc1>),
    Hev1(Py<Mp4SampleEntryHev1>),
    Hvc1(Py<Mp4SampleEntryHvc1>),
    Av01(Py<Mp4SampleEntryAv01>),
    Opus(Py<Mp4SampleEntryOpus>),
    Mp4a(Py<Mp4SampleEntryMp4a>),
    Flac(Py<Mp4SampleEntryFlac>),
    Stpp(Py<Mp4SampleEntryStpp>),
    Wvtt(Py<Mp4SampleEntryWvtt>),
    Tx3g(Py<Mp4SampleEntryTx3g>),
}

impl Mp4SampleEntryAny {
    fn clone_ref(&self, py: Python<'_>) -> Self {
        match self {
            Self::Vp08(p) => Self::Vp08(p.clone_ref(py)),
            Self::Vp09(p) => Self::Vp09(p.clone_ref(py)),
            Self::Avc1(p) => Self::Avc1(p.clone_ref(py)),
            Self::Hev1(p) => Self::Hev1(p.clone_ref(py)),
            Self::Hvc1(p) => Self::Hvc1(p.clone_ref(py)),
            Self::Av01(p) => Self::Av01(p.clone_ref(py)),
            Self::Opus(p) => Self::Opus(p.clone_ref(py)),
            Self::Mp4a(p) => Self::Mp4a(p.clone_ref(py)),
            Self::Flac(p) => Self::Flac(p.clone_ref(py)),
            Self::Stpp(p) => Self::Stpp(p.clone_ref(py)),
            Self::Wvtt(p) => Self::Wvtt(p.clone_ref(py)),
            Self::Tx3g(p) => Self::Tx3g(p.clone_ref(py)),
        }
    }

    fn to_core(&self, _py: Python<'_>) -> SampleEntry {
        match self {
            Self::Vp08(p) => p.get().to_sample_entry(),
            Self::Vp09(p) => p.get().to_sample_entry(),
            Self::Avc1(p) => p.get().to_sample_entry(),
            Self::Hev1(p) => p.get().to_sample_entry(),
            Self::Hvc1(p) => p.get().to_sample_entry(),
            Self::Av01(p) => p.get().to_sample_entry(),
            Self::Opus(p) => p.get().to_sample_entry(),
            Self::Mp4a(p) => p.get().to_sample_entry(),
            Self::Flac(p) => p.get().to_sample_entry(),
            Self::Stpp(p) => p.get().to_sample_entry(),
            Self::Wvtt(p) => p.get().to_sample_entry(),
            Self::Tx3g(p) => p.get().to_sample_entry(),
        }
    }
}

fn sample_entry_from_core(
    py: Python<'_>,
    entry: &SampleEntry,
) -> PyResult<Option<Mp4SampleEntryAny>> {
    let out = match entry {
        SampleEntry::Vp08(b) => {
            Mp4SampleEntryAny::Vp08(Py::new(py, Mp4SampleEntryVp08::from_box(b))?)
        }
        SampleEntry::Vp09(b) => {
            Mp4SampleEntryAny::Vp09(Py::new(py, Mp4SampleEntryVp09::from_box(b))?)
        }
        SampleEntry::Avc1(b) => {
            Mp4SampleEntryAny::Avc1(Py::new(py, Mp4SampleEntryAvc1::from_box(b))?)
        }
        SampleEntry::Hev1(b) => {
            Mp4SampleEntryAny::Hev1(Py::new(py, Mp4SampleEntryHev1::from_box(b))?)
        }
        SampleEntry::Hvc1(b) => {
            Mp4SampleEntryAny::Hvc1(Py::new(py, Mp4SampleEntryHvc1::from_box(b))?)
        }
        SampleEntry::Av01(b) => {
            Mp4SampleEntryAny::Av01(Py::new(py, Mp4SampleEntryAv01::from_box(b))?)
        }
        SampleEntry::Opus(b) => {
            Mp4SampleEntryAny::Opus(Py::new(py, Mp4SampleEntryOpus::from_box(b))?)
        }
        SampleEntry::Mp4a(b) => {
            Mp4SampleEntryAny::Mp4a(Py::new(py, Mp4SampleEntryMp4a::from_box(b))?)
        }
        SampleEntry::Flac(b) => {
            Mp4SampleEntryAny::Flac(Py::new(py, Mp4SampleEntryFlac::from_box(b))?)
        }
        SampleEntry::Stpp(b) => {
            Mp4SampleEntryAny::Stpp(Py::new(py, Mp4SampleEntryStpp::from_box(b))?)
        }
        SampleEntry::Wvtt(b) => {
            Mp4SampleEntryAny::Wvtt(Py::new(py, Mp4SampleEntryWvtt::from_box(b))?)
        }
        SampleEntry::Tx3g(b) => {
            Mp4SampleEntryAny::Tx3g(Py::new(py, Mp4SampleEntryTx3g::from_box(b))?)
        }
        SampleEntry::Unknown(_) => return Ok(None),
    };
    let _ = py;
    Ok(Some(out))
}

// ===== Mp4TrackInfo =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4TrackInfo {
    #[pyo3(get)]
    track_id: u32,
    // Python 側は "audio" / "video" 固定なので String で保持する
    kind: String,
    #[pyo3(get)]
    duration: u64,
    #[pyo3(get)]
    timescale: u32,
}

#[pymethods]
impl Mp4TrackInfo {
    #[new]
    #[pyo3(signature = (track_id, kind, duration, timescale))]
    fn new(track_id: u32, kind: String, duration: u64, timescale: u32) -> PyResult<Self> {
        // 妥当性チェックだけ行い、正規化はしない
        let _ = str_to_track_kind(&kind)?;
        // timescale=0 は timestamp_seconds / duration_seconds の 0 除算で
        // inf / nan を生むため、append_sample と同じ検証で弾く。
        // Demuxer 経由の TrackInfo は shiguredo_mp4 の NonZeroU32 由来で
        // 0 にならないため、到達可能な経路はこのコンストラクタのみ
        if timescale == 0 {
            return Err(PyValueError::new_err("timescale must be non-zero"));
        }
        Ok(Self {
            track_id,
            kind,
            duration,
            timescale,
        })
    }

    #[getter]
    fn kind(&self) -> &str {
        &self.kind
    }

    fn __repr__(&self) -> String {
        format!(
            "Mp4TrackInfo(track_id={}, kind={:?}, duration={}, timescale={})",
            self.track_id, self.kind, self.duration, self.timescale
        )
    }
}

// ===== Mp4MuxSample =====

#[pyclass(module = "mp4.mp4_ext", frozen, skip_from_py_object)]
struct Mp4MuxSample {
    #[pyo3(get)]
    track_kind: String,
    // 9 種の SampleEntry のうちいずれか (None なら前と同じ)
    sample_entry: Option<Mp4SampleEntryAny>,
    #[pyo3(get)]
    keyframe: bool,
    #[pyo3(get)]
    timescale: u32,
    #[pyo3(get)]
    duration: u32,
    #[pyo3(get)]
    composition_time_offset: Option<i64>,
    data: Py<PyBytes>,
}

#[pymethods]
impl Mp4MuxSample {
    #[new]
    #[pyo3(signature = (
        track_kind,
        sample_entry,
        keyframe,
        timescale,
        duration,
        data,
        composition_time_offset = None,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        track_kind: String,
        sample_entry: Option<Mp4SampleEntryAny>,
        keyframe: bool,
        timescale: u32,
        duration: u32,
        data: &Bound<'_, PyAny>,
        composition_time_offset: Option<i64>,
    ) -> PyResult<Self> {
        let _ = str_to_track_kind(&track_kind)?;
        // bytes ならそのまま Py<PyBytes> を保持して二重コピーを回避する
        let data_py = adopt_or_copy_bytes(py, data)?;
        Ok(Self {
            track_kind,
            sample_entry,
            keyframe,
            timescale,
            duration,
            composition_time_offset,
            data: data_py,
        })
    }

    #[getter]
    fn sample_entry(&self, py: Python<'_>) -> Option<Mp4SampleEntryAny> {
        self.sample_entry.as_ref().map(|s| s.clone_ref(py))
    }

    #[getter]
    fn data(&self, py: Python<'_>) -> Py<PyBytes> {
        self.data.clone_ref(py)
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        let size = self.data.bind(py).as_bytes().len();
        format!(
            "Mp4MuxSample(track_kind={:?}, keyframe={}, timescale={}, duration={}, data_size={})",
            self.track_kind, self.keyframe, self.timescale, self.duration, size
        )
    }
}

// ===== Mp4DemuxSample (遅延読み込み対応) =====

#[pyclass(module = "mp4.mp4_ext", frozen, skip_from_py_object)]
struct Mp4DemuxSample {
    #[pyo3(get)]
    track: Py<Mp4TrackInfo>,
    sample_entry: Option<Mp4SampleEntryAny>,
    #[pyo3(get)]
    keyframe: bool,
    #[pyo3(get)]
    timestamp: u64,
    #[pyo3(get)]
    duration: u32,
    #[pyo3(get)]
    composition_time_offset: Option<i64>,
    #[pyo3(get)]
    data_offset: u64,
    #[pyo3(get)]
    data_size: u64,
    input_stream: Py<PyAny>,
    // Demuxer と共有する I/O シリアライズ用ロック。
    // 同一 input_stream に対して複数の Mp4DemuxSample が同時に seek + read を叩くと
    // ファイル位置が競合してデータが混ざるため、Free-Threading 環境でも安全に読める
    // ようにサンプル間でロックを共有する。
    stream_lock: Arc<Mutex<()>>,
    // 一度読み込んだデータをキャッシュする (Free-Threading 対応で Mutex 化)
    data_cache: Mutex<Option<Py<PyBytes>>>,
}

#[pymethods]
impl Mp4DemuxSample {
    #[new]
    #[pyo3(signature = (
        track,
        sample_entry,
        keyframe,
        timestamp,
        duration,
        data_offset,
        data_size,
        input_stream,
        composition_time_offset = None,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        track: Py<Mp4TrackInfo>,
        sample_entry: Option<Mp4SampleEntryAny>,
        keyframe: bool,
        timestamp: u64,
        duration: u32,
        data_offset: u64,
        data_size: u64,
        input_stream: Py<PyAny>,
        composition_time_offset: Option<i64>,
    ) -> Self {
        Self {
            track,
            sample_entry,
            keyframe,
            timestamp,
            duration,
            composition_time_offset,
            data_offset,
            data_size,
            input_stream,
            // Python から直接コンストラクタが呼ばれた場合、この Sample 単体で
            // ロックが完結する (Demuxer から作られる通常のフローでは Demuxer と
            // 共有した Arc を渡す)
            stream_lock: Arc::new(Mutex::new(())),
            data_cache: Mutex::new(None),
        }
    }

    #[getter]
    fn sample_entry(&self, py: Python<'_>) -> Option<Mp4SampleEntryAny> {
        self.sample_entry.as_ref().map(|s| s.clone_ref(py))
    }

    #[getter]
    fn data(&self, py: Python<'_>) -> PyResult<Py<PyBytes>> {
        // ファストパス: すでにキャッシュ済みならロックを離す前にコピーだけ返す。
        {
            let cache = self
                .data_cache
                .lock_py_attached(py)
                .map_err(|_| poisoned_err("sample data cache"))?;
            if let Some(ref b) = *cache {
                return Ok(b.clone_ref(py));
            }
        }
        // 破損データで巨大な値になっている可能性を弾く
        if self.data_size > MAX_SAMPLE_SIZE {
            return Err(Mp4Exception::new_err(format!(
                "Sample data size too large (corrupted data?): {} bytes (max: {} bytes)",
                self.data_size, MAX_SAMPLE_SIZE
            )));
        }
        // I/O は Demuxer と共有する stream_lock で直列化する。
        // 同一 stream を複数のサンプル (あるいは iteration の feed_required_input)
        // が並行して叩くと seek/read が競合するため、必ずロック内で完結させる。
        let read: Py<PyBytes> = {
            let _guard = self
                .stream_lock
                .lock_py_attached(py)
                .map_err(|_| poisoned_err("demuxer stream lock"))?;
            // ロック取得直後にもう一度キャッシュを見る。前段のファストパスと
            // ロック取得の間に別スレッドが埋めていた場合、I/O を省ける。
            {
                let cache = self
                    .data_cache
                    .lock_py_attached(py)
                    .map_err(|_| poisoned_err("sample data cache"))?;
                if let Some(ref b) = *cache {
                    return Ok(b.clone_ref(py));
                }
            }
            self.input_stream
                .call_method1(py, "seek", (self.data_offset,))?;
            let bytes: Py<PyBytes> = self
                .input_stream
                .call_method1(py, "read", (self.data_size,))?
                .extract(py)?;
            if bytes.bind(py).as_bytes().len() as u64 != self.data_size {
                return Err(Mp4Exception::new_err(format!(
                    "Failed to read sample data: expected {} bytes, got {}",
                    self.data_size,
                    bytes.bind(py).as_bytes().len()
                )));
            }
            bytes
        };
        *self
            .data_cache
            .lock_py_attached(py)
            .map_err(|_| poisoned_err("sample data cache"))? = Some(read.clone_ref(py));
        Ok(read)
    }

    #[getter]
    fn timestamp_seconds(&self, py: Python<'_>) -> f64 {
        let t = self.track.borrow(py);
        self.timestamp as f64 / t.timescale as f64
    }

    #[getter]
    fn duration_seconds(&self, py: Python<'_>) -> f64 {
        let t = self.track.borrow(py);
        self.duration as f64 / t.timescale as f64
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        let tid = self.track.borrow(py).track_id;
        format!(
            "Mp4DemuxSample(track_id={}, keyframe={}, timestamp={}, data_size={})",
            tid, self.keyframe, self.timestamp, self.data_size
        )
    }
}

// ===== Mp4TrackMetadata =====

#[pyclass(module = "mp4.mp4_ext", frozen, from_py_object)]
#[derive(Clone)]
struct Mp4TrackMetadata {
    #[pyo3(get)]
    language: String,
    #[pyo3(get)]
    name: String,
}

#[pymethods]
impl Mp4TrackMetadata {
    #[new]
    #[pyo3(signature = (language = "und", name = ""))]
    fn new(language: &str, name: &str) -> Self {
        Self {
            language: language.to_owned(),
            name: name.to_owned(),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "Mp4TrackMetadata(language={:?}, name={:?})",
            self.language, self.name
        )
    }
}

impl Mp4TrackMetadata {
    fn to_core(&self) -> PyResult<CoreTrackMetadata> {
        // LanguageCode は各バイトが 0x60..=0x7F (小文字アルファベット 3 文字) の
        // 範囲に収まる必要がある
        let language = LanguageCode::from_ascii(&self.language).ok_or_else(|| {
            PyValueError::new_err(format!(
                "invalid language code: {:?} (expected 3 lowercase ASCII letters)",
                self.language
            ))
        })?;
        // Utf8String は null を含む文字列を拒否する
        let name = Utf8String::new(&self.name)
            .ok_or_else(|| PyValueError::new_err("name must not contain null characters"))?;
        Ok(CoreTrackMetadata { language, name })
    }
}

// ===== Mp4FileMuxerOptions =====

#[pyclass(module = "mp4.mp4_ext", from_py_object)]
#[derive(Clone)]
struct Mp4FileMuxerOptions {
    #[pyo3(get)]
    reserved_moov_box_size: usize,
    #[pyo3(get)]
    audio_track: Option<Mp4TrackMetadata>,
    #[pyo3(get)]
    video_track: Option<Mp4TrackMetadata>,
    #[pyo3(get)]
    subtitle_track: Option<Mp4TrackMetadata>,
}

#[pymethods]
impl Mp4FileMuxerOptions {
    #[new]
    #[pyo3(signature = (
        reserved_moov_box_size = 0,
        audio_track = None,
        video_track = None,
        subtitle_track = None,
    ))]
    fn new(
        reserved_moov_box_size: usize,
        audio_track: Option<Mp4TrackMetadata>,
        video_track: Option<Mp4TrackMetadata>,
        subtitle_track: Option<Mp4TrackMetadata>,
    ) -> Self {
        Self {
            reserved_moov_box_size,
            audio_track,
            video_track,
            subtitle_track,
        }
    }

    // cls を使わないので #[staticmethod] にする。
    // Python 側から Mp4FileMuxerOptions.estimate_maximum_moov_box_size(a, v) と
    // 呼べる API は #[classmethod] と変わらない。
    #[staticmethod]
    #[pyo3(signature = (*sample_counts))]
    fn estimate_maximum_moov_box_size(sample_counts: Vec<usize>) -> usize {
        core_estimate_moov(&sample_counts)
    }
}

// ===== Mp4FileMuxer =====

// append_sample 失敗時にストリームを巻き戻せない場合、Muxer は使用不能になる。
// 破棄するようユーザーに伝える文言として、エラーメッセージに付加する。
const UNUSABLE_MUXER_MESSAGE: &str = "The muxer is in an unusable state and must be discarded";

// Free-Threading 対応: メソッドを &self に統一し、内部状態を Mutex で保護する。
// nanobind の ft_mutex 相当のブロッキング動作をシミュレートする。
struct MuxerState {
    core: Option<CoreMuxer>,
    finalized: bool,
    closed: bool,
}

/// MP4 ファイルのマルチプレクサー。
///
/// append_sample が失敗した場合の挙動:
/// - seekable なストリームでは、書き込んだバイトが巻き戻され、入力の補正後に
///   append_sample を retry できる
/// - 非 seekable なストリーム (実パイプなど) や巻き戻しに失敗した場合は、Muxer が
///   使用不能になり、以後の動作は保証されない。例外は RuntimeError になり、
///   メッセージに案内と元のエラーが含まれる。close() は finalize を実行して
///   破損ファイルを書き出すため、呼び出さずに破棄すること
/// - with 構文では例外発生時も __exit__ が close() を実行してしまうため、非
///   seekable なストリームでは with 構文を使わず、失敗時の破棄を考慮した
///   使用方法を取ること
#[pyclass(module = "mp4.mp4_ext", frozen, skip_from_py_object)]
struct Mp4FileMuxer {
    state: Mutex<MuxerState>,
    stream: Py<PyAny>,
    should_close_stream: bool,
}

fn is_pathlike(obj: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(obj.hasattr("__fspath__")? || obj.is_instance_of::<PyString>())
}

impl Mp4FileMuxer {
    // 呼び出し側で lock 済みの state を受け取り finalize を進める
    fn finalize_locked(&self, py: Python<'_>, state: &mut MuxerState) -> PyResult<()> {
        if state.finalized {
            return Ok(());
        }
        let core = state
            .core
            .as_mut()
            .ok_or_else(|| PyRuntimeError::new_err("muxer already dropped"))?;
        let finalized = core.finalize().map_err(map_err)?;
        for (offset, bytes) in finalized.offset_and_bytes_pairs() {
            self.stream.call_method1(py, "seek", (offset,))?;
            self.stream
                .call_method1(py, "write", (PyBytes::new(py, bytes),))?;
        }
        state.finalized = true;
        Ok(())
    }

    // append_sample が失敗したときに、write 済みのバイトを巻き戻す。
    // seekable でないストリームや truncate できないストリームでは巻き戻せず、
    // その場合は Muxer が使用不能になる
    fn rollback_append(&self, py: Python<'_>, data_offset: u64) -> PyResult<()> {
        let seekable: bool = self.stream.call_method0(py, "seekable")?.extract(py)?;
        if !seekable {
            return Err(PyRuntimeError::new_err("stream is not seekable"));
        }
        self.stream.call_method1(py, "seek", (data_offset,))?;
        // 位置非依存のストリーム実装でも確実に切り詰めるため、位置を明示する
        self.stream.call_method1(py, "truncate", (data_offset,))?;
        Ok(())
    }
}

#[pymethods]
impl Mp4FileMuxer {
    #[new]
    #[pyo3(signature = (destination, options = None))]
    fn new(
        py: Python<'_>,
        destination: Py<PyAny>,
        options: Option<Mp4FileMuxerOptions>,
    ) -> PyResult<Self> {
        let (stream, should_close) = {
            let dst = destination.bind(py);
            if is_pathlike(dst)? {
                let builtins = py.import("builtins")?;
                let opened = builtins.call_method1("open", (destination, "wb"))?;
                (opened.unbind(), true)
            } else {
                (destination, false)
            }
        };

        let core_options = options
            .map(|o| -> PyResult<CoreMuxerOptions> {
                Ok(CoreMuxerOptions {
                    reserved_moov_box_size: o.reserved_moov_box_size,
                    creation_timestamp: Duration::ZERO,
                    audio_track: o
                        .audio_track
                        .map(|t| t.to_core())
                        .transpose()?
                        .unwrap_or_default(),
                    video_track: o
                        .video_track
                        .map(|t| t.to_core())
                        .transpose()?
                        .unwrap_or_default(),
                    subtitle_track: o
                        .subtitle_track
                        .map(|t| t.to_core())
                        .transpose()?
                        .unwrap_or_default(),
                })
            })
            .transpose()?
            .unwrap_or_default();
        let core = CoreMuxer::with_options(core_options).map_err(map_err)?;

        // 初期ボックス群を先に書き出す
        stream.call_method1(py, "write", (PyBytes::new(py, core.initial_boxes_bytes()),))?;

        Ok(Self {
            state: Mutex::new(MuxerState {
                core: Some(core),
                finalized: false,
                closed: false,
            }),
            stream,
            should_close_stream: should_close,
        })
    }

    fn append_sample(&self, py: Python<'_>, sample: &Mp4MuxSample) -> PyResult<()> {
        let mut state = self
            .state
            .lock_py_attached(py)
            .map_err(|_| poisoned_err("muxer"))?;
        if state.closed {
            return Err(PyRuntimeError::new_err("muxer is closed"));
        }
        // finalize 済みの場合は write に進む前にエラーを返す。
        // コアの FinalizedBoxes::offset_and_bytes_pairs は mdat ヘッダーを最後に
        // 返すため、finalize 直後のストリーム位置は mdat ヘッダー末尾になる。
        // ここに write すると mdat ペイロード先頭を上書きし、その後のロールバック
        // (truncate) でファイル全体が破壊されるため。文言はコアの
        // MuxError::AlreadyFinalized と揃える。
        if state.finalized {
            return Err(PyRuntimeError::new_err(
                "Muxer has already been finalized",
            ));
        }
        let core = state
            .core
            .as_mut()
            .ok_or_else(|| PyRuntimeError::new_err("muxer already dropped"))?;

        // 実パイプのように tell() できないストリームは、write 後の巻き戻しも
        // 不可能なため、write に進む前に使用不能としてエラーを返す
        let data_offset: u64 = self
            .stream
            .call_method0(py, "tell")
            .map_err(|err| {
                PyRuntimeError::new_err(format!(
                    "failed to get stream position for append_sample: {err}. {UNUSABLE_MUXER_MESSAGE}"
                ))
            })?
            .extract(py)?;

        // write 以降の失敗で書き込んだバイトがストリームに残ると、以降の
        // append_sample が位置不一致で失敗し続ける。エラー時は write 前の位置へ
        // 巻き戻して retry を可能にするため、write 以降を 1 つのクロージャに
        // まとめ、失敗時は必ずロールバックを実行してからエラーを伝播する
        let append_result = (|| -> PyResult<()> {
            // Mp4MuxSample.data はすでに Py<PyBytes> なので、新しい PyBytes を作らず
            // 元の Python bytes をそのまま stream.write に渡して余分なコピーを避ける。
            let data_len = sample.data.bind(py).as_bytes().len();
            self.stream
                .call_method1(py, "write", (sample.data.clone_ref(py),))?;

            let timescale = NonZeroU32::new(sample.timescale)
                .ok_or_else(|| PyValueError::new_err("timescale must be non-zero"))?;
            let track_kind = str_to_track_kind(&sample.track_kind)?;
            let sample_entry_opt = sample.sample_entry.as_ref().map(|e| e.to_core(py));

            let core_sample = CoreMuxSample {
                track_kind,
                sample_entry: sample_entry_opt,
                keyframe: sample.keyframe,
                timescale,
                duration: sample.duration,
                composition_time_offset: sample.composition_time_offset,
                data_offset,
                data_size: data_len,
            };

            core.append_sample(&core_sample).map_err(map_err)?;
            Ok(())
        })();

        if let Err(err) = append_result {
            // 巻き戻しに失敗した場合は Muxer が使用不能になるため、元のエラーに
            // 案内を付加して伝播する
            return match self.rollback_append(py, data_offset) {
                Ok(()) => Err(err),
                Err(rollback_err) => Err(PyRuntimeError::new_err(format!(
                    "{err}. Additionally, failed to roll back the stream: {rollback_err}. {UNUSABLE_MUXER_MESSAGE}"
                ))),
            };
        }
        Ok(())
    }

    fn finalize(&self, py: Python<'_>) -> PyResult<()> {
        let mut state = self
            .state
            .lock_py_attached(py)
            .map_err(|_| poisoned_err("muxer"))?;
        self.finalize_locked(py, &mut state)
    }

    fn close(&self, py: Python<'_>) -> PyResult<()> {
        let mut state = self
            .state
            .lock_py_attached(py)
            .map_err(|_| poisoned_err("muxer"))?;
        if state.closed {
            return Ok(());
        }
        if !state.finalized {
            self.finalize_locked(py, &mut state)?;
        }
        if self.should_close_stream {
            self.stream.call_method0(py, "close")?;
        }
        state.closed = true;
        Ok(())
    }

    fn __enter__(slf: Py<Self>) -> Py<Self> {
        slf
    }

    // __exit__ の引数は Python 側では位置引数として (exc_type, exc_val, exc_tb) が
    // 期待されるため、キーワード呼び出しに配慮して leading underscore を外す。
    // Rust 側で参照を破棄したいだけなので `&Bound<'_, PyAny>` にして refcount 操作を避ける。
    #[pyo3(signature = (exc_type, exc_val, exc_tb))]
    #[allow(unused_variables)]
    fn __exit__(
        &self,
        py: Python<'_>,
        exc_type: &Bound<'_, PyAny>,
        exc_val: &Bound<'_, PyAny>,
        exc_tb: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        self.close(py)?;
        Ok(false)
    }
}

// ===== Mp4FileDemuxer (on-demand loading) =====

// next_sample から取得したサンプル情報を、state.core のライフタイムから切り離して
// 持ち出すためのタプル型。フィールドの意味は以下のとおり:
// (track_id, data_offset, data_size, keyframe, timestamp, duration,
//  composition_time_offset, sample_entry)
type NextSampleExtracted = (
    u32,
    u64,
    u64,
    bool,
    u64,
    u32,
    Option<i64>,
    Option<shiguredo_mp4::boxes::SampleEntry>,
);

struct DemuxerState {
    core: CoreDemuxer,
    closed: bool,
    tracks_cache: Option<Vec<Py<Mp4TrackInfo>>>,
    // demuxer が「終端に達した」もしくは「回復不能なエラー」を返した後は、
    // これ以上サンプルを取ろうとしない
    ended: bool,
}

#[pyclass(module = "mp4.mp4_ext", frozen, skip_from_py_object)]
struct Mp4FileDemuxer {
    state: Mutex<DemuxerState>,
    input_stream: Py<PyAny>,
    // input_stream への seek + read を Demuxer 本体と各 Mp4DemuxSample の間で
    // 直列化するためのロック。Free-Threading 環境で複数スレッドが sample.data を
    // 触ったときにファイル位置が競合しないようにする。
    // Arc にしているのは Mp4DemuxSample にも clone_ref して同じロックを共有させるため。
    stream_lock: Arc<Mutex<()>>,
    should_close_stream: bool,
}

impl Mp4FileDemuxer {
    // 必要なデータをストリームから供給する。真の EOF に達したら true を返す。
    // lock 済みの state を受け取る (lock 中に IO する)。
    // stream_lock は内部で個別に取得し、sample.data と直列化する。
    fn feed_required_input(&self, py: Python<'_>, state: &mut DemuxerState) -> PyResult<bool> {
        let mut iterations = 0;
        loop {
            iterations += 1;
            if iterations > MAX_FEED_ITERATIONS {
                return Err(Mp4Exception::new_err(
                    "feed_required_input: too many iterations (possible infinite loop on corrupted data)",
                ));
            }
            let Some(RequiredInput { position, size }) = state.core.required_input() else {
                return Ok(false);
            };
            if position > i64::MAX as u64 {
                return Err(Mp4Exception::new_err(format!(
                    "Required input position too large (corrupted data?): {position}"
                )));
            }
            if let Some(n) = size
                && n as u64 > i64::MAX as u64
            {
                return Err(Mp4Exception::new_err(format!(
                    "Required input size too large (corrupted data?): {n}"
                )));
            }
            // seek + read の間に別スレッドが入って位置を移動させないよう、
            // 1 回の読み込みは必ず stream_lock のロック内で完結させる。
            let read: Py<PyBytes> = {
                let _guard = self
                    .stream_lock
                    .lock_py_attached(py)
                    .map_err(|_| poisoned_err("demuxer stream lock"))?;
                self.input_stream.call_method1(py, "seek", (position,))?;
                match size {
                    Some(n) => self
                        .input_stream
                        .call_method1(py, "read", (n,))?
                        .extract(py)?,
                    None => self.input_stream.call_method0(py, "read")?.extract(py)?,
                }
            };
            let data = read.bind(py).as_bytes();
            state.core.handle_input(DemuxInput { position, data });
            if let Some(n) = size {
                if data.len() < n {
                    return Ok(true);
                }
            } else if data.is_empty() {
                return Ok(true);
            }
        }
    }

    fn ensure_tracks(&self, py: Python<'_>, state: &mut DemuxerState) -> PyResult<()> {
        if state.tracks_cache.is_some() || state.ended {
            return Ok(());
        }
        loop {
            match state.core.tracks() {
                Ok(tracks) => {
                    let mut cache = Vec::with_capacity(tracks.len());
                    for t in tracks {
                        let info = Mp4TrackInfo {
                            track_id: t.track_id,
                            kind: track_kind_to_str(t.kind).to_owned(),
                            duration: t.duration,
                            timescale: t.timescale.get(),
                        };
                        cache.push(Py::new(py, info)?);
                    }
                    state.tracks_cache = Some(cache);
                    return Ok(());
                }
                Err(DemuxError::InputRequired(_)) => {
                    if self.feed_required_input(py, state)? {
                        state.tracks_cache = Some(Vec::new());
                        state.ended = true;
                        return Ok(());
                    }
                }
                Err(_) => {
                    state.tracks_cache = Some(Vec::new());
                    state.ended = true;
                    return Ok(());
                }
            }
        }
    }
}

#[pymethods]
impl Mp4FileDemuxer {
    #[new]
    fn new(py: Python<'_>, source: Py<PyAny>) -> PyResult<Self> {
        let (stream, should_close) = {
            let src = source.bind(py);
            if src.cast::<PyBytes>().is_ok() {
                let io = py.import("io")?;
                let bytes_io = io.call_method1("BytesIO", (source,))?;
                (bytes_io.unbind(), true)
            } else if is_pathlike(src)? {
                let builtins = py.import("builtins")?;
                let opened = builtins.call_method1("open", (source, "rb"))?;
                (opened.unbind(), true)
            } else {
                (source, false)
            }
        };
        Ok(Self {
            state: Mutex::new(DemuxerState {
                core: CoreDemuxer::new(),
                closed: false,
                tracks_cache: None,
                ended: false,
            }),
            input_stream: stream,
            stream_lock: Arc::new(Mutex::new(())),
            should_close_stream: should_close,
        })
    }

    #[getter]
    fn tracks(&self, py: Python<'_>) -> PyResult<Vec<Py<Mp4TrackInfo>>> {
        let mut state = self
            .state
            .lock_py_attached(py)
            .map_err(|_| poisoned_err("demuxer"))?;
        if state.closed {
            return Err(PyRuntimeError::new_err("demuxer is closed"));
        }
        self.ensure_tracks(py, &mut state)?;
        Ok(state
            .tracks_cache
            .as_ref()
            .unwrap()
            .iter()
            .map(|t| t.clone_ref(py))
            .collect())
    }

    fn __iter__(slf: Py<Self>) -> Py<Self> {
        slf
    }

    fn __next__(&self, py: Python<'_>) -> PyResult<Py<Mp4DemuxSample>> {
        let mut state = self
            .state
            .lock_py_attached(py)
            .map_err(|_| poisoned_err("demuxer"))?;
        if state.closed {
            return Err(PyStopIteration::new_err(()));
        }
        self.ensure_tracks(py, &mut state)?;
        if state.ended {
            return Err(PyStopIteration::new_err(()));
        }

        loop {
            // sample のライフタイムを state.core と切り離すため、Ok(Some(_)) 内で
            // 必要な情報をすべてコピー・クローンしてから外の処理に移る。
            let extracted: Option<NextSampleExtracted> = match state.core.next_sample() {
                Ok(Some(sample)) => {
                    if sample.data_size as u64 > MAX_SAMPLE_SIZE {
                        return Err(Mp4Exception::new_err(format!(
                            "Sample data size too large (corrupted data?): {} bytes",
                            sample.data_size
                        )));
                    }
                    Some((
                        sample.track.track_id,
                        sample.data_offset,
                        sample.data_size as u64,
                        sample.keyframe,
                        sample.timestamp,
                        sample.duration,
                        sample.composition_time_offset,
                        sample.sample_entry.cloned(),
                    ))
                }
                Ok(None) => {
                    state.ended = true;
                    return Err(PyStopIteration::new_err(()));
                }
                Err(DemuxError::InputRequired(_)) => {
                    if self.feed_required_input(py, &mut state)? {
                        state.ended = true;
                        return Err(PyStopIteration::new_err(()));
                    }
                    continue;
                }
                Err(_) => {
                    state.ended = true;
                    return Err(PyStopIteration::new_err(()));
                }
            };

            if let Some((
                track_id,
                data_offset,
                data_size,
                keyframe,
                timestamp,
                duration,
                composition_time_offset,
                sample_entry_owned,
            )) = extracted
            {
                let sample_entry_py = sample_entry_owned
                    .as_ref()
                    .map(|se| sample_entry_from_core(py, se))
                    .transpose()?
                    .flatten();
                let track_py = state
                    .tracks_cache
                    .as_ref()
                    .and_then(|c| c.iter().find(|t| t.borrow(py).track_id == track_id))
                    .map(|t| t.clone_ref(py))
                    .ok_or_else(|| map_err("track not found in cache"))?;

                let out = Mp4DemuxSample {
                    track: track_py,
                    sample_entry: sample_entry_py,
                    keyframe,
                    timestamp,
                    duration,
                    composition_time_offset,
                    data_offset,
                    data_size,
                    input_stream: self.input_stream.clone_ref(py),
                    // Demuxer と同じロックを共有し、sample.data と feed_required_input の
                    // 間で input_stream を直列化する。
                    stream_lock: Arc::clone(&self.stream_lock),
                    data_cache: Mutex::new(None),
                };
                return Py::new(py, out);
            }
        }
    }

    fn close(&self, py: Python<'_>) -> PyResult<()> {
        let mut state = self
            .state
            .lock_py_attached(py)
            .map_err(|_| poisoned_err("demuxer"))?;
        if state.closed {
            return Ok(());
        }
        if self.should_close_stream {
            self.input_stream.call_method0(py, "close")?;
        }
        state.closed = true;
        Ok(())
    }

    fn __enter__(slf: Py<Self>) -> Py<Self> {
        slf
    }

    // Muxer 側と揃えて、キーワード呼び出しに配慮して leading underscore を外し、
    // Bound を参照で受けて余分な refcount 操作を避ける。
    #[pyo3(signature = (exc_type, exc_val, exc_tb))]
    #[allow(unused_variables)]
    fn __exit__(
        &self,
        py: Python<'_>,
        exc_type: &Bound<'_, PyAny>,
        exc_val: &Bound<'_, PyAny>,
        exc_tb: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        self.close(py)?;
        Ok(false)
    }
}

// ===== モジュール登録 =====

// [NOTE] PyO3 の experimental-inspect による .pyi 生成は inline module 形式でしか
// 動作しない (関数形式 `#[pymodule] fn mod_name` は非対応)。ここでは既存の型定義を
// そのまま参照する形で inline module を構成する。
// PyO3 0.28 以降は `gil_used = false` が既定なので明示指定は不要。
#[pymodule]
mod mp4_ext {
    #[pymodule_export]
    use super::{
        Mp4DemuxSample, Mp4Exception, Mp4FileDemuxer, Mp4FileMuxer, Mp4FileMuxerOptions,
        Mp4MuxSample, Mp4SampleEntryAv01, Mp4SampleEntryAvc1, Mp4SampleEntryFlac,
        Mp4SampleEntryHev1, Mp4SampleEntryHvc1, Mp4SampleEntryMp4a, Mp4SampleEntryOpus,
        Mp4SampleEntryStpp, Mp4SampleEntryTx3g, Mp4SampleEntryVp08, Mp4SampleEntryVp09,
        Mp4SampleEntryWvtt, Mp4TrackInfo, Mp4TrackMetadata, estimate_maximum_moov_box_size,
        library_version,
    };
}
