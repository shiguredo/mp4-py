"""
hypothesis を使った fuzzing テスト (PBT)

ランダムなデータを入力して、想定内の破損データ由来エラーは許容し、
想定外の例外はテスト失敗として検出することを確認する。
"""

import io

from hypothesis import given, settings
from hypothesis import strategies as st

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
)

# 破損データ由来で許容するエラーメッセージのホワイトリスト (小文字固定)。
# 照合時は str(e).lower() と比較する。ホワイトリスト外の RuntimeError は
# テスト失敗とする。
# パースエラーは RuntimeError として Python 側に届く (Demux のパースエラーを
# Python 側に報告する対応) ため、コア由来のパースエラーメッセージ
# (Failed to decode MP4 box / Sample table error) もホワイトリストに含める。
ALLOWED_ERROR_PATTERNS: list[str] = [
    "corrupted data",
    "too many iterations",
    "required input",
    "failed to read sample data",
    "failed to decode mp4 box",
    "sample table error",
]

# 有効な ftyp ボックス (size=20, major_brand="isom", compatible_brand="isom")
VALID_FTYP_BOX: bytes = bytes(
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


@given(data=st.binary(min_size=0, max_size=10000))
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_demuxer_random_bytes(data: bytes) -> None:
    """ランダムなバイナリデータを Demuxer に渡して想定外の例外が出ないことを確認"""
    demuxer = Mp4FileDemuxer(io.BytesIO(data))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(data=st.binary(min_size=0, max_size=10000))
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_demuxer_with_mp4_header(data: bytes) -> None:
    """MP4 ヘッダー付きのランダムデータを Demuxer に渡して想定外の例外が出ないことを確認"""
    mp4_data = VALID_FTYP_BOX + data

    demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
    try:
        for sample in demuxer:
            # sample.data は遅延読み込みのため、ここでアクセスして
            # データサイズ検証の例外 (Sample data size too large /
            # Failed to read sample data) を try の範囲で検出する
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(
    valid_mp4=st.binary(min_size=100, max_size=5000),
    corruption_offset=st.integers(min_value=0, max_value=9999),
    corruption_byte=st.integers(min_value=0, max_value=255),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_corrupted_mp4(
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

    demuxer = Mp4FileDemuxer(io.BytesIO(bytes(mp4_bytes)))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(
    box_type=st.binary(min_size=4, max_size=4),
    box_size=st.integers(min_value=0, max_value=0xFFFFFFFF),
    box_data=st.binary(min_size=0, max_size=5000),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_random_box_structure(
    box_type: bytes,
    box_size: int,
    box_data: bytes,
) -> None:
    """ランダムなボックス構造を生成してパースを試みる"""
    size_bytes = box_size.to_bytes(4, "big")
    mp4_data = size_bytes + box_type + box_data

    demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


# ボックスサイズの境界値
BOX_SIZE_BOUNDARY_VALUES = [
    0,  # サイズ 0（ファイル末尾まで）
    1,  # 不正なサイズ
    7,  # ヘッダより小さい
    8,  # 最小の有効なボックス（ヘッダのみ）
    9,  # ヘッダ + 1 バイト
    0xFFFFFFFF,  # 32 ビット size の最大値
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


@given(
    box_type=st.sampled_from(MP4_BOX_TYPES),
    box_size=st.sampled_from(BOX_SIZE_BOUNDARY_VALUES),
    box_data=st.binary(min_size=0, max_size=1000),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_box_size_boundaries(
    box_type: bytes,
    box_size: int,
    box_data: bytes,
) -> None:
    """ボックスサイズの境界値をテスト"""
    size_bytes = box_size.to_bytes(4, "big")
    mp4_data = size_bytes + box_type + box_data

    demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(
    box_type=st.sampled_from(MP4_BOX_TYPES),
    extended_size=st.integers(min_value=0, max_value=0xFFFFFFFFFFFFFFFF),
    box_data=st.binary(min_size=0, max_size=1000),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_extended_size_box(
    box_type: bytes,
    extended_size: int,
    box_data: bytes,
) -> None:
    """拡張サイズ（64 ビット）のボックスをテスト"""
    # size=1 は拡張サイズを使用することを示す
    size_bytes = (1).to_bytes(4, "big")
    extended_size_bytes = extended_size.to_bytes(8, "big")
    mp4_data = size_bytes + box_type + extended_size_bytes + box_data

    demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(
    box_data=st.binary(min_size=0, max_size=5000),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_ftyp_with_random_body(box_data: bytes) -> None:
    """ftyp ボックスにランダムなボディを付けてテスト"""
    # ftyp ボックスの構造: size(4) + type(4) + major_brand(4) + minor_version(4) + compatible_brands(...)
    size = 8 + len(box_data)
    size_bytes = size.to_bytes(4, "big")
    mp4_data = size_bytes + b"ftyp" + box_data

    demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(
    moov_data=st.binary(min_size=0, max_size=5000),
    mdat_data=st.binary(min_size=0, max_size=5000),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_ftyp_moov_mdat_structure(
    moov_data: bytes,
    mdat_data: bytes,
) -> None:
    """ftyp + moov + mdat 構造をテスト"""
    # ランダムな moov
    moov_size = (8 + len(moov_data)).to_bytes(4, "big")
    moov = moov_size + b"moov" + moov_data

    # ランダムな mdat
    mdat_size = (8 + len(mdat_data)).to_bytes(4, "big")
    mdat = mdat_size + b"mdat" + mdat_data

    mp4_data = VALID_FTYP_BOX + moov + mdat

    demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(
    num_boxes=st.integers(min_value=1, max_value=10),
    data=st.data(),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_nested_boxes(num_boxes: int, data: st.DataObject) -> None:
    """ネストしたボックス構造をランダムに生成"""
    mp4_data = b""

    for _ in range(num_boxes):
        box_type = data.draw(st.binary(min_size=4, max_size=4))
        box_content = data.draw(st.binary(min_size=0, max_size=1000))
        box_size = 8 + len(box_content)
        size_bytes = box_size.to_bytes(4, "big")
        mp4_data += size_bytes + box_type + box_content

    demuxer = Mp4FileDemuxer(io.BytesIO(mp4_data))
    try:
        for sample in demuxer:
            _ = sample.data
    except RuntimeError as e:
        assert any(p in str(e).lower() for p in ALLOWED_ERROR_PATTERNS), (
            f"予期しないエラーメッセージ: {e}"
        )


@given(
    sample_count=st.integers(min_value=1, max_value=10),
    data=st.data(),
)
@settings(max_examples=1000, deadline=None)
def prop_fuzzing_muxer_random_data(sample_count: int, data: st.DataObject) -> None:
    """Muxer にランダムなサンプルデータを渡して有効入力で例外が出ないことを確認"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # timescale はテスト全体で 1 回だけ生成し、全サンプルで共通使用する
    # (サンプル間で timescale が異なると muxer が Timescale mismatch で失敗するため)
    timescale = data.draw(st.integers(min_value=1, max_value=1000000))

    for i in range(sample_count):
        sample_entry = Mp4SampleEntryVp08(
            width=data.draw(st.integers(min_value=1, max_value=4096)),
            height=data.draw(st.integers(min_value=1, max_value=4096)),
        )
        sample_data = data.draw(st.binary(min_size=1, max_size=5000))

        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            # 先頭サンプルは必ず keyframe にする (sync samples が必要なため)
            keyframe=(i == 0) or data.draw(st.booleans()),
            timescale=timescale,
            duration=data.draw(st.integers(min_value=1, max_value=1000000)),
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demuxed = list(demuxer)
    assert len(demuxed) == sample_count, (
        f"demux したサンプル数が一致すること (実際: {len(demuxed)})"
    )
