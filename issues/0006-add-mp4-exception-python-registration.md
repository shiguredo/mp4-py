# Mp4Exception を Python 側でカスタム例外として捕捉できるようにする

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/add-mp4-exception-python-registration
- Polished: {YYYY-MM-DD}

## 目的

C++ 側で定義している `Mp4Exception` を `nb::exception<Mp4Exception>` で nanobind 経由 Python に公開し、`try: ... except mp4.Mp4Exception:` の形でユーザーアプリが例外を分類できるようにする。

## 優先度根拠

High。

- 現在 `Mp4Exception` は `std::runtime_error` を派生させただけで、`nb::exception<>` 登録がないため Python 側では通常の `RuntimeError` として飛ぶ。
- 一方で C++ ラッパー内では `std::invalid_argument` (Python 側 `ValueError`) と `Mp4Exception` (Python 側 `RuntimeError`) を意図的に使い分けているのに、Python ユーザーは両者を型で区別できない。
- 破損 MP4 の検出 (`Mp4Exception`) と、内部バグ (`MP4_ERROR_NULL_POINTER` → `std::invalid_argument`) をアプリで分類したい要求は自然に発生する。
- 修正コストは小さく (NB_MODULE 冒頭に 1 行追加 + Python 側 re-export)、影響範囲がラッパーに閉じる。

## 現状

`src/mp4_ext.cpp:31-34` で `Mp4Exception` を定義。

```cpp
class Mp4Exception : public std::runtime_error {
 public:
  explicit Mp4Exception(const std::string& msg) : std::runtime_error(msg) {}
};
```

しかし、`NB_MODULE(mp4_ext, m)` (`src/mp4_ext.cpp:1566-2188`) の中に `nb::exception<Mp4Exception>(m, "Mp4Exception")` の登録がない (grep で 0 件確認)。したがって Python 側では:

- `Mp4Exception` → nanobind の既定 exception translator により `RuntimeError` に写像
- `std::invalid_argument` → `ValueError` に写像 (nb_error.h の builtin_exception 定義による)

派生させている意義が失われている。加えて `src/mp4/__init__.py` の `__all__` にも `Mp4Exception` は含まれていない。

## 設計方針

- `NB_MODULE` 冒頭で `nb::exception<Mp4Exception>(m, "Mp4Exception")` を登録する
- 登録後、Python 側では `mp4.mp4_ext.Mp4Exception` として自動的に利用可能になる
- `src/mp4/__init__.py` で `from .mp4_ext import Mp4Exception` を追加、`__all__` にも追加する
- 基底クラスは `Exception` (nanobind 既定) で問題ない。`RuntimeError` にサブクラス化したい場合は `nb::exception<Mp4Exception>(m, "Mp4Exception", PyExc_RuntimeError)` の形で指定する (後方互換性を維持するために PyExc_RuntimeError 派生を推奨)

## 完了条件

- Python から `import mp4; mp4.Mp4Exception` でクラスにアクセスできる
- `except mp4.Mp4Exception:` で `Mp4Exception` が投げられた C++ 例外を捕捉できる
- 既存の `except RuntimeError:` も引き続き機能する (`PyExc_RuntimeError` 派生にした場合)
- 追加テスト: `test_mp4.py` に「破損 MP4 で `Mp4Exception` が発火し、`isinstance(e, RuntimeError)` も真」を確認するテストを追加
- CHANGES.md の `## develop` に「[ADD] `Mp4Exception` を Python 側で捕捉可能にする」を追記

## 解決方法

1. `src/mp4_ext.cpp:1566-1568` あたりの `NB_MODULE(mp4_ext, m)` 冒頭に以下を追加:
   ```cpp
   nb::exception<Mp4Exception>(m, "Mp4Exception", PyExc_RuntimeError);
   ```
2. `src/mp4/__init__.py:6-29` の `from .mp4_ext import ...` に `Mp4Exception` を追加
3. `src/mp4/__init__.py:56` の `__all__` に `"Mp4Exception"` を追加
4. `tests/test_mp4.py` に破損 MP4 で `Mp4Exception` を捕捉するテストを追加
5. `CHANGES.md` の `## develop` に ADD エントリを追記
6. 既存の `std::invalid_argument` を投げている箇所 (`src/mp4_ext.cpp:917, 1531, 1537`) は本 issue の対象外だが、別途 `issues/0010-refactor-error-classification-null-and-stop-iteration.md` で扱う
