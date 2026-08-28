# README と examples の duration_seconds が消滅 API を参照して動作しない

- Created: 2026-08-13
- Completed: {YYYY-MM-DD}
- Branch: feature/update-duration-seconds-references
- Polished: {YYYY-MM-DD}

## 目的

README.md と examples/demux.py が、PyO3 移行で消滅した API を参照したままになっている。README のコード例をそのまま実行すると AttributeError になりユーザーを混乱させ、examples/demux.py はトラック情報表示とサンプル情報表示の一部が壊れている。現在の API で動作する記載に修正する。

## 現状

`Mp4TrackInfo` (src/lib.rs) が持つのは `track_id` / `kind` / `duration` (u64) / `timescale` (u32) のみで、seconds 換算のプロパティは存在しない。seconds 換算 API (`timestamp_seconds` / `duration_seconds`) は `Mp4DemuxSample` にのみ存在する。

`Mp4DemuxSample` のデータ位置・サイズの公開プロパティは `data_offset` / `data_size` (アンダースコアなし) であり、`_data_offset` / `_data_size` は存在しない。

消滅 API を参照している箇所:

- README.md の「トラック情報の取得」節: `track.duration_seconds` (Mp4TrackInfo の duration_seconds)
- examples/demux.py のトラック情報表示: `track.duration_seconds`
- examples/demux.py のサンプル情報表示: `sample._data_offset` / `sample._data_size`

## 設計方針

対象はドキュメントとサンプルコードのみで、ライブラリ本体 (`src/lib.rs`) は変更しない。

### 方針 A: 消滅 API を現在の公開プロパティに置き換える

- `track.duration_seconds` は `track.duration / track.timescale` の計算表示に置き換える
- `sample._data_offset` / `sample._data_size` は `sample.data_offset` / `sample.data_size` に置き換える

## 完了条件

- README.md の「トラック情報の取得」節が実行時に AttributeError にならないコード例になっている
- examples/demux.py のトラック情報表示とサンプル情報表示が実行時に AttributeError にならない
- examples/demux.py を実際に実行して正常に動作することを確認する

## 解決方法

1. README.md の「トラック情報の取得」節の `track.duration_seconds` を `track.duration / track.timescale` の計算表示に置き換える
2. examples/demux.py のトラック情報表示の `track.duration_seconds` を同様に置き換える
3. examples/demux.py のサンプル情報表示の `sample._data_offset` / `sample._data_size` を `sample.data_offset` / `sample.data_size` に置き換える
4. examples/demux.py を実行して動作を確認する
