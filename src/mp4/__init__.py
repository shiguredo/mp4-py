"""Python bindings for mp4-rust"""

from importlib.metadata import version
from typing import Literal, Union

from .mp4_ext import (
    # ユーティリティ関数
    library_version,
    estimate_maximum_moov_box_size,
    # サンプルエントリークラス
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
    # トラック情報
    Mp4TrackInfo,
    # Demuxer 関連
    Mp4DemuxSample,
    Mp4FileDemuxer,
    # Muxer 関連
    Mp4MuxSample,
    Mp4FileMuxer,
    Mp4FileMuxerOptions,
)

__version__ = version("mp4-py")

# 型定義
Mp4TrackKind = Literal["audio", "video"]
"""MP4 ファイル内のトラックの種類を表す型"""

Mp4SampleEntry = Union[
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
]
"""MP4 サンプルエントリー"""


def native_version() -> str:
    """mp4-rust のバージョンを返す"""
    return library_version()


__all__ = [
    "__version__",
    "native_version",
    "estimate_maximum_moov_box_size",
    "Mp4TrackKind",
    "Mp4TrackInfo",
    "Mp4SampleEntryAvc1",
    "Mp4SampleEntryHev1",
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
