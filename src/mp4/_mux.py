import ctypes
from pathlib import Path
from typing import Optional, List
import io

from mp4._c_api import _get_lib, _RawMp4MuxSample, _RawMp4SampleEntry, _RawMp4Error
from mp4._types import Mp4TrackKind, _to_raw_mp4_track_kind, _to_raw_mp4_sample_entry


class Mp4FileMuxerOptions:
    """MP4 ファイルマルチプレックス時のオプション設定

    # 使用例

    ```python
    from mp4 import Mp4FileMuxerOptions, Mp4FileMuxer

    # faststart オプション付きで設定
    options = Mp4FileMuxerOptions(reserved_moov_box_size=8192)

    with open("output.mp4", "wb") as fp:
        with Mp4FileMuxer(fp, options) as muxer:
            # マルチプレックス処理...\n            pass
    ```
    """

    def __init__(self, reserved_moov_box_size: int = 0):
        """オプションを初期化

        Args:
            reserved_moov_box_size: faststart 用に事前確保する moov ボックスのサイズ
                デフォルト値 0 は faststart 無効を意味する
        """
        self.reserved_moov_box_size = reserved_moov_box_size

    @staticmethod
    def estimate_maximum_moov_box_size(audio_sample_count: int, video_sample_count: int) -> int:
        """moov ボックスの最大サイズを見積もる

        Args:
            audio_sample_count: 音声トラック内の予想サンプル数
            video_sample_count: 映像トラック内の予想サンプル数

        Returns:
            moov ボックスに必要な最大バイト数

        # 使用例

        ```python
        from mp4 import Mp4FileMuxerOptions

        # 音声 1000 サンプル、映像 3000 フレームの場合
        required_size = Mp4FileMuxerOptions.estimate_maximum_moov_box_size(1000, 3000)
        options = Mp4FileMuxerOptions(reserved_moov_box_size=required_size)
        ```
        """
        lib = _get_lib()
        return lib.mp4_estimate_maximum_moov_box_size(audio_sample_count, video_sample_count)


class Mp4MuxSample:
    """MP ファイルに追加するメディアサンプルを表すクラス"""

    def __init__(
        self,
        track_kind: Mp4TrackKind,
        sample_entry: Optional["Mp4SampleEntry"],
        keyframe: bool,
        timescale: int,
        duration: int,
        data: bytes,
    ):
        """サンプルを初期化

        Args:
            track_kind: サンプルが属するトラックの種別（\"audio\" または \"video\"）
            sample_entry: サンプルの詳細情報（コーデック設定など）
                最初のサンプルでは必須。以降のサンプルでは前のサンプルと同じ
                コーデック設定の場合は None を指定可能
            keyframe: キーフレームであるかどうか
            timescale: サンプルのタイムスケール（時間単位）
            duration: サンプルの尺（タイムスケール単位）
            data: サンプルデータ（バイト列）
        """
        self.track_kind = track_kind
        self.sample_entry = sample_entry
        self.keyframe = keyframe
        self.timescale = timescale
        self.duration = duration
        self.data = data

    def __repr__(self) -> str:
        return (
            f"Mp4MuxSample(track_kind={self.track_kind}, keyframe={self.keyframe}, "
            f"timescale={self.timescale}, duration={self.duration}, data_size={len(self.data)})"
        )


class Mp4FileMuxer:
    """MP4 ファイルをマルチプレックスするクラス

    ファイルパスまたはバイナリストリームに対して MP4 ファイルを構築するための
    高レベルインタフェースを提供する

    # 使用例

    ```python
    from mp4 import Mp4FileMuxer, Mp4FileMuxerOptions, Mp4MuxSample, Mp4SampleEntryAvc1

    # オプション設定
    options = Mp4FileMuxerOptions(reserved_moov_box_size=8192)

    # ファイルにマルチプレックス
    with Mp4FileMuxer("output.mp4", options) as muxer:
        # H.264 ビデオサンプルエントリーを作成
        video_entry = Mp4SampleEntryAvc1(
            width=1920,
            height=1080,
            avc_profile_indication=66,  # Baseline
            profile_compatibility=0xc0,
            avc_level_indication=31,    # Level 3.1
            sps_data=[b"..."],          # SPS NALU
            pps_data=[b"..."],          # PPS NALU
        )

        # サンプルを追加
        with open("video.h264", "rb") as video_fp:
            video_data = video_fp.read()

        sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=video_entry,
            keyframe=True,
            timescale=30,
            duration=1,
            data=video_data,
        )
        muxer.append_sample(sample)

        # 全てのサンプルの追加が終わったら finalize() を呼んでファイルを完成させる
        muxer.finalize()

    # バイナリストリームにマルチプレックス
    with open("output.mp4", "wb") as fp:
        muxer = Mp4FileMuxer(fp, options)
        # マルチプレックス処理...
        muxer.finalize()
    ```
    """

    def __init__(
        self,
        destination: Path | str | io.IOBase,
        options: Optional[Mp4FileMuxerOptions] = None,
    ) -> None:
        self._lib = _get_lib()
        self._raw_muxer = None
        self._output_stream: Optional[io.IOBase] = None
        self._should_close_stream = False
        self._finalized = False

        # ソースの種別に応じて出力ストリームを確定
        if isinstance(destination, (str, Path)):
            path = Path(destination)
            self._output_stream = open(path, "wb")
            self._should_close_stream = True
        elif isinstance(destination, io.IOBase):
            self._output_stream = destination
            self._should_close_stream = False
        else:
            raise TypeError(
                f"destination must be a file path (str or Path) or BinaryIO, got {type(destination).__name__}"
            )

        # C API の muxer を作成
        self._raw_muxer = self._lib.mp4_file_muxer_new()
        if not self._raw_muxer:
            raise RuntimeError("Failed to create mp4 muxer")

        # デフォルトオプション
        if options is None:
            options = Mp4FileMuxerOptions()

        # オプションをセット
        if options.reserved_moov_box_size > 0:
            error = self._lib.mp4_file_muxer_set_reserved_moov_box_size(
                self._raw_muxer, options.reserved_moov_box_size
            )
            self._check_error(error)

        # マルチプレックス処理を初期化
        error = self._lib.mp4_file_muxer_initialize(self._raw_muxer)
        self._check_error(error)

        # 初期出力データをストリームに書き込む
        self._flush_output()

    def __enter__(self) -> "Mp4FileMuxer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        if self._raw_muxer is not None:
            if not self._finalized:
                self.finalize()
            self._lib.mp4_file_muxer_free(self._raw_muxer)
            self._raw_muxer = None

        if self._output_stream is not None and self._should_close_stream:
            self._output_stream.close()
            self._output_stream = None

    def _check_error(self, error_code: int) -> None:
        if error_code == _RawMp4Error.OK:
            return

        msg = self._lib.mp4_file_muxer_get_last_error(self._raw_muxer).decode()

        if error_code == _RawMp4Error.NULL_POINTER:
            raise ValueError(f"Null pointer error: {msg}")
        elif error_code == _RawMp4Error.INVALID_STATE:
            raise RuntimeError(f"Invalid state: {msg}")
        elif error_code == _RawMp4Error.OUTPUT_REQUIRED:
            raise RuntimeError(f"Output required: {msg}")
        elif error_code == _RawMp4Error.INVALID_INPUT:
            raise ValueError(f"Invalid input: {msg}")
        else:
            raise RuntimeError(f"MP4 error ({error_code}): {msg}")

    def _flush_output(self) -> None:
        """内部バッファから出力データをストリームに書き込む"""
        while True:
            output_offset = ctypes.c_uint64()
            output_size = ctypes.c_uint32()
            output_data = ctypes.POINTER(ctypes.c_uint8)()

            error = self._lib.mp4_file_muxer_next_output(
                self._raw_muxer,
                ctypes.byref(output_offset),
                ctypes.byref(output_size),
                ctypes.byref(output_data),
            )
            self._check_error(error)

            if output_size.value == 0:
                break

            # バッファから実際のバイト列を取得
            data = bytes(output_data[: output_size.value])
            self._output_stream.seek(output_offset.value)
            self._output_stream.write(data)

    def append_sample(self, sample: Mp4MuxSample) -> None:
        """マルチプレックスにサンプルを追加

        Args:
            sample: 追加するサンプル

        Raises:
            RuntimeError: サンプルの追加に失敗した場合
        """
        if self._raw_muxer is None:
            raise RuntimeError("Muxer is closed")

        # 現在のストリーム位置を取得（サンプルデータを追記する位置）
        sample_data_offset = self._output_stream.tell()

        # サンプルデータをストリームに追記
        self._output_stream.write(sample.data)

        # サンプルデータのサイズを取得
        sample_data_size = len(sample.data)

        # マルチプレックスサンプル用の C 構造体を作成
        c_mux_sample = _RawMp4MuxSample()
        c_mux_sample.track_kind = _to_raw_mp4_track_kind(sample.track_kind)
        c_mux_sample.keyframe = sample.keyframe
        c_mux_sample.timescale = sample.timescale
        c_mux_sample.duration = sample.duration
        c_mux_sample.data_offset = sample_data_offset
        c_mux_sample.data_size = sample_data_size

        # サンプルエントリーを変換
        if sample.sample_entry is not None:
            with _to_raw_mp4_sample_entry(sample.sample_entry) as raw_entry:
                c_mux_sample.sample_entry = ctypes.pointer(raw_entry)

                error = self._lib.mp4_file_muxer_append_sample(
                    self._raw_muxer, ctypes.byref(c_mux_sample)
                )
                self._check_error(error)
        else:
            # sample_entry が None の場合は NULL ポインタを設定
            c_mux_sample.sample_entry = None

            error = self._lib.mp4_file_muxer_append_sample(
                self._raw_muxer, ctypes.byref(c_mux_sample)
            )
            self._check_error(error)

        # 出力データがあれば書き込む
        self._flush_output()

    def finalize(self) -> None:
        """マルチプレックス処理を完了

        Raises:
            RuntimeError: ファイナライズに失敗した場合
        """
        if self._raw_muxer is None:
            raise RuntimeError("Muxer is closed")

        error = self._lib.mp4_file_muxer_finalize(self._raw_muxer)
        self._check_error(error)
        self._finalized = True

        # 残りの出力データを書き込む
        self._flush_output()
