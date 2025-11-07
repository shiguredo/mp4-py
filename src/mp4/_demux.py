import ctypes
import io
from pathlib import Path
from typing import Iterator, Optional, List

from mp4._c_api import _get_lib, _RawMp4DemuxSample, _RawMp4DemuxTrackInfo, _RawMp4Error
from mp4._types import (
    Mp4TrackKind,
    _from_raw_mp4_track_kind,
    _from_raw_mp4_sample_entry,
    Mp4SampleEntry,
)


class Mp4TrackInfo:
    """トラック情報"""

    def __init__(self, track_id: int, kind: Mp4TrackKind, duration: int, timescale: int):
        self.track_id = track_id
        self.kind = kind
        self.duration = duration
        self.timescale = timescale

    @property
    def duration_seconds(self) -> float:
        """秒単位のトラック尺"""
        return self.duration / self.timescale

    def __repr__(self) -> str:
        return (
            f"Mp4TrackInfo(track_id={self.track_id}, kind={self.kind}, "
            f"duration={self.duration}, timescale={self.timescale})"
        )


class Mp4DemuxSample:
    """MP ファイルから取り出されたメディアサンプル"""

    def __init__(
        self,
        track: Mp4TrackInfo,
        sample_entry: Optional[Mp4SampleEntry],
        keyframe: bool,
        timestamp: int,
        duration: int,
        data_offset: int,
        data_size: int,
        input_stream: io.IOBase,
    ):
        self.track = track
        self.sample_entry = sample_entry
        self.keyframe = keyframe
        self.timestamp = timestamp
        self.duration = duration
        self._data_offset = data_offset
        self._data_size = data_size
        self._input_stream = input_stream
        self._data_cache: Optional[bytes] = None

    @property
    def data(self) -> bytes:
        """サンプルデータ"""
        if self._data_cache is None:
            self._input_stream.seek(self._data_offset)
            self._data_cache = self._input_stream.read(self._data_size)
            if len(self._data_cache) != self._data_size:
                raise RuntimeError(
                    f"Failed to read sample data: expected {self._data_size} bytes, "
                    f"got {len(self._data_cache)} bytes"
                )
        return self._data_cache

    @property
    def timestamp_seconds(self) -> float:
        """秒単位のタイムスタンプ"""

        return self.timestamp / self.track.timescale

    @property
    def duration_seconds(self) -> float:
        """秒単位のサンプル尺"""
        return self.duration / self.track.timescale

    def __repr__(self) -> str:
        return (
            f"Mp4DemuxSample(track_id={self.track.track_id}, keyframe={self.keyframe}, "
            f"timestamp={self.timestamp}, data_size={self._data_size})"
        )


class Mp4FileDemuxer:
    """MP4 ファイルをデマルチプレックスするためのクラス

    ファイルパスまたはバイナリストリームから MP4 ファイルを読み込み、
    トラック情報の取得とメディアサンプルの走査を行うための高レベルインタフェースを提供する

    # 使用例

    ```python
    from mp4 import Mp4FileDemuxer

    # ファイルパスから demuxer を作成
    with Mp4FileDemuxer("input.mp4") as demuxer:
        # トラック情報を取得
        for track in demuxer.tracks:
            print(f"Track {track.track_id}: {track.kind}, duration={track.duration_seconds}s")

        # サンプルを走査して処理
        for sample in demuxer:
            print(f"Sample: {sample.timestamp_seconds}s, keyframe={sample.keyframe}")

    # バイナリストリームから demuxer を作成
    with open("input.mp4", "rb") as fp:
        demuxer = Mp4FileDemuxer(fp)
        for sample in demuxer:
            # サンプルを処理...
            pass
    ```
    """

    def __init__(self, source: Path | str | io.IOBase) -> None:
        self._lib = _get_lib()
        self._raw_demuxer = None
        self._input_stream: Optional[io.IOBase] = None
        self._should_close_stream = False

        # ソースの種別に応じて入力ストリームを確定
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"MP4 file not found: {path}")
            self._input_stream = open(path, "rb")
            self._should_close_stream = True
        elif isinstance(source, io.IOBase):
            self._input_stream = source
            self._should_close_stream = False
        else:
            raise TypeError(
                f"source must be a file path (str or Path) or BinaryIO, got {type(source).__name__}"
            )

        # C API の demuxer を初期化
        self._raw_demuxer = self._lib.mp4_file_demuxer_new()
        if not self._raw_demuxer:
            raise RuntimeError("Failed to create mp4 demuxer")

    def __enter__(self) -> "Mp4FileDemuxer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        """Mp4FileDemuxer をクローズしてリソースを解放する"""
        if self._raw_demuxer is not None:
            self._lib.mp4_file_demuxer_free(self._raw_demuxer)
            self._raw_demuxer = None

        if self._input_stream is not None and self._should_close_stream:
            self._input_stream.close()
            self._input_stream = None

    def _check_error(self, error_code: int) -> None:
        if error_code == _RawMp4Error.OK:
            return

        msg = self._lib.mp4_file_demuxer_get_last_error(self._raw_demuxer).decode()

        if error_code == _RawMp4Error.NO_MORE_SAMPLES:
            raise StopIteration()
        elif error_code == _RawMp4Error.NULL_POINTER:
            raise ValueError(f"Null pointer error: {msg}")
        elif error_code == _RawMp4Error.INPUT_REQUIRED:
            raise RuntimeError(f"Input required: {msg}")
        else:
            raise RuntimeError(f"MP4 error ({error_code}): {msg}")

    def _feed_required_input(self) -> None:
        while True:
            required_pos = ctypes.c_uint64()
            required_size = ctypes.c_int32()

            error = self._lib.mp4_file_demuxer_get_required_input(
                self._raw_demuxer, ctypes.byref(required_pos), ctypes.byref(required_size)
            )
            self._check_error(error)

            # ストリームから必要なデータを読み込む
            pos = required_pos.value
            size = required_size.value

            if size == 0:
                # 必要なデータは全て読んだ
                break

            if size == -1:
                # ファイル末尾までのデータを読む
                self._input_stream.seek(pos)
                data = self._input_stream.read()
            else:
                # 指定サイズ分読む
                self._input_stream.seek(pos)
                data = self._input_stream.read(size)

            buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            error = self._lib.mp4_file_demuxer_handle_input(
                self._raw_demuxer, pos, buffer, len(data)
            )
            self._check_error(error)

    @property
    def tracks(self) -> List[Mp4TrackInfo]:
        """MP4 ファイルに含まれるすべてのメディアトラック情報を取得する"""
        if self._raw_demuxer is None:
            raise RuntimeError("Demuxer is closed")

        while True:
            tracks_ptr = ctypes.POINTER(_RawMp4DemuxTrackInfo)()
            track_count = ctypes.c_uint32()

            error = self._lib.mp4_file_demuxer_get_tracks(
                self._raw_demuxer, ctypes.byref(tracks_ptr), ctypes.byref(track_count)
            )
            if error == _RawMp4Error.INPUT_REQUIRED:
                self._feed_required_input()
                continue
            self._check_error(error)

            track_info_list = []
            for i in range(track_count.value):
                track = tracks_ptr[i]
                track_info = Mp4TrackInfo(
                    track_id=track.track_id,
                    kind=_from_raw_mp4_track_kind(track.kind),
                    duration=track.duration,
                    timescale=track.timescale,
                )
                track_info_list.append(track_info)

            return track_info_list

    def __iter__(self) -> Iterator[Mp4DemuxSample]:
        if self._raw_demuxer is None:
            raise RuntimeError("Demuxer is closed")

        return self

    def __next__(self) -> Mp4DemuxSample:
        if self._raw_demuxer is None:
            raise RuntimeError("Demuxer is closed")

        while True:
            sample = _RawMp4DemuxSample()
            error = self._lib.mp4_file_demuxer_next_sample(self._raw_demuxer, ctypes.byref(sample))
            if error == _RawMp4Error.INPUT_REQUIRED:
                self._feed_required_input()
                continue
            self._check_error(error)

            track_info = Mp4TrackInfo(
                track_id=sample.track.contents.track_id,
                kind=_from_raw_mp4_track_kind(sample.track.contents.kind),
                duration=sample.track.contents.duration,
                timescale=sample.track.contents.timescale,
            )

            # sample_entry を変換
            sample_entry = None
            if sample.sample_entry:  # 前のサンプルと値が同じ場合は NULL (False 扱い) になる
                sample_entry = _from_raw_mp4_sample_entry(sample.sample_entry.contents)

            return Mp4DemuxSample(
                track=track_info,
                sample_entry=sample_entry,
                keyframe=sample.keyframe,
                timestamp=sample.timestamp,
                duration=sample.duration,
                data_offset=sample.data_offset,
                data_size=sample.data_size,
                input_stream=self._input_stream,
            )
