# 値検証のエラーメッセージに実際の値が含まれず、期待値だけのものと不統一

- Created: 2026-08-29
- Completed: {YYYY-MM-DD}
- Branch: feature/update-validation-error-message-value
- Polished: {YYYY-MM-DD}

## 目的

shiguredo-python スキルのエラーメッセージ規約 (期待値と実際の値を示すこと) に照らして、`src/lib.rs` の値検証系エラーメッセージの形式を統一する。実際の値が載っていないメッセージは、利用者が入力側のどこを直せばよいか特定できない。

## 現状

`src/lib.rs` 内で、実際の値を載せている検証メッセージと載せていない検証メッセージが混在している。

実際の値を載せているもの:

- `validate_range` の `{name} must be 0..=0x{max:x}, got 0x{value:x}` (ビット幅検証全般)
- `validate_vpcc` の `bit_depth must be 8, 10 or 12, got {bit_depth}`
- `extract_bytes` の `expected bytes, bytearray, memoryview or an iterable of int (0-255), got {type_name}`

実際の値を載せていないもの:

- `Mp4SampleEntryTx3g::new` の `background_color_rgba must be exactly 4 bytes` と `default_style text_color_rgba must be exactly 4 bytes`
- `Mp4SampleEntryHev1::new` / `Mp4SampleEntryHvc1::new` 共通の `nalu_types and nalu_data must have the same length`
- `Mp4SampleEntryStpp::new` の `namespace must not contain null characters` / `schema_location must not contain null characters` / `auxiliary_mime_types must not contain null characters`
- `Mp4TrackInfo::new` と `Mp4FileMuxer::append_sample` 内の `NonZeroU32` チェックの `timescale must be non-zero` (`Mp4MuxSample::new` は `timescale=0` を検証しないため、エラーは `append_sample` で届く)
- `Mp4TrackMetadata::to_core` の `name must not contain null characters`

長さの検証では実際の長さを、件数の不一致ではそれぞれの件数を、null 文字の検証では該当する位置を、`timescale` の検証では実際の値を、それぞれ示せるにもかかわらず、いずれも期待値だけが返っている。

テストは `pytest.raises(ValueError, match=...)` で文言の部分一致に依存しているため、文言を変える場合は `tests/test_mp4.py` と `tests/prop_*.py` の追従が必要になる。

## 設計方針

- 実際の値を追記する形式に統一する。接頭辞の語順は `validate_range` の既存形式 (期待値, got 実際の値) に揃える
- バイト列・文字列の長さを示す場合は長さの数値を示し、データ本体をそのまま埋め込まない (大容量データや利用者の文章内容がエラーメッセージに載るのを防ぐ)。null 文字の検証は位置 (インデックス) を示す
- エラーメッセージは英語・末尾ピリオド無しという既存規約を守る
- 文言変更は後方互換のある変更として扱い、既存テストの `match` パターンを新しい文言へ追従させる

## 完了条件

- 上記の「実際の値を載せていないもの」に列挙した検証のメッセージが、期待値と実際の値の両方を含む
- 実際の値としてデータ本体がエラーメッセージに載っていない
- 全テストが通過し、文言に依存するテストが新しいメッセージへ追従している
