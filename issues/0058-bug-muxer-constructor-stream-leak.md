# Mp4FileMuxer コンストラクタ失敗時に開いたストリームがリークする

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-muxer-constructor-stream-leak
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

`Mp4FileMuxer` をファイルパスで構築する際、`CoreMuxer::with_options` の失敗や初期ボックス書き出しの失敗時に、開いたファイルハンドルが閉じられずリークする問題を解消する。

## 現状

`src/lib.rs` の `Mp4FileMuxer::new` は、パス入力 (`os.PathLike` または `str`) を `open(path, "wb")` で開いた後、以下の失敗経路でハンドルを閉じずにエラーを返す:

- `CoreMuxer::with_options(core_options)` の失敗
- `stream.write(initial_boxes_bytes())` の失敗

`close()` はオブジェクト構築後にしか動作しないため、コンストラクタ段階の失敗では開いたハンドルが GC まで解放されず、ファイルディスクリプタがリークする。Windows ではさらに削除済みファイルに対する書き込みエラー等、リソースのロックが続く可能性がある。

## 設計方針

- コンストラクタ内で `open` した後に失敗した場合、開いたストリームを明示的に閉じる
- エラー伝播前にハンドルを閉じる (RAII パターンまたは明示的な close 呼び出し)

## 完了条件

- コンストラクタ失敗時に開いたファイルハンドルが閉じられる
- ファイルディスクリプタがリークしないことを検証するテストが追加されている
- 既存テストが全通過する
