# 破損 MP4 の null 入り StppBox が黙って誤パースされる

- Created: 2026-08-16
- Completed: 2026-08-19
- Branch: feature/fix-stpp-null-box-silent-misparse
- Polished: 2026-08-19

## 目的

破損 MP4 の stpp ボックスに null バイトが含まれる場合のデマクス挙動を確認し、黙っての誤パース (データ欠損がエラーなしで進行する状態) の有無と対応の要否を判断する。

## 現状

コア (shiguredo_mp4 2026.4.0) の `Utf8String::decode` は null バイトで読み止める (null が終端まで見つからない場合のみエラー)。このため、null 入り stpp ボックスのデマクス挙動は破損パターンで分かれる:

- 文字列領域内の null 置換が 1 箇所だけの破損 (単一 null): フィールドが短く解釈され (フィールドずれ)、残りバイトが 8 バイト未満になり unknown box の読み取りが必ず失敗してデコードエラーになる。このエラーは 0036 (2026-08-16 完了) により `RuntimeError` として Python 側に届く (実測: 文字列領域の全バイト単一置換で全ケース検出)
- フィールド先頭からの連続 null: フィールドが空文字列として解釈され、残りバイトが size=0 (可変サイズ) の unknown box として成功するため、エラーなしで欠損値 (空文字列) が返る (実測: namespace / auxiliary_mime_types 全体の null 化で `namespace=''` 等が返る)

0031 (null 文字入り入力で panic する問題の修正) の対応は `Mp4SampleEntryStpp::new` の null 文字検証のみで、Python 側からの入力経路を塞ぐだけであり、デマクス時の破損データ経路は対象外のまま。

## 設計方針

- まずコアのデコード挙動を実際に確認する (null 入り stpp ボックスのデマクス結果)
- コア側 / バインド側 / 対応不要のいずれで対応すべきかを判断する
- バインド側の検出はデコード結果の検証に限られる。silent パターンは空文字列と size=0 (可変サイズ) の unknown box として現れるため、これらの検査が検出手段になり得るが、誤検知のリスクを含めて検出方式の実現可能性を判断する
- 検出した場合のエラーの報告方法は、破損データ由来エラーの型統一 (0053) の実装と整合させる
- コア側の修正が必要と判断された場合は、コア (shiguredo/mp4-rs) 側の issue として分離し、本 issue は調査結果の記録とテストで結了する

## 完了条件

- null 入り stpp ボックスに対するデマクス挙動が確認され、黙っての誤パースが起きる破損パターン (連続 null) と、エラーとして検出される破損パターン (単一 null) が切り分けられる
- 対応の要否が判断され、判断結果が ## 解決方法 に記録される
- バインド側で対応が必要な場合は、黙っての誤パースを検出できる仕組みが実装される

## 解決方法

調査と対応の判断結果を記録する。

1. コア (`shiguredo_mp4` 2026.4.0) の `Utf8String::decode` と `StppBox::decode` のデコード経路を再確認した
   - `Utf8String::decode` は null バイトで読み止める (null が終端まで見つからない場合のみエラー)。null 自体を検出するわけではない
2. null 入り stpp ボックスのデマクス挙動をテストで再現した (単一 null と連続 null の両パターン)
   - 単一 null (文字列領域内の 1 バイトを null 置換): フィールドずれにより残りバイトを unknown box として読む際にペイロード境界を超え、`Failed to decode MP4 box: [stpp] InsufficientBuffer` として RuntimeError が届く (破損検出の経路として機能している)
   - 連続 null (フィールド先頭からの連続 null): フィールドが空文字列として解釈され、残りバイトが size=0 (可変サイズ) の unknown box として成功するため、エラーなしで欠損値 (空文字列) が返る黙っての誤パースになる
3. 対応方針を確定した
   - 根因はコアの `Utf8String::decode` / `StppBox::decode` のデコード挙動にあり、コア側の対応として分離する。本 issue (mp4-py) は調査結果の記録と挙動の特性化テストで結了する
   - バインド側 (mp4-py) での namespace 空文字検出は不採用とした。理由は、仕様上非空の namespace が空で返ることを破損とみなす誤検知のリスク、コンストラクタが空 namespace を許容するため mux → demux の往復で自ファイルがエラーになる往復不整合、および schema_location / auxiliary_mime_types のみの破損は検出不能という部分カバレッジによる
   - コア側修正の対応は別途提案する (本 flow ではコアリポジトリに issue を作成しない)
4. 特性化テストを追加した (`tests/test_mp4.py`)
   - `test_stpp_demux_reports_single_null_corruption`: 単一 null が RuntimeError (`Failed to decode MP4 box: [stpp]`) になることを検証
   - `test_stpp_demux_silent_misparse_on_consecutive_null`: 連続 null がエラーなしで namespace / schema_location / auxiliary_mime_types を空文字列として返す既知ギャップを特性化
5. `CHANGES.md` の `## develop` の `### misc` にテスト追加のエントリを追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
6. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (124 passed, 7 skipped) を確認した
