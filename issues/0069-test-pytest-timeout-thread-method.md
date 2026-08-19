# pytest-timeout のタイムアウト方式を検討する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/test-pytest-timeout-thread-method
- Polished: {YYYY-MM-DD}

## 目的

pytest-timeout の既定のタイムアウト方式 (signal) が、Free-Threading テストのデッドロック検出に十分か検証し、必要なら thread 方式に切り替える。テストハング時のセーフティネットの信頼性を高める。

## 現状

pyproject.toml の `timeout = 10` と CI の `--timeout=30` で pytest-timeout によるタイムアウトを設定している。既定のタイムアウト方式は signal ベースで、メインスレッドのみにシグナルを送る。

Free-Threading テスト (tests/test_free_threading.py) では ThreadPoolExecutor を使うが、デッドロックが起きた worker を `shutdown(wait=True)` が待つ間にタイムアウト例外が伝播しても、スレッドが終了しない限りプロセスが終了しない可能性がある。`timeout_method = "thread"` にするとタイムアウト例外がテストスレッド自体に送出され、より確実にテストを中断できる。

## 設計方針

- 実際のデッドロック状況を再現して signal / thread 両方式の挙動を比較する
- 必要に応じて pyproject.toml に `timeout_method = "thread"` を設定する
- テストスレッドの処理が確実に中断されることを確認する

## 完了条件

- タイムアウト時にテストプロセスが確実に終了する
- 方式変更後も既存テストが全通過する
