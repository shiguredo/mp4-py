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
@given(data=st.binary(min_size=0, max_size=10000))
@settings(max_examples=10, deadline=None)
def test_fuzzing_demuxer_random_bytes(data: bytes) -> None:
    """ランダムなバイナリデータを Demuxer に渡してクラッシュしないことを確認"""
    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(data=st.binary(min_size=0, max_size=10000))
@settings(max_examples=10, deadline=None)
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
    valid_mp4=st.binary(min_size=100, max_size=5000),
    corruption_offset=st.integers(min_value=0, max_value=9999),
    corruption_byte=st.integers(min_value=0, max_value=255),
)
@settings(max_examples=10, deadline=None)
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
    box_data=st.binary(min_size=0, max_size=5000),
)
@settings(max_examples=10, deadline=None)
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


# ボックスサイズの境界値
BOX_SIZE_BOUNDARY_VALUES = [
    0,  # サイズ 0（ファイル末尾まで）
    1,  # 不正なサイズ
    7,  # ヘッダより小さい
    8,  # 最小の有効なボックス（ヘッダのみ）
    9,  # ヘッダ + 1 バイト
    0xFFFFFFFF,  # 拡張サイズを示す特殊値
]

# MP4 の重要なボックスタイプ
MP4_BOX_TYPES = [
    b"ftyp",  # ファイルタイプ
    b"moov",  # ムービー（メタデータ）
    b"mdat",  # メディアデータ
    b"free",  # フリースペース
    b"skip",  # スキップ
    b"moof",  # ムービーフラグメント
    b"mfra",  # ムービーフラグメントランダムアクセス
    b"trak",  # トラック
    b"tkhd",  # トラックヘッダ
    b"mdia",  # メディア
    b"minf",  # メディア情報
    b"stbl",  # サンプルテーブル
    b"stsd",  # サンプル記述
    b"stts",  # タイムトゥサンプル
    b"stsc",  # サンプルトゥチャンク
    b"stsz",  # サンプルサイズ
    b"stco",  # チャンクオフセット
    b"co64",  # 64 ビットチャンクオフセット
]


@skip_fuzzing
@given(
    box_type=st.sampled_from(MP4_BOX_TYPES),
    box_size=st.sampled_from(BOX_SIZE_BOUNDARY_VALUES),
    box_data=st.binary(min_size=0, max_size=1000),
)
@settings(max_examples=10, deadline=None)
def test_fuzzing_box_size_boundaries(
    box_type: bytes,
    box_size: int,
    box_data: bytes,
) -> None:
    """ボックスサイズの境界値をテスト"""
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
    box_type=st.sampled_from(MP4_BOX_TYPES),
    extended_size=st.integers(min_value=0, max_value=0xFFFFFFFFFFFFFFFF),
    box_data=st.binary(min_size=0, max_size=1000),
)
@settings(max_examples=10, deadline=None)
def test_fuzzing_extended_size_box(
    box_type: bytes,
    extended_size: int,
    box_data: bytes,
) -> None:
    """拡張サイズ（64 ビット）のボックスをテスト"""
    # size=1 は拡張サイズを使用することを示す
    size_bytes = (1).to_bytes(4, "big")
    extended_size_bytes = extended_size.to_bytes(8, "big")
    mp4_data = size_bytes + box_type + extended_size_bytes + box_data

    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(
    box_data=st.binary(min_size=0, max_size=5000),
)
@settings(max_examples=10, deadline=None)
def test_fuzzing_ftyp_with_random_body(box_data: bytes) -> None:
    """ftyp ボックスにランダムなボディを付けてテスト"""
    # ftyp ボックスの構造: size(4) + type(4) + major_brand(4) + minor_version(4) + compatible_brands(...)
    size = 8 + len(box_data)
    size_bytes = size.to_bytes(4, "big")
    mp4_data = size_bytes + b"ftyp" + box_data

    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(
    moov_data=st.binary(min_size=0, max_size=5000),
    mdat_data=st.binary(min_size=0, max_size=5000),
)
@settings(max_examples=10, deadline=None)
def test_fuzzing_ftyp_moov_mdat_structure(
    moov_data: bytes,
    mdat_data: bytes,
) -> None:
    """ftyp + moov + mdat 構造をテスト"""
    # 有効な ftyp
    ftyp = bytes(
        [
            0x00,
            0x00,
            0x00,
            0x14,  # size = 20
            0x66,
            0x74,
            0x79,
            0x70,  # "ftyp"
            0x69,
            0x73,
            0x6F,
            0x6D,  # major_brand = "isom"
            0x00,
            0x00,
            0x02,
            0x00,  # minor_version
            0x69,
            0x73,
            0x6F,
            0x6D,  # compatible_brand = "isom"
        ]
    )

    # ランダムな moov
    moov_size = (8 + len(moov_data)).to_bytes(4, "big")
    moov = moov_size + b"moov" + moov_data

    # ランダムな mdat
    mdat_size = (8 + len(mdat_data)).to_bytes(4, "big")
    mdat = mdat_size + b"mdat" + mdat_data

    mp4_data = ftyp + moov + mdat

    try:
        demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
        for sample in demuxer:
            _ = sample.data
    except (ValueError, RuntimeError, StopIteration):
        pass


@skip_fuzzing
@given(
    num_boxes=st.integers(min_value=1, max_value=10),
    data=st.data(),
)
@settings(max_examples=10, deadline=None)
def test_fuzzing_nested_boxes(num_boxes: int, data: st.DataObject) -> None:
    """ネストしたボックス構造をランダムに生成"""
    mp4_data = b""

    for _ in range(num_boxes):
        box_type = data.draw(st.binary(min_size=4, max_size=4))
        box_content = data.draw(st.binary(min_size=0, max_size=1000))
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
    sample_count=st.integers(min_value=1, max_value=10),
    data=st.data(),
)
@settings(max_examples=10, deadline=None)
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
            sample_data = data.draw(st.binary(min_size=1, max_size=5000))

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
