"""
Mux/Demux ラウンドトリップの property-based testing
"""

import io

from hypothesis import given, settings
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
    Mp4SampleEntryHvc1,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
)

from conftest import (
    st_video_sample_entry,
    st_audio_sample_entry,
    st_vp08_sample_entry,
    st_sample_data,
    st_timescale,
    st_duration,
    st_keyframe,
)


@given(
    sample_entry=st_video_sample_entry,
    sample_data=st_sample_data,
    timescale=st_timescale,
    duration=st_duration,
    keyframe=st_keyframe,
)
@settings(max_examples=100)
def prop_video_mux_demux_roundtrip(
    sample_entry: (
        Mp4SampleEntryVp08
        | Mp4SampleEntryVp09
        | Mp4SampleEntryAvc1
        | Mp4SampleEntryHev1
        | Mp4SampleEntryHvc1
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
def prop_audio_mux_demux_roundtrip(
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


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_count=st.integers(min_value=1, max_value=20),
    base_data=st_sample_data,
    timescale=st_timescale,
    duration=st_duration,
)
@settings(max_examples=50)
def prop_multiple_samples_roundtrip(
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


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_count=st.integers(min_value=1, max_value=10),
    sample_data=st_sample_data,
    timescale=st_timescale,
    duration=st_duration,
)
@settings(max_examples=50)
def prop_faststart_roundtrip(
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
