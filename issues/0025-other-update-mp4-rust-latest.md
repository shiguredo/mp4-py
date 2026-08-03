# mp4-rs を最新版 (2026.4.0) に追従する

- Created: 2026-08-03
- Completed: 2026-08-03
- Branch: feature/update-mp4-rust-2026-4-0
- Polished: {YYYY-MM-DD}

## 目的

依存する `shiguredo_mp4` (Rust クレート) を 2026.3.0 から最新版 2026.4.0 に上げる。

2026.4.0 は破壊的変更を含むため、バインディング側の追従が必要になる。

## 現状

`Cargo.toml` の `[dependencies]` で `shiguredo_mp4 = "=2026.3.0"` に固定している。

2026.4.0 をそのまま適用するとビルドエラーになる。追加・変更された API は以下のとおり:

- `TrackKind` に `Subtitle` バリアントが追加された
- `SampleEntry` に `Stpp` / `Wvtt` / `Tx3g` バリアントが追加された
- `Mp4FileMuxerOptions` に `audio_track` / `video_track` / `subtitle_track` (言語・トラック名) が追加された
- `estimate_maximum_moov_box_size` が任意トラック数対応 (`&[usize]`) にシグネチャ変更された
- 最小サポート Rust バージョンが 1.93 に上がった

## 設計方針

バインディングの既存スタイル (`src/lib.rs` の pyclass / PyO3 パターン) に合わせて追従する。

- `TrackKind::Subtitle` は Python 側 `track_kind="subtitle"` に対応させる
- `Stpp` / `Wvtt` / `Tx3g` はそれぞれ `Mp4SampleEntryStpp` / `Mp4SampleEntryWvtt` / `Mp4SampleEntryTx3g` として全フィールド公開する
- トラックメタデータは `Mp4TrackMetadata` クラスを新設し、`Mp4FileMuxerOptions` の `audio_track` / `video_track` / `subtitle_track` で受け取る
- `estimate_maximum_moov_box_size` は可変長引数 `(*sample_counts)` に変更する (既存の 2 引数呼び出しはそのまま動作させる)
- `rust-version` は 1.93 に引き上げる

## 完了条件

- `shiguredo_mp4` が 2026.4.0 に更新されること
- 字幕トラック (stpp / wvtt / tx3g) の mux / demux ができること
- トラックメタデータ (言語・名前) を指定できること
- `estimate_maximum_moov_box_size` が任意トラック数で呼べること
- GIL あり (3.12 / 3.13 / 3.14) と Free-Threading (3.14t) で全テストが通ること

## 解決方法

`feature/update-mp4-rust-2026-4-0` ブランチで対応済み。

- `Cargo.toml` の `shiguredo_mp4` を `=2026.4.0` に更新し、`rust-version` を 1.93 に引き上げた
- `src/lib.rs` に以下を実装した:
  - `track_kind_to_str` / `str_to_track_kind` に `TrackKind::Subtitle` 対応を追加
  - `Mp4SampleEntryStpp` / `Mp4SampleEntryWvtt` / `Mp4SampleEntryTx3g` を新設し、`Mp4SampleEntryAny` と `sample_entry_from_core` に追加
  - `Mp4TrackMetadata` を新設し、`Mp4FileMuxerOptions` に `audio_track` / `video_track` / `subtitle_track` を追加
  - `estimate_maximum_moov_box_size` を可変長引数に変更
- `python/mp4/__init__.py` に新クラスの公開と `Mp4TrackKind` / `Mp4SampleEntry` の型定義更新
- `tests/` に字幕サンプルエントリー・トラックメタデータ・可変長引数・3 トラック混在のテストを追加
- `CHANGES.md` と README を更新
