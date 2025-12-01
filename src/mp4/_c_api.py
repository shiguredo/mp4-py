# https://github.com/shiguredo/mp4-rust/blob/develop/crates/c-api/include/mp4.h に直接対応する関数やクラスなどを提供するためのモジュール
#
# それぞれの関数やクラスの詳細は大元の mp4.h のコメントを参照のこと（メンテナンスの手間を軽減するために、このファイル内にはコメントは記載しない）
#
# NOTE:
# - ここで定義されている関数やクラスは利用者からは隠蔽する想定（直接公開はしない）
from enum import IntEnum
from pathlib import Path
from typing import Optional

from cffi import FFI

# cffi の FFI インスタンスを作成
ffi = FFI()

# mp4.h の C 宣言を定義
ffi.cdef("""
    // エラーコード
    typedef enum Mp4Error {
        MP4_ERROR_OK = 0,
        MP4_ERROR_INVALID_INPUT,
        MP4_ERROR_INVALID_DATA,
        MP4_ERROR_INVALID_STATE,
        MP4_ERROR_INPUT_REQUIRED,
        MP4_ERROR_OUTPUT_REQUIRED,
        MP4_ERROR_NULL_POINTER,
        MP4_ERROR_NO_MORE_SAMPLES,
        MP4_ERROR_UNSUPPORTED,
        MP4_ERROR_OTHER,
    } Mp4Error;

    // トラック種別
    typedef enum Mp4TrackKind {
        MP4_TRACK_KIND_AUDIO = 0,
        MP4_TRACK_KIND_VIDEO = 1,
    } Mp4TrackKind;

    // サンプルエントリー種別
    typedef enum Mp4SampleEntryKind {
        MP4_SAMPLE_ENTRY_KIND_AVC1,
        MP4_SAMPLE_ENTRY_KIND_HEV1,
        MP4_SAMPLE_ENTRY_KIND_VP08,
        MP4_SAMPLE_ENTRY_KIND_VP09,
        MP4_SAMPLE_ENTRY_KIND_AV01,
        MP4_SAMPLE_ENTRY_KIND_OPUS,
        MP4_SAMPLE_ENTRY_KIND_MP4A,
    } Mp4SampleEntryKind;

    // Demuxer 構造体（不透明型）
    typedef struct Mp4FileDemuxer {
        uint8_t _private[0];
    } Mp4FileDemuxer;

    // トラック情報
    typedef struct Mp4DemuxTrackInfo {
        uint32_t track_id;
        Mp4TrackKind kind;
        uint64_t duration;
        uint32_t timescale;
    } Mp4DemuxTrackInfo;

    // AVC1 サンプルエントリー
    typedef struct Mp4SampleEntryAvc1 {
        uint16_t width;
        uint16_t height;
        uint8_t avc_profile_indication;
        uint8_t profile_compatibility;
        uint8_t avc_level_indication;
        uint8_t length_size_minus_one;
        const uint8_t *const *sps_data;
        const uint32_t *sps_sizes;
        uint32_t sps_count;
        const uint8_t *const *pps_data;
        const uint32_t *pps_sizes;
        uint32_t pps_count;
        bool is_chroma_format_present;
        uint8_t chroma_format;
        bool is_bit_depth_luma_minus8_present;
        uint8_t bit_depth_luma_minus8;
        bool is_bit_depth_chroma_minus8_present;
        uint8_t bit_depth_chroma_minus8;
    } Mp4SampleEntryAvc1;

    // HEV1 サンプルエントリー
    typedef struct Mp4SampleEntryHev1 {
        uint16_t width;
        uint16_t height;
        uint8_t general_profile_space;
        uint8_t general_tier_flag;
        uint8_t general_profile_idc;
        uint32_t general_profile_compatibility_flags;
        uint64_t general_constraint_indicator_flags;
        uint8_t general_level_idc;
        uint8_t chroma_format_idc;
        uint8_t bit_depth_luma_minus8;
        uint8_t bit_depth_chroma_minus8;
        uint16_t min_spatial_segmentation_idc;
        uint8_t parallelism_type;
        uint16_t avg_frame_rate;
        uint8_t constant_frame_rate;
        uint8_t num_temporal_layers;
        uint8_t temporal_id_nested;
        uint8_t length_size_minus_one;
        uint32_t nalu_array_count;
        const uint8_t *nalu_types;
        const uint32_t *nalu_counts;
        const uint8_t *const *nalu_data;
        const uint32_t *nalu_sizes;
    } Mp4SampleEntryHev1;

    // VP08 サンプルエントリー
    typedef struct Mp4SampleEntryVp08 {
        uint16_t width;
        uint16_t height;
        uint8_t bit_depth;
        uint8_t chroma_subsampling;
        bool video_full_range_flag;
        uint8_t colour_primaries;
        uint8_t transfer_characteristics;
        uint8_t matrix_coefficients;
    } Mp4SampleEntryVp08;

    // VP09 サンプルエントリー
    typedef struct Mp4SampleEntryVp09 {
        uint16_t width;
        uint16_t height;
        uint8_t profile;
        uint8_t level;
        uint8_t bit_depth;
        uint8_t chroma_subsampling;
        bool video_full_range_flag;
        uint8_t colour_primaries;
        uint8_t transfer_characteristics;
        uint8_t matrix_coefficients;
    } Mp4SampleEntryVp09;

    // AV01 サンプルエントリー
    typedef struct Mp4SampleEntryAv01 {
        uint16_t width;
        uint16_t height;
        uint8_t seq_profile;
        uint8_t seq_level_idx_0;
        uint8_t seq_tier_0;
        uint8_t high_bitdepth;
        uint8_t twelve_bit;
        uint8_t monochrome;
        uint8_t chroma_subsampling_x;
        uint8_t chroma_subsampling_y;
        uint8_t chroma_sample_position;
        bool initial_presentation_delay_present;
        uint8_t initial_presentation_delay_minus_one;
        const uint8_t *config_obus;
        uint32_t config_obus_size;
    } Mp4SampleEntryAv01;

    // Opus サンプルエントリー
    typedef struct Mp4SampleEntryOpus {
        uint8_t channel_count;
        uint16_t sample_rate;
        uint16_t sample_size;
        uint16_t pre_skip;
        uint32_t input_sample_rate;
        int16_t output_gain;
    } Mp4SampleEntryOpus;

    // MP4A サンプルエントリー
    typedef struct Mp4SampleEntryMp4a {
        uint8_t channel_count;
        uint16_t sample_rate;
        uint16_t sample_size;
        uint32_t buffer_size_db;
        uint32_t max_bitrate;
        uint32_t avg_bitrate;
        const uint8_t *dec_specific_info;
        uint32_t dec_specific_info_size;
    } Mp4SampleEntryMp4a;

    // サンプルエントリーデータのユニオン
    typedef union Mp4SampleEntryData {
        Mp4SampleEntryAvc1 avc1;
        Mp4SampleEntryHev1 hev1;
        Mp4SampleEntryVp08 vp08;
        Mp4SampleEntryVp09 vp09;
        Mp4SampleEntryAv01 av01;
        Mp4SampleEntryOpus opus;
        Mp4SampleEntryMp4a mp4a;
    } Mp4SampleEntryData;

    // サンプルエントリー
    typedef struct Mp4SampleEntry {
        Mp4SampleEntryKind kind;
        Mp4SampleEntryData data;
    } Mp4SampleEntry;

    // デマルチプレックスサンプル
    typedef struct Mp4DemuxSample {
        const Mp4DemuxTrackInfo *track;
        const Mp4SampleEntry *sample_entry;
        bool keyframe;
        uint64_t timestamp;
        uint32_t duration;
        uint64_t data_offset;
        uintptr_t data_size;
    } Mp4DemuxSample;

    // Muxer 構造体（不透明型）
    typedef struct Mp4FileMuxer {
        uint8_t _private[0];
    } Mp4FileMuxer;

    // マルチプレックスサンプル
    typedef struct Mp4MuxSample {
        Mp4TrackKind track_kind;
        const Mp4SampleEntry *sample_entry;
        bool keyframe;
        uint32_t timescale;
        uint32_t duration;
        uint64_t data_offset;
        uint32_t data_size;
    } Mp4MuxSample;

    // バージョン情報
    const char *mp4_library_version(void);

    // Demuxer 関数
    Mp4FileDemuxer *mp4_file_demuxer_new(void);
    void mp4_file_demuxer_free(Mp4FileDemuxer *demuxer);
    const char *mp4_file_demuxer_get_last_error(const Mp4FileDemuxer *demuxer);
    Mp4Error mp4_file_demuxer_get_required_input(
        Mp4FileDemuxer *demuxer,
        uint64_t *out_required_input_position,
        int32_t *out_required_input_size
    );
    Mp4Error mp4_file_demuxer_handle_input(
        Mp4FileDemuxer *demuxer,
        uint64_t input_position,
        const uint8_t *input_data,
        uint32_t input_data_size
    );
    Mp4Error mp4_file_demuxer_get_tracks(
        Mp4FileDemuxer *demuxer,
        const Mp4DemuxTrackInfo **out_tracks,
        uint32_t *out_track_count
    );
    Mp4Error mp4_file_demuxer_next_sample(
        Mp4FileDemuxer *demuxer,
        Mp4DemuxSample *out_sample
    );

    // Muxer 関数
    Mp4FileMuxer *mp4_file_muxer_new(void);
    void mp4_file_muxer_free(Mp4FileMuxer *muxer);
    const char *mp4_file_muxer_get_last_error(const Mp4FileMuxer *muxer);
    Mp4Error mp4_file_muxer_set_reserved_moov_box_size(Mp4FileMuxer *muxer, uint64_t size);
    Mp4Error mp4_file_muxer_initialize(Mp4FileMuxer *muxer);
    Mp4Error mp4_file_muxer_next_output(
        Mp4FileMuxer *muxer,
        uint64_t *out_output_offset,
        uint32_t *out_output_size,
        const uint8_t **out_output_data
    );
    Mp4Error mp4_file_muxer_append_sample(Mp4FileMuxer *muxer, const Mp4MuxSample *sample);
    Mp4Error mp4_file_muxer_finalize(Mp4FileMuxer *muxer);

    // ユーティリティ関数
    uint32_t mp4_estimate_maximum_moov_box_size(uint32_t audio_sample_count, uint32_t video_sample_count);
""")


class Mp4TrackKind(IntEnum):
    AUDIO = 0
    VIDEO = 1


class Mp4SampleEntryKind(IntEnum):
    AVC1 = 0
    HEV1 = 1
    VP08 = 2
    VP09 = 3
    AV01 = 4
    OPUS = 5
    MP4A = 6


class Mp4Error(IntEnum):
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


def _load_library():
    """ライブラリを読み込む"""
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
                    return ffi.dlopen(str(lib_path))
                except OSError:
                    continue

    # 2. wheel インストール時: mp4/lib から探す
    package_lib_dir = Path(__file__).parent / "lib"
    if package_lib_dir.exists():
        for lib_name in lib_names:
            lib_path = package_lib_dir / lib_name
            if lib_path.exists():
                try:
                    return ffi.dlopen(str(lib_path))
                except OSError:
                    continue

    raise RuntimeError("Failed to load mp4 library")


_lib = None


def _get_lib():
    """ライブラリを取得する"""
    global _lib
    if _lib is None:
        _lib = _load_library()
    return _lib
