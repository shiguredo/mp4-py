# mp4-rust の C API に対応する Python 型定義
#
# nanobind で直接バインドされた構造体を Python 向けにラップする
from dataclasses import dataclass
from typing import Literal, List, Optional

from mp4._mp4 import (
    SampleEntryAvc1 as _NativeSampleEntryAvc1,
    SampleEntryHev1 as _NativeSampleEntryHev1,
    SampleEntryVp08 as _NativeSampleEntryVp08,
    SampleEntryVp09 as _NativeSampleEntryVp09,
    SampleEntryAv01 as _NativeSampleEntryAv01,
    SampleEntryOpus as _NativeSampleEntryOpus,
    SampleEntryMp4a as _NativeSampleEntryMp4a,
)

Mp4TrackKind = Literal["audio", "video"]
"""
MP4 ファイル内のトラックの種類を表す型
"""


@dataclass
class Mp4SampleEntryAvc1:
    """
    AVC1（H.264）コーデック用のサンプルエントリー
    """

    width: int
    height: int
    avc_profile_indication: int
    profile_compatibility: int
    avc_level_indication: int
    sps_data: List[bytes]
    pps_data: List[bytes]
    length_size_minus_one: int = 3
    chroma_format: Optional[int] = None
    bit_depth_luma_minus8: Optional[int] = None
    bit_depth_chroma_minus8: Optional[int] = None

    @staticmethod
    def _from_native(native: _NativeSampleEntryAvc1) -> "Mp4SampleEntryAvc1":
        return Mp4SampleEntryAvc1(
            width=native.width,
            height=native.height,
            avc_profile_indication=native.avc_profile_indication,
            profile_compatibility=native.profile_compatibility,
            avc_level_indication=native.avc_level_indication,
            length_size_minus_one=native.length_size_minus_one,
            sps_data=[bytes(s) for s in native.sps_data],
            pps_data=[bytes(p) for p in native.pps_data],
            chroma_format=native.chroma_format,
            bit_depth_luma_minus8=native.bit_depth_luma_minus8,
            bit_depth_chroma_minus8=native.bit_depth_chroma_minus8,
        )

    def _to_native(self) -> _NativeSampleEntryAvc1:
        native = _NativeSampleEntryAvc1()
        native.width = self.width
        native.height = self.height
        native.avc_profile_indication = self.avc_profile_indication
        native.profile_compatibility = self.profile_compatibility
        native.avc_level_indication = self.avc_level_indication
        native.length_size_minus_one = self.length_size_minus_one
        native.sps_data = self.sps_data
        native.pps_data = self.pps_data
        # Optional フィールドは None でなければ設定
        if self.chroma_format is not None:
            native.chroma_format = self.chroma_format
        if self.bit_depth_luma_minus8 is not None:
            native.bit_depth_luma_minus8 = self.bit_depth_luma_minus8
        if self.bit_depth_chroma_minus8 is not None:
            native.bit_depth_chroma_minus8 = self.bit_depth_chroma_minus8
        return native


@dataclass
class Mp4SampleEntryHev1:
    """
    HEV1（H.265/HEVC）コーデック用のサンプルエントリー
    """

    width: int
    height: int
    general_profile_idc: int
    general_level_idc: int
    nalu_types: List[int]
    nalu_data: List[bytes]
    length_size_minus_one: int = 3
    general_tier_flag: int = 0
    general_profile_space: int = 0
    general_profile_compatibility_flags: int = 0
    general_constraint_indicator_flags: int = 0
    chroma_format_idc: int = 1
    bit_depth_luma_minus8: int = 0
    bit_depth_chroma_minus8: int = 0
    min_spatial_segmentation_idc: int = 0
    parallelism_type: int = 0
    avg_frame_rate: int = 0
    constant_frame_rate: int = 0
    num_temporal_layers: int = 0
    temporal_id_nested: int = 0

    @staticmethod
    def _from_native(native: _NativeSampleEntryHev1) -> "Mp4SampleEntryHev1":
        return Mp4SampleEntryHev1(
            width=native.width,
            height=native.height,
            general_profile_space=native.general_profile_space,
            general_tier_flag=native.general_tier_flag,
            general_profile_idc=native.general_profile_idc,
            general_profile_compatibility_flags=native.general_profile_compatibility_flags,
            general_constraint_indicator_flags=native.general_constraint_indicator_flags,
            general_level_idc=native.general_level_idc,
            chroma_format_idc=native.chroma_format_idc,
            bit_depth_luma_minus8=native.bit_depth_luma_minus8,
            bit_depth_chroma_minus8=native.bit_depth_chroma_minus8,
            min_spatial_segmentation_idc=native.min_spatial_segmentation_idc,
            parallelism_type=native.parallelism_type,
            avg_frame_rate=native.avg_frame_rate,
            constant_frame_rate=native.constant_frame_rate,
            num_temporal_layers=native.num_temporal_layers,
            temporal_id_nested=native.temporal_id_nested,
            length_size_minus_one=native.length_size_minus_one,
            nalu_types=list(native.nalu_types),
            nalu_data=[bytes(d) for d in native.nalu_data],
        )

    def _to_native(self) -> _NativeSampleEntryHev1:
        # nalu_types と nalu_data の長さが等しいことをチェックする
        if len(self.nalu_types) != len(self.nalu_data):
            raise ValueError(
                f"nalu_types and nalu_data must have the same length. "
                f"nalu_types: {len(self.nalu_types)}, nalu_data: {len(self.nalu_data)}"
            )

        native = _NativeSampleEntryHev1()
        native.width = self.width
        native.height = self.height
        native.general_profile_space = self.general_profile_space
        native.general_tier_flag = self.general_tier_flag
        native.general_profile_idc = self.general_profile_idc
        native.general_profile_compatibility_flags = self.general_profile_compatibility_flags
        native.general_constraint_indicator_flags = self.general_constraint_indicator_flags
        native.general_level_idc = self.general_level_idc
        native.chroma_format_idc = self.chroma_format_idc
        native.bit_depth_luma_minus8 = self.bit_depth_luma_minus8
        native.bit_depth_chroma_minus8 = self.bit_depth_chroma_minus8
        native.min_spatial_segmentation_idc = self.min_spatial_segmentation_idc
        native.parallelism_type = self.parallelism_type
        native.avg_frame_rate = self.avg_frame_rate
        native.constant_frame_rate = self.constant_frame_rate
        native.num_temporal_layers = self.num_temporal_layers
        native.temporal_id_nested = self.temporal_id_nested
        native.length_size_minus_one = self.length_size_minus_one
        native.nalu_types = self.nalu_types
        native.nalu_data = self.nalu_data
        return native


@dataclass
class Mp4SampleEntryVp08:
    """
    VP08（VP8）コーデック用のサンプルエントリー
    """

    width: int
    height: int
    bit_depth: int = 8
    chroma_subsampling: int = 0
    video_full_range_flag: bool = False
    colour_primaries: int = 1
    transfer_characteristics: int = 1
    matrix_coefficients: int = 1

    @staticmethod
    def _from_native(native: _NativeSampleEntryVp08) -> "Mp4SampleEntryVp08":
        return Mp4SampleEntryVp08(
            width=native.width,
            height=native.height,
            bit_depth=native.bit_depth,
            chroma_subsampling=native.chroma_subsampling,
            video_full_range_flag=native.video_full_range_flag,
            colour_primaries=native.colour_primaries,
            transfer_characteristics=native.transfer_characteristics,
            matrix_coefficients=native.matrix_coefficients,
        )

    def _to_native(self) -> _NativeSampleEntryVp08:
        native = _NativeSampleEntryVp08()
        native.width = self.width
        native.height = self.height
        native.bit_depth = self.bit_depth
        native.chroma_subsampling = self.chroma_subsampling
        native.video_full_range_flag = self.video_full_range_flag
        native.colour_primaries = self.colour_primaries
        native.transfer_characteristics = self.transfer_characteristics
        native.matrix_coefficients = self.matrix_coefficients
        return native


@dataclass
class Mp4SampleEntryVp09:
    """
    VP09（VP9）コーデック用のサンプルエントリー
    """

    width: int
    height: int
    profile: int
    level: int
    bit_depth: int = 8
    chroma_subsampling: int = 0
    video_full_range_flag: bool = False
    colour_primaries: int = 1
    transfer_characteristics: int = 1
    matrix_coefficients: int = 1

    @staticmethod
    def _from_native(native: _NativeSampleEntryVp09) -> "Mp4SampleEntryVp09":
        return Mp4SampleEntryVp09(
            width=native.width,
            height=native.height,
            profile=native.profile,
            level=native.level,
            bit_depth=native.bit_depth,
            chroma_subsampling=native.chroma_subsampling,
            video_full_range_flag=native.video_full_range_flag,
            colour_primaries=native.colour_primaries,
            transfer_characteristics=native.transfer_characteristics,
            matrix_coefficients=native.matrix_coefficients,
        )

    def _to_native(self) -> _NativeSampleEntryVp09:
        native = _NativeSampleEntryVp09()
        native.width = self.width
        native.height = self.height
        native.profile = self.profile
        native.level = self.level
        native.bit_depth = self.bit_depth
        native.chroma_subsampling = self.chroma_subsampling
        native.video_full_range_flag = self.video_full_range_flag
        native.colour_primaries = self.colour_primaries
        native.transfer_characteristics = self.transfer_characteristics
        native.matrix_coefficients = self.matrix_coefficients
        return native


@dataclass
class Mp4SampleEntryAv01:
    """
    AV01（AV1）コーデック用のサンプルエントリー
    """

    width: int
    height: int
    config_obus: bytes
    seq_profile: int
    seq_level_idx_0: int
    seq_tier_0: int = 0
    high_bitdepth: int = 0
    twelve_bit: int = 0
    monochrome: int = 0
    chroma_subsampling_x: int = 1
    chroma_subsampling_y: int = 1
    chroma_sample_position: int = 0
    initial_presentation_delay_present: bool = False
    initial_presentation_delay_minus_one: int = 0

    @staticmethod
    def _from_native(native: _NativeSampleEntryAv01) -> "Mp4SampleEntryAv01":
        return Mp4SampleEntryAv01(
            width=native.width,
            height=native.height,
            seq_profile=native.seq_profile,
            seq_level_idx_0=native.seq_level_idx_0,
            seq_tier_0=native.seq_tier_0,
            high_bitdepth=native.high_bitdepth,
            twelve_bit=native.twelve_bit,
            monochrome=native.monochrome,
            chroma_subsampling_x=native.chroma_subsampling_x,
            chroma_subsampling_y=native.chroma_subsampling_y,
            chroma_sample_position=native.chroma_sample_position,
            initial_presentation_delay_present=native.initial_presentation_delay_present,
            initial_presentation_delay_minus_one=native.initial_presentation_delay_minus_one,
            config_obus=bytes(native.config_obus),
        )

    def _to_native(self) -> _NativeSampleEntryAv01:
        native = _NativeSampleEntryAv01()
        native.width = self.width
        native.height = self.height
        native.seq_profile = self.seq_profile
        native.seq_level_idx_0 = self.seq_level_idx_0
        native.seq_tier_0 = self.seq_tier_0
        native.high_bitdepth = self.high_bitdepth
        native.twelve_bit = self.twelve_bit
        native.monochrome = self.monochrome
        native.chroma_subsampling_x = self.chroma_subsampling_x
        native.chroma_subsampling_y = self.chroma_subsampling_y
        native.chroma_sample_position = self.chroma_sample_position
        native.initial_presentation_delay_present = self.initial_presentation_delay_present
        native.initial_presentation_delay_minus_one = self.initial_presentation_delay_minus_one
        native.config_obus = self.config_obus
        return native


@dataclass
class Mp4SampleEntryOpus:
    """
    Opus 音声コーデック用のサンプルエントリー
    """

    channel_count: int
    sample_rate: int
    sample_size: int = 16
    pre_skip: int = 0
    input_sample_rate: Optional[int] = None
    output_gain: int = 0

    @staticmethod
    def _from_native(native: _NativeSampleEntryOpus) -> "Mp4SampleEntryOpus":
        return Mp4SampleEntryOpus(
            channel_count=native.channel_count,
            sample_rate=native.sample_rate,
            sample_size=native.sample_size,
            pre_skip=native.pre_skip,
            input_sample_rate=native.input_sample_rate,
            output_gain=native.output_gain,
        )

    def _to_native(self) -> _NativeSampleEntryOpus:
        native = _NativeSampleEntryOpus()
        native.channel_count = self.channel_count
        native.sample_rate = self.sample_rate
        native.sample_size = self.sample_size
        native.pre_skip = self.pre_skip
        native.input_sample_rate = (
            self.sample_rate if self.input_sample_rate is None else self.input_sample_rate
        )
        native.output_gain = self.output_gain
        return native


@dataclass
class Mp4SampleEntryMp4a:
    """
    MP4A（AAC）音声コーデック用のサンプルエントリー
    """

    channel_count: int
    sample_rate: int
    dec_specific_info: bytes
    sample_size: int = 16
    buffer_size_db: int = 0
    max_bitrate: int = 0
    avg_bitrate: int = 0

    @staticmethod
    def _from_native(native: _NativeSampleEntryMp4a) -> "Mp4SampleEntryMp4a":
        return Mp4SampleEntryMp4a(
            channel_count=native.channel_count,
            sample_rate=native.sample_rate,
            sample_size=native.sample_size,
            buffer_size_db=native.buffer_size_db,
            max_bitrate=native.max_bitrate,
            avg_bitrate=native.avg_bitrate,
            dec_specific_info=bytes(native.dec_specific_info),
        )

    def _to_native(self) -> _NativeSampleEntryMp4a:
        native = _NativeSampleEntryMp4a()
        native.channel_count = self.channel_count
        native.sample_rate = self.sample_rate
        native.sample_size = self.sample_size
        native.buffer_size_db = self.buffer_size_db
        native.max_bitrate = self.max_bitrate
        native.avg_bitrate = self.avg_bitrate
        native.dec_specific_info = self.dec_specific_info
        return native


Mp4SampleEntry = (
    Mp4SampleEntryAvc1
    | Mp4SampleEntryHev1
    | Mp4SampleEntryVp08
    | Mp4SampleEntryVp09
    | Mp4SampleEntryAv01
    | Mp4SampleEntryOpus
    | Mp4SampleEntryMp4a
)
"""
MP4 サンプルエントリー
"""


def _from_native_sample_entry(native) -> Mp4SampleEntry:
    """ネイティブのサンプルエントリーを Python 型に変換"""
    if isinstance(native, _NativeSampleEntryAvc1):
        return Mp4SampleEntryAvc1._from_native(native)
    elif isinstance(native, _NativeSampleEntryHev1):
        return Mp4SampleEntryHev1._from_native(native)
    elif isinstance(native, _NativeSampleEntryVp08):
        return Mp4SampleEntryVp08._from_native(native)
    elif isinstance(native, _NativeSampleEntryVp09):
        return Mp4SampleEntryVp09._from_native(native)
    elif isinstance(native, _NativeSampleEntryAv01):
        return Mp4SampleEntryAv01._from_native(native)
    elif isinstance(native, _NativeSampleEntryOpus):
        return Mp4SampleEntryOpus._from_native(native)
    elif isinstance(native, _NativeSampleEntryMp4a):
        return Mp4SampleEntryMp4a._from_native(native)
    else:
        raise ValueError(f"Unknown sample entry type: {type(native)}")


def _to_native_sample_entry(entry: Mp4SampleEntry):
    """Python 型のサンプルエントリーをネイティブに変換"""
    return entry._to_native()
