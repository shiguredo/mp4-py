# Muxer / Demuxer の境界で size_t → uint32_t / int32_t のサイレント切り詰めが起きる

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-integer-truncation-in-mux-demux-boundaries
- Polished: {YYYY-MM-DD}

## 目的

C++ ラッパーと mp4-rust C API の境界で、`size_t` (通常 64 bit) を `uint32_t` に無検査キャスト、`size_t` を `int32_t` に無検査キャストしている 2 箇所を修正し、4 GiB 超の入出力データでのサイレントなデータ破壊 / 誤動作を防ぐ。

- Muxer 側: `sample.data.size()` を `uint32_t` に切り詰めることで、書き込み位置と Muxer 内部のトラッキング位置が乖離し、MP4 ファイルが破損する
- Demuxer 側: `data.size()` を `uint32_t` へ切り詰め、加えて `int32_t` にキャストして比較することで、`data.size() > 2^31` の場合に負値となり EOF を偽通知する

## 優先度根拠

High。

- Muxer 側は「書き込みは全量成功しストリームは進むが、Muxer には切り捨てサイズが通知され、以降のサンプルすべてで `MP4_ERROR_POSITION_MISMATCH` が発生」する。**最終的に生成される MP4 ファイルは破損** し、症状が発生した後に再現も困難になる。
- Demuxer 側は特に `required_size == -1` (ファイル末尾までの読み込み要求) と組み合わさると 4 GiB 超で必ず発火する。破損 MP4 を解析する内部フローで、実際は EOF ではないのに `StopIteration` を投げるため、無音でサンプル取得を打ち切る。
- どちらも「大きなファイル」でしか顕在化しないため、通常の PBT / テストでは絶対に検出できない。放置するとリリース版で不具合の元になる。

## 現状

### Muxer 側 (`src/mp4_ext.cpp:1487`)

```cpp
raw_sample.data_size = static_cast<uint32_t>(sample.data.size());
```

`mp4.h:1117` で `Mp4MuxSample.data_size` は `uint32_t` として定義されている。C++ 側で 64 bit の `size_t` から無検査キャストしているため、`sample.data.size() > UINT32_MAX` (4 GiB) で silent truncation。

上流の 1469 行 `output_stream_.attr("write")(sample.data);` は full size を書き込むため、次サンプルで `tell()` が実位置を返し、Muxer 期待位置とずれて `MP4_ERROR_POSITION_MISMATCH` (`mp4.h:2148`) が発生する。

### Demuxer 側 (`src/mp4_ext.cpp:1000-1007`)

```cpp
error = mp4_file_demuxer_handle_input(demuxer_, required_pos, data_ptr,
                                      static_cast<uint32_t>(data_len));   // 切り捨て
check_error(error);

if (required_size > 0 && static_cast<int32_t>(data_len) < required_size) {  // 符号反転
  return true;
}
```

`data_len` は `size_t`。`mp4.h:1310-1313` で `input_data_size` は `uint32_t`。`required_size == -1` (`mp4.h:1229` 「ファイル末尾までのデータが必要」) の場合、Python の `input_stream_.attr("read")()` (991 行) が上限なく読むため、`data_len` が 4 GiB を超えうる。

さらに `static_cast<int32_t>(data_len)` は `data_len > 2^31` で負値になる。負値は `required_size (正)` より必ず小さいため、EOF 偽通知として `return true` が実行され、`next()` 側で `StopIteration` に変換される。

## 設計方針

### Muxer 側

- 書き込み前に `sample.data.size() > std::numeric_limits<uint32_t>::max()` を検査し、`Mp4Exception` を投げる
- **必ず書き込みの前** に検査すること。書いてから throw するとストリームだけが進み Muxer と乖離する

### Demuxer 側

- 事前に `data.size() > std::numeric_limits<uint32_t>::max()` を検査し、`Mp4Exception` を投げる
- 比較は `size_t` に統一する (`static_cast<size_t>(required_size)` へ寄せる)。`required_size` が負値の場合はそもそも早期 return なのでキャスト前に分岐する

## 完了条件

- Muxer の `append_sample` で `sample.data.size() > UINT32_MAX` の入力に対して `Mp4Exception` を投げ、`output_stream_.attr("write")` が呼ばれる前に例外化されている
- Demuxer の `feed_required_input` で `data.size() > UINT32_MAX` の入力に対して `Mp4Exception` を投げ、`mp4_file_demuxer_handle_input` に切り詰めた値が渡らない
- Demuxer の `feed_required_input` の EOF 判定で `int32_t` への符号反転が発生しない
- 追加テスト: `sample.data` に `bytes(2**32)` 相当の巨大データを持たせて `append_sample` を呼び、`Mp4Exception` が発火することを検証 (メモリ確保が現実的でないなら、`class HugeBytesLike` のような擬似オブジェクトを渡すか、境界値の直下 `UINT32_MAX - 1` と直上 `UINT32_MAX + 1` を切り替えられる mock 相当を用意する — ただし本プロジェクトはモック禁止規約なので実データで再現できる範囲に留める)

## 解決方法

1. `src/mp4_ext.cpp:1459-1493` の `append_sample()` 冒頭部分で `output_stream_.attr("write")` を呼ぶ前に以下を追加:
   ```cpp
   if (sample.data.size() > std::numeric_limits<uint32_t>::max()) {
     throw Mp4Exception("Sample data too large for Mp4MuxSample: " +
                        std::to_string(sample.data.size()) + " bytes (max: " +
                        std::to_string(std::numeric_limits<uint32_t>::max()) + " bytes)");
   }
   ```
2. `src/mp4_ext.cpp:997-1007` の EOF 比較を以下に置き換え:
   ```cpp
   const auto* data_ptr = static_cast<const uint8_t*>(data.data());
   size_t data_len = data.size();

   if (data_len > std::numeric_limits<uint32_t>::max()) {
     throw Mp4Exception("Input data too large for handle_input: " +
                        std::to_string(data_len) + " bytes");
   }

   error = mp4_file_demuxer_handle_input(demuxer_, required_pos, data_ptr,
                                         static_cast<uint32_t>(data_len));
   check_error(error);

   if (required_size > 0 &&
       data_len < static_cast<size_t>(required_size)) {
     return true;
   }
   ```
3. 単体テストを `tests/test_mp4.py` に追加。境界値 (UINT32_MAX 前後) を扱えるサイズで再現し、それ以上のサイズは擬似ストリーム経由で `Mp4Exception` を投げることを確認する
