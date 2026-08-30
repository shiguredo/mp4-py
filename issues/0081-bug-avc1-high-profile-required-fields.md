# Mp4SampleEntryAvc1 が High 系プロファイルで必須の avcC フィールドを未指定のまま受理し finalize で失敗する

- Created: 2026-08-29
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-avc1-high-profile-required-fields
- Polished: 2026-08-30

## 目的

AVC1 のサンプルエントリーで、プロファイルによっては必須となる `avcC` のフィールドを未指定のまま構築を成功させている状態を解消する。入力の欠落をコンストラクタで `ValueError` として検出し、エラー発生点を利用者の入力位置近くに戻す。

## 現状

`src/lib.rs` の `Mp4SampleEntryAvc1::new` は `chroma_format` / `bit_depth_luma_minus8` / `bit_depth_chroma_minus8` を `Option<u8>` として受け取り、既定は `None` のままだ。ビット幅検証 (`validate_range`) は `Some` のときだけ走るため、`None` は無検証で通過する。

コア (`shiguredo_mp4`) 側は `AvcCBox::encode` で `avc_profile_indication` が 66 / 77 / 88 以外の場合にこの 3 フィールドを必須としており、欠けていると `Error::invalid_input` を返す。コアのフィールド doc にも「`avc_profile_indication` が 66 / 77 / 88 以外の場合のみ ISO/IEC 14496-15 仕様上は必須」と明記されている。

実測した再現手順 (High プロファイル = 100、3 フィールドを省略):

```python
from mp4 import Mp4FileMuxer, Mp4MuxSample, Mp4SampleEntryAvc1
import io

entry = Mp4SampleEntryAvc1(
    1920, 1080, 100, 40, 0xFF,
    sps_data=[b"\x67\x64\x00\x28"],
    pps_data=[b"\x68\xeb\x35\x80"],
)
muxer = Mp4FileMuxer(io.BytesIO())
muxer.append_sample(Mp4MuxSample(track_kind="video", sample_entry=entry, keyframe=True, timescale=1000, duration=100, data=b"\x00" * 16))
muxer.finalize()  # RuntimeError: mp4 error: Failed to encode MP4 box: InvalidInput: Missing 'chroma_format' field in 'avcC' box
```

- `append_sample` まで成功し、失敗は `finalize` で発生する。エラーメッセージは欠落フィールドを 1 つしか挙げない
- `chroma_format=1` を与えると次は `bit_depth_luma_minus8`、さらに `bit_depth_luma_minus8=0` を与えると `bit_depth_chroma_minus8` と、別のエラーへ順番に進む。3 つとも与えて初めて成功する
- `avc_profile_indication` を 66 / 77 / 88 にすると 3 フィールド省略のまま finalize まで成功する

`tests/conftest.py` の `st_avc1_sample_entry` は Baseline / Main / Extended (66 / 77 / 88) のプロファイルのみ生成するため、PBT はこの経路を踏まない。

なお、本不具合は「既定値が後段の必須要件と矛盾する」という意味で、`Mp4SampleEntryTx3g` の `background_color_rgba` で発生した不具合と同型である。

## 設計方針

- `Mp4SampleEntryAvc1::new` で `avc_profile_indication` を参照し、66 / 77 / 88 以外の場合に 3 フィールドのいずれかが `None` なら `ValueError` を返す
- 制約はコアのフィールド doc に明記されているため、値域検証をコア doc 明記分に限定する既存方針 (ビット幅検証の整備時の方針) と衝突しない
- エラーメッセージは英語で、期待する条件と実際の値を含める (`validate_range` の方式を踏襲する)
- 検証を追加した場合、66 / 77 / 88 では 3 フィールド省略が従来どおり通ることを単体テストで固定する。プロファイルと 3 フィールドの組合わせは有限なので `pytest.mark.parametrize` の `ids` 付きで検証する
- `from_box` (demux 経路) は対象外とする。入力データ由来の値をそのまま保持する既存方針のため検証を追加しない
- 検証の追加に伴い、「AVC1 High Profile と Opus input_sample_rate の PBT カバレッジを拡張する」issue (open) の戦略は、profile=100 で 3 フィールドを省略すると構築時に `ValueError` になるため、3 フィールドを常に与える形に整合させる必要がある

## 完了条件

- `avc_profile_indication` が 66 / 77 / 88 以外で 3 フィールドのいずれかが未指定の場合、構築時に `ValueError` になる
- `avc_profile_indication` が 66 / 77 / 88 の場合、3 フィールド省略で構築から finalize まで従来どおり成功する
- 既存テストが全通過する
