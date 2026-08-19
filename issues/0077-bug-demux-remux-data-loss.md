# demux 経由のデータ劣化 (channelcount 切り詰め / Flac ブロック種別 / HEVC array_completeness / avc1 sps_ext) を解消する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-demux-remux-data-loss
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

外部の MP4 ファイルを demux して remux したときに、合法だが非標準的な入力で静かにデータが劣化する経路を解消する。破損検出を謳う本バインディングとして、無言の劣化をなくすか、明示的に検出する。

## 現状

`src/lib.rs` の各 SampleEntry の `from_box` (demux 経路) に、データが黙って失われる箇所がある:

1. **channelcount の u16 → u8 切り詰め**: `Mp4SampleEntryOpus::from_box` / `Mp4SampleEntryMp4a::from_box` / `Mp4SampleEntryFlac::from_box` は `b.audio.channelcount as u8` で保持する。コアの `AudioSampleEntryFields.channelcount` は u16 のため、255 を超えるチャンネル数のトラックは demux で静かに切り詰められ、remux で別の値のトラックが書かれる

2. **Flac の先頭ブロックを無条件に STREAMINFO とみなす**: `Mp4SampleEntryFlac::from_box` は `metadata_blocks.first()` の `block_data` を無条件に `streaminfo_data` として公開する。`FlacMetadataBlock::block_type` の確認がなく、先頭ブロックが STREAMINFO 以外のファイルでは誤ったデータを公開し、remux で破損を書き出す可能性がある

3. **HEVC の array_completeness の喪失**: `HevcCommon::to_hvcc` は `HvccNalUintArray { array_completeness: Uint::new(0), ... }` と常に 0 を書く。外部 HEVC ファイルで 1 のことが多い array_completeness ビットが remux で常に 0 に潰れる

4. **AVC1 の sps_ext の喪失**: `Mp4SampleEntryAvc1::to_sample_entry` は `sps_ext_list: Vec::new()` で常に空にする。SPS 拡張 (SPS ext NAL unit) を持つファイルのデータが remux で失われる

## 設計方針

- 各項目について、値の公開方法を拡張する (u16 で公開 / block_type を確認する / array_completeness を保持する / sps_ext を公開する) か、非対応であることを明示的に検出してエラーにするかを判断する
- 公開 API の互換性を考慮し、公開フィールドの追加は ADD、検出の追加はバグ修正として扱う

## 完了条件

- 上記のデータ劣化経路が解消される
- 各項目の挙動がテストで固定される (特性化テストまたはエラーテスト)
- 既存テストが全通過する
