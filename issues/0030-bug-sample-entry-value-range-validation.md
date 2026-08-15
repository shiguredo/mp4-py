# SampleEntry コンストラクタの値域未検証でビット幅超過の黙った切り捨て・隣接フィールド汚染が起きる

- Priority: High
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-sample-entry-value-range-validation
- Polished: 2026-08-15

## 目的

`Mp4SampleEntry*` 系コンストラクタがフィールドの値域を検証しないため、コアクレートのビット幅を超える値がエラーにならずに「黙って切り捨て」または「隣接フィールドの値の汚染」を起こし、不正な MP4 が静かに生成される状態を解消する。

## 優先度根拠

High。

- 値域外の値がエラーにならず、不正な MP4 が静かに生成される (データ破壊)
- 既存の検証 (Tx3g の 4 バイト固定長、timescale=0) との不整合
- 修正コストは小〜中 (各コンストラクタへの値域検証追加 + テスト)

## 現状

コア (shiguredo_mp4 2026.4.0) の `Uint::to_bits` はマスクなしの単純シフト (`self.0 << OFFSET`) であり、エンコード時は各フィールドのビット列を OR 結合する。このためフィールド幅を超える値を渡すと:

- 黙って切り捨て (デコード時に別の値になる)
- 隣接フィールドのビットを汚染 (デコード時に隣のフィールドの値が変わる)

具体例 (いずれも `src/lib.rs` の該当コンストラクタで検証がなく、コアのフィールド定義から発生が確認できる):

- `Mp4SampleEntryAv01(seq_level_idx_0=32)` → ビット 5 が `seq_profile` 位置に混入し、デコードで `seq_profile=1` に化ける (seq_level_idx_0 は 5 ビット)
- `Mp4SampleEntryAv01(chroma_sample_position=4)` → ビット 2 が `chroma_subsampling_y` 位置に混入 (chroma_sample_position は 2 ビット)
- `Mp4SampleEntryHev1(general_profile_idc=32)` → ビット 5 が `general_tier_flag` 位置に混入 (general_profile_idc は 5 ビット)
- `Mp4SampleEntryHev1(num_temporal_layers=8)` → `constant_frame_rate=1` に化ける (num_temporal_layers は 3 ビット)
- `Mp4SampleEntryHev1(nalu_types=[128])` → `array_completeness=1` に化ける (nal_unit_type は 6 ビット)
- `Mp4SampleEntryVp08(chroma_subsampling=8)` → ビット 4 が `bit_depth` の最下位ビットに混入し、デコードで `bit_depth` が 1 増える (chroma_subsampling は 3 ビット。bit_depth 既定 8 の場合は 9 に化ける)
- `Mp4SampleEntryMp4a(buffer_size_db=0x1000000)` → 上位 8 ビットが黙って破棄され 0 に化ける (24 ビットフィールド)

検証を欠くコンストラクタ (全て `src/lib.rs`):

- `Mp4SampleEntryVp08::new` / `Mp4SampleEntryVp09::new`: `bit_depth` (4 ビット) / `chroma_subsampling` (3 ビット)
- `Mp4SampleEntryAvc1::new`: `length_size_minus_one` (2 ビット) / `chroma_format` / `bit_depth_luma_minus8` / `bit_depth_chroma_minus8` (いずれも reserved ビット固定で OR されるため、超過時は「隣接フィールドの汚染」にはならず、下位ビット幅分の値が残る「マスク」になる。例: `length_size_minus_one=5` → デコードで 1 に化ける)
- `Mp4SampleEntryHev1::new` / `Mp4SampleEntryHvc1::new`: ビット幅制約のあるフィールド (general_profile_space 2 ビット / general_tier_flag 1 ビット / general_profile_idc 5 ビット / general_constraint_indicator_flags 48 ビット / min_spatial_segmentation_idc 12 ビット / parallelism_type 2 ビット / chroma_format_idc 2 ビット / bit_depth_luma_minus8 3 ビット / bit_depth_chroma_minus8 3 ビット / constant_frame_rate 2 ビット / num_temporal_layers 3 ビット / temporal_id_nested 1 ビット / length_size_minus_one 2 ビット) と `nalu_types` (6 ビット)
  - 型幅とビット幅が一致する `general_profile_compatibility_flags` (u32) / `general_level_idc` (u8) / `avg_frame_rate` (u16) は検証不要
- `Mp4SampleEntryAv01::new`: ビット幅制約のある全フィールド (seq_profile 3 ビット / seq_level_idx_0 5 ビット / seq_tier_0 1 ビット / high_bitdepth 1 ビット / twelve_bit 1 ビット / monochrome 1 ビット / chroma_subsampling_x 1 ビット / chroma_subsampling_y 1 ビット / chroma_sample_position 2 ビット / initial_presentation_delay_minus_one 4 ビット)
- `Mp4SampleEntryMp4a::new`: `buffer_size_db` (24 ビット)

対照的に `Mp4SampleEntryTx3g::new` は 4 バイト固定長の検証を、`Mp4TrackInfo::new` は `timescale=0` の検証を行っており、この系だけが未検証。Opus / Flac は全フィールドが型幅 = フィールド幅のため対象外。

テスト (`tests/conftest.py`) のストラテジーは全て値域内を生成する (上限値を含むが上限超は生成しない) ため、現状のテストでは検出できない。

## 設計方針

- 各コンストラクタ (`new`) でフィールドの値域を検証し、型幅内 (u8 / u16 / u32 / u64 の範囲内) かつビット幅外の値に `PyValueError` を返す (Tx3g の 4 バイト検証と同じ方式)。Rust 型幅を超える入力は PyO3 が `OverflowError` で拒否するため対象外
- 検証の基準値はコアのフィールド定義 (ビット幅) を一次資料とする。意味論的な制約は、コアの doc コメントに明記されているフィールドに限ってビット幅の検証に加えて検証する (例: vpcC の `bit_depth` は 8 / 10 / 12)。`initial_presentation_delay_minus_one` は `initial_presentation_delay_present=false` でコアに渡らない場合でも常時検証する (不正値を構築時に弾く)
- エラーメッセージは英語で、期待する値域を含める
- 注意: `tests/conftest.py` の変更は PBT カバレッジ拡張 (別 issue で AVC1 High Profile 等を追加予定) と競合しうるため、境界値の追加は roundtrip が成立するフィールドに限定する。特に:
  - avcC は非 Baseline/Main/Extended プロファイルのときのみ `chroma_format` 等を書き込むため、それらの境界値の PBT 化はプロファイル追加と組み合わせる (単独では roundtrip が成立しない)
  - av1C の `initial_presentation_delay_minus_one` は `initial_presentation_delay_present=true` のときのみ書き込まれるため、境界値の PBT 化は present=true と組み合わせる
  - 追加する境界値は本 issue が新設する値域検証を通過する値に限定する (意味論的検証で拒否される値を入れると PBT が失敗する)

## 完了条件

- 型幅内かつビット幅外の値を各コンストラクタに渡すと `ValueError` が発生し、不正な MP4 が生成されない
- 値域内の値は従来どおり動作する (PBT が全通過する)
- 境界値 (上限ちょうど・上限 +1) のテストが追加される

## 解決方法

1. `src/lib.rs` の各 SampleEntry コンストラクタに値域検証を追加する (検証対象は「現状」セクションの列挙のとおり。Hev1/Hvc1 は `nalu_types` を含む)
2. `tests/test_mp4.py` に境界値 (上限 +1) で `ValueError` になることを検証するテストを追加する
3. `tests/conftest.py` のストラテジーに、roundtrip が成立するフィールドの上限値を含めて PBT でエンコード → デコード roundtrip が成立することを確認する (avc1 の `chroma_format` 等はプロファイル追加と組み合わせる)
4. CHANGES.md の `## develop` に「[FIX] SampleEntry コンストラクタの値域検証を追加する」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
5. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
