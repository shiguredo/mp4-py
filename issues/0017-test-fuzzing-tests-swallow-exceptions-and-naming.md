# test_fuzzing.py の全 fuzzing テストが例外を握りつぶす + 命名規則違反

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/test-fuzzing-fix-exception-swallowing-and-rename
- Polished: {YYYY-MM-DD}

## 目的

`tests/test_fuzzing.py` の 3 種類の問題を同時に解消する。

1. 全 10 fuzzing テストが `except (ValueError, RuntimeError, StopIteration): pass` で例外を握りつぶし、リグレッション検出に失敗する
2. ファイル名・関数名が `test_` prefix なのに、実質は全て PBT (`@given` 付き) で `prop_` prefix が正しい
3. `tests/prop_error.py:49` で `pytest.raises(Exception)` で基底クラスを受けている

## 優先度根拠

High。

- `CODEBASE.md:43`「明確な理由がない限りは try/except をテストでは利用しない」に違反。
- 現状の実装は「クラッシュしなければ OK」しか検証しておらず、`Mp4Exception` が `RuntimeError` として飛ぶ以上、本来クラッシュ扱いすべき例外まで沈黙する。10 個中 9 個のテストが実質「クラッシュ検知」しか行っていない。
- `for sample in demuxer` パターンでは `StopIteration` は自動吸収されるため、`StopIteration` の catch は 8 箇所すべてデッドコード。
- 命名規則 (`pyproject.toml:39-41` 「PBT は prop_ prefix を使用する」) に違反。
- 修正コストは中程度 (例外の分類 + ホワイトリスト assert + ファイル名リネーム)。

## 現状

### 例外握りつぶし

`tests/test_fuzzing.py:22-33` (代表例):
```python
@given(...)
@settings(max_examples=1000)
def test_fuzzing_muxer_random_bytes(...) -> None:
    """MP4 の muxer にランダムなバイト列を渡してもクラッシュしない"""
    ...
    try:
        muxer.append_sample(sample)
        muxer.finalize()
    except (ValueError, RuntimeError, StopIteration):
        pass
```

同様のパターンが 10 箇所 (22-28, 62-66, 102-106, 125-129, 181-185, 206-210, 225-229, 279-283, 303-307, 320-347)。

`Mp4Exception` は `std::runtime_error` サブクラスとして nanobind が `RuntimeError` に変換するため、本来クラッシュ扱いすべき例外まで沈黙する。`test_fuzzing_muxer_random_data` (316-348) だけは finalize 後に demux し直して sample 数の不変条件を検証している。

### 命名規則違反

全 10 関数が `@given` 付きの PBT だが、ファイル名 `test_fuzzing.py`、関数名 `test_fuzzing_*`。

### pytest.raises(Exception)

`tests/prop_error.py:49`:
```python
# finalize 後に追加しようとするとエラー
with pytest.raises(Exception):
    muxer.append_sample(mux_sample)
```

`Exception` は基底クラスなので `AssertionError` / `SystemError` / `MemoryError` まで受けてしまう。実装ミスで別種例外が出ても pass する。

## 設計方針

### 例外握りつぶしの解消

- `StopIteration` の catch を削除 (デッドコード)
- `ValueError` / `RuntimeError` の catch は例外メッセージをホワイトリスト assert (`"corrupted data"` / `"too many iterations"` 等)
- 「有効入力範囲では非例外・破損時は特定例外」の不変条件を明示

### 命名規則の統一

- `tests/test_fuzzing.py` → `tests/prop_fuzzing.py`
- 関数名: `test_fuzzing_*` → `prop_fuzzing_*`

### pytest.raises の型指定

- `pytest.raises(Exception)` → `pytest.raises(RuntimeError, match="...")` に変更
- `issues/0006-add-mp4-exception-python-registration.md` の対応後は `Mp4Exception` に絞ることも可能

## 完了条件

- `tests/test_fuzzing.py` が `tests/prop_fuzzing.py` にリネームされる
- 全 10 関数の `test_fuzzing_*` が `prop_fuzzing_*` にリネームされる
- 全ての try/except が以下のいずれかに置き換わる:
  - `StopIteration` catch は削除
  - `ValueError` / `RuntimeError` は `pytest.raises(RuntimeError, match=...)` パターン、または例外メッセージのホワイトリスト assert
- `tests/prop_error.py:49` の `pytest.raises(Exception)` が `pytest.raises(RuntimeError, match="...")` に変更
- 全テスト通過

## 解決方法

1. `git mv tests/test_fuzzing.py tests/prop_fuzzing.py`
2. `tests/prop_fuzzing.py` 内で全 `test_fuzzing_*` を `prop_fuzzing_*` に置換
3. 各 try/except を以下のパターンに書き換え:
   ```python
   # Before
   try:
       samples = list(demuxer)
   except (ValueError, RuntimeError, StopIteration):
       pass

   # After
   allowed_error_patterns = [
       "corrupted data",
       "too many iterations",
       "unexpected end of file",
       "invalid",
   ]
   try:
       samples = list(demuxer)
   except RuntimeError as e:
       assert any(p in str(e).lower() for p in allowed_error_patterns), \
           f"予期しないエラーメッセージ: {e}"
   ```
4. `StopIteration` catch は削除 (`for` ループで自動吸収されるため)
5. `tests/prop_error.py:49` の `pytest.raises(Exception)` を `pytest.raises(RuntimeError, match="closed|Invalid state|finalized")` に置き換え
6. `NO_UV_SYNC=1 uv run pytest tests/prop_fuzzing.py` で全通過を確認
7. `issues/0016-test-add-pytest-timeout-config.md` の対応後に実施すること (timeout 設定が先)
