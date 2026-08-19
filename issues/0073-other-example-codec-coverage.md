# examples/demux.py が字幕系 SampleEntry を表示できない

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-example-codec-coverage
- Polished: {YYYY-MM-DD}

## 目的

`examples/demux.py` のサンプルエントリー表示を、2026.2.0 で公開する全 SampleEntry 種に対応させる。字幕トラック対応を宣伝する一方で、代表的な example が字幕トラックを「Unknown codec」と表示する不整合を解消する。

## 現状

`examples/demux.py` の `get_sample_entry_description` は import と isinstance 分岐が Avc1 / Hev1 / Vp08 / Vp09 / Av01 / Opus / Mp4a / Flac の 8 種のみで、`Mp4SampleEntryHvc1` / `Mp4SampleEntryStpp` / `Mp4SampleEntryWvtt` / `Mp4SampleEntryTx3g` は `else: return "Unknown codec"` に落ちる。

2026.2.0 で字幕トラック (STPP / WVTT / TX3G) 対応を公開する予定だが、サンプルプログラムが字幕トラックを表示できないため、デモとして不十分。

## 設計方針

- 残りの 4 種 (Hvc1 / Stpp / Wvtt / Tx3g) の表示分岐を追加する
- 表示内容は各 SampleEntry の公開プロパティから妥当な情報を選ぶ (例: Stpp なら namespace / schema_location)

## 完了条件

- 全 SampleEntry 種が適切に表示される
- スクリプトが実在する字幕トラック入り MP4 で正しく動作する
