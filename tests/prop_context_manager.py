"""
コンテキストマネージャーの property-based testing
"""

import io

from hypothesis import given, settings
from hypothesis import strategies as st

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
    Mp4SampleEntryOpus,
)

from conftest import (
    st_vp08_sample_entry,
    st_opus_sample_entry,
    st_sample_data,
)


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_data=st_sample_data,
)
@settings(max_examples=50)
def prop_context_manager_muxer(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
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
def prop_context_manager_demuxer(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
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


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_count=st.integers(min_value=1, max_value=20),
    sample_data=st.binary(min_size=1, max_size=1000),
)
@settings(max_examples=50)
def prop_with_muxer_demuxer_roundtrip(
    sample_entry: Mp4SampleEntryVp08,
    sample_count: int,
    sample_data: bytes,
) -> None:
    """with 文で muxer と demuxer を使った roundtrip テスト"""
    output_buffer = io.BytesIO()

    # with 文で muxer を使用
    with Mp4FileMuxer(output_buffer) as muxer:
        for i in range(sample_count):
            mux_sample = Mp4MuxSample(
                track_kind="video",
                sample_entry=sample_entry,
                keyframe=i == 0,
                timescale=30000,
                duration=1001,
                data=sample_data,
            )
            muxer.append_sample(mux_sample)

    # with 文で demuxer を使用
    output_buffer.seek(0)
    with Mp4FileDemuxer(output_buffer) as demuxer:
        samples = list(demuxer)
        assert len(samples) == sample_count
        for i, sample in enumerate(samples):
            assert sample.data == sample_data
            assert sample.keyframe == (i == 0)


@given(
    video_entry=st_vp08_sample_entry(),
    audio_entry=st_opus_sample_entry(),
    video_data=st.binary(min_size=1, max_size=500),
    audio_data=st.binary(min_size=1, max_size=500),
)
@settings(max_examples=50)
def prop_with_mixed_tracks_roundtrip(
    video_entry: Mp4SampleEntryVp08,
    audio_entry: Mp4SampleEntryOpus,
    video_data: bytes,
    audio_data: bytes,
) -> None:
    """with 文でビデオとオーディオの混合トラックをテスト"""
    output_buffer = io.BytesIO()

    with Mp4FileMuxer(output_buffer) as muxer:
        # ビデオサンプル
        muxer.append_sample(
            Mp4MuxSample(
                track_kind="video",
                sample_entry=video_entry,
                keyframe=True,
                timescale=30000,
                duration=1001,
                data=video_data,
            )
        )
        # オーディオサンプル
        muxer.append_sample(
            Mp4MuxSample(
                track_kind="audio",
                sample_entry=audio_entry,
                keyframe=True,
                timescale=48000,
                duration=960,
                data=audio_data,
            )
        )

    output_buffer.seek(0)
    with Mp4FileDemuxer(output_buffer) as demuxer:
        tracks = demuxer.tracks
        assert len(tracks) == 2

        samples = list(demuxer)
        assert len(samples) == 2

        video_samples = [s for s in samples if s.track.kind == "video"]
        audio_samples = [s for s in samples if s.track.kind == "audio"]

        assert len(video_samples) == 1
        assert len(audio_samples) == 1
        assert video_samples[0].data == video_data
        assert audio_samples[0].data == audio_data
