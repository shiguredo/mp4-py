# 型スタブ (.pyi) に Mp4Exception が含まれないため型チェッカから解決できない

- Priority: Medium
- Created: 2026-08-16
- Completed: {YYYY-MM-DD}
- Branch: feature/add-pyi-exception-stub
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

`mp4.Mp4Exception` を静的型チェッカ (pyright / mypy 等) から解決できるようにする。実行時の動作は問題ないが、型スタブに `Mp4Exception` が含まれないため、型チェッカでは unknown 扱いになり、`except mp4.Mp4Exception:` の型検査ができない。

## 現状

pyo3-introspection 0.29 の `maturin build --generate-stubs` が生成する `mp4_ext.pyi` に、`create_exception!` で定義した例外が含まれないことを実測確認済み (wheel を展開して grep で 0 件。pyclass は 19 個すべて出力される)。

- 原因は pyo3 の experimental-inspect が `create_exception!` 型を出力しないこと (pyo3 自身の stubs 生成テストでも `create_exception!` の例外が欠落し、`#[pyclass(extends)]` 版のみ出力されている)
- `src/lib.rs` の `create_exception!(mp4.mp4_ext, Mp4Exception, PyRuntimeError)` が生成元
- issue 0006 の完了条件で「本 issue の対象外とし別途検討する」としている

## 設計方針

- 手書きの `.pyi` を同梱して `Mp4Exception` の宣言を補う方法を検討する (ビルド構成の変更が必要: 生成スタブへの追記、または手書きスタブへの置き換え)
- もしくは pyo3 の stubs 生成が `create_exception!` をサポートする将来バージョンを待つ方針も選択肢として残す
- 方針は調査結果とコスト次第で確定する

## 完了条件

- 型チェッカ (pyright / mypy の少なくとも 1 つ) が `mp4.Mp4Exception` を unknown として扱わないことを確認できる
- 生成スタブの検証テスト (生成 `.pyi` に `Mp4Exception` が含まれること、または同梱スタブで解決できること) を追加する

## 解決方法

1. pyo3-introspection が `create_exception!` を出力できるか最新の動向を調査する
2. 手書き `.pyi` の同梱方法 (maturin の設定、生成スタブとの合成方法) を調査する
3. 実装する
4. 型チェッカでの解決を確認するテストを追加する
5. CHANGES.md にエントリを追記する
6. 全テスト通過を確認する
