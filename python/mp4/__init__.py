"""Python bindings for shiguredo/mp4-rs (PyO3)"""

from importlib.metadata import version
from typing import Literal, Union

from .mp4_ext import (
    Mp4DemuxSample,
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4FileMuxerOptions,
    Mp4MuxSample,
    Mp4SampleEntryAv01,
    Mp4SampleEntryAvc1,
    Mp4SampleEntryFlac,
    Mp4SampleEntryHev1,
    Mp4SampleEntryHvc1,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryOpus,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4TrackInfo,
    estimate_maximum_moov_box_size,
    library_version,
)

__version__ = version("mp4-py")

# 型定義
Mp4TrackKind = Literal["audio", "video"]
"""MP4 ファイル内のトラックの種類を表す型"""

Mp4SampleEntry = Union[
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryHvc1,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
]
"""MP4 サンプルエントリー"""


def native_version() -> str:
    """バインド対象の shiguredo_mp4 (Rust クレート) のバージョンを返す"""
    return library_version()


__all__ = [
    "__version__",
    "native_version",
    "estimate_maximum_moov_box_size",
    "Mp4TrackKind",
    "Mp4TrackInfo",
    "Mp4SampleEntryAvc1",
    "Mp4SampleEntryHev1",
    "Mp4SampleEntryHvc1",
    "Mp4SampleEntryVp08",
    "Mp4SampleEntryVp09",
    "Mp4SampleEntryAv01",
    "Mp4SampleEntryOpus",
    "Mp4SampleEntryMp4a",
    "Mp4SampleEntryFlac",
    "Mp4SampleEntry",
    "Mp4DemuxSample",
    "Mp4MuxSample",
    "Mp4FileDemuxer",
    "Mp4FileMuxer",
    "Mp4FileMuxerOptions",
]
