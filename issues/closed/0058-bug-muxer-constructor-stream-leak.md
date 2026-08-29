# Mp4FileMuxer コンストラクタ失敗時に開いたストリームがリークする

- Created: 2026-08-19
- Completed: 2026-08-29
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

## 不要と判断した理由 (closed)

closed 0032 と同一テーマ (`Mp4FileMuxer::new` のエラーパスでのストリームリーク) であり、0032 で実測検証により「バグは存在しない」と判断済み。本 issue は 0032 closed の 4 日後に一括起票された重複で、0032 への言及がないまま同じ前提を主張している。polish-issue 本審の 2 系統のレビューが独立に再検証し、同じ結論になったため重複として closed にする。

- 0032 closed (2026-08-15) 後に `Mp4FileMuxer::new` 周辺の実装変更はなく (`git log -L` と `git log -S should_close` で確認)、リーク経路が新たに生まれていない
- 理由: エラー伝播時にローカル変数 `stream: Py<PyAny>` が drop され、唯一の参照が消えるため CPython の refcount が 0 になり、即時 dealloc → close される (GC 待ちではない)
- 再検証: options 変換失敗 (不正な language code) のエラー経路を 200 回 / 1000 回連続実行しても fd 数は不変で、リークの累積なし。対照として正常系で muxer を保持した場合は fd が +1 することも確認済み
- `ResourceWarning` が dealloc 時の close の証拠として記録される (GC 待ちなら fd が残り続ける)
- 完了条件の「fd リークしないことを検証するテスト」はリークが存在しないため修正前から通る。fd 数の計測は Linux / macOS のみで Windows は `/proc/self/fd` / `/dev/fd` 相当がなく、環境依存の不安定なテストになる
- 補足: コンストラクタ失敗時に 0 バイトの空ファイルがディスクに残る点は fd リークとは別の性質の問題であり、本 issue の完了条件には含まれない。対処が必要なら別 issue として起票すること
