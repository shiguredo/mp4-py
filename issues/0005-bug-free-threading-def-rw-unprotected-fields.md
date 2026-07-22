# Free-Threading で def_rw で公開する複合型フィールドが nb::lock_self なしで race する

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-free-threading-def-rw-unprotected-fields
- Polished: {YYYY-MM-DD}

## 目的

nanobind の `def_rw` で公開している `std::vector<nb::bytes>` / `std::string` / `std::optional<...>` などの複合型フィールドに `nb::lock_self()` が付いておらず、Free-Threading ビルドで複数スレッドから同時アクセスすると heap-use-after-free / bad refcount / データ破壊が起きる可能性を解消する。

## 優先度根拠

High。

- `CMakeLists.txt:105` の `FREE_THREADED` 指定により Free-Threading ビルドを公式にサポートしている以上、公開フィールドは Free-Threading 安全である必要がある。
- Python 側の期待: `sample_entry.sps_data = [...]` と `for sps in sample_entry.sps_data: ...` を別スレッドから並列に実行しても壊れない (これは Python の通常の期待動作)。
- 現在の実装ではロックがないため、`std::vector` の move-assign 中に古い vector が破棄されつつ、getter が返した `const std::vector<nb::bytes>&` を Python 変換する経路と衝突すると、heap-use-after-free。`std::string kind` も SBO (Small Buffer Optimization) の切り替えでポインタが飛ぶ。
- 症状は Muxer 側 `SampleEntryConverter::convert` が渡された `entry` を isinstance 判定 + cast → `entry.sps_data` を舐めるループの中で起きうるため、実運用パスで発火する。

## 現状

nanobind の `def_rw` 実装は `nb_class.h:703-719` で `def_prop_rw` に単純なラムダを渡すだけで、`nb::lock_self()` を明示しない限り Free-Threading の暗黙ロックが付かない。

以下の `def_rw` は複合型を公開しているにも関わらず `nb::lock_self()` が指定されていない (`src/mp4_ext.cpp`):

- 1635-1638: Avc1 `sps_data` / `pps_data` (`std::vector<nb::bytes>`)
- 1751-1754: Hev1 `nalu_types` / `nalu_data`
- 1859-1862: Hvc1 `nalu_types` / `nalu_data`
- 1964: Av01 `config_obus` (`nb::bytes`)
- 1984: Opus `input_sample_rate` (`std::optional<uint32_t>`)
- 2011: Mp4a `dec_specific_info` (`nb::bytes`)
- 2027: Flac `streaminfo_data` (`nb::bytes`)
- 2039: TrackInfo `kind` (`std::string`)
- 2140-2154: MuxSample `track_kind` (`std::string`) / `sample_entry` (`nb::object`) / `data` (`nb::bytes`)

対して `def_ro` 公開の `PyMp4DemuxSample` はミューテーションを禁じている (`src/mp4_ext.cpp:2060-2073`)。API 対称性としても不整合。

## 設計方針

### 方針 A (推奨): 複合型 def_rw に一律 `nb::lock_self()` を付ける

- 保護コストは軽微 (アクセスごとに ft_mutex を取るだけ)
- Free-Threading ビルド以外では no-op
- 既存 API を変えずに Free-Threading 安全になる

### 方針 B: Demuxer 由来の値クラスを `def_ro` に固定

- ミューテーションを禁じ、変更したい場合は `Mp4SampleEntryAvc1(width=..., sps_data=[...])` で「作り直し」フローに寄せる
- API 変更が大きい。ユーザーコードの互換性が失われる

方針 A を採用する。

## 完了条件

- 上記 8 種類のフィールドすべての `def_rw` に `nb::lock_self()` が付く
- Free-Threading ビルドで「あるスレッドが `entry.sps_data` を反復中に別スレッドが `entry.sps_data = [...]` する」テストで crash / 不整合が起きない
- 追加テスト (`test_free_threading.py`): `Mp4SampleEntryAvc1` を共有し、複数スレッドから sps_data の read + write を並列実行して壊れないことを確認

## 解決方法

1. `src/mp4_ext.cpp` の以下の `def_rw` すべてに `nb::lock_self()` を追加:
   ```cpp
   .def_rw("sps_data", &PyMp4SampleEntryAvc1::sps_data,
           "List of SPS (Sequence Parameter Set) data",
           nb::lock_self())
   ```
   対象:
   - Avc1: sps_data, pps_data, chroma_format, bit_depth_luma_minus8, bit_depth_chroma_minus8
   - Hev1 / Hvc1: nalu_types, nalu_data, その他 std::string / std::vector を含むフィールド
   - Av01: config_obus
   - Opus: input_sample_rate
   - Mp4a: dec_specific_info
   - Flac: streaminfo_data
   - TrackInfo: kind
   - MuxSample: track_kind, sample_entry, data
2. スカラー型 (uint8_t / uint16_t / uint32_t / bool 等) は atomic な代入で済むので `nb::lock_self()` は付けない (ノイズを避ける)
3. `test_free_threading.py` に「同一 sample_entry オブジェクトの複合フィールドを並列に read/write する」テストを追加
4. 本 issue 対応後は `issues/0006-refactor-sample-entry-converter-unnecessary-copy.md` (別 issue) で `SampleEntryConverter` の不要コピーを削除可能になる
