# demux 経由のデータ劣化 (channelcount 切り詰め / HEVC array_completeness / avc1 sps_ext) を解消する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-demux-remux-data-loss
- Polished: 2026-08-30
- Milestone: 2026.2.0

## 目的

外部の MP4 ファイルを demux して remux したときに、合法な入力 (標準的・非標準的を問わず) で静かにデータが劣化する経路を解消する。破損検出を謳う本バインディングとして、無言の劣化をなくすか、明示的に検出する。

## 現状

`src/lib.rs` の各 SampleEntry の `from_box` (demux 経路) に、データが黙って失われる箇所がある:

1. **channelcount の u16 → u8 切り詰め**: `Mp4SampleEntryOpus::from_box` / `Mp4SampleEntryMp4a::from_box` / `Mp4SampleEntryFlac::from_box` は `b.audio.channelcount as u8` で保持する。コアの `AudioSampleEntryFields.channelcount` は u16 であり、`decode` は値域を検証しないため、255 を超えるチャンネル数のトラックは demux で静かに切り詰められ、remux で別の値のトラックが書かれる

2. **HEVC の array_completeness の喪失**: `HevcCommon::to_hvcc` は `HvccNalUintArray { array_completeness: Uint::new(0), ... }` と常に 0 を書く。コアの `HvccBox::decode` は `array_completeness` を読んで保持するが、`HevcCommon::from_hvcc` は参照しないため、外部 HEVC ファイルで 1 のことが多い array_completeness ビットが remux で常に 0 に潰れる

3. **AVC1 の sps_ext の喪失**: `Mp4SampleEntryAvc1::to_sample_entry` は `sps_ext_list: Vec::new()` で常に空にする。コアの `AvccBox::decode` は `sps_ext_list` を読んで保持するが、`Mp4SampleEntryAvc1::from_box` は参照しないため、SPS 拡張 (SPS ext NAL unit) を持つファイルのデータが remux で失われる

なお、Flac の先頭メタデータブロックは対応不要である。コアの `DflaBox::decode` は先頭ブロックを STREAMINFO (block_type=0) に制約しており、非 STREAMINFO の先頭ブロックは demux の時点でエラーとして検出される。このため `Mp4SampleEntryFlac::from_box` が `metadata_blocks.first()` の `block_data` を無条件に `streaminfo_data` として公開しても、誤ったデータを公開する経路は存在しない。

## 設計方針

各項目は「値を保持して引き継ぐ (変更履歴の種別は ADD)」か「非対応であることを明示的に検出してエラーにする (変更履歴の種別は FIX)」かのどちらかで対応する。判断基準は次のとおり:

- 公開属性の追加だけで保持できるものは保持する (ADD)
- 公開属性の型変更 (u8 → u16 など) を伴う破壊的変更が必要で、かつ実用上ほぼ発生しない入力であるものは、検出してエラーにする (FIX)
- demux 経路 (`from_box`) は入力データ由来の値をそのまま保持する既存方針に従う

各項目の対応方針は次のとおり:

- **channelcount**: 255 超のチャンネル数は実用上ほぼ発生しないため、`from_box` で 255 超を検出して `Mp4Exception` にする (FIX)。公開属性 `channel_count` を u8 から u16 に拡張する破壊的変更は行わない
- **HEVC array_completeness**: `HevcCommon` に array_completeness を追加して保持し、hvcc へ引き継ぐ (ADD)
- **AVC1 sps_ext**: `Mp4SampleEntryAvc1` に sps_ext を追加して保持し、avcC へ引き継ぐ (ADD)

## 完了条件

- 各項目の対応方針が実装されている (channelcount は 255 超を `Mp4Exception` で検出、array_completeness と sps_ext は保持)
- 各項目の挙動がテストで固定される (検出はエラーテスト、保持は roundtrip で値が引き継がれることを検証するテスト)
- 既存テストが全通過する
