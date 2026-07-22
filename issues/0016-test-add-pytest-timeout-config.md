# pytest --timeout=10 が pyproject.toml / conftest.py に未設定 (規約違反)

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/test-add-pytest-timeout-config
- Polished: {YYYY-MM-DD}

## 目的

`pytest-timeout` を依存に持ちながら、pytest 実行時のタイムアウトが `pyproject.toml` / `conftest.py` に一切設定されていない状態を解消する。CODEBASE.md の pytest 規約 (`--timeout=10` 相当) に準拠させ、破損 MP4 テスト等でハングした場合のセーフティネットを確立する。

## 優先度根拠

High。

- `CODEBASE.md:34-36` に明記された規約違反:
  - 「pytest 実行時長くても 60 秒以内にすること」
  - 「pytest のタイムアウトは pytest-timeout を利用すること」
  - 「`pytest --timeout=10` のように指定すること」
- 実運用では `NO_UV_SYNC=1 uv run pytest` だけで実行するケースがあり、コマンドラインから timeout が渡らない。
- `src/mp4_ext.cpp:929-963` の `feed_required_input` は無限ループ回避のため `kMaxIterations = 10000` を持つが、これを消費し切る前にテストがハングした場合の保険がない。
- 修正コストは pyproject.toml に 1 行追加するだけ。

## 現状

`pyproject.toml:32`:
```toml
test = ["hypothesis", "pytest", "pytest-timeout"]
```

`pytest-timeout` は依存に含まれている。

`pyproject.toml:38-42`:
```toml
[tool.pytest.ini_options]
# Property-Based Testing (PBT) は prop_ prefix を使用する
python_files = ["test_*.py", "prop_*.py"]
python_functions = ["test_*", "prop_*"]
testpaths = ["tests"]
```

`[tool.pytest.ini_options]` に `timeout = 10` の指定なし。`tests/conftest.py` (218 行) も PBT strategy 定義のみで pytest フックがない。

`.github/workflows/wheel.yml` は 3 箇所で `NO_UV_SYNC=1 uv run pytest` を実行するが、`--timeout` オプションを渡していない。

`Makefile:test` は `uv run pytest tests/ --timeout=10` で `--timeout=10` を明示しているが、CI と手動実行で挙動が食い違っている。

## 設計方針

### 既定タイムアウトを `pyproject.toml` に設定

- `[tool.pytest.ini_options]` に `timeout = 10` を追加
- コマンドラインで `--timeout=N` を渡した場合はそちらが優先される
- 長時間 PBT (`test_fuzzing_*` は max_examples=1000) は個別に `@pytest.mark.timeout(30)` で上書き

## 完了条件

- `pyproject.toml` の `[tool.pytest.ini_options]` に `timeout = 10` が追加される
- CI 実行 (`.github/workflows/wheel.yml`) でも 10 秒タイムアウトが有効になる
- 長時間 PBT で必要なテストには個別に `@pytest.mark.timeout(N)` (N > 10) が付く
- Makefile の `--timeout=10` は残す (明示性のため冗長でも許容)

## 解決方法

1. `pyproject.toml:38-42` を以下に変更:
   ```toml
   [tool.pytest.ini_options]
   # Property-Based Testing (PBT) は prop_ prefix を使用する
   python_files = ["test_*.py", "prop_*.py"]
   python_functions = ["test_*", "prop_*"]
   testpaths = ["tests"]
   timeout = 10
   ```
2. `tests/test_fuzzing.py` の `@settings(max_examples=1000)` が指定されているテスト (`test_fuzzing_muxer_random_data` 等) にケース単位のマーカーを付ける:
   ```python
   @pytest.mark.timeout(60)
   @given(...)
   @settings(max_examples=1000)
   def test_fuzzing_muxer_random_data(...):
       ...
   ```
3. `Makefile` の `test:` ターゲット (`uv run pytest tests/ --timeout=10`) は残す (冗長でも意図が明確)
4. `NO_UV_SYNC=1 uv run pytest tests/` で全テストが 10 秒以内に完走することを確認
5. `issues/0017-fix-fuzzing-tests-swallow-exceptions-and-naming.md` の対応と同時にリネームすると混乱するので、本 issue を先行させる
