# Free-Threading の並行 I/O 競合テストを追加する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/test-free-threading-io-race
- Polished: {YYYY-MM-DD}

## 目的

Free-Threading (GIL 無効) 環境で、Demuxer の feed 処理と Mp4DemuxSample.data の読み出しが並行実行されるケースをテストで検証する。stream_lock による直列化が設計どおり機能することを実測で担保する。

## 現状

`src/lib.rs` の Mp4FileDemuxer は、feed_required_input と Mp4DemuxSample.data の間で stream_lock を共有し、seek + read の競合を直列化する設計になっている。しかし、tests/test_free_threading.py の注記が自認する通り、moov 読み込みは最初の next() で完了するため、以降の next() は I/O を発生させず、実際に「feed 処理と sample.data の並行 I/O が競合する」ケースは一度も実行されない。

stream_lock が直列化するはずの経路の並行実行がテストで検証されておらず、ロックの破綻 (データ混線) があっても検出できない。

## 設計方針

- 並行して sample.data を読みつつ、別スレッドで demuxer の反復 (あるいは新規の demuxer 構築) を進めるテストを追加する
- 読み出したデータが混線していないことを検証する (各 sample のデータサイズ・内容の一致)
- Free-Threading 環境でのみ実行される skipif を付ける

## 完了条件

- feed と sample.data の並行 I/O 競合がテストで実行される
- データの混線が検出できる (ロックが壊れた場合にテストが失敗する)
- 既存テストが全通過する
