"""MP4 ファイルをリマルチプレックスするサンプルプログラム

入力 MP4 ファイルを読み込んでデマルチプレックスし、
すべてのサンプルを新しい MP4 ファイルに書き直すプログラムである

使用方法:
    python remux.py <input_mp4> <output_mp4>

例:
    python remux.py input.mp4 output.mp4
"""

import sys

from mp4 import Mp4FileDemuxer, Mp4FileMuxer, Mp4MuxSample


def remux(demuxer: Mp4FileDemuxer, muxer: Mp4FileMuxer) -> int:
    """デマルチプレクサーからマルチプレクサーへすべてのサンプルを変換する

    demuxer から取得したサンプルを Mp4MuxSample へ詰め替えて
    muxer に逐次追加する (メモリに蓄積しない)。
    composition_time_offset も引き継ぐため、B フレーム入り H.264 等
    ctts を持つコンテンツでも PTS = DTS + composition_time_offset で
    導出される A/V 同期が崩れない。

    戻り値は処理したサンプル数である
    """
    sample_count = 0
    for sample in demuxer:
        mux_sample = Mp4MuxSample(
            track_kind=sample.track.kind,
            sample_entry=sample.sample_entry,
            keyframe=sample.keyframe,
            timescale=sample.track.timescale,
            duration=sample.duration,
            data=sample.data,
            composition_time_offset=sample.composition_time_offset,
        )
        muxer.append_sample(mux_sample)
        sample_count += 1
    return sample_count


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input_mp4> <output_mp4>", file=sys.stderr)
        sys.exit(1)

    input_filepath = sys.argv[1]
    output_filepath = sys.argv[2]

    try:
        # ==================== ストリーミング処理（mux/demux をインターリーブ） ====================
        print("Remuxing input file...")

        with Mp4FileDemuxer(input_filepath) as demuxer:
            # トラック情報を取得
            tracks = demuxer.tracks
            print(f"Found {len(tracks)} track(s)\n")

            with Mp4FileMuxer(output_filepath) as muxer:
                sample_count = remux(demuxer, muxer)

                print(f"Total samples processed: {sample_count}\n")

                # マルチプレックサーを完了
                print("Finalizing muxer...")
                muxer.finalize()

            print(f"\nSuccessfully remuxed '{input_filepath}' to '{output_filepath}'")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
