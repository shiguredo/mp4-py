# Free-Threading wheel の ubuntu / windows ビルドでテストが実行されない

- Created: 2026-08-15
- Completed: 2026-08-16
- Branch: feature/add-free-threading-wheel-tests
- Polished: 2026-08-15

## 目的

`.github/workflows/wheel.yml` の Free-Threading (Python 3.14t) ジョブのうち、ubuntu / windows でビルドのみが行われテストが実行されていない状態を解消し、全プラットフォームで 3.14t の動作を検証する。macOS のみの検証ではプラットフォーム依存の問題 (例: pytest-timeout の thread 方式は Windows で既定となり、タイムアウト時にプロセス全体を強制終了する挙動) を検出できない。

## 現状

`.github/workflows/wheel.yml` の構成:

- `build_ft_macos`: 「Test wheel (3.14t)」ステップあり。`NO_UV_SYNC=1 .venv-ft/bin/pytest tests/test_free_threading.py tests/test_mp4.py --timeout=30 -q --noconftest` を実行
- `build_ft_ubuntu`: ビルド + artifact アップロードのみ、テストなし
- `build_ft_windows`: ビルド + artifact アップロードのみ、テストなし

abi3 系 (`build_abi3_*`) は全ジョブ (macos / ubuntu / windows) でテストを実行しているため、Free-Threading 系だけテストが欠落している。

なお、FT ジョブのテストステップでは `--noconftest` が必須である: FT ジョブの venv には hypothesis がインストールされない (`uv pip install ... pytest pytest-timeout` のみ) 一方、`tests/conftest.py` が `from hypothesis import strategies as st` を import するため、`--noconftest` なしでは conftest 読み込み時に `ModuleNotFoundError` でテストが即失敗する。

## 設計方針

- `build_ft_ubuntu` / `build_ft_windows` に `build_ft_macos` と同じテストステップを追加する
- 実行コマンドは `build_ft_macos` と同一にする (`NO_UV_SYNC=1 .venv-ft/bin/pytest tests/test_free_threading.py tests/test_mp4.py --timeout=30 -q --noconftest`)
- prop_* テスト (PBT) は対象外とする。理由は「FT venv に hypothesis がインストールされない」ため (prop_* ファイル自身と conftest.py が hypothesis を import するため、hypothesis 未インストールでは実行できない。3.14t での hypothesis 実行可否は未検証)
- `build_ft_ubuntu` には `astral-sh/setup-uv` ステップが無いため、テストステップと合わせて追加する (uv と Python 3.14t の準備に必要。他ジョブの実装と同様)
- Windows では `shell: bash` 指定と `.venv-ft/Scripts/` のパス (venv 名は macos のテストステップと同じ `.venv-ft`。実行ファイルのパス形式は abi3 windows ジョブの `.venv/Scripts/` 実装に合わせる) にする

## 完了条件

- ubuntu (x86_64 / arm64) の 3.14t wheel でテストが実行される
- windows の 3.14t wheel でテストが実行される
- 既存の Free-Threading テストが全通過する

## 解決方法

1. `.github/workflows/wheel.yml` の `build_ft_ubuntu` に `astral-sh/setup-uv` ステップと、`build_ft_macos` と同じテストステップを追加した (ubuntu-24.04 / ubuntu-24.04-arm 両方)
2. `build_ft_windows` に同様のテストステップを追加した (shell: bash と `.venv-ft/Scripts/` パス。実行ファイルのパス形式は abi3 windows ジョブの実装を踏襲)
3. ブランチ名を `feature/add-free-threading-wheel-tests` に変更した (当初の `feature/test-` は shiguredo-git の命名規則に該当しないため。0016 の先例と同様)
4. CHANGES.md の `### misc` に「[UPDATE] Free-Threading wheel の ubuntu / windows ビルドでテストを実行する」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
5. develop への push で CI が通ることを確認した
