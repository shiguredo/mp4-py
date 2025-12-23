"""
hypothesis を使った fuzzing テスト

ランダムなデータを入力してクラッシュしないことを確認する。

実行方法:
    pytest tests/test_fuzzing.py --run-fuzzing
"""

import io
import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
)


# 環境変数または --run-fuzzing オプションで有効化
def pytest_configure(config):
    config.addinivalue_line("markers", "fuzzing: mark test as fuzzing test")


# fuzzing テストをスキップするかどうか
skip_fuzzing = pytest.mark.skipif(
    os.environ.get("RUN_FUZZING", "0") != "1",
    reason="fuzzing テストはデフォルトでスキップ。RUN_FUZZING=1 で有効化。",
)


@skip_fuzzing
@given(data=st.binary(min_size=0, max_size=100))
@settings(max_examples=3, deadline=None)
def test_fuzzing_demuxer_random_bytes(data: bytes) -> None:
    """ランダムなバイナリデータを Demuxer に渡してクラッシュしないことを確認"""
    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(data=st.binary(min_size=0, max_size=100))
@settings(max_examples=3, deadline=None)
def test_fuzzing_demuxer_with_mp4_header(data: bytes) -> None:
    """MP4 ヘッダー付きのランダムデータを Demuxer に渡してクラッシュしないことを確認"""
    ftyp_header = bytes(
        [
            0x00,
            0x00,
            0x00,
            0x14,
            0x66,
            0x74,
            0x79,
            0x70,
            0x69,
            0x73,
            0x6F,
            0x6D,
            0x00,
            0x00,
            0x02,
            0x00,
            0x69,
            0x73,
            0x6F,
            0x6D,
        ]
    )
    mp4_data = ftyp_header + data

    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(
    valid_mp4=st.binary(min_size=50, max_size=100),
    corruption_offset=st.integers(min_value=0, max_value=99),
    corruption_byte=st.integers(min_value=0, max_value=255),
)
@settings(max_examples=3, deadline=None)
def test_fuzzing_corrupted_mp4(
    valid_mp4: bytes,
    corruption_offset: int,
    corruption_byte: int,
) -> None:
    """正規の MP4 を生成してから一部を破損させてパースを試みる"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_entry = Mp4SampleEntryVp08(width=640, height=480)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=30000,
        duration=1001,
        data=valid_mp4,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    mp4_bytes = bytearray(output_buffer.getvalue())
    if len(mp4_bytes) > 0:
        corruption_pos = corruption_offset % len(mp4_bytes)
        mp4_bytes[corruption_pos] = corruption_byte

    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(bytes(mp4_bytes)))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(
    box_type=st.binary(min_size=4, max_size=4),
    box_size=st.integers(min_value=0, max_value=0xFFFFFFFF),
    box_data=st.binary(min_size=0, max_size=100),
)
@settings(max_examples=3, deadline=None)
def test_fuzzing_random_box_structure(
    box_type: bytes,
    box_size: int,
    box_data: bytes,
) -> None:
    """ランダムなボックス構造を生成してパースを試みる"""
    size_bytes = box_size.to_bytes(4, "big")
    mp4_data = size_bytes + box_type + box_data

    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(
    num_boxes=st.integers(min_value=1, max_value=3),
    data=st.data(),
)
@settings(max_examples=3, deadline=None)
def test_fuzzing_nested_boxes(num_boxes: int, data: st.DataObject) -> None:
    """ネストしたボックス構造をランダムに生成"""
    mp4_data = b""

    for _ in range(num_boxes):
        box_type = data.draw(st.binary(min_size=4, max_size=4))
        box_content = data.draw(st.binary(min_size=0, max_size=50))
        box_size = 8 + len(box_content)
        size_bytes = box_size.to_bytes(4, "big")
        mp4_data += size_bytes + box_type + box_content

    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(
    sample_count=st.integers(min_value=1, max_value=3),
    data=st.data(),
)
@settings(max_examples=3, deadline=None)
def test_fuzzing_muxer_random_data(sample_count: int, data: st.DataObject) -> None:
    """Muxer にランダムなサンプルデータを渡してクラッシュしないことを確認"""
    output_buffer = io.BytesIO()

    try:
        muxer = Mp4FileMuxer(output_buffer)

        for _ in range(sample_count):
            sample_entry = Mp4SampleEntryVp08(
                width=data.draw(st.integers(min_value=1, max_value=4096)),
                height=data.draw(st.integers(min_value=1, max_value=4096)),
            )
            sample_data = data.draw(st.binary(min_size=1, max_size=100))

            mux_sample = Mp4MuxSample(
                track_kind="video",
                sample_entry=sample_entry,
                keyframe=data.draw(st.booleans()),
                timescale=data.draw(st.integers(min_value=1, max_value=1000000)),
                duration=data.draw(st.integers(min_value=1, max_value=1000000)),
                data=sample_data,
            )
            muxer.append_sample(mux_sample)

        muxer.finalize()

        output_buffer.seek(0)
        demuxer = Mp4FileDemuxer(output_buffer)
        demuxed = list(demuxer)
        assert len(demuxed) == sample_count

    except (ValueError, RuntimeError, StopIteration):
        pass
