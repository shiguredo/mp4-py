"""
タイムスタンプ計算の property-based testing
"""

import io

from hypothesis import given, settings
from hypothesis import strategies as st

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
    Mp4TrackInfo,
    Mp4DemuxSample,
)


@given(
    timescale=st.integers(min_value=1, max_value=1_000_000),
    duration=st.integers(min_value=1, max_value=1_000_000),
    sample_count=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100)
def prop_timestamp_accumulation(timescale: int, duration: int, sample_count: int) -> None:
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
def prop_timestamp_seconds_calculation(timestamp: int, timescale: int) -> None:
    """timestamp_seconds は timestamp / timescale で計算される"""
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
