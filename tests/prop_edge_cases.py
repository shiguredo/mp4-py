"""
境界値・エッジケースの property-based testing
"""

import io

from hypothesis import given, settings
from hypothesis import strategies as st

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
    Mp4SampleEntryHev1,
)


def prop_minimum_sample_size() -> None:
    """最小サイズ (1 バイト) のサンプル"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=b"\x00",  # 1 バイトのサンプル
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert demux_sample.data == b"\x00"


def prop_minimum_dimensions() -> None:
    """最小サイズの解像度 (1x1)"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1, height=1)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=b"test",
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert demux_sample.sample_entry.width == 1
    assert demux_sample.sample_entry.height == 1


def prop_maximum_dimensions() -> None:
    """大きな解像度 (8K)"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=7680, height=4320)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=b"test",
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert demux_sample.sample_entry.width == 7680
    assert demux_sample.sample_entry.height == 4320


def prop_minimum_duration() -> None:
    """最小の duration (1)"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=1,  # 最小の duration
        data=b"test",
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert demux_sample.duration == 1


def prop_large_duration() -> None:
    """大きな duration"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)
    large_duration = 2**31 - 1  # i32 の最大値に近い値
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=large_duration,
        data=b"test",
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert demux_sample.duration == large_duration


def prop_minimum_timescale() -> None:
    """最小の timescale (1)"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1,  # 最小の timescale
        duration=1,
        data=b"test",
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert demux_sample.track.timescale == 1


def prop_hev1_empty_nalu() -> None:
    """HEV1 で空の NALU リスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryHev1(
        width=1920,
        height=1080,
        general_profile_idc=1,
        general_level_idc=120,
        nalu_types=[],  # 空の NALU types
        nalu_data=[],  # 空の NALU data
    )

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=b"test",
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryHev1)


@given(
    sample_count=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=20)
def prop_all_keyframes(sample_count: int) -> None:
    """全てキーフレームの場合"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)

    for i in range(sample_count):
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,  # 全てキーフレーム
            timescale=30000,
            duration=1001,
            data=bytes([i % 256]) * 100,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    for sample in demuxer:
        assert sample.keyframe is True


@given(
    sample_count=st.integers(min_value=2, max_value=100),
)
@settings(max_examples=20)
def prop_no_keyframes_except_first(sample_count: int) -> None:
    """最初以外キーフレームなしの場合"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)

    for i in range(sample_count):
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=(i == 0),  # 最初だけキーフレーム
            timescale=30000,
            duration=1001,
            data=bytes([i % 256]) * 100,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    for i, sample in enumerate(demuxer):
        assert sample.keyframe == (i == 0)


@given(
    sample_size=st.integers(min_value=10000, max_value=100000),
)
@settings(max_examples=10)
def prop_large_sample_data(sample_size: int) -> None:
    """大きなサンプルデータ"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)
    large_data = bytes([i % 256 for i in range(sample_size)])

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=large_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    assert demux_sample.data == large_data


def prop_single_sample_per_track() -> None:
    """各トラックに 1 サンプルずつ"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    from mp4 import Mp4SampleEntryOpus

    video_entry = Mp4SampleEntryVp08(width=1920, height=1080)
    audio_entry = Mp4SampleEntryOpus(
        channel_count=2,
        sample_rate=48000,
        sample_size=16,
        pre_skip=312,
        output_gain=0,
    )

    # ビデオ 1 サンプル
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="video",
            sample_entry=video_entry,
            keyframe=True,
            timescale=30000,
            duration=1001,
            data=b"video",
        )
    )

    # オーディオ 1 サンプル
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="audio",
            sample_entry=audio_entry,
            keyframe=True,
            timescale=48000,
            duration=960,
            data=b"audio",
        )
    )

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    samples = list(demuxer)
    assert len(samples) == 2

    video_samples = [s for s in samples if s.track.kind == "video"]
    audio_samples = [s for s in samples if s.track.kind == "audio"]

    assert len(video_samples) == 1
    assert len(audio_samples) == 1
