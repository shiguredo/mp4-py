# cargo fmt --check が develop で通らない (finalized チェックのフォーマット違反)

- Created: 2026-08-16
- Completed: 2026-08-28
- Branch: feature/fix-cargo-fmt-finalized-check
- Polished: {YYYY-MM-DD}

## 目的

`cargo fmt --all -- --check` が develop ブランチで失敗する状態を解消する。prek の cargo-fmt フック (`cargo fmt --all -- --check`) がコミット時に失敗し、開発フローが滞るため。

## 現状

`src/lib.rs` の `Mp4FileMuxer::append_sample` 内の finalized チェック (0029 で追加) が rustfmt の出力と一致しない:

```rust
if state.finalized {
    return Err(PyRuntimeError::new_err(
        "Muxer has already been finalized",
    ));
}
```

rustfmt はこれを 1 行にまとめる (行長 100 文字以内のため):

```rust
if state.finalized {
    return Err(PyRuntimeError::new_err("Muxer has already been finalized"));
}
```

`cargo fmt --check` の実行で確認済み。0029 のマージ時に `cargo fmt` が実行されず develop に入った。

## 設計方針

- `cargo fmt --all` を実行してフォーマットを修正する
- 書式以外の変更はしない

## 完了条件

- `cargo fmt --all -- --check` が成功する
- 全テストが通過する

## 解決方法

`cargo fmt --all` を実行してフォーマットを修正した。commit `89f8d02` (src/lib.rs に cargo fmt を適用する) で develop に入り、以後 `cargo fmt --all -- --check` は成功する。

1. `Mp4FileMuxer::append_sample` 冒頭の finalized チェックを rustfmt 出力どおりの 1 行記述に直した (書式以外の変更はない)
2. 2026-08-28 に `cargo fmt --all -- --check` の成功を再確認した
3. 2026-08-28 に `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で 124 passed / 7 skipped を確認した
