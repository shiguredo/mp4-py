"""Free-Threading 環境で複数スレッドから並列に mux したときのスケーリングを測る。

各スレッドはそれぞれ独立した Muxer を持って並列に mux する。
1 スレッド (シリアル) との比 (speedup) と 8 スレッド理想比 (=8x) との差を出す。

3.14t 環境で PyO3 版が期待通りスケールするかの回帰確認用。
"""

import io
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import mp4


NUM_SAMPLES = 500
SAMPLE_SIZE = 4096
TIMESCALE = 1_000_000
SAMPLE_DURATION = 33_333
TOTAL_JOBS = 32
THREADS = 8


def make_samples() -> list[bytes]:
    return [bytes((i * 17 + j) & 0xFF for j in range(SAMPLE_SIZE)) for i in range(NUM_SAMPLES)]


def one_mux(samples: list[bytes]) -> None:
    output = io.BytesIO()
    muxer = mp4.Mp4FileMuxer(output)
    entry = mp4.Mp4SampleEntryVp08(width=1920, height=1080, bit_depth=8, chroma_subsampling=1)
    for data in samples:
        muxer.append_sample(
            mp4.Mp4MuxSample(
                track_kind="video",
                sample_entry=entry,
                keyframe=True,
                timescale=TIMESCALE,
                duration=SAMPLE_DURATION,
                data=data,
            )
        )
    muxer.finalize()


def bench_serial(samples: list[bytes], jobs: int) -> float:
    t0 = time.perf_counter()
    for _ in range(jobs):
        one_mux(samples)
    return time.perf_counter() - t0


def bench_parallel(samples: list[bytes], jobs: int, threads: int) -> float:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(one_mux, samples) for _ in range(jobs)]
        for f in futures:
            f.result()
    return time.perf_counter() - t0


def main() -> None:
    samples = make_samples()
    # sys._is_gil_enabled は Python 3.13 で追加された API のため、
    # 存在しない環境 (Python 3.12) では GIL 有効が確定しているので True とみなす
    gil_enabled = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
    print(f"Python: {sys.version.split()[0]}, GIL: {gil_enabled}")
    print(f"mp4-py version: {mp4.__version__}")
    print(
        f"jobs={TOTAL_JOBS}, samples/job={NUM_SAMPLES}, sample_size={SAMPLE_SIZE} B, "
        f"threads={THREADS}"
    )
    print()

    for _ in range(2):
        one_mux(samples)

    serial_runs = [bench_serial(samples, TOTAL_JOBS) for _ in range(3)]
    parallel_runs = [bench_parallel(samples, TOTAL_JOBS, THREADS) for _ in range(3)]
    s = statistics.median(serial_runs)
    p = statistics.median(parallel_runs)
    speedup = s / p if p > 0 else float("inf")
    print(f"serial   ({TOTAL_JOBS} jobs, 1 thread):    {s * 1000:8.1f} ms")
    print(
        f"parallel ({TOTAL_JOBS} jobs, {THREADS} threads): {p * 1000:8.1f} ms "
        f"(speedup {speedup:.2f}x / ideal {THREADS}x)"
    )
    print(f"parallel efficiency: {speedup / THREADS * 100:.0f}%")


if __name__ == "__main__":
    main()
