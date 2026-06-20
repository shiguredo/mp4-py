# 変更履歴

- CHANGE
  - 後方互換性のない変更
- UPDATE
  - 後方互換性がある変更
- ADD
  - 後方互換性がある追加
- FIX
  - バグ修正

## develop

- [CHANGE] `Mp4FileMuxerOptions.reserved_moov_box_size` を `uint32` で受け取るようにする
  - mp4-rust 2026.2.0 の C API 型変更 (`u64` → `u32`) に追従する
  - @voluntas
- [ADD] `Mp4DemuxSample` に `composition_time_offset` プロパティを追加する
  - `ctts` / `trun` 由来のコンポジション時間オフセットを `int | None` で参照できる
  - @voluntas
- [ADD] `Mp4MuxSample` に `composition_time_offset` 引数とプロパティを追加する
  - 指定した場合は `ctts` ボックスを生成する
  - @voluntas
- [UPDATE] mp4-rust を 2026.3.0 に上げる
  - @voluntas
- [UPDATE] nanobind を 2.13.0 以上に上げる
  - @voluntas
- [UPDATE] scikit-build-core を 0.12.2 以上に上げる
  - @voluntas

### misc

- [UPDATE] hypothesis を 6.155.6 に上げる
  - @voluntas
- [UPDATE] pytest を 9.1.1 に上げる
  - @voluntas
- [UPDATE] ruff を 0.15.18 に上げる
  - @voluntas
- [UPDATE] ty を 0.0.51 に上げる
  - @voluntas

## 2026.1.0

**リリース日**:: 2026-01-07

**祝いリリース**
