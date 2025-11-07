# https://github.com/shiguredo/mp4-rust/blob/develop/crates/c-api/include/mp4.h に直接対応する関数やクラスなどを提供するためのモジュール
#
# それぞれの関数やクラスの詳細は大元の mp4.h のコメントを参照のこと（メンテナンスの手間を軽減するために、このファイル内にはコメントは記載しない）
#
# NOTE:
# - ここで提供するクラスには _Raw プレフィックスが付与される
# - ここで定義されている関数やクラスは利用者からは隠蔽する想定（直接公開はしない）
import ctypes
from enum import IntEnum
from pathlib import Path
from typing import Optional


class _RawMp4TrackKind(IntEnum):
    AUDIO = 0
    VIDEO = 1


class _RawMp4SampleEntryKind(IntEnum):
    AVC1 = 0
    HEV1 = 1
    VP08 = 2
    VP09 = 3
    AV01 = 4
    OPUS = 5
    MP4A = 6


class _RawMp4Error(IntEnum):
    OK = 0
    INVALID_INPUT = 1
    INVALID_DATA = 2
    INVALID_STATE = 3
    INPUT_REQUIRED = 4
    OUTPUT_REQUIRED = 5
    NULL_POINTER = 6
    NO_MORE_SAMPLES = 7
    UNSUPPORTED = 8
    OTHER = 9


class _RawMp4DemuxTrackInfo(ctypes.Structure):
    _fields_ = [
        ("track_id", ctypes.c_uint32),
        ("kind", ctypes.c_uint32),
        ("duration", ctypes.c_uint64),
        ("timescale", ctypes.c_uint32),
    ]


class _RawMp4SampleEntryAvc1(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
        ("avc_profile_indication", ctypes.c_uint8),
        ("profile_compatibility", ctypes.c_uint8),
        ("avc_level_indication", ctypes.c_uint8),
        ("length_size_minus_one", ctypes.c_uint8),
        ("sps_data", ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8))),
        ("sps_sizes", ctypes.POINTER(ctypes.c_uint32)),
        ("sps_count", ctypes.c_uint32),
        ("pps_data", ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8))),
        ("pps_sizes", ctypes.POINTER(ctypes.c_uint32)),
        ("pps_count", ctypes.c_uint32),
        ("is_chroma_format_present", ctypes.c_bool),
        ("chroma_format", ctypes.c_uint8),
        ("is_bit_depth_luma_minus8_present", ctypes.c_bool),
        ("bit_depth_luma_minus8", ctypes.c_uint8),
        ("is_bit_depth_chroma_minus8_present", ctypes.c_bool),
        ("bit_depth_chroma_minus8", ctypes.c_uint8),
    ]


class _RawMp4SampleEntryHev1(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
        ("general_profile_space", ctypes.c_uint8),
        ("general_tier_flag", ctypes.c_uint8),
        ("general_profile_idc", ctypes.c_uint8),
        ("general_profile_compatibility_flags", ctypes.c_uint32),
        ("general_constraint_indicator_flags", ctypes.c_uint64),
        ("general_level_idc", ctypes.c_uint8),
        ("chroma_format_idc", ctypes.c_uint8),
        ("bit_depth_luma_minus8", ctypes.c_uint8),
        ("bit_depth_chroma_minus8", ctypes.c_uint8),
        ("min_spatial_segmentation_idc", ctypes.c_uint16),
        ("parallelism_type", ctypes.c_uint8),
        ("avg_frame_rate", ctypes.c_uint16),
        ("constant_frame_rate", ctypes.c_uint8),
        ("num_temporal_layers", ctypes.c_uint8),
        ("temporal_id_nested", ctypes.c_uint8),
        ("length_size_minus_one", ctypes.c_uint8),
        ("nalu_array_count", ctypes.c_uint32),
        ("nalu_types", ctypes.POINTER(ctypes.c_uint8)),
        ("nalu_counts", ctypes.POINTER(ctypes.c_uint32)),
        ("nalu_data", ctypes.POINTER(ctypes.c_uint8)),
        ("nalu_sizes", ctypes.POINTER(ctypes.c_uint32)),
    ]


class _RawMp4SampleEntryVp08(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
        ("bit_depth", ctypes.c_uint8),
        ("chroma_subsampling", ctypes.c_uint8),
        ("video_full_range_flag", ctypes.c_bool),
        ("colour_primaries", ctypes.c_uint8),
        ("transfer_characteristics", ctypes.c_uint8),
        ("matrix_coefficients", ctypes.c_uint8),
    ]


class _RawMp4SampleEntryVp09(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
        ("profile", ctypes.c_uint8),
        ("level", ctypes.c_uint8),
        ("bit_depth", ctypes.c_uint8),
        ("chroma_subsampling", ctypes.c_uint8),
        ("video_full_range_flag", ctypes.c_bool),
        ("colour_primaries", ctypes.c_uint8),
        ("transfer_characteristics", ctypes.c_uint8),
        ("matrix_coefficients", ctypes.c_uint8),
    ]


class _RawMp4SampleEntryAv01(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
        ("seq_profile", ctypes.c_uint8),
        ("seq_level_idx_0", ctypes.c_uint8),
        ("seq_tier_0", ctypes.c_uint8),
        ("high_bitdepth", ctypes.c_uint8),
        ("twelve_bit", ctypes.c_uint8),
        ("monochrome", ctypes.c_uint8),
        ("chroma_subsampling_x", ctypes.c_uint8),
        ("chroma_subsampling_y", ctypes.c_uint8),
        ("chroma_sample_position", ctypes.c_uint8),
        ("initial_presentation_delay_present", ctypes.c_bool),
        ("initial_presentation_delay_minus_one", ctypes.c_uint8),
        ("config_obus", ctypes.POINTER(ctypes.c_uint8)),
        ("config_obus_size", ctypes.c_uint32),
    ]


class _RawMp4SampleEntryOpus(ctypes.Structure):
    _fields_ = [
        ("channel_count", ctypes.c_uint8),
        ("sample_rate", ctypes.c_uint16),
        ("sample_size", ctypes.c_uint16),
        ("pre_skip", ctypes.c_uint16),
        ("input_sample_rate", ctypes.c_uint32),
        ("output_gain", ctypes.c_int16),
    ]


class _RawMp4SampleEntryMp4a(ctypes.Structure):
    _fields_ = [
        ("channel_count", ctypes.c_uint8),
        ("sample_rate", ctypes.c_uint16),
        ("sample_size", ctypes.c_uint16),
        ("buffer_size_db", ctypes.c_uint32),
        ("max_bitrate", ctypes.c_uint32),
        ("avg_bitrate", ctypes.c_uint32),
        ("dec_specific_info", ctypes.POINTER(ctypes.c_uint8)),
        ("dec_specific_info_size", ctypes.c_uint32),
    ]


class _RawMp4SampleEntryData(ctypes.Union):
    _fields_ = [
        ("avc1", _RawMp4SampleEntryAvc1),
        ("hev1", _RawMp4SampleEntryHev1),
        ("vp08", _RawMp4SampleEntryVp08),
        ("vp09", _RawMp4SampleEntryVp09),
        ("av01", _RawMp4SampleEntryAv01),
        ("opus", _RawMp4SampleEntryOpus),
        ("mp4a", _RawMp4SampleEntryMp4a),
    ]


class _RawMp4SampleEntry(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_uint32),
        ("data", _RawMp4SampleEntryData),
    ]


class _RawMp4DemuxSample(ctypes.Structure):
    _fields_ = [
        ("track", ctypes.POINTER(_RawMp4DemuxTrackInfo)),
        ("sample_entry", ctypes.POINTER(_RawMp4SampleEntry)),
        ("keyframe", ctypes.c_bool),
        ("timestamp", ctypes.c_uint64),
        ("duration", ctypes.c_uint32),
        ("data_offset", ctypes.c_uint64),
        ("data_size", ctypes.c_uint64),
    ]


class _RawMp4MuxSample(ctypes.Structure):
    _fields_ = [
        ("track_kind", ctypes.c_uint32),
        ("sample_entry", ctypes.POINTER(_RawMp4SampleEntry)),
        ("keyframe", ctypes.c_bool),
        ("timescale", ctypes.c_uint32),
        ("duration", ctypes.c_uint32),
        ("data_offset", ctypes.c_uint64),
        ("data_size", ctypes.c_uint32),
    ]


class _Mp4FileDemuxer(ctypes.Structure):
    pass


class _Mp4FileMuxer(ctypes.Structure):
    pass


def _load_library() -> ctypes.CDLL:
    lib_names = [
        "libmp4.so",
        "libmp4.dylib",
    ]

    # 1. 開発時: _build/mp4-rust/lib から探す
    build_lib_dir = Path(__file__).parent.parent.parent / "_build" / "mp4-rust" / "lib"
    if build_lib_dir.exists():
        for lib_name in lib_names:
            lib_path = build_lib_dir / lib_name
            if lib_path.exists():
                try:
                    return ctypes.CDLL(str(lib_path))
                except OSError:
                    continue

    # 2. wheel インストール時: mp4_py/lib から探す
    #
    # TODO(sile): この方法でいいのかどうかは要確認
    package_lib_dir = Path(__file__).parent / "lib"
    if package_lib_dir.exists():
        for lib_name in lib_names:
            lib_path = package_lib_dir / lib_name
            if lib_path.exists():
                try:
                    return ctypes.CDLL(str(lib_path))
                except OSError:
                    continue

    raise RuntimeError("Failed to load mp4 library")


_lib: Optional[ctypes.CDLL] = None


def _get_lib() -> ctypes.CDLL:
    global _lib
    if _lib is None:
        _lib = _load_library()
        _setup_function_signatures(_lib)
    return _lib


def _setup_function_signatures(lib: ctypes.CDLL) -> None:
    # =====================================================================
    # バージョン情報関数
    # =====================================================================
    lib.mp4_library_version.restype = ctypes.c_char_p
    lib.mp4_library_version.argtypes = []

    # =====================================================================
    # Demuxer 関数
    # =====================================================================
    lib.mp4_file_demuxer_new.restype = ctypes.POINTER(_Mp4FileDemuxer)
    lib.mp4_file_demuxer_new.argtypes = []

    lib.mp4_file_demuxer_free.restype = None
    lib.mp4_file_demuxer_free.argtypes = [ctypes.POINTER(_Mp4FileDemuxer)]

    lib.mp4_file_demuxer_get_last_error.restype = ctypes.c_char_p
    lib.mp4_file_demuxer_get_last_error.argtypes = [ctypes.POINTER(_Mp4FileDemuxer)]

    lib.mp4_file_demuxer_get_required_input.restype = ctypes.c_int32
    lib.mp4_file_demuxer_get_required_input.argtypes = [
        ctypes.POINTER(_Mp4FileDemuxer),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int32),
    ]

    lib.mp4_file_demuxer_handle_input.restype = ctypes.c_int32
    lib.mp4_file_demuxer_handle_input.argtypes = [
        ctypes.POINTER(_Mp4FileDemuxer),
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_uint32,
    ]

    lib.mp4_file_demuxer_get_tracks.restype = ctypes.c_int32
    lib.mp4_file_demuxer_get_tracks.argtypes = [
        ctypes.POINTER(_Mp4FileDemuxer),
        ctypes.POINTER(ctypes.POINTER(_RawMp4DemuxTrackInfo)),
        ctypes.POINTER(ctypes.c_uint32),
    ]

    lib.mp4_file_demuxer_next_sample.restype = ctypes.c_int32
    lib.mp4_file_demuxer_next_sample.argtypes = [
        ctypes.POINTER(_Mp4FileDemuxer),
        ctypes.POINTER(_RawMp4DemuxSample),
    ]

    # =====================================================================
    # Muxer 関数
    # =====================================================================
    lib.mp4_file_muxer_new.restype = ctypes.POINTER(_Mp4FileMuxer)
    lib.mp4_file_muxer_new.argtypes = []

    lib.mp4_file_muxer_free.restype = None
    lib.mp4_file_muxer_free.argtypes = [ctypes.POINTER(_Mp4FileMuxer)]

    lib.mp4_file_muxer_get_last_error.restype = ctypes.c_char_p
    lib.mp4_file_muxer_get_last_error.argtypes = [ctypes.POINTER(_Mp4FileMuxer)]

    lib.mp4_file_muxer_set_reserved_moov_box_size.restype = ctypes.c_int32
    lib.mp4_file_muxer_set_reserved_moov_box_size.argtypes = [
        ctypes.POINTER(_Mp4FileMuxer),
        ctypes.c_uint64,
    ]

    lib.mp4_file_muxer_initialize.restype = ctypes.c_int32
    lib.mp4_file_muxer_initialize.argtypes = [ctypes.POINTER(_Mp4FileMuxer)]

    lib.mp4_file_muxer_next_output.restype = ctypes.c_int32
    lib.mp4_file_muxer_next_output.argtypes = [
        ctypes.POINTER(_Mp4FileMuxer),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),
    ]

    lib.mp4_file_muxer_append_sample.restype = ctypes.c_int32
    lib.mp4_file_muxer_append_sample.argtypes = [
        ctypes.POINTER(_Mp4FileMuxer),
        ctypes.POINTER(_RawMp4MuxSample),
    ]

    lib.mp4_file_muxer_finalize.restype = ctypes.c_int32
    lib.mp4_file_muxer_finalize.argtypes = [ctypes.POINTER(_Mp4FileMuxer)]

    lib.mp4_estimate_maximum_moov_box_size.restype = ctypes.c_uint32
    lib.mp4_estimate_maximum_moov_box_size.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
