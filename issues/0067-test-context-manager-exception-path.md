# コンテキストマネージャの例外経路テストを追加する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/test-context-manager-exception-path
- Polished: {YYYY-MM-DD}

## 目的

`with` 構文の例外発生時における `__exit__` の挙動 (`close()` が finalize を実行し破損ファイルを書き出す) をテストで固定する。Muxer のドキュメント (src/lib.rs の Mp4FileMuxer) が注意喚起しているが、テストで検証されていないため、挙動の変更・回帰を検出できるようにする。

## 現状

- `tests/prop_context_manager.py` の `prop_context_manager_muxer` は正常系のみを検証しており、`len(output_buffer.getvalue()) > 0` の assert だけで出力の正しさを demux で確認していない
- `__exit__` が例外発生中でも close() → finalize を実行する挙動を検証するテストが存在しない。非 seekable ストリームでは破損出力が書き出される危険があり、ドキュメントに注意書きはあるがテストで固定されていない
- コンテキストマネージャ経由で正しい MP4 が生成されるかを demux で確認するテストがない

## 設計方針

- コンテキストマネージャ経由の正常系で、出力が demux 可能であることを検証する (prop_context_manager_muxer の強化)
- ブロック内で例外が発生した場合の `__exit__` の挙動を検証するテストを追加する
- 例外時の出力がどうなるか (破損するか・破損しないか) を明確にし、ドキュメントと整合することを確認する

## 完了条件

- コンテキストマネージャ経由の正常系・例外系がテストで固定される
- 既存テストが全通過する
