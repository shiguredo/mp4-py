# パースエラーメッセージにビルド環境の絶対パスが露出する

- Created: 2026-08-16
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-error-message-absolute-path
- Polished: {YYYY-MM-DD}

## 目的

パースエラーを Python 側に報告するようになった結果、`RuntimeError` のメッセージにビルドマシンの絶対パス (`(at /Users/voluntas/.cargo/registry/.../basic_types.rs:461)`) が含まれるようになった。配布パッケージのエラーメッセージにビルド環境情報が含まれるのは情報開示・品質の問題であり、解消する。

## 現状

コア (shiguredo_mp4 2026.4.0) の `Error` の Display 実装が常に `(at {file!()}:{line!()})` を付加するため、パースエラーが Python 側に届く際にビルドマシンのユーザー名と絶対パスが露出する:

```
mp4 error: Failed to decode MP4 box: InvalidData: Expected box type `ftyp`, but got `\x00\x00\x00\x00` (at /Users/voluntas/.cargo/registry/src/index.crates.io-.../basic_types.rs:461)
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

1. コアの Display 実装を確認し、`(at ...)` の付加がどのレイヤーで行われているかを特定する
2. バインド側で除去するかコア側へ依頼するかを判断する
3. 対応を実装し、テストを追加する
4. 全テスト通過を確認する
