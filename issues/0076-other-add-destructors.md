# Mp4FileMuxer / Mp4FileDemuxer に __del__ 相当の後始末がない

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-add-destructors
- Polished: {YYYY-MM-DD}

## 目的

`Mp4FileMuxer` / `Mp4FileDemuxer` の close を忘れた場合に、開いたファイルハンドルが GC まで解放されずリソースリークする可能性を解消する。with 構文では問題ないが、close を呼び忘れた利用者へのセーフティネットを検討する。

## 現状

`src/lib.rs` の Mp4FileMuxer / Mp4FileDemuxer には `__exit__` (with 構文) はあるが、`__del__` / Drop 相当の後始末がない。`should_close_stream = true` のストリーム (ファイルパスから open した場合) は、close を呼び忘れると GC までファイルが開き続ける。

Muxer は finalize を実行しないまま GC されると、破損した不完全なファイルが書き出されたまま残るリスクもある。

## 設計方針

- `__del__` を追加するか、GC 時の後始末の設計を検討する
- Muxer の GC 時 finalize の自動実行は危険 (ユーザーが意図的に破棄したいケースもある。非 seekable ストリームの失敗時は「close せずに破棄」が推奨されている) ため、デストラクタで自動 finalize するかは設計判断が必要
- 少なくとも、開いたストリームの close は保証する

## 完了条件

- close を呼び忘れた場合のリソースリークが解消される
- 既存の推奨使用方法 (失敗時は close せず破棄) と矛盾しない
- 既存テストが全通過する
