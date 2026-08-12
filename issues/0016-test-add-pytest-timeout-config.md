# pytest のタイムアウトが pyproject.toml に未設定 (規約違反)

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/test-add-pytest-timeout-config
- Polished: 2026-08-12

## 目的

`pytest-timeout` を依存に持ちながら、pytest 実行時のタイムアウトが `pyproject.toml` に一切設定されていない状態を解消する。CODEBASE.md の pytest 規約に準拠させ、破損 MP4 テスト等でハングした場合のセーフティネットを確立する。

なお、pytest-timeout の signal 方式は Python レベルの実行中しかシグナルを処理できないため、Rust 拡張 (PyO3) 内部で GIL を保持したまま無限ループ・デッドロックした場合はタイムアウトで中断できない。その場合は CI のジョブタイムアウト (`timeout-minutes`) と手動での強制終了が最終手段となる。Windows では thread 方式が既定で、タイムアウト時にプロセス全体を強制終了するためこの限界は当てはまらない。

## 優先度根拠

High。

- CODEBASE.md の pytest 規約違反:
  - 「pytest 実行時長くても 60 秒以内にすること」
  - 「pytest のタイムアウトは pytest-timeout を利用すること」
  - 「`pytest --timeout=10` のように指定すること」
- ローカル実行 (`NO_UV_SYNC=1 uv run pytest tests/`) ではコマンドラインからタイムアウトが渡らず、テストがハングした場合の保険がない
- 修正コストは pyproject.toml への 1 行追加のみ

## 現状

`pyproject.toml` の `[dependency-groups]` の `test` グループに `pytest-timeout` は含まれている。

`pyproject.toml` の `[tool.pytest.ini_options]` は `python_files` / `python_functions` / `testpaths` のみで、`timeout` の指定がない。`tests/conftest.py` も PBT strategy 定義のみで pytest フックがない。

`.github/workflows/wheel.yml` のテスト実行は全箇所でコマンドラインに `--timeout=30` を明示している。pytest-timeout はコマンドラインの `--timeout` が ini の `timeout` より優先されるため、本 issue の変更後も CI は 30 秒のまま変わらない。

ローカルでの実測では全テストが 5 秒程度で完走する (91 passed / 5 skipped)。`timeout = 10` を設定しても既存テストは影響を受けない。

## 設計方針

### 既定タイムアウトを `pyproject.toml` に設定

- `[tool.pytest.ini_options]` に `timeout = 10` を追加する
- コマンドラインで `--timeout=N` を渡した場合はそちらが優先される。CI は `--timeout=30` を明示しているので 30 秒のまま
- 個別のテストで 10 秒を超える場合は `@pytest.mark.timeout(N)` (N は 30 以下。CI のセーフティネットを超えない値) を付与する
  - 実測では現状の全テストが 10 秒以内に収まっており、付与対象は現状存在しない。将来 10 秒を超えるテストが追加された場合に付与する
  - タイムアウトで失敗したテストへのマーカー付与は、まずバグやデッドロックを疑ったうえで正当に時間のかかるテストと確認できた場合のみとする

## 完了条件

- `pyproject.toml` の `[tool.pytest.ini_options]` に `timeout = 10` が追加される
- `NO_UV_SYNC=1 uv run pytest tests/` で全テストがタイムアウトせずに完走する
- 10 秒を超えるテストがある場合は `@pytest.mark.timeout(N)` (N は 30 以下) が付与される
- `.github/workflows/wheel.yml` の `--timeout=30` は変更しない (コマンドライン指定が優先されるため CI の挙動は変わらない)

## 解決方法

1. `pyproject.toml` の `[tool.pytest.ini_options]` に `timeout = 10` を追加する
2. `NO_UV_SYNC=1 uv run pytest tests/` で全テストがタイムアウトせずに完走することを確認する
3. 10 秒を超えるテストが検出された場合は `@pytest.mark.timeout(N)` (N は 30 以下) を付与する
4. 変更は `pyproject.toml` のみで完結するため、fuzzing テストの例外修正とリネーム (issues/0017-test-fuzzing-tests-swallow-exceptions-and-naming.md) は本 issue の対応後 (マージ順で本 issue が先) に実施する
