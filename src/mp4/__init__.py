"""Python bindings for mp4-rust"""

from importlib.metadata import version

from mp4._types import (
    Mp4TrackKind,
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntry,
)
from mp4._demux import (
    Mp4TrackInfo,
    Mp4DemuxSample,
    Mp4FileDemuxer,
)
from mp4._mux import (
    Mp4MuxSample,
    Mp4FileMuxer,
    Mp4FileMuxerOptions,
)

__version__ = version("mp4-py")


def native_version() -> str:
    """mp4-rust のバージョンを返す"""
    from mp4._c_api import _get_lib

    return _get_lib().mp4_library_version().decode("utf-8")


__all__ = [
    "__version__",
    "native_version",
    "Mp4TrackKind",
    "Mp4TrackInfo",
    "Mp4SampleEntryAvc1",
    "Mp4SampleEntryHev1",
    "Mp4SampleEntryVp08",
    "Mp4SampleEntryVp09",
    "Mp4SampleEntryAv01",
    "Mp4SampleEntryOpus",
    "Mp4SampleEntryMp4a",
    "Mp4SampleEntry",
    "Mp4DemuxSample",
    "Mp4MuxSample",
    "Mp4FileDemuxer",
    "Mp4FileMuxer",
    "Mp4FileMuxerOptions",
]
