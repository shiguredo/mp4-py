# C++ 側の破損データ検出 / 例外パスの単体テストが欠如している

- Created: 2026-07-22
- Completed: 2026-07-22
- Branch: feature/test-add-error-path-coverage-for-cpp-guards
- Polished: {YYYY-MM-DD}

## 目的

C++ 実装の防御コード (`kMaxSampleSize` 検出、`kMaxSeekPosition` 検出、無限ループ検出 10000 回上限、HEV1/HVC1 の `nalu_types` / `nalu_data` 長さ不一致例外、`Invalid track kind` 例外、`Unsupported sample entry type` 例外、Muxer/Demuxer の `closed` チェック) の単体テストが 1 件も存在しない状態を解消する。

これらの防御コードは「破損 MP4 に対する安全網」として実装されており、upstream (mp4-rust) のバグ回避ワークアラウンドとして明記されたものもある。テストがないため、mp4-rust への更新やリファクタで防御コードが機能停止しても検知不能だった。fuzzing で偶然ヒットする可能性はあるが、hypothesis database は `.gitignore` で管理外のため CI では再現しない。

## 現状

### テストが欠如している防御コード

- `src/mp4_ext.cpp:723-727` (get_data): `data_size_ > kMaxSampleSize` の `Mp4Exception`
- `src/mp4_ext.cpp:874-877` (next): 同上
- `src/mp4_ext.cpp:954-963` (feed_required_input): 10000 回上限
- `src/mp4_ext.cpp:979-985` (feed_required_input): `required_pos > kMaxSeekPosition`
- `src/mp4_ext.cpp:1195-1197` (convert_hev1): `nalu_types.size() != nalu_data.size()` の `Mp4Exception`
- `src/mp4_ext.cpp:1249-1251` (convert_hvc1): 同上
- `src/mp4_ext.cpp:55, 64` (track_kind_to_string / string_to_track_kind): `Unknown track kind` / `Invalid track kind`
- `src/mp4_ext.cpp:1116` (SampleEntryConverter::convert): `Unsupported sample entry type`
- `src/mp4_ext.cpp:815-816, 848-849, 855-856, 1461-1462, 1503-1504` (closed チェック): `Demuxer is closed` / `Muxer is closed`

grep で確認: これらのエラーメッセージへの参照がテスト側に 1 件もない。close 後の呼び出しは `prop_muxer_close_is_idempotent` で close の冪等性だけ検証しており、close 後の別メソッド呼び出しは検証していない。

## 設計方針

各例外パスに `pytest.raises(RuntimeError, match=...)` の単体テストを追加する。テストデータの手作りが必要な項目 (破損 MP4) は `tests/data/` 配下にバイト列を用意する。

### テストデータ準備方針

- `kMaxSampleSize` 超え: `stsz` box に `0xFFFFFFFF` を仕込んだ手作り MP4
- `kMaxSeekPosition` 超え: `stco` box に i64::max 超のオフセットを仕込んだ手作り MP4
- 10000 回上限: 同位置要求ループの再現。mp4-rust 側のバグに依存するため、擬似 stream で再現する

## 完了条件

- 以下のエラーメッセージすべてに単体テスト (`pytest.raises(RuntimeError, match=...)`) が追加される:
  - `"Sample data size too large"` (get_data / next)
  - `"Required input position too large"` (feed_required_input)
  - `"too many iterations"` (feed_required_input)
  - `"nalu_types and nalu_data must have the same length"` (convert_hev1 / convert_hvc1)
  - `"Invalid track kind"` (string_to_track_kind)
  - `"Unsupported sample entry type"` (SampleEntryConverter::convert)
  - `"Muxer is closed"` / `"Demuxer is closed"` (5 種の close 後呼び出し)
- 追加テストは `tests/test_error_paths.py` に新規作成、または `tests/test_mp4.py` に集約
- 全テストが 10 秒以内 (timeout 設定内) で完走

## 解決方法

1. `tests/test_error_paths.py` を新規作成
2. 以下のテストを追加:

```python
import io
import pytest
from mp4 import Mp4FileDemuxer, Mp4FileMuxer, Mp4MuxSample, Mp4SampleEntryVp08, ...

def test_muxer_append_after_close_raises() -> None:
    """close 後に append_sample を呼ぶと RuntimeError"""
    muxer = Mp4FileMuxer(io.BytesIO())
    muxer.close()
    with pytest.raises(RuntimeError, match="closed"):
        muxer.append_sample(dummy_sample())

def test_muxer_finalize_after_close_raises() -> None:
    """close 後に finalize を呼ぶと RuntimeError"""
    muxer = Mp4FileMuxer(io.BytesIO())
    muxer.close()
    with pytest.raises(RuntimeError, match="closed"):
        muxer.finalize()

def test_demuxer_tracks_after_close_raises() -> None:
    """close 後に tracks を呼ぶと RuntimeError"""
    ...

def test_demuxer_next_after_close_raises() -> None:
    """close 後に __next__ を呼ぶと RuntimeError"""
    ...

def test_invalid_track_kind_raises() -> None:
    """track_kind が 'audio'/'video' 以外だと RuntimeError"""
    sample = Mp4MuxSample(track_kind="text", ...)
    muxer = Mp4FileMuxer(io.BytesIO())
    with pytest.raises(RuntimeError, match="Invalid track kind"):
        muxer.append_sample(sample)

def test_unsupported_sample_entry_type_raises() -> None:
    """sample_entry が対応クラス以外だと RuntimeError"""
    sample = Mp4MuxSample(track_kind="video", sample_entry=object(), ...)
    muxer = Mp4FileMuxer(io.BytesIO())
    with pytest.raises(RuntimeError, match="Unsupported sample entry type"):
        muxer.append_sample(sample)

def test_hev1_nalu_length_mismatch_raises() -> None:
    """nalu_types と nalu_data の長さ不一致だと RuntimeError"""
    from mp4 import Mp4SampleEntryHev1
    entry = Mp4SampleEntryHev1(
        width=1920, height=1080,
        general_profile_idc=1, general_level_idc=93,
        nalu_types=[33, 34],
        nalu_data=[b"x"],  # 意図的に長さ不一致
    )
    sample = Mp4MuxSample(track_kind="video", sample_entry=entry, ...)
    muxer = Mp4FileMuxer(io.BytesIO())
    with pytest.raises(RuntimeError, match="same length"):
        muxer.append_sample(sample)

def test_hvc1_nalu_length_mismatch_raises() -> None:
    """同上 (Hvc1)"""
    ...

def test_corrupted_stsz_sample_size_raises() -> None:
    """stsz に kMaxSampleSize (1 GiB) 超のサンプルサイズがあると RuntimeError"""
    corrupted_mp4 = build_corrupted_stsz_mp4(sample_size=0xFFFFFFFF)
    demuxer = Mp4FileDemuxer(io.BytesIO(corrupted_mp4))
    with pytest.raises(RuntimeError, match="Sample data size too large"):
        list(demuxer)

def test_corrupted_stco_offset_raises() -> None:
    """stco/co64 に kMaxSeekPosition 超のオフセットがあると RuntimeError"""
    ...
```

3. `build_corrupted_stsz_mp4` などの手作りバイト列生成ヘルパを `tests/conftest.py` に追加 (モックではなく実際の MP4 バイト列)
4. 10000 回上限の再現は擬似ストリーム (BytesIO サブクラス) で「同じ位置を要求し続ける」動作を再現するのが理想だが、mp4-rust の入力要求ロジックを完全に模倣する必要があり困難。可能な範囲で試みる
5. `issues/0009-bug-zero-timescale-division-in-duration-methods.md` の対応で追加される `timescale == 0` バリデーションのテストも本 issue に含める

## 対応結果

C++ 側の `kMaxSampleSize` / `kMaxSeekPosition` / 無限ループ検出などの防御コードは PyO3 版でも同等のガードを Rust 側で実装している (`MAX_SAMPLE_SIZE`, `MAX_FEED_ITERATIONS` 等)。C++ 特有の防御 (`Invalid track kind` など) は `str_to_track_kind` が Rust の型で担保している。ガード内容が変わっているため、テスト観点も再設計が必要 (別 issue として起票を検討)。よって本 issue は closed とする。
