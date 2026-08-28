# Mp4FileMuxer::new のエラーパスで開いたストリームがリークする

- Created: 2026-08-15
- Completed: 2026-08-15
- Branch: feature/fix-muxer-new-stream-leak
- Polished: {YYYY-MM-DD}

## 目的

`Mp4FileMuxer::new` をファイルパス指定で呼び出したとき、内部で `builtins.open()` したストリームがエラーパスで閉じられずリークする問題を解消する。

## 現状

`src/lib.rs` の `Mp4FileMuxer::new` は:

1. `is_pathlike` 判定で path なら `builtins.open(destination, "wb")` して `should_close = true`
2. `options` を `CoreMuxerOptions` に変換 (不正な language code 等で `PyValueError` になりうる)
3. `CoreMuxer::with_options` の呼び出し (失敗しうる)
4. `stream.write(initial_boxes_bytes())` の呼び出し (失敗しうる)

2〜4 のいずれかで `?` によりエラーが伝播すると、1 で開いたファイルストリームが閉じられず残る。`should_close_stream` が true のままオブジェクト自体も破棄されるため、ファイルハンドルが GC まで開き続ける。

既存テストは全て `io.BytesIO` を渡すため (`should_close = false`)、この経路を検出できない。`Mp4FileDemuxer::new` も同構造 (`builtins.open(source, "rb")`) のため同様の問題を持つ。

## 設計方針

- エラーパスで `should_close` が true なら、エラーを返す前に開いたストリームを閉じる
- クローズ処理自体が失敗しても、元のエラーを優先して返す

## 完了条件

- 不正な options (例: 大文字の language code) で `Mp4FileMuxer(path)` を呼ぶと例外が発生し、開いたファイルストリームが閉じられる
- 正常系は従来どおり動作する
- テストで「エラー後にストリームが閉じられている」ことを検証する

## 解決方法

1. `src/lib.rs` の `Mp4FileMuxer::new` で、options 変換以降のエラー時に `should_close` が true なら `stream.close()` を呼んでからエラーを返すように変更する (クロージャまたは drop ガードで実装)
2. `Mp4FileDemuxer::new` も同様に修正する
3. `tests/test_mp4.py` に「不正な options でパス指定 muxer を構築すると例外になり、内部で開かれたストリームが閉じられる」ことを検証するテストを追加する (一時ファイルを使用)
4. `NO_UV_SYNC=1 uv run pytest tests/` で全テスト通過を確認する

## 不要と判断した理由 (closed)

polish-issue での実測検証により、本 issue が報告するバグは存在しないと判断した。

- エラーパスを 100 回連続で実行しても fd 数は不変 (4 → 4) で、リークの累積なし
- 理由: エラー時に `stream: Py<PyAny>` のローカル変数が Rust の巻き戻しで drop され、唯一の参照が消えるため CPython の refcount が 0 になり、即時 dealloc → close される (GC 待ちではない)
- `Mp4FileDemuxer::new` は open 後に失敗しうる操作が存在しないため、リークするエラーパスが構造的に存在しない
- closed 0001 の「コンストラクタ途中失敗時のリソース解放は所有権システムで保証される」という判断と整合する
