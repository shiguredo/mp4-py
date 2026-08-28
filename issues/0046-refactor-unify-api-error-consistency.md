# API のエラーハンドリング一貫性とコード整理を改善する

- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Branch: feature/refactor-unify-api-error-consistency
- Polished: 2026-08-15

## 目的

`src/lib.rs` の公開 API に残るエラーハンドリングの非対称性と読みにくい実装を改善し、利用者が予測しやすい挙動に統一する。Muxer の finalize 後の中間状態の対処は、finalize 後の append_sample のロールバック破壊の修正 (0029) から委譲された項目である。利用者に見える挙動変更を含むが、通常の使用経路では発生しないエッジケースの改善に留める。その他のバグ修正は各 issue で行い、本 issue は一貫性の改善に絞る。

## 現状

### エラーハンドリングの非対称性

- `Mp4FileDemuxer` の close 済み `__next__` が `StopIteration` を返す (閉じた後のイテレーションが正常終了と区別不能) に対し、`Mp4FileMuxer` の close 済み `append_sample` は `RuntimeError("muxer is closed")` を返す。なお Demuxer の `tracks` getter は既に `demuxer is closed` を返しており、Demuxer 内部でも非対称
- `Mp4DemuxSample.data` の getter が `seek` 未実装のストリームで生の `AttributeError` を伝播する。Muxer 側は `rollback_append` 内で `seekable()` チェックにより `RuntimeError("stream is not seekable")` に変換している (これは write 失敗後のエラーパスのみで、事前チェックではない)。Demuxer 側には同様の変換がない。なお非 seekable ストリームを `Mp4FileDemuxer` に渡した場合、最初の seek は `feed_required_input` で発生し、`tracks` / `__next__` 呼び出し時に `AttributeError` になる (sample.data 経路に到達するのは直接構築の場合のみ)
- `Mp4FileMuxer::finalize_locked` は `core.finalize()` 成功後にストリームへの seek / write が失敗すると、`state.finalized` が false のままコア側は finalize 済みになり、以後 `finalize()` / `close()` が `AlreadyFinalized` で失敗し続ける中間状態で固定される (finalize 後の append_sample のロールバック破壊の修正 (0029) から委譲された項目)

### 読みにくい実装

- `Mp4FileDemuxer::__next__` の `NextSampleExtracted` 8 要素タプルはフィールドの意味がコメントでしか分からず、展開部も読みにくい。struct 化が望ましい
- `Mp4FileDemuxer::new` は `PyBytes` / pathlike / ストリームの 3 分岐で、`bytearray` / `memoryview` を渡すとストリーム扱いになり、seek がない旨の不明瞭なエラーになる (`extract_bytes` が buffer protocol 対応しているのと非対称)
- `Mp4SampleEntryVp08` / `Mp4SampleEntryVp09` の `to_sample_entry` / `from_box` がほぼ同一の手書き重複 (Hev1 / Hvc1 は共通 struct + マクロで共通化済み)
- `Mp4SampleEntry*` の `__repr__` が一部のクラス (Vp08 / Stpp / Wvtt / Tx3g) にのみ実装され、表示内容もクラスごとに異なる (引数と導出値の混在)

### コンストラクタ検証の不整合

- `Mp4MuxSample::new` は `timescale=0` を検証せず、`append_sample` までエラーが遅延される。`Mp4TrackInfo::new` は new 時点で `PyValueError` にするため不整合。検証を new に移すと、timescale=0 を失敗トリガーに使う既存テスト 3 件 (`test_append_sample_rollback_on_error` / `test_append_sample_retry_after_rollback` / `test_append_sample_rollback_failure_message`) の書き換えが必要になる (代替トリガー: `sample_entry=None` によるコアの `MissingSampleEntry`。既存の `test_append_sample_core_error_rollback_and_retry` が使用)

## 設計方針

- エラーの型とタイミングを Muxer / Demuxer で対称にする (close 済みのエラーは `RuntimeError`、非 seekable のエラーは `RuntimeError("stream is not seekable")` 相当)
- 非 seekable ストリームのガードは、`feed_required_input` と `Mp4DemuxSample.data` の両方の seek 呼び出しを対象にする (seek 呼び出しの失敗を明示的なエラーに変換する形。変換対象は seek 未実装由来の失敗 (AttributeError / UnsupportedOperation) に限定し、閉じたストリーム等の ValueError は誤変換しない)
- `finalize_locked` の中間状態は「書き込み失敗で finalize 済み扱いにする」方針を採らない (以後の `finalize()` が無言で成功を返し、部分書き込みで破損したファイルを成功扱いするため)。ストリーム書き込み失敗時は、`state.core` を drop して Muxer を使用不能にし、破棄を促すメッセージ付きのエラーを返す (core の drop により、以後の `append_sample` は write 実行前に「muxer already dropped」で止まり、finalize 失敗後のロールバック破壊 (0029 が修正した経路) を別経路で再発させない。コア API による retry 設計は行わない)
- タプルは struct に置き換える
- Vp08 / Vp09 の共通化は共通 struct (HevcCommon と同様の方式) で行い、マクロは追加しない (shiguredo-rust スキルのマクロ禁止規約)
- 挙動変更 (close 済み `__next__` のエラー化、非 seekable のエラー化、`Mp4FileDemuxer` の bytearray / memoryview 受理、timescale=0 の早期検証、finalize 書き込み失敗後の使用不能化) には、それぞれ回帰テストを追加する
- 新設するエラーは `RuntimeError` のままとする (カスタム例外への型分類は別 issue のスコープ)

## 完了条件

- close 済み Demuxer のイテレーションが `RuntimeError` として報告される
- 非 seekable ストリームの Demux (feed 経路・sample.data 経路の両方) が明確なエラーメッセージになる
- `finalize_locked` のストリーム書き込み失敗時に、Muxer が使用不能として破棄を促すメッセージ付きのエラーを返し、以後の `append_sample` が write 前に止まる (ロールバック破壊を再発させない)
- `NextSampleExtracted` が struct になる
- `Mp4FileDemuxer::new` が bytearray / memoryview を受理する
- Vp08 / Vp09 の変換コードが共通 struct で共通化される
- `__repr__` の実装有無と形式が統一される
- `Mp4MuxSample::new` が `timescale=0` を `ValueError` で弾く
- 挙動変更に対する回帰テストが追加される (close 済みイテレーションのエラー化、非 seekable のエラー化、bytearray / memoryview 受理、timescale=0 の早期検証、finalize 書き込み失敗後の使用不能化)
- 影響を受ける既存テストが調整される (timescale=0 トリガーの 3 テストは代替トリガーへ書き換え)
- CHANGES.md に追記される
- 全テストが通過する

## 解決方法

1. `src/lib.rs` の `Mp4FileDemuxer::__next__` の close 済みチェックを `RuntimeError("demuxer is closed")` に変更する (0036 の設計原則「StopIteration は常に正常終了のみを意味し、エラーは例外で伝える」と方向が一致する。0036 は `Err(_)` アーム、本項目は close 済みアームで変更箇所が異なる)
2. `feed_required_input` と `Mp4DemuxSample.data` の seek 呼び出しの失敗を、明示的なエラー (`RuntimeError("stream is not seekable")` 相当) に変換する
3. `finalize_locked` のストリーム書き込み失敗時は、`state.core` を drop して Muxer を使用不能にし、破棄を促すメッセージ付きのエラーを返す (0029 から委譲された項目。core の drop により以後の `append_sample` は write 前に「muxer already dropped」で止まり、ロールバック破壊を再発させない。なお 0030 (SampleEntry 値域検証) は `Mp4SampleEntryVp08::new` / `Mp4SampleEntryVp09::new` を変更するため、本 issue の共通 struct 化 (解決方法 6) と同一関数を編集する。実装順序はどちらを先にしてもよいが、両方の変更をマージする際に調整が必要な場合がある)
4. `NextSampleExtracted` を struct 化する
5. `Mp4FileDemuxer::new` に bytearray / memoryview 対応を追加する (受理範囲は bytes-like (buffer protocol) に限定し、`extract_bytes` のフォールバック (list[int] 等) までは含めない)
6. Vp08 / Vp09 の変換コードを共通 struct で共通化し、`__repr__` の実装有無と形式を統一する (SampleEntry 系は全クラスに実装する)
7. `Mp4MuxSample::new` で `timescale=0` を検証する (`PyValueError`)。`append_sample` 内の `NonZeroU32` チェックは防御として残す
8. 上記の挙動変更に対する回帰テストを `tests/test_mp4.py` に追加し、timescale=0 をトリガーに使う既存テスト 3 件を代替トリガー (`sample_entry=None` による `MissingSampleEntry`) へ書き換える (finalize 書き込み失敗の再現は、後方 seek 不可のストリーム (例: gzip.GzipFile) で行う。既存の `test_append_sample_rollback_failure_message` と同じ手法)
9. CHANGES.md に追記する (挙動変更は種別に分けて記載: close 済みイテレーションのエラー化は [CHANGE]、bytearray / memoryview 受理は [ADD]、内部整理は `### misc`。shiguredo-changelog スキルの形式に従う)
10. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
