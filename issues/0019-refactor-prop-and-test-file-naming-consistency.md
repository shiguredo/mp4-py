# prop_*.py と test_*.py の命名規則違反 (PBT でないテストが prop_ prefix にある)

- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Branch: feature/refactor-prop-and-test-file-naming-consistency
- Polished: {YYYY-MM-DD}

## 目的

`pyproject.toml` の `[tool.pytest.ini_options]` 内コメント「Property-Based Testing (PBT) は prop_ prefix を使用する」に反し、`tests/prop_*.py` に `@given` を持たない決定的テストが 10 件混入している状態を解消する。決定的テストは `tests/test_*.py` に移動、または境界値を strategy に含めて PBT 化する。`prop_` prefix を PBT に限定しておかないと、prefix による識別の意味そのものが失われる。

## 現状

`@given` なしの決定的テストが `prop_*.py` に混入:

- `tests/prop_edge_cases.py` の `prop_minimum_sample_size`
- `tests/prop_edge_cases.py` の `prop_minimum_dimensions`
- `tests/prop_edge_cases.py` の `prop_maximum_dimensions`
- `tests/prop_edge_cases.py` の `prop_minimum_duration`
- `tests/prop_edge_cases.py` の `prop_large_duration`
- `tests/prop_edge_cases.py` の `prop_minimum_timescale`
- `tests/prop_edge_cases.py` の `prop_hev1_empty_nalu`
- `tests/prop_edge_cases.py` の `prop_single_sample_per_track`
- `tests/prop_error.py` の `prop_muxer_empty_finalize`
- `tests/prop_error.py` の `prop_demuxer_empty_file`

これらは全て境界値のテスト (解像度 1x1, duration=1, timescale=1 等) だが、`@given` がなく決定的。命名規則違反。

## 設計方針

以下のいずれかを採用する。

### 方針 A: 決定的テストを `tests/test_*.py` に移動

- 命名規則が明確に守られる
- 各 prop_ ファイルから該当関数を切り出し、新規 `tests/test_edge_cases.py` / `tests/test_empty_cases.py` に移動

### 方針 B: 境界値を strategy に含めて PBT 化

- テストがより網羅的になる
- 例: `prop_minimum_dimensions` と `prop_maximum_dimensions` を統合し、`st.sampled_from([1, 16, 4096, 7680])` で幅と高さを網羅
- ただし、境界の 1 点だけを検証したい場合は決定的テストの方が意図が明確

### 推奨

境界値テストは決定的にとどめる方が意図が伝わりやすい (PBT にすると shrink で境界に到達するかが不確定)。方針 A を推奨。

## 完了条件

- `tests/prop_*.py` に `@given` を持たない関数が 0 件になる
- 移動先のテスト (`tests/test_edge_cases.py` / `tests/test_empty_cases.py`) が全通過
- 既存の PBT (`prop_*.py` に残るもの) も全通過

## 解決方法

1. `tests/test_edge_cases.py` を新規作成し、`tests/prop_edge_cases.py` から `@given` なしの関数 8 個を移動
2. `tests/test_empty_cases.py` を新規作成し、`tests/prop_error.py` から `prop_muxer_empty_finalize` / `prop_demuxer_empty_file` の 2 個を移動
3. 移動時に関数名の prefix を `prop_` → `test_` に置換
4. 移動先ファイルの import 文を整理
5. `NO_UV_SYNC=1 uv run pytest` で全テストが通ることを確認
