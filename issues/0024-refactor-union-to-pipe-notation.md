# python/mp4/__init__.py の Union を | 記法に統一する

- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Branch: feature/refactor-union-to-pipe-notation
- Polished: {YYYY-MM-DD}

## 目的

`python/mp4/__init__.py` で `Union[...]` を使用している箇所を、`A | B | ...` の PEP 604 記法に置き換える。`CODEBASE.md` の型アノテーション節にある「`Optional` ではなく `| None` を使うこと」規約と対称性を取り、型表記を 1 通りに揃える。

## 現状

`python/mp4/__init__.py` 冒頭の import:
```python
"""Python bindings for shiguredo/mp4-rs (PyO3)"""

from importlib.metadata import version
from typing import Literal, Union
```

`python/mp4/__init__.py` の `Mp4SampleEntry` 型エイリアス:
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
    Mp4SampleEntryStpp,
    Mp4SampleEntryWvtt,
    Mp4SampleEntryTx3g,
]
"""MP4 サンプルエントリー"""
```

`Union` は typing からの import。`requires-python = ">=3.12"` (pyproject.toml) かつ ruff の `target-version = "py312"` なので `A | B` 記法は問題なく使える。

## 設計方針

- `Union[...]` → `A | B | ...` に置き換え
- `from typing import Literal, Union` の `Union` を削除 (`Literal` は残す)
- 型エイリアスの意味は変わらない (Python 3.10+ の `type` statement は不要)

## 完了条件

- `python/mp4/__init__.py` で `Union` の import と使用が 0 件になる
- `Mp4SampleEntry` 型エイリアスが `A | B | ...` 記法で定義される
- ty (静的型検査) が通ることを確認 (`uv run ty check`)
- 全テスト通過

## 解決方法

1. `python/mp4/__init__.py` の import 文を書き換え:
   ```python
   from typing import Literal
   ```
2. `python/mp4/__init__.py` の `Mp4SampleEntry` を書き換え:
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
       | Mp4SampleEntryStpp
       | Mp4SampleEntryWvtt
       | Mp4SampleEntryTx3g
   )
   """MP4 サンプルエントリー"""
   ```
3. `uv run ty check python/mp4/` で型検査が通ることを確認
4. `uv run ruff format python/mp4/` でフォーマットを整える
5. `NO_UV_SYNC=1 uv run pytest` で全テスト通過を確認
