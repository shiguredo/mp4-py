# dev.py にブランチ制約と安全確認を追加する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-dev-py-branch-guard
- Polished: {YYYY-MM-DD}

## 目的

canary リリース用スクリプト `dev.py` が、想定外のブランチや中途半端なローカル状態から PyPI 公開タグを打つ危険をなくす。リリース作業の安全性を高める。

## 現状

`dev.py` の `git_operations` は現在のブランチを無条件に push + tag する。以下のリスクがある:

- `on.push.tags: ["202*"]` (wheel.yml) により、feature ブランチ上で `dev.py` を実行すると、そのコミットから canary リリースが PyPI に公開される。develop ブランチ限定のガードがない
- 作業ツリーの dirty 状態・既存タグ名の衝突をチェックせずに `git commit` → `git tag` → `git push` を自動実行する。失敗時は素の traceback になり、バージョンだけ変更された未コミット状態が残る
- バージョン書き換え (`write_version`) の後に `uv sync` が失敗すると、バージョンだけ変わった未コミット状態で停止する

## 設計方針

- 実行前に以下を検証してから操作を開始する
  - 現在のブランチが develop であること
  - 作業ツリーが clean であること
  - タグが既に存在しないこと
- `uv sync` の失敗時は version の書き換えを巻き戻すか、その旨を明確に報告する
- 各ステップの失敗時に中途半端な状態が残らないようにする

## 完了条件

- develop 以外のブランチで `dev.py` を実行すると、操作を開始せずエラーで停止する
- dirty な作業ツリーで実行するとエラーで停止する
- 既存タグと衝突する場合はエラーで停止する
- 既存の canary リリースフローが従来どおり動作する
