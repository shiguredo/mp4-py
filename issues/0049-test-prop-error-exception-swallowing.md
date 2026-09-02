# prop_error.py の 2 テストが例外を握りつぶしたまま残っている

- Created: 2026-08-16
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-prop-error-exception-swallowing
- Polished: 2026-09-02
- Milestone: 2026.2.0

## 目的

`tests/prop_error.py` の `prop_demuxer_handles_garbage_data` と `prop_demuxer_handles_truncated_mp4` が `except RuntimeError: pass` で例外を握りつぶしたままである状態を解消する。fuzzing テストの例外握りつぶし解消 (0017) の取りこぼしであり、CODEBASE.md の「明確な理由がない限りは try/except をテストでは利用しないこと」に違反したまま残っている。

## 現状

`tests/prop_error.py` の 2 テストが `except RuntimeError: pass` で例外を握りつぶしている:

- `prop_demuxer_handles_garbage_data` (ランダムデータを Demuxer に渡す)
- `prop_demuxer_handles_truncated_mp4` (不完全な MP4 データを Demuxer に渡す)

0017 で解消した `prop_fuzzing.py` と同じ問題が残っている。0017 の実装で確立した方式 (破損データ由来メッセージのホワイトリスト assert) を適用すれば、想定外の RuntimeError を検出できるようになる。

なお、0036 の実装後、パースエラー (DecodeError / SampleTableError / InvalidState) は `src/lib.rs` の `__next__` / `ensure_tracks` で `RuntimeError` (`mp4 error: ...` 形式) として Python 側に報告される。`feed_required_input` のエラー (`too many iterations` / `Required input ... too large`) と `sample.data` アクセス時のサイズ検証エラー (`Sample data size too large`) は `Mp4Exception` (RuntimeError 派生) として届く。したがって、この 2 テストにホワイトリスト assert を適用すれば、想定外の例外を検出できる。

## 設計方針

- `prop_fuzzing.py` の `ALLOWED_ERROR_PATTERNS` と同じホワイトリスト assert 方式に統一する
- ホワイトリストは二重定義を避けるため `prop_fuzzing.py` から import する (共通モジュール化は prop_fuzzing.py の変更も伴うため行わない)
- moov 発見前に EOF に達する経路はエラーにならず空リスト (トラック 0 本の正常終了) になるため、従来どおり許容する (0036 で確定した仕様)

## 完了条件

- `tests/prop_error.py` の 2 テストから `except RuntimeError: pass` がなくなる
- 想定外の RuntimeError が飛んだらテスト失敗になる (ホワイトリスト assert)
- 全テスト通過

## 解決方法

1. `prop_fuzzing.py` の `ALLOWED_ERROR_PATTERNS` を import する (二重定義しない)
2. 2 テストの try/except をホワイトリスト assert に書き換える (`sample.data` アクセスも try の範囲に含める)
3. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
4. CHANGES.md の `### misc` にエントリを追記する
