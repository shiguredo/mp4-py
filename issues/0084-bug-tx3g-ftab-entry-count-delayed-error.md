# Mp4SampleEntryTx3g が ftab の entry_count 上限を超える font_table を受理して finalize で失敗する

- Created: 2026-08-29
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-tx3g-ftab-entry-count-limit
- Polished: 2026-08-31

## 目的

`Mp4SampleEntryTx3g::new` が `font_table` のエントリー数を検証せず、ftab の `entry_count` (u16) の上限を超える入力を構築時に黙って受理する状態を解消する。エラー発生点を利用者の入力位置近くに戻す。字幕系 SampleEntry の遅延エラー解消 (font_name 長の構築時検証) の残余である。

## 現状

`src/lib.rs` の `Mp4SampleEntryTx3g::new` は `font_table` のエントリー数を検証していない。エントリー自体は合法値 (フォント名 255 バイト以下) でも、エントリー数が 65536 以上のとき構築と `append_sample` は成功し、`finalize` で初めて `RuntimeError` になる。

再現手順 (65537 エントリー、フォント名は 1 バイトの合法値):

```python
import io
from mp4 import Mp4FileMuxer, Mp4MuxSample, Mp4SampleEntryTx3g

entry = Mp4SampleEntryTx3g(font_table=[(1, b"F")] * 65537)  # 構築は成功する

muxer = Mp4FileMuxer(io.BytesIO())
muxer.append_sample(
    Mp4MuxSample(
        track_kind="subtitle",
        sample_entry=entry,
        keyframe=True,
        timescale=1000,
        duration=100,
        data=bytes(16),
    )
)
muxer.finalize()  # RuntimeError: mp4 error: Failed to encode MP4 box:
                  # InvalidInput: ftab.entry_count exceeds u16::MAX
```

原因はコア (`shiguredo_mp4`) の `FtabBox::encode` が `u16::try_from(self.entries.len())` を要求し、失敗時に `Error::invalid_input("ftab.entry_count exceeds u16::MAX")` を返す構造的制約にある。`FtabBox` の doc コメントに最大エントリー数の明記はないが、`entry_count` が u16 である構造的制約であり、意味論的制約の検証方針 (コアの doc コメントに明記されているフィールドに限る) の対象ではなく、ビット幅検証と同列に扱える。

`from_box` (demux 経路) は対象外とする。コアの `FtabBox::decode` は `entry_count: u16` で読むため、65535 を超えるエントリー数が demux で流入する経路は存在しない。

## 設計方針

- `Mp4SampleEntryTx3g::new` は `font_table` のエントリー数が 65536 以上のとき `ValueError` を返す (65535 以下は合法)。フォント名長の検証と同じループ近くに置き、エラーメッセージは英語で期待する値域を含める
- `from_box` (demux 経路) は入力データ由来の値をそのまま保持する既存方針のため検証対象外とする
- 単体テスト (`tests/test_mp4.py`) で、65536 エントリーの `font_table` が `ValueError` になることと、境界値 (65535 エントリー) が構築できることを検証する。65535 エントリーの構築は大量の小オブジェクトを生成するため、テストの実行時間 (既定タイムアウト 10 秒) 内に収まる形式にする

## 完了条件

- 65536 以上のエントリーを持つ `font_table` がコンストラクタで `ValueError` になる
- 65535 以下のエントリーは従来どおり動作する (既存テストを含め全通過する)
