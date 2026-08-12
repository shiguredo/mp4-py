# timescale が 0 の場合の timestamp_seconds / duration_seconds が 0 除算で inf / nan を返す

- Priority: Medium
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-zero-timescale-division-in-duration-methods
- Polished: 2026-08-12

## 目的

`Mp4TrackInfo(timescale=0)` を Python 側で手作りできてしまい、`Mp4DemuxSample` の `timestamp_seconds` / `duration_seconds` (src/lib.rs) が `timestamp / timescale` の 0 除算で `inf` / `nan` を返す問題を解消する。コンストラクタで `timescale == 0` を弾くことで、0 除算に到達する経路を構造的に排除する。

## 優先度根拠

Medium。

- Python 側から `Mp4TrackInfo(track_id=1, kind="video", duration=1000, timescale=0)` を手で作れるため、実装ミスや誤用で `inf` / `nan` が伝播しうる。
- `Mp4MuxSample` の timescale は append_sample 時に `PyValueError` (「timescale must be non-zero」) で既に弾かれている (src/lib.rs) が、`Mp4TrackInfo` には同様の検証がない。
- 修正は `Mp4TrackInfo::new` へのバリデーション追加のみで完結する。

## 現状

`src/lib.rs` の `Mp4TrackInfo::new` (src/lib.rs) は `timescale == 0` を検証しておらず、`Mp4TrackInfo(timescale=0)` が作成できてしまう。

`Mp4DemuxSample::timestamp_seconds` / `duration_seconds` (src/lib.rs) は `self.timestamp as f64 / t.timescale as f64` の 0 除算で、`timescale == 0` の場合 `inf` / `nan` を返す (実測確認済み)。

なお、Demuxer 経由で生成される `Mp4TrackInfo` の timescale は shiguredo_mp4 の `TrackInfo::timescale` が `NonZeroU32` のため 0 にはならず、到達可能な経路は Python からの直接構築のみである。fMP4 の init segment で 0 になりうるのは timescale ではなく duration であり、本 issue の対象外。

## 設計方針

### 方針 A: コンストラクタで timescale == 0 を弾く

- `Mp4TrackInfo::new` に `timescale == 0` の検証を追加し、`PyValueError` を投げる
  - 例外型は既存の同種バリデーション (append_sample の「timescale must be non-zero」) と同じ `PyValueError` とする (破損データ検出専用の `Mp4Exception` (issue 0006) は入力バリデーションの対象外)
- これにより `Mp4DemuxSample(track=Mp4TrackInfo(timescale=0), ...)` の経路も塞がれ、`timestamp_seconds` / `duration_seconds` の 0 除算は構造的に到達不能になる
- Demuxer 経由の TrackInfo は `NonZeroU32` 由来で 0 にならないため、計算時の nan 返却は不要

## 完了条件

- Python コンストラクタ `Mp4TrackInfo(..., timescale=0)` が `ValueError` を投げる
- `Mp4DemuxSample` の `timestamp_seconds` / `duration_seconds` は 0 除算に到達しない
- 追加テスト: `Mp4TrackInfo(track_id=1, kind="video", duration=1000, timescale=0)` で `ValueError` が発火することを確認するテストを `tests/test_mp4.py` に追加する (既存の `test_track_info_properties` と同じ直接構築パターン)
- README.md と examples/demux.py の `track.duration_seconds` は PyO3 移行で消滅した API を参照しており動作しない (実行時に AttributeError になる) ため、本 issue の対応時に追跡 issue を起票する
- CHANGES.md の `## develop` に FIX エントリを追記 (shiguredo-changelog スキルの形式に従う)

## 解決方法

1. `src/lib.rs` の `Mp4TrackInfo::new` に `timescale == 0` の検証を追加する:
   - `if timescale == 0 { return Err(PyValueError::new_err("timescale must be non-zero")); }` の明示的な検証を追加する (既存の append_sample の検証 (src/lib.rs) と同じメッセージ・例外型にする。フィールド型は `u32` のまま変更しない)
2. `tests/test_mp4.py` に「`timescale=0` で `Mp4TrackInfo` を作ると `ValueError` が発火する」テストを追加する (既存の `test_track_info_properties` と同じ直接構築パターン)
3. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
4. CHANGES.md の `## develop` に FIX エントリを追記する

なお、README.md と examples/demux.py の `track.duration_seconds` は PyO3 移行で消滅した API を参照しており動作しない (実行時に AttributeError になる) ため、追跡 issue を完了条件に従って起票する (本 issue のスコープ外)。
