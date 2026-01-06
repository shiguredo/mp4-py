"""
hypothesis を使った property-based testing 用のストラテジー定義
"""

from hypothesis import strategies as st

from mp4 import (
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryHvc1,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
)


# ============================================================================
# 共通のストラテジー
# ============================================================================

st_width = st.integers(min_value=16, max_value=4096)
st_height = st.integers(min_value=16, max_value=4096)
st_timescale = st.integers(min_value=1, max_value=1_000_000)
st_duration = st.integers(min_value=1, max_value=1_000_000)
st_sample_data = st.binary(min_size=1, max_size=4096)
st_keyframe = st.booleans()

# u8 フィールド
st_u8 = st.integers(min_value=0, max_value=255)

# オーディオのストラテジー
st_channel_count = st.integers(min_value=1, max_value=8)
# sample_rate は uint16_t (最大 65535) なので 96000 は除外
st_sample_rate = st.sampled_from([8000, 16000, 22050, 44100, 48000])
st_sample_size = st.sampled_from([8, 16, 24, 32])


# ============================================================================
# ビデオサンプルエントリーのストラテジー
# ============================================================================


@st.composite
def st_vp08_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryVp08:
    return Mp4SampleEntryVp08(
        width=draw(st_width),
        height=draw(st_height),
        bit_depth=draw(st.sampled_from([8, 10, 12])),
        chroma_subsampling=draw(st.integers(min_value=0, max_value=3)),
        video_full_range_flag=draw(st.booleans()),
        colour_primaries=draw(st_u8),
        transfer_characteristics=draw(st_u8),
        matrix_coefficients=draw(st_u8),
    )


@st.composite
def st_vp09_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryVp09:
    return Mp4SampleEntryVp09(
        width=draw(st_width),
        height=draw(st_height),
        profile=draw(st.integers(min_value=0, max_value=3)),
        level=draw(st.integers(min_value=10, max_value=62)),
        bit_depth=draw(st.sampled_from([8, 10, 12])),
        chroma_subsampling=draw(st.integers(min_value=0, max_value=3)),
        video_full_range_flag=draw(st.booleans()),
        colour_primaries=draw(st_u8),
        transfer_characteristics=draw(st_u8),
        matrix_coefficients=draw(st_u8),
    )


@st.composite
def st_avc1_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryAvc1:
    # 有効な SPS/PPS データを生成（最小限のダミー）
    sps_data = [bytes([0x67] + draw(st.lists(st_u8, min_size=4, max_size=32)))]
    pps_data = [bytes([0x68] + draw(st.lists(st_u8, min_size=2, max_size=16)))]

    # Baseline(66), Main(77), Extended(88) 以外のプロファイルでは
    # chroma_format, bit_depth_luma_minus8, bit_depth_chroma_minus8 が必要
    # Baseline/Main/Extended のみを使用して単純化する
    avc_profile = draw(st.sampled_from([66, 77, 88]))

    return Mp4SampleEntryAvc1(
        width=draw(st_width),
        height=draw(st_height),
        avc_profile_indication=avc_profile,
        avc_level_indication=draw(st_u8),
        profile_compatibility=draw(st_u8),
        sps_data=sps_data,
        pps_data=pps_data,
        length_size_minus_one=draw(st.sampled_from([0, 1, 3])),
    )


@st.composite
def st_hev1_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryHev1:
    nalu_count = draw(st.integers(min_value=1, max_value=3))
    nalu_types = [draw(st.integers(min_value=32, max_value=35)) for _ in range(nalu_count)]
    nalu_data = [draw(st.binary(min_size=4, max_size=64)) for _ in range(nalu_count)]

    return Mp4SampleEntryHev1(
        width=draw(st_width),
        height=draw(st_height),
        general_profile_idc=draw(st.integers(min_value=1, max_value=5)),
        general_level_idc=draw(st.integers(min_value=30, max_value=186)),
        nalu_types=nalu_types,
        nalu_data=nalu_data,
        general_profile_space=draw(st.integers(min_value=0, max_value=3)),
        general_tier_flag=draw(st.integers(min_value=0, max_value=1)),
        chroma_format_idc=draw(st.integers(min_value=0, max_value=3)),
        bit_depth_luma_minus8=draw(st.integers(min_value=0, max_value=4)),
        bit_depth_chroma_minus8=draw(st.integers(min_value=0, max_value=4)),
        length_size_minus_one=draw(st.sampled_from([0, 1, 3])),
    )


@st.composite
def st_hvc1_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryHvc1:
    nalu_count = draw(st.integers(min_value=1, max_value=3))
    nalu_types = [draw(st.integers(min_value=32, max_value=35)) for _ in range(nalu_count)]
    nalu_data = [draw(st.binary(min_size=4, max_size=64)) for _ in range(nalu_count)]

    return Mp4SampleEntryHvc1(
        width=draw(st_width),
        height=draw(st_height),
        general_profile_idc=draw(st.integers(min_value=1, max_value=5)),
        general_level_idc=draw(st.integers(min_value=30, max_value=186)),
        nalu_types=nalu_types,
        nalu_data=nalu_data,
        general_profile_space=draw(st.integers(min_value=0, max_value=3)),
        general_tier_flag=draw(st.integers(min_value=0, max_value=1)),
        chroma_format_idc=draw(st.integers(min_value=0, max_value=3)),
        bit_depth_luma_minus8=draw(st.integers(min_value=0, max_value=4)),
        bit_depth_chroma_minus8=draw(st.integers(min_value=0, max_value=4)),
        length_size_minus_one=draw(st.sampled_from([0, 1, 3])),
    )


@st.composite
def st_av01_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryAv01:
    return Mp4SampleEntryAv01(
        width=draw(st_width),
        height=draw(st_height),
        seq_profile=draw(st.integers(min_value=0, max_value=2)),
        seq_level_idx_0=draw(st.integers(min_value=0, max_value=31)),
        config_obus=draw(st.binary(min_size=0, max_size=64)),
        seq_tier_0=draw(st.integers(min_value=0, max_value=1)),
        high_bitdepth=draw(st.integers(min_value=0, max_value=1)),
        twelve_bit=draw(st.integers(min_value=0, max_value=1)),
        monochrome=draw(st.integers(min_value=0, max_value=1)),
        chroma_subsampling_x=draw(st.integers(min_value=0, max_value=1)),
        chroma_subsampling_y=draw(st.integers(min_value=0, max_value=1)),
        chroma_sample_position=draw(st.integers(min_value=0, max_value=3)),
    )


# ============================================================================
# オーディオサンプルエントリーのストラテジー
# ============================================================================


@st.composite
def st_opus_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryOpus:
    return Mp4SampleEntryOpus(
        draw(st_channel_count),
        draw(st_sample_rate),
        draw(st_sample_size),
        draw(st.integers(min_value=0, max_value=65535)),
        None,
        draw(st.integers(min_value=-32768, max_value=32767)),
    )


@st.composite
def st_mp4a_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryMp4a:
    return Mp4SampleEntryMp4a(
        channel_count=draw(st_channel_count),
        sample_rate=draw(st_sample_rate),
        dec_specific_info=draw(st.binary(min_size=2, max_size=64)),
        sample_size=draw(st_sample_size),
        buffer_size_db=draw(st.integers(min_value=0, max_value=16777215)),
        max_bitrate=draw(st.integers(min_value=0, max_value=1_000_000)),
        avg_bitrate=draw(st.integers(min_value=0, max_value=1_000_000)),
    )


@st.composite
def st_flac_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryFlac:
    return Mp4SampleEntryFlac(
        draw(st_channel_count),
        draw(st_sample_rate),
        draw(st.binary(min_size=34, max_size=34)),
        draw(st_sample_size),
    )


# ============================================================================
# 統合ストラテジー
# ============================================================================

st_video_sample_entry = st.one_of(
    st_vp08_sample_entry(),
    st_vp09_sample_entry(),
    st_avc1_sample_entry(),
    st_hev1_sample_entry(),
    st_hvc1_sample_entry(),
    st_av01_sample_entry(),
)

st_audio_sample_entry = st.one_of(
    st_opus_sample_entry(),
    st_mp4a_sample_entry(),
    st_flac_sample_entry(),
)
