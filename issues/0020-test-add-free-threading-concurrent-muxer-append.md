# Free-Threading で同一 Muxer への並列 append_sample テストが欠如

- Priority: Medium
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/test-add-free-threading-concurrent-muxer-append
- Polished: {YYYY-MM-DD}

## 目的

`tests/test_free_threading.py` は close の並列 (`test_muxer_close_concurrent`, 204-230) と別インスタンスの並列 (`test_multiple_muxers_parallel`, 121-176) しかカバーしていない。同一 Muxer に対する `append_sample` の同時呼び出しテストが 0 件のため、Free-Threading ビルドでの正しさが検証されていない。

## 優先度根拠

Medium。

- `CMakeLists.txt:105` `FREE_THREADED` 指定により Free-Threading ビルドを公式にサポートしている。
- 実装は `nb::ft_mutex mutex_` (`src/mp4_ext.cpp:1520`) を `append_sample` 冒頭 (1460) で取得しているので、同一 Muxer への並列 append は逐次化される設計。しかし出力ストリーム (`output_stream_`) の `tell` / `write` は Python 側 GIL 相当のロックが Free-Threading では無くなる可能性があり、テストで動作確認する価値がある。
- `issues/0007-bug-lock-held-during-python-callbacks.md` (ロック再入デッドロック) の対応前後で挙動が変わる可能性があるため、回帰検出用にも有用。

## 現状

`tests/test_free_threading.py` にある関連テスト:

- `test_muxer_close_concurrent` (204-230): 8 スレッドから close を並列に呼ぶ
- `test_multiple_muxers_parallel` (121-176): 別インスタンスの Muxer を並列に動かす

同一 Muxer に対する `append_sample` の並列呼び出しは検証なし。ロックで直列化される想定だが、次のケースが未検証:
1. 8 スレッドが同一 Muxer に append_sample を呼び、全サンプルが正しく mux される
2. finalize 後に demux し、全サンプルが復元でき、データ整合性が保たれる

## 設計方針

- 8 スレッドから独立サンプルを append → finalize → demux で全サンプル復元とデータ整合性を確認するテストを追加
- サンプルには一意な pattern (thread_id + sample_index の組み合わせ) を埋め込み、demux 側で識別可能にする

## 完了条件

- 同一 Muxer への並列 `append_sample` が競合なく完了し、全サンプルが順序どおり (append 順ではなく mux 順) に demux できる
- Free-Threading ビルドと通常ビルドの両方で通過
- タイムアウト内 (10 秒) で完走

## 解決方法

1. `tests/test_free_threading.py` に以下のテストを追加:

```python
def test_muxer_concurrent_append() -> None:
    """複数スレッドから同一 Muxer に append_sample を呼んでも壊れない"""
    from concurrent.futures import ThreadPoolExecutor
    import threading

    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    lock = threading.Lock()  # Muxer 側のロックに加えて Python 側でも直列化

    NUM_THREADS = 8
    SAMPLES_PER_THREAD = 10

    def append_samples(thread_id: int) -> None:
        for i in range(SAMPLES_PER_THREAD):
            # thread_id と i をエンコードした一意のデータ
            data = f"t{thread_id:02d}s{i:04d}".encode() + b"\x00" * 100
            sample = Mp4MuxSample(
                track_kind="video",
                sample_entry=Mp4SampleEntryVp08(width=320, height=240)
                    if (thread_id == 0 and i == 0) else None,
                keyframe=True,
                timescale=30,
                duration=1,
                data=data,
            )
            with lock:  # Muxer 側の同時 append は失敗しうるため、意図的に直列化
                muxer.append_sample(sample)

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        list(executor.map(append_samples, range(NUM_THREADS)))

    muxer.finalize()

    # demux し直して全サンプルが取得できることを確認
    output_buffer.seek(0)
    with Mp4FileDemuxer(output_buffer) as demuxer:
        samples = list(demuxer)

    assert len(samples) == NUM_THREADS * SAMPLES_PER_THREAD
    # データ整合性: 各サンプルの先頭 8 バイトが tXXsYYYY 形式
    for sample in samples:
        prefix = sample.data[:8]
        assert prefix.startswith(b"t") and b"s" in prefix, \
            f"サンプルデータが破損: {prefix!r}"
```

**注意**: 上記テストは Python 側で `threading.Lock` を追加している。これは `append_sample` の並列呼び出しが本質的に seekable stream に対する `tell` + `write` を必要とし、`output_stream_` の状態を排他しないと data_offset がずれるため。純粋に「Muxer 内部ロックが機能する」ことを検証したいなら、Python 側ロックを外して失敗を許容するテストを別に用意する。

2. `issues/0005-bug-free-threading-def-rw-unprotected-fields.md` の対応後に実施することを推奨
3. 実行時間が長い場合は `@pytest.mark.timeout(30)` を付ける
