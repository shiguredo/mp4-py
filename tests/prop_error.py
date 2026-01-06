"""
エラーハンドリングの property-based testing
"""

import io

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
)

from conftest import (
    st_vp08_sample_entry,
    st_sample_data,
)


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_data=st_sample_data,
)
@settings(max_examples=20)
def prop_append_after_finalize_raises_error(
    sample_entry: Mp4SampleEntryVp08, sample_data: bytes
) -> None:
    """finalize 後に append_sample を呼ぶとエラーになる"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # 最初のサンプルを追加
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

    # finalize 後に追加しようとするとエラー
    with pytest.raises(Exception):
        muxer.append_sample(mux_sample)


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_data=st_sample_data,
)
@settings(max_examples=20)
def prop_double_finalize_is_idempotent(
    sample_entry: Mp4SampleEntryVp08, sample_data: bytes
) -> None:
    """二重に finalize を呼んでも問題ない"""
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

    # 二重 finalize は許容される
    muxer.finalize()


@given(data=st.binary(min_size=1, max_size=100))
@settings(max_examples=50)
def prop_demuxer_handles_garbage_data(data: bytes) -> None:
    """ランダムなデータを渡してもクラッシュしない"""
    buffer = io.BytesIO(data)
    demuxer = Mp4FileDemuxer(buffer)

    # エラーを投げずに空のリストを返すか、正常に処理する
    samples = list(demuxer)
    # クラッシュしなければ成功
    assert isinstance(samples, list)


@given(
    prefix=st.binary(min_size=0, max_size=50),
    suffix=st.binary(min_size=0, max_size=50),
)
@settings(max_examples=30)
def prop_demuxer_handles_truncated_mp4(prefix: bytes, suffix: bytes) -> None:
    """不完全な MP4 データを渡してもクラッシュしない (エラーは許容)"""
    # 有効な ftyp ボックスの先頭部分
    ftyp_header = b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00"

    # 途中で切れたデータ
    truncated_data = prefix + ftyp_header[:8] + suffix

    buffer = io.BytesIO(truncated_data)
    demuxer = Mp4FileDemuxer(buffer)

    # パース失敗は RuntimeError として報告される
    # クラッシュしなければ成功
    try:
        samples = list(demuxer)
        assert isinstance(samples, list)
    except RuntimeError:
        # パースエラーは許容
        pass


def prop_muxer_empty_finalize() -> None:
    """サンプルなしで finalize しても正常に動作する"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    muxer.finalize()

    # 有効な MP4 ファイルが生成される
    assert len(output_buffer.getvalue()) > 0


def prop_demuxer_empty_file() -> None:
    """空のファイルを渡してもクラッシュしない"""
    buffer = io.BytesIO(b"")
    demuxer = Mp4FileDemuxer(buffer)

    # 空のファイルではサンプルがない
    samples = list(demuxer)
    assert samples == []


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_data=st_sample_data,
)
@settings(max_examples=20)
def prop_muxer_close_is_idempotent(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
    """close() を複数回呼んでも問題ない"""
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

    # close() を複数回呼ぶ
    muxer.close()
    muxer.close()
    muxer.close()

    # クラッシュしなければ成功


@given(
    sample_entry=st_vp08_sample_entry(),
    sample_data=st_sample_data,
)
@settings(max_examples=20)
def prop_demuxer_close_is_idempotent(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
    """Demuxer の close() を複数回呼んでも問題ない"""
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

    # close() を複数回呼ぶ
    demuxer.close()
    demuxer.close()
    demuxer.close()

    # クラッシュしなければ成功
