# Free-Threading で同一 Muxer への並列 append_sample テストが欠如

- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Branch: feature/test-add-free-threading-concurrent-muxer-append
- Polished: 2026-08-31
- Milestone: 2026.2.0

## 目的

Free-Threading ビルドは `CODEBASE.md` の Free-Threading 節が定めるサポート対象であり、同一 Muxer に対する `append_sample` の同時呼び出しを検証する必要がある。ところが `tests/test_free_threading.py` は `test_muxer_close_concurrent` による close の並列と、`test_multiple_muxers_parallel` による別インスタンスの並列しかカバーしていない。同一 Muxer に対する `append_sample` の同時呼び出しテストが 0 件のため、Free-Threading ビルドでの正しさが検証されていない。`CODEBASE.md` に「pyo3 0.29 では 3.14t 環境で並列に append_sample を回すとスケーリングが悪化する既知事象あり」と記録されている通り、この経路は実測上の問題が既知であり、回帰を検出するテストが特に価値を持つ。

## 現状

`tests/test_free_threading.py` にある関連テスト:

- `test_muxer_close_concurrent`: 8 スレッドから close を並列に呼ぶ
- `test_multiple_muxers_parallel`: 別インスタンスの Muxer を並列に動かす

同一 Muxer に対する `append_sample` の並列呼び出しは検証なし。実装側は `src/lib.rs` の `Mp4FileMuxer::append_sample` が `lock_py_attached` で状態ロックを取得したまま tell / write を実行するため、並列呼び出しは Muxer 内部で直列化される。この直列化が正しく機能して全サンプルが mux されることを固定するテストが欠けている。

なお、本ファイルの全テストはファイル先頭の `pytestmark` (GIL 有効時スキップ) により Free-Threading (3.14t) ビルドでだけ実行される。

## 設計方針

- Python 側の `threading.Lock` は使わない。Python 側で直列化すると Muxer 内部の状態ロックが検証対象から外れ、逐次実行と等価になる
- 全サンプルで同一の `Mp4SampleEntryVp08` を明示的に渡す。`sample_entry=None` はコア仕様では「前のサンプルと同じ」を意味し、先頭サンプル (新規チャンクの解決) で `None` だと `MissingSampleEntry` になるため、どのスレッドが先に追加するかで結果が変わらない入力を用意する
- 8 スレッドから独立サンプルを append → finalize → demux で全サンプル復元とデータ整合性を確認する
- サンプルには一意な pattern (thread_id + sample_index の組み合わせ) を埋め込み、demux 側で識別可能にする

## 完了条件

- 8 スレッドから同一 Muxer への並列 `append_sample` が競合なく完了し、全サンプルが mux される
- demux で 80 サンプル (8 スレッド × 10 サンプル) がすべて復元でき、各サンプルのデータが thread_id とサンプル番号から決まる期待値と一致する
- Free-Threading (3.14t) ビルドで通過し、GIL 有効ビルドでは既存の `pytestmark` によりスキップされる
- pytest のタイムアウト (既定 10 秒) 内で完走する

## 解決方法

1. `tests/test_free_threading.py` に以下のテストを追加する:

```python
def test_muxer_concurrent_append() -> None:
    """複数スレッドから同一 Muxer に append_sample を並列に呼んでも壊れない

    目的: Mp4FileMuxer が内部の状態ロックで append_sample を直列化する実装
          のもとで、全サンプルが正しく mux されることを確認する
    検証: demux で全 80 サンプルが重複なく取得でき、各サンプルのデータが
          thread_id とサンプル番号から決まる期待値と一致すること
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)
    samples_per_thread = SAMPLES_PER_FILE

    def append_samples(thread_id: int) -> None:
        for i in range(samples_per_thread):
            # thread_id と i を一意なインデックスに変換してデータに埋め込む
            data = create_dummy_sample(thread_id * samples_per_thread + i)
            sample = Mp4MuxSample(
                track_kind="video",
                # None は「前のサンプルと同じ」を意味し、先頭サンプルの
                # タイミングに依存するため、全サンプルで明示的に渡す
                sample_entry=sample_entry,
                keyframe=True,
                timescale=1000000,
                duration=33333,
                data=data,
            )
            muxer.append_sample(sample)

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        list(executor.map(append_samples, range(NUM_THREADS)))

    muxer.finalize()

    # demux し直して全サンプルが取得できることを確認する
    output_buffer.seek(0)
    with Mp4FileDemuxer(output_buffer) as demuxer:
        samples = list(demuxer)

    assert len(samples) == NUM_THREADS * samples_per_thread
    # データは thread_id とサンプル番号から決定的に生成されるため、
    # 欠落と重複は集合の不一致として検出できる
    expected = {
        create_dummy_sample(thread_id * samples_per_thread + i)
        for thread_id in range(NUM_THREADS)
        for i in range(samples_per_thread)
    }
    assert {sample.data for sample in samples} == expected
```

2. 実行時間が長い場合は `@pytest.mark.timeout(30)` を付ける (pytest-timeout のマーカー)
