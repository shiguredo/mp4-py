# wheel.yml の Windows runner を windows-2025-vs2026 に変更する

- Priority: Low
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/update-windows-runner
- Polished: 2026-08-15

## 目的

`.github/workflows/wheel.yml` の Windows runner が `windows-2025` を使用しており、`shiguredo-github-actions` スキルの「`windows-2025` の代わりに `windows-2025-vs2026` を使うこと」という規約に違反している状態を解消する。

## 優先度根拠

Low。

- `windows-2025` は現時点で deprecated ではなく緊急性はないが、スキル規約違反の是正
- 修正コストは小 (2 ジョブの runs-on 変更のみ)

## 現状

`.github/workflows/wheel.yml`:

- `build_abi3_windows`: `runs-on: windows-2025`
- `build_ft_windows`: `runs-on: windows-2025`

`windows-2025-vs2026` は Visual Studio 2026 ツールチェーンを含む runner (actions/runner-images の Available Images 表に存在)。`build_abi3_windows` と `build_ft_windows` はともに PyPI 公開用 wheel をビルドしており (publish_pypi が `wheels-*` を全取得して公開)、VS2026 ツールチェーンでのビルド結果が公開 wheel に反映されることに留意する (macos-26 の「リリース用 artifact は古い SDK の macos-15 のみ」という使い分けとは異なり、Windows は単一 runner のため使い分けはない)。

## 設計方針

- 両ジョブの `runs-on` を `windows-2025-vs2026` に変更する
- それ以外の変更はしない

## 完了条件

- 両ジョブの `runs-on` が `windows-2025-vs2026` になる
- CI が通る

## 解決方法

1. `.github/workflows/wheel.yml` の `build_abi3_windows` / `build_ft_windows` の `runs-on` を `windows-2025-vs2026` に変更する
2. develop への push で CI が通ることを確認する
