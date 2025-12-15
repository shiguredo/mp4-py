"""Free-Threading (GIL フリー) 環境でのスレッドセーフティテスト

このテストは複数スレッドから同時にオブジェクトを操作し、
データ競合やクラッシュが発生しないことを確認する。

注意: GIL あり環境 (Python 3.12 など) では GIL がスレッド間の
同時実行を制限するため、並列実行テストにはならない。

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
    Mp4DemuxSample,
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
    Mp4TrackInfo,
)


def is_gil_enabled() -> bool:
    """GIL が有効かどうかを確認"""
    # Python 3.13+ で利用可能
    if hasattr(sys, "_is_gil_enabled"):
        return sys._is_gil_enabled()
    # それ以前のバージョンは常に GIL 有効
    return True


# Free-Threading 環境でない場合は全テストをスキップ
pytestmark = pytest.mark.skipif(
    is_gil_enabled(),
    reason="Free-Threading テストは GIL 無効の Python (例: Python 3.13t, 3.14t) が必要です",
)


# テスト用定数
NUM_THREADS = 8
NUM_ITERATIONS = 100
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
SAMPLE_DURATION = 33333
TIMESCALE = 1000000


def create_dummy_sample(index: int, size: int = 1024) -> bytes:
    """テスト用のダミーサンプルデータを生成"""
    data = bytearray(size)
    for j in range(size):
        data[j] = (index * 17 + j) & 0xFF
    return bytes(data)


def create_test_mp4_buffer() -> io.BytesIO:
    """テスト用の MP4 データを生成"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    for i in range(10):
        sample_data = create_dummy_sample(i)
        sample_entry = Mp4SampleEntryVp08(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
        )
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()
    output_buffer.seek(0)
    return output_buffer


class TestDemuxerThreadSafety:
    """Demuxer のスレッドセーフティテスト"""

    def test_demuxer_tracks_concurrent_access(self):
        """複数スレッドから同時に tracks プロパティにアクセス"""
        mp4_buffer = create_test_mp4_buffer()
        demuxer = Mp4FileDemuxer(mp4_buffer)

        barrier = threading.Barrier(NUM_THREADS)
        results = []
        errors = []

        def access_tracks(thread_id: int):
            try:
                barrier.wait()
                for _ in range(NUM_ITERATIONS):
                    tracks = demuxer.tracks
                    results.append((thread_id, len(tracks)))
            except Exception as e:
                errors.append((thread_id, e))

        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            futures = [executor.submit(access_tracks, i) for i in range(NUM_THREADS)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == NUM_THREADS * NUM_ITERATIONS

        # 全ての結果が同じトラック数を返すことを確認
        track_counts = set(count for _, count in results)
        assert len(track_counts) == 1, f"Inconsistent track counts: {track_counts}"

    def test_demuxer_close_concurrent(self):
        """複数スレッドから同時に close() を呼び出し"""
        mp4_buffer = create_test_mp4_buffer()
        demuxer = Mp4FileDemuxer(mp4_buffer)

        barrier = threading.Barrier(NUM_THREADS)
        errors = []

        def close_demuxer(thread_id: int):
            try:
                barrier.wait()
                # 複数回 close() を呼んでも安全であることを確認
                for _ in range(NUM_ITERATIONS):
                    demuxer.close()
            except Exception as e:
                errors.append((thread_id, e))

        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            futures = [executor.submit(close_demuxer, i) for i in range(NUM_THREADS)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors occurred: {errors}"


class TestDemuxSampleThreadSafety:
    """DemuxSample のスレッドセーフティテスト"""

    def test_demux_sample_data_concurrent_access(self):
        """複数スレッドから同時に data プロパティにアクセス (遅延読み込み)"""
        # サンプルを作成
        track = Mp4TrackInfo(
            track_id=1,
            kind="video",
            duration=5000000,
            timescale=1000000,
        )
        sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)
        test_data = b"test_data_for_concurrent_access"

        demux_sample = Mp4DemuxSample(
            track=track,
            sample_entry=sample_entry,
            keyframe=True,
            timestamp=500000,
            duration=33333,
            data_offset=0,
            data_size=len(test_data),
            input_stream=io.BytesIO(test_data),
        )

        barrier = threading.Barrier(NUM_THREADS)
        results = []
        errors = []

        def access_data(thread_id: int):
            try:
                barrier.wait()
                for _ in range(NUM_ITERATIONS):
                    # data プロパティは遅延読み込みでキャッシュされる
                    data = demux_sample.data
                    results.append((thread_id, data))
            except Exception as e:
                errors.append((thread_id, e))

        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            futures = [executor.submit(access_data, i) for i in range(NUM_THREADS)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == NUM_THREADS * NUM_ITERATIONS

        # 全ての結果が同じデータを返すことを確認
        data_set = set(data for _, data in results)
        assert len(data_set) == 1, f"Inconsistent data: {data_set}"
        assert test_data in data_set


class TestMuxerThreadSafety:
    """Muxer のスレッドセーフティテスト

    注意: Muxer は同一インスタンスへの同時書き込みはサポートされない設計だが、
    close() の同時呼び出しは安全であるべき。
    """

    def test_muxer_close_concurrent(self):
        """複数スレッドから同時に close() を呼び出し"""
        output_buffer = io.BytesIO()
        muxer = Mp4FileMuxer(output_buffer)

        # 1 つサンプルを追加
        sample_data = create_dummy_sample(0)
        sample_entry = Mp4SampleEntryVp08(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
        )
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

        barrier = threading.Barrier(NUM_THREADS)
        errors = []

        def close_muxer(thread_id: int):
            try:
                barrier.wait()
                # 複数回 close() を呼んでも安全であることを確認
                for _ in range(NUM_ITERATIONS):
                    muxer.close()
            except Exception as e:
                errors.append((thread_id, e))

        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            futures = [executor.submit(close_muxer, i) for i in range(NUM_THREADS)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors occurred: {errors}"


class TestMultipleInstancesThreadSafety:
    """複数インスタンスの並列使用テスト"""

    def test_multiple_demuxers_parallel(self):
        """複数の Demuxer インスタンスを並列で使用"""
        errors = []
        results = []

        def process_demuxer(thread_id: int):
            try:
                # 各スレッドが独自の MP4 バッファと Demuxer を持つ
                mp4_buffer = create_test_mp4_buffer()
                demuxer = Mp4FileDemuxer(mp4_buffer)

                tracks = demuxer.tracks
                samples = list(demuxer)

                results.append((thread_id, len(tracks), len(samples)))
                demuxer.close()
            except Exception as e:
                errors.append((thread_id, e))

        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            futures = [executor.submit(process_demuxer, i) for i in range(NUM_THREADS)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == NUM_THREADS

        # 全てのスレッドが同じ結果を得ることを確認
        for thread_id, track_count, sample_count in results:
            assert track_count == 1, f"Thread {thread_id}: unexpected track count {track_count}"
            assert sample_count == 10, f"Thread {thread_id}: unexpected sample count {sample_count}"

    def test_multiple_muxers_parallel(self):
        """複数の Muxer インスタンスを並列で使用"""
        errors = []
        results = []

        def process_muxer(thread_id: int):
            try:
                output_buffer = io.BytesIO()
                muxer = Mp4FileMuxer(output_buffer)

                for i in range(5):
                    sample_data = create_dummy_sample(thread_id * 100 + i)
                    sample_entry = Mp4SampleEntryVp08(
                        width=VIDEO_WIDTH,
                        height=VIDEO_HEIGHT,
                    )
                    mux_sample = Mp4MuxSample(
                        track_kind="video",
                        sample_entry=sample_entry,
                        keyframe=True,
                        timescale=TIMESCALE,
                        duration=SAMPLE_DURATION,
                        data=sample_data,
                    )
                    muxer.append_sample(mux_sample)

                muxer.finalize()
                muxer.close()

                results.append((thread_id, len(output_buffer.getvalue())))
            except Exception as e:
                errors.append((thread_id, e))

        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            futures = [executor.submit(process_muxer, i) for i in range(NUM_THREADS)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == NUM_THREADS

        # 全てのスレッドが有効な出力を生成したことを確認
        for thread_id, size in results:
            assert size > 0, f"Thread {thread_id}: empty output"
