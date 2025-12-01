// mp4-rust の C API に対する nanobind バインディング
//
// sans I/O なので、ファイル読み書きは Python 側で行い、
// ここでは C API のラッパーを提供する

#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

extern "C" {
#include "mp4.h"
}

namespace nb = nanobind;
using namespace nb::literals;

// ============================================================================
// Python 向け構造体定義
// ============================================================================

// トラック種別を文字列で返す
inline std::string track_kind_to_string(Mp4TrackKind kind) {
  switch (kind) {
  case MP4_TRACK_KIND_AUDIO:
    return "audio";
  case MP4_TRACK_KIND_VIDEO:
    return "video";
  default:
    throw std::runtime_error("Unknown track kind");
  }
}

inline Mp4TrackKind string_to_track_kind(const std::string &kind) {
  if (kind == "audio") {
    return MP4_TRACK_KIND_AUDIO;
  } else if (kind == "video") {
    return MP4_TRACK_KIND_VIDEO;
  } else {
    throw std::runtime_error("Unknown track kind: " + kind);
  }
}

// サンプルエントリ種別
enum class PySampleEntryKind {
  AVC1 = 0,
  HEV1 = 1,
  VP08 = 2,
  VP09 = 3,
  AV01 = 4,
  OPUS = 5,
  MP4A = 6,
};

// AVC1 サンプルエントリー
struct PySampleEntryAvc1 {
  uint16_t width;
  uint16_t height;
  uint8_t avc_profile_indication;
  uint8_t profile_compatibility;
  uint8_t avc_level_indication;
  uint8_t length_size_minus_one;
  std::vector<nb::bytes> sps_data;
  std::vector<nb::bytes> pps_data;
  std::optional<uint8_t> chroma_format;
  std::optional<uint8_t> bit_depth_luma_minus8;
  std::optional<uint8_t> bit_depth_chroma_minus8;
};

// HEV1 サンプルエントリー
struct PySampleEntryHev1 {
  uint16_t width;
  uint16_t height;
  uint8_t general_profile_idc;
  uint8_t general_level_idc;
  std::vector<uint8_t> nalu_types;
  std::vector<nb::bytes> nalu_data;
  uint8_t length_size_minus_one;
  uint8_t general_tier_flag;
  uint8_t general_profile_space;
  uint32_t general_profile_compatibility_flags;
  uint64_t general_constraint_indicator_flags;
  uint8_t chroma_format_idc;
  uint8_t bit_depth_luma_minus8;
  uint8_t bit_depth_chroma_minus8;
  uint16_t min_spatial_segmentation_idc;
  uint8_t parallelism_type;
  uint16_t avg_frame_rate;
  uint8_t constant_frame_rate;
  uint8_t num_temporal_layers;
  uint8_t temporal_id_nested;
};

// VP08 サンプルエントリー
struct PySampleEntryVp08 {
  uint16_t width;
  uint16_t height;
  uint8_t bit_depth;
  uint8_t chroma_subsampling;
  bool video_full_range_flag;
  uint8_t colour_primaries;
  uint8_t transfer_characteristics;
  uint8_t matrix_coefficients;
};

// VP09 サンプルエントリー
struct PySampleEntryVp09 {
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
};

// AV01 サンプルエントリー
struct PySampleEntryAv01 {
  uint16_t width;
  uint16_t height;
  nb::bytes config_obus;
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
};

// Opus サンプルエントリー
struct PySampleEntryOpus {
  uint8_t channel_count;
  uint16_t sample_rate;
  uint16_t sample_size;
  uint16_t pre_skip;
  std::optional<uint32_t> input_sample_rate;
  int16_t output_gain;
};

// MP4A サンプルエントリー
struct PySampleEntryMp4a {
  uint8_t channel_count;
  uint16_t sample_rate;
  nb::bytes dec_specific_info;
  uint16_t sample_size;
  uint32_t buffer_size_db;
  uint32_t max_bitrate;
  uint32_t avg_bitrate;
};

// トラック情報
struct PyTrackInfo {
  uint32_t track_id;
  std::string kind;
  uint64_t duration;
  uint32_t timescale;
};

// Demux サンプル（sans I/O なのでデータはオフセットとサイズのみ）
struct PyDemuxSample {
  PyTrackInfo track;
  std::optional<nb::object> sample_entry; // Python オブジェクトとして保持
  bool keyframe;
  uint64_t timestamp;
  uint32_t duration;
  uint64_t data_offset;
  size_t data_size;
};

// Mux サンプル
struct PyMuxSample {
  std::string track_kind;
  std::optional<nb::object> sample_entry;
  bool keyframe;
  uint32_t timescale;
  uint32_t duration;
  nb::bytes data;
};

// ============================================================================
// C API から Python 構造体への変換
// ============================================================================

nb::object convert_sample_entry(const Mp4SampleEntry *entry) {
  if (!entry) {
    return nb::none();
  }

  switch (entry->kind) {
  case MP4_SAMPLE_ENTRY_KIND_AVC1: {
    const auto &avc1 = entry->data.avc1;
    PySampleEntryAvc1 py_avc1;
    py_avc1.width = avc1.width;
    py_avc1.height = avc1.height;
    py_avc1.avc_profile_indication = avc1.avc_profile_indication;
    py_avc1.profile_compatibility = avc1.profile_compatibility;
    py_avc1.avc_level_indication = avc1.avc_level_indication;
    py_avc1.length_size_minus_one = avc1.length_size_minus_one;

    // SPS データを抽出
    for (uint32_t i = 0; i < avc1.sps_count; i++) {
      py_avc1.sps_data.push_back(nb::bytes(
          reinterpret_cast<const char *>(avc1.sps_data[i]), avc1.sps_sizes[i]));
    }

    // PPS データを抽出
    for (uint32_t i = 0; i < avc1.pps_count; i++) {
      py_avc1.pps_data.push_back(nb::bytes(
          reinterpret_cast<const char *>(avc1.pps_data[i]), avc1.pps_sizes[i]));
    }

    // オプションフィールド
    if (avc1.is_chroma_format_present) {
      py_avc1.chroma_format = avc1.chroma_format;
    }
    if (avc1.is_bit_depth_luma_minus8_present) {
      py_avc1.bit_depth_luma_minus8 = avc1.bit_depth_luma_minus8;
    }
    if (avc1.is_bit_depth_chroma_minus8_present) {
      py_avc1.bit_depth_chroma_minus8 = avc1.bit_depth_chroma_minus8;
    }

    return nb::cast(py_avc1);
  }

  case MP4_SAMPLE_ENTRY_KIND_HEV1: {
    const auto &hev1 = entry->data.hev1;
    PySampleEntryHev1 py_hev1;
    py_hev1.width = hev1.width;
    py_hev1.height = hev1.height;
    py_hev1.general_profile_space = hev1.general_profile_space;
    py_hev1.general_tier_flag = hev1.general_tier_flag;
    py_hev1.general_profile_idc = hev1.general_profile_idc;
    py_hev1.general_profile_compatibility_flags =
        hev1.general_profile_compatibility_flags;
    py_hev1.general_constraint_indicator_flags =
        hev1.general_constraint_indicator_flags;
    py_hev1.general_level_idc = hev1.general_level_idc;
    py_hev1.chroma_format_idc = hev1.chroma_format_idc;
    py_hev1.bit_depth_luma_minus8 = hev1.bit_depth_luma_minus8;
    py_hev1.bit_depth_chroma_minus8 = hev1.bit_depth_chroma_minus8;
    py_hev1.min_spatial_segmentation_idc = hev1.min_spatial_segmentation_idc;
    py_hev1.parallelism_type = hev1.parallelism_type;
    py_hev1.avg_frame_rate = hev1.avg_frame_rate;
    py_hev1.constant_frame_rate = hev1.constant_frame_rate;
    py_hev1.num_temporal_layers = hev1.num_temporal_layers;
    py_hev1.temporal_id_nested = hev1.temporal_id_nested;
    py_hev1.length_size_minus_one = hev1.length_size_minus_one;

    // NALU データを抽出
    uint32_t nalu_index = 0;
    for (uint32_t i = 0; i < hev1.nalu_array_count; i++) {
      py_hev1.nalu_types.push_back(hev1.nalu_types[i]);
      uint32_t count = hev1.nalu_counts[i];
      for (uint32_t j = 0; j < count; j++) {
        py_hev1.nalu_data.push_back(
            nb::bytes(reinterpret_cast<const char *>(hev1.nalu_data[nalu_index]),
                      hev1.nalu_sizes[nalu_index]));
        nalu_index++;
      }
    }

    return nb::cast(py_hev1);
  }

  case MP4_SAMPLE_ENTRY_KIND_VP08: {
    const auto &vp08 = entry->data.vp08;
    PySampleEntryVp08 py_vp08;
    py_vp08.width = vp08.width;
    py_vp08.height = vp08.height;
    py_vp08.bit_depth = vp08.bit_depth;
    py_vp08.chroma_subsampling = vp08.chroma_subsampling;
    py_vp08.video_full_range_flag = vp08.video_full_range_flag;
    py_vp08.colour_primaries = vp08.colour_primaries;
    py_vp08.transfer_characteristics = vp08.transfer_characteristics;
    py_vp08.matrix_coefficients = vp08.matrix_coefficients;
    return nb::cast(py_vp08);
  }

  case MP4_SAMPLE_ENTRY_KIND_VP09: {
    const auto &vp09 = entry->data.vp09;
    PySampleEntryVp09 py_vp09;
    py_vp09.width = vp09.width;
    py_vp09.height = vp09.height;
    py_vp09.profile = vp09.profile;
    py_vp09.level = vp09.level;
    py_vp09.bit_depth = vp09.bit_depth;
    py_vp09.chroma_subsampling = vp09.chroma_subsampling;
    py_vp09.video_full_range_flag = vp09.video_full_range_flag;
    py_vp09.colour_primaries = vp09.colour_primaries;
    py_vp09.transfer_characteristics = vp09.transfer_characteristics;
    py_vp09.matrix_coefficients = vp09.matrix_coefficients;
    return nb::cast(py_vp09);
  }

  case MP4_SAMPLE_ENTRY_KIND_AV01: {
    const auto &av01 = entry->data.av01;
    PySampleEntryAv01 py_av01;
    py_av01.width = av01.width;
    py_av01.height = av01.height;
    py_av01.seq_profile = av01.seq_profile;
    py_av01.seq_level_idx_0 = av01.seq_level_idx_0;
    py_av01.seq_tier_0 = av01.seq_tier_0;
    py_av01.high_bitdepth = av01.high_bitdepth;
    py_av01.twelve_bit = av01.twelve_bit;
    py_av01.monochrome = av01.monochrome;
    py_av01.chroma_subsampling_x = av01.chroma_subsampling_x;
    py_av01.chroma_subsampling_y = av01.chroma_subsampling_y;
    py_av01.chroma_sample_position = av01.chroma_sample_position;
    py_av01.initial_presentation_delay_present =
        av01.initial_presentation_delay_present;
    py_av01.initial_presentation_delay_minus_one =
        av01.initial_presentation_delay_minus_one;
    py_av01.config_obus = nb::bytes(
        reinterpret_cast<const char *>(av01.config_obus), av01.config_obus_size);
    return nb::cast(py_av01);
  }

  case MP4_SAMPLE_ENTRY_KIND_OPUS: {
    const auto &opus = entry->data.opus;
    PySampleEntryOpus py_opus;
    py_opus.channel_count = opus.channel_count;
    py_opus.sample_rate = opus.sample_rate;
    py_opus.sample_size = opus.sample_size;
    py_opus.pre_skip = opus.pre_skip;
    py_opus.input_sample_rate = opus.input_sample_rate;
    py_opus.output_gain = opus.output_gain;
    return nb::cast(py_opus);
  }

  case MP4_SAMPLE_ENTRY_KIND_MP4A: {
    const auto &mp4a = entry->data.mp4a;
    PySampleEntryMp4a py_mp4a;
    py_mp4a.channel_count = mp4a.channel_count;
    py_mp4a.sample_rate = mp4a.sample_rate;
    py_mp4a.sample_size = mp4a.sample_size;
    py_mp4a.buffer_size_db = mp4a.buffer_size_db;
    py_mp4a.max_bitrate = mp4a.max_bitrate;
    py_mp4a.avg_bitrate = mp4a.avg_bitrate;
    py_mp4a.dec_specific_info =
        nb::bytes(reinterpret_cast<const char *>(mp4a.dec_specific_info),
                  mp4a.dec_specific_info_size);
    return nb::cast(py_mp4a);
  }

  default:
    throw std::runtime_error("Unknown sample entry kind");
  }
}

// ============================================================================
// Demuxer ラッパークラス
// ============================================================================

class PyFileDemuxer {
public:
  PyFileDemuxer() : demuxer_(mp4_file_demuxer_new()) {
    if (!demuxer_) {
      throw std::runtime_error("Failed to create mp4 demuxer");
    }
  }

  ~PyFileDemuxer() {
    if (demuxer_) {
      mp4_file_demuxer_free(demuxer_);
    }
  }

  // コピー禁止
  PyFileDemuxer(const PyFileDemuxer &) = delete;
  PyFileDemuxer &operator=(const PyFileDemuxer &) = delete;

  // 必要な入力データの位置とサイズを取得
  std::tuple<uint64_t, int32_t> get_required_input() {
    uint64_t pos = 0;
    int32_t size = 0;
    auto error =
        mp4_file_demuxer_get_required_input(demuxer_, &pos, &size);
    check_error(error);
    return {pos, size};
  }

  // 入力データを供給
  void handle_input(uint64_t position, nb::bytes data) {
    auto error = mp4_file_demuxer_handle_input(
        demuxer_, position, reinterpret_cast<const uint8_t *>(data.c_str()),
        static_cast<uint32_t>(data.size()));
    check_error(error);
  }

  // トラック情報を取得
  std::vector<PyTrackInfo> get_tracks() {
    const Mp4DemuxTrackInfo *tracks = nullptr;
    uint32_t count = 0;

    auto error = mp4_file_demuxer_get_tracks(demuxer_, &tracks, &count);
    if (error == MP4_ERROR_INPUT_REQUIRED) {
      throw std::runtime_error("Input required");
    }
    check_error(error);

    std::vector<PyTrackInfo> result;
    for (uint32_t i = 0; i < count; i++) {
      PyTrackInfo info;
      info.track_id = tracks[i].track_id;
      info.kind = track_kind_to_string(tracks[i].kind);
      info.duration = tracks[i].duration;
      info.timescale = tracks[i].timescale;
      result.push_back(info);
    }
    return result;
  }

  // 次のサンプルを取得
  std::optional<PyDemuxSample> next_sample() {
    Mp4DemuxSample sample;
    auto error = mp4_file_demuxer_next_sample(demuxer_, &sample);

    if (error == MP4_ERROR_NO_MORE_SAMPLES) {
      return std::nullopt;
    }
    if (error == MP4_ERROR_INPUT_REQUIRED) {
      throw std::runtime_error("Input required");
    }
    check_error(error);

    PyDemuxSample result;
    result.track.track_id = sample.track->track_id;
    result.track.kind = track_kind_to_string(sample.track->kind);
    result.track.duration = sample.track->duration;
    result.track.timescale = sample.track->timescale;
    result.sample_entry =
        sample.sample_entry
            ? std::make_optional(convert_sample_entry(sample.sample_entry))
            : std::nullopt;
    result.keyframe = sample.keyframe;
    result.timestamp = sample.timestamp;
    result.duration = sample.duration;
    result.data_offset = sample.data_offset;
    result.data_size = sample.data_size;
    return result;
  }

  // エラーかどうか確認
  bool requires_input() {
    auto [pos, size] = get_required_input();
    return size != 0;
  }

private:
  Mp4FileDemuxer *demuxer_;

  void check_error(Mp4Error error) {
    if (error == MP4_ERROR_OK) {
      return;
    }

    const char *msg = mp4_file_demuxer_get_last_error(demuxer_);
    std::string error_msg = msg ? msg : "Unknown error";

    switch (error) {
    case MP4_ERROR_NULL_POINTER:
      throw std::runtime_error("Null pointer error: " + error_msg);
    case MP4_ERROR_INVALID_INPUT:
      throw std::runtime_error("Invalid input: " + error_msg);
    case MP4_ERROR_INVALID_DATA:
      throw std::runtime_error("Invalid data: " + error_msg);
    case MP4_ERROR_INVALID_STATE:
      throw std::runtime_error("Invalid state: " + error_msg);
    case MP4_ERROR_UNSUPPORTED:
      throw std::runtime_error("Unsupported: " + error_msg);
    default:
      throw std::runtime_error("MP4 error (" + std::to_string(error) +
                               "): " + error_msg);
    }
  }
};

// ============================================================================
// Muxer ラッパークラス
// ============================================================================

// Python オブジェクトから C 構造体への変換時に使用するヘルパー構造体
struct SampleEntryHolder {
  Mp4SampleEntry entry;
  // バッファを保持
  std::vector<std::vector<uint8_t>> sps_buffers;
  std::vector<std::vector<uint8_t>> pps_buffers;
  std::vector<const uint8_t *> sps_ptrs;
  std::vector<const uint8_t *> pps_ptrs;
  std::vector<uint32_t> sps_sizes;
  std::vector<uint32_t> pps_sizes;
  std::vector<std::vector<uint8_t>> nalu_buffers;
  std::vector<const uint8_t *> nalu_ptrs;
  std::vector<uint32_t> nalu_sizes;
  std::vector<uint32_t> nalu_counts;
  std::vector<uint8_t> nalu_types;
  std::vector<uint8_t> config_obus_buffer;
  std::vector<uint8_t> dec_specific_info_buffer;
};

class PyFileMuxer {
public:
  PyFileMuxer() : muxer_(mp4_file_muxer_new()), finalized_(false) {
    if (!muxer_) {
      throw std::runtime_error("Failed to create mp4 muxer");
    }
  }

  ~PyFileMuxer() {
    if (muxer_) {
      mp4_file_muxer_free(muxer_);
    }
  }

  // コピー禁止
  PyFileMuxer(const PyFileMuxer &) = delete;
  PyFileMuxer &operator=(const PyFileMuxer &) = delete;

  // faststart 用の moov ボックスサイズを設定
  void set_reserved_moov_box_size(uint64_t size) {
    auto error = mp4_file_muxer_set_reserved_moov_box_size(muxer_, size);
    check_error(error);
  }

  // 初期化
  void initialize() {
    auto error = mp4_file_muxer_initialize(muxer_);
    check_error(error);
  }

  // 出力データを取得
  std::optional<std::tuple<uint64_t, nb::bytes>> next_output() {
    uint64_t offset = 0;
    uint32_t size = 0;
    const uint8_t *data = nullptr;

    auto error = mp4_file_muxer_next_output(muxer_, &offset, &size, &data);
    check_error(error);

    if (size == 0) {
      return std::nullopt;
    }

    return std::make_tuple(offset,
                           nb::bytes(reinterpret_cast<const char *>(data), size));
  }

  // サンプルを追加
  void append_sample(const std::string &track_kind, nb::object sample_entry_obj,
                     bool keyframe, uint32_t timescale, uint32_t duration,
                     uint64_t data_offset, uint32_t data_size) {
    Mp4MuxSample sample;
    sample.track_kind = string_to_track_kind(track_kind);
    sample.keyframe = keyframe;
    sample.timescale = timescale;
    sample.duration = duration;
    sample.data_offset = data_offset;
    sample.data_size = data_size;

    SampleEntryHolder holder;
    if (!sample_entry_obj.is_none()) {
      convert_sample_entry_to_c(sample_entry_obj, holder);
      sample.sample_entry = &holder.entry;
    } else {
      sample.sample_entry = nullptr;
    }

    auto error = mp4_file_muxer_append_sample(muxer_, &sample);
    check_error(error);
  }

  // ファイナライズ
  void finalize() {
    auto error = mp4_file_muxer_finalize(muxer_);
    check_error(error);
    finalized_ = true;
  }

  bool is_finalized() const { return finalized_; }

private:
  Mp4FileMuxer *muxer_;
  bool finalized_;

  void check_error(Mp4Error error) {
    if (error == MP4_ERROR_OK) {
      return;
    }

    const char *msg = mp4_file_muxer_get_last_error(muxer_);
    std::string error_msg = msg ? msg : "Unknown error";

    switch (error) {
    case MP4_ERROR_NULL_POINTER:
      throw std::runtime_error("Null pointer error: " + error_msg);
    case MP4_ERROR_INVALID_INPUT:
      throw std::runtime_error("Invalid input: " + error_msg);
    case MP4_ERROR_INVALID_STATE:
      throw std::runtime_error("Invalid state: " + error_msg);
    case MP4_ERROR_OUTPUT_REQUIRED:
      throw std::runtime_error("Output required: " + error_msg);
    default:
      throw std::runtime_error("MP4 error (" + std::to_string(error) +
                               "): " + error_msg);
    }
  }

  void convert_sample_entry_to_c(nb::object obj, SampleEntryHolder &holder) {
    if (nb::isinstance<PySampleEntryAvc1>(obj)) {
      auto py = nb::cast<PySampleEntryAvc1>(obj);
      holder.entry.kind = MP4_SAMPLE_ENTRY_KIND_AVC1;
      auto &avc1 = holder.entry.data.avc1;
      avc1.width = py.width;
      avc1.height = py.height;
      avc1.avc_profile_indication = py.avc_profile_indication;
      avc1.profile_compatibility = py.profile_compatibility;
      avc1.avc_level_indication = py.avc_level_indication;
      avc1.length_size_minus_one = py.length_size_minus_one;

      // SPS データ
      for (const auto &sps : py.sps_data) {
        std::vector<uint8_t> buf(sps.c_str(), sps.c_str() + sps.size());
        holder.sps_buffers.push_back(std::move(buf));
        holder.sps_sizes.push_back(static_cast<uint32_t>(sps.size()));
      }
      for (auto &buf : holder.sps_buffers) {
        holder.sps_ptrs.push_back(buf.data());
      }
      avc1.sps_data = holder.sps_ptrs.data();
      avc1.sps_sizes = holder.sps_sizes.data();
      avc1.sps_count = static_cast<uint32_t>(holder.sps_ptrs.size());

      // PPS データ
      for (const auto &pps : py.pps_data) {
        std::vector<uint8_t> buf(pps.c_str(), pps.c_str() + pps.size());
        holder.pps_buffers.push_back(std::move(buf));
        holder.pps_sizes.push_back(static_cast<uint32_t>(pps.size()));
      }
      for (auto &buf : holder.pps_buffers) {
        holder.pps_ptrs.push_back(buf.data());
      }
      avc1.pps_data = holder.pps_ptrs.data();
      avc1.pps_sizes = holder.pps_sizes.data();
      avc1.pps_count = static_cast<uint32_t>(holder.pps_ptrs.size());

      // オプションフィールド
      avc1.is_chroma_format_present = py.chroma_format.has_value();
      avc1.chroma_format = py.chroma_format.value_or(0);
      avc1.is_bit_depth_luma_minus8_present =
          py.bit_depth_luma_minus8.has_value();
      avc1.bit_depth_luma_minus8 = py.bit_depth_luma_minus8.value_or(0);
      avc1.is_bit_depth_chroma_minus8_present =
          py.bit_depth_chroma_minus8.has_value();
      avc1.bit_depth_chroma_minus8 = py.bit_depth_chroma_minus8.value_or(0);

    } else if (nb::isinstance<PySampleEntryHev1>(obj)) {
      auto py = nb::cast<PySampleEntryHev1>(obj);
      if (py.nalu_types.size() != py.nalu_data.size()) {
        throw std::runtime_error(
            "nalu_types and nalu_data must have the same length");
      }

      holder.entry.kind = MP4_SAMPLE_ENTRY_KIND_HEV1;
      auto &hev1 = holder.entry.data.hev1;
      hev1.width = py.width;
      hev1.height = py.height;
      hev1.general_profile_space = py.general_profile_space;
      hev1.general_tier_flag = py.general_tier_flag;
      hev1.general_profile_idc = py.general_profile_idc;
      hev1.general_profile_compatibility_flags =
          py.general_profile_compatibility_flags;
      hev1.general_constraint_indicator_flags =
          py.general_constraint_indicator_flags;
      hev1.general_level_idc = py.general_level_idc;
      hev1.chroma_format_idc = py.chroma_format_idc;
      hev1.bit_depth_luma_minus8 = py.bit_depth_luma_minus8;
      hev1.bit_depth_chroma_minus8 = py.bit_depth_chroma_minus8;
      hev1.min_spatial_segmentation_idc = py.min_spatial_segmentation_idc;
      hev1.parallelism_type = py.parallelism_type;
      hev1.avg_frame_rate = py.avg_frame_rate;
      hev1.constant_frame_rate = py.constant_frame_rate;
      hev1.num_temporal_layers = py.num_temporal_layers;
      hev1.temporal_id_nested = py.temporal_id_nested;
      hev1.length_size_minus_one = py.length_size_minus_one;

      // NALU データ
      holder.nalu_types = py.nalu_types;
      for (size_t i = 0; i < py.nalu_types.size(); i++) {
        holder.nalu_counts.push_back(1);
      }
      for (const auto &nalu : py.nalu_data) {
        std::vector<uint8_t> buf(nalu.c_str(), nalu.c_str() + nalu.size());
        holder.nalu_buffers.push_back(std::move(buf));
        holder.nalu_sizes.push_back(static_cast<uint32_t>(nalu.size()));
      }
      for (auto &buf : holder.nalu_buffers) {
        holder.nalu_ptrs.push_back(buf.data());
      }

      hev1.nalu_array_count = static_cast<uint32_t>(py.nalu_types.size());
      hev1.nalu_types = holder.nalu_types.data();
      hev1.nalu_counts = holder.nalu_counts.data();
      hev1.nalu_data = holder.nalu_ptrs.data();
      hev1.nalu_sizes = holder.nalu_sizes.data();

    } else if (nb::isinstance<PySampleEntryVp08>(obj)) {
      auto py = nb::cast<PySampleEntryVp08>(obj);
      holder.entry.kind = MP4_SAMPLE_ENTRY_KIND_VP08;
      auto &vp08 = holder.entry.data.vp08;
      vp08.width = py.width;
      vp08.height = py.height;
      vp08.bit_depth = py.bit_depth;
      vp08.chroma_subsampling = py.chroma_subsampling;
      vp08.video_full_range_flag = py.video_full_range_flag;
      vp08.colour_primaries = py.colour_primaries;
      vp08.transfer_characteristics = py.transfer_characteristics;
      vp08.matrix_coefficients = py.matrix_coefficients;

    } else if (nb::isinstance<PySampleEntryVp09>(obj)) {
      auto py = nb::cast<PySampleEntryVp09>(obj);
      holder.entry.kind = MP4_SAMPLE_ENTRY_KIND_VP09;
      auto &vp09 = holder.entry.data.vp09;
      vp09.width = py.width;
      vp09.height = py.height;
      vp09.profile = py.profile;
      vp09.level = py.level;
      vp09.bit_depth = py.bit_depth;
      vp09.chroma_subsampling = py.chroma_subsampling;
      vp09.video_full_range_flag = py.video_full_range_flag;
      vp09.colour_primaries = py.colour_primaries;
      vp09.transfer_characteristics = py.transfer_characteristics;
      vp09.matrix_coefficients = py.matrix_coefficients;

    } else if (nb::isinstance<PySampleEntryAv01>(obj)) {
      auto py = nb::cast<PySampleEntryAv01>(obj);
      holder.entry.kind = MP4_SAMPLE_ENTRY_KIND_AV01;
      auto &av01 = holder.entry.data.av01;
      av01.width = py.width;
      av01.height = py.height;
      av01.seq_profile = py.seq_profile;
      av01.seq_level_idx_0 = py.seq_level_idx_0;
      av01.seq_tier_0 = py.seq_tier_0;
      av01.high_bitdepth = py.high_bitdepth;
      av01.twelve_bit = py.twelve_bit;
      av01.monochrome = py.monochrome;
      av01.chroma_subsampling_x = py.chroma_subsampling_x;
      av01.chroma_subsampling_y = py.chroma_subsampling_y;
      av01.chroma_sample_position = py.chroma_sample_position;
      av01.initial_presentation_delay_present =
          py.initial_presentation_delay_present;
      av01.initial_presentation_delay_minus_one =
          py.initial_presentation_delay_minus_one;

      // config_obus
      holder.config_obus_buffer.assign(py.config_obus.c_str(),
                                       py.config_obus.c_str() + py.config_obus.size());
      av01.config_obus = holder.config_obus_buffer.data();
      av01.config_obus_size =
          static_cast<uint32_t>(holder.config_obus_buffer.size());

    } else if (nb::isinstance<PySampleEntryOpus>(obj)) {
      auto py = nb::cast<PySampleEntryOpus>(obj);
      holder.entry.kind = MP4_SAMPLE_ENTRY_KIND_OPUS;
      auto &opus = holder.entry.data.opus;
      opus.channel_count = py.channel_count;
      opus.sample_rate = py.sample_rate;
      opus.sample_size = py.sample_size;
      opus.pre_skip = py.pre_skip;
      opus.input_sample_rate = py.input_sample_rate.value_or(py.sample_rate);
      opus.output_gain = py.output_gain;

    } else if (nb::isinstance<PySampleEntryMp4a>(obj)) {
      auto py = nb::cast<PySampleEntryMp4a>(obj);
      holder.entry.kind = MP4_SAMPLE_ENTRY_KIND_MP4A;
      auto &mp4a = holder.entry.data.mp4a;
      mp4a.channel_count = py.channel_count;
      mp4a.sample_rate = py.sample_rate;
      mp4a.sample_size = py.sample_size;
      mp4a.buffer_size_db = py.buffer_size_db;
      mp4a.max_bitrate = py.max_bitrate;
      mp4a.avg_bitrate = py.avg_bitrate;

      // dec_specific_info
      holder.dec_specific_info_buffer.assign(
          py.dec_specific_info.c_str(),
          py.dec_specific_info.c_str() + py.dec_specific_info.size());
      mp4a.dec_specific_info = holder.dec_specific_info_buffer.data();
      mp4a.dec_specific_info_size =
          static_cast<uint32_t>(holder.dec_specific_info_buffer.size());

    } else {
      throw std::runtime_error("Unknown sample entry type");
    }
  }
};

// ============================================================================
// ユーティリティ関数
// ============================================================================

std::string get_library_version() {
  const char *version = mp4_library_version();
  return version ? version : "";
}

uint32_t estimate_maximum_moov_box_size(uint32_t audio_sample_count,
                                        uint32_t video_sample_count) {
  return mp4_estimate_maximum_moov_box_size(audio_sample_count,
                                            video_sample_count);
}

// ============================================================================
// nanobind モジュール定義
// ============================================================================

NB_MODULE(_mp4, m) {
  m.doc() = "nanobind bindings for mp4-rust C API";

  // バージョン取得関数
  m.def("native_version", &get_library_version, "mp4-rust のバージョンを返す");

  // moov ボックスサイズ見積もり関数
  m.def("estimate_maximum_moov_box_size", &estimate_maximum_moov_box_size,
        "audio_sample_count"_a, "video_sample_count"_a,
        "moov ボックスの最大サイズを見積もる");

  // トラック情報
  nb::class_<PyTrackInfo>(m, "TrackInfo")
      .def_ro("track_id", &PyTrackInfo::track_id, "トラック ID")
      .def_ro("kind", &PyTrackInfo::kind, "トラック種別")
      .def_ro("duration", &PyTrackInfo::duration, "尺（タイムスケール単位）")
      .def_ro("timescale", &PyTrackInfo::timescale, "タイムスケール")
      .def("__repr__", [](const PyTrackInfo &t) {
        return "TrackInfo(track_id=" + std::to_string(t.track_id) +
               ", kind='" + t.kind + "', duration=" + std::to_string(t.duration) +
               ", timescale=" + std::to_string(t.timescale) + ")";
      });

  // サンプルエントリー: AVC1
  nb::class_<PySampleEntryAvc1>(m, "SampleEntryAvc1")
      .def(nb::init<>())
      .def_rw("width", &PySampleEntryAvc1::width)
      .def_rw("height", &PySampleEntryAvc1::height)
      .def_rw("avc_profile_indication", &PySampleEntryAvc1::avc_profile_indication)
      .def_rw("profile_compatibility", &PySampleEntryAvc1::profile_compatibility)
      .def_rw("avc_level_indication", &PySampleEntryAvc1::avc_level_indication)
      .def_rw("length_size_minus_one", &PySampleEntryAvc1::length_size_minus_one)
      .def_rw("sps_data", &PySampleEntryAvc1::sps_data)
      .def_rw("pps_data", &PySampleEntryAvc1::pps_data)
      .def_rw("chroma_format", &PySampleEntryAvc1::chroma_format)
      .def_rw("bit_depth_luma_minus8", &PySampleEntryAvc1::bit_depth_luma_minus8)
      .def_rw("bit_depth_chroma_minus8", &PySampleEntryAvc1::bit_depth_chroma_minus8);

  // サンプルエントリー: HEV1
  nb::class_<PySampleEntryHev1>(m, "SampleEntryHev1")
      .def(nb::init<>())
      .def_rw("width", &PySampleEntryHev1::width)
      .def_rw("height", &PySampleEntryHev1::height)
      .def_rw("general_profile_idc", &PySampleEntryHev1::general_profile_idc)
      .def_rw("general_level_idc", &PySampleEntryHev1::general_level_idc)
      .def_rw("nalu_types", &PySampleEntryHev1::nalu_types)
      .def_rw("nalu_data", &PySampleEntryHev1::nalu_data)
      .def_rw("length_size_minus_one", &PySampleEntryHev1::length_size_minus_one)
      .def_rw("general_tier_flag", &PySampleEntryHev1::general_tier_flag)
      .def_rw("general_profile_space", &PySampleEntryHev1::general_profile_space)
      .def_rw("general_profile_compatibility_flags",
              &PySampleEntryHev1::general_profile_compatibility_flags)
      .def_rw("general_constraint_indicator_flags",
              &PySampleEntryHev1::general_constraint_indicator_flags)
      .def_rw("chroma_format_idc", &PySampleEntryHev1::chroma_format_idc)
      .def_rw("bit_depth_luma_minus8", &PySampleEntryHev1::bit_depth_luma_minus8)
      .def_rw("bit_depth_chroma_minus8", &PySampleEntryHev1::bit_depth_chroma_minus8)
      .def_rw("min_spatial_segmentation_idc",
              &PySampleEntryHev1::min_spatial_segmentation_idc)
      .def_rw("parallelism_type", &PySampleEntryHev1::parallelism_type)
      .def_rw("avg_frame_rate", &PySampleEntryHev1::avg_frame_rate)
      .def_rw("constant_frame_rate", &PySampleEntryHev1::constant_frame_rate)
      .def_rw("num_temporal_layers", &PySampleEntryHev1::num_temporal_layers)
      .def_rw("temporal_id_nested", &PySampleEntryHev1::temporal_id_nested);

  // サンプルエントリー: VP08
  nb::class_<PySampleEntryVp08>(m, "SampleEntryVp08")
      .def(nb::init<>())
      .def_rw("width", &PySampleEntryVp08::width)
      .def_rw("height", &PySampleEntryVp08::height)
      .def_rw("bit_depth", &PySampleEntryVp08::bit_depth)
      .def_rw("chroma_subsampling", &PySampleEntryVp08::chroma_subsampling)
      .def_rw("video_full_range_flag", &PySampleEntryVp08::video_full_range_flag)
      .def_rw("colour_primaries", &PySampleEntryVp08::colour_primaries)
      .def_rw("transfer_characteristics", &PySampleEntryVp08::transfer_characteristics)
      .def_rw("matrix_coefficients", &PySampleEntryVp08::matrix_coefficients);

  // サンプルエントリー: VP09
  nb::class_<PySampleEntryVp09>(m, "SampleEntryVp09")
      .def(nb::init<>())
      .def_rw("width", &PySampleEntryVp09::width)
      .def_rw("height", &PySampleEntryVp09::height)
      .def_rw("profile", &PySampleEntryVp09::profile)
      .def_rw("level", &PySampleEntryVp09::level)
      .def_rw("bit_depth", &PySampleEntryVp09::bit_depth)
      .def_rw("chroma_subsampling", &PySampleEntryVp09::chroma_subsampling)
      .def_rw("video_full_range_flag", &PySampleEntryVp09::video_full_range_flag)
      .def_rw("colour_primaries", &PySampleEntryVp09::colour_primaries)
      .def_rw("transfer_characteristics", &PySampleEntryVp09::transfer_characteristics)
      .def_rw("matrix_coefficients", &PySampleEntryVp09::matrix_coefficients);

  // サンプルエントリー: AV01
  nb::class_<PySampleEntryAv01>(m, "SampleEntryAv01")
      .def(nb::init<>())
      .def_rw("width", &PySampleEntryAv01::width)
      .def_rw("height", &PySampleEntryAv01::height)
      .def_rw("config_obus", &PySampleEntryAv01::config_obus)
      .def_rw("seq_profile", &PySampleEntryAv01::seq_profile)
      .def_rw("seq_level_idx_0", &PySampleEntryAv01::seq_level_idx_0)
      .def_rw("seq_tier_0", &PySampleEntryAv01::seq_tier_0)
      .def_rw("high_bitdepth", &PySampleEntryAv01::high_bitdepth)
      .def_rw("twelve_bit", &PySampleEntryAv01::twelve_bit)
      .def_rw("monochrome", &PySampleEntryAv01::monochrome)
      .def_rw("chroma_subsampling_x", &PySampleEntryAv01::chroma_subsampling_x)
      .def_rw("chroma_subsampling_y", &PySampleEntryAv01::chroma_subsampling_y)
      .def_rw("chroma_sample_position", &PySampleEntryAv01::chroma_sample_position)
      .def_rw("initial_presentation_delay_present",
              &PySampleEntryAv01::initial_presentation_delay_present)
      .def_rw("initial_presentation_delay_minus_one",
              &PySampleEntryAv01::initial_presentation_delay_minus_one);

  // サンプルエントリー: Opus
  nb::class_<PySampleEntryOpus>(m, "SampleEntryOpus")
      .def(nb::init<>())
      .def_rw("channel_count", &PySampleEntryOpus::channel_count)
      .def_rw("sample_rate", &PySampleEntryOpus::sample_rate)
      .def_rw("sample_size", &PySampleEntryOpus::sample_size)
      .def_rw("pre_skip", &PySampleEntryOpus::pre_skip)
      .def_rw("input_sample_rate", &PySampleEntryOpus::input_sample_rate)
      .def_rw("output_gain", &PySampleEntryOpus::output_gain);

  // サンプルエントリー: MP4A
  nb::class_<PySampleEntryMp4a>(m, "SampleEntryMp4a")
      .def(nb::init<>())
      .def_rw("channel_count", &PySampleEntryMp4a::channel_count)
      .def_rw("sample_rate", &PySampleEntryMp4a::sample_rate)
      .def_rw("dec_specific_info", &PySampleEntryMp4a::dec_specific_info)
      .def_rw("sample_size", &PySampleEntryMp4a::sample_size)
      .def_rw("buffer_size_db", &PySampleEntryMp4a::buffer_size_db)
      .def_rw("max_bitrate", &PySampleEntryMp4a::max_bitrate)
      .def_rw("avg_bitrate", &PySampleEntryMp4a::avg_bitrate);

  // Demux サンプル
  nb::class_<PyDemuxSample>(m, "DemuxSample")
      .def_ro("track", &PyDemuxSample::track)
      .def_ro("sample_entry", &PyDemuxSample::sample_entry)
      .def_ro("keyframe", &PyDemuxSample::keyframe)
      .def_ro("timestamp", &PyDemuxSample::timestamp)
      .def_ro("duration", &PyDemuxSample::duration)
      .def_ro("data_offset", &PyDemuxSample::data_offset)
      .def_ro("data_size", &PyDemuxSample::data_size)
      .def("__repr__", [](const PyDemuxSample &s) {
        return "DemuxSample(track_id=" + std::to_string(s.track.track_id) +
               ", keyframe=" + (s.keyframe ? "True" : "False") +
               ", timestamp=" + std::to_string(s.timestamp) +
               ", data_size=" + std::to_string(s.data_size) + ")";
      });

  // Demuxer
  nb::class_<PyFileDemuxer>(m, "FileDemuxer")
      .def(nb::init<>())
      .def("get_required_input", &PyFileDemuxer::get_required_input,
           "次の処理に必要な入力データの位置とサイズを取得")
      .def("handle_input", &PyFileDemuxer::handle_input, "position"_a, "data"_a,
           "入力データを供給")
      .def("get_tracks", &PyFileDemuxer::get_tracks, "トラック情報を取得")
      .def("next_sample", &PyFileDemuxer::next_sample, "次のサンプルを取得")
      .def("requires_input", &PyFileDemuxer::requires_input,
           "入力データが必要かどうかを確認");

  // Muxer
  nb::class_<PyFileMuxer>(m, "FileMuxer")
      .def(nb::init<>())
      .def("set_reserved_moov_box_size", &PyFileMuxer::set_reserved_moov_box_size,
           "size"_a, "faststart 用の moov ボックスサイズを設定")
      .def("initialize", &PyFileMuxer::initialize, "マルチプレックス処理を初期化")
      .def("next_output", &PyFileMuxer::next_output, "出力データを取得")
      .def("append_sample", &PyFileMuxer::append_sample, "track_kind"_a,
           "sample_entry"_a, "keyframe"_a, "timescale"_a, "duration"_a,
           "data_offset"_a, "data_size"_a, "サンプルを追加")
      .def("finalize", &PyFileMuxer::finalize, "マルチプレックス処理を完了")
      .def("is_finalized", &PyFileMuxer::is_finalized,
           "ファイナライズ済みかどうかを確認");
}
