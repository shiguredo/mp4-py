# timescale が 0 の場合の duration_seconds / timestamp_seconds が 0 除算で inf を返す

- Priority: Medium
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-zero-timescale-division-in-duration-methods
- Polished: {YYYY-MM-DD}

## 目的

`PyMp4TrackInfo::duration_seconds()` / `PyMp4DemuxSample::timestamp_seconds()` / `PyMp4DemuxSample::duration_seconds()` は `static_cast<double>(...) / timescale` で計算しており、`timescale == 0` の場合 IEEE 754 の 0 除算で `inf` / `nan` を返す。Python から `PyMp4TrackInfo(timescale=0)` を作成できるため到達可能。防御的にバリデーションを追加する。

## 優先度根拠

Medium。

- fMP4 の init segment で `timescale = 0` になる場合があると `mp4.h:361-363` に記載されており、C API 経由で 0 が渡ってくる可能性はゼロではない。
- Python 側から `Mp4TrackInfo(timescale=0)` / `Mp4DemuxSample(track=Mp4TrackInfo(timescale=0), ...)` を手で作れるため、実装ミスや誤用で `inf` が伝播しうる。
- 修正はコンストラクタバリデーション or 計算時例外化で完結する。

## 現状

`src/mp4_ext.cpp:672-674` の `PyMp4TrackInfo::duration_seconds()`:

```cpp
double duration_seconds() const {
  return static_cast<double>(duration) / timescale;
}
```

`src/mp4_ext.cpp:741-747` の `PyMp4DemuxSample::timestamp_seconds()` / `duration_seconds()`:

```cpp
double timestamp_seconds() const {
  return static_cast<double>(timestamp) / track.timescale;
}

double duration_seconds() const {
  return static_cast<double>(duration) / track.timescale;
}
```

いずれも `timescale == 0` チェックがない。Python から `Mp4TrackInfo(track_id=1, kind="video", duration=1000, timescale=0)` を作成すると、`duration_seconds` は `inf` を返す。

## 設計方針

以下のいずれかを採用する。

### 方針 A: コンストラクタで timescale == 0 を弾く

- `PyMp4TrackInfo(uint32_t, std::string, uint64_t, uint32_t)` コンストラクタ (`src/mp4_ext.cpp:663-670`) と、`.def(nb::init<...>())` 経由で作成される Python から使うコンストラクタで `timescale == 0` を検査
- Demuxer 内部で作成される場合 (`src/mp4_ext.cpp:836-839`) は、mp4-rust 側が 0 を返す状況があるので弾かず、`duration_seconds()` の側で 0 除算を防ぐ

### 方針 B: 計算時に例外化 or 特別値を返す

- `duration_seconds()` / `timestamp_seconds()` で `timescale == 0` の場合 `Mp4Exception("timescale is zero")` を投げる
- あるいはドキュメントに明記した上で `nan` を返す

### 推奨

方針 A + 方針 B の組み合わせ。

- Python から手で作成されるケースはコンストラクタで弾く (`Mp4Exception`)
- Demuxer 経由で作成されるケース (fMP4 init segment 等の合法な `timescale = 0`) では、計算時に `nan` を返してドキュメント化

## 完了条件

- Python コンストラクタ `Mp4TrackInfo(..., timescale=0)` が `Mp4Exception` を投げる
- Demuxer 経由で `timescale = 0` の TrackInfo が生成された場合、`duration_seconds()` は `nan` を返す (docstring に明記)
- 追加テスト: `Mp4TrackInfo(track_id=1, kind="video", duration=1000, timescale=0)` で `Mp4Exception` 発火を確認
- 追加テスト: Demuxer 経由の TrackInfo で `duration_seconds()` が `nan` を返すことを確認 (fMP4 が絡むためテストデータ準備が必要 — mp4-rust 側テストデータの流用を検討)

## 解決方法

1. `src/mp4_ext.cpp:663-670` の Python 公開コンストラクタ用にラムダを追加し、`timescale == 0` で `Mp4Exception` を投げる:
   ```cpp
   .def(
       "__init__",
       [](PyMp4TrackInfo* self, uint32_t track_id, const std::string& kind,
          uint64_t duration, uint32_t timescale) {
         if (timescale == 0) {
           throw Mp4Exception("timescale must be greater than 0");
         }
         new (self) PyMp4TrackInfo(track_id, kind, duration, timescale);
       },
       "track_id"_a, "kind"_a, "duration"_a, "timescale"_a)
   ```
2. `PyMp4TrackInfo::duration_seconds()` (672-674) と `PyMp4DemuxSample::timestamp_seconds()` / `duration_seconds()` (741-747) は現状のまま (Demuxer 由来の `timescale == 0` は `nan` を返す)
3. 各メソッドの docstring に「`timescale == 0` の場合、戻り値は nan」と明記
4. `tests/test_mp4.py` にコンストラクタバリデーションのテストを追加
5. `tests/prop_edge_cases.py` の `prop_minimum_timescale` (166 行) の関連確認
