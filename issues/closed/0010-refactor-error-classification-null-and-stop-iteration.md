# check_error のエラー分類 (MP4_ERROR_NULL_POINTER, stop_iteration) を見直す

- Priority: Medium
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/refactor-error-classification-null-and-stop-iteration
- Polished: {YYYY-MM-DD}

## 目的

`check_error()` のエラー分類の 2 つの問題を解消する。

1. `MP4_ERROR_NULL_POINTER` を `std::invalid_argument` (Python 側 `TypeError`) にマップしているが、これはラッパー内部のバグを意味するので `RuntimeError` にマップすべき
2. `check_error()` が `MP4_ERROR_NO_MORE_SAMPLES` を `nb::stop_iteration()` に変換しているが、`get_tracks()` など iter でない箇所からも `check_error()` が呼ばれるため、`StopIteration` の漏出リスクがある

## 優先度根拠

Medium。

- 「Python に上がる例外の意味が原因を誤らせる」不具合。ラッパー内部で NULL を渡すことは論理的にあり得ないため、`TypeError` になるとユーザーが「引数の型が悪い」と誤解する。
- `stop_iteration` は現状 `next()` 側 (`src/mp4_ext.cpp:868-870`) で `NO_MORE_SAMPLES` を先処理しているので `check_error()` の 914-915 行の分岐は実質デッドコードだが、将来の変更で顕在化しうる。PEP 479 挙動と組み合わさると混乱を招く。
- 修正コストは switch 文の書き換えだけで完結する。

## 現状

### `MP4_ERROR_NULL_POINTER` のマップ

`src/mp4_ext.cpp:906-923` (Demuxer 側) と `src/mp4_ext.cpp:1522-1541` (Muxer 側):

```cpp
switch (error) {
  case MP4_ERROR_NO_MORE_SAMPLES:
    throw nb::stop_iteration();          // ← 汎用ヘルパで無条件に投げる
  case MP4_ERROR_NULL_POINTER:
    throw std::invalid_argument("Null pointer error: " + msg_str);  // ← TypeError にマップ
  case MP4_ERROR_INPUT_REQUIRED:
    throw Mp4Exception("Input required: " + msg_str);
  default:
    throw Mp4Exception("MP4 error (" + std::to_string(error) + "): " + msg_str);
}
```

`MP4_ERROR_NULL_POINTER` は C API に NULL を渡した際に返る値 (`mp4.h:1219, 1234, 1277` 等)。C++ ラッパー実装で NULL を渡すことは論理的にあり得ないため、この例外はラッパー内部のバグを意味する。ユーザーには `RuntimeError` (or 本 issue 対応後は `Mp4Exception`) として上げるべき。

### `stop_iteration` の投げ位置

`check_error()` は以下から呼ばれる:
- `get_tracks()` (`src/mp4_ext.cpp:831`)
- `next()` (`src/mp4_ext.cpp:871`)
- `feed_required_input()` (`src/mp4_ext.cpp:970, 1002`)

`get_tracks()` から `NO_MORE_SAMPLES` が返る可能性は現状ないが、汎用ヘルパで無条件に `stop_iteration` を投げるのは PEP 479 挙動 (Python 3.7+ で generator 内の `StopIteration` は `RuntimeError` にラップされる) と組み合わさると混乱を招く。かつ `next()` 側 (868-870) で既に `NO_MORE_SAMPLES` を先処理しているため、914-915 行は実質デッドコード。

## 設計方針

- `MP4_ERROR_NULL_POINTER` を `Mp4Exception("Internal error: null pointer passed to C API")` にマップし、`RuntimeError` として上げる
- `check_error()` から `stop_iteration` を投げるのを廃止し、呼び出し側 (`next()` 側) で明示的に `NO_MORE_SAMPLES` を分岐する
- Muxer 側も同様の変更 (Muxer は `NO_MORE_SAMPLES` を返さないので実質 `NULL_POINTER` の分類のみ変更)

## 完了条件

- Demuxer / Muxer の `check_error()` で `MP4_ERROR_NULL_POINTER` が `Mp4Exception` (Python 側 `RuntimeError`) にマップされる
- `check_error()` から `stop_iteration` が投げられない。`NO_MORE_SAMPLES` の分岐は削除
- `next()` (`src/mp4_ext.cpp:853-897`) 側で `NO_MORE_SAMPLES` を明示的に処理し `nb::stop_iteration()` を投げる (既存の 868-870 行のロジックのみ残る)
- 追加テスト: `check_error` に到達する経路で `NULL_POINTER` が返るのは異常系なので直接テストは困難。ドキュメントで挙動を明記する

## 解決方法

1. `src/mp4_ext.cpp:906-923` を以下に変更:
   ```cpp
   void check_error(Mp4Error error) {
     if (error == MP4_ERROR_OK)
       return;

     const char* msg = mp4_file_demuxer_get_last_error(demuxer_);
     std::string msg_str = msg ? msg : "";

     switch (error) {
       case MP4_ERROR_NULL_POINTER:
         throw Mp4Exception("Internal error: null pointer passed to C API: " + msg_str);
       case MP4_ERROR_INPUT_REQUIRED:
         throw Mp4Exception("Input required: " + msg_str);
       // NO_MORE_SAMPLES は呼び出し側で先処理する
       default:
         throw Mp4Exception("MP4 error (" + std::to_string(error) + "): " + msg_str);
     }
   }
   ```
2. `src/mp4_ext.cpp:1522-1541` の Muxer 側も `MP4_ERROR_NULL_POINTER` を `Mp4Exception` に変更 (`std::invalid_argument` → `Mp4Exception`)
3. 既存の `next()` 側 868-870 行の `NO_MORE_SAMPLES` 先処理は残す
4. 本 issue は `issues/0006-add-mp4-exception-python-registration.md` の対応後に実施することを推奨 (Mp4Exception が Python 側で捕捉可能になっているとよい)

## 対応結果

`MP4_ERROR_NULL_POINTER` / `MP4_ERROR_NO_MORE_SAMPLES` はいずれも mp4-rust の C API 固有のエラーコードであり、PyO3 バインディングでは C API を経由しないため該当エラーの分類問題そのものが消滅した。PyO3 版では `next_sample()` の `Ok(None)` を明示的に `PyStopIteration` に変換しており、汎用 error → StopIteration マッピングは存在しない。よって closed とする。
