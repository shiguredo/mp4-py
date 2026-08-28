# 破損データ由来エラーが Mp4Exception と RuntimeError の 2 型で届く

- Created: 2026-08-16
- Completed: {YYYY-MM-DD}
- Branch: feature/refactor-unify-corrupted-data-errors
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

破損データ由来のエラーが、デマクサー内で 2 種類の例外型として届く状態を解消する。ユーザーが `except mp4.Mp4Exception:` で破損データ由来のエラーを一律に捕捉できるようにする。

## 現状

- feed 中のエラー (too many iterations / Required input position/size too large) は `Mp4Exception` (破損データ検出の型分類用例外。0006 で導入)
- パースエラー (DecodeError / SampleTableError) は素の `PyRuntimeError` (`mp4 error: ...` 形式。0036 で表面化)

デマクサー内で破損データ由来のエラーが 2 種類の例外型で届くため、`except mp4.Mp4Exception:` で一律捕捉しようとするとパースエラーは捕捉できない。テストは `pytest.raises(RuntimeError, ...)` のため通るが、ユーザー視点では不統一。

## 設計方針

- パースエラー (DecodeError / SampleTableError) も `Mp4Exception` に変換するか、エラーハンドリングの一貫性を扱う別 issue (0046) の設計に合わせて統合するかを検討する
- 0046 (API のエラーハンドリング一貫性とコード整理) の実装タイミングとの整合を取る

## 完了条件

- 破損データ由来のエラーが 1 種類の例外型で届く
- 既存テストが全通過する

## 解決方法

1. 0046 の設計と整合する方針を確定する
2. パースエラーの例外型を統一する
3. テストを追加・更新する
4. 全テスト通過を確認する
