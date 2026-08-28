# Free-Threading で Mp4DemuxSample と Demuxer が共有する input_stream のレース (実装済み・テスト未達)

- Created: 2026-07-22
- Completed: 2026-08-13
- Branch: feature/fix-free-threading-shared-input-stream-race
- Polished: 2026-08-12

## 目的

Free-Threading ビルド (Python 3.14t) は `CODEBASE.md` の Free-Threading 節が定める正式サポート対象である。その環境で、Demuxer と `Mp4DemuxSample` が共有する input_stream (Python file object) への `seek` / `read` が race し、別サンプルのデータを返す問題の回帰テストを追加する。症状はデータの静かな取り違えであり、テスト・検証で気付きにくい点が危険だった。実装は PyO3 移行時に完了済みであり、本 issue の残作業は検証テストのみ。

## 現状

### 実装済みの内容

PyO3 移行時 (コミット 5694230) に、issue の設計方針 A 相当の実装が `src/lib.rs` に導入済みである:

- `Mp4FileDemuxer` が `stream_lock: Arc<Mutex<()>>` を保持
- `__next__` で生成する `Mp4DemuxSample` に `Arc::clone(&self.stream_lock)` で同一ロックを共有
- `Mp4DemuxSample` の `data` getter は seek + read を `stream_lock` のロック内で完結
- `feed_required_input()` も同じ `stream_lock` を取得してから seek + read を実行
- ロック順序は state → stream_lock で統一されており、逆順経路はない (デッドロックなし)

### 未達の内容

完了条件のテスト 2 件が `tests/test_free_threading.py` に存在しない:

1. 「複数サンプルを demux した後、8 スレッドから独立に `.data` を読み出して検証するテスト」
2. 「同一 Demuxer に対して `next()` を続けているスレッドと、既に取得したサンプルの `.data` を読むスレッドを混在させるテスト」

既存の `test_demuxer_concurrent_iteration` (tests/test_free_threading.py) は各スレッドが next() 直後に自分のスレッドで `.data` を読む構成で、「demux 全サンプル取得後に別スレッドから並列に `.data` アクセス」という発火経路を実質的に踏みにくい。

## 設計方針

- 実装は完了済みのため、追加の設計は不要
- テスト追加のみを実施する

## 完了条件

- 追加テスト: 複数サンプルを demux した後、8 スレッドから独立に `.data` を読み出してデータの一致を検証するテストを `tests/test_free_threading.py` に追加する
  - 検証は data hash ではなく、既存テスト (`test_demuxer_concurrent_iteration`) と同じ全バイト直接比較とする (hash は衝突の懸念があるため)。期待値は `create_dummy_sample(i)` とサンプル順で対応する
- 追加テスト: 同一 Demuxer に対して `next()` を続けているスレッドと、既に取得したサンプルの `.data` を読むスレッドを混在させても壊れないことを検証するテストを `tests/test_free_threading.py` に追加する
  - 検証はテスト 1 と同じく、全サンプルの `.data` が期待値と全バイト一致することを確認する
  - このテストの目的は「並行 `next()` と `.data` 読み出しのストレス下で全バイト一致する」ことの検証である。サンプル取得時点で moov の読み込みは完了しているため、`feed_required_input` との I/O 競合が発生する構造ではない点に注意する
- 追加テストは 3.14t (Free-Threading) 環境で実行される前提とし、CODEBASE.md の pytest 規約 (60 秒以内、`--timeout=10`) 内で完走する

## 解決方法

`tests/test_free_threading.py` に回帰テスト 2 件を追加した。実装 (stream_lock 共有) は既存のまま変更なし。

- `test_demuxed_samples_parallel_data_access`: demux 完了後の全サンプルの `.data` を 8 スレッドから barrier で同時突入して読み出し、タイムスタンプでソートして `create_dummy_sample(i)` と全バイト直接比較する
- `test_demuxer_next_with_parallel_data_access`: `next()` を続けるスレッド (1 本) と、取得済みサンプルの `.data` を読むスレッド (7 本) を queue で受け渡して混在させ、全サンプルの `.data` が期待値と全バイト一致することを検証する
  - next スレッドは 1 本に限定した。複数本だと「最後のサンプルの put」と「取得完了イベントの set」の順序が保証されず、取りこぼしのフレークが起きるため
- 検証は data hash ではなく既存テストと同じ全バイト直接比較。期待値は `create_dummy_sample(i)` とサンプル順で対応
- 3.14t 環境で 7 件全通過 (0.14 秒)、GIL 有効環境 (3.12) では 91 passed / 7 skipped を確認済み
- CHANGES.md の `## develop` の `### misc` にテスト追加エントリを追記した
