"""
hypothesis を使った property-based testing

mp4-rust の実装を参考に、MP4 の Mux/Demux のプロパティをテストする。
"""

import io

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4FileMuxerOptions,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
    estimate_maximum_moov_box_size,
)


# ============================================================================
# ストラテジー定義
# ============================================================================

# 共通のストラテジー
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


# VP08 サンプルエントリーのストラテジー
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


# VP09 サンプルエントリーのストラテジー
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


# AVC1 サンプルエントリーのストラテジー
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


# HEV1 サンプルエントリーのストラテジー
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


# AV01 サンプルエントリーのストラテジー
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


# Opus サンプルエントリーのストラテジー
@st.composite
def st_opus_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryOpus:
    # 位置引数で渡す
    return Mp4SampleEntryOpus(
        draw(st_channel_count),  # channel_count
        draw(st_sample_rate),  # sample_rate
        draw(st_sample_size),  # sample_size
        draw(st.integers(min_value=0, max_value=65535)),  # pre_skip
        None,  # input_sample_rate
        draw(st.integers(min_value=-32768, max_value=32767)),  # output_gain
    )


# MP4A サンプルエントリーのストラテジー
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


# FLAC サンプルエントリーのストラテジー
@st.composite
def st_flac_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryFlac:
    # 位置引数で渡す
    return Mp4SampleEntryFlac(
        draw(st_channel_count),  # channel_count
        draw(st_sample_rate),  # sample_rate
        draw(st.binary(min_size=34, max_size=34)),  # streaminfo_data
        draw(st_sample_size),  # sample_size
    )


# ビデオサンプルエントリーの統合ストラテジー
st_video_sample_entry = st.one_of(
    st_vp08_sample_entry(),
    st_vp09_sample_entry(),
    st_avc1_sample_entry(),
    st_hev1_sample_entry(),
    st_av01_sample_entry(),
)

# オーディオサンプルエントリーの統合ストラテジー
st_audio_sample_entry = st.one_of(
    st_opus_sample_entry(),
    st_mp4a_sample_entry(),
    st_flac_sample_entry(),
)


# ============================================================================
# ラウンドトリップテスト
# ============================================================================


@given(
    sample_entry=st_video_sample_entry,
    sample_data=st_sample_data,
    timescale=st_timescale,
    duration=st_duration,
    keyframe=st_keyframe,
)
@settings(max_examples=100)
def test_video_mux_demux_roundtrip(
    sample_entry: (
        Mp4SampleEntryVp08
        | Mp4SampleEntryVp09
        | Mp4SampleEntryAvc1
        | Mp4SampleEntryHev1
        | Mp4SampleEntryAv01
    ),
    sample_data: bytes,
    timescale: int,
    duration: int,
    keyframe: bool,
) -> None:
    """ビデオサンプルの Mux → Demux ラウンドトリップでデータが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=keyframe,
        timescale=timescale,
        duration=duration,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demux_sample = next(demuxer)

    # サンプルデータが一致する
    assert demux_sample.data == sample_data
    # キーフレームフラグが一致する
    assert demux_sample.keyframe == keyframe
    # トラック種別が一致する
    assert demux_sample.track.kind == "video"
    # duration が一致する
    assert demux_sample.duration == duration
    # timescale が一致する
    assert demux_sample.track.timescale == timescale


@given(
    sample_entry=st_audio_sample_entry,
    sample_data=st_sample_data,
    timescale=st_timescale,
    duration=st_duration,
)
@settings(max_examples=100)
def test_audio_mux_demux_roundtrip(
    sample_entry: Mp4SampleEntryOpus | Mp4SampleEntryMp4a | Mp4SampleEntryFlac,
    sample_data: bytes,
    timescale: int,
    duration: int,
) -> None:
    """オーディオサンプルの Mux → Demux ラウンドトリップでデータが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="audio",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=timescale,
        duration=duration,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demux_sample = next(demuxer)

    # サンプルデータが一致する
    assert demux_sample.data == sample_data
    # トラック種別が一致する
    assert demux_sample.track.kind == "audio"
    # duration が一致する
    assert demux_sample.duration == duration
    # timescale が一致する
    assert demux_sample.track.timescale == timescale


# ============================================================================
# 複数サンプルのラウンドトリップテスト
# ============================================================================


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_count=st.integers(min_value=1, max_value=20),
    base_data=st_sample_data,
    timescale=st_timescale,
    duration=st_duration,
)
@settings(max_examples=50)
def test_multiple_samples_roundtrip(
    sample_entry: Mp4SampleEntryVp08,
    sample_count: int,
    base_data: bytes,
    timescale: int,
    duration: int,
) -> None:
    """複数サンプルの Mux → Demux で全てのサンプルが正しく復元される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    original_samples = []
    for i in range(sample_count):
        # 各サンプルにインデックスを埋め込む
        sample_data = bytes([i % 256]) + base_data
        is_keyframe = i % 5 == 0

        original_samples.append(
            {
                "data": sample_data,
                "keyframe": is_keyframe,
            }
        )

        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=is_keyframe,
            timescale=timescale,
            duration=duration,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demuxed_samples = list(demuxer)

    # サンプル数が一致する
    assert len(demuxed_samples) == sample_count

    # 各サンプルが正しく復元される
    for original, demuxed in zip(original_samples, demuxed_samples):
        assert demuxed.data == original["data"]
        assert demuxed.keyframe == original["keyframe"]


# ============================================================================
# faststart オプションのテスト
# ============================================================================


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_count=st.integers(min_value=1, max_value=10),
    sample_data=st_sample_data,
    timescale=st_timescale,
    duration=st_duration,
)
@settings(max_examples=50)
def test_faststart_roundtrip(
    sample_entry: Mp4SampleEntryVp08,
    sample_count: int,
    sample_data: bytes,
    timescale: int,
    duration: int,
) -> None:
    """faststart オプション付きでも正しくラウンドトリップできる"""
    output_buffer = io.BytesIO()

    estimated_size = Mp4FileMuxerOptions.estimate_maximum_moov_box_size(0, sample_count)
    options = Mp4FileMuxerOptions(reserved_moov_box_size=estimated_size)
    muxer = Mp4FileMuxer(output_buffer, options=options)

    for i in range(sample_count):
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=i == 0,
            timescale=timescale,
            duration=duration,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demuxed_samples = list(demuxer)
    assert len(demuxed_samples) == sample_count

    for demuxed in demuxed_samples:
        assert demuxed.data == sample_data


# ============================================================================
# estimate_maximum_moov_box_size のプロパティテスト
# ============================================================================


@given(
    audio_count=st.integers(min_value=0, max_value=10000),
    video_count=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=200)
def test_estimate_moov_size_non_negative(audio_count: int, video_count: int) -> None:
    """moov サイズの推定値は常に非負"""
    size = estimate_maximum_moov_box_size(audio_count, video_count)
    assert size >= 0


@given(
    audio_count=st.integers(min_value=0, max_value=10000),
    video_count=st.integers(min_value=0, max_value=10000),
    delta=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=200)
def test_estimate_moov_size_monotonic(audio_count: int, video_count: int, delta: int) -> None:
    """サンプル数が増えると推定サイズも増加（単調性）"""
    size_base = estimate_maximum_moov_box_size(audio_count, video_count)
    size_more_audio = estimate_maximum_moov_box_size(audio_count + delta, video_count)
    size_more_video = estimate_maximum_moov_box_size(audio_count, video_count + delta)

    assert size_more_audio >= size_base
    assert size_more_video >= size_base


# ============================================================================
# サンプルエントリーのフィールド保持テスト
# ============================================================================


@given(sample_entry=st_vp08_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_vp08_fields_preserved(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
    """VP08 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryVp08)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.bit_depth == sample_entry.bit_depth
    assert restored.chroma_subsampling == sample_entry.chroma_subsampling
    assert restored.video_full_range_flag == sample_entry.video_full_range_flag
    assert restored.colour_primaries == sample_entry.colour_primaries
    assert restored.transfer_characteristics == sample_entry.transfer_characteristics
    assert restored.matrix_coefficients == sample_entry.matrix_coefficients


@given(sample_entry=st_vp09_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_vp09_fields_preserved(sample_entry: Mp4SampleEntryVp09, sample_data: bytes) -> None:
    """VP09 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryVp09)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.profile == sample_entry.profile
    assert restored.level == sample_entry.level
    assert restored.bit_depth == sample_entry.bit_depth
    assert restored.chroma_subsampling == sample_entry.chroma_subsampling
    assert restored.video_full_range_flag == sample_entry.video_full_range_flag


@given(sample_entry=st_avc1_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_avc1_fields_preserved(sample_entry: Mp4SampleEntryAvc1, sample_data: bytes) -> None:
    """AVC1 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryAvc1)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.avc_profile_indication == sample_entry.avc_profile_indication
    assert restored.avc_level_indication == sample_entry.avc_level_indication
    assert restored.profile_compatibility == sample_entry.profile_compatibility
    assert restored.sps_data == sample_entry.sps_data
    assert restored.pps_data == sample_entry.pps_data


@given(sample_entry=st_hev1_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_hev1_fields_preserved(sample_entry: Mp4SampleEntryHev1, sample_data: bytes) -> None:
    """HEV1 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryHev1)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.general_profile_idc == sample_entry.general_profile_idc
    assert restored.general_level_idc == sample_entry.general_level_idc
    assert restored.nalu_types == sample_entry.nalu_types
    assert restored.nalu_data == sample_entry.nalu_data


@given(sample_entry=st_av01_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_av01_fields_preserved(sample_entry: Mp4SampleEntryAv01, sample_data: bytes) -> None:
    """AV01 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryAv01)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.seq_profile == sample_entry.seq_profile
    assert restored.seq_level_idx_0 == sample_entry.seq_level_idx_0
    assert restored.config_obus == sample_entry.config_obus


@given(sample_entry=st_opus_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_opus_fields_preserved(sample_entry: Mp4SampleEntryOpus, sample_data: bytes) -> None:
    """Opus サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="audio",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=48000,
        duration=960,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryOpus)

    assert restored.channel_count == sample_entry.channel_count
    assert restored.sample_rate == sample_entry.sample_rate
    assert restored.pre_skip == sample_entry.pre_skip
    assert restored.output_gain == sample_entry.output_gain


@given(sample_entry=st_mp4a_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_mp4a_fields_preserved(sample_entry: Mp4SampleEntryMp4a, sample_data: bytes) -> None:
    """MP4A サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="audio",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=48000,
        duration=1024,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryMp4a)

    assert restored.channel_count == sample_entry.channel_count
    assert restored.sample_rate == sample_entry.sample_rate
    assert restored.dec_specific_info == sample_entry.dec_specific_info


@given(sample_entry=st_flac_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def test_flac_fields_preserved(sample_entry: Mp4SampleEntryFlac, sample_data: bytes) -> None:
    """FLAC サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="audio",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=48000,
        duration=4096,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryFlac)

    assert restored.channel_count == sample_entry.channel_count
    assert restored.sample_rate == sample_entry.sample_rate
    assert restored.streaminfo_data == sample_entry.streaminfo_data


# ============================================================================
# タイムスタンプ計算のプロパティテスト
# ============================================================================


@given(
    timescale=st.integers(min_value=1, max_value=1_000_000),
    duration=st.integers(min_value=1, max_value=1_000_000),
    sample_count=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100)
def test_timestamp_accumulation(timescale: int, duration: int, sample_count: int) -> None:
    """タイムスタンプは duration の累積で計算される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)

    for _ in range(sample_count):
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=timescale,
            duration=duration,
            data=b"test",
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demuxed_samples = list(demuxer)

    # 各サンプルのタイムスタンプが累積になっている
    for i, sample in enumerate(demuxed_samples):
        expected_timestamp = i * duration
        assert sample.timestamp == expected_timestamp


@given(
    timestamp=st.integers(min_value=0, max_value=1_000_000_000),
    timescale=st.integers(min_value=1, max_value=1_000_000),
)
@settings(max_examples=200)
def test_timestamp_seconds_calculation(timestamp: int, timescale: int) -> None:
    """timestamp_seconds は timestamp / timescale で計算される"""
    from mp4 import Mp4TrackInfo, Mp4DemuxSample, Mp4SampleEntryVp08

    track = Mp4TrackInfo(
        track_id=1,
        kind="video",
        duration=timestamp + 1000,
        timescale=timescale,
    )
    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)

    demux_sample = Mp4DemuxSample(
        track=track,
        sample_entry=sample_entry,
        keyframe=True,
        timestamp=timestamp,
        duration=1000,
        data_offset=0,
        data_size=4,
        input_stream=io.BytesIO(b"test"),
    )

    expected_seconds = timestamp / timescale
    # 浮動小数点の誤差を考慮
    assert abs(demux_sample.timestamp_seconds - expected_seconds) < 1e-9


# ============================================================================
# コンテキストマネージャーのテスト
# ============================================================================


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_data=st_sample_data,
)
@settings(max_examples=50)
def test_context_manager_muxer(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
    """Mp4FileMuxer のコンテキストマネージャーが正しく動作する"""
    output_buffer = io.BytesIO()

    with Mp4FileMuxer(output_buffer) as muxer:
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=1000000,
            duration=33333,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)
        muxer.finalize()

    # コンテキストマネージャーを抜けた後でもファイルが正しく生成されている
    assert len(output_buffer.getvalue()) > 0


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_data=st_sample_data,
)
@settings(max_examples=50)
def test_context_manager_demuxer(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
    """Mp4FileDemuxer のコンテキストマネージャーが正しく動作する"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)

    with Mp4FileDemuxer(output_buffer) as demuxer:
        demux_sample = next(demuxer)
        assert demux_sample.data == sample_data


# ============================================================================
# 複雑な MP4 ファイル構造のテスト
# ============================================================================


@given(
    video_entry=st_vp08_sample_entry(),
    audio_entry=st_opus_sample_entry(),
    video_count=st.integers(min_value=1, max_value=30),
    audio_count=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=50)
def test_mixed_video_audio_tracks(
    video_entry: Mp4SampleEntryVp08,
    audio_entry: Mp4SampleEntryOpus,
    video_count: int,
    audio_count: int,
) -> None:
    """ビデオとオーディオの複数トラックを含む MP4 ファイル"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    video_samples = []
    audio_samples = []

    # ビデオとオーディオをインターリーブして追加
    video_idx = 0
    audio_idx = 0
    while video_idx < video_count or audio_idx < audio_count:
        # ビデオを追加
        if video_idx < video_count:
            data = bytes([video_idx % 256]) * 100
            video_samples.append(data)
            mux_sample = Mp4MuxSample(
                track_kind="video",
                sample_entry=video_entry,
                keyframe=video_idx % 10 == 0,
                timescale=30000,
                duration=1001,
                data=data,
            )
            muxer.append_sample(mux_sample)
            video_idx += 1

        # オーディオを追加
        if audio_idx < audio_count:
            data = bytes([audio_idx % 256]) * 50
            audio_samples.append(data)
            mux_sample = Mp4MuxSample(
                track_kind="audio",
                sample_entry=audio_entry,
                keyframe=True,
                timescale=48000,
                duration=960,
                data=data,
            )
            muxer.append_sample(mux_sample)
            audio_idx += 1

    muxer.finalize()

    # デマルチプレックス
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    # トラック数を確認
    tracks = demuxer.tracks
    assert len(tracks) == 2

    # サンプルを分類
    demuxed_video = []
    demuxed_audio = []
    for sample in demuxer:
        if sample.track.kind == "video":
            demuxed_video.append(sample.data)
        else:
            demuxed_audio.append(sample.data)

    # サンプル数とデータを確認
    assert len(demuxed_video) == video_count
    assert len(demuxed_audio) == audio_count
    assert demuxed_video == video_samples
    assert demuxed_audio == audio_samples


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_count=st.integers(min_value=10, max_value=100),
    data=st.data(),
)
@settings(max_examples=30)
def test_variable_duration_samples(
    sample_entry: Mp4SampleEntryVp08,
    sample_count: int,
    data: st.DataObject,
) -> None:
    """異なる duration を持つサンプルの処理"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    original_samples = []
    for i in range(sample_count):
        # 各サンプルに異なる duration を割り当て
        duration = data.draw(st.integers(min_value=100, max_value=10000))
        sample_data = bytes([i % 256]) * data.draw(st.integers(min_value=10, max_value=500))

        original_samples.append(
            {
                "data": sample_data,
                "duration": duration,
                "keyframe": i % 5 == 0,
            }
        )

        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=i % 5 == 0,
            timescale=1000000,
            duration=duration,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demuxed_samples = list(demuxer)

    assert len(demuxed_samples) == sample_count

    # 各サンプルの duration とデータが一致することを確認
    expected_timestamp = 0
    for original, demuxed in zip(original_samples, demuxed_samples):
        assert demuxed.data == original["data"]
        assert demuxed.duration == original["duration"]
        assert demuxed.keyframe == original["keyframe"]
        assert demuxed.timestamp == expected_timestamp
        expected_timestamp += original["duration"]


@given(
    sample_entry=st_vp09_sample_entry(),
    keyframe_interval=st.integers(min_value=1, max_value=30),
    sample_count=st.integers(min_value=30, max_value=120),
)
@settings(max_examples=30)
def test_keyframe_patterns(
    sample_entry: Mp4SampleEntryVp09,
    keyframe_interval: int,
    sample_count: int,
) -> None:
    """様々なキーフレームパターンの処理"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    expected_keyframes = []
    for i in range(sample_count):
        is_keyframe = i % keyframe_interval == 0
        expected_keyframes.append(is_keyframe)

        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=is_keyframe,
            timescale=90000,
            duration=3000,
            data=b"frame" + bytes([i % 256]),
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demuxed_samples = list(demuxer)

    # キーフレームパターンが保持されていることを確認
    for i, sample in enumerate(demuxed_samples):
        assert sample.keyframe == expected_keyframes[i]


@given(
    video_entry=st_video_sample_entry,
    audio_entry=st_audio_sample_entry,
    video_count=st.integers(min_value=50, max_value=200),
    audio_count=st.integers(min_value=100, max_value=400),
)
@settings(max_examples=20, deadline=None)
def test_large_file_structure(
    video_entry: (
        Mp4SampleEntryVp08
        | Mp4SampleEntryVp09
        | Mp4SampleEntryAvc1
        | Mp4SampleEntryHev1
        | Mp4SampleEntryAv01
    ),
    audio_entry: Mp4SampleEntryOpus | Mp4SampleEntryMp4a | Mp4SampleEntryFlac,
    video_count: int,
    audio_count: int,
) -> None:
    """大量のサンプルを含む MP4 ファイル（ストレステスト）"""
    output_buffer = io.BytesIO()

    # faststart 用に moov サイズを推定
    estimated_size = Mp4FileMuxerOptions.estimate_maximum_moov_box_size(audio_count, video_count)
    options = Mp4FileMuxerOptions(reserved_moov_box_size=estimated_size)
    muxer = Mp4FileMuxer(output_buffer, options=options)

    total_video_bytes = 0
    total_audio_bytes = 0

    # ビデオサンプルを追加
    for i in range(video_count):
        data = bytes([i % 256]) * 200
        total_video_bytes += len(data)
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=video_entry,
            keyframe=i % 30 == 0,
            timescale=30000,
            duration=1001,
            data=data,
        )
        muxer.append_sample(mux_sample)

    # オーディオサンプルを追加
    for i in range(audio_count):
        data = bytes([i % 256]) * 100
        total_audio_bytes += len(data)
        mux_sample = Mp4MuxSample(
            track_kind="audio",
            sample_entry=audio_entry,
            keyframe=True,
            timescale=48000,
            duration=1024,
            data=data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    # ファイルサイズの検証
    file_size = len(output_buffer.getvalue())
    assert file_size > total_video_bytes + total_audio_bytes

    # デマルチプレックスして検証
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    video_samples = 0
    audio_samples = 0
    for sample in demuxer:
        if sample.track.kind == "video":
            video_samples += 1
        else:
            audio_samples += 1

    assert video_samples == video_count
    assert audio_samples == audio_count


@given(
    data=st.data(),
)
@settings(max_examples=20)
def test_random_codec_combinations(data: st.DataObject) -> None:
    """ランダムなコーデックの組み合わせ"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # ランダムにビデオコーデックを選択
    video_entry = data.draw(st_video_sample_entry)
    # ランダムにオーディオコーデックを選択
    audio_entry = data.draw(st_audio_sample_entry)

    sample_count = data.draw(st.integers(min_value=5, max_value=20))

    for i in range(sample_count):
        # ビデオ
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=video_entry,
            keyframe=i == 0,
            timescale=30000,
            duration=1001,
            data=b"video" + bytes([i]),
        )
        muxer.append_sample(mux_sample)

        # オーディオ
        mux_sample = Mp4MuxSample(
            track_kind="audio",
            sample_entry=audio_entry,
            keyframe=True,
            timescale=48000,
            duration=1024,
            data=b"audio" + bytes([i]),
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 2

    demuxed = list(demuxer)
    assert len(demuxed) == sample_count * 2


@given(
    sample_entry=st_vp08_sample_entry(),
    data=st.data(),
)
@settings(max_examples=10, suppress_health_check=[HealthCheck.data_too_large])
def test_variable_size_samples(
    sample_entry: Mp4SampleEntryVp08,
    data: st.DataObject,
) -> None:
    """様々なサイズのサンプルデータ"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    original_data = []
    sample_count = data.draw(st.integers(min_value=3, max_value=10))

    for i in range(sample_count):
        # 1 バイトから 500 バイトまでのランダムサイズ
        size = data.draw(st.integers(min_value=1, max_value=500))
        sample_data = data.draw(st.binary(min_size=size, max_size=size))
        original_data.append(sample_data)

        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=i == 0,
            timescale=30000,
            duration=1001,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    for i, sample in enumerate(demuxer):
        assert sample.data == original_data[i]
