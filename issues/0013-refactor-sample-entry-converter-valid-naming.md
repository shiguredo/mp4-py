# SampleEntryConverter::valid の名称が実態と乖離しており「命名詐欺」になっている

- Priority: Low
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/refactor-sample-entry-converter-valid-naming
- Polished: {YYYY-MM-DD}

## 目的

`SampleEntryConverter::valid` フィールドの名称は「変換結果が妥当か」に読めるが、実態は「入力が None ではないか」の記録に過ぎない。エラー時 (`Unsupported sample entry type` の throw) には `valid = true` のまま。呼び出し側 (`src/mp4_ext.cpp:1478`) は `converter.valid ? &converter.raw_entry : nullptr` として「NULL 渡しは前サンプルと同じ」というセマンティクスの実現に使っている。命名と意味を一致させる。

## 優先度根拠

Low。

- 機能上のバグではないが、コードを読む際に強い誤解を招く。
- 修正コストは小さい (フィールド名の変更 + 数箇所の参照書き換え)。
- `issues/0012-refactor-split-mp4-ext-and-sample-entry-scaffolding.md` の対応時にまとめて実施してもよい。

## 現状

`src/mp4_ext.cpp:1071` でフィールド定義:

```cpp
class SampleEntryConverter {
 public:
  Mp4SampleEntry raw_entry;
  bool valid = false;
  ...
};
```

`src/mp4_ext.cpp:1089-1117` の `convert()`:

```cpp
void convert(nb::object entry) {
  if (entry.is_none()) {
    valid = false;
    return;
  }

  valid = true;                       // ← 先に true にしてから isinstance ラダー
  if (nb::isinstance<PyMp4SampleEntryAvc1>(entry)) {
    convert_avc1(nb::cast<PyMp4SampleEntryAvc1&>(entry));
  } else if (...) {
    ...
  } else {
    throw Mp4Exception("Unsupported sample entry type");  // ← throw 前に valid = true のまま
  }
}
```

呼び出し側 (`src/mp4_ext.cpp:1478`):

```cpp
raw_sample.sample_entry = converter.valid ? &converter.raw_entry : nullptr;
```

つまり `valid` の意味は「呼び出し側が非 NULL の sample_entry を渡すべきか (前サンプルと同じセマンティクスを使わないか)」であり、`mp4.h:1036-1041` の「NULL の場合は前のサンプルと同じ」という C API 契約に対応している。

「valid」という名前だと「変換が成功したか」に読める。しかし throw 時にも一時的に true になるし、実際の意味は「入力が None ではないか」。

## 設計方針

以下のいずれかを採用する。

### 方針 A (推奨): フィールド名を `has_entry` / `is_present` に改名

- 変更コスト最小
- コードを読む際の誤解を減らす

### 方針 B: `std::optional<Mp4SampleEntry>` にして状態フラグを廃止

- より C++ っぽい設計
- `raw_entry` の生成コストが追加コピーになる可能性 (Mp4SampleEntry の union は 100 バイト前後)
- 呼び出し側は `converter.entry ? &*converter.entry : nullptr` になる

方針 A で十分。方針 B は overkill。

## 完了条件

- `SampleEntryConverter::valid` が `has_entry` (または `is_present`) に改名される
- コメントで「NULL 渡しは前サンプルと同じセマンティクスを実現するためのフラグ」と明記される
- 全テスト通過

## 解決方法

1. `src/mp4_ext.cpp:1071` を書き換え:
   ```cpp
   /// このコンバータで変換した sample_entry を C API に渡すべきかどうか。
   /// false の場合、C API 側で「前サンプルと同じ sample_entry を再利用する」
   /// セマンティクスが働く (mp4.h:1036-1041 参照)。
   bool has_entry = false;
   ```
2. `src/mp4_ext.cpp:1091, 1095` の `valid = ...` を `has_entry = ...` に置き換え
3. `src/mp4_ext.cpp:1478` の `converter.valid` を `converter.has_entry` に置き換え
4. `convert()` の docstring で「入力が None ではないケースを検出するフラグ」と説明
5. `issues/0012-refactor-split-mp4-ext-and-sample-entry-scaffolding.md` の対応と同時実施を検討
