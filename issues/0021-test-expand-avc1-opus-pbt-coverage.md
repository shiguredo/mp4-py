# AVC1 High Profile と Opus input_sample_rate の PBT カバレッジを拡張する

- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Branch: feature/test-expand-avc1-opus-pbt-coverage
- Polished: 2026-09-01
- Milestone: 2026.2.0

## 目的

`tests/conftest.py` の PBT strategy が以下の重要ケースを含んでおらず、実装のリグレッションを検出できない状態を解消する。

1. AVC1 の High Profile (100 系) と Optional フィールド (`chroma_format`, `bit_depth_luma_minus8`, `bit_depth_chroma_minus8`)
2. Opus の `input_sample_rate=Some(値)` の roundtrip

## 現状

### AVC1 (`tests/conftest.py` の `st_avc1_sample_entry`)

```python
avc_profile = draw(st.sampled_from([66, 77, 88]))  # Baseline/Main/Extended のみ
# High Profile (100), High 10 (110), High 4:2:2 (122), High 4:4:4 (244) 未網羅
# chroma_format / bit_depth_luma_minus8 / bit_depth_chroma_minus8 が strategy に含まれない
```

`tests/prop_sample_entry.py` の `prop_avc1_fields_preserved` は上記 3 フィールドの roundtrip assert をしていない。

`st_avc1_sample_entry` 内のコメント「Baseline/Main/Extended のみを使用して単純化する」により意図的に絞られているが、実装で最も使われる High Profile 系が対象外。

### Opus (`tests/conftest.py` の `st_opus_sample_entry`)

```python
return Mp4SampleEntryOpus(
    draw(st_channel_count),
    draw(st_sample_rate),
    draw(st_sample_size),
    draw(st.integers(min_value=0, max_value=65535)),
    None,  # ← input_sample_rate が固定
    draw(st.integers(min_value=-32768, max_value=32767)),
)
```

`tests/prop_sample_entry.py` の `prop_opus_fields_preserved` も `input_sample_rate` の roundtrip assert をしていない。

`src/lib.rs` の `Mp4SampleEntryOpus::to_sample_entry` は `self.input_sample_rate.unwrap_or(self.sample_rate as u32)` でデフォルト化し、`Mp4SampleEntryOpus::from_box` は常に `Some(...)` を返すため、`Some(値)` を渡した場合の roundtrip 保存が検証されていない。

## 設計方針

### AVC1

- strategy に profile=100 を加え、Optional フィールドは profile に応じて条件付きで生成する:
  ```python
  avc_profile = draw(st.sampled_from([66, 77, 88, 100]))
  # 66/77/88 では Optional フィールドが avcC に書き込まれず roundtrip 後に常に None で
  # 戻るため None 固定にする。High (100) では ISO/IEC 14496-15 上必須であり、
  # コアの AvccBox::encode が欠落時にエラーを返すため必ず実値を与える
  if avc_profile in (66, 77, 88):
      chroma_format = None
      bit_depth_luma_minus8 = None
      bit_depth_chroma_minus8 = None
  else:
      chroma_format = draw(st.sampled_from([0, 1, 2, 3]))
      bit_depth_luma_minus8 = draw(st.sampled_from([0, 2, 4]))
      bit_depth_chroma_minus8 = draw(st.sampled_from([0, 2, 4]))
  ```
- `prop_avc1_fields_preserved` に 3 フィールドの roundtrip assert を追加
- 注: profile=100 で 3 フィールドを省略すると構築時に `ValueError` になる (必須化の方針は High 系プロファイルの必須フィールド検証の issue で定める)。そのため本 issue の strategy は必ず 3 フィールドを与える形で整合させる

### Opus

- strategy に `input_sample_rate=Some(値)` を含める:
  ```python
  # input_sample_rate は u32 のため sample_rate (u16) の上限 (65535) を超える値も
  # roundtrip が成立することを検証する
  input_sample_rate = draw(st.one_of(
      st.none(),
      st.integers(min_value=8000, max_value=192000),
  ))
  ```
- `prop_opus_fields_preserved` に `input_sample_rate` の roundtrip assert を追加
- 注意: 現状の実装は `None → sample_rate` にフォールバックするため、roundtrip では `Some(sample_rate)` として戻る。仕様として明確化が必要 (`Mp4SampleEntryOpus` の docstring にフォールバック挙動を明記する)

## 完了条件

- `st_avc1_sample_entry` strategy に High Profile (100) と Optional フィールドが含まれる (66/77/88 では None、100 では実値)
- `prop_avc1_fields_preserved` で `chroma_format` / `bit_depth_luma_minus8` / `bit_depth_chroma_minus8` の roundtrip が assert される
- `st_opus_sample_entry` strategy に `input_sample_rate=Some(値)` が含まれる
- `prop_opus_fields_preserved` で `input_sample_rate` の roundtrip が assert される (None 時は `sample_rate` と一致する)
- 追加した assert がすべて通る (profile 条件付き戦略とフォールバック挙動への対応により決定的に成立する)

## 解決方法

1. `tests/conftest.py` の `st_avc1_sample_entry` を書き換え:
   ```python
   @st.composite
   def st_avc1_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryAvc1:
       # 有効な SPS/PPS データを生成（最小限のダミー）
       sps_data = [bytes([0x67] + draw(st.lists(st_u8, min_size=4, max_size=32)))]
       pps_data = [bytes([0x68] + draw(st.lists(st_u8, min_size=2, max_size=16)))]

       avc_profile = draw(st.sampled_from([66, 77, 88, 100]))
       # Baseline/Main/Extended (66/77/88) では Optional フィールドが avcC に
       # 書き込まれず roundtrip 後に常に None で戻るため、None 固定にする
       if avc_profile in (66, 77, 88):
           chroma_format = None
           bit_depth_luma = None
           bit_depth_chroma = None
       else:
           # High (100) では 3 フィールドが必須 (ISO/IEC 14496-15、コアの
           # AvccBox::encode が欠落時にエラーを返す) のため必ず実値を与える
           chroma_format = draw(st.sampled_from([0, 1, 2, 3]))
           bit_depth_luma = draw(st.sampled_from([0, 2, 4]))
           bit_depth_chroma = draw(st.sampled_from([0, 2, 4]))

       return Mp4SampleEntryAvc1(
           width=draw(st_width),
           height=draw(st_height),
           avc_profile_indication=avc_profile,
           avc_level_indication=draw(st_u8),
           profile_compatibility=draw(st_u8),
           sps_data=sps_data,
           pps_data=pps_data,
           length_size_minus_one=draw(st.sampled_from([0, 1, 3])),
           chroma_format=chroma_format,
           bit_depth_luma_minus8=bit_depth_luma,
           bit_depth_chroma_minus8=bit_depth_chroma,
       )
   ```
2. `tests/prop_sample_entry.py` の `prop_avc1_fields_preserved` に以下を追加:
   ```python
   assert restored.chroma_format == sample_entry.chroma_format
   assert restored.bit_depth_luma_minus8 == sample_entry.bit_depth_luma_minus8
   assert restored.bit_depth_chroma_minus8 == sample_entry.bit_depth_chroma_minus8
   ```
3. `tests/conftest.py` の `st_opus_sample_entry` を書き換え (5 番目の引数を変数化):
   ```python
   @st.composite
   def st_opus_sample_entry(draw: st.DrawFn) -> Mp4SampleEntryOpus:
       # input_sample_rate は u32 のため sample_rate (u16) の上限 (65535) を
       # 超える値も roundtrip が成立することを検証する
       input_sample_rate = draw(st.one_of(
           st.none(),
           st.integers(min_value=8000, max_value=192000),
       ))
       return Mp4SampleEntryOpus(
           draw(st_channel_count),
           draw(st_sample_rate),
           draw(st_sample_size),
           draw(st.integers(min_value=0, max_value=65535)),
           input_sample_rate,
           draw(st.integers(min_value=-32768, max_value=32767)),
       )
   ```
4. `tests/prop_sample_entry.py` の `prop_opus_fields_preserved` に:
   ```python
   # 現実装は None → sample_rate にフォールバックするため、
   # None 時は sample_rate と一致することを確認
   if sample_entry.input_sample_rate is None:
       assert restored.input_sample_rate == sample_entry.sample_rate
   else:
       assert restored.input_sample_rate == sample_entry.input_sample_rate
   ```
5. 上記フォールバック挙動は `src/lib.rs` の `Mp4SampleEntryOpus` の docstring に明記する
