# mp4-py

## Rust / PyO3

- `cargo fmt` でフォーマットすること
- `cargo clippy` で静的解析すること
- shiguredo/mp4-rs は `Cargo.toml` の path 依存で参照している
  - ローカル開発では `../mp4-rs` にチェックアウトが必要
- pyo3 の feature は `extension-module`, `abi3-py312`, `experimental-inspect` を有効化する
- `abi3-py312` により Python 3.12 以降の GIL 有効ビルドは 1 wheel で共有する
- Free-Threading (3.14t) は abi3 対象外なのでバージョン固有 wheel を別ビルドする
- `#[pymodule(gil_used = false)]` inline module 形式で書くこと
  - 関数形式 (`#[pymodule] fn`) は `--generate-stubs` が動かない
- SampleEntry 系の pyclass は `frozen, from_py_object` を付ける (immutable + Sync)
- Muxer / Demuxer / DemuxSample の pyclass は `frozen, skip_from_py_object` を付ける
- 内部状態を保護する Mutex は `std::sync::Mutex` + `pyo3::sync::MutexExt::lock_py_attached(py)` を使う
  - Python コールバック越しにロックを保持する場面のデッドロックを避けるため

## ビルド

- 開発ビルド: `maturin develop --release`
- wheel 生成: `maturin build --release --out wheelhouse --generate-stubs`
- sdist: `maturin sdist`
- stub 単体: `maturin generate-stubs --out stubs`

## Python

- Python の命名規則に従うこと
- `pip` を使わず `uv` を使うこと
- `uv run ruff format` でコードをフォーマットすること
- `uv run ruff check` でコードを静的解析すること

### 型アノテーション

- `Optional` ではなく `| None` を使うこと

### Free-Threading

- Free-Threading 環境では GIL は存在しない
- GIL の取得と解放という表現は使わないこと
- PyO3 の `Python::attach` は「Python ランタイムにアタッチ」として使用する
- `SuspendAttach` は「Python ランタイムからデタッチ」として使用する
- pyclass 内部状態は `std::sync::Mutex<T>` で保護し `lock_py_attached(py)` で取得すること
- 現状 pyo3 0.29 では 3.14t 環境で並列に append_sample を回すとスケーリングが悪化する既知事象あり
  - 単一スレッド性能は nanobind と同等 (小サンプルで 15% 程度遅い)

### pytest

- モックやスタブは利用禁止
- テストは pytest のみを利用すること
- タスクを完了する前に全てのテストを実行して、全てのテストが通ることを確認すること
- pytest 実行時長くても 60 秒以内にすること
- pytest のタイムアウトは pytest-timeout を利用すること
  - `pytest --timeout=10` のように指定すること
- テスト実行時は `NO_UV_SYNC=1` を指定すること
  - `NO_UV_SYNC=1 uv run pytest` のように指定すること
- テストを削除してテストを通したりしないこと
- テストを無効にしてテストを通したりしないこと
- テストがタイムアウトしたら重大な問題が発生していると考えること
  - デッドロックが発生している可能性がある
- 明確な理由がない限りは try/expect をテストでは利用しないこと
- class を使わないこと
- lambda は使わないで def を使うこと

### hypothesis

- hypothesis の database (.hypothesis/examples/) をクリアしてテストを通すことは禁止
  - database には failing case が保存されている
  - バグを修正すること

## リリース

- バージョンは `Cargo.toml` の `[package] version` を source of truth とする
  - pyproject.toml は `dynamic = ["version"]` で maturin が Cargo.toml から読み取る
- リリース手順:
  1. `Cargo.toml` の version を更新
  2. `CHANGES.md` の `develop` セクションをバージョン節へ移動
  3. コミット + git tag `202X.Y.Z`
  4. tag を push すると `.github/workflows/wheel.yml` が起動し PyPI + GitHub Release に公開する
- CHANGES.md は `shiguredo-changelog` スキルの規約に従うこと
