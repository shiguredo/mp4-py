//! shiguredo_mp4 の PyO3 バインディング (投資判断のための調査プロトタイプ)
//!
//! MVP スコープ:
//! - library_version
//! - estimate_maximum_moov_box_size
//! - Mp4SampleEntryVp08
//! - Mp4TrackInfo / Mp4MuxSample / Mp4DemuxSample
//! - Mp4FileMuxerOptions / Mp4FileMuxer
//! - Mp4FileDemuxer

use std::num::NonZeroU32;
use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyType};

use shiguredo_mp4::{
    Encode, TrackKind, Uint,
    boxes::{SampleEntry, VisualSampleEntryFields, Vp08Box, VpccBox},
    demux::{Input as DemuxInput, Mp4FileDemuxer as CoreDemuxer},
    mux::{
        Mp4FileMuxer as CoreMuxer, Mp4FileMuxerOptions as CoreMuxerOptions,
        Sample as CoreMuxSample, estimate_maximum_moov_box_size as core_estimate_moov,
    },
};

// ===== ユーティリティ =====

#[pyfunction]
fn library_version() -> &'static str {
    env!("SHIGUREDO_MP4_VERSION")
}

#[pyfunction]
fn estimate_maximum_moov_box_size(audio_sample_count: u32, video_sample_count: u32) -> usize {
    // nanobind 版と揃えて (audio, video) の 2 引数 API にする。
    core_estimate_moov(&[audio_sample_count as usize, video_sample_count as usize])
}

// ===== TrackKind の Python 表現 =====
// Python 側は "audio" / "video" の str リテラル型で扱う (nanobind 版と互換)。

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

// ===== Mp4SampleEntryVp08 =====

#[pyclass(module = "mp4_pyo3.mp4_pyo3_ext")]
#[derive(Clone)]
struct Mp4SampleEntryVp08 {
    #[pyo3(get, set)]
    width: u16,
    #[pyo3(get, set)]
    height: u16,
    #[pyo3(get, set)]
    bit_depth: u8,
    #[pyo3(get, set)]
    chroma_subsampling: u8,
    #[pyo3(get, set)]
    video_full_range_flag: bool,
    #[pyo3(get, set)]
    colour_primaries: u8,
    #[pyo3(get, set)]
    transfer_characteristics: u8,
    #[pyo3(get, set)]
    matrix_coefficients: u8,
}

#[pymethods]
impl Mp4SampleEntryVp08 {
    #[new]
    #[pyo3(signature = (
        width,
        height,
        bit_depth = 8,
        chroma_subsampling = 1,
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
    // shiguredo_mp4 側の SampleEntry を組み立てる。
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
        let visual = VisualSampleEntryFields {
            data_reference_index: VisualSampleEntryFields::DEFAULT_DATA_REFERENCE_INDEX,
            width: self.width,
            height: self.height,
            horizresolution: VisualSampleEntryFields::DEFAULT_HORIZRESOLUTION,
            vertresolution: VisualSampleEntryFields::DEFAULT_VERTRESOLUTION,
            frame_count: VisualSampleEntryFields::DEFAULT_FRAME_COUNT,
            compressorname: VisualSampleEntryFields::NULL_COMPRESSORNAME,
            depth: VisualSampleEntryFields::DEFAULT_DEPTH,
        };
        SampleEntry::Vp08(Vp08Box {
            visual,
            vpcc_box,
            unknown_boxes: Vec::new(),
        })
    }
}

// ===== Mp4TrackInfo =====

#[pyclass(module = "mp4_pyo3.mp4_pyo3_ext")]
#[derive(Clone)]
struct Mp4TrackInfo {
    #[pyo3(get)]
    track_id: u32,
    #[pyo3(get)]
    kind: &'static str,
    #[pyo3(get)]
    duration: u64,
    #[pyo3(get)]
    timescale: u32,
}

#[pymethods]
impl Mp4TrackInfo {
    fn __repr__(&self) -> String {
        format!(
            "Mp4TrackInfo(track_id={}, kind={:?}, duration={}, timescale={})",
            self.track_id, self.kind, self.duration, self.timescale
        )
    }
}

// ===== Mp4MuxSample =====

#[pyclass(module = "mp4_pyo3.mp4_pyo3_ext")]
struct Mp4MuxSample {
    #[pyo3(get, set)]
    track_kind: String,
    // sample_entry は現状 Vp08 のみ受け付ける (MVP 制約)。None なら「前のサンプルと同じ」
    sample_entry: Option<Py<Mp4SampleEntryVp08>>,
    #[pyo3(get, set)]
    keyframe: bool,
    #[pyo3(get, set)]
    timescale: u32,
    #[pyo3(get, set)]
    duration: u32,
    #[pyo3(get, set)]
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
        track_kind: String,
        sample_entry: Option<Py<Mp4SampleEntryVp08>>,
        keyframe: bool,
        timescale: u32,
        duration: u32,
        data: Py<PyBytes>,
        composition_time_offset: Option<i64>,
    ) -> Self {
        Self {
            track_kind,
            sample_entry,
            keyframe,
            timescale,
            duration,
            composition_time_offset,
            data,
        }
    }

    #[getter]
    fn sample_entry(&self, py: Python<'_>) -> Option<Py<Mp4SampleEntryVp08>> {
        self.sample_entry.as_ref().map(|s| s.clone_ref(py))
    }

    #[setter]
    fn set_sample_entry(&mut self, value: Option<Py<Mp4SampleEntryVp08>>) {
        self.sample_entry = value;
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

// ===== Mp4DemuxSample =====

#[pyclass(module = "mp4_pyo3.mp4_pyo3_ext")]
struct Mp4DemuxSample {
    #[pyo3(get)]
    track: Py<Mp4TrackInfo>,
    #[pyo3(get)]
    keyframe: bool,
    #[pyo3(get)]
    timestamp: u64,
    #[pyo3(get)]
    duration: u32,
    #[pyo3(get)]
    composition_time_offset: Option<i64>,
    data: Py<PyBytes>,
}

#[pymethods]
impl Mp4DemuxSample {
    #[getter]
    fn data(&self, py: Python<'_>) -> Py<PyBytes> {
        self.data.clone_ref(py)
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        let size = self.data.bind(py).as_bytes().len();
        let tid = self.track.borrow(py).track_id;
        format!(
            "Mp4DemuxSample(track_id={}, keyframe={}, timestamp={}, duration={}, data_size={})",
            tid, self.keyframe, self.timestamp, self.duration, size
        )
    }
}

// ===== Mp4FileMuxerOptions =====

#[pyclass(module = "mp4_pyo3.mp4_pyo3_ext")]
#[derive(Clone)]
struct Mp4FileMuxerOptions {
    #[pyo3(get, set)]
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

// Python の file-like object を保持し、seek/write/tell を委譲する。
// nanobind 版と同じセマンティクス:
// - 出力先に __fspath__ / str が渡された場合は open(path, "wb") で開く
// - 通常のオブジェクトはそのまま使う (呼び出し側の close() 責務)
#[pyclass(module = "mp4_pyo3.mp4_pyo3_ext", unsendable)]
struct Mp4FileMuxer {
    core: Option<CoreMuxer>,
    stream: PyObject,
    should_close_stream: bool,
    finalized: bool,
    closed: bool,
}

fn map_mux_err<E: std::fmt::Display>(e: E) -> PyErr {
    PyRuntimeError::new_err(format!("mp4 mux error: {e}"))
}

impl Mp4FileMuxer {
    fn write_initial(&self, py: Python<'_>) -> PyResult<()> {
        let core = self.core.as_ref().expect("muxer available");
        let initial = core.initial_boxes_bytes();
        self.stream
            .call_method1(py, "write", (PyBytes::new(py, initial),))?;
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
        // ファイルパス風の入力なら builtins.open で開く。
        let (stream, should_close) = {
            let dst = destination.bind(py);
            let is_pathlike = dst.hasattr("__fspath__")? || dst.is_instance_of::<pyo3::types::PyString>();
            if is_pathlike {
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
        let core = CoreMuxer::with_options(core_options).map_err(map_mux_err)?;

        let this = Self {
            core: Some(core),
            stream,
            should_close_stream: should_close,
            finalized: false,
            closed: false,
        };
        this.write_initial(py)?;
        Ok(this)
    }

    fn append_sample(&mut self, py: Python<'_>, sample: &Mp4MuxSample) -> PyResult<()> {
        if self.closed {
            return Err(PyRuntimeError::new_err("muxer is closed"));
        }
        let core = self
            .core
            .as_mut()
            .ok_or_else(|| PyRuntimeError::new_err("muxer already dropped"))?;

        // 出力ストリームの現在位置とサンプルデータを取得する。
        let data_offset: u64 = self.stream.call_method0(py, "tell")?.extract(py)?;
        let data_bytes = sample.data.bind(py).as_bytes();

        // sample.data の書きこみを先に済ませる (nanobind 版と揃える)。
        self.stream
            .call_method1(py, "write", (PyBytes::new(py, data_bytes),))?;

        let timescale = NonZeroU32::new(sample.timescale)
            .ok_or_else(|| PyValueError::new_err("timescale must be non-zero"))?;
        let track_kind = str_to_track_kind(&sample.track_kind)?;
        let sample_entry_opt = sample
            .sample_entry
            .as_ref()
            .map(|e| e.borrow(py).to_sample_entry());

        let core_sample = CoreMuxSample {
            track_kind,
            sample_entry: sample_entry_opt,
            keyframe: sample.keyframe,
            timescale,
            duration: sample.duration,
            composition_time_offset: sample.composition_time_offset,
            data_offset,
            data_size: data_bytes.len(),
        };

        core.append_sample(&core_sample).map_err(map_mux_err)?;
        Ok(())
    }

    fn finalize(&mut self, py: Python<'_>) -> PyResult<()> {
        self.finalize_internal(py)
    }

    fn close(&mut self, py: Python<'_>) -> PyResult<()> {
        if self.closed {
            return Ok(());
        }
        if !self.finalized {
            // ベストエフォート: append 済みなら finalize、そうでなければ 0 サンプルで失敗するのでスキップ判定
            // (nanobind 版は無条件に呼んでエラーは伝播させる)
            self.finalize_internal(py)?;
        }
        if self.should_close_stream {
            self.stream.call_method0(py, "close")?;
        }
        self.closed = true;
        Ok(())
    }

    fn __enter__(slf: Py<Self>) -> Py<Self> {
        slf
    }

    #[pyo3(signature = (_exc_type, _exc_val, _exc_tb))]
    fn __exit__(
        &mut self,
        py: Python<'_>,
        _exc_type: Bound<'_, PyAny>,
        _exc_val: Bound<'_, PyAny>,
        _exc_tb: Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        self.close(py)?;
        Ok(false)
    }
}

impl Mp4FileMuxer {
    fn finalize_internal(&mut self, py: Python<'_>) -> PyResult<()> {
        if self.finalized {
            return Ok(());
        }
        let core = self
            .core
            .as_mut()
            .ok_or_else(|| PyRuntimeError::new_err("muxer already dropped"))?;
        let finalized = core.finalize().map_err(map_mux_err)?;

        // moov / mdat ヘッダなど、ファイル完成に必要なバイト列を対応するオフセットに書きこむ。
        for (offset, bytes) in finalized.offset_and_bytes_pairs() {
            self.stream.call_method1(py, "seek", (offset,))?;
            self.stream
                .call_method1(py, "write", (PyBytes::new(py, bytes),))?;
        }
        self.finalized = true;
        Ok(())
    }
}

// ===== Mp4FileDemuxer =====

// 現状はファイル全体をメモリに読みこんで一括で handle_input する簡易実装。
// nanobind 版は C API の on-demand loading を使うが、プロトタイプでは省略する。
#[pyclass(module = "mp4_pyo3.mp4_pyo3_ext", unsendable)]
struct Mp4FileDemuxer {
    core: CoreDemuxer,
    // handle_input に渡すデータの所有権を Demuxer 側に持たせる。
    // ここで確保した Vec<u8> のポインタが有効な間だけ Mp4FileDemuxer は動く。
    _buffer: Vec<u8>,
    // 上と同一データを Py<PyBytes> でも保持して、切り出しコストを削減する。
    buffer_bytes: Py<PyBytes>,
    tracks_cache: Vec<Py<Mp4TrackInfo>>,
}

#[pymethods]
impl Mp4FileDemuxer {
    #[new]
    fn new(py: Python<'_>, source: PyObject) -> PyResult<Self> {
        // 入力を全部読み込む (ファイルパス / bytes / file-like いずれにも対応)。
        let bytes_obj: Py<PyBytes> = {
            let src = source.bind(py);
            if let Ok(b) = src.downcast::<PyBytes>() {
                b.clone().unbind()
            } else if src.hasattr("__fspath__")? || src.is_instance_of::<pyo3::types::PyString>() {
                let builtins = py.import("builtins")?;
                let f = builtins.call_method1("open", (source, "rb"))?;
                let read: Py<PyBytes> = f.call_method0("read")?.extract()?;
                f.call_method0("close")?;
                read
            } else {
                // file-like: read() を呼ぶ
                let read: Py<PyBytes> = src.call_method0("read")?.extract()?;
                read
            }
        };

        let buffer: Vec<u8> = bytes_obj.bind(py).as_bytes().to_vec();
        let mut core = CoreDemuxer::new();
        core.handle_input(DemuxInput {
            position: 0,
            data: &buffer,
        });
        let tracks_raw = core.tracks().map_err(map_mux_err)?;
        let mut tracks_cache = Vec::with_capacity(tracks_raw.len());
        for t in tracks_raw {
            let info = Mp4TrackInfo {
                track_id: t.track_id,
                kind: track_kind_to_str(t.kind),
                duration: t.duration,
                timescale: t.timescale.get(),
            };
            tracks_cache.push(Py::new(py, info)?);
        }

        Ok(Self {
            core,
            _buffer: buffer,
            buffer_bytes: bytes_obj,
            tracks_cache,
        })
    }

    #[getter]
    fn tracks(&self, py: Python<'_>) -> Vec<Py<Mp4TrackInfo>> {
        self.tracks_cache.iter().map(|t| t.clone_ref(py)).collect()
    }

    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Py<Mp4DemuxSample>>> {
        let sample_opt = self.core.next_sample().map_err(map_mux_err)?;
        let Some(sample) = sample_opt else {
            return Ok(None);
        };

        // Sample<'_> は demuxer を借りているので、必要な情報を全部コピーしてから抜ける。
        let track_id = sample.track.track_id;
        let track_py = self
            .tracks_cache
            .iter()
            .find_map(|t| {
                let borrow = t.borrow(py);
                if borrow.track_id == track_id {
                    Some(t.clone_ref(py))
                } else {
                    None
                }
            })
            .ok_or_else(|| PyRuntimeError::new_err("track not found in cache"))?;

        // sample.data_offset は入力データ内 (= self.buffer_bytes) のオフセット
        let offset = sample.data_offset as usize;
        let end = offset + sample.data_size;
        let data_slice = &self.buffer_bytes.bind(py).as_bytes()[offset..end];
        let data_py = PyBytes::new(py, data_slice).unbind();

        let out = Mp4DemuxSample {
            track: track_py,
            keyframe: sample.keyframe,
            timestamp: sample.timestamp,
            duration: sample.duration,
            composition_time_offset: sample.composition_time_offset,
            data: data_py,
        };
        Ok(Some(Py::new(py, out)?))
    }
}

// ===== モジュール登録 =====

#[pymodule(gil_used = false)]
fn mp4_pyo3_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(library_version, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_maximum_moov_box_size, m)?)?;
    m.add_class::<Mp4SampleEntryVp08>()?;
    m.add_class::<Mp4TrackInfo>()?;
    m.add_class::<Mp4MuxSample>()?;
    m.add_class::<Mp4DemuxSample>()?;
    m.add_class::<Mp4FileMuxerOptions>()?;
    m.add_class::<Mp4FileMuxer>()?;
    m.add_class::<Mp4FileDemuxer>()?;
    // ダミー Encode use を消化 (エンコード API を今後使うため import を維持)
    let _ = <Vp08Box as Encode>::encode;
    Ok(())
}
