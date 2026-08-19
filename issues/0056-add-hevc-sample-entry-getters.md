# Hev1 / Hvc1 の hvcC サブフィールド getter を公開する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/add-hevc-sample-entry-getters
- Polished: {YYYY-MM-DD}

## 目的

`Mp4SampleEntryHev1` / `Mp4SampleEntryHvc1` でコンストラクタが受け付ける hvcC の各フィールドを、demux 後に読み戻せるようにする。他 SampleEntry との API 対称性を確保する。

## 現状

`src/lib.rs` の hevc_pyclass! マクロが生成する getter は `width` / `height` / `general_profile_idc` / `general_level_idc` / `nalu_types` / `nalu_data` の 6 つのみ。一方コンストラクタは 20 引数を受け付けており、`general_profile_space` / `general_tier_flag` / `general_profile_compatibility_flags` / `general_constraint_indicator_flags` / `chroma_format_idc` / `bit_depth_luma_minus8` / `bit_depth_chroma_minus8` / `min_spatial_segmentation_idc` / `parallelism_type` / `avg_frame_rate` / `constant_frame_rate` / `num_temporal_layers` / `temporal_id_nested` / `length_size_minus_one` は設定できても読み戻せない。

比較対象の `Mp4SampleEntryAvc1` (11 属性) / `Mp4SampleEntryAv01` (14 属性) は全フィールドを getter 公開しており、Hev1/Hvc1 のみ非対称になっている。

帰結として、mux 前に設定した hvcC サブフィールドが demux 後に検証できないため、roundtrip の回帰検出も不可能になっている。

## 設計方針

- コンストラクタが受け付ける全フィールドに対応する getter を追加する
- 既存の hevc_pyclass! マクロ内に getter を追加するか、フィールド単位で一括公開する形を検討する
- 公開に伴い、roundtrip を検証する PBT (tests/conftest.py の st_hev1/st_hvc1 ストラテジー) の assert を拡充する

## 完了条件

- Hev1/Hvc1 の全コンストラクタ引数が getter で読み戻せる
- 各フィールドの roundtrip が PBT で検証される
- 既存テストが全通過する
