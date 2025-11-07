# https://github.com/shiguredo/mp4-rust/blob/develop/crates/c-api/include/mp4.h で定義されている構造体などを Python 用に使いやすくラップするためのモジュール
#
# なお、各処理固有の構造体などはそれぞれの専用モジュール（例えば _mux.py）で定義されている
import ctypes
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal, List, Optional, Generator

from mp4._c_api import (
    _RawMp4TrackKind,
    _RawMp4SampleEntry,
    _RawMp4SampleEntryAvc1,
    _RawMp4SampleEntryHev1,
    _RawMp4SampleEntryVp08,
    _RawMp4SampleEntryVp09,
    _RawMp4SampleEntryAv01,
    _RawMp4SampleEntryOpus,
    _RawMp4SampleEntryMp4a,
    _RawMp4SampleEntryKind,
)

Mp4TrackKind = Literal["audio", "video"]
"""
MP4 ファイル内のトラックの種類を表す型
"""


def _from_raw_mp4_track_kind(raw_kind: _RawMp4TrackKind) -> Mp4TrackKind:
    if raw_kind == _RawMp4TrackKind.AUDIO:
        return "audio"
    elif raw_kind == _RawMp4TrackKind.VIDEO:
        return "video"
    else:
        raise ValueError(f"Unknown track kind: {raw_kind}")


def _to_raw_mp4_track_kind(kind: Mp4TrackKind) -> int:
    return {"audio": 0, "video": 1}[kind]


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
    def _from_raw(raw_avc1: _RawMp4SampleEntryAvc1) -> "Mp4SampleEntryAvc1":
        # SPS データを抽出
        sps_data = []
        if raw_avc1.sps_count > 0 and raw_avc1.sps_data and raw_avc1.sps_sizes:
            for i in range(raw_avc1.sps_count):
                size = raw_avc1.sps_sizes[i]
                data = bytes(raw_avc1.sps_data[i][:size])
                sps_data.append(data)

        # PPS データを抽出
        pps_data = []
        if raw_avc1.pps_count > 0 and raw_avc1.pps_data and raw_avc1.pps_sizes:
            for i in range(raw_avc1.pps_count):
                size = raw_avc1.pps_sizes[i]
                data = bytes(raw_avc1.pps_data[i][:size])
                pps_data.append(data)

        # オプションのクロマ形式情報を抽出
        chroma_format = raw_avc1.chroma_format if raw_avc1.is_chroma_format_present else None
        bit_depth_luma_minus8 = (
            raw_avc1.bit_depth_luma_minus8 if raw_avc1.is_bit_depth_luma_minus8_present else None
        )
        bit_depth_chroma_minus8 = (
            raw_avc1.bit_depth_chroma_minus8
            if raw_avc1.is_bit_depth_chroma_minus8_present
            else None
        )

        return Mp4SampleEntryAvc1(
            width=raw_avc1.width,
            height=raw_avc1.height,
            avc_profile_indication=raw_avc1.avc_profile_indication,
            profile_compatibility=raw_avc1.profile_compatibility,
            avc_level_indication=raw_avc1.avc_level_indication,
            length_size_minus_one=raw_avc1.length_size_minus_one,
            sps_data=sps_data,
            pps_data=pps_data,
            chroma_format=chroma_format,
            bit_depth_luma_minus8=bit_depth_luma_minus8,
            bit_depth_chroma_minus8=bit_depth_chroma_minus8,
        )

    @contextmanager
    def _to_raw(self) -> Generator[_RawMp4SampleEntryAvc1, None, None]:
        # NOTE: C 側に渡すアドレスの予期せぬ解放を防止するために with パターンを使っている
        sps_arrays = []
        sps_pointers = (ctypes.POINTER(ctypes.c_uint8) * len(self.sps_data))()
        sps_sizes = (ctypes.c_uint32 * len(self.sps_data))()

        for i, sps in enumerate(self.sps_data):
            sps_array = (ctypes.c_uint8 * len(sps)).from_buffer_copy(sps)
            sps_arrays.append(sps_array)
            sps_pointers[i] = ctypes.cast(sps_array, ctypes.POINTER(ctypes.c_uint8))
            sps_sizes[i] = len(sps)

        # PPS バッファを作成
        pps_arrays = []
        pps_pointers = (ctypes.POINTER(ctypes.c_uint8) * len(self.pps_data))()
        pps_sizes = (ctypes.c_uint32 * len(self.pps_data))()

        for i, pps in enumerate(self.pps_data):
            pps_array = (ctypes.c_uint8 * len(pps)).from_buffer_copy(pps)
            pps_arrays.append(pps_array)
            pps_pointers[i] = ctypes.cast(pps_array, ctypes.POINTER(ctypes.c_uint8))
            pps_sizes[i] = len(pps)

        # raw 構造体を構築
        raw_avc1 = _RawMp4SampleEntryAvc1()
        raw_avc1.width = self.width
        raw_avc1.height = self.height
        raw_avc1.avc_profile_indication = self.avc_profile_indication
        raw_avc1.profile_compatibility = self.profile_compatibility
        raw_avc1.avc_level_indication = self.avc_level_indication
        raw_avc1.length_size_minus_one = self.length_size_minus_one
        raw_avc1.sps_data = sps_pointers
        raw_avc1.sps_sizes = sps_sizes
        raw_avc1.sps_count = len(self.sps_data)
        raw_avc1.pps_data = pps_pointers
        raw_avc1.pps_sizes = pps_sizes
        raw_avc1.pps_count = len(self.pps_data)
        raw_avc1.is_chroma_format_present = False
        raw_avc1.is_bit_depth_luma_minus8_present = False
        raw_avc1.is_bit_depth_chroma_minus8_present = False

        # オプションフィールドを設定
        if self.chroma_format is not None:
            raw_avc1.is_chroma_format_present = True
            raw_avc1.chroma_format = self.chroma_format
        if self.bit_depth_luma_minus8 is not None:
            raw_avc1.is_bit_depth_luma_minus8_present = True
            raw_avc1.bit_depth_luma_minus8 = self.bit_depth_luma_minus8
        if self.bit_depth_chroma_minus8 is not None:
            raw_avc1.is_bit_depth_chroma_minus8_present = True
            raw_avc1.bit_depth_chroma_minus8 = self.bit_depth_chroma_minus8

        yield raw_avc1


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
    def _from_raw(raw_hev1: _RawMp4SampleEntryHev1) -> "Mp4SampleEntryHev1":
        # NALU types を抽出
        nalu_types = []
        if raw_hev1.nalu_array_count > 0 and raw_hev1.nalu_types:
            for i in range(raw_hev1.nalu_array_count):
                nalu_types.append(raw_hev1.nalu_types[i])

        # NALU data を抽出
        nalu_data = []
        if raw_hev1.nalu_sizes and raw_hev1.nalu_data:
            # nalu_counts から各タイプのNALUサンプル数を取得
            offset = 0
            for i in range(raw_hev1.nalu_array_count):
                count = raw_hev1.nalu_counts[i] if raw_hev1.nalu_counts else 0
                for j in range(count):
                    size = raw_hev1.nalu_sizes[offset + j]
                    # 実装上、データは連続していると仮定
                    data = bytes(raw_hev1.nalu_data[offset + j : offset + j + size])
                    nalu_data.append(data)
                offset += count

        return Mp4SampleEntryHev1(
            width=raw_hev1.width,
            height=raw_hev1.height,
            general_profile_space=raw_hev1.general_profile_space,
            general_tier_flag=raw_hev1.general_tier_flag,
            general_profile_idc=raw_hev1.general_profile_idc,
            general_profile_compatibility_flags=raw_hev1.general_profile_compatibility_flags,
            general_constraint_indicator_flags=raw_hev1.general_constraint_indicator_flags,
            general_level_idc=raw_hev1.general_level_idc,
            chroma_format_idc=raw_hev1.chroma_format_idc,
            bit_depth_luma_minus8=raw_hev1.bit_depth_luma_minus8,
            bit_depth_chroma_minus8=raw_hev1.bit_depth_chroma_minus8,
            min_spatial_segmentation_idc=raw_hev1.min_spatial_segmentation_idc,
            parallelism_type=raw_hev1.parallelism_type,
            avg_frame_rate=raw_hev1.avg_frame_rate,
            constant_frame_rate=raw_hev1.constant_frame_rate,
            num_temporal_layers=raw_hev1.num_temporal_layers,
            temporal_id_nested=raw_hev1.temporal_id_nested,
            length_size_minus_one=raw_hev1.length_size_minus_one,
            nalu_types=nalu_types,
            nalu_data=nalu_data,
        )

    @contextmanager
    def _to_raw(self) -> Generator[_RawMp4SampleEntryHev1, None, None]:
        # NOTE: C 側に渡すアドレスの予期せぬ解放を防止するために with パターンを使っている
        nalu_types_array = (ctypes.c_uint8 * len(self.nalu_types))(*self.nalu_types)

        # NALU data バッファを作成
        nalu_data_arrays = []
        nalu_sizes = (ctypes.c_uint32 * len(self.nalu_data))()

        for i, data in enumerate(self.nalu_data):
            nalu_array = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            nalu_data_arrays.append(nalu_array)
            nalu_sizes[i] = len(data)

        # 連続したデータバッファを作成
        total_size = sum(len(d) for d in self.nalu_data)
        combined_data = (ctypes.c_uint8 * total_size)()
        offset = 0
        for data in self.nalu_data:
            for i, byte in enumerate(data):
                combined_data[offset + i] = byte
            offset += len(data)

        raw_hev1 = _RawMp4SampleEntryHev1()
        raw_hev1.width = self.width
        raw_hev1.height = self.height
        raw_hev1.general_profile_space = self.general_profile_space
        raw_hev1.general_tier_flag = self.general_tier_flag
        raw_hev1.general_profile_idc = self.general_profile_idc
        raw_hev1.general_profile_compatibility_flags = self.general_profile_compatibility_flags
        raw_hev1.general_constraint_indicator_flags = self.general_constraint_indicator_flags
        raw_hev1.general_level_idc = self.general_level_idc
        raw_hev1.chroma_format_idc = self.chroma_format_idc
        raw_hev1.bit_depth_luma_minus8 = self.bit_depth_luma_minus8
        raw_hev1.bit_depth_chroma_minus8 = self.bit_depth_chroma_minus8
        raw_hev1.min_spatial_segmentation_idc = self.min_spatial_segmentation_idc
        raw_hev1.parallelism_type = self.parallelism_type
        raw_hev1.avg_frame_rate = self.avg_frame_rate
        raw_hev1.constant_frame_rate = self.constant_frame_rate
        raw_hev1.num_temporal_layers = self.num_temporal_layers
        raw_hev1.temporal_id_nested = self.temporal_id_nested
        raw_hev1.length_size_minus_one = self.length_size_minus_one
        raw_hev1.nalu_array_count = len(self.nalu_types)
        raw_hev1.nalu_types = ctypes.cast(nalu_types_array, ctypes.POINTER(ctypes.c_uint8))
        raw_hev1.nalu_data = ctypes.cast(combined_data, ctypes.POINTER(ctypes.c_uint8))
        raw_hev1.nalu_sizes = nalu_sizes

        yield raw_hev1


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
    def _from_raw(raw_vp08: _RawMp4SampleEntryVp08) -> "Mp4SampleEntryVp08":
        return Mp4SampleEntryVp08(
            width=raw_vp08.width,
            height=raw_vp08.height,
            bit_depth=raw_vp08.bit_depth,
            chroma_subsampling=raw_vp08.chroma_subsampling,
            video_full_range_flag=raw_vp08.video_full_range_flag,
            colour_primaries=raw_vp08.colour_primaries,
            transfer_characteristics=raw_vp08.transfer_characteristics,
            matrix_coefficients=raw_vp08.matrix_coefficients,
        )

    @contextmanager
    def _to_raw(self) -> Generator[_RawMp4SampleEntryVp08, None, None]:
        # NOTE: リソース管理的には不要ではあるけど、他のクラスとインタフェースを合わせるために with パターンを使っている
        raw_vp08 = _RawMp4SampleEntryVp08()
        raw_vp08.width = self.width
        raw_vp08.height = self.height
        raw_vp08.bit_depth = self.bit_depth
        raw_vp08.chroma_subsampling = self.chroma_subsampling
        raw_vp08.video_full_range_flag = self.video_full_range_flag
        raw_vp08.colour_primaries = self.colour_primaries
        raw_vp08.transfer_characteristics = self.transfer_characteristics
        raw_vp08.matrix_coefficients = self.matrix_coefficients

        yield raw_vp08


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
    def _from_raw(raw_vp09: _RawMp4SampleEntryVp09) -> "Mp4SampleEntryVp09":
        return Mp4SampleEntryVp09(
            width=raw_vp09.width,
            height=raw_vp09.height,
            profile=raw_vp09.profile,
            level=raw_vp09.level,
            bit_depth=raw_vp09.bit_depth,
            chroma_subsampling=raw_vp09.chroma_subsampling,
            video_full_range_flag=raw_vp09.video_full_range_flag,
            colour_primaries=raw_vp09.colour_primaries,
            transfer_characteristics=raw_vp09.transfer_characteristics,
            matrix_coefficients=raw_vp09.matrix_coefficients,
        )

    @contextmanager
    def _to_raw(self) -> Generator[_RawMp4SampleEntryVp09, None, None]:
        # NOTE: リソース管理的には不要ではあるけど、他のクラスとインタフェースを合わせるために with パターンを使っている
        raw_vp09 = _RawMp4SampleEntryVp09()
        raw_vp09.width = self.width
        raw_vp09.height = self.height
        raw_vp09.profile = self.profile
        raw_vp09.level = self.level
        raw_vp09.bit_depth = self.bit_depth
        raw_vp09.chroma_subsampling = self.chroma_subsampling
        raw_vp09.video_full_range_flag = self.video_full_range_flag
        raw_vp09.colour_primaries = self.colour_primaries
        raw_vp09.transfer_characteristics = self.transfer_characteristics
        raw_vp09.matrix_coefficients = self.matrix_coefficients

        yield raw_vp09


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
    def _from_raw(raw_av01: _RawMp4SampleEntryAv01) -> "Mp4SampleEntryAv01":
        return Mp4SampleEntryAv01(
            width=raw_av01.width,
            height=raw_av01.height,
            seq_profile=raw_av01.seq_profile,
            seq_level_idx_0=raw_av01.seq_level_idx_0,
            seq_tier_0=raw_av01.seq_tier_0,
            high_bitdepth=raw_av01.high_bitdepth,
            twelve_bit=raw_av01.twelve_bit,
            monochrome=raw_av01.monochrome,
            chroma_subsampling_x=raw_av01.chroma_subsampling_x,
            chroma_subsampling_y=raw_av01.chroma_subsampling_y,
            chroma_sample_position=raw_av01.chroma_sample_position,
            initial_presentation_delay_present=raw_av01.initial_presentation_delay_present,
            initial_presentation_delay_minus_one=raw_av01.initial_presentation_delay_minus_one,
            config_obus=bytes(raw_av01.config_obus[: raw_av01.config_obus_size]),
        )

    @contextmanager
    def _to_raw(self) -> Generator[_RawMp4SampleEntryAv01, None, None]:
        # NOTE: C 側に渡すアドレスの予期せぬ解放を防止するために with パターンを使っている
        config_obus_array = (ctypes.c_uint8 * len(self.config_obus)).from_buffer_copy(
            self.config_obus
        )
        config_obus_size = len(self.config_obus)

        raw_av01 = _RawMp4SampleEntryAv01()
        raw_av01.width = self.width
        raw_av01.height = self.height
        raw_av01.seq_profile = self.seq_profile
        raw_av01.seq_level_idx_0 = self.seq_level_idx_0
        raw_av01.seq_tier_0 = self.seq_tier_0
        raw_av01.high_bitdepth = self.high_bitdepth
        raw_av01.twelve_bit = self.twelve_bit
        raw_av01.monochrome = self.monochrome
        raw_av01.chroma_subsampling_x = self.chroma_subsampling_x
        raw_av01.chroma_subsampling_y = self.chroma_subsampling_y
        raw_av01.chroma_sample_position = self.chroma_sample_position
        raw_av01.initial_presentation_delay_present = self.initial_presentation_delay_present
        raw_av01.initial_presentation_delay_minus_one = self.initial_presentation_delay_minus_one
        raw_av01.config_obus = ctypes.cast(config_obus_array, ctypes.POINTER(ctypes.c_uint8))
        raw_av01.config_obus_size = config_obus_size

        yield raw_av01


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
    def _from_raw(raw_opus: _RawMp4SampleEntryOpus) -> "Mp4SampleEntryOpus":
        return Mp4SampleEntryOpus(
            channel_count=raw_opus.channel_count,
            sample_rate=raw_opus.sample_rate,
            sample_size=raw_opus.sample_size,
            pre_skip=raw_opus.pre_skip,
            input_sample_rate=raw_opus.input_sample_rate,
            output_gain=raw_opus.output_gain,
        )

    @contextmanager
    def _to_raw(self) -> Generator[_RawMp4SampleEntryOpus, None, None]:
        # NOTE: リソース管理的には不要ではあるけど、他のクラスとインタフェースを合わせるために with パターンを使っている
        raw_opus = _RawMp4SampleEntryOpus()
        raw_opus.channel_count = self.channel_count
        raw_opus.sample_rate = self.sample_rate
        raw_opus.sample_size = self.sample_size
        raw_opus.pre_skip = self.pre_skip
        raw_opus.input_sample_rate = (
            self.sample_rate if self.input_sample_rate is None else self.input_sample_rate
        )
        raw_opus.output_gain = self.output_gain

        yield raw_opus


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
    def _from_raw(raw_mp4a: _RawMp4SampleEntryMp4a) -> "Mp4SampleEntryMp4a":
        dec_specific_info = bytes(raw_mp4a.dec_specific_info[: raw_mp4a.dec_specific_info_size])

        return Mp4SampleEntryMp4a(
            channel_count=raw_mp4a.channel_count,
            sample_rate=raw_mp4a.sample_rate,
            sample_size=raw_mp4a.sample_size,
            buffer_size_db=raw_mp4a.buffer_size_db,
            max_bitrate=raw_mp4a.max_bitrate,
            avg_bitrate=raw_mp4a.avg_bitrate,
            dec_specific_info=dec_specific_info,
        )

    @contextmanager
    def _to_raw(self) -> Generator[_RawMp4SampleEntryMp4a, None, None]:
        # NOTE: C 側に渡すアドレスの予期せぬ解放を防止するために with パターンを使っている
        dec_specific_info_array = (ctypes.c_uint8 * len(self.dec_specific_info)).from_buffer_copy(
            self.dec_specific_info
        )
        dec_specific_info_size = len(self.dec_specific_info)

        raw_mp4a = _RawMp4SampleEntryMp4a()
        raw_mp4a.channel_count = self.channel_count
        raw_mp4a.sample_rate = self.sample_rate
        raw_mp4a.sample_size = self.sample_size
        raw_mp4a.buffer_size_db = self.buffer_size_db
        raw_mp4a.max_bitrate = self.max_bitrate
        raw_mp4a.avg_bitrate = self.avg_bitrate
        raw_mp4a.dec_specific_info = ctypes.cast(
            dec_specific_info_array, ctypes.POINTER(ctypes.c_uint8)
        )
        raw_mp4a.dec_specific_info_size = dec_specific_info_size

        yield raw_mp4a


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


def _from_raw_mp4_sample_entry(raw_entry: _RawMp4SampleEntry) -> Mp4SampleEntry:
    kind = _RawMp4SampleEntryKind(raw_entry.kind)

    if kind == _RawMp4SampleEntryKind.AVC1:
        return Mp4SampleEntryAvc1._from_raw(raw_entry.data.avc1)
    elif kind == _RawMp4SampleEntryKind.HEV1:
        return Mp4SampleEntryHev1._from_raw(raw_entry.data.hev1)
    elif kind == _RawMp4SampleEntryKind.VP08:
        return Mp4SampleEntryVp08._from_raw(raw_entry.data.vp08)
    elif kind == _RawMp4SampleEntryKind.VP09:
        return Mp4SampleEntryVp09._from_raw(raw_entry.data.vp09)
    elif kind == _RawMp4SampleEntryKind.AV01:
        return Mp4SampleEntryAv01._from_raw(raw_entry.data.av01)
    elif kind == _RawMp4SampleEntryKind.OPUS:
        return Mp4SampleEntryOpus._from_raw(raw_entry.data.opus)
    elif kind == _RawMp4SampleEntryKind.MP4A:
        return Mp4SampleEntryMp4a._from_raw(raw_entry.data.mp4a)
    else:
        raise ValueError(f"Unsupported sample entry kind: {kind}")


@contextmanager
def _to_raw_mp4_sample_entry(entry: Mp4SampleEntry) -> Generator[_RawMp4SampleEntry, None, None]:
    raw_entry = _RawMp4SampleEntry()

    if isinstance(entry, Mp4SampleEntryAvc1):
        raw_entry.kind = _RawMp4SampleEntryKind.AVC1
        with entry._to_raw() as raw_avc1:
            raw_entry.data.avc1 = raw_avc1
            yield raw_entry
    elif isinstance(entry, Mp4SampleEntryHev1):
        raw_entry.kind = _RawMp4SampleEntryKind.HEV1
        with entry._to_raw() as raw_hev1:
            raw_entry.data.hev1 = raw_hev1
            yield raw_entry
    elif isinstance(entry, Mp4SampleEntryVp08):
        raw_entry.kind = _RawMp4SampleEntryKind.VP08
        with entry._to_raw() as raw_vp08:
            raw_entry.data.vp08 = raw_vp08
            yield raw_entry
    elif isinstance(entry, Mp4SampleEntryVp09):
        raw_entry.kind = _RawMp4SampleEntryKind.VP09
        with entry._to_raw() as raw_vp09:
            raw_entry.data.vp09 = raw_vp09
            yield raw_entry
    elif isinstance(entry, Mp4SampleEntryAv01):
        raw_entry.kind = _RawMp4SampleEntryKind.AV01
        with entry._to_raw() as raw_av01:
            raw_entry.data.av01 = raw_av01
            yield raw_entry
    elif isinstance(entry, Mp4SampleEntryOpus):
        raw_entry.kind = _RawMp4SampleEntryKind.OPUS
        with entry._to_raw() as raw_opus:
            raw_entry.data.opus = raw_opus
            yield raw_entry
    elif isinstance(entry, Mp4SampleEntryMp4a):
        raw_entry.kind = _RawMp4SampleEntryKind.MP4A
        with entry._to_raw() as raw_mp4a:
            raw_entry.data.mp4a = raw_mp4a
            yield raw_entry
    else:
        raise ValueError(f"Unsupported sample entry type: {type(entry).__name__}")
