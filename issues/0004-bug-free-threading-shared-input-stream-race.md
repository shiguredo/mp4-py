# Free-Threading で Mp4DemuxSample と Demuxer が共有する input_stream のレース (実装済み・テスト未達)

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-free-threading-shared-input-stream-race
- Polished: 2026-08-12

## 目的

Free-Threading (Python 3.14t) で、Demuxer と `Mp4DemuxSample` が共有する input_stream (Python file object) への `seek` / `read` が race し、別サンプルのデータを返す問題の回帰テストを追加する。実装は PyO3 移行時に完了済みであり、本 issue の残作業は検証テストのみ。

## 優先度根拠

High。

- mp4-py は Free-Threading ビルド (Python 3.14t) を正式サポート対象としている (CODEBASE.md の Free-Threading 節)。
- 症状はデータの静かな取り違えで、テスト・検証で気付かない可能性が高い。
- 実装は完了済みだが、それを保証するテストが存在しない。

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

1. `tests/test_free_threading.py` に「複数サンプルを demux した後、8 スレッドから独立に `.data` を読み出して全バイト比較するテスト」を追加する
2. `tests/test_free_threading.py` に「同一 Demuxer の `next()` を続けるスレッドと取得済みサンプルの `.data` を読むスレッドを混在させるテスト」を追加する
3. `NO_UV_SYNC=1 uv run pytest tests/test_free_threading.py --timeout=10` で 3.14t 環境にて全通過を確認する
