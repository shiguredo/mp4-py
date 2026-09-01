# Free-Threading テストがスレッドデッドロック時に pytest プロセスごとハングする

- Created: 2026-08-13
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-pytest-hang-on-thread-deadlock
- Polished: 2026-09-01
- Milestone: 2026.2.0

## 目的

Free-Threading テストで、テスト対象コードがスレッドデッドロック (バグ実装) に陥った場合に pytest プロセスがハングし、pytest-timeout の 10 秒で検出できない問題を解消する。テストが検出すべきデッドロックという症状を、テスト自体のハングによって検出できないのは本末転倒である。CI ではジョブタイムアウト (`.github/workflows/wheel.yml` の `timeout-minutes`) まで検出が遅れ、デッドロックを含む変更のマージ事故につながる。

## 現状

`tests/test_free_threading.py` の全テスト (7 件) は `with ThreadPoolExecutor(...)` + `f.result()` でワーカーの完了を待つ構造である。

pytest-timeout の signal 方式は、タイムアウト時に SIGALRM でテスト関数の実行フレームへ `TimeoutExpired` を raise する。しかし、`with ThreadPoolExecutor` の `__exit__` は `shutdown(wait=True)` を実行し、デッドロックしたワーカーの `join()` でメインスレッドが永久ブロックする。SIGALRM は 1 回しか発火しないため、このブロックは中断できず、pytest プロセスがハングする。

これは新規テストに限らず、既存の ThreadPoolExecutor 使用テスト (test_demuxer_concurrent_iteration 等) すべてに共通する構造である。

関連する既知の制約として、pytest-timeout の signal 方式は Python レベルの実行中しかシグナルを処理できない点は issues/closed/0016-test-add-pytest-timeout-config.md の注記にもあるが、本 issue は「設定不足」ではなく「スレッド join によるハング」が問題であり、別の対象である。Windows では thread 方式が既定でタイムアウト時にプロセス全体を強制終了するため、この問題は当てはまらない。

## 設計方針

対応はテスト側の終了待ち構造の変更のみとし、実装コードには影響を与えない。

### 方針 A: ワーカー完了待ちをタイムアウト付きにし、ハング時に失敗として報告する

- ThreadPoolExecutor は `with` コンテキストマネージャで使わず、明示的に生成と shutdown を管理する。`with` の `__exit__` は `shutdown(wait=True)` を実行してデッドロックワーカーの `join()` でブロックするため、残したままだと現状と同じハングになる
- `f.result()` での無制限待ちをやめ、`concurrent.futures.as_completed(futures, timeout=N)` で完了待ちする
- タイムアウト時は `executor.shutdown(wait=False, cancel_futures=True)` でワーカーを打ち切り、テスト失敗として報告する
- 正常に全ワーカーが完了した場合のみ `executor.shutdown(wait=True)` を呼び、ワーカースレッドを確実に終了させる
- 実行中ワーカーの強制終了は Python の ThreadPoolExecutor では不可能なため、ワーカーが残る場合のプロセス終了時の join ハングは完全には防げない。その場合は CI のジョブタイムアウトが最終手段となる (0016 の注記と同じ扱い)
- N は pytest のタイムアウト (10 秒) より短い値とする

### 方針 B: ポーリングに上限を設ける

- queue ポーリング型のテスト (test_demuxer_next_with_parallel_data_access 等) は、ポーリング回数に上限を設けて異常終了を検出する
- 方針 A と併用する。方針 A は executor の完了待ちを対象とし、方針 B はデッドロック時に reader スレッドが無限ポーリングして残存スレッドを増やすのを防ぐ補助である

## 完了条件

- `tests/test_free_threading.py` の ThreadPoolExecutor 使用テスト (7 件すべて) が、ワーカーのデッドロック時にテストをタイムアウト失敗として報告し、デッドロックをテストハングで隠さない
- ワーカー残存によるプロセス終了時の join ハングは防げないため、CI のジョブタイムアウトを最終手段として許容する
- 正常時は既存の全テストが変更前と同じく通過する (3.14t CI は test_free_threading.py 7 件と test_mp4.py 72 件を実行、GIL 有効環境は 133 passed / 7 skipped。2026-09-01 時点)
- テスト実行は CODEBASE.md の pytest 規約 (60 秒以内、`--timeout=10`) 内で完走する

## 解決方法

1. ThreadPoolExecutor を `with` コンテキストマネージャで使わず、明示的な生成と shutdown の管理に変更する (`__exit__` の `shutdown(wait=True)` がデッドロックワーカーの `join()` でブロックするため)
2. `tests/test_free_threading.py` の全 ThreadPoolExecutor 使用テストの完了待ちを、`concurrent.futures.as_completed(futures, timeout=N)` + タイムアウト時の `executor.shutdown(wait=False, cancel_futures=True)` に変更する
3. queue ポーリング型テスト (test_demuxer_next_with_parallel_data_access) にポーリング回数の上限を設ける
4. タイムアウト時の失敗メッセージは日本語で、デッドロックの可能性を明示する
5. 変更後は 3.14t 環境で全テスト通過を確認する (`NO_UV_SYNC=1 uv run pytest tests/test_free_threading.py --timeout=10`)
6. 正常時は既存の全テスト (GIL 有効環境を含む) が通過することを確認する
