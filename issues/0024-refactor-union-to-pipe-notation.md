# src/mp4/__init__.py の Union を | 記法に統一する

- Priority: Low
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/refactor-union-to-pipe-notation
- Polished: {YYYY-MM-DD}

## 目的

`src/mp4/__init__.py:4, 37-47` で `Union[...]` を使用している箇所を、`A | B | ...` の PEP 604 記法に置き換える。`CODEBASE.md:20` の「`Optional` ではなく `| None` を使う」規約と対称性を取る。

## 優先度根拠

Low。

- 機能上は等価で、`Union[...]` も現状動作する。
- ただし、`Optional` → `| None` の規約が明文化されているのに `Union` だけ残っているのは一貫性の欠如。
- `target-version = "py312"` (`pyproject.toml:45`) なので `A | B` 記法は問題なく使える。
- 修正コストは軽微 (数行の書き換え + import 削除)。

## 現状

`src/mp4/__init__.py:1-4`:
```python
"""Python bindings for mp4-rust"""

from importlib.metadata import version
from typing import Literal, Union
```

`src/mp4/__init__.py:37-48`:
```python
Mp4SampleEntry = Union[
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryHvc1,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
]
"""MP4 サンプルエントリー"""
```

`Union` は typing からの import。Python 3.10+ (`target-version = "py312"`) では `A | B` 記法が推奨。

## 設計方針

- `Union[...]` → `A | B | ...` に置き換え
- `from typing import Literal, Union` の `Union` を削除 (`Literal` は残す)
- 型エイリアスの意味は変わらない (Python 3.10+ の `type` statement は不要)

## 完了条件

- `src/mp4/__init__.py` で `Union` の import と使用が 0 件になる
- `Mp4SampleEntry` 型エイリアスが `A | B | ...` 記法で定義される
- ty (静的型検査) が通ることを確認 (`uv run ty check`)
- 全テスト通過

## 解決方法

1. `src/mp4/__init__.py:4` を書き換え:
   ```python
   from typing import Literal
   ```
2. `src/mp4/__init__.py:37-47` を書き換え:
   ```python
   Mp4SampleEntry = (
       Mp4SampleEntryAvc1
       | Mp4SampleEntryHev1
       | Mp4SampleEntryHvc1
       | Mp4SampleEntryVp08
       | Mp4SampleEntryVp09
       | Mp4SampleEntryAv01
       | Mp4SampleEntryOpus
       | Mp4SampleEntryMp4a
       | Mp4SampleEntryFlac
   )
   """MP4 サンプルエントリー"""
   ```
3. `uv run ty check src/mp4/` で型検査が通ることを確認
4. `uv run ruff format src/mp4/` でフォーマットを整える
5. `NO_UV_SYNC=1 uv run pytest` で全テスト通過を確認
