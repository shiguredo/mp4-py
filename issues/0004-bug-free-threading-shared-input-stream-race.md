# Free-Threading で PyMp4DemuxSample と Demuxer が共有する input_stream が未保護

- Priority: High
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-free-threading-shared-input-stream-race
- Polished: {YYYY-MM-DD}

## 目的

`PyMp4DemuxSample` は Demuxer が保持する `input_stream_` (Python file object) を同一オブジェクトのまま共有している。`get_data()` は `nb::lock_self()` (自オブジェクトのロック) しか取らず、Demuxer 側の `feed_required_input()` は Demuxer の `nb::ft_mutex mutex_` を取る。ロックが独立しているため、Free-Threading で複数の `PyMp4DemuxSample` の `.data` を別スレッドから並列にアクセスすると、共有ストリームに対する `seek` / `read` が race する古典的 TOCTOU となり、**別サンプルのデータを掴んで返す** 可能性がある。

## 優先度根拠

High。

- `CMakeLists.txt:105` で `FREE_THREADED` を宣言しており、Free-Threading ビルド (Python 3.14t 等) を正式サポート対象としている。
- 症状はデータの静かな取り違え。サイズ一致チェック (`src/mp4_ext.cpp:732-736`) は同サイズの別サンプルなら通過してしまうため、テスト・検証で気付かない可能性が高い。
- `test_free_threading.py:253` 等の既存テストは `next()` と `sample.data` を同一 `with lock:` 内で直列化しており、この race を全く踏まない。実運用で「demux 全サンプルを取得してから並列に .data アクセス」というごく自然なパターンで発火する。

## 現状

### 共有ポイント

`src/mp4_ext.cpp:891` の Demuxer `next()` 内で、生成したサンプルに Demuxer の入力ストリームを渡している。

```cpp
result.input_stream_ = input_stream_;
```

`PyMp4DemuxSample::get_data()` (`src/mp4_ext.cpp:721-739`) は以下を実行。

```cpp
nb::bytes get_data() {
  if (!data_cache_) {
    ...
    input_stream_.attr("seek")(data_offset_);
    nb::object read_result = input_stream_.attr("read")(data_size_);
    data_cache_ = nb::cast<nb::bytes>(read_result);
    ...
  }
  return *data_cache_;
}
```

バインディングは `src/mp4_ext.cpp:2074` で `nb::lock_self()` を指定しているが、これは **自身の PyMp4DemuxSample オブジェクト** のロックであり、共有 file object や Demuxer のロックとは無関係。

Demuxer 側の `feed_required_input()` (`src/mp4_ext.cpp:897-1009`) も同じ `input_stream_` に対して `seek` / `read` を実行するが、こちらは Demuxer の `nb::ft_mutex mutex_` (904 行) を取っている。

### レース発生シナリオ

1. スレッド A が `sample_a.data` を呼び、`input_stream_.attr("seek")(offset_a)` を実行
2. スレッド B が同時に `sample_b.data` を呼び、`input_stream_.attr("seek")(offset_b)` を実行
3. スレッド A が `input_stream_.attr("read")(size_a)` を実行 → 実際に読まれるのは offset_b からの size_a バイト
4. `data_cache_->size() != data_size_` チェック (`src/mp4_ext.cpp:732-736`) は size_a と size_b が偶然一致すると通過し、**サンプル A のはずが offset_b のデータを返す**

`io.BytesIO` は 3.14t でオブジェクト単位のロックがあるため crash は避けられるが、seek 位置の取り合いはロックでは救えない。

## 設計方針

以下のいずれかを採用する。両方の trade-off を検討したうえで、実装は方針 A を推奨する。

### 方針 A (推奨): ストリーム専用ロックを Demuxer 側で保持し、Sample から共有参照する

- Demuxer 側に `std::shared_ptr<nb::ft_mutex>` として「ストリーム排他用ロック」を持たせる
- `PyMp4DemuxSample` に同じ `shared_ptr` を渡す
- `get_data()` と `feed_required_input()` の seek+read シーケンスをそのロックで囲む
- Demuxer が破棄されてもロックオブジェクトは Sample が生きている限り残るため、後片付けが安全

### 方針 B: `next()` の時点でストリームから即読み込み、`input_stream_` を Sample に保持させない

- 遅延読み込みを捨てて、`data_cache_` を `next()` 時点で埋める
- API 変更は起きないが、大量サンプルを列挙するだけで全データがメモリに載る (現状の遅延読み込みの利点を失う)
- パフォーマンス影響が大きすぎるため非推奨

## 完了条件

- 複数の `PyMp4DemuxSample` の `.data` を並列に読み出しても、常に正しいサンプルデータが返る
- Demuxer 側の `feed_required_input()` と Sample 側の `get_data()` が同一ストリームロックで直列化される
- 追加テスト: 複数サンプルを demux した後、8 スレッドから独立に `.data` を読み出して data hash を検証するテストを追加 (`test_free_threading.py`)
- 追加テスト: 同一 Demuxer に対して `next()` を続けているスレッドと、既に取得したサンプルの `.data` を読むスレッドを混在させても壊れないことを検証

## 解決方法

1. `PyMp4FileDemuxer` に以下を追加:
   ```cpp
   std::shared_ptr<nb::ft_mutex> stream_mutex_ =
       std::make_shared<nb::ft_mutex>();
   ```
2. `next()` (`src/mp4_ext.cpp:853-897`) の中で `PyMp4DemuxSample` に `stream_mutex_` を渡す
3. `PyMp4DemuxSample` に `std::shared_ptr<nb::ft_mutex> stream_mutex_;` を追加
4. `PyMp4DemuxSample::get_data()` の seek + read を `nb::ft_lock_guard lock(*stream_mutex_);` で囲む
5. `PyMp4FileDemuxer::feed_required_input()` の seek + read も `stream_mutex_` を取ってから実行するように変更 (Demuxer 側 `mutex_` の内側で追加ロックを取る形になる。デッドロックを避けるため順序を統一)
6. 上記変更に合わせて、`nb::lock_self()` を `def_prop_ro("data", ...)` から外すか残すかは要検討 (残しても実害はないが、意味が曖昧になる)
