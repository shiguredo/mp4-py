"""PyO3 版バインディングの最小限のラウンドトリップ検証"""

import io

from mp4_pyo3 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
    estimate_maximum_moov_box_size,
    library_version,
)


NUM_VIDEO_SAMPLES = 5
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
SAMPLE_DURATION = 33333
TIMESCALE = 1000000


def make_sample(index: int, size: int = 1024) -> bytes:
    buf = bytearray(size)
    for j in range(size):
        buf[j] = (index * 17 + j) & 0xFF
    return bytes(buf)


def test_library_version_looks_like_semver() -> None:
    v = library_version()
    parts = v.split(".")
    assert len(parts) >= 2, f"予期しないバージョン形式: {v!r}"


def test_estimate_maximum_moov_box_size_increases_with_samples() -> None:
    small = estimate_maximum_moov_box_size(0, 10)
    large = estimate_maximum_moov_box_size(0, 1000)
    assert large > small


def test_mux_demux_roundtrip_vp08() -> None:
    """mux → demux したときにサンプル数とデータが一致することを確認する"""
    output = io.BytesIO()
    muxer = Mp4FileMuxer(output)

    originals: list[bytes] = []
    for i in range(NUM_VIDEO_SAMPLES):
        data = make_sample(i)
        originals.append(data)

        entry = Mp4SampleEntryVp08(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            bit_depth=8,
            chroma_subsampling=1,
        )
        muxer.append_sample(
            Mp4MuxSample(
                track_kind="video",
                sample_entry=entry,
                keyframe=True,
                timescale=TIMESCALE,
                duration=SAMPLE_DURATION,
                data=data,
            )
        )

    muxer.finalize()

    output.seek(0)
    demuxer = Mp4FileDemuxer(output.getvalue())
    tracks = demuxer.tracks
    assert len(tracks) == 1
    assert tracks[0].kind == "video"

    demuxed = list(demuxer)
    assert len(demuxed) == NUM_VIDEO_SAMPLES, f"サンプル数不一致: {len(demuxed)}"
    for i, (orig, got) in enumerate(zip(originals, demuxed)):
        assert got.data == orig, f"サンプル {i} のデータが一致しない"
        assert got.keyframe is True
