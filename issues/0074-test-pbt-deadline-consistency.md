# PBT の deadline 設定を整備する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/test-pbt-deadline-consistency
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

hypothesis の PBT テストの deadline 設定を揃え、遅い CI 環境でのフレークを防ぐ。テストの実行時間の変動に頑健にする。

## 現状

`tests/prop_large_file_structure` のみ `deadline=None` を指定しているが、`prop_large_sample_data` (最大 100 KB のサンプル) や `prop_variable_duration_samples` (最大 100 サンプル) はデフォルトの deadline (200 ms) のままになっている。遅い CI 環境ではこれらのテストが deadline 超過でフレークする可能性がある。

## 設計方針

- データ量の大きい PBT テストの deadline 設定を確認し、必要に応じて `deadline=None` か十分な値に揃える
- 全 PBT テストの deadline 設定を一覧で確認し、方針を統一する

## 完了条件

- 大きなデータを扱う PBT テストが deadline 超過でフレークしない
- 既存テストが全通過する
