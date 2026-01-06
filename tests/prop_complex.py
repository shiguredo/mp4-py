"""
複雑な MP4 ファイル構造の property-based testing
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
    Mp4SampleEntryHvc1,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
)

from conftest import (
    st_vp08_sample_entry,
    st_vp09_sample_entry,
    st_opus_sample_entry,
    st_video_sample_entry,
    st_audio_sample_entry,
)


@given(
    video_entry=st_vp08_sample_entry(),
    audio_entry=st_opus_sample_entry(),
    video_count=st.integers(min_value=1, max_value=30),
    audio_count=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=50)
def prop_mixed_video_audio_tracks(
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
def prop_variable_duration_samples(
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
def prop_keyframe_patterns(
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
def prop_large_file_structure(
    video_entry: (
        Mp4SampleEntryVp08
        | Mp4SampleEntryVp09
        | Mp4SampleEntryAvc1
        | Mp4SampleEntryHev1
        | Mp4SampleEntryHvc1
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
def prop_random_codec_combinations(data: st.DataObject) -> None:
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
def prop_variable_size_samples(
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
