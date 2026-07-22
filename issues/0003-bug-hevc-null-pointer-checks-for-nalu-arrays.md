# HEV1 / HVC1 の from_raw で nalu_data / nalu_sizes / nalu_counts の NULL チェックが欠落

- Priority: High
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/fix-hevc-null-pointer-checks-for-nalu-arrays
- Polished: {YYYY-MM-DD}

## 目的

HEV1 / HVC1 サンプルエントリーの `from_raw` において、C API 側の `Mp4SampleEntryHev1` / `Mp4SampleEntryHvc1` が持つ複数のポインタフィールドのうち、`raw.nalu_types` のみ NULL チェックしており、`raw.nalu_data` / `raw.nalu_sizes` / `raw.nalu_counts` は NULL チェックせずに参照している。C API 契約上これらのフィールドは NULL 可能性が型で排除されていないため、破損データや上流変更で SEGV する可能性がある。同ファイル内の AVC1 実装 (`raw.sps_data && raw.sps_sizes` の複合チェック) と実装水準を揃える。

## 優先度根拠

High。

- 破損 MP4 データを扱う経路で SEGV する可能性があり、Python プロセス全体を落とす致命的欠陥。
- AVC1 側 (`src/mp4_ext.cpp:116, 124`) では既に複合 NULL チェックがあるにも関わらず、HEV1 / HVC1 だけで抜けている **一貫性の欠落**。同じ規約を後から追加した際の見落としと推測される。
- 修正は極めて限定的 (条件式 2 箇所の追加) で影響範囲が閉じている。

## 現状

`src/mp4_ext.cpp:235-247` (Hev1) と `src/mp4_ext.cpp:342-354` (Hvc1) はどちらも以下のパターン。

```cpp
if (raw.nalu_array_count > 0 && raw.nalu_types) {
  uint32_t offset = 0;
  for (uint32_t i = 0; i < raw.nalu_array_count; i++) {
    uint32_t count = raw.nalu_counts ? raw.nalu_counts[i] : 0;  // nalu_counts のみ null 対応
    for (uint32_t j = 0; j < count; j++) {
      result.nalu_types.push_back(raw.nalu_types[i]);
      uint32_t size = raw.nalu_sizes[offset + j];               // NULL 参照の可能性
      result.nalu_data.push_back(nb::bytes(
          reinterpret_cast<const char*>(raw.nalu_data[offset + j]),
          size));                                                 // NULL 参照の可能性
    }
    offset += count;
  }
}
```

一方 AVC1 (`src/mp4_ext.cpp:116-129`) では次のように複合チェックしている。

```cpp
if (raw.sps_count > 0 && raw.sps_data && raw.sps_sizes) {
  for (uint32_t i = 0; i < raw.sps_count; i++) {
    result.sps_data.push_back(nb::bytes(
        reinterpret_cast<const char*>(raw.sps_data[i]), raw.sps_sizes[i]));
  }
}
```

C API 側の型宣言 (`mp4.h:482-485` Hev1、`mp4.h:542-545` Hvc1) はいずれも `const uint32_t *` / `const uint8_t *const *` で NULL 可能性を型で排除していない。将来 mp4-rust 側の実装変更で NULL が返るようになった場合、C++ 側は SEGV する。

## 設計方針

- HEV1 / HVC1 の `from_raw` の複合 NULL チェックを AVC1 と同じ水準に揃える
- 全ポインタが揃った場合のみループを実行し、NULL があれば空の結果として扱う (AVC1 の挙動と同じ)

## 完了条件

- `src/mp4_ext.cpp:235` の Hev1 側と `src/mp4_ext.cpp:342` の Hvc1 側の条件が以下に統一される:
  ```cpp
  if (raw.nalu_array_count > 0 && raw.nalu_types && raw.nalu_data &&
      raw.nalu_sizes && raw.nalu_counts) {
    ...
  }
  ```
- 追加テスト: mp4-rust 側で NULL を返す状況を人工的に作るのは難しいが、少なくとも該当分岐が「全 NULL 揃わない場合は空 vec で返る」ことを assert するテストを 1 件追加

## 解決方法

1. `src/mp4_ext.cpp:235` の条件を書き換え:
   ```cpp
   if (raw.nalu_array_count > 0 && raw.nalu_types && raw.nalu_data &&
       raw.nalu_sizes && raw.nalu_counts) {
   ```
   同時に、`raw.nalu_counts ? raw.nalu_counts[i] : 0` の三項演算子は上位ガードで NULL が排除されているので `raw.nalu_counts[i]` に簡略化してもよい
2. `src/mp4_ext.cpp:342` の Hvc1 側にも同じ書き換えを適用
3. 本 issue の対応は `issues/0011-refactor-hevc-hev1-hvc1-duplication.md` と競合しうる。0011 でコピペ解消するタイミングでは、共通化された 1 箇所を修正する形になる

## 対応結果

バインディングを nanobind から PyO3 に置き換えたため、C API のポインタフィールドを Rust の Vec や参照経由でしか扱わなくなり、NULL チェック観点そのものが消滅した。よって closed とする。
