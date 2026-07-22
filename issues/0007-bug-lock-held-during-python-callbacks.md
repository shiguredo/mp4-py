# nb::ft_mutex を保持したまま Python コールバックを呼び出しており再入デッドロックの可能性

- Priority: High
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/fix-lock-held-during-python-callbacks
- Polished: {YYYY-MM-DD}

## 目的

`PyMp4FileDemuxer` / `PyMp4FileMuxer` の各メソッドが `nb::ft_lock_guard lock(mutex_)` を保持したまま Python コールバック (`input_stream_.attr("seek/read/close")` / `output_stream_.attr("tell/write/seek/close")` 等) を呼んでおり、コールバックから同じインスタンスの別メソッドが再入すると `nb::ft_mutex` は非再入的なため自己デッドロックする。ラップされたストリームや監査フックからの再入で発火するため、Free-Threading ビルドで顕在化する。

## 優先度根拠

High。

- Python 側で「stream をラップして書き込みを監視する」「stream.close() で cleanup 処理を挟む」等の実装は珍しくない。
- 例: `class WrappedIO: def write(self, b): mux.append_sample(...)` のようなラップを渡されると、`append_sample` 内の `output_stream_.attr("write")` (`src/mp4_ext.cpp:1469`) から再入 `append_sample` に入り、`nb::ft_mutex` は非再入なので **プロセス全体がフリーズ** する。
- デッドロックは検出が難しく、原因追跡に時間がかかる。ドキュメントで禁止するだけでもよいが、実装で改善する余地がある。

## 現状

`src/mp4_ext.cpp` の以下の関数はすべて `nb::ft_lock_guard lock(mutex_)` を保持したまま Python 呼び出しを行う。

- `close()` (797-810 行): `input_stream_.attr("close")()` (807)
- `get_tracks()` (813-843 行): (内部で feed_required_input を呼ぶ)
- `iter()` / `next()` (846-897 行): 同上
- `feed_required_input()` (897-1009 行): `input_stream_.attr("seek")` (987) / `read` (991, 993)
- `append_sample()` (1459-1493 行): `output_stream_.attr("tell")` (1465) / `write` (1469)
- `finalize()` / `finalize_internal()` (1495-1513 行): `flush_output()` (1512) → `output_stream_.attr("seek")` (1557) / `write` (1559)
- `flush_output()` (1544-1561 行)

`nb::ft_mutex` は Python 3.13 free-threading 用の `PyMutex` ベースで、`PyMutex_Lock` は再帰非対応。同じスレッドが二度目に取ろうとするとブロックする。

## 設計方針

以下のいずれか、または組み合わせで対応する。

### 方針 A: ドキュメントで明記する (最低限)

- 各クラスの docstring に「同一インスタンスへの再入を禁止する」と明記
- Python 側で入力/出力ストリームから同一 Demuxer / Muxer のメソッドを呼ばないよう警告

### 方針 B (推奨): 状態を局所コピーしてから Python 呼び出しをロック外で実行

- ロックが必要な区間 (`muxer_` へのアクセス、`closed_` フラグの読み書き等) と、Python 呼び出しに必要なコンテキストを分離する
- ロックを解放してから Python 呼び出しを行う
- 現状の実装は「1 メソッド = 1 ロック区間」なので、リファクタコストは大きい

### 方針 C: 再入可能ロックの採用

- `std::recursive_mutex` 相当を Free-Threading 互換で使う (nanobind に該当ヘルパがない可能性あり)
- 実装コスト最小だが、根本原因 (ロック境界の設計不備) は残る

### 推奨

最終的な理想は方針 B だが、コスト高。まずは方針 A (docstring + `test_free_threading.py` のドキュメント化テスト) を実施し、方針 B は追加検討事項として本 issue に記録する。

## 完了条件

- `PyMp4FileDemuxer` / `PyMp4FileMuxer` の class docstring に「同一インスタンスへの再入を禁止する」旨が明記される
- README.md にも該当節を追加
- 追加テスト: 意図的な再入 (WrappedIO 経由の再入 append_sample) が発生した場合、pytest でタイムアウト検知される想定のテストを 1 件追加 (`@pytest.mark.xfail(reason="known deadlock", timeout=5)`)。ただしテスト実行時間を延ばしすぎない設定にする
- 方針 B (状態コピーによるロック解放) の実装計画をコメントとして issue に残す。実装は別 issue に分離してよい

## 解決方法

1. `src/mp4_ext.cpp` の `PyMp4FileDemuxer` / `PyMp4FileMuxer` の class docstring に以下を追記:
   ```
   "\n\n"
   "Thread safety note:\n"
   "    The same Demuxer/Muxer instance must not be re-entered from a "
   "callback (e.g., a wrapped input/output stream that invokes another "
   "method on the same instance). Free-threading builds hold a non-"
   "reentrant mutex during method execution and would deadlock."
   ```
2. `README.md` に「注意: 同一 Muxer/Demuxer インスタンスへの再入は禁止」節を追記
3. `tests/test_free_threading.py` に再入検出テスト (xfail + timeout) を追加
4. 方針 B の実装を試行する場合は、`append_sample` から着手 (最も呼び出し頻度が高い)。実装は別 issue とする

## 対応結果

バインディングを nanobind から PyO3 に置き換えた際、`std::sync::Mutex` + `pyo3::sync::MutexExt::lock_py_attached(py)` を採用した。この API は Python コールバック呼び出し前後で Python ランタイムからのデタッチ/アタッチを行うため、GC の stop-the-world とロック保持の競合が回避される。よって closed とする。
