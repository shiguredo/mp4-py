"""Free-Threading (GIL フリー) 環境でのスレッドセーフティテスト

このテストは複数スレッドから同時にオブジェクトを操作し、
データ競合やクラッシュが発生しないことを確認する。

テスト対象:
1. 複数の独立したインスタンスの並列使用 (グローバル状態の競合検出)
2. close() の concurrent 呼び出し (ロックの冪等性確認)
3. 同一 Demuxer の並列イテレーション (ロック動作 + データ整合性確認)

Free-Threading テストを実行するには:
    uv run -p 3.14t pytest tests/test_free_threading.py -v -s

ビルドも Free-Threading 環境で行う必要がある:
    uv build -p 3.14t
"""

import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
)


def is_gil_enabled() -> bool:
    """GIL が有効かどうかを確認"""
    if hasattr(sys, "_is_gil_enabled"):
        return sys._is_gil_enabled()
    return True


# Free-Threading 環境でない場合は全テストをスキップ
pytestmark = pytest.mark.skipif(
    is_gil_enabled(),
    reason="Free-Threading テストは GIL 無効の Python (例: Python 3.13t, 3.14t) が必要です",
)

NUM_THREADS = 8
SAMPLES_PER_FILE = 10


def create_dummy_sample(index: int, size: int = 1024) -> bytes:
    """テスト用のダミーサンプルデータを生成 (インデックスから決定的に生成)"""
    data = bytearray(size)
    for j in range(size):
        data[j] = (index * 17 + j) & 0xFF
    return bytes(data)


def create_test_mp4_buffer(sample_count: int = SAMPLES_PER_FILE) -> io.BytesIO:
    """テスト用の MP4 データを生成"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    for i in range(sample_count):
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=Mp4SampleEntryVp08(width=1920, height=1080),
            keyframe=True,
            timescale=1000000,
            duration=33333,
            data=create_dummy_sample(i),
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()
    output_buffer.seek(0)
    return output_buffer


# =============================================================================
# グローバル状態の競合検出テスト
# =============================================================================


def test_multiple_demuxers_parallel():
    """複数の Demuxer インスタンスを並列で使用

    目的: mp4-rust ライブラリ内部のグローバル状態がスレッドセーフであることを確認
    検証: 各スレッドで全サンプルが正しく読み取れること
    """
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(NUM_THREADS)

    def process_demuxer(thread_id: int):
        barrier.wait()
        mp4_buffer = create_test_mp4_buffer()
        demuxer = Mp4FileDemuxer(mp4_buffer)

        tracks = demuxer.tracks
        samples = list(demuxer)

        # サンプルデータの内容を検証
        data_valid = all(sample.data == create_dummy_sample(i) for i, sample in enumerate(samples))

        with lock:
            results.append((thread_id, len(tracks), len(samples), data_valid))
        demuxer.close()

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(process_demuxer, i) for i in range(NUM_THREADS)]
        for f in futures:
            f.result()

    assert len(results) == NUM_THREADS
    for thread_id, track_count, sample_count, data_valid in results:
        assert track_count == 1, f"Thread {thread_id}: unexpected track count"
        assert sample_count == SAMPLES_PER_FILE, f"Thread {thread_id}: unexpected sample count"
        assert data_valid, f"Thread {thread_id}: sample data corrupted"


def test_multiple_muxers_parallel():
    """複数の Muxer インスタンスを並列で使用

    目的: mp4-rust ライブラリ内部のグローバル状態がスレッドセーフであることを確認
    検証: 生成した MP4 を Demuxer で読み取り、内容が正しいか確認
    """
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(NUM_THREADS)
    samples_per_thread = 5

    def process_muxer(thread_id: int):
        barrier.wait()
        output_buffer = io.BytesIO()
        muxer = Mp4FileMuxer(output_buffer)

        # スレッドごとに異なるデータを書き込み
        expected_data = []
        for i in range(samples_per_thread):
            sample_data = create_dummy_sample(thread_id * 100 + i)
            expected_data.append(sample_data)
            mux_sample = Mp4MuxSample(
                track_kind="video",
                sample_entry=Mp4SampleEntryVp08(width=1920, height=1080),
                keyframe=True,
                timescale=1000000,
                duration=33333,
                data=sample_data,
            )
            muxer.append_sample(mux_sample)

        muxer.finalize()
        muxer.close()

        # 生成した MP4 を読み取って検証
        output_buffer.seek(0)
        demuxer = Mp4FileDemuxer(output_buffer)
        read_samples = list(demuxer)
        demuxer.close()

        # データの整合性を確認
        data_valid = len(read_samples) == samples_per_thread and all(
            read_samples[i].data == expected_data[i] for i in range(samples_per_thread)
        )

        with lock:
            results.append((thread_id, data_valid))

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(process_muxer, i) for i in range(NUM_THREADS)]
        for f in futures:
            f.result()

    assert len(results) == NUM_THREADS
    for thread_id, data_valid in results:
        assert data_valid, f"Thread {thread_id}: muxed data corrupted or incomplete"


# =============================================================================
# close() の冪等性テスト
# =============================================================================


def test_demuxer_close_concurrent():
    """複数スレッドから同時に close() を呼び出し

    目的: close() が複数スレッドから同時に呼び出されても安全であることを確認
    """
    mp4_buffer = create_test_mp4_buffer()
    demuxer = Mp4FileDemuxer(mp4_buffer)
    barrier = threading.Barrier(NUM_THREADS)

    def close_demuxer(_thread_id: int):
        barrier.wait()
        for _ in range(100):
            demuxer.close()

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(close_demuxer, i) for i in range(NUM_THREADS)]
        for f in futures:
            f.result()


def test_muxer_close_concurrent():
    """複数スレッドから同時に close() を呼び出し

    目的: close() が複数スレッドから同時に呼び出されても安全であることを確認
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=1920, height=1080),
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=create_dummy_sample(0),
    )
    muxer.append_sample(mux_sample)
    barrier = threading.Barrier(NUM_THREADS)

    def close_muxer(_thread_id: int):
        barrier.wait()
        for _ in range(100):
            muxer.close()

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(close_muxer, i) for i in range(NUM_THREADS)]
        for f in futures:
            f.result()


# =============================================================================
# 同一インスタンスの並列アクセステスト
# =============================================================================


def test_demuxer_concurrent_iteration():
    """同一 Demuxer を複数スレッドから並列にイテレーション

    目的: ft_mutex によるロックが正しく機能し、全サンプルが漏れなく取得されることを確認
    検証: 取得したサンプル数、タイムスタンプの重複なし、データ内容の整合性
    """
    mp4_buffer = create_test_mp4_buffer()
    demuxer = Mp4FileDemuxer(mp4_buffer)
    collected_samples = []
    lock = threading.Lock()
    barrier = threading.Barrier(NUM_THREADS)

    def iterate_demuxer(_thread_id: int):
        barrier.wait()
        while True:
            sample = next(demuxer, None)
            if sample is None:
                break
            # サンプルのデータを即座に読み取る (遅延読み込みをここで実行)
            with lock:
                collected_samples.append((sample.timestamp, sample.data))

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(iterate_demuxer, i) for i in range(NUM_THREADS)]
        for f in futures:
            f.result()

    demuxer.close()

    # 全サンプルが取得されたことを確認
    assert len(collected_samples) == SAMPLES_PER_FILE, (
        f"Expected {SAMPLES_PER_FILE} samples, got {len(collected_samples)}"
    )

    # タイムスタンプの重複がないことを確認
    timestamps = [ts for ts, _ in collected_samples]
    assert len(set(timestamps)) == SAMPLES_PER_FILE, "Duplicate samples detected"

    # タイムスタンプでソートしてデータ内容を検証
    def get_timestamp(x):
        return x[0]

    collected_samples.sort(key=get_timestamp)
    for i, (_, data) in enumerate(collected_samples):
        expected = create_dummy_sample(i)
        assert data == expected, f"Sample {i}: data corrupted"
