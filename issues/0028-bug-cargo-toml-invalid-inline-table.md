# Cargo.toml のマルチライン inline table が TOML 1.0 違反になっている

- Priority: Medium
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-cargo-toml-invalid-inline-table
- Polished: 2026-08-15

## 目的

`Cargo.toml` の `[dependencies]` で `pyo3` がマルチライン inline table 形式で記述されており、TOML 1.0 規格違反になっている状態を解消する。規格違反のままでは、厳密パーサを使うツールでビルドが失敗しうる (ローカルの maturin 1.9.6 で実測) ため、書式を正す。

## 現状

`Cargo.toml` の `[dependencies]`:

```toml
pyo3 = {
  version = "0.29",
  features = ["abi3-py312", "experimental-inspect", "extension-module"]
}
```

inline table 内の改行は TOML 1.0 で禁止されている (TOML v1.0.0 仕様: "No newlines are allowed between the curly braces unless they are valid within a value")。

実際の影響は以下のとおり:

- cargo のパーサ (toml_edit) は寛容なため `cargo build` / `cargo clippy` は通る
- `python3 -m tomllib` の厳密パースは `Invalid initial character for a key part (at line 21, column 9)` で失敗する
- ローカル環境の maturin 1.9.6 は `TOML parse error at line 21, column 9 / invalid inline table / expected \`}\`` で失敗する (`maturin build` / `maturin sdist` を実機で確認)
- pyproject.toml が要求する maturin 1.14 以降ではビルド成功する (実機確認済み)。CI (PyO3/maturin-action は最新 maturin を使用) も success のため、リリースパイプラインへの即時影響はない

つまり実害は「ローカル開発環境で古い maturin を使うと失敗する」ことと、「TOML 1.0 規格違反が残ったままである」こと。規格違反のままでは厳密パーサで失敗する状態が続くため修正する。

`shiguredo_mp4 = "=2026.4.0"` は 1 行のため問題ない。`[build-dependencies]` の `cargo_metadata = "0.23"` も同様。

## 設計方針

- inline table を 1 行に潰す、または `[dependencies.pyo3]` セクション形式に変更する
- コメント (用途・Free-Threading 対応の理由) は失わない
- 書式以外の変更はしない

## 完了条件

- pyproject.toml が要求するバージョン (maturin 1.14 以降) で `maturin build --release --out wheelhouse --generate-stubs` が成功する
- `maturin develop --release` が成功する (maturin 1.14 以降)
- `maturin sdist` が成功する (maturin 1.14 以降)
- `cargo build` / `cargo clippy --all-targets -- -D warnings` が従来どおり通る
- `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` が全テスト通過する

## 解決方法

1. `Cargo.toml` の `[dependencies]` の `pyo3` を 1 行の inline table に書き換える (コメントは維持)
2. `python3 -c "import tomllib; tomllib.load(open('Cargo.toml','rb'))"` で厳密パースが通ることを確認する
3. `uv run --with "maturin>=1.14,<2" maturin build --release --out wheelhouse --generate-stubs` で wheel が生成できることを確認する (ローカルの maturin が 1.14 未満でも、pyproject.toml の要求バージョンで検証する)
4. `maturin develop --release` と `maturin sdist` は、maturin 1.14 以降が入った開発環境で実行して成功を確認する
5. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
6. CHANGES.md の `### misc` に「[FIX] Cargo.toml の pyo3 依存を TOML 1.0 準拠の 1 行 inline table に修正する」を追記する (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
