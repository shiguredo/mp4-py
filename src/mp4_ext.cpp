// mp4-rust C API の nanobind ラッパー
//
// このモジュールは mp4-rust の C API を Python から使いやすい形式で公開する

#include "mp4.h"

#include <Python.h>
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include <cstdint>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace nb = nanobind;
using namespace nb::literals;

// ===== 例外クラス =====

class Mp4Exception : public std::runtime_error {
 public:
  explicit Mp4Exception(const std::string& msg) : std::runtime_error(msg) {}
};

// ===== ユーティリティ関数 =====

static std::string library_version() {
  return std::string(mp4_library_version());
}

static uint32_t estimate_maximum_moov_box_size(uint32_t audio_sample_count,
                                               uint32_t video_sample_count) {
  return mp4_estimate_maximum_moov_box_size(audio_sample_count,
                                            video_sample_count);
}

static std::string track_kind_to_string(Mp4TrackKind kind) {
  switch (kind) {
    case MP4_TRACK_KIND_AUDIO:
      return "audio";
    case MP4_TRACK_KIND_VIDEO:
      return "video";
    default:
      throw Mp4Exception("Unknown track kind");
  }
}

static Mp4TrackKind string_to_track_kind(const std::string& kind) {
  if (kind == "audio")
    return MP4_TRACK_KIND_AUDIO;
  if (kind == "video")
    return MP4_TRACK_KIND_VIDEO;
  throw Mp4Exception("Invalid track kind: " + kind);
}

// ===== サンプルエントリー構造体 =====

struct PyMp4SampleEntryAvc1 {
  uint16_t width = 0;
  uint16_t height = 0;
  uint8_t avc_profile_indication = 0;
  uint8_t profile_compatibility = 0;
  uint8_t avc_level_indication = 0;
  uint8_t length_size_minus_one = 3;
  std::vector<nb::bytes> sps_data;
  std::vector<nb::bytes> pps_data;
  std::optional<uint8_t> chroma_format;
  std::optional<uint8_t> bit_depth_luma_minus8;
  std::optional<uint8_t> bit_depth_chroma_minus8;

  PyMp4SampleEntryAvc1() = default;
  PyMp4SampleEntryAvc1(uint16_t width_,
                       uint16_t height_,
                       uint8_t avc_profile_indication_,
                       uint8_t avc_level_indication_,
                       uint8_t profile_compatibility_,
                       const std::vector<nb::bytes>& sps_data_,
                       const std::vector<nb::bytes>& pps_data_,
                       uint8_t length_size_minus_one_,
                       std::optional<uint8_t> chroma_format_,
                       std::optional<uint8_t> bit_depth_luma_minus8_,
                       std::optional<uint8_t> bit_depth_chroma_minus8_)
      : width(width_),
        height(height_),
        avc_profile_indication(avc_profile_indication_),
        profile_compatibility(profile_compatibility_),
        avc_level_indication(avc_level_indication_),
        length_size_minus_one(length_size_minus_one_),
        sps_data(sps_data_),
        pps_data(pps_data_),
        chroma_format(chroma_format_),
        bit_depth_luma_minus8(bit_depth_luma_minus8_),
        bit_depth_chroma_minus8(bit_depth_chroma_minus8_) {}

  static PyMp4SampleEntryAvc1 from_raw(const Mp4SampleEntryAvc1& raw) {
    PyMp4SampleEntryAvc1 result;
    result.width = raw.width;
    result.height = raw.height;
    result.avc_profile_indication = raw.avc_profile_indication;
    result.profile_compatibility = raw.profile_compatibility;
    result.avc_level_indication = raw.avc_level_indication;
    result.length_size_minus_one = raw.length_size_minus_one;

    // SPS データを抽出
    if (raw.sps_count > 0 && raw.sps_data && raw.sps_sizes) {
      for (uint32_t i = 0; i < raw.sps_count; i++) {
        result.sps_data.push_back(nb::bytes(
            reinterpret_cast<const char*>(raw.sps_data[i]), raw.sps_sizes[i]));
      }
    }

    // PPS データを抽出
    if (raw.pps_count > 0 && raw.pps_data && raw.pps_sizes) {
      for (uint32_t i = 0; i < raw.pps_count; i++) {
        result.pps_data.push_back(nb::bytes(
            reinterpret_cast<const char*>(raw.pps_data[i]), raw.pps_sizes[i]));
      }
    }

    // オプションフィールド
    if (raw.is_chroma_format_present) {
      result.chroma_format = raw.chroma_format;
    }
    if (raw.is_bit_depth_luma_minus8_present) {
      result.bit_depth_luma_minus8 = raw.bit_depth_luma_minus8;
    }
    if (raw.is_bit_depth_chroma_minus8_present) {
      result.bit_depth_chroma_minus8 = raw.bit_depth_chroma_minus8;
    }

    return result;
  }
};

struct PyMp4SampleEntryHev1 {
  uint16_t width = 0;
  uint16_t height = 0;
  uint8_t general_profile_space = 0;
  uint8_t general_tier_flag = 0;
  uint8_t general_profile_idc = 0;
  uint32_t general_profile_compatibility_flags = 0;
  uint64_t general_constraint_indicator_flags = 0;
  uint8_t general_level_idc = 0;
  uint8_t chroma_format_idc = 1;
  uint8_t bit_depth_luma_minus8 = 0;
  uint8_t bit_depth_chroma_minus8 = 0;
  uint16_t min_spatial_segmentation_idc = 0;
  uint8_t parallelism_type = 0;
  uint16_t avg_frame_rate = 0;
  uint8_t constant_frame_rate = 0;
  uint8_t num_temporal_layers = 0;
  uint8_t temporal_id_nested = 0;
  uint8_t length_size_minus_one = 3;
  std::vector<uint8_t> nalu_types;
  std::vector<nb::bytes> nalu_data;

  PyMp4SampleEntryHev1() = default;
  PyMp4SampleEntryHev1(uint16_t width_,
                       uint16_t height_,
                       uint8_t general_profile_idc_,
                       uint8_t general_level_idc_,
                       const std::vector<uint8_t>& nalu_types_,
                       const std::vector<nb::bytes>& nalu_data_,
                       uint8_t general_profile_space_,
                       uint8_t general_tier_flag_,
                       uint32_t general_profile_compatibility_flags_,
                       uint64_t general_constraint_indicator_flags_,
                       uint8_t chroma_format_idc_,
                       uint8_t bit_depth_luma_minus8_,
                       uint8_t bit_depth_chroma_minus8_,
                       uint16_t min_spatial_segmentation_idc_,
                       uint8_t parallelism_type_,
                       uint16_t avg_frame_rate_,
                       uint8_t constant_frame_rate_,
                       uint8_t num_temporal_layers_,
                       uint8_t temporal_id_nested_,
                       uint8_t length_size_minus_one_)
      : width(width_),
        height(height_),
        general_profile_space(general_profile_space_),
        general_tier_flag(general_tier_flag_),
        general_profile_idc(general_profile_idc_),
        general_profile_compatibility_flags(
            general_profile_compatibility_flags_),
        general_constraint_indicator_flags(general_constraint_indicator_flags_),
        general_level_idc(general_level_idc_),
        chroma_format_idc(chroma_format_idc_),
        bit_depth_luma_minus8(bit_depth_luma_minus8_),
        bit_depth_chroma_minus8(bit_depth_chroma_minus8_),
        min_spatial_segmentation_idc(min_spatial_segmentation_idc_),
        parallelism_type(parallelism_type_),
        avg_frame_rate(avg_frame_rate_),
        constant_frame_rate(constant_frame_rate_),
        num_temporal_layers(num_temporal_layers_),
        temporal_id_nested(temporal_id_nested_),
        length_size_minus_one(length_size_minus_one_),
        nalu_types(nalu_types_),
        nalu_data(nalu_data_) {}

  static PyMp4SampleEntryHev1 from_raw(const Mp4SampleEntryHev1& raw) {
    PyMp4SampleEntryHev1 result;
    result.width = raw.width;
    result.height = raw.height;
    result.general_profile_space = raw.general_profile_space;
    result.general_tier_flag = raw.general_tier_flag;
    result.general_profile_idc = raw.general_profile_idc;
    result.general_profile_compatibility_flags =
        raw.general_profile_compatibility_flags;
    result.general_constraint_indicator_flags =
        raw.general_constraint_indicator_flags;
    result.general_level_idc = raw.general_level_idc;
    result.chroma_format_idc = raw.chroma_format_idc;
    result.bit_depth_luma_minus8 = raw.bit_depth_luma_minus8;
    result.bit_depth_chroma_minus8 = raw.bit_depth_chroma_minus8;
    result.min_spatial_segmentation_idc = raw.min_spatial_segmentation_idc;
    result.parallelism_type = raw.parallelism_type;
    result.avg_frame_rate = raw.avg_frame_rate;
    result.constant_frame_rate = raw.constant_frame_rate;
    result.num_temporal_layers = raw.num_temporal_layers;
    result.temporal_id_nested = raw.temporal_id_nested;
    result.length_size_minus_one = raw.length_size_minus_one;

    // NALU データを抽出
    if (raw.nalu_array_count > 0 && raw.nalu_types) {
      uint32_t offset = 0;
      for (uint32_t i = 0; i < raw.nalu_array_count; i++) {
        uint32_t count = raw.nalu_counts ? raw.nalu_counts[i] : 0;
        for (uint32_t j = 0; j < count; j++) {
          result.nalu_types.push_back(raw.nalu_types[i]);
          uint32_t size = raw.nalu_sizes[offset + j];
          result.nalu_data.push_back(nb::bytes(
              reinterpret_cast<const char*>(raw.nalu_data[offset + j]), size));
        }
        offset += count;
      }
    }

    return result;
  }
};

struct PyMp4SampleEntryVp08 {
  uint16_t width = 0;
  uint16_t height = 0;
  uint8_t bit_depth = 8;
  uint8_t chroma_subsampling = 0;
  bool video_full_range_flag = false;
  uint8_t colour_primaries = 1;
  uint8_t transfer_characteristics = 1;
  uint8_t matrix_coefficients = 1;

  PyMp4SampleEntryVp08() = default;
  PyMp4SampleEntryVp08(uint16_t width_,
                       uint16_t height_,
                       uint8_t bit_depth_ = 8,
                       uint8_t chroma_subsampling_ = 0,
                       bool video_full_range_flag_ = false,
                       uint8_t colour_primaries_ = 1,
                       uint8_t transfer_characteristics_ = 1,
                       uint8_t matrix_coefficients_ = 1)
      : width(width_),
        height(height_),
        bit_depth(bit_depth_),
        chroma_subsampling(chroma_subsampling_),
        video_full_range_flag(video_full_range_flag_),
        colour_primaries(colour_primaries_),
        transfer_characteristics(transfer_characteristics_),
        matrix_coefficients(matrix_coefficients_) {}

  static PyMp4SampleEntryVp08 from_raw(const Mp4SampleEntryVp08& raw) {
    PyMp4SampleEntryVp08 result;
    result.width = raw.width;
    result.height = raw.height;
    result.bit_depth = raw.bit_depth;
    result.chroma_subsampling = raw.chroma_subsampling;
    result.video_full_range_flag = raw.video_full_range_flag;
    result.colour_primaries = raw.colour_primaries;
    result.transfer_characteristics = raw.transfer_characteristics;
    result.matrix_coefficients = raw.matrix_coefficients;
    return result;
  }
};

struct PyMp4SampleEntryVp09 {
  uint16_t width = 0;
  uint16_t height = 0;
  uint8_t profile = 0;
  uint8_t level = 0;
  uint8_t bit_depth = 8;
  uint8_t chroma_subsampling = 0;
  bool video_full_range_flag = false;
  uint8_t colour_primaries = 1;
  uint8_t transfer_characteristics = 1;
  uint8_t matrix_coefficients = 1;

  PyMp4SampleEntryVp09() = default;
  PyMp4SampleEntryVp09(uint16_t width_,
                       uint16_t height_,
                       uint8_t profile_,
                       uint8_t level_,
                       uint8_t bit_depth_ = 8,
                       uint8_t chroma_subsampling_ = 0,
                       bool video_full_range_flag_ = false,
                       uint8_t colour_primaries_ = 1,
                       uint8_t transfer_characteristics_ = 1,
                       uint8_t matrix_coefficients_ = 1)
      : width(width_),
        height(height_),
        profile(profile_),
        level(level_),
        bit_depth(bit_depth_),
        chroma_subsampling(chroma_subsampling_),
        video_full_range_flag(video_full_range_flag_),
        colour_primaries(colour_primaries_),
        transfer_characteristics(transfer_characteristics_),
        matrix_coefficients(matrix_coefficients_) {}

  static PyMp4SampleEntryVp09 from_raw(const Mp4SampleEntryVp09& raw) {
    PyMp4SampleEntryVp09 result;
    result.width = raw.width;
    result.height = raw.height;
    result.profile = raw.profile;
    result.level = raw.level;
    result.bit_depth = raw.bit_depth;
    result.chroma_subsampling = raw.chroma_subsampling;
    result.video_full_range_flag = raw.video_full_range_flag;
    result.colour_primaries = raw.colour_primaries;
    result.transfer_characteristics = raw.transfer_characteristics;
    result.matrix_coefficients = raw.matrix_coefficients;
    return result;
  }
};

struct PyMp4SampleEntryAv01 {
  uint16_t width = 0;
  uint16_t height = 0;
  uint8_t seq_profile = 0;
  uint8_t seq_level_idx_0 = 0;
  uint8_t seq_tier_0 = 0;
  uint8_t high_bitdepth = 0;
  uint8_t twelve_bit = 0;
  uint8_t monochrome = 0;
  uint8_t chroma_subsampling_x = 1;
  uint8_t chroma_subsampling_y = 1;
  uint8_t chroma_sample_position = 0;
  bool initial_presentation_delay_present = false;
  uint8_t initial_presentation_delay_minus_one = 0;
  nb::bytes config_obus;

  PyMp4SampleEntryAv01() = default;
  PyMp4SampleEntryAv01(uint16_t width_,
                       uint16_t height_,
                       uint8_t seq_profile_,
                       uint8_t seq_level_idx_0_,
                       const nb::bytes& config_obus_,
                       uint8_t seq_tier_0_,
                       uint8_t high_bitdepth_,
                       uint8_t twelve_bit_,
                       uint8_t monochrome_,
                       uint8_t chroma_subsampling_x_,
                       uint8_t chroma_subsampling_y_,
                       uint8_t chroma_sample_position_,
                       bool initial_presentation_delay_present_,
                       uint8_t initial_presentation_delay_minus_one_)
      : width(width_),
        height(height_),
        seq_profile(seq_profile_),
        seq_level_idx_0(seq_level_idx_0_),
        seq_tier_0(seq_tier_0_),
        high_bitdepth(high_bitdepth_),
        twelve_bit(twelve_bit_),
        monochrome(monochrome_),
        chroma_subsampling_x(chroma_subsampling_x_),
        chroma_subsampling_y(chroma_subsampling_y_),
        chroma_sample_position(chroma_sample_position_),
        initial_presentation_delay_present(initial_presentation_delay_present_),
        initial_presentation_delay_minus_one(
            initial_presentation_delay_minus_one_),
        config_obus(config_obus_) {}

  static PyMp4SampleEntryAv01 from_raw(const Mp4SampleEntryAv01& raw) {
    PyMp4SampleEntryAv01 result;
    result.width = raw.width;
    result.height = raw.height;
    result.seq_profile = raw.seq_profile;
    result.seq_level_idx_0 = raw.seq_level_idx_0;
    result.seq_tier_0 = raw.seq_tier_0;
    result.high_bitdepth = raw.high_bitdepth;
    result.twelve_bit = raw.twelve_bit;
    result.monochrome = raw.monochrome;
    result.chroma_subsampling_x = raw.chroma_subsampling_x;
    result.chroma_subsampling_y = raw.chroma_subsampling_y;
    result.chroma_sample_position = raw.chroma_sample_position;
    result.initial_presentation_delay_present =
        raw.initial_presentation_delay_present;
    result.initial_presentation_delay_minus_one =
        raw.initial_presentation_delay_minus_one;
    result.config_obus = nb::bytes(
        reinterpret_cast<const char*>(raw.config_obus), raw.config_obus_size);
    return result;
  }
};

struct PyMp4SampleEntryOpus {
  uint8_t channel_count = 0;
  uint16_t sample_rate = 0;
  uint16_t sample_size = 16;
  uint16_t pre_skip = 0;
  std::optional<uint32_t> input_sample_rate;
  int16_t output_gain = 0;

  PyMp4SampleEntryOpus() = default;
  PyMp4SampleEntryOpus(
      uint8_t channel_count_,
      uint16_t sample_rate_,
      uint16_t sample_size_ = 16,
      uint16_t pre_skip_ = 0,
      std::optional<uint32_t> input_sample_rate_ = std::nullopt,
      int16_t output_gain_ = 0)
      : channel_count(channel_count_),
        sample_rate(sample_rate_),
        sample_size(sample_size_),
        pre_skip(pre_skip_),
        input_sample_rate(input_sample_rate_),
        output_gain(output_gain_) {}

  static PyMp4SampleEntryOpus from_raw(const Mp4SampleEntryOpus& raw) {
    PyMp4SampleEntryOpus result;
    result.channel_count = raw.channel_count;
    result.sample_rate = raw.sample_rate;
    result.sample_size = raw.sample_size;
    result.pre_skip = raw.pre_skip;
    result.input_sample_rate = raw.input_sample_rate;
    result.output_gain = raw.output_gain;
    return result;
  }
};

struct PyMp4SampleEntryMp4a {
  uint8_t channel_count = 0;
  uint16_t sample_rate = 0;
  uint16_t sample_size = 16;
  uint32_t buffer_size_db = 0;
  uint32_t max_bitrate = 0;
  uint32_t avg_bitrate = 0;
  nb::bytes dec_specific_info;

  PyMp4SampleEntryMp4a() = default;
  PyMp4SampleEntryMp4a(uint8_t channel_count_,
                       uint16_t sample_rate_,
                       const nb::bytes& dec_specific_info_,
                       uint16_t sample_size_,
                       uint32_t buffer_size_db_,
                       uint32_t max_bitrate_,
                       uint32_t avg_bitrate_)
      : channel_count(channel_count_),
        sample_rate(sample_rate_),
        sample_size(sample_size_),
        buffer_size_db(buffer_size_db_),
        max_bitrate(max_bitrate_),
        avg_bitrate(avg_bitrate_),
        dec_specific_info(dec_specific_info_) {}

  static PyMp4SampleEntryMp4a from_raw(const Mp4SampleEntryMp4a& raw) {
    PyMp4SampleEntryMp4a result;
    result.channel_count = raw.channel_count;
    result.sample_rate = raw.sample_rate;
    result.sample_size = raw.sample_size;
    result.buffer_size_db = raw.buffer_size_db;
    result.max_bitrate = raw.max_bitrate;
    result.avg_bitrate = raw.avg_bitrate;
    result.dec_specific_info =
        nb::bytes(reinterpret_cast<const char*>(raw.dec_specific_info),
                  raw.dec_specific_info_size);
    return result;
  }
};

struct PyMp4SampleEntryFlac {
  uint8_t channel_count = 0;
  uint16_t sample_rate = 0;
  uint16_t sample_size = 16;
  nb::bytes streaminfo_data;

  PyMp4SampleEntryFlac() = default;
  PyMp4SampleEntryFlac(uint8_t channel_count_,
                       uint16_t sample_rate_,
                       const nb::bytes& streaminfo_data_,
                       uint16_t sample_size_)
      : channel_count(channel_count_),
        sample_rate(sample_rate_),
        sample_size(sample_size_),
        streaminfo_data(streaminfo_data_) {}

  static PyMp4SampleEntryFlac from_raw(const Mp4SampleEntryFlac& raw) {
    PyMp4SampleEntryFlac result;
    result.channel_count = raw.channel_count;
    result.sample_rate = raw.sample_rate;
    result.sample_size = raw.sample_size;
    result.streaminfo_data =
        nb::bytes(reinterpret_cast<const char*>(raw.streaminfo_data),
                  raw.streaminfo_size);
    return result;
  }
};

// サンプルエントリーを C API の構造体から Python オブジェクトに変換
static nb::object sample_entry_from_raw(const Mp4SampleEntry* raw) {
  if (!raw)
    return nb::none();

  switch (raw->kind) {
    case MP4_SAMPLE_ENTRY_KIND_AVC1:
      return nb::cast(PyMp4SampleEntryAvc1::from_raw(raw->data.avc1));
    case MP4_SAMPLE_ENTRY_KIND_HEV1:
      return nb::cast(PyMp4SampleEntryHev1::from_raw(raw->data.hev1));
    case MP4_SAMPLE_ENTRY_KIND_VP08:
      return nb::cast(PyMp4SampleEntryVp08::from_raw(raw->data.vp08));
    case MP4_SAMPLE_ENTRY_KIND_VP09:
      return nb::cast(PyMp4SampleEntryVp09::from_raw(raw->data.vp09));
    case MP4_SAMPLE_ENTRY_KIND_AV01:
      return nb::cast(PyMp4SampleEntryAv01::from_raw(raw->data.av01));
    case MP4_SAMPLE_ENTRY_KIND_OPUS:
      return nb::cast(PyMp4SampleEntryOpus::from_raw(raw->data.opus));
    case MP4_SAMPLE_ENTRY_KIND_MP4A:
      return nb::cast(PyMp4SampleEntryMp4a::from_raw(raw->data.mp4a));
    case MP4_SAMPLE_ENTRY_KIND_FLAC:
      return nb::cast(PyMp4SampleEntryFlac::from_raw(raw->data.flac));
    default:
      throw Mp4Exception("Unsupported sample entry kind");
  }
}

// ===== トラック情報 =====

struct PyMp4TrackInfo {
  uint32_t track_id = 0;
  std::string kind;
  uint64_t duration = 0;
  uint32_t timescale = 1;

  PyMp4TrackInfo() = default;
  PyMp4TrackInfo(uint32_t track_id_,
                 const std::string& kind_,
                 uint64_t duration_,
                 uint32_t timescale_)
      : track_id(track_id_),
        kind(kind_),
        duration(duration_),
        timescale(timescale_) {}

  double duration_seconds() const {
    return static_cast<double>(duration) / timescale;
  }

  std::string repr() const {
    return "Mp4TrackInfo(track_id=" + std::to_string(track_id) +
           ", kind=" + kind + ", duration=" + std::to_string(duration) +
           ", timescale=" + std::to_string(timescale) + ")";
  }
};

// ===== Demuxer サンプル =====

class PyMp4DemuxSample {
 public:
  PyMp4TrackInfo track;
  nb::object sample_entry;
  bool keyframe = false;
  uint64_t timestamp = 0;
  uint32_t duration = 0;

  // 遅延読み込み用
  nb::object input_stream_;
  uint64_t data_offset_ = 0;
  uint64_t data_size_ = 0;
  std::optional<nb::bytes> data_cache_;

  PyMp4DemuxSample() = default;
  PyMp4DemuxSample(const PyMp4TrackInfo& track_,
                   const nb::object& sample_entry_,
                   bool keyframe_,
                   uint64_t timestamp_,
                   uint32_t duration_,
                   uint64_t data_offset_,
                   uint64_t data_size_,
                   const nb::object& input_stream_)
      : track(track_),
        sample_entry(sample_entry_),
        keyframe(keyframe_),
        timestamp(timestamp_),
        duration(duration_),
        input_stream_(input_stream_),
        data_offset_(data_offset_),
        data_size_(data_size_) {}

  nb::bytes get_data() {
    if (!data_cache_) {
      input_stream_.attr("seek")(data_offset_);
      nb::object read_result = input_stream_.attr("read")(data_size_);
      data_cache_ = nb::cast<nb::bytes>(read_result);
      if (data_cache_->size() != data_size_) {
        throw Mp4Exception("Failed to read sample data: expected " +
                           std::to_string(data_size_) + " bytes, got " +
                           std::to_string(data_cache_->size()) + " bytes");
      }
    }
    return *data_cache_;
  }

  double timestamp_seconds() const {
    return static_cast<double>(timestamp) / track.timescale;
  }

  double duration_seconds() const {
    return static_cast<double>(duration) / track.timescale;
  }

  std::string repr() const {
    return "Mp4DemuxSample(track_id=" + std::to_string(track.track_id) +
           ", keyframe=" + (keyframe ? "True" : "False") +
           ", timestamp=" + std::to_string(timestamp) +
           ", data_size=" + std::to_string(data_size_) + ")";
  }
};

// ===== Demuxer クラス =====

class PyMp4FileDemuxer {
 public:
  // コピー禁止
  PyMp4FileDemuxer(const PyMp4FileDemuxer&) = delete;
  PyMp4FileDemuxer& operator=(const PyMp4FileDemuxer&) = delete;

  PyMp4FileDemuxer(nb::object source)
      : demuxer_(nullptr), should_close_stream_(false), closed_(false) {
    // ソースの種別を判定
    if (nb::hasattr(source, "__fspath__") || nb::isinstance<nb::str>(source)) {
      // ファイルパスの場合
      nb::object builtins = nb::module_::import_("builtins");
      input_stream_ = builtins.attr("open")(source, "rb");
      should_close_stream_ = true;
    } else {
      // io.IOBase の場合
      input_stream_ = source;
      should_close_stream_ = false;
    }

    // Demuxer を作成
    demuxer_ = mp4_file_demuxer_new();
    if (!demuxer_) {
      throw Mp4Exception("Failed to create mp4 demuxer");
    }
  }

  ~PyMp4FileDemuxer() { close(); }

  PyMp4FileDemuxer& enter() { return *this; }

  void exit(nb::object /*exc_type*/,
            nb::object /*exc_val*/,
            nb::object /*exc_tb*/) {
    close();
  }

  void close() {
    nb::ft_lock_guard lock(mutex_);
    if (closed_)
      return;

    if (demuxer_) {
      mp4_file_demuxer_free(demuxer_);
      demuxer_ = nullptr;
    }

    if (should_close_stream_ && !input_stream_.is_none()) {
      input_stream_.attr("close")();
    }
    input_stream_ = nb::none();
    closed_ = true;
  }

  std::vector<PyMp4TrackInfo> get_tracks() {
    nb::ft_lock_guard lock(mutex_);
    if (closed_)
      throw Mp4Exception("Demuxer is closed");

    while (true) {
      const Mp4DemuxTrackInfo* tracks;
      uint32_t track_count;

      Mp4Error error =
          mp4_file_demuxer_get_tracks(demuxer_, &tracks, &track_count);
      if (error == MP4_ERROR_INPUT_REQUIRED) {
        bool eof = feed_required_input();
        if (eof) {
          throw Mp4Exception("Unexpected end of file while parsing MP4");
        }
        continue;
      }
      check_error(error);

      std::vector<PyMp4TrackInfo> result;
      for (uint32_t i = 0; i < track_count; i++) {
        PyMp4TrackInfo info;
        info.track_id = tracks[i].track_id;
        info.kind = track_kind_to_string(tracks[i].kind);
        info.duration = tracks[i].duration;
        info.timescale = tracks[i].timescale;
        result.push_back(info);
      }
      return result;
    }
  }

  PyMp4FileDemuxer& iter() {
    nb::ft_lock_guard lock(mutex_);
    if (closed_)
      throw Mp4Exception("Demuxer is closed");
    return *this;
  }

  PyMp4DemuxSample next() {
    nb::ft_lock_guard lock(mutex_);
    if (closed_)
      throw Mp4Exception("Demuxer is closed");

    while (true) {
      Mp4DemuxSample raw_sample;
      Mp4Error error = mp4_file_demuxer_next_sample(demuxer_, &raw_sample);
      if (error == MP4_ERROR_INPUT_REQUIRED) {
        bool eof = feed_required_input();
        if (eof) {
          throw nb::stop_iteration();
        }
        continue;
      }
      if (error == MP4_ERROR_NO_MORE_SAMPLES) {
        throw nb::stop_iteration();
      }
      check_error(error);

      PyMp4DemuxSample result;
      result.track.track_id = raw_sample.track->track_id;
      result.track.kind = track_kind_to_string(raw_sample.track->kind);
      result.track.duration = raw_sample.track->duration;
      result.track.timescale = raw_sample.track->timescale;
      result.sample_entry = sample_entry_from_raw(raw_sample.sample_entry);
      result.keyframe = raw_sample.keyframe;
      result.timestamp = raw_sample.timestamp;
      result.duration = raw_sample.duration;
      result.input_stream_ = input_stream_;
      result.data_offset_ = raw_sample.data_offset;
      result.data_size_ = raw_sample.data_size;

      return result;
    }
  }

 private:
  Mp4FileDemuxer* demuxer_;
  nb::object input_stream_;
  bool should_close_stream_;
  bool closed_;
  mutable nb::ft_mutex mutex_;

  void check_error(Mp4Error error) {
    if (error == MP4_ERROR_OK)
      return;

    const char* msg = mp4_file_demuxer_get_last_error(demuxer_);
    std::string msg_str = msg ? msg : "";

    switch (error) {
      case MP4_ERROR_NO_MORE_SAMPLES:
        throw nb::stop_iteration();
      case MP4_ERROR_NULL_POINTER:
        throw std::invalid_argument("Null pointer error: " + msg_str);
      case MP4_ERROR_INPUT_REQUIRED:
        throw Mp4Exception("Input required: " + msg_str);
      default:
        throw Mp4Exception("MP4 error (" + std::to_string(error) +
                           "): " + msg_str);
    }
  }

  // 入力データを供給する。EOF に達した場合は true を返す
  bool feed_required_input() {
    // 無限ループ防止用のカウンター
    constexpr int kMaxIterations = 10000;
    int iteration_count = 0;

    while (true) {
      if (++iteration_count > kMaxIterations) {
        throw Mp4Exception(
            "feed_required_input: too many iterations, possible infinite loop");
      }

      uint64_t required_pos;
      int32_t required_size;

      Mp4Error error = mp4_file_demuxer_get_required_input(
          demuxer_, &required_pos, &required_size);
      check_error(error);

      if (required_size == 0)
        return false;

      input_stream_.attr("seek")(required_pos);

      nb::object data_obj;
      if (required_size == -1) {
        data_obj = input_stream_.attr("read")();
      } else {
        data_obj = input_stream_.attr("read")(required_size);
      }

      nb::bytes data = nb::cast<nb::bytes>(data_obj);
      const auto* data_ptr = static_cast<const uint8_t*>(data.data());
      size_t data_len = data.size();

      error = mp4_file_demuxer_handle_input(demuxer_, required_pos, data_ptr,
                                            static_cast<uint32_t>(data_len));
      check_error(error);

      // 要求サイズより少ないデータしか読めなかった場合（EOF または truncated）
      if (required_size > 0 && static_cast<int32_t>(data_len) < required_size) {
        return true;
      }
    }
  }
};

// ===== Muxer オプション =====

struct PyMp4FileMuxerOptions {
  uint64_t reserved_moov_box_size = 0;

  PyMp4FileMuxerOptions() = default;
  PyMp4FileMuxerOptions(uint64_t reserved_moov_box_size_)
      : reserved_moov_box_size(reserved_moov_box_size_) {}

  static uint32_t estimate_maximum_moov_box_size(uint32_t audio_sample_count,
                                                 uint32_t video_sample_count) {
    return mp4_estimate_maximum_moov_box_size(audio_sample_count,
                                              video_sample_count);
  }
};

// ===== Muxer サンプル =====

struct PyMp4MuxSample {
  std::string track_kind;
  nb::object sample_entry;
  bool keyframe = false;
  uint32_t timescale = 0;
  uint32_t duration = 0;
  nb::bytes data;

  PyMp4MuxSample() = default;
  PyMp4MuxSample(const std::string& track_kind_,
                 const nb::object& sample_entry_,
                 bool keyframe_,
                 uint32_t timescale_,
                 uint32_t duration_,
                 const nb::bytes& data_)
      : track_kind(track_kind_),
        sample_entry(sample_entry_),
        keyframe(keyframe_),
        timescale(timescale_),
        duration(duration_),
        data(data_) {}

  std::string repr() const {
    return "Mp4MuxSample(track_kind=" + track_kind +
           ", keyframe=" + (keyframe ? "True" : "False") +
           ", timescale=" + std::to_string(timescale) +
           ", duration=" + std::to_string(duration) +
           ", data_size=" + std::to_string(data.size()) + ")";
  }
};

// ===== Muxer クラス =====

// サンプルエントリーを Python オブジェクトから C API の構造体に変換するためのヘルパー
class SampleEntryConverter {
 public:
  Mp4SampleEntry raw_entry;
  bool valid = false;

  // 各種バッファ（メモリを保持するため）
  std::vector<std::vector<uint8_t>> sps_buffers;
  std::vector<const uint8_t*> sps_pointers;
  std::vector<uint32_t> sps_sizes;
  std::vector<std::vector<uint8_t>> pps_buffers;
  std::vector<const uint8_t*> pps_pointers;
  std::vector<uint32_t> pps_sizes;
  std::vector<uint8_t> nalu_types_buffer;
  std::vector<uint32_t> nalu_counts_buffer;
  std::vector<std::vector<uint8_t>> nalu_data_buffers;
  std::vector<const uint8_t*> nalu_data_pointers;
  std::vector<uint32_t> nalu_sizes_buffer;
  std::vector<uint8_t> config_obus_buffer;
  std::vector<uint8_t> dec_specific_info_buffer;
  std::vector<uint8_t> streaminfo_buffer;

  void convert(nb::object entry) {
    if (entry.is_none()) {
      valid = false;
      return;
    }

    valid = true;

    if (nb::isinstance<PyMp4SampleEntryAvc1>(entry)) {
      convert_avc1(nb::cast<PyMp4SampleEntryAvc1&>(entry));
    } else if (nb::isinstance<PyMp4SampleEntryHev1>(entry)) {
      convert_hev1(nb::cast<PyMp4SampleEntryHev1&>(entry));
    } else if (nb::isinstance<PyMp4SampleEntryVp08>(entry)) {
      convert_vp08(nb::cast<PyMp4SampleEntryVp08&>(entry));
    } else if (nb::isinstance<PyMp4SampleEntryVp09>(entry)) {
      convert_vp09(nb::cast<PyMp4SampleEntryVp09&>(entry));
    } else if (nb::isinstance<PyMp4SampleEntryAv01>(entry)) {
      convert_av01(nb::cast<PyMp4SampleEntryAv01&>(entry));
    } else if (nb::isinstance<PyMp4SampleEntryOpus>(entry)) {
      convert_opus(nb::cast<PyMp4SampleEntryOpus&>(entry));
    } else if (nb::isinstance<PyMp4SampleEntryMp4a>(entry)) {
      convert_mp4a(nb::cast<PyMp4SampleEntryMp4a&>(entry));
    } else if (nb::isinstance<PyMp4SampleEntryFlac>(entry)) {
      convert_flac(nb::cast<PyMp4SampleEntryFlac&>(entry));
    } else {
      throw Mp4Exception("Unsupported sample entry type");
    }
  }

 private:
  void convert_avc1(PyMp4SampleEntryAvc1& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_AVC1;
    auto& avc1 = raw_entry.data.avc1;

    avc1.width = entry.width;
    avc1.height = entry.height;
    avc1.avc_profile_indication = entry.avc_profile_indication;
    avc1.profile_compatibility = entry.profile_compatibility;
    avc1.avc_level_indication = entry.avc_level_indication;
    avc1.length_size_minus_one = entry.length_size_minus_one;

    // SPS データ
    for (auto& sps : entry.sps_data) {
      const auto* ptr = static_cast<const uint8_t*>(sps.data());
      sps_buffers.emplace_back(ptr, ptr + sps.size());
      sps_sizes.push_back(static_cast<uint32_t>(sps.size()));
    }
    for (auto& buf : sps_buffers) {
      sps_pointers.push_back(buf.data());
    }
    avc1.sps_data = sps_pointers.empty() ? nullptr : sps_pointers.data();
    avc1.sps_sizes = sps_sizes.empty() ? nullptr : sps_sizes.data();
    avc1.sps_count = static_cast<uint32_t>(sps_buffers.size());

    // PPS データ
    for (auto& pps : entry.pps_data) {
      const auto* ptr = static_cast<const uint8_t*>(pps.data());
      pps_buffers.emplace_back(ptr, ptr + pps.size());
      pps_sizes.push_back(static_cast<uint32_t>(pps.size()));
    }
    for (auto& buf : pps_buffers) {
      pps_pointers.push_back(buf.data());
    }
    avc1.pps_data = pps_pointers.empty() ? nullptr : pps_pointers.data();
    avc1.pps_sizes = pps_sizes.empty() ? nullptr : pps_sizes.data();
    avc1.pps_count = static_cast<uint32_t>(pps_buffers.size());

    // オプションフィールド
    avc1.is_chroma_format_present = entry.chroma_format.has_value();
    avc1.chroma_format = entry.chroma_format.value_or(0);
    avc1.is_bit_depth_luma_minus8_present =
        entry.bit_depth_luma_minus8.has_value();
    avc1.bit_depth_luma_minus8 = entry.bit_depth_luma_minus8.value_or(0);
    avc1.is_bit_depth_chroma_minus8_present =
        entry.bit_depth_chroma_minus8.has_value();
    avc1.bit_depth_chroma_minus8 = entry.bit_depth_chroma_minus8.value_or(0);
  }

  void convert_hev1(PyMp4SampleEntryHev1& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_HEV1;
    auto& hev1 = raw_entry.data.hev1;

    hev1.width = entry.width;
    hev1.height = entry.height;
    hev1.general_profile_space = entry.general_profile_space;
    hev1.general_tier_flag = entry.general_tier_flag;
    hev1.general_profile_idc = entry.general_profile_idc;
    hev1.general_profile_compatibility_flags =
        entry.general_profile_compatibility_flags;
    hev1.general_constraint_indicator_flags =
        entry.general_constraint_indicator_flags;
    hev1.general_level_idc = entry.general_level_idc;
    hev1.chroma_format_idc = entry.chroma_format_idc;
    hev1.bit_depth_luma_minus8 = entry.bit_depth_luma_minus8;
    hev1.bit_depth_chroma_minus8 = entry.bit_depth_chroma_minus8;
    hev1.min_spatial_segmentation_idc = entry.min_spatial_segmentation_idc;
    hev1.parallelism_type = entry.parallelism_type;
    hev1.avg_frame_rate = entry.avg_frame_rate;
    hev1.constant_frame_rate = entry.constant_frame_rate;
    hev1.num_temporal_layers = entry.num_temporal_layers;
    hev1.temporal_id_nested = entry.temporal_id_nested;
    hev1.length_size_minus_one = entry.length_size_minus_one;

    // nalu_types と nalu_data の長さが等しいことをチェック
    if (entry.nalu_types.size() != entry.nalu_data.size()) {
      throw Mp4Exception("nalu_types and nalu_data must have the same length");
    }

    // NALU データ
    nalu_types_buffer = entry.nalu_types;
    nalu_counts_buffer.resize(entry.nalu_types.size(), 1);

    for (auto& nalu : entry.nalu_data) {
      const auto* ptr = static_cast<const uint8_t*>(nalu.data());
      nalu_data_buffers.emplace_back(ptr, ptr + nalu.size());
      nalu_sizes_buffer.push_back(static_cast<uint32_t>(nalu.size()));
    }
    for (auto& buf : nalu_data_buffers) {
      nalu_data_pointers.push_back(buf.data());
    }

    hev1.nalu_array_count = static_cast<uint32_t>(entry.nalu_types.size());
    hev1.nalu_types =
        nalu_types_buffer.empty() ? nullptr : nalu_types_buffer.data();
    hev1.nalu_counts =
        nalu_counts_buffer.empty() ? nullptr : nalu_counts_buffer.data();
    hev1.nalu_data =
        nalu_data_pointers.empty() ? nullptr : nalu_data_pointers.data();
    hev1.nalu_sizes =
        nalu_sizes_buffer.empty() ? nullptr : nalu_sizes_buffer.data();
  }

  void convert_vp08(PyMp4SampleEntryVp08& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_VP08;
    auto& vp08 = raw_entry.data.vp08;

    vp08.width = entry.width;
    vp08.height = entry.height;
    vp08.bit_depth = entry.bit_depth;
    vp08.chroma_subsampling = entry.chroma_subsampling;
    vp08.video_full_range_flag = entry.video_full_range_flag;
    vp08.colour_primaries = entry.colour_primaries;
    vp08.transfer_characteristics = entry.transfer_characteristics;
    vp08.matrix_coefficients = entry.matrix_coefficients;
  }

  void convert_vp09(PyMp4SampleEntryVp09& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_VP09;
    auto& vp09 = raw_entry.data.vp09;

    vp09.width = entry.width;
    vp09.height = entry.height;
    vp09.profile = entry.profile;
    vp09.level = entry.level;
    vp09.bit_depth = entry.bit_depth;
    vp09.chroma_subsampling = entry.chroma_subsampling;
    vp09.video_full_range_flag = entry.video_full_range_flag;
    vp09.colour_primaries = entry.colour_primaries;
    vp09.transfer_characteristics = entry.transfer_characteristics;
    vp09.matrix_coefficients = entry.matrix_coefficients;
  }

  void convert_av01(PyMp4SampleEntryAv01& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_AV01;
    auto& av01 = raw_entry.data.av01;

    av01.width = entry.width;
    av01.height = entry.height;
    av01.seq_profile = entry.seq_profile;
    av01.seq_level_idx_0 = entry.seq_level_idx_0;
    av01.seq_tier_0 = entry.seq_tier_0;
    av01.high_bitdepth = entry.high_bitdepth;
    av01.twelve_bit = entry.twelve_bit;
    av01.monochrome = entry.monochrome;
    av01.chroma_subsampling_x = entry.chroma_subsampling_x;
    av01.chroma_subsampling_y = entry.chroma_subsampling_y;
    av01.chroma_sample_position = entry.chroma_sample_position;
    av01.initial_presentation_delay_present =
        entry.initial_presentation_delay_present;
    av01.initial_presentation_delay_minus_one =
        entry.initial_presentation_delay_minus_one;

    const auto* config_ptr =
        static_cast<const uint8_t*>(entry.config_obus.data());
    config_obus_buffer.assign(config_ptr,
                              config_ptr + entry.config_obus.size());
    av01.config_obus = config_obus_buffer.data();
    av01.config_obus_size = static_cast<uint32_t>(config_obus_buffer.size());
  }

  void convert_opus(PyMp4SampleEntryOpus& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_OPUS;
    auto& opus = raw_entry.data.opus;

    opus.channel_count = entry.channel_count;
    opus.sample_rate = entry.sample_rate;
    opus.sample_size = entry.sample_size;
    opus.pre_skip = entry.pre_skip;
    opus.input_sample_rate =
        entry.input_sample_rate.value_or(entry.sample_rate);
    opus.output_gain = entry.output_gain;
  }

  void convert_mp4a(PyMp4SampleEntryMp4a& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_MP4A;
    auto& mp4a = raw_entry.data.mp4a;

    mp4a.channel_count = entry.channel_count;
    mp4a.sample_rate = entry.sample_rate;
    mp4a.sample_size = entry.sample_size;
    mp4a.buffer_size_db = entry.buffer_size_db;
    mp4a.max_bitrate = entry.max_bitrate;
    mp4a.avg_bitrate = entry.avg_bitrate;

    const auto* dec_ptr =
        static_cast<const uint8_t*>(entry.dec_specific_info.data());
    dec_specific_info_buffer.assign(dec_ptr,
                                    dec_ptr + entry.dec_specific_info.size());
    mp4a.dec_specific_info = dec_specific_info_buffer.data();
    mp4a.dec_specific_info_size =
        static_cast<uint32_t>(dec_specific_info_buffer.size());
  }

  void convert_flac(PyMp4SampleEntryFlac& entry) {
    raw_entry.kind = MP4_SAMPLE_ENTRY_KIND_FLAC;
    auto& flac = raw_entry.data.flac;

    flac.channel_count = entry.channel_count;
    flac.sample_rate = entry.sample_rate;
    flac.sample_size = entry.sample_size;

    const auto* streaminfo_ptr =
        static_cast<const uint8_t*>(entry.streaminfo_data.data());
    streaminfo_buffer.assign(streaminfo_ptr,
                             streaminfo_ptr + entry.streaminfo_data.size());
    flac.streaminfo_data = streaminfo_buffer.data();
    flac.streaminfo_size = static_cast<uint32_t>(streaminfo_buffer.size());
  }
};

class PyMp4FileMuxer {
 public:
  // コピー禁止
  PyMp4FileMuxer(const PyMp4FileMuxer&) = delete;
  PyMp4FileMuxer& operator=(const PyMp4FileMuxer&) = delete;

  PyMp4FileMuxer(nb::object destination,
                 std::optional<PyMp4FileMuxerOptions> options)
      : muxer_(nullptr),
        should_close_stream_(false),
        finalized_(false),
        closed_(false) {
    // 出力先を判定
    if (nb::hasattr(destination, "__fspath__") ||
        nb::isinstance<nb::str>(destination)) {
      nb::object builtins = nb::module_::import_("builtins");
      output_stream_ = builtins.attr("open")(destination, "wb");
      should_close_stream_ = true;
    } else {
      output_stream_ = destination;
      should_close_stream_ = false;
    }

    // Muxer を作成
    muxer_ = mp4_file_muxer_new();
    if (!muxer_) {
      throw Mp4Exception("Failed to create mp4 muxer");
    }

    // オプション設定
    if (options && options->reserved_moov_box_size > 0) {
      Mp4Error error = mp4_file_muxer_set_reserved_moov_box_size(
          muxer_, options->reserved_moov_box_size);
      check_error(error);
    }

    // 初期化
    Mp4Error error = mp4_file_muxer_initialize(muxer_);
    check_error(error);

    // 初期出力をフラッシュ
    flush_output();
  }

  ~PyMp4FileMuxer() { close(); }

  PyMp4FileMuxer& enter() { return *this; }

  void exit(nb::object /*exc_type*/,
            nb::object /*exc_val*/,
            nb::object /*exc_tb*/) {
    close();
  }

  void close() {
    nb::ft_lock_guard lock(mutex_);
    if (closed_)
      return;

    if (muxer_) {
      if (!finalized_) {
        finalize_internal();
      }
      mp4_file_muxer_free(muxer_);
      muxer_ = nullptr;
    }

    if (should_close_stream_ && !output_stream_.is_none()) {
      output_stream_.attr("close")();
    }
    output_stream_ = nb::none();
    closed_ = true;
  }

  void append_sample(PyMp4MuxSample& sample) {
    nb::ft_lock_guard lock(mutex_);
    if (closed_)
      throw Mp4Exception("Muxer is closed");

    // 現在のストリーム位置を取得
    nb::object tell_result = output_stream_.attr("tell")();
    uint64_t data_offset = nb::cast<uint64_t>(tell_result);

    // サンプルデータを書き込み
    output_stream_.attr("write")(sample.data);

    // サンプルエントリーを変換
    SampleEntryConverter converter;
    converter.convert(sample.sample_entry);

    // C 構造体を構築
    Mp4MuxSample raw_sample;
    raw_sample.track_kind = string_to_track_kind(sample.track_kind);
    raw_sample.sample_entry = converter.valid ? &converter.raw_entry : nullptr;
    raw_sample.keyframe = sample.keyframe;
    raw_sample.timescale = sample.timescale;
    raw_sample.duration = sample.duration;
    raw_sample.data_offset = data_offset;
    raw_sample.data_size = static_cast<uint32_t>(sample.data.size());

    Mp4Error error = mp4_file_muxer_append_sample(muxer_, &raw_sample);
    check_error(error);

    flush_output();
  }

  void finalize() {
    nb::ft_lock_guard lock(mutex_);
    finalize_internal();
  }

 private:
  // ロックを取らない内部版 (close() から呼び出し用)
  void finalize_internal() {
    if (closed_)
      throw Mp4Exception("Muxer is closed");
    if (finalized_)
      return;

    Mp4Error error = mp4_file_muxer_finalize(muxer_);
    check_error(error);
    finalized_ = true;

    flush_output();
  }

  Mp4FileMuxer* muxer_;
  nb::object output_stream_;
  bool should_close_stream_;
  bool finalized_;
  bool closed_;
  mutable nb::ft_mutex mutex_;

  void check_error(Mp4Error error) {
    if (error == MP4_ERROR_OK)
      return;

    const char* msg = mp4_file_muxer_get_last_error(muxer_);
    std::string msg_str = msg ? msg : "";

    switch (error) {
      case MP4_ERROR_NULL_POINTER:
        throw std::invalid_argument("Null pointer error: " + msg_str);
      case MP4_ERROR_INVALID_STATE:
        throw Mp4Exception("Invalid state: " + msg_str);
      case MP4_ERROR_OUTPUT_REQUIRED:
        throw Mp4Exception("Output required: " + msg_str);
      case MP4_ERROR_INVALID_INPUT:
        throw std::invalid_argument("Invalid input: " + msg_str);
      default:
        throw Mp4Exception("MP4 error (" + std::to_string(error) +
                           "): " + msg_str);
    }
  }

  void flush_output() {
    while (true) {
      uint64_t output_offset;
      uint32_t output_size;
      const uint8_t* output_data;

      Mp4Error error = mp4_file_muxer_next_output(muxer_, &output_offset,
                                                  &output_size, &output_data);
      check_error(error);

      if (output_size == 0)
        break;

      output_stream_.attr("seek")(output_offset);
      nb::bytes data(reinterpret_cast<const char*>(output_data), output_size);
      output_stream_.attr("write")(data);
    }
  }
};

// ===== nanobind モジュール定義 =====

NB_MODULE(mp4_ext, m) {
  m.doc() = "Python bindings for mp4-rust (nanobind)";

  // ユーティリティ関数
  m.def("library_version", &library_version,
        nb::sig("def library_version() -> str"),
        "mp4-rust ライブラリのバージョンを取得する");

  m.def("estimate_maximum_moov_box_size", &estimate_maximum_moov_box_size,
        "audio_sample_count"_a, "video_sample_count"_a,
        nb::sig("def estimate_maximum_moov_box_size(audio_sample_count: int, "
                "video_sample_count: "
                "int) -> int"),
        "moov ボックスの最大サイズを見積もる");

  // サンプルエントリークラス
  nb::class_<PyMp4SampleEntryAvc1>(m, "Mp4SampleEntryAvc1")
      .def(nb::init<>())
      .def(
          "__init__",
          [](PyMp4SampleEntryAvc1* self, uint16_t width, uint16_t height,
             uint8_t avc_profile_indication, uint8_t avc_level_indication,
             uint8_t profile_compatibility, nb::object sps_data_obj,
             nb::object pps_data_obj, uint8_t length_size_minus_one,
             std::optional<uint8_t> chroma_format,
             std::optional<uint8_t> bit_depth_luma_minus8,
             std::optional<uint8_t> bit_depth_chroma_minus8) {
            new (self) PyMp4SampleEntryAvc1();
            self->width = width;
            self->height = height;
            self->avc_profile_indication = avc_profile_indication;
            self->avc_level_indication = avc_level_indication;
            self->profile_compatibility = profile_compatibility;
            self->length_size_minus_one = length_size_minus_one;
            self->chroma_format = chroma_format;
            self->bit_depth_luma_minus8 = bit_depth_luma_minus8;
            self->bit_depth_chroma_minus8 = bit_depth_chroma_minus8;
            if (!sps_data_obj.is_none()) {
              for (auto item : sps_data_obj) {
                self->sps_data.push_back(nb::cast<nb::bytes>(item));
              }
            }
            if (!pps_data_obj.is_none()) {
              for (auto item : pps_data_obj) {
                self->pps_data.push_back(nb::cast<nb::bytes>(item));
              }
            }
          },
          "width"_a, "height"_a, "avc_profile_indication"_a,
          "avc_level_indication"_a, "profile_compatibility"_a,
          "sps_data"_a = nb::none(), "pps_data"_a = nb::none(),
          "length_size_minus_one"_a = 3, "chroma_format"_a = std::nullopt,
          "bit_depth_luma_minus8"_a = std::nullopt,
          "bit_depth_chroma_minus8"_a = std::nullopt)
      .def_rw("width", &PyMp4SampleEntryAvc1::width)
      .def_rw("height", &PyMp4SampleEntryAvc1::height)
      .def_rw("avc_profile_indication",
              &PyMp4SampleEntryAvc1::avc_profile_indication)
      .def_rw("profile_compatibility",
              &PyMp4SampleEntryAvc1::profile_compatibility)
      .def_rw("avc_level_indication",
              &PyMp4SampleEntryAvc1::avc_level_indication)
      .def_rw("length_size_minus_one",
              &PyMp4SampleEntryAvc1::length_size_minus_one)
      .def_rw("sps_data", &PyMp4SampleEntryAvc1::sps_data)
      .def_rw("pps_data", &PyMp4SampleEntryAvc1::pps_data)
      .def_rw("chroma_format", &PyMp4SampleEntryAvc1::chroma_format)
      .def_rw("bit_depth_luma_minus8",
              &PyMp4SampleEntryAvc1::bit_depth_luma_minus8)
      .def_rw("bit_depth_chroma_minus8",
              &PyMp4SampleEntryAvc1::bit_depth_chroma_minus8);

  nb::class_<PyMp4SampleEntryHev1>(m, "Mp4SampleEntryHev1")
      .def(nb::init<>())
      .def(
          "__init__",
          [](PyMp4SampleEntryHev1* self, uint16_t width, uint16_t height,
             uint8_t general_profile_idc, uint8_t general_level_idc,
             nb::object nalu_types_obj, nb::object nalu_data_obj,
             uint8_t general_profile_space, uint8_t general_tier_flag,
             uint32_t general_profile_compatibility_flags,
             uint64_t general_constraint_indicator_flags,
             uint8_t chroma_format_idc, uint8_t bit_depth_luma_minus8,
             uint8_t bit_depth_chroma_minus8,
             uint16_t min_spatial_segmentation_idc, uint8_t parallelism_type,
             uint16_t avg_frame_rate, uint8_t constant_frame_rate,
             uint8_t num_temporal_layers, uint8_t temporal_id_nested,
             uint8_t length_size_minus_one) {
            new (self) PyMp4SampleEntryHev1();
            self->width = width;
            self->height = height;
            self->general_profile_space = general_profile_space;
            self->general_tier_flag = general_tier_flag;
            self->general_profile_idc = general_profile_idc;
            self->general_profile_compatibility_flags =
                general_profile_compatibility_flags;
            self->general_constraint_indicator_flags =
                general_constraint_indicator_flags;
            self->general_level_idc = general_level_idc;
            self->chroma_format_idc = chroma_format_idc;
            self->bit_depth_luma_minus8 = bit_depth_luma_minus8;
            self->bit_depth_chroma_minus8 = bit_depth_chroma_minus8;
            self->min_spatial_segmentation_idc = min_spatial_segmentation_idc;
            self->parallelism_type = parallelism_type;
            self->avg_frame_rate = avg_frame_rate;
            self->constant_frame_rate = constant_frame_rate;
            self->num_temporal_layers = num_temporal_layers;
            self->temporal_id_nested = temporal_id_nested;
            self->length_size_minus_one = length_size_minus_one;
            if (!nalu_types_obj.is_none()) {
              for (auto item : nalu_types_obj) {
                self->nalu_types.push_back(nb::cast<uint8_t>(item));
              }
            }
            if (!nalu_data_obj.is_none()) {
              for (auto item : nalu_data_obj) {
                self->nalu_data.push_back(nb::cast<nb::bytes>(item));
              }
            }
          },
          "width"_a, "height"_a, "general_profile_idc"_a, "general_level_idc"_a,
          "nalu_types"_a = nb::none(), "nalu_data"_a = nb::none(),
          "general_profile_space"_a = 0, "general_tier_flag"_a = 0,
          "general_profile_compatibility_flags"_a = 0,
          "general_constraint_indicator_flags"_a = 0, "chroma_format_idc"_a = 1,
          "bit_depth_luma_minus8"_a = 0, "bit_depth_chroma_minus8"_a = 0,
          "min_spatial_segmentation_idc"_a = 0, "parallelism_type"_a = 0,
          "avg_frame_rate"_a = 0, "constant_frame_rate"_a = 0,
          "num_temporal_layers"_a = 0, "temporal_id_nested"_a = 0,
          "length_size_minus_one"_a = 3)
      .def_rw("width", &PyMp4SampleEntryHev1::width)
      .def_rw("height", &PyMp4SampleEntryHev1::height)
      .def_rw("general_profile_space",
              &PyMp4SampleEntryHev1::general_profile_space)
      .def_rw("general_tier_flag", &PyMp4SampleEntryHev1::general_tier_flag)
      .def_rw("general_profile_idc", &PyMp4SampleEntryHev1::general_profile_idc)
      .def_rw("general_profile_compatibility_flags",
              &PyMp4SampleEntryHev1::general_profile_compatibility_flags)
      .def_rw("general_constraint_indicator_flags",
              &PyMp4SampleEntryHev1::general_constraint_indicator_flags)
      .def_rw("general_level_idc", &PyMp4SampleEntryHev1::general_level_idc)
      .def_rw("chroma_format_idc", &PyMp4SampleEntryHev1::chroma_format_idc)
      .def_rw("bit_depth_luma_minus8",
              &PyMp4SampleEntryHev1::bit_depth_luma_minus8)
      .def_rw("bit_depth_chroma_minus8",
              &PyMp4SampleEntryHev1::bit_depth_chroma_minus8)
      .def_rw("min_spatial_segmentation_idc",
              &PyMp4SampleEntryHev1::min_spatial_segmentation_idc)
      .def_rw("parallelism_type", &PyMp4SampleEntryHev1::parallelism_type)
      .def_rw("avg_frame_rate", &PyMp4SampleEntryHev1::avg_frame_rate)
      .def_rw("constant_frame_rate", &PyMp4SampleEntryHev1::constant_frame_rate)
      .def_rw("num_temporal_layers", &PyMp4SampleEntryHev1::num_temporal_layers)
      .def_rw("temporal_id_nested", &PyMp4SampleEntryHev1::temporal_id_nested)
      .def_rw("length_size_minus_one",
              &PyMp4SampleEntryHev1::length_size_minus_one)
      .def_rw("nalu_types", &PyMp4SampleEntryHev1::nalu_types)
      .def_rw("nalu_data", &PyMp4SampleEntryHev1::nalu_data);

  nb::class_<PyMp4SampleEntryVp08>(m, "Mp4SampleEntryVp08")
      .def(nb::init<>())
      .def(nb::init<uint16_t, uint16_t, uint8_t, uint8_t, bool, uint8_t,
                    uint8_t, uint8_t>(),
           "width"_a, "height"_a, "bit_depth"_a = 8, "chroma_subsampling"_a = 0,
           "video_full_range_flag"_a = false, "colour_primaries"_a = 1,
           "transfer_characteristics"_a = 1, "matrix_coefficients"_a = 1)
      .def_rw("width", &PyMp4SampleEntryVp08::width)
      .def_rw("height", &PyMp4SampleEntryVp08::height)
      .def_rw("bit_depth", &PyMp4SampleEntryVp08::bit_depth)
      .def_rw("chroma_subsampling", &PyMp4SampleEntryVp08::chroma_subsampling)
      .def_rw("video_full_range_flag",
              &PyMp4SampleEntryVp08::video_full_range_flag)
      .def_rw("colour_primaries", &PyMp4SampleEntryVp08::colour_primaries)
      .def_rw("transfer_characteristics",
              &PyMp4SampleEntryVp08::transfer_characteristics)
      .def_rw("matrix_coefficients",
              &PyMp4SampleEntryVp08::matrix_coefficients);

  nb::class_<PyMp4SampleEntryVp09>(m, "Mp4SampleEntryVp09")
      .def(nb::init<>())
      .def(nb::init<uint16_t, uint16_t, uint8_t, uint8_t, uint8_t, uint8_t,
                    bool, uint8_t, uint8_t, uint8_t>(),
           "width"_a, "height"_a, "profile"_a, "level"_a, "bit_depth"_a = 8,
           "chroma_subsampling"_a = 0, "video_full_range_flag"_a = false,
           "colour_primaries"_a = 1, "transfer_characteristics"_a = 1,
           "matrix_coefficients"_a = 1)
      .def_rw("width", &PyMp4SampleEntryVp09::width)
      .def_rw("height", &PyMp4SampleEntryVp09::height)
      .def_rw("profile", &PyMp4SampleEntryVp09::profile)
      .def_rw("level", &PyMp4SampleEntryVp09::level)
      .def_rw("bit_depth", &PyMp4SampleEntryVp09::bit_depth)
      .def_rw("chroma_subsampling", &PyMp4SampleEntryVp09::chroma_subsampling)
      .def_rw("video_full_range_flag",
              &PyMp4SampleEntryVp09::video_full_range_flag)
      .def_rw("colour_primaries", &PyMp4SampleEntryVp09::colour_primaries)
      .def_rw("transfer_characteristics",
              &PyMp4SampleEntryVp09::transfer_characteristics)
      .def_rw("matrix_coefficients",
              &PyMp4SampleEntryVp09::matrix_coefficients);

  nb::class_<PyMp4SampleEntryAv01>(m, "Mp4SampleEntryAv01")
      .def(nb::init<>())
      .def(nb::init<uint16_t, uint16_t, uint8_t, uint8_t, nb::bytes, uint8_t,
                    uint8_t, uint8_t, uint8_t, uint8_t, uint8_t, uint8_t, bool,
                    uint8_t>(),
           "width"_a, "height"_a, "seq_profile"_a, "seq_level_idx_0"_a,
           "config_obus"_a, "seq_tier_0"_a = 0, "high_bitdepth"_a = 0,
           "twelve_bit"_a = 0, "monochrome"_a = 0, "chroma_subsampling_x"_a = 1,
           "chroma_subsampling_y"_a = 1, "chroma_sample_position"_a = 0,
           "initial_presentation_delay_present"_a = false,
           "initial_presentation_delay_minus_one"_a = 0)
      .def_rw("width", &PyMp4SampleEntryAv01::width)
      .def_rw("height", &PyMp4SampleEntryAv01::height)
      .def_rw("seq_profile", &PyMp4SampleEntryAv01::seq_profile)
      .def_rw("seq_level_idx_0", &PyMp4SampleEntryAv01::seq_level_idx_0)
      .def_rw("seq_tier_0", &PyMp4SampleEntryAv01::seq_tier_0)
      .def_rw("high_bitdepth", &PyMp4SampleEntryAv01::high_bitdepth)
      .def_rw("twelve_bit", &PyMp4SampleEntryAv01::twelve_bit)
      .def_rw("monochrome", &PyMp4SampleEntryAv01::monochrome)
      .def_rw("chroma_subsampling_x",
              &PyMp4SampleEntryAv01::chroma_subsampling_x)
      .def_rw("chroma_subsampling_y",
              &PyMp4SampleEntryAv01::chroma_subsampling_y)
      .def_rw("chroma_sample_position",
              &PyMp4SampleEntryAv01::chroma_sample_position)
      .def_rw("initial_presentation_delay_present",
              &PyMp4SampleEntryAv01::initial_presentation_delay_present)
      .def_rw("initial_presentation_delay_minus_one",
              &PyMp4SampleEntryAv01::initial_presentation_delay_minus_one)
      .def_rw("config_obus", &PyMp4SampleEntryAv01::config_obus);

  nb::class_<PyMp4SampleEntryOpus>(m, "Mp4SampleEntryOpus")
      .def(nb::init<>())
      .def(nb::init<uint8_t, uint16_t, uint16_t, uint16_t,
                    std::optional<uint32_t>, int16_t>(),
           "channel_count"_a, "sample_rate"_a, "sample_size"_a = 16,
           "pre_skip"_a = 0, "input_sample_rate"_a = std::nullopt,
           "output_gain"_a = 0)
      .def_rw("channel_count", &PyMp4SampleEntryOpus::channel_count)
      .def_rw("sample_rate", &PyMp4SampleEntryOpus::sample_rate)
      .def_rw("sample_size", &PyMp4SampleEntryOpus::sample_size)
      .def_rw("pre_skip", &PyMp4SampleEntryOpus::pre_skip)
      .def_rw("input_sample_rate", &PyMp4SampleEntryOpus::input_sample_rate)
      .def_rw("output_gain", &PyMp4SampleEntryOpus::output_gain);

  nb::class_<PyMp4SampleEntryMp4a>(m, "Mp4SampleEntryMp4a")
      .def(nb::init<>())
      .def(nb::init<uint8_t, uint16_t, nb::bytes, uint16_t, uint32_t, uint32_t,
                    uint32_t>(),
           "channel_count"_a, "sample_rate"_a, "dec_specific_info"_a,
           "sample_size"_a = 16, "buffer_size_db"_a = 0, "max_bitrate"_a = 0,
           "avg_bitrate"_a = 0)
      .def_rw("channel_count", &PyMp4SampleEntryMp4a::channel_count)
      .def_rw("sample_rate", &PyMp4SampleEntryMp4a::sample_rate)
      .def_rw("sample_size", &PyMp4SampleEntryMp4a::sample_size)
      .def_rw("buffer_size_db", &PyMp4SampleEntryMp4a::buffer_size_db)
      .def_rw("max_bitrate", &PyMp4SampleEntryMp4a::max_bitrate)
      .def_rw("avg_bitrate", &PyMp4SampleEntryMp4a::avg_bitrate)
      .def_rw("dec_specific_info", &PyMp4SampleEntryMp4a::dec_specific_info);

  nb::class_<PyMp4SampleEntryFlac>(m, "Mp4SampleEntryFlac")
      .def(nb::init<>())
      .def(nb::init<uint8_t, uint16_t, nb::bytes, uint16_t>(),
           "channel_count"_a, "sample_rate"_a, "streaminfo_data"_a,
           "sample_size"_a = 16)
      .def_rw("channel_count", &PyMp4SampleEntryFlac::channel_count)
      .def_rw("sample_rate", &PyMp4SampleEntryFlac::sample_rate)
      .def_rw("sample_size", &PyMp4SampleEntryFlac::sample_size)
      .def_rw("streaminfo_data", &PyMp4SampleEntryFlac::streaminfo_data);

  // トラック情報
  nb::class_<PyMp4TrackInfo>(m, "Mp4TrackInfo")
      .def(nb::init<>())
      .def(nb::init<uint32_t, std::string, uint64_t, uint32_t>(), "track_id"_a,
           "kind"_a, "duration"_a, "timescale"_a)
      .def_rw("track_id", &PyMp4TrackInfo::track_id)
      .def_rw("kind", &PyMp4TrackInfo::kind)
      .def_rw("duration", &PyMp4TrackInfo::duration)
      .def_rw("timescale", &PyMp4TrackInfo::timescale)
      .def_prop_ro("duration_seconds", &PyMp4TrackInfo::duration_seconds)
      .def("__repr__", &PyMp4TrackInfo::repr);

  // Demuxer サンプル
  nb::class_<PyMp4DemuxSample>(m, "Mp4DemuxSample")
      .def(nb::init<>())
      .def(nb::init<PyMp4TrackInfo, nb::object, bool, uint64_t, uint32_t,
                    uint64_t, uint64_t, nb::object>(),
           "track"_a, "sample_entry"_a, "keyframe"_a, "timestamp"_a,
           "duration"_a, "data_offset"_a, "data_size"_a, "input_stream"_a)
      .def_ro("track", &PyMp4DemuxSample::track)
      .def_ro("sample_entry", &PyMp4DemuxSample::sample_entry)
      .def_ro("keyframe", &PyMp4DemuxSample::keyframe)
      .def_ro("timestamp", &PyMp4DemuxSample::timestamp)
      .def_ro("duration", &PyMp4DemuxSample::duration)
      .def_prop_ro("data", &PyMp4DemuxSample::get_data, nb::lock_self())
      .def_prop_ro("timestamp_seconds", &PyMp4DemuxSample::timestamp_seconds)
      .def_prop_ro("duration_seconds", &PyMp4DemuxSample::duration_seconds)
      .def("__repr__", &PyMp4DemuxSample::repr);

  // Demuxer
  nb::class_<PyMp4FileDemuxer>(m, "Mp4FileDemuxer")
      .def(nb::init<nb::object>(), "source"_a)
      .def("close", &PyMp4FileDemuxer::close)
      .def_prop_ro("tracks", &PyMp4FileDemuxer::get_tracks)
      .def(
          "__enter__",
          [](PyMp4FileDemuxer& self) -> PyMp4FileDemuxer& { return self; },
          nb::rv_policy::reference)
      .def("__exit__", &PyMp4FileDemuxer::exit, "exc_type"_a.none(),
           "exc_val"_a.none(), "exc_tb"_a.none())
      .def("__iter__", &PyMp4FileDemuxer::iter, nb::rv_policy::reference)
      .def("__next__", &PyMp4FileDemuxer::next);

  // Muxer オプション
  nb::class_<PyMp4FileMuxerOptions>(m, "Mp4FileMuxerOptions")
      .def(nb::init<>())
      .def(nb::init<uint64_t>(), "reserved_moov_box_size"_a = 0)
      .def_rw("reserved_moov_box_size",
              &PyMp4FileMuxerOptions::reserved_moov_box_size)
      .def_static("estimate_maximum_moov_box_size",
                  &PyMp4FileMuxerOptions::estimate_maximum_moov_box_size,
                  "audio_sample_count"_a, "video_sample_count"_a);

  // Muxer サンプル
  nb::class_<PyMp4MuxSample>(m, "Mp4MuxSample")
      .def(nb::init<>())
      .def(nb::init<std::string, nb::object, bool, uint32_t, uint32_t,
                    nb::bytes>(),
           "track_kind"_a, "sample_entry"_a, "keyframe"_a, "timescale"_a,
           "duration"_a, "data"_a)
      .def_rw("track_kind", &PyMp4MuxSample::track_kind)
      .def_rw("sample_entry", &PyMp4MuxSample::sample_entry)
      .def_rw("keyframe", &PyMp4MuxSample::keyframe)
      .def_rw("timescale", &PyMp4MuxSample::timescale)
      .def_rw("duration", &PyMp4MuxSample::duration)
      .def_rw("data", &PyMp4MuxSample::data)
      .def("__repr__", &PyMp4MuxSample::repr);

  // Muxer
  nb::class_<PyMp4FileMuxer>(m, "Mp4FileMuxer")
      .def(nb::init<nb::object, std::optional<PyMp4FileMuxerOptions>>(),
           "destination"_a, "options"_a = nb::none())
      .def("close", &PyMp4FileMuxer::close)
      .def("append_sample", &PyMp4FileMuxer::append_sample, "sample"_a)
      .def("finalize", &PyMp4FileMuxer::finalize)
      .def(
          "__enter__",
          [](PyMp4FileMuxer& self) -> PyMp4FileMuxer& { return self; },
          nb::rv_policy::reference)
      .def("__exit__", &PyMp4FileMuxer::exit, "exc_type"_a.none(),
           "exc_val"_a.none(), "exc_tb"_a.none());
}
