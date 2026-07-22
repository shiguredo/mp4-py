# PyMp4DemuxSample::data_size_ の型が C API の uintptr_t と不一致

- Priority: Low
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/refactor-data-size-type-consistency-with-c-api
- Polished: {YYYY-MM-DD}

## 目的

`Mp4DemuxSample.data_size` は C API 側で `uintptr_t` (mp4.h:928) だが、C++ 側の `PyMp4DemuxSample::data_size_` は `uint64_t` (`src/mp4_ext.cpp:698`)。64bit プラットフォームでは等価だが、意図が読みにくく、将来の C API 型変更や 32bit プラットフォーム対応時に脆弱。型を揃える。

## 優先度根拠

Low。

- 現状の対応プラットフォーム (`README.md:24-32`) は全て 64bit LP64/LLP64 なので実害はない。
- ただし、C API 側の型変更に追従漏れが起きる潜在リスク。`Mp4FileMuxerOptions.reserved_moov_box_size` の `u64 → u32` 変更 (`CHANGES.md:14-16`) と同種の追従作業がいずれ必要になる。
- 修正コストは型宣言 1 行 + `static_assert` 追加程度。

## 現状

`mp4.h:928`:
```c
uintptr_t data_size;
```

`src/mp4_ext.cpp:698`:
```cpp
uint64_t data_size_ = 0;
```

`src/mp4_ext.cpp:892-893` で raw から代入:
```cpp
result.data_offset_ = raw_sample.data_offset;
result.data_size_ = raw_sample.data_size;  // uintptr_t → uint64_t の暗黙変換
```

64bit プラットフォームでは `sizeof(uintptr_t) == sizeof(uint64_t) == 8` なので問題は表面化しない。32bit プラットフォームに移植した場合 (`sizeof(uintptr_t) == 4`) は uint64_t への拡張なので破損しないが、逆方向 (Muxer 側で size_t を uint32_t にキャストする箇所) は既に別 issue (`issues/0002-bug-integer-truncation-in-mux-demux-boundaries.md`) で扱っている。

## 設計方針

以下のいずれかを採用する。

### 方針 A (推奨): C++ 側も uintptr_t に揃える

- 型が完全に一致し、C API 契約が守られる
- 32bit プラットフォームに移植する際も追加変更不要

### 方針 B: 現状の uint64_t を維持し、`static_assert` で担保

```cpp
static_assert(sizeof(uintptr_t) == sizeof(uint64_t),
              "PyMp4DemuxSample::data_size_ assumes 64-bit platform");
```

- 意図を明確化するが、32bit プラットフォームでコンパイルエラー
- サポート範囲を明示的に絞る

`README.md:24-32` で 64bit プラットフォームのみサポートを明示しているため、方針 B でも十分。方針 A の方が型整合性が良い。

## 完了条件

- `PyMp4DemuxSample::data_size_` の型が `uintptr_t` に変更される (方針 A) または `static_assert` が追加される (方針 B)
- 全テスト通過
- CMakeLists.txt / README.md でサポートプラットフォーム範囲に変更がない

## 解決方法

### 方針 A の場合

1. `src/mp4_ext.cpp:698, 719` の `uint64_t data_size_` を `uintptr_t data_size_` に変更
2. `src/mp4_ext.cpp:702-719` のコンストラクタ引数の型も `uintptr_t` に変更
3. `src/mp4_ext.cpp:892-893` の代入は変更不要 (型が一致)
4. `src/mp4_ext.cpp:2055-2059` の `nb::init<..., uint64_t, uint64_t, ...>()` を `nb::init<..., uint64_t, uintptr_t, ...>()` に変更 (data_size のみ)
5. `PyMp4DemuxSample::get_data()` (`src/mp4_ext.cpp:721-739`) の `data_size_ > kMaxSampleSize` 比較は uint64_t + uint64_t の変換で問題なし

### 方針 B の場合

1. `src/mp4_ext.cpp:698` のフィールド定義直後に `static_assert(sizeof(uintptr_t) == sizeof(uint64_t), ...)` を追加
2. コメントで「64bit プラットフォームのみサポート」と明記

## 対応結果

C API 型 (`uintptr_t` など) との整合性の議論は、バインディングが Rust クレート `shiguredo_mp4` 直接呼び出しに置き換わったことで解消した。PyO3 版では `data_size: u64` を使用しており、mp4-rs の型定義とネイティブに整合する。よって closed とする。
