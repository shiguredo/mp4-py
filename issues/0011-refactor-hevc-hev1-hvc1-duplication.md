# HEV1 / HVC1 の struct / from_raw / convert / binding が完全コピペ (200+ 行の重複)

- Priority: Medium
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/refactor-hevc-hev1-hvc1-duplication
- Polished: {YYYY-MM-DD}

## 目的

`src/mp4_ext.cpp` の HEV1 / HVC1 サンプルエントリー実装が完全コピペ (フィールド定義 20 個、コンストラクタ引数 20 個、from_raw 40 行以上、convert 50 行以上、`.def_rw` バインディング 20 個) になっている状態を解消し、将来のフィールド追加時に片方だけ変更する事故を防ぐ。

## 優先度根拠

Medium。

- 現時点で機能上のバグではないが、`AGENTS.md`「Don't live with broken windows」「一切妥協をしないこと」に真っ向から反する。
- 実際に diff を取ると差分は `Hev1` / `Hvc1` の名前置換 6 行のみ。C API 側 (`mp4.h:462-486` Hev1 / `mp4.h:522-546` Hvc1) もフィールド完全一致。
- 過去 commit `efe3934` でリファクタし `1d8145d` で revert された経緯があり、revert 理由が不明のまま重複が残っている。技術的負債として顕在化している。
- 新規コーデック追加や既存フィールド追加の際に 6 箇所 (struct×2 + convert×2 + binding×2) を触ることになり、片方だけ変更する事故が非常に容易。
- 修正コストは大きいがテストで担保できる。

## 現状

以下がすべて型名以外完全一致 (`diff` で確認):

- `src/mp4_ext.cpp:146-251` (Hev1 struct + from_raw) と `src/mp4_ext.cpp:253-358` (Hvc1 struct + from_raw): 差分は `Hev1` / `Hvc1` の名前置換 6 行のみ
- `src/mp4_ext.cpp:1169-1221` (convert_hev1) と `src/mp4_ext.cpp:1223-1275` (convert_hvc1): 完全一致 (kind と data.hev1 / data.hvc1 の差だけ)
- `src/mp4_ext.cpp:1648-1754` (Hev1 binding) と `src/mp4_ext.cpp:1756-1862` (Hvc1 binding): docstring 冒頭以外完全一致

C API 側:
```c
typedef struct Mp4SampleEntryHev1 {
  uint16_t width;
  uint16_t height;
  // ... 20 フィールド
} Mp4SampleEntryHev1;

typedef struct Mp4SampleEntryHvc1 {
  uint16_t width;
  uint16_t height;
  // ... 20 フィールド (完全一致)
} Mp4SampleEntryHvc1;
```

## 設計方針

### 方針 A (推奨): template で共通化

`Mp4SampleEntryHev1` と `Mp4SampleEntryHvc1` がフィールド完全一致なので、共通のヘルパテンプレートを用意する。

```cpp
template <Mp4SampleEntryKind Kind, typename Raw>
struct PyMp4SampleEntryHevcBase {
  uint16_t width = 0;
  uint16_t height = 0;
  // ... 20 フィールド
  std::vector<uint8_t> nalu_types;
  std::vector<nb::bytes> nalu_data;

  static PyMp4SampleEntryHevcBase from_raw(const Raw& raw) {
    PyMp4SampleEntryHevcBase result;
    // ... 40 行の共通ロジック
    return result;
  }
};

using PyMp4SampleEntryHev1 =
    PyMp4SampleEntryHevcBase<MP4_SAMPLE_ENTRY_KIND_HEV1, Mp4SampleEntryHev1>;
using PyMp4SampleEntryHvc1 =
    PyMp4SampleEntryHevcBase<MP4_SAMPLE_ENTRY_KIND_HVC1, Mp4SampleEntryHvc1>;
```

convert 側も同様に template 化:

```cpp
template <Mp4SampleEntryKind Kind, typename PyEntry, typename Raw>
void convert_hevc(PyEntry& entry, Mp4SampleEntry& raw_entry, /* buffers */) {
  raw_entry.kind = Kind;
  Raw* raw = nullptr;
  if constexpr (Kind == MP4_SAMPLE_ENTRY_KIND_HEV1) {
    raw = &raw_entry.data.hev1;
  } else {
    raw = &raw_entry.data.hvc1;
  }
  // ... 50 行の共通ロジック
}
```

バインディング側は関数として括り出す:

```cpp
template <typename PyEntry>
void register_hevc_binding(nb::module_& m, const char* name, const char* doc) {
  nb::class_<PyEntry>(m, name, doc)
      .def(nb::init<>())
      .def("__init__", ...)
      .def_rw("width", &PyEntry::width, ...)
      // ... 20 個の def_rw
      ;
}

// NB_MODULE 内:
register_hevc_binding<PyMp4SampleEntryHev1>(m, "Mp4SampleEntryHev1", "...");
register_hevc_binding<PyMp4SampleEntryHvc1>(m, "Mp4SampleEntryHvc1", "...");
```

### 方針 B: HEV1 を HVC1 の型エイリアスにする

- C API 側は別型なので単純なエイリアスは不可能
- nanobind の `nb::class_` は型ごとに別クラスを要求するため、この方針は取れない

### 方針 A が採用される。過去 revert (1d8145d) の理由を突き止め、同じ罠を踏まないよう対処する。

## 完了条件

- HEV1 / HVC1 の struct 定義が 1 つの template から派生する
- from_raw / convert / binding のロジック行数が現状の半分以下に減る
- 既存の PBT (`prop_hev1_fields_preserved` / `prop_hvc1_fields_preserved` in `tests/prop_sample_entry.py`) が全通過
- 過去 revert (commit `1d8145d`) の理由をコミットメッセージ / issue history から確認し、同じ罠を回避したことを PR 本文に明記
- `issues/0003-bug-hevc-null-pointer-checks-for-nalu-arrays.md` の対応後に着手 (NULL チェック追加を先に済ませてから共通化する方が差分が小さい)

## 解決方法

1. 過去 commit `efe3934` (HEVC リファクタ) と `1d8145d` (Revert) の差分を確認し、revert 理由を特定する
   ```bash
   git show efe3934
   git show 1d8145d
   ```
2. 問題の原因が nanobind の型登録に起因するのか、それとも他の理由 (テスト失敗など) かを見極める
3. 方針 A (template 共通化) で実装する
4. `src/mp4_ext.cpp:146-358` の 2 つの struct を template ベース + `using` エイリアスに置き換え
5. `src/mp4_ext.cpp:1169-1275` の 2 つの convert 関数を template ベースの 1 つに統合
6. `src/mp4_ext.cpp:1648-1862` の 2 つのバインディングを共通の register 関数に統合
7. `SampleEntryConverter::convert()` (`src/mp4_ext.cpp:1097-1117`) の isinstance ラダーは変更不要 (別クラスとして扱われるため)
8. 全 PBT を実行し、Hev1/Hvc1 の roundtrip が壊れていないことを確認
9. 本 issue 対応は `issues/0012-refactor-split-mp4-ext-and-sample-entry-scaffolding.md` (ファイル分割) の一部として実施してもよい

## 対応結果

バインディングを nanobind から PyO3 に置き換えた際、Hev1 / Hvc1 の共通コンポーネント (HevcCommon 構造体 + hevc_pyclass! マクロ) で重複を除去した。src/lib.rs の hevc_pyclass 定義参照。よって closed とする。
