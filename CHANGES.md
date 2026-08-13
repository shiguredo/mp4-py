# 変更履歴

- CHANGE
  - 後方互換性のない変更
- UPDATE
  - 後方互換性がある変更
- ADD
  - 後方互換性がある追加
- FIX
  - バグ修正

## develop

- [CHANGE] バインディング実装を nanobind から PyO3 に置き換える
  - shiguredo/mp4-rs の C API ではなく Rust クレート `shiguredo_mp4` を直接バインドする
  - ビルドバックエンドを scikit-build-core + CMake から maturin + Cargo に変更する
  - Free-Threading (Python 3.14t) は PyO3 0.29 制約により 3.14+ のみ対応する
  - Python 3.13t は非対応となる
  - @voluntas
- [CHANGE] `Mp4FileMuxerOptions.reserved_moov_box_size` を `uint32` で受け取るようにする
  - mp4-rust 2026.2.0 の C API 型変更 (`u64` → `u32`) に追従する
  - @voluntas
- [CHANGE] `estimate_maximum_moov_box_size` を任意トラック数対応にする
  - 可変長引数 `estimate_maximum_moov_box_size(*sample_counts)` に変更する
  - @voluntas
- [ADD] abi3 wheel (Python 3.12 以降共通) を追加する
  - 1 wheel で 3.12 / 3.13 / 3.14 の GIL 有効ビルドすべてに対応する
  - @voluntas
- [ADD] `.pyi` 型スタブを wheel に自動同梱する
  - `maturin build --generate-stubs` により pyo3-introspection 経由で自動生成する
  - @voluntas
- [ADD] `Mp4DemuxSample` に `composition_time_offset` プロパティを追加する
  - `ctts` / `trun` 由来のコンポジション時間オフセットを `int | None` で参照できる
  - @voluntas
- [ADD] `Mp4MuxSample` に `composition_time_offset` 引数とプロパティを追加する
  - 指定した場合は `ctts` ボックスを生成する
  - @voluntas
- [ADD] `Mp4TrackMetadata` を追加する
  - `Mp4FileMuxerOptions` の `audio_track` / `video_track` / `subtitle_track` に言語 (`mdhd.language`) とトラック名 (`hdlr.name`) を指定できる
  - @voluntas
- [ADD] `Mp4SampleEntryStpp` / `Mp4SampleEntryWvtt` / `Mp4SampleEntryTx3g` を追加する
  - 字幕トラック (`track_kind="subtitle"`) の mux / demux に対応する
  - @voluntas
- [UPDATE] mp4-rust を 2026.4.0 に上げる
  - @voluntas
- [FIX] append_sample 失敗時に書き込んだバイトがストリームに残らないようにする
  - write 以降のエラーで seekable なストリームを巻き戻し、入力の補正後に retry できるようにする
  - 非 seekable なストリームでは使用不能の案内を例外メッセージに付加する
  - @voluntas

### misc

- [UPDATE] Free-Threading 環境で input_stream 共有レースの回帰テストを追加する
  - @voluntas
- [UPDATE] hypothesis を 6.158.1 に上げる
  - @voluntas
- [UPDATE] pytest を 9.1.1 に上げる
  - @voluntas
- [UPDATE] `build-system.requires` の maturin バージョン下限を `1.14` に引き上げる
  - @voluntas

## 2026.1.0

**リリース日**:: 2026-01-07

**祝いリリース**
