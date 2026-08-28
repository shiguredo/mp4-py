# cargo fmt --check が develop で通らない (finalized チェックのフォーマット違反)

- Created: 2026-08-16
- Completed: {YYYY-MM-DD}
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

1. `cargo fmt --all` を実行する
2. `cargo fmt --all -- --check` で成功を確認する
3. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
