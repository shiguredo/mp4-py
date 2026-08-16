# extract_bytes が int などの型ミスを静かにゼロ埋めバイト列に変換する

- Priority: Medium
- Created: 2026-08-15
- Completed: 2026-08-16
- Model: Opus 4.7
- Branch: feature/fix-extract-bytes-silently-converts-int
- Polished: 2026-08-15

## 目的

`Mp4MuxSample(data=...)` などに `int` を渡した場合に、エラーにならず「その値の長さのゼロ埋めバイト列」として静かに書き込まれる問題を解消する。型ミスによるデータ破壊をエラーとして検出できるようにする。

## 優先度根拠

Medium。

- 型ミスがエラーにならず、静かに不正なデータが書き込まれる (データ破壊)
- `data=2**30` のような巨大な int では 1GB 規模のゼロ埋めバッファが確保され、メモリ消費につながる (DoS 的側面)
- 修正コストは小 (フォールバック前の型チェック追加 + テスト)

## 現状

`src/lib.rs` の `extract_bytes` は:

1. `PyBytes` へのキャスト (高速パス)
2. `PyBuffer` 経由 (bytearray / memoryview 等)
3. 最終フォールバック: `builtins.bytes(obj)` を呼ぶ

3 のフォールバックは Python の `bytes(12345)` が `b"\x00" * 12345` を返す仕様をそのまま通すため、`data=12345` のような型ミスが 12345 バイトのゼロデータとして書き込まれる (エラーにならない)。`bytes(True)` も `b"\x00"` (1 バイトのゼロ列) になり、`bool` も同様に静かに変換される。`bytes(1.5)` は `TypeError` になるため `float` は対象外。`bytes("abc")` も `TypeError` になる。

`adopt_or_copy_bytes` も同じ経路を使うため、`Mp4MuxSample(data=...)` に影響する。`bytes([1,2,3])` は `b'\x01\x02\x03'` になり、`list[int]` は意図されたフォールバック (コメントにも「list[int] 等」と明記)。

`extract_bytes` は `Mp4MuxSample::new` の `data` 以外にも、`Mp4SampleEntryAv01::new` の `config_obus` / `Mp4SampleEntryMp4a::new` の `dec_specific_info` / `Mp4SampleEntryFlac::new` の `streaminfo_data`、および `extract_bytes_list` 経由で `Mp4SampleEntryAvc1` の `sps_data` / `pps_data` と `Mp4SampleEntryHev1` / `Hvc1` の `nalu_data` で使われる。修正は `extract_bytes` 集中型なので全経路に自動的に適用される。

## 設計方針

- フォールバックの前に、`int` / `bool` などバイト列として意図されないスカラー型を明示的に `TypeError` にする (標準のスカラー型で実際に静かに変換されるのは `int` / `bool`。`float` と `str` は `bytes()` が既に `TypeError` を返すためチェック不要。`__bytes__` / `__index__` を持つユーザー定義型は型ミスとは区別できるため対象外)
- フォールバック自体は `list[int]` (0-255) など Python の bytes コンストラクタが受け付ける型のために残す
- エラーメッセージは英語で、期待する型 (bytes / bytearray / memoryview、または 0-255 の int の iterable) を含める

## 完了条件

- `Mp4MuxSample(data=12345)` で `TypeError` が発生する
- `data=True` でも `TypeError` が発生する
- `data=b"..."` / `data=bytearray(...)` / `data=memoryview(...)` / `data=[1,2,3]` は従来どおり動作する
- 追加テストで「int が TypeError になる」「list[int] は動作する」ことを検証する

## 解決方法

1. `src/lib.rs` の `extract_bytes` のフォールバック前に `is_instance_of::<PyInt>()` の型チェックを追加し、int / bool (bool は int のサブクラス) を `TypeError` にした
   - エラーメッセージは英語で期待する型 (bytes / bytearray / memoryview、または 0-255 の int の iterable) と実際の型名を含む
   - コメントに `bytes(12345)` が `b"\x00" * 12345` を返す仕様と、float / str は `bytes()` が元々 TypeError を返すためチェック不要な理由を明記した
   - `list[int]` フォールバックは維持した
2. `tests/test_mp4.py` に 3 テストを追加した:
   - `test_mux_sample_rejects_int_data`: `Mp4MuxSample(data=12345)` / `data=True` が TypeError になることを検証
   - `test_mux_sample_accepts_bytes_like_data`: `data=[1,2,3]` / `data=bytearray(...)` / `data=memoryview(...)` が従来どおり動作することを検証 (list[int] フォールバックと buffer protocol 経路の回帰防止)
   - `test_extract_bytes_rejects_int_in_sample_entries`: `config_obus=12345` / `dec_specific_info=12345` / `streaminfo_data=12345` / `sps_data=[12345]` / `nalu_data=[12345]` が TypeError になることを検証 (extract_bytes / extract_bytes_list 経路)
3. CHANGES.md の `## develop` に「[FIX] extract_bytes が int / bool を静かにゼロ埋めバイト列に変換しないようにする」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
4. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (118 passed, 7 skipped) を確認した
