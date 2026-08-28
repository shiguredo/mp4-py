# パースエラーメッセージにビルド環境の絶対パスが露出する

- Created: 2026-08-16
- Completed: 2026-08-28
- Branch: feature/fix-error-message-absolute-path
- Polished: {YYYY-MM-DD}

## 目的

パースエラーを Python 側に報告するようになった結果、`RuntimeError` のメッセージにビルドマシンの絶対パス (cargo レジストリ配下のソースファイルパス) が含まれるようになった。配布パッケージのエラーメッセージにビルド環境情報が含まれるのは情報開示・品質の問題であり、解消する。

## 現状

コア (shiguredo_mp4 2026.4.0) の `Error` の Display 実装が常に `(at {file!()}:{line!()})` を付加するため、パースエラーが Python 側に届く際にビルドマシンのユーザー名と絶対パスが露出する。実測したメッセージの形は次のとおりである (ビルド環境のパス部は `<ビルド環境の絶対パス>` に置き換えてある)。

```
mp4 error: Failed to decode MP4 box: InvalidData: Expected box type `ftyp`, but got `\x00\x00\x00\x00` (at <ビルド環境の絶対パス>/basic_types.rs:461)
```

パースエラーの握りつぶし修正 (0036) により初めてユーザーに露出するようになった。

## 設計方針

- バインド側 (`mp4-py`) で `(at ...)` 部分を除去するか、コア側 (shiguredo/mp4-rs) に Display の変更を依頼するかを検討する
- バインド側で除去する場合は、メッセージ末尾の `(at ...)` を正規表現で除去する方式の妥当性を検討する (コアの Display 形式に依存するため、コアのバージョン更新で壊れうる点に注意)
- コア側で対応する場合は、shiguredo/mp4-rs に issue を立てて、`file!()` の代わりにモジュール名のみを表示する等の変更を依頼する

## 完了条件

- `RuntimeError` のメッセージにビルドマシンの絶対パスが含まれない
- エラーメッセージの可読性が維持される (エラー種別・原因の説明は残る)

## 解決方法

コア側で対応された。shiguredo_mp4 2026.5.0 で `Error` の Display が `shorten_source_path` を通すようになり、最後方の `src/` 以降だけを報告する形に変わった。本リポジトリでは 2026.5.0 への追従 (commit `1f292c1`) により解消している。

1. `(at ...)` の付加はコアの `Error` の Display 実装 (shiguredo_mp4 の codec 層) であることを特定した
2. バインド側で除去するのではなく、コア側の Display 変更によって解決した (バインド側で正規表現による除去はしていない)
3. 2026-08-28 に実測で確認した。破損入力のデマクスは `mp4 error: Failed to decode MP4 box: InvalidData: Expected box type ftyp, but got ... (at src/basic_types.rs:461)` の形になり、ビルドマシンの絶対パスも cargo レジストリへのパスも含まれない
4. エラー種別・理由・ボックス型はそのまま残っており、可読性は維持されている
5. 2026-08-28 に `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で 124 passed / 7 skipped を確認した
