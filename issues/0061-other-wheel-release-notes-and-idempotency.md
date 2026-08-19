# wheel.yml の GitHub Release 本文・権限・再実行性を改善する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-wheel-release-notes-and-idempotency
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

`.github/workflows/wheel.yml` のリリースワークフローを、公開物の品質と運用の安全性の観点で改善する。具体的には以下の 3 点を扱う:

1. GitHub Release の本文が空のまま作成される
2. ビルドジョブへ不要な `contents: write` 権限が漏れる
3. 公開失敗後の再実行が「release already exists」で恒久失敗する

## 現状

### 1. GitHub Release の本文が空

`create_release` ジョブの `gh release create` に `--notes` / `--notes-file` がなく、Release body に CHANGES.md のリリースノートが載らない。checkout 済みなので `--notes-file CHANGES.md` を渡すだけでリリースノートが掲載できる。

### 2. 不要な権限の付与

workflow レベルの `permissions: contents: write, actions: read` を全ジョブが継承する。build 系 8 ジョブは checkout (contents: read) と artifact アップロードのみで write 権限は不要。`create_release` だけに `contents: write` を残し、他は最小権限化できる (`publish_pypi` は job レベルで `id-token: write` のみに絞られており、この方針と不整合)。

### 3. 再実行が恒久失敗する

`gh release create ${{ github.ref_name }}` は同名 release が存在するとエラーになる。publish_pypi が失敗した (例: ネットワーク一時エラー) 場合、修正後にワークフロー全体を再実行しても、先行して作成済みの GitHub Release が再実行のたびに失敗し、ジョブが常に failed のまま残る。`gh release view` での存在チェックなどで冪等に再実行できる仕組みがない。

## 設計方針

- `--notes-file CHANGES.md` を `gh release create` に渡す
- workflow レベルの `permissions` を最小化し、`create_release` のみ job レベルで `contents: write` を付与する
- リリース作成前に `gh release view` で既存リリースの有無を確認し、存在する場合はスキップまたはエラーを明確にする (再実行可能にする)

## 完了条件

- GitHub Release の本文に CHANGES.md の内容が掲載される
- ビルドジョブに不要な write 権限が付与されない
- 公開途中で失敗しても、再実行でリリースを完了できる
- 既存の公開フロー (develop push / tag push) が従来どおり動作する
