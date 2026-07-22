# PyMp4FileDemuxer::enter / PyMp4FileMuxer::enter は使われていないデッドコード

- Priority: Low
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/refactor-remove-dead-enter-methods
- Polished: {YYYY-MM-DD}

## 目的

`PyMp4FileDemuxer::enter()` / `PyMp4FileMuxer::enter()` は定義されているが、対応する `__enter__` バインディングは lambda で置き換えられており、これらのメソッドは一切呼ばれない。デッドコードを削除して意図を明確にする。

## 優先度根拠

Low。

- 機能上のバグではないが、コードを読む際に「なぜ定義しているのに使われていないのか」で混乱する。
- 修正コストは 2 メソッド削除だけで完結する。

## 現状

### メソッド定義

`src/mp4_ext.cpp:788`:
```cpp
PyMp4FileDemuxer& enter() { return *this; }
```

`src/mp4_ext.cpp:1431`:
```cpp
PyMp4FileMuxer& enter() { return *this; }
```

### バインディング (lambda で置き換え)

`src/mp4_ext.cpp:2100-2103`:
```cpp
.def(
    "__enter__",
    [](PyMp4FileDemuxer& self) -> PyMp4FileDemuxer& { return self; },
    nb::rv_policy::reference)
```

`src/mp4_ext.cpp:2183-2186`:
```cpp
.def(
    "__enter__",
    [](PyMp4FileMuxer& self) -> PyMp4FileMuxer& { return self; },
    nb::rv_policy::reference)
```

`enter()` メソッドは grep で他に参照なし。完全に呼ばれないデッドコード。

## 設計方針

以下のいずれかを採用する。

### 方針 A (推奨): デッドコードの `enter()` を削除

- 変更コスト最小
- lambda ベースの `__enter__` バインディングだけ残す
- 一貫性: `iter()` (846) はメソッド定義かつバインディング (2106) で使われているため、`enter()` だけ lambda ベースなのはやや不整合だが、大きな問題ではない

### 方針 B: lambda を削除し `enter()` メソッドを使う

- `.def("__enter__", &PyMp4FileDemuxer::enter, nb::rv_policy::reference)` に置き換え
- `iter()` (2106) と統一される
- コード削減にはならないが、パターンが揃う

### 方針 A + 方針 B のどちらでもよい。方針 A を推奨。

## 完了条件

- `PyMp4FileDemuxer::enter()` / `PyMp4FileMuxer::enter()` メソッドが削除される
- 既存の `.def("__enter__", ...)` lambda はそのまま残る
- 既存の context manager テスト (`prop_context_manager.py`) が全通過

## 解決方法

1. `src/mp4_ext.cpp:788` を削除
2. `src/mp4_ext.cpp:1431` を削除
3. `NB_MODULE` 内の `.def("__enter__", ...)` lambda はそのまま
4. `make develop && NO_UV_SYNC=1 uv run pytest tests/prop_context_manager.py` で context manager テストが通ることを確認

## 対応結果

`PyMp4FileDemuxer::enter` / `PyMp4FileMuxer::enter` は C++ 実装内のデッドコードであり、nanobind から PyO3 への置き換えで消滅した。PyO3 版の `__enter__` は Muxer / Demuxer の pyclass 上に単一の `fn __enter__(slf: Py<Self>) -> Py<Self>` として定義されており、重複はない。よって closed とする。
