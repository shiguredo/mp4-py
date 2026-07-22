//! shiguredo_mp4 の PyO3 バインディング (nanobind 版と全機能パリティを目指す)

use std::num::NonZeroU32;
use std::sync::Mutex;
use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyStopIteration, PyValueError};
use pyo3::prelude::*;
use pyo3::sync::MutexExt;
use pyo3::types::{PyBytes, PyString, PyType};
use pyo3::{Py, PyAny};

// PyO3 0.29 で `pyo3::PyObject` の型 alias が削除されたため、下流で使いやすいように張り直す。
type PyObject = Py<PyAny>;

use shiguredo_mp4::{
    FixedPointNumber, TrackKind, Uint,
    boxes::{
        Av01Box, Av1cBox, Avc1Box, AvccBox, AudioSampleEntryFields, DflaBox, DopsBox, EsdsBox,
        FlacBox, FlacMetadataBlock, Hev1Box, Hvc1Box, HvccBox, HvccNalUintArray, Mp4aBox, OpusBox,
        SampleEntry, VisualSampleEntryFields, Vp08Box, Vp09Box, VpccBox,
    },
    demux::{
        DemuxError, Input as DemuxInput, Mp4FileDemuxer as CoreDemuxer, RequiredInput,
    },
    descriptors::{DecoderConfigDescriptor, DecoderSpecificInfo, EsDescriptor, SlConfigDescriptor},
    mux::{
        Mp4FileMuxer as CoreMuxer, Mp4FileMuxerOptions as CoreMuxerOptions,
        Sample as CoreMuxSample, estimate_maximum_moov_box_size as core_estimate_moov,
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
fn estimate_maximum_moov_box_size(audio_sample_count: u32, video_sample_count: u32) -> usize {
    core_estimate_moov(&[audio_sample_count as usize, video_sample_count as usize])
}

fn map_err<E: std::fmt::Display>(e: E) -> PyErr {
    PyRuntimeError::new_err(format!("mp4 error: {e}"))
}

fn track_kind_to_str(kind: TrackKind) -> &'static str {
    match kind {
        TrackKind::Audio => "audio",
        TrackKind::Video => "video",
    }
}

fn str_to_track_kind(s: &str) -> PyResult<TrackKind> {
    match s {
        "audio" => Ok(TrackKind::Audio),
        "video" => Ok(TrackKind::Video),
        other => Err(PyValueError::new_err(format!(
            "invalid track_kind: {other:?} (expected 'audio' or 'video')"
        ))),
    }
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

// Python の bytes-like (bytes / bytearray / memoryview / buffer protocol 対応) を Vec<u8> に変換する。
// nanobind 版は Python の builtins.bytes(iterable) にフォールバックしていたが、
// PyO3 0.29 では PyBuffer 経由でゼロ経路が短くなる。
fn extract_bytes(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    // 高速パス: すでに bytes ならスライスをそのままコピー
    if let Ok(b) = obj.cast::<PyBytes>() {
        return Ok(b.as_bytes().to_vec());
    }
    // 汎用パス: buffer protocol 経由 (bytearray / memoryview / array.array 等)
    if let Ok(buf) = pyo3::buffer::PyBuffer::<u8>::get(obj) {
        return buf.to_vec(py);
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
    ) -> Self {
        Self {
            width,
            height,
            bit_depth,
            chroma_subsampling,
            video_full_range_flag,
            colour_primaries,
            transfer_characteristics,
            matrix_coefficients,
        }
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
    ) -> Self {
        Self {
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
        }
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
            initial_presentation_delay_present: b.av1c_box.initial_presentation_delay_minus_one.is_some(),
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
        }
    }
}

fn sample_entry_from_core(py: Python<'_>, entry: &SampleEntry) -> PyResult<Option<Mp4SampleEntryAny>> {
    let out = match entry {
        SampleEntry::Vp08(b) => Mp4SampleEntryAny::Vp08(Py::new(py, Mp4SampleEntryVp08::from_box(b))?),
        SampleEntry::Vp09(b) => Mp4SampleEntryAny::Vp09(Py::new(py, Mp4SampleEntryVp09::from_box(b))?),
        SampleEntry::Avc1(b) => Mp4SampleEntryAny::Avc1(Py::new(py, Mp4SampleEntryAvc1::from_box(b))?),
        SampleEntry::Hev1(b) => Mp4SampleEntryAny::Hev1(Py::new(py, Mp4SampleEntryHev1::from_box(b))?),
        SampleEntry::Hvc1(b) => Mp4SampleEntryAny::Hvc1(Py::new(py, Mp4SampleEntryHvc1::from_box(b))?),
        SampleEntry::Av01(b) => Mp4SampleEntryAny::Av01(Py::new(py, Mp4SampleEntryAv01::from_box(b))?),
        SampleEntry::Opus(b) => Mp4SampleEntryAny::Opus(Py::new(py, Mp4SampleEntryOpus::from_box(b))?),
        SampleEntry::Mp4a(b) => Mp4SampleEntryAny::Mp4a(Py::new(py, Mp4SampleEntryMp4a::from_box(b))?),
        SampleEntry::Flac(b) => Mp4SampleEntryAny::Flac(Py::new(py, Mp4SampleEntryFlac::from_box(b))?),
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

#[pyclass(module = "mp4.mp4_ext", skip_from_py_object)]
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
    input_stream: PyObject,
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
        input_stream: PyObject,
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
            data_cache: Mutex::new(None),
        }
    }

    #[getter]
    fn sample_entry(&self, py: Python<'_>) -> Option<Mp4SampleEntryAny> {
        self.sample_entry.as_ref().map(|s| s.clone_ref(py))
    }

    #[getter]
    fn data(&self, py: Python<'_>) -> PyResult<Py<PyBytes>> {
        {
            let cache = self.data_cache.lock_py_attached(py).unwrap();
            if let Some(ref b) = *cache {
                return Ok(b.clone_ref(py));
            }
        }
        // 破損データで巨大な値になっている可能性を弾く
        if self.data_size > MAX_SAMPLE_SIZE {
            return Err(map_err(format!(
                "Sample data size too large (corrupted data?): {} bytes (max: {} bytes)",
                self.data_size, MAX_SAMPLE_SIZE
            )));
        }
        self.input_stream.call_method1(py, "seek", (self.data_offset,))?;
        let read: Py<PyBytes> = self
            .input_stream
            .call_method1(py, "read", (self.data_size,))?
            .extract(py)?;
        if read.bind(py).as_bytes().len() as u64 != self.data_size {
            return Err(map_err(format!(
                "Failed to read sample data: expected {} bytes, got {}",
                self.data_size,
                read.bind(py).as_bytes().len()
            )));
        }
        *self.data_cache.lock_py_attached(py).unwrap() = Some(read.clone_ref(py));
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

// ===== Mp4FileMuxerOptions =====

#[pyclass(module = "mp4.mp4_ext", from_py_object)]
#[derive(Clone)]
struct Mp4FileMuxerOptions {
    #[pyo3(get)]
    reserved_moov_box_size: usize,
}

#[pymethods]
impl Mp4FileMuxerOptions {
    #[new]
    #[pyo3(signature = (reserved_moov_box_size = 0))]
    fn new(reserved_moov_box_size: usize) -> Self {
        Self {
            reserved_moov_box_size,
        }
    }

    #[classmethod]
    fn estimate_maximum_moov_box_size(
        _cls: &Bound<'_, PyType>,
        audio_sample_count: u32,
        video_sample_count: u32,
    ) -> usize {
        core_estimate_moov(&[audio_sample_count as usize, video_sample_count as usize])
    }
}

// ===== Mp4FileMuxer =====

// Free-Threading 対応: メソッドを &self に統一し、内部状態を Mutex で保護する。
// nanobind の ft_mutex 相当のブロッキング動作をシミュレートする。
struct MuxerState {
    core: Option<CoreMuxer>,
    finalized: bool,
    closed: bool,
}

#[pyclass(module = "mp4.mp4_ext", frozen, skip_from_py_object)]
struct Mp4FileMuxer {
    state: Mutex<MuxerState>,
    stream: PyObject,
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
}

#[pymethods]
impl Mp4FileMuxer {
    #[new]
    #[pyo3(signature = (destination, options = None))]
    fn new(
        py: Python<'_>,
        destination: PyObject,
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
            .map(|o| CoreMuxerOptions {
                reserved_moov_box_size: o.reserved_moov_box_size,
                creation_timestamp: Duration::ZERO,
            })
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
        let mut state = self.state.lock_py_attached(py).unwrap();
        if state.closed {
            return Err(PyRuntimeError::new_err("muxer is closed"));
        }
        let core = state
            .core
            .as_mut()
            .ok_or_else(|| PyRuntimeError::new_err("muxer already dropped"))?;

        let data_offset: u64 = self.stream.call_method0(py, "tell")?.extract(py)?;
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
    }

    fn finalize(&self, py: Python<'_>) -> PyResult<()> {
        let mut state = self.state.lock_py_attached(py).unwrap();
        self.finalize_locked(py, &mut state)
    }

    fn close(&self, py: Python<'_>) -> PyResult<()> {
        let mut state = self.state.lock_py_attached(py).unwrap();
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

    #[pyo3(signature = (_exc_type, _exc_val, _exc_tb))]
    fn __exit__(
        &self,
        py: Python<'_>,
        _exc_type: Bound<'_, PyAny>,
        _exc_val: Bound<'_, PyAny>,
        _exc_tb: Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        self.close(py)?;
        Ok(false)
    }
}

// ===== Mp4FileDemuxer (on-demand loading) =====

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
    input_stream: PyObject,
    should_close_stream: bool,
}

impl Mp4FileDemuxer {
    // 必要なデータをストリームから供給する。真の EOF に達したら true を返す。
    // lock 済みの state を受け取る (lock 中に IO する)
    fn feed_required_input(&self, py: Python<'_>, state: &mut DemuxerState) -> PyResult<bool> {
        let mut iterations = 0;
        loop {
            iterations += 1;
            if iterations > MAX_FEED_ITERATIONS {
                return Err(map_err(
                    "feed_required_input: too many iterations (possible infinite loop on corrupted data)",
                ));
            }
            let Some(RequiredInput { position, size }) = state.core.required_input() else {
                return Ok(false);
            };
            if position > i64::MAX as u64 {
                return Err(map_err(format!(
                    "Required input position too large (corrupted data?): {position}"
                )));
            }
            if let Some(n) = size {
                if n as u64 > i64::MAX as u64 {
                    return Err(map_err(format!(
                        "Required input size too large (corrupted data?): {n}"
                    )));
                }
            }
            self.input_stream.call_method1(py, "seek", (position,))?;
            let read: Py<PyBytes> = match size {
                Some(n) => self
                    .input_stream
                    .call_method1(py, "read", (n,))?
                    .extract(py)?,
                None => self.input_stream.call_method0(py, "read")?.extract(py)?,
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
    fn new(py: Python<'_>, source: PyObject) -> PyResult<Self> {
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
            should_close_stream: should_close,
        })
    }

    #[getter]
    fn tracks(&self, py: Python<'_>) -> PyResult<Vec<Py<Mp4TrackInfo>>> {
        let mut state = self.state.lock_py_attached(py).unwrap();
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
        let mut state = self.state.lock_py_attached(py).unwrap();
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
            let extracted: Option<(
                u32,
                u64,
                u64,
                bool,
                u64,
                u32,
                Option<i64>,
                Option<shiguredo_mp4::boxes::SampleEntry>,
            )> = match state.core.next_sample() {
                Ok(Some(sample)) => {
                    if sample.data_size as u64 > MAX_SAMPLE_SIZE {
                        return Err(map_err(format!(
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
                    data_cache: Mutex::new(None),
                };
                return Py::new(py, out);
            }
        }
    }

    fn close(&self, py: Python<'_>) -> PyResult<()> {
        let mut state = self.state.lock_py_attached(py).unwrap();
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

    #[pyo3(signature = (_exc_type, _exc_val, _exc_tb))]
    fn __exit__(
        &self,
        py: Python<'_>,
        _exc_type: Bound<'_, PyAny>,
        _exc_val: Bound<'_, PyAny>,
        _exc_tb: Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        self.close(py)?;
        Ok(false)
    }
}

// ===== モジュール登録 =====

// [NOTE] PyO3 の experimental-inspect による .pyi 生成は inline module 形式でしか
// 動作しない (関数形式 `#[pymodule] fn mod_name` は非対応)。ここでは既存の型定義を
// そのまま参照する形で inline module を構成する。
#[pymodule(gil_used = false)]
mod mp4_ext {
    #[pymodule_export]
    use super::{
        Mp4DemuxSample, Mp4FileDemuxer, Mp4FileMuxer, Mp4FileMuxerOptions, Mp4MuxSample,
        Mp4SampleEntryAv01, Mp4SampleEntryAvc1, Mp4SampleEntryFlac, Mp4SampleEntryHev1,
        Mp4SampleEntryHvc1, Mp4SampleEntryMp4a, Mp4SampleEntryOpus, Mp4SampleEntryVp08,
        Mp4SampleEntryVp09, Mp4TrackInfo, estimate_maximum_moov_box_size, library_version,
    };
}
