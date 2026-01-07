"""MP4 ファイルをデマルチプレックスして、メディアトラックとサンプル情報を表示する例

このスクリプトは、MP4 ファイルをデマルチプレックスして、含まれるメディアトラックと
サンプルの情報を表示します。

使用方法:
    python demux.py <mp4_file>

例:
    python demux.py input.mp4
"""

import sys
from pathlib import Path

from mp4 import Mp4FileDemuxer


def get_sample_entry_description(sample_entry) -> str:
    """サンプルエントリーの情報を文字列で返す"""
    if sample_entry is None:
        return "(same as previous)"

    from mp4 import (
        Mp4SampleEntryAvc1,
        Mp4SampleEntryHev1,
        Mp4SampleEntryVp08,
        Mp4SampleEntryVp09,
        Mp4SampleEntryAv01,
        Mp4SampleEntryOpus,
        Mp4SampleEntryMp4a,
        Mp4SampleEntryFlac,
    )

    if isinstance(sample_entry, Mp4SampleEntryAvc1):
        return (
            f"AVC1 (H.264) - {sample_entry.width}x{sample_entry.height}, "
            f"Profile: {sample_entry.avc_profile_indication}, "
            f"Level: {sample_entry.avc_level_indication}"
        )
    elif isinstance(sample_entry, Mp4SampleEntryHev1):
        return (
            f"HEV1 (H.265/HEVC) - {sample_entry.width}x{sample_entry.height}, "
            f"Profile: {sample_entry.general_profile_idc}, "
            f"Level: {sample_entry.general_level_idc}"
        )
    elif isinstance(sample_entry, Mp4SampleEntryVp08):
        return (
            f"VP08 (VP8) - {sample_entry.width}x{sample_entry.height}, "
            f"Bit depth: {sample_entry.bit_depth}"
        )
    elif isinstance(sample_entry, Mp4SampleEntryVp09):
        return (
            f"VP09 (VP9) - {sample_entry.width}x{sample_entry.height}, "
            f"Profile: {sample_entry.profile}, Level: {sample_entry.level}, "
            f"Bit depth: {sample_entry.bit_depth}"
        )
    elif isinstance(sample_entry, Mp4SampleEntryAv01):
        return (
            f"AV01 (AV1) - {sample_entry.width}x{sample_entry.height}, "
            f"Profile: {sample_entry.seq_profile}, Level: {sample_entry.seq_level_idx_0}"
        )
    elif isinstance(sample_entry, Mp4SampleEntryOpus):
        return (
            f"Opus - Channels: {sample_entry.channel_count}, "
            f"Sample rate: {sample_entry.sample_rate} Hz"
        )
    elif isinstance(sample_entry, Mp4SampleEntryMp4a):
        return (
            f"MP4A (AAC) - Channels: {sample_entry.channel_count}, "
            f"Sample rate: {sample_entry.sample_rate} Hz"
        )
    elif isinstance(sample_entry, Mp4SampleEntryFlac):
        return (
            f"FLAC - Channels: {sample_entry.channel_count}, "
            f"Sample rate: {sample_entry.sample_rate} Hz"
        )
    else:
        return "Unknown codec"


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <mp4_file>", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    file_path = Path(filepath)

    if not file_path.exists():
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        sys.exit(1)

    try:
        # MP4 ファイルをデマルチプレックス
        with Mp4FileDemuxer(filepath) as demuxer:
            # トラック情報を取得
            tracks = demuxer.tracks

            print(f"Found {len(tracks)} track(s)\n")

            # トラック情報を表示
            for i, track in enumerate(tracks, 1):
                print(f"Track {i}:")
                print(f"  Track ID: {track.track_id}")
                print(f"  Kind: {track.kind}")
                print(f"  Duration: {track.duration} (timescale: {track.timescale})")
                print(f"  Duration (seconds): {track.duration_seconds:.2f}s\n")

            # サンプル情報を表示
            sample_count = 0
            keyframe_count = 0

            print("Samples:")
            for sample in demuxer:
                sample_count += 1

                print(f"  Sample {sample_count}:")
                print(f"    Track ID: {sample.track.track_id}")
                print(f"    Keyframe: {'Yes' if sample.keyframe else 'No'}")
                print(f"    Timestamp: {sample.timestamp} ({sample.timestamp_seconds:.6f}s)")
                print(f"    Duration: {sample.duration} ({sample.duration_seconds:.6f}s)")
                print(f"    Data offset: 0x{sample._data_offset:x}")
                print(f"    Data size: {sample._data_size} bytes")

                # サンプルエントリー情報を表示
                if sample.sample_entry is not None:
                    print(f"    Codec: {get_sample_entry_description(sample.sample_entry)}")

                print()

                if keyframe_count == 0:
                    keyframe_count += sample.keyframe

                # 最初の10個のサンプルのみ表示
                if sample_count >= 10:
                    print("  ... (showing first 10 samples)\n")
                    break

            print(f"Total: {sample_count} samples shown")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
