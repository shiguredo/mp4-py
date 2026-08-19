# Demuxer を close した後の Mp4DemuxSample.data 読み出しを明確にする

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/doc-sample-data-after-close
- Polished: {YYYY-MM-DD}

## 目的

`Mp4FileDemuxer` を close した後、取得済みの `Mp4DemuxSample.data` を初回アクセスすると閉じたストリームへの seek/read で Python の `ValueError` になる挙動を明確にする。ドキュメントに記載するか、エラーを変換して明示的に報告する。

## 現状

`src/lib.rs` の `Mp4FileDemuxer::close` は `should_close_stream = true` のストリーム (ファイルパス / bytes 入力) を閉じる。その後、取得済みの `Mp4DemuxSample.data` に初回アクセスすると、`Mp4DemuxSample::data` の getter が閉じられたストリームに seek / read を呼び、Python の `ValueError` (閉じたファイルへの I/O) が素のまま伝播する。

`tests/test_free_threading.py` の `test_demuxed_samples_parallel_data_access` は BytesIO 直渡し (`should_close_stream = false`) に依存しており、「.data は close 前に読む」旨が API 文書に記載されていない。

## 設計方針

- `Mp4DemuxSample.data` のドキュメント (docstring) に「Demuxer を close する前に読み出すこと」を明記する
- エラーメッセージを明確にする場合、閉じたストリームへのアクセスを検出して `RuntimeError` 等で報告するか、Mp4Exception 化する (issue 0053 の型分類方針と整合)

## 完了条件

- 挙動がドキュメントに記載される
- 必要に応じてエラーが明確になる
- 既存テストが全通過する
