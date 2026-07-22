"""mp4-py の mux/demux ラウンドトリップの実行時間を計測する。

サンプルサイズ・サンプル数を変えて median 実行時間を見る。
性能回帰チェックや Python バージョン間比較の目安に使う。
"""

import io
import statistics
import sys
import time

import mp4


NUM_SAMPLES = 500
SAMPLE_SIZE = 4096
TIMESCALE = 1_000_000
SAMPLE_DURATION = 33_333
WARMUP = 3
ITERATIONS = 10


def make_samples() -> list[bytes]:
    return [bytes((i * 17 + j) & 0xFF for j in range(SAMPLE_SIZE)) for i in range(NUM_SAMPLES)]


def run_once(samples: list[bytes]) -> tuple[int, int]:
    """mux → demux 1 セットの実行時間 (mux ns, demux ns)"""
    output = io.BytesIO()
    muxer = mp4.Mp4FileMuxer(output)
    entry = mp4.Mp4SampleEntryVp08(width=1920, height=1080, bit_depth=8, chroma_subsampling=1)
    t0 = time.perf_counter_ns()
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
    t1 = time.perf_counter_ns()

    output.seek(0)
    demuxer = mp4.Mp4FileDemuxer(output)
    t2 = time.perf_counter_ns()
    for sample in demuxer:
        _ = sample.data
    t3 = time.perf_counter_ns()
    return (t1 - t0, t3 - t2)


def fmt_ns(v: float) -> str:
    return f"{v / 1000:9.1f} us"


def main() -> None:
    samples = make_samples()
    total_bytes = NUM_SAMPLES * SAMPLE_SIZE
    print(f"Python: {sys.version.split()[0]}, GIL: {sys._is_gil_enabled()}")
    print(f"mp4-py version: {mp4.__version__} (native: {mp4.native_version()})")
    print(
        f"samples={NUM_SAMPLES}, sample_size={SAMPLE_SIZE} bytes, "
        f"total={total_bytes / 1024 / 1024:.1f} MB, iterations={ITERATIONS} (warmup {WARMUP})"
    )
    print()

    for _ in range(WARMUP):
        run_once(samples)

    runs = [run_once(samples) for _ in range(ITERATIONS)]
    mux_ns = [r[0] for r in runs]
    demux_ns = [r[1] for r in runs]

    print(
        f"mux   mean={fmt_ns(statistics.mean(mux_ns))} "
        f"median={fmt_ns(statistics.median(mux_ns))} "
        f"min={fmt_ns(min(mux_ns))}"
    )
    print(
        f"demux mean={fmt_ns(statistics.mean(demux_ns))} "
        f"median={fmt_ns(statistics.median(demux_ns))} "
        f"min={fmt_ns(min(demux_ns))}"
    )


if __name__ == "__main__":
    main()
