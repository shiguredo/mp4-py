# SampleEntry の意味論的値域検証の不足 (Wvtt config / Tx3g justification / font_name 遅延エラー)

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-validate-sample-entry-semantic-ranges
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

2026.2.0 で新規公開する字幕系 SampleEntry のうち、仕様が定める意味論的な値域・形式の検証が欠けている箇所を解消する。コンストラクタで受け付けておきながら、後段 (finalize) で遅延エラーになる経路をなくす。

## 現状

`src/lib.rs` の SampleEntry コンストラクタのうち、ビット幅検証 (`validate_range`) は整備されているが、意味論的な値域の検証が不足している:

- `Mp4SampleEntryWvtt::new` は `config` に任意の文字列を受け入れる。空文字列や "WEBVTT" で始まらない文字列でもエラーなく受理し、不正な vttC を生成する。ISO/IEC 14496-30 では config は "WEBVTT" 始まりが必須
- `Mp4SampleEntryTx3g::new` の `horizontal_justification` / `vertical_justification` は `i8` 全域を受け入れる。3GPP TS 26.245 では -1 / 0 / 1 のみ許容
- `Mp4SampleEntryTx3g` の `font_table` のフォント名はコアの `FontRecord::encode` で Pascal 文字列 (1 バイト長) に書かれるため、256 バイト以上は finalize 時点で `RuntimeError` になる。コンストラクタ受理 → append_sample 成功 → finalize で失敗するため、エラー発生点が入力から離れて分かりにくい

## 設計方針

- 各コンストラクタで仕様が定める値域・形式を検証し、`ValueError` で早期に弾く
- フォント名の 255 バイト上限はコンストラクタ時点で検証する
- 検証を追加した箇所に PBT (tests/conftest.py の st_wvtt / st_tx3g ストラテジー) と単体テストを追加する

## 完了条件

- 不正な config / justification / font_name がコンストラクタで `ValueError` になる
- 合法な値は従来どおり動作する
- 既存テストが全通過する
