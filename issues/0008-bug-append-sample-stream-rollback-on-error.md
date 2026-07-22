# append_sample 失敗時に write 済みバイトがストリームに残って以降破綻する

- Priority: Medium
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-append-sample-stream-rollback-on-error
- Polished: {YYYY-MM-DD}

## 目的

`PyMp4FileMuxer::append_sample()` は「(1) 出力ストリームに `sample.data` を書き込む → (2) `mp4_file_muxer_append_sample()` を呼ぶ → (3) `check_error()` で結果検証」の順序で処理する。ステップ (2) 以降で失敗した場合、Muxer 側は「サンプル未追加」の状態のままだがストリーム位置だけが進んでしまい、以降の `append_sample()` は必ず `MP4_ERROR_POSITION_MISMATCH` で失敗し続ける。この不整合を解消する。

## 優先度根拠

Medium。

- 失敗ケースは異常系だが、ユーザー入力が原因 (無効な sample_entry、範囲外の composition_time_offset 等) の場合に発生し、リカバリ不能な状態に陥る。
- 現状はドキュメント上の記載もなく、ユーザーは「例外を catch して次のサンプルを試す」流儀で書きたくなるが、それが破綻する。
- 修正は Python 側 stream の seekable 判定と truncate 呼び出しの追加で可能。

## 現状

`src/mp4_ext.cpp:1459-1493` の実装。

```cpp
void append_sample(PyMp4MuxSample& sample) {
  nb::ft_lock_guard lock(mutex_);
  if (closed_)
    throw Mp4Exception("Muxer is closed");

  nb::object tell_result = output_stream_.attr("tell")();
  uint64_t data_offset = nb::cast<uint64_t>(tell_result);

  output_stream_.attr("write")(sample.data);   // ← 書き込み

  SampleEntryConverter converter;
  converter.convert(sample.sample_entry);

  Mp4MuxSample raw_sample;
  ...

  Mp4Error error = mp4_file_muxer_append_sample(muxer_, &raw_sample);
  check_error(error);                          // ← ここで throw

  flush_output();
}
```

`check_error` が throw すると、`output_stream_` には `sample.data` が書き込まれたままで、次の `append_sample` 呼び出しでは `tell()` が実位置を返すが Muxer は元の位置を期待し、`MP4_ERROR_POSITION_MISMATCH` (`mp4.h:2148`) が発生する。

`mp4.h:2122-2200` のドキュメントには「サンプルデータをファイルに書き込み → append_sample」の順序が規定されており、この順序自体は正しい。しかし失敗時の巻き戻しは実装依存で、mp4-py 側は現在何もしていない。

## 設計方針

### 方針 A (推奨): seekable なストリームでは truncate + seek で巻き戻す

- `output_stream_` に対して `seekable()` / `truncate()` が使えるか判定
- `check_error` が throw する前に `output_stream_.attr("seek")(data_offset)` + `output_stream_.attr("truncate")()` で巻き戻す
- 巻き戻せない場合 (パイプ等) はドキュメント通り「Muxer を破棄すべし」と例外メッセージに書く

### 方針 B: ドキュメントで「append_sample 失敗後は Muxer を破棄すべし」と明記

- 実装コスト最小、ユーザー責任
- 現状無記載なので、少なくともこれは実施する

## 完了条件

- `append_sample()` 中に `check_error` が throw した場合、seekable なストリームならストリーム位置が呼び出し前に戻る
- seekable でないストリームの場合、例外メッセージに「Muxer は使用不能状態になった。破棄すること」と明記される
- README.md / class docstring に「append_sample が失敗した場合の挙動」を明記
- 追加テスト: 意図的に append_sample を失敗させ (無効な composition_time_offset 等)、その後 `tell()` の位置が変わらないことを確認するテスト (seekable ストリームで)
- 追加テスト: 同シナリオを retry パターンで実行し、2 度目の append_sample が成功することを確認

## 解決方法

1. `src/mp4_ext.cpp:1459-1493` の `append_sample()` を以下に変更:
   ```cpp
   void append_sample(PyMp4MuxSample& sample) {
     nb::ft_lock_guard lock(mutex_);
     if (closed_)
       throw Mp4Exception("Muxer is closed");

     nb::object tell_result = output_stream_.attr("tell")();
     uint64_t data_offset = nb::cast<uint64_t>(tell_result);

     output_stream_.attr("write")(sample.data);

     SampleEntryConverter converter;
     converter.convert(sample.sample_entry);

     Mp4MuxSample raw_sample;
     // ... (フィールド設定は現状通り)

     Mp4Error error = mp4_file_muxer_append_sample(muxer_, &raw_sample);
     if (error != MP4_ERROR_OK) {
       try_rollback_stream(data_offset);
       check_error(error);
     }

     flush_output();
   }

   void try_rollback_stream(uint64_t offset) {
     try {
       if (nb::hasattr(output_stream_, "seekable") &&
           nb::cast<bool>(output_stream_.attr("seekable")()) &&
           nb::hasattr(output_stream_, "truncate")) {
         output_stream_.attr("seek")(offset);
         output_stream_.attr("truncate")();
       }
     } catch (...) {
       // 巻き戻し失敗は無視。呼び出し元で throw される例外を優先
     }
   }
   ```
2. `PyMp4FileMuxer` の class docstring に「append_sample が失敗した場合、非 seekable ストリームでは Muxer を破棄すること」と明記
3. `README.md` の Muxer 節に同じ記載を追加
4. `tests/test_mp4.py` に retry パターンのテストを追加
