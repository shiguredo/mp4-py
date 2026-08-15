# pytest の addopts (strict-markers / strict-config) が未設定

- Priority: Low
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/test-add-pytest-strict-config
- Polished: 2026-08-15

## 目的

`pyproject.toml` の pytest 設定に `addopts` がなく、未登録マーカーの使用 (マーカー名の typo による適用漏れ) や設定ファイルの typo を検出できない状態を解消する。

## 優先度根拠

Low。

- 現状のテストに未登録マーカーは存在せず、挙動を変えない予防的設定 (将来のマーカー typo を CI で検出できるようにする)
- 修正コストは小 (pyproject.toml への addopts 追加のみ)

## 現状

`pyproject.toml` の `[tool.pytest.ini_options]` は:

```toml
[tool.pytest.ini_options]
python_files = ["test_*.py", "prop_*.py"]
python_functions = ["test_*", "prop_*"]
testpaths = ["tests"]
```

`addopts` が未設定。時雨堂の Python 参考設定では `addopts = ["-ra", "--strict-markers", "--strict-config"]` を指定しており、以下が有効になる:

- `-ra`: テスト結果のサマリで passed 以外 (skipped / xfailed 等) を常に要約表示
- `--strict-markers`: 未登録マーカーの使用をエラーにする (マーカー名の typo を検出できる)
- `--strict-config`: 設定ファイル内の未知のキー (ini キー名の typo) をエラーにする

現状のテストのマーカー使用は `tests/test_free_threading.py` の `pytestmark = pytest.mark.skipif(...)` (pytest 組み込み) のみで、未登録マーカーは存在しない。なお `@pytest.mark.timeout` は pytest-timeout プラグインが自動登録するため、strict 化後も使用可能 (未登録マーカーにはならない)。

pytest タイムアウトの `timeout` 設定は別 issue (issues/0016-test-add-pytest-timeout-config.md) で対応予定のため、本 issue では扱わない。0016 と同一セクションを編集するため、両方ともセクション末尾 (または先頭) に追記するとマージ時にコンフリクトし得る。追加位置をずらして実装する (例: addopts をセクション先頭、timeout をセクション末尾) ことで、マージ順に関わらずコンフリクトを回避できる。

## 設計方針

- `addopts = ["-ra", "--strict-markers", "--strict-config"]` を追加する
- 現状のテストに未登録マーカーは存在しないため、`markers` への追加は不要 (将来 `@pytest.mark.*` を追加する場合は、組み込み・プラグイン登録済み以外のマーカーを `[tool.pytest.ini_options]` の `markers` に登録すること)

## 完了条件

- `addopts` が設定され、`NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` が全テスト通過する
- 既存テストに未登録マーカーがないこと (組み込みの skipif のみ)
- CI (wheel.yml) のテスト実行も strict 化が有効になる (リポジトリルートの pyproject.toml が読まれるため) ことを確認する

## 解決方法

1. `pyproject.toml` の `[tool.pytest.ini_options]` に `addopts = ["-ra", "--strict-markers", "--strict-config"]` を追加する
2. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する (未登録マーカーが検出された場合のみ、`markers` に登録する。現状は skipif のみで検出されない想定)
3. CHANGES.md の `### misc` に「[UPDATE] pytest の addopts に `-ra` / `--strict-markers` / `--strict-config` を追加する」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
