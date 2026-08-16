# bench スクリプトの sys._is_gil_enabled() が Python 3.12 で AttributeError になる

- Priority: Low
- Created: 2026-08-15
- Completed: 2026-08-16
- Model: Opus 4.7
- Branch: feature/fix-bench-gil-detection
- Polished: 2026-08-15

## 目的

`bench/` の 2 スクリプトが Python 3.12 (GIL 有効) で起動直後に `AttributeError` で落ちる問題を解消し、対応 Python バージョン全てで実行できるようにする。

## 優先度根拠

Low。

- プロジェクトの最小対応バージョン (Python 3.12) で bench が即死する割れ窓
- 静的解析有効化の別 issue (0038) が ty の 4 diagnostics のうち 2 件の解消を本 issue に委任しており、0038 の実装順序 1 に位置づけられている
- 修正コストは小 (2 ファイルの hasattr ガード追加)

## 現状

`bench/bench_muxdemux.py` と `bench/bench_parallel.py` は実行環境の GIL 有無を表示するために `sys._is_gil_enabled()` をガードなしで直接呼んでいる:

```python
print(f"Python: {sys.version.split()[0]}, GIL: {sys._is_gil_enabled()}")
```

`sys._is_gil_enabled` は Python 3.13 で追加された API のため、プロジェクトが対応する Python 3.12 では `AttributeError` で即クラッシュする (実機確認済み)。一方、`tests/test_free_threading.py` の `is_gil_enabled()` は `hasattr(sys, "_is_gil_enabled")` でガードし、API が存在しない環境では GIL 有効 (True) とみなすフォールバックを持つ。bench だけが未対応。

なお、静的解析の型検査 (ty) ではこの 2 箇所が diagnostics として検出されており、その解消も別 issue (0038) から本 issue に委任されている。

## 設計方針

- `hasattr` でガードし、API が存在しない環境では GIL 有効 (True) とみなす (`tests/test_free_threading.py` の `is_gil_enabled()` と同じ方針。Python 3.12 は GIL 有効が確定している環境のため、True 表示が事実に即している)
- 出力は英語のまま (規約に沿う)

## 完了条件

- 両 bench スクリプトが Python 3.12 / 3.13 / 3.14 / 3.14t の全てでクラッシュせずに実行できる
- Python 3.12 で `GIL: True` と表示される (フォールバック値の検証)
- `uv run ty check` で bench の 2 diagnostics が解消している (本 issue の変更のみで解消する。静的解析有効化の別 issue の前提)
- 出力は英語のまま (規約に沿う)

## 解決方法

1. `bench/bench_muxdemux.py` / `bench/bench_parallel.py` の `sys._is_gil_enabled()` 呼び出しを `hasattr` ガード付きに変更した (API が存在しない環境では GIL 有効が確定しているので True とみなす。`tests/test_free_threading.py` の `is_gil_enabled()` と同じ方針)
2. Python 3.12 で実行してクラッシュせず `GIL: True` と表示されることを確認した (3.13+ / 3.14t は API が存在し挙動が変わらないことを実機 4 環境で確認)
3. `uv run ty check` で bench の 2 diagnostics が解消されていることを確認した
4. CHANGES.md の `### misc` に「[FIX] bench スクリプトの GIL 検出を Python 3.12 対応にする」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
