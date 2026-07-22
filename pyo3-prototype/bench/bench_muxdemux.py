"""nanobind (mp4) と PyO3 (mp4_pyo3) の mux/demux ラウンドトリップ性能を計測する。

同一のサンプル数・サンプルサイズ・コーデック (VP08) で両実装を走らせて
平均実行時間を比較する。
"""

import io
import statistics
import time

import mp4 as nb  # nanobind 版
import mp4_pyo3 as p3  # PyO3 版


# --- パラメータ ---
NUM_SAMPLES = 500
SAMPLE_SIZE = 4096  # 4 KB / sample
TIMESCALE = 1_000_000
SAMPLE_DURATION = 33_333  # 30fps
WARMUP = 3
ITERATIONS = 10


def make_samples() -> list[bytes]:
    """テスト用のサンプルデータを生成 (毎回同じ内容)"""
    return [bytes((i * 17 + j) & 0xFF for j in range(SAMPLE_SIZE)) for i in range(NUM_SAMPLES)]


def run_nanobind(samples: list[bytes]) -> tuple[int, int]:
    """nanobind 版で mux → demux。(mux ns, demux ns) を返す"""
    # ---- mux ----
    output = io.BytesIO()
    muxer = nb.Mp4FileMuxer(output)
    entry = nb.Mp4SampleEntryVp08(width=1920, height=1080, bit_depth=8, chroma_subsampling=1)
    t0 = time.perf_counter_ns()
    for data in samples:
        muxer.append_sample(
            nb.Mp4MuxSample(
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

    # ---- demux ----
    output.seek(0)
    demuxer = nb.Mp4FileDemuxer(output)
    t2 = time.perf_counter_ns()
    for sample in demuxer:
        _ = sample.data  # 遅延読み込みも計測に含める
    t3 = time.perf_counter_ns()

    return (t1 - t0, t3 - t2)


def run_pyo3(samples: list[bytes]) -> tuple[int, int]:
    """PyO3 版で mux → demux"""
    output = io.BytesIO()
    muxer = p3.Mp4FileMuxer(output)
    entry = p3.Mp4SampleEntryVp08(width=1920, height=1080, bit_depth=8, chroma_subsampling=1)
    t0 = time.perf_counter_ns()
    for data in samples:
        muxer.append_sample(
            p3.Mp4MuxSample(
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
    demuxer = p3.Mp4FileDemuxer(output)
    t2 = time.perf_counter_ns()
    for sample in demuxer:
        _ = sample.data
    t3 = time.perf_counter_ns()

    return (t1 - t0, t3 - t2)


def summarize(name: str, runs: list[tuple[int, int]]) -> None:
    mux_ns = [r[0] for r in runs]
    demux_ns = [r[1] for r in runs]

    def fmt_ns(v: float) -> str:
        us = v / 1000
        return f"{us:9.1f} us"

    print(f"{name}")
    print(
        f"  mux   mean={fmt_ns(statistics.mean(mux_ns))} "
        f"median={fmt_ns(statistics.median(mux_ns))} "
        f"min={fmt_ns(min(mux_ns))}"
    )
    print(
        f"  demux mean={fmt_ns(statistics.mean(demux_ns))} "
        f"median={fmt_ns(statistics.median(demux_ns))} "
        f"min={fmt_ns(min(demux_ns))}"
    )


def main() -> None:
    samples = make_samples()
    total_bytes = NUM_SAMPLES * SAMPLE_SIZE
    print(f"nanobind version: {nb.native_version()}")
    print(f"PyO3     version: {p3.library_version()}")
    print(
        f"samples={NUM_SAMPLES}, sample_size={SAMPLE_SIZE} bytes, "
        f"total={total_bytes / 1024 / 1024:.1f} MB, iterations={ITERATIONS} (warmup {WARMUP})"
    )
    print()

    # ---- warmup ----
    for _ in range(WARMUP):
        run_nanobind(samples)
        run_pyo3(samples)

    # ---- measure ----
    nb_runs = [run_nanobind(samples) for _ in range(ITERATIONS)]
    p3_runs = [run_pyo3(samples) for _ in range(ITERATIONS)]

    summarize("nanobind (mp4)", nb_runs)
    print()
    summarize("PyO3     (mp4_pyo3)", p3_runs)
    print()

    nb_mux = statistics.median([r[0] for r in nb_runs])
    p3_mux = statistics.median([r[0] for r in p3_runs])
    nb_dmx = statistics.median([r[1] for r in nb_runs])
    p3_dmx = statistics.median([r[1] for r in p3_runs])
    print("比率 (PyO3 / nanobind, 小さいほど PyO3 が速い):")
    print(f"  mux   {p3_mux / nb_mux:.3f}x")
    print(f"  demux {p3_dmx / nb_dmx:.3f}x")


if __name__ == "__main__":
    main()
