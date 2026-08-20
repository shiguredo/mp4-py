# SampleEntry の意味論的値域検証の不足 (Wvtt config / Tx3g justification / font_name 遅延エラー)

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-validate-sample-entry-semantic-ranges
- Polished: 2026-08-20
- Milestone: 2026.2.0

## 目的

2026.2.0 で新規公開する字幕系 SampleEntry のうち、仕様が定める意味論的な値域・形式の検証が欠けている箇所を解消する。不正な入力をコンストラクタで `ValueError` として早期に弾き、後段 (finalize) での遅延エラーや不正なボックスの黙った生成を防ぐ。

## 現状

`src/lib.rs` の SampleEntry コンストラクタのうち、ビット幅検証 (`validate_range`) は整備されている (closed issue 0030) が、意味論的な値域・形式の検証が不足している。いずれもコア (shiguredo_mp4) の doc コメントに制約が明記されており、0030 の方針 (「意味論的な制約は、コアの doc コメントに明記されているフィールドに限って検証する」) の残余である:

- `Mp4SampleEntryWvtt::new` は `config` に任意の文字列を受け入れる。空文字列や "WEBVTT" で始まらない文字列でもエラーなく受理し、不正な vttC を生成する。コアの `VttCBox::config` は「"WEBVTT" 行で始まる UTF-8 文字列」と定義されている
- `Mp4SampleEntryTx3g::new` の `horizontal_justification` / `vertical_justification` は `i8` 全域を受け入れる。コアの `Tx3gBox` の doc は `0 = left / 1 = centered / -1 = right` のみを定義している
- `Mp4SampleEntryTx3g` の `font_table` のフォント名はコアの `FontRecord::encode` で 1 バイト長の Pascal 文字列 (`font_name_length: u8`) に書かれるため、256 バイト以上は finalize 時点で `RuntimeError` になる。コンストラクタ受理 → append_sample 成功 → finalize で失敗するため、エラー発生点が入力から離れて分かりにくい

なお、検証はコンストラクタ (`new`) のみに追加する。demux 経路 (`from_box`) は入力データ由来の値をそのまま保持する既存方針のため検証対象外とする。

0054 (Tx3g デフォルト引数の破損) は `background_color_rgba` のデフォルト値の別バグであり、本 issue の justification / font_name / config 検証とは対象フィールドが異なるため重複しない。

## 設計方針

- `Mp4SampleEntryWvtt::new` は `config` が `"WEBVTT"` 始まりであることを検証する (コアの `VttCBox::config` の doc に合わせ、prefix 一致で判定する)
- `Mp4SampleEntryTx3g::new` は `horizontal_justification` / `vertical_justification` が `-1` / `0` / `1` のいずれかであることを検証する
- `Mp4SampleEntryTx3g::new` は `font_table` の各フォント名が 255 バイト以下であることを検証する (コアの `FontRecord::encode` の `u8::try_from(font_name.len())` が 256 以上で失敗する制約に合わせる)
- エラーメッセージは英語で、期待する値域を含める (0030 の方式を踏襲する)
- 単体テスト (`tests/test_mp4.py`) で不正値 (config が "WEBVTT" 始まりでない / justification が -1・0・1 以外 / font_name が 256 バイト以上) が `ValueError` になることと、境界値 (config が "WEBVTT" 始まり / justification が -1・0・1 / font_name が 255 バイト) で動作することを検証する
- 既存の `st_wvtt_sample_entry` / `st_tx3g_sample_entry` ストラテジー (tests/conftest.py) と、それを使う PBT (`prop_sample_entry.py` の `prop_wvtt_fields_preserved` / `prop_tx3g_fields_preserved`) は合法値のみを生成するため、検証追加後もそのまま成立する。PBT の変更は不要だが、全通過を確認する。PBT に境界値を追加する場合は、本 issue が新設する検証を通過する値 (font_name は 255 バイト以下) に限定する (0030 の注意を踏襲)

## 完了条件

- 不正な config ("WEBVTT" 始まりでない) / justification (-1・0・1 以外) / font_name (256 バイト以上) がコンストラクタで `ValueError` になる
- 合法な値 (config が "WEBVTT" 始まり / justification が -1・0・1 / font_name が 255 バイト以下) は従来どおり動作する
- 既存テストが全通過する
