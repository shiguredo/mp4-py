# AVC1 High Profile と Opus input_sample_rate の PBT カバレッジを拡張する

- Priority: Medium
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/test-expand-avc1-opus-pbt-coverage
- Polished: {YYYY-MM-DD}

## 目的

`tests/conftest.py` の PBT strategy が以下の重要ケースを含んでおらず、実装のリグレッションを検出できない状態を解消する。

1. AVC1 の High Profile (100 系) と Optional フィールド (`chroma_format`, `bit_depth_luma_minus8`, `bit_depth_chroma_minus8`)
2. Opus の `input_sample_rate=Some(値)` の roundtrip

## 優先度根拠

Medium。

- AVC1 High Profile 系は実運用で最も使われるプロファイル (`4:2:0 8-bit` 以外の色空間・ビット深度を扱う際に必須)。`chroma_format` は AVC High Profile 系で必須フィールドだが、テストで検証されていない。
- `mp4_ext.cpp:1159-1166` の `is_chroma_format_present` フラグと組で C API に渡す実装があるが、リグレッションが起きても検知できない。
- Opus の `input_sample_rate` は `nb-mediasoup` など実運用で使われる可能性があり、None/Some(値) の両方を検証する必要がある。
- 修正コストは strategy の拡張と assert 追加のみ。

## 現状

### AVC1 (`tests/conftest.py:76-96`)

```python
avc_profile = draw(st.sampled_from([66, 77, 88]))  # Baseline/Main/Extended のみ
# High Profile (100), High 10 (110), High 4:2:2 (122), High 4:4:4 (244) 未網羅
# chroma_format / bit_depth_luma_minus8 / bit_depth_chroma_minus8 が strategy に含まれない
```

`prop_avc1_fields_preserved` (`tests/prop_sample_entry.py:132-138`) は上記 3 フィールドの roundtrip assert をしていない。

conftest.py:84-85 のコメント「Baseline/Main/Extended のみを使用して単純化」により意図的に絞られているが、実装で最も使われる High Profile 系が対象外。

### Opus (`tests/conftest.py:167-175`)

```python
return Mp4SampleEntryOpus(
    channel_count=draw(...),
    sample_rate=draw(...),
    ...
    input_sample_rate=None,  # ← 固定
    output_gain=0,
)
```

`prop_opus_fields_preserved` (`tests/prop_sample_entry.py:239-267`) も `input_sample_rate` の roundtrip assert をしていない。

`src/mp4_ext.cpp:1343-1344` の実装は `input_sample_rate.value_or(sample_rate)` でデフォルト化しているが、`Some(値)` を渡した場合の roundtrip 保存が検証されていない。

## 設計方針

### AVC1

- strategy に profile=100 を加え、Optional フィールドを含める:
  ```python
  avc_profile = draw(st.sampled_from([66, 77, 88, 100]))
  chroma_format = draw(st.one_of(st.none(), st.sampled_from([0, 1, 2, 3])))
  bit_depth_luma_minus8 = draw(st.one_of(st.none(), st.sampled_from([0, 2, 4])))
  bit_depth_chroma_minus8 = draw(st.one_of(st.none(), st.sampled_from([0, 2, 4])))
  ```
- `prop_avc1_fields_preserved` に 3 フィールドの roundtrip assert を追加

### Opus

- strategy に `input_sample_rate=Some(値)` を含める:
  ```python
  input_sample_rate = draw(st.one_of(
      st.none(),
      st.integers(min_value=1, max_value=192000),
  ))
  ```
- `prop_opus_fields_preserved` に `input_sample_rate` の roundtrip assert を追加
- 注意: 現状の実装は `None → sample_rate` にフォールバックするため、roundtrip では `Some(sample_rate)` として戻る。仕様として明確化 (`issues/0010-refactor-error-classification-null-and-stop-iteration.md` とは別に、Opus 側の docstring 明記が必要)

## 完了条件

- `st_avc1_sample_entry` strategy に High Profile (100) と Optional フィールドが含まれる
- `prop_avc1_fields_preserved` で `chroma_format` / `bit_depth_luma_minus8` / `bit_depth_chroma_minus8` の roundtrip が assert される
- `st_opus_sample_entry` strategy に `input_sample_rate=Some(値)` が含まれる
- `prop_opus_fields_preserved` で `input_sample_rate` の roundtrip が assert される (現実装のフォールバック挙動を考慮)
- 追加 assert で失敗しないこと (もしくは既存実装の挙動を明確に記述)

## 解決方法

1. `tests/conftest.py:76-96` の `st_avc1_sample_entry` を書き換え:
   ```python
   @st.composite
   def st_avc1_sample_entry(draw):
       avc_profile = draw(st.sampled_from([66, 77, 88, 100]))
       # Optional フィールドは None または実値
       chroma_format = draw(st.one_of(
           st.none(),
           st.sampled_from([0, 1, 2, 3]),
       ))
       bit_depth_luma = draw(st.one_of(
           st.none(),
           st.sampled_from([0, 2, 4]),
       ))
       bit_depth_chroma = draw(st.one_of(
           st.none(),
           st.sampled_from([0, 2, 4]),
       ))
       return Mp4SampleEntryAvc1(
           width=draw(st_dimension),
           height=draw(st_dimension),
           avc_profile_indication=avc_profile,
           ...
           chroma_format=chroma_format,
           bit_depth_luma_minus8=bit_depth_luma,
           bit_depth_chroma_minus8=bit_depth_chroma,
       )
   ```
2. `tests/prop_sample_entry.py:132-138` の `prop_avc1_fields_preserved` に以下を追加:
   ```python
   assert restored.chroma_format == sample_entry.chroma_format
   assert restored.bit_depth_luma_minus8 == sample_entry.bit_depth_luma_minus8
   assert restored.bit_depth_chroma_minus8 == sample_entry.bit_depth_chroma_minus8
   ```
3. `tests/conftest.py:167-175` の `st_opus_sample_entry` を書き換え:
   ```python
   input_sample_rate = draw(st.one_of(
       st.none(),
       st.integers(min_value=8000, max_value=192000),
   ))
   ```
4. `tests/prop_sample_entry.py:239-267` の `prop_opus_fields_preserved` に:
   ```python
   # 現実装は None → sample_rate にフォールバックするため、
   # None 時は sample_rate と一致することを確認
   if sample_entry.input_sample_rate is None:
       assert restored.input_sample_rate == sample_entry.sample_rate
   else:
       assert restored.input_sample_rate == sample_entry.input_sample_rate
   ```
5. 上記フォールバック挙動は Mp4SampleEntryOpus の docstring に明記する (別途 `src/mp4_ext.cpp:1984` 付近)
