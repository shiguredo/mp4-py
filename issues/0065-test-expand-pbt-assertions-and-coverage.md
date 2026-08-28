# Hev1 / Hvc1 / Av01 / Mp4a / Flac の roundtrip 保存 PBT の assert を拡充する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/test-expand-pbt-assertions-and-coverage
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

`tests/prop_sample_entry.py` のフィールド保存 PBT が、ストラテジーが生成するフィールドの多くを assert していないため、回帰が検出できない状態を解消する。Avc1 / Opus は issue 0021 (open) の対象のため、本 issue ではそれ以外の SampleEntry を扱う。

## 現状

ストラテジー (tests/conftest.py) が生成するにもかかわらず、`tests/prop_sample_entry.py` の roundtrip テストで assert されていないフィールドがある (実測では正しく保持されるため、assert 追加だけで検証が有効化できる):

- hev1 / hvc1: `general_profile_space` / `general_tier_flag` / `chroma_format_idc` / `bit_depth_luma_minus8` / `bit_depth_chroma_minus8` / `length_size_minus_one` (19 フィールド中 6 のみ assert)
- av01: `seq_tier_0` / `high_bitdepth` / `twelve_bit` / `monochrome` / `chroma_subsampling_x` / `chroma_subsampling_y` / `chroma_sample_position` (12 フィールド中 5 のみ assert)
- mp4a: `sample_size` / `buffer_size_db` / `max_bitrate` / `avg_bitrate` (未 assert)
- flac: `sample_size` (未 assert)

また、hvcC の getter が未公開 (issue 0056) のため、hev1/hvc1 のサブフィールドはそもそも読み戻せない。0056 の実装後に assert を追加する。

## 設計方針

- 各 SampleEntry の roundtrip テストに、未 assert のフィールドを追加する
- 追加前に実測で保持されることを確認し、保持されないフィールドがある場合は挙動の明確化を別途検討する
- hvcC の getter 公開 (issue 0056) に依存する項目は、その issue との整合を取る

## 完了条件

- 各 SampleEntry の全フィールドが roundtrip で assert される
- 既存テストが全通過する
