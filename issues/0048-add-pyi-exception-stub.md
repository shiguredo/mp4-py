# 型スタブ (.pyi) に Mp4Exception が含まれないため型チェッカから解決できない

- Created: 2026-08-16
- Completed: {YYYY-MM-DD}
- Branch: feature/add-pyi-exception-stub
- Polished: 2026-09-01
- Milestone: 2026.2.0

## 目的

`mp4.Mp4Exception` を静的型チェッカから解決できるようにする (検証はプロジェクトの型チェッカである `ty` で行う)。実行時の動作は問題ないが、型スタブに `Mp4Exception` が含まれないため、型チェッカでは unknown 扱いになり、`except mp4.Mp4Exception:` の型検査ができない。

## 現状

pyo3-introspection 0.29 の `maturin build --generate-stubs` が生成する `mp4_ext.pyi` に、`create_exception!` で定義した例外が含まれないことを実測確認済み (wheel を展開して grep で 0 件。pyclass は 19 個すべて出力される)。

- 原因は pyo3 の experimental-inspect (pyo3-introspection) が `create_exception!` 型をスタブに出力しないことにある (生成スタブからの例外欠落は issue 0006 で実測確認済み)
- `src/lib.rs` の `create_exception!(mp4.mp4_ext, Mp4Exception, PyRuntimeError)` が生成元
- `python/mp4/__init__.py` は `from .mp4_ext import ...` で `Mp4Exception` を再公開しており、スタブに宣言が無いと `mp4.Mp4Exception` は unknown になる
- issue 0006 の完了条件で「本 issue の対象外とし別途検討する」としている
- pyproject.toml の `[tool.ty.analysis] allowed-unresolved-imports` は `mp4.mp4_ext` の import 解決不能を許容している (同梱スタブで解決できるようになったら見直す)

## 設計方針

- 手書きの `.pyi` を同梱して `Mp4Exception` の宣言を補う方針で確定する (ビルド構成の変更が必要: 生成スタブへの追記、または手書きスタブへの置き換え。maturin のスタブ同梱動作と生成スタブとの合成方法は調査して確定する)
- pyo3 の stubs 生成が `create_exception!` をサポートする将来バージョンを待つ選択肢は、本 issue の完了条件 (型チェッカでの解決確認) を満たせないため対象外とする
- 検証はプロジェクトの型チェッカ (`ty`) で行う
- 同梱スタブで `mp4.mp4_ext` が解決できるようになった場合は、pyproject.toml の `[tool.ty.analysis] allowed-unresolved-imports` から `mp4.mp4_ext` を外して確認する

## 完了条件

- 同梱するスタブに `Mp4Exception` の宣言が含まれ、プロジェクトの型チェッカ (`ty`) が `mp4.Mp4Exception` を unknown として扱わないことを確認できる
- 同梱スタブで `mp4.Mp4Exception` が解決できることを自動化したテストが追加される
- 既存テストが全通過する

## 解決方法

1. pyo3-introspection が `create_exception!` を出力できるか最新の動向を調査する (対応済みなら生成スタブで解決できるため、同梱スタブが不要になるかを判断する)
2. 手書き `.pyi` の同梱方法 (maturin の設定、生成スタブとの合成方法) を調査する
3. 実装する (同梱スタブの追加とビルド構成の変更)
4. 型チェッカ (`ty`) での解決を確認するテストを追加する
5. pyproject.toml の `[tool.ty.analysis] allowed-unresolved-imports` の `mp4.mp4_ext` を外せるか確認する
6. CHANGES.md にエントリを追記する
7. 全テスト通過を確認する
