# prop_error.py の 2 テストが例外を握りつぶしたまま残っている

- Created: 2026-08-16
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-prop-error-exception-swallowing
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

`tests/prop_error.py` の `prop_demuxer_handles_garbage_data` と `prop_demuxer_handles_truncated_mp4` が `except RuntimeError: pass` で例外を握りつぶしたままである状態を解消する。fuzzing テストの例外握りつぶし解消 (0017) の取りこぼしであり、CODEBASE.md の「明確な理由がない限りは try/except をテストでは利用しないこと」に違反したまま残っている。

## 現状

`tests/prop_error.py` の 2 テストが `except RuntimeError: pass` で例外を握りつぶしている:

- `prop_demuxer_handles_garbage_data` (ランダムデータを Demuxer に渡す)
- `prop_demuxer_handles_truncated_mp4` (不完全な MP4 データを Demuxer に渡す)

0017 で解消した `prop_fuzzing.py` と同じ問題が残っている。0017 の実装で確立した方式 (破損データ由来メッセージのホワイトリスト assert) を適用すれば、想定外の RuntimeError を検出できるようになる。

なお、demux のパースエラーはバインディング層 (`src/lib.rs` の `__next__`) で `PyStopIteration` に変換され Python 側に届かないことが多いため、実際に発火するのは主に `sample.data` アクセス時のサイズ検証エラーである (0017 の実装で実測済み)。エラー隠蔽の解消自体は 0036 のスコープ。

## 設計方針

- `prop_fuzzing.py` の `ALLOWED_ERROR_PATTERNS` と同じホワイトリスト assert 方式に統一する
- ホワイトリストは重複を避けるため `prop_fuzzing.py` から import するか、共通モジュールへ移動するかを検討する (両ファイルで同じ定数を二重定義しないこと)
- パース失敗で空リストになる経路 (エラーではなく空結果) は従来どおり許容する (0036 の実装後に見直す)

## 完了条件

- `tests/prop_error.py` の 2 テストから `except RuntimeError: pass` がなくなる
- 想定外の RuntimeError が飛んだらテスト失敗になる (ホワイトリスト assert)
- 全テスト通過

## 解決方法

1. `prop_fuzzing.py` のホワイトリスト定数を共通化する (import または共通モジュール化。二重定義しない)
2. 2 テストの try/except をホワイトリスト assert に書き換える
3. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
4. CHANGES.md の `### misc` にエントリを追記する
