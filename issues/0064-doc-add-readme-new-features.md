# README に 2026.2.0 の新機能を記載する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/doc-add-readme-new-features
- Polished: {YYYY-MM-DD}

## 目的

2026.2.0 で追加・変更された公開 API の使い方を README に反映し、リリースノートで宣伝する機能がドキュメントから辿れるようにする。

## 現状

README の基本 API 節に、2026.2.0 の develop サイクルで追加された機能の記載が一切ない:

- `Mp4Exception` による破損データ検出エラーの型分類 (README は `RuntimeError` としか書いておらず、推奨捕捉型 `Mp4Exception` に言及しない)
- `Mp4DemuxSample` / `Mp4MuxSample` の `composition_time_offset` (ctts)
- `Mp4TrackMetadata` による言語 (`mdhd.language`) / トラック名 (`hdlr.name`) の指定
- 字幕トラック (STPP / WVTT / TX3G) の mux / demux の実例
- `estimate_maximum_moov_box_size` の可変長引数化
- `.pyi` 型スタブの同梱
- `Mp4SampleEntry` の Union 型 (`mp4.Mp4SampleEntry`)

また「サンプル」節に `examples/version.py` の紹介がない。

## 設計方針

- 基本 API 節に上記の機能を追記する (コード例を添える)
- エラー処理の説明に `Mp4Exception` の捕捉例を追加する
- 「サンプル」節に `examples/version.py` を追加する
- 実装と一致することを確認してから記載する (examples の実装整合は issue 0027 等で別途対応)

## 完了条件

- README に 2026.2.0 の新機能が記載されている
- 記載されたコード例が実際に動作する
- 既存の記載との整合が取れている
