# mp4_ext.cpp 2189 行の一枚岩を分割し、サンプルエントリー 9 種の三重構造を整理する

- Created: 2026-07-22
- Completed: 2026-07-22
- Branch: feature/refactor-split-mp4-ext-and-sample-entry-scaffolding
- Polished: {YYYY-MM-DD}

## 目的

`src/mp4_ext.cpp` は 2189 行 (NB_MODULE 内だけで 622 行) の一枚岩。サンプルエントリー 9 種すべてが「struct 定義 + from_raw + convert + binding」の三重〜四重構造で重複しており、1 コーデック追加や既存フィールド追加のたびに 4 箇所 (`AGENTS.md`「If it hurts, do it more often」に反する) を触る必要がある。ファイル分割と共通化で保守性を上げる。機能上のバグはないが、単一 .cpp の再コンパイルによるビルド時間、ファイル横断で見づらい PR 差分、同ファイルへの並行変更によるコンフリクトが継続的に効く。

## 現状

### ファイル構成

```
src/mp4_ext.cpp: 2189 行
├─ 定数・例外 (1-34 行)
├─ ユーティリティ (36-65 行)
├─ サンプルエントリー struct 9 種 (69-623 行, from_raw を含む)
├─ sample_entry_from_raw (626-652 行)
├─ TrackInfo (656-681 行)
├─ DemuxSample (685-755 行)
├─ Demuxer (759-1010 行)
├─ MuxerOptions + MuxSample (1014-1063 行)
├─ SampleEntryConverter (1067-1383 行)
├─ Muxer (1385-1562 行)
└─ NB_MODULE (1566-2188 行)
```

### サンプルエントリー 9 種の三重構造

各コーデックが以下 4 箇所を持つ:
- struct 定義 (69-623 行に集中)
- `static Xxx from_raw(const RawXxx& raw)` (同上)
- `void SampleEntryConverter::convert_xxx(...)` (1121-1382 行)
- `nb::class_<Xxx>(m, "Xxx", ...) ... .def_rw(...)` (1582-2028 行)

例えば Avc1 のフィールド 11 個は次の 4 か所すべてに現れる:
- `src/mp4_ext.cpp:69-104`: struct + コンストラクタ (11 個の引数)
- `src/mp4_ext.cpp:106-143`: from_raw (11 個をコピー)
- `src/mp4_ext.cpp:1121-1167`: convert_avc1 (11 個をコピー)
- `src/mp4_ext.cpp:1582-1646`: バインディング (`.def_rw` 11 個)

## 設計方針

### ファイル分割

```
src/mp4_ext.cpp                             (~150 行、NB_MODULE の骨組みのみ)
src/mp4_ext/
├─ exceptions.hpp                           (Mp4Exception, kMaxSampleSize)
├─ utilities.hpp                            (library_version, estimate_maximum_moov_box_size,
│                                            track_kind_to_string 等)
├─ track_info.hpp                           (PyMp4TrackInfo)
├─ sample_entry/
│  ├─ avc1.hpp                              (struct + from_raw + convert + register)
│  ├─ hevc.hpp                              (hev1 + hvc1 共通、issue 0011 で共通化)
│  ├─ vp0x.hpp                              (vp08 + vp09)
│  ├─ av01.hpp
│  ├─ audio.hpp                             (opus + mp4a + flac)
│  └─ dispatch.hpp                          (sample_entry_from_raw, SampleEntryConverter)
├─ demuxer.hpp                              (PyMp4DemuxSample + PyMp4FileDemuxer)
└─ muxer.hpp                                (PyMp4MuxSample + PyMp4FileMuxer + Options)
```

各ファイルに `void register_xxx(nb::module_& m);` を用意し、`NB_MODULE` は register 関数の呼び出し列のみに絞る。

### 三重構造の共通化

- HEVC 系は `issues/0011-refactor-hevc-hev1-hvc1-duplication.md` で template 化
- 単純フィールドのみのコーデック (VP08, VP09, Opus) は X-macro 相当で from_raw / convert を宣言的に記述
- 完全な reflection は C++20 では不可能なので、コーデック追加は依然「4 箇所編集」だが「1 コーデック = 1 ファイル」に集約される

### CMakeLists.txt

```cmake
nanobind_add_module(mp4_ext
  NB_DOMAIN "mp4"
  FREE_THREADED
  src/mp4_ext.cpp
)
target_include_directories(mp4_ext PRIVATE
  ${MP4_SOURCE_DIR}/include
  src
)
```

ヘッダオンリー実装なので追加ソースは不要 (register 関数はテンプレート化する場合を除く)。

## 完了条件

- `src/mp4_ext.cpp` が 300 行以下 (NB_MODULE の骨組みだけ) になる
- サンプルエントリー実装が 1 コーデック = 1 ファイルに集約される
- 全 PBT / 単体テスト / Free-Threading テストが通る
- ビルド時間が計測可能な範囲で悪化していないこと (可能なら改善)
- 新規コーデック追加手順を CODEBASE.md に追記

## 解決方法

1. `issues/0011-refactor-hevc-hev1-hvc1-duplication.md` の対応と同時に進めることを推奨
2. まず単純なコーデック (VP08 / VP09 / Opus) の分割から着手し、パターンを固める
3. 次に AVC1 / HEVC / AV01 / MP4A / FLAC を分割
4. 最後に DemuxSample / Demuxer / MuxSample / Muxer / Options を分割
5. `NB_MODULE` の内容を `register_xxx(m)` の羅列に置き換え
6. `SampleEntryConverter` は `dispatch.hpp` に集約
7. すべてのステップで `make develop && NO_UV_SYNC=1 uv run pytest` を実行し回帰がないことを確認
8. CMakeLists.txt 側で追加ヘッダの include path を確認

## 対応結果

バインディングを nanobind から PyO3 に置き換えた際、src/lib.rs の 1 ファイル構成となり、マクロと Rust の型システムで各サンプルエントリーの重複記述が排除された。C++ 版の三重〜四重構造 (struct / from_raw / convert / def_rw) が Rust では struct + to_sample_entry + from_box + `#[pyo3(get)]` のみに集約されている。よって closed とする。
