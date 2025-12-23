# 破損した MP4 データで無限ループが発生する問題

## 概要

破損した MP4 データを `Mp4FileDemuxer` でパースする際、`feed_required_input()` が無限ループに陥る問題が発生した。

hypothesis を使った fuzzing テスト (`test_fuzzing_corrupted_mp4`) で発見された。

## 再現条件

- 正規の MP4 を生成後、一部のバイトをランダムに破損させる
- 破損した MP4 を `Mp4FileDemuxer` でパースする

## 原因分析

### Rust 側 (mp4-rust) の設計

`Mp4FileDemuxer::handle_input()` の実装:

```rust
pub fn handle_input(&mut self, input: Input) {
    if let Err(e) = self.handle_input_inner(input)
        && !matches!(e, DemuxError::InputRequired(_))  // InputRequired は無視
    {
        self.handle_input_error = Some(e);
    }
}
```

- `InputRequired` エラーは意図的に `handle_input_error` に保存されない
- これは「もっとデータが必要」という正常なフローを示すための設計
- しかし、同じ `InputRequired` が繰り返されるケースを考慮していない

### C API の問題

`mp4_file_demuxer_handle_input()` は常に `MP4_ERROR_OK` を返す:

```rust
demuxer.inner.handle_input(input);
Mp4Error::MP4_ERROR_OK  // 常に OK
```

- Rust の `handle_input()` は戻り値が `()` なのでエラーを返せない
- C++ 側はエラーを検知できない

### 無限ループの流れ

1. C++ が `mp4_file_demuxer_get_required_input()` を呼ぶ
2. Rust が位置 X のデータを要求
3. C++ がデータを読んで `mp4_file_demuxer_handle_input()` を呼ぶ
4. Rust 内部で `InputRequired` エラー発生（phase が進まない）
5. エラーは無視され、`handle_input_error` に保存されない
6. C++ は OK を受け取り、再度 1 に戻る
7. Rust が同じ位置 X を要求 → 無限ループ

## 現在のワークアラウンド (mp4-py)

`src/mp4_ext.cpp` の `feed_required_input()` にイテレーションカウンターを追加:

```cpp
bool feed_required_input() {
  // 無限ループ防止用のカウンター
  constexpr int kMaxIterations = 10000;
  int iteration_count = 0;

  while (true) {
    if (++iteration_count > kMaxIterations) {
      throw Mp4Exception(
          "feed_required_input: too many iterations, possible infinite loop");
    }
    // ...
  }
}
```

これは根本的な修正ではなく、無限ループを検出して例外をスローするワークアラウンド。

## mp4-rust 側で本来すべき修正

### 案 1: 同じ入力要求の繰り返しを検出

`handle_input()` で前回と同じ `InputRequired` が返されたらエラーにする:

```rust
pub fn handle_input(&mut self, input: Input) {
    match self.handle_input_inner(input) {
        Ok(()) => {
            self.last_required_input = None;
        }
        Err(DemuxError::InputRequired(required)) => {
            // 同じ入力要求が繰り返されたらエラー
            if self.last_required_input == Some(required) {
                self.handle_input_error = Some(DemuxError::DecodeError(
                    Error::invalid_data("same input required repeatedly")
                ));
            } else {
                self.last_required_input = Some(required);
            }
        }
        Err(e) => {
            self.handle_input_error = Some(e);
        }
    }
}
```

### 案 2: handle_input() が Result を返すように変更

API を変更して、呼び出し元がエラーをハンドリングできるようにする:

```rust
pub fn handle_input(&mut self, input: Input) -> Result<(), DemuxError> {
    self.handle_input_inner(input)
}
```

ただし、これは破壊的変更になる。

### 案 3: C API でエラーを返す

`mp4_file_demuxer_handle_input()` が `InputRequired` エラーを返すようにする:

```rust
pub unsafe extern "C" fn mp4_file_demuxer_handle_input(...) -> Mp4Error {
    // ...
    match demuxer.inner.handle_input_with_result(input) {
        Ok(()) => Mp4Error::MP4_ERROR_OK,
        Err(DemuxError::InputRequired(_)) => Mp4Error::MP4_ERROR_INPUT_REQUIRED,
        Err(_) => Mp4Error::MP4_ERROR_DECODE,
    }
}
```

## 推奨

案 1 が最も影響範囲が小さく、既存の API を変更せずに問題を解決できる。

mp4-rust 側で修正するまでは、mp4-py の C++ ワークアラウンドで対応する。
