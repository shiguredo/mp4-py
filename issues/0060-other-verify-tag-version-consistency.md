# リリースパイプラインにタグと pyproject バージョンの一致検証を追加する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-verify-tag-version-consistency
- Polished: {YYYY-MM-DD}

## 目的

GitHub Actions のリリースワークフローが、プッシュされたタグ名と pyproject.toml のバージョンの一致を検証せずに PyPI へ公開してしまうリスクを解消する。バージョン更新忘れによる pre-release の誤公開を防ぐ。

## 現状

`.github/workflows/wheel.yml` の `publish_pypi` ジョブのゲートは `if: contains(github.ref, 'tags/202')` のみで、タグ名と `pyproject.toml` の `[project] version` の一致を検証する箇所がない。

`pyproject.toml` の version が `2026.2.0.dev2` のままタグ `2026.2.0` を push すると:

- maturin が pyproject の version を使って wheel を組むため、PyPI に pre-release の `2026.2.0.dev2` が公開される (`uv add mp4-py` は pre-release を解決しないため、利用者は古い 2026.1.0 のまま取り続ける)
- GitHub Release はタグ名から final の `2026.2.0` として作成され、公開物同士が食い違う
- PyPI はファイル削除不可のため、誤って公開した pre-release の取り消しができない

CODEBASE.md のリリース手順にもこの整合を確認するステップがなく、唯一の防衛線は作業者の目視になっている。

## 設計方針

- リリースジョブの冒頭でタグ名と pyproject.toml の version を突き合わせる検証ステップを追加する
- 不一致の場合はジョブを失敗させ、公開を停止する
- 検証は Python の 1 スクリプトかシェルの grep で実現できる (例: `python -c` で pyproject.toml の version を読み、`$GITHUB_REF_NAME` と比較)

## 完了条件

- version が dev 付きのまま tag を push すると、公開前にジョブが失敗する
- 一致する場合は従来どおり公開される
- リリース手順 (CODEBASE.md) にこの検証の言及が追記される
