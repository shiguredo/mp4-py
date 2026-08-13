import gzip
import io
import os

import pytest

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
    Mp4FileMuxerOptions,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
    Mp4SampleEntryVp09,
    Mp4SampleEntryAvc1,
    Mp4SampleEntryHev1,
    Mp4SampleEntryHvc1,
    Mp4SampleEntryAv01,
    Mp4SampleEntryOpus,
    Mp4SampleEntryMp4a,
    Mp4SampleEntryFlac,
    Mp4SampleEntryStpp,
    Mp4SampleEntryWvtt,
    Mp4SampleEntryTx3g,
    Mp4TrackInfo,
    Mp4TrackMetadata,
    Mp4DemuxSample,
    estimate_maximum_moov_box_size,
)

# テスト用定数
NUM_VIDEO_SAMPLES = 5
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
SAMPLE_DURATION = 33333  # ~30 fps (マイクロ秒)
TIMESCALE = 1000000  # マイクロ秒


def create_dummy_sample(index: int, size: int = 1024) -> bytes:
    """テスト用のダミーサンプルデータを生成"""
    data = bytearray(size)
    for j in range(size):
        data[j] = (index * 17 + j) & 0xFF
    return bytes(data)


def test_mux_demux_roundtrip():
    """マルチプレックス → デマルチプレックスのラウンドトリップテスト"""
    # ===== マルチプレックス処理 =====
    output_buffer = io.BytesIO()

    # オプションなしで初期化（faststart 無効）
    muxer = Mp4FileMuxer(output_buffer)

    # サンプルを追加
    original_samples = []
    for i in range(NUM_VIDEO_SAMPLES):
        sample_data = create_dummy_sample(i)
        original_samples.append(
            {
                "data": sample_data,
                "timestamp": i * SAMPLE_DURATION,
                "duration": SAMPLE_DURATION,
                "keyframe": True,
            }
        )

        # VP08サンプルエントリー情報を作成
        sample_entry = Mp4SampleEntryVp08(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            bit_depth=8,
            chroma_subsampling=1,
        )

        # Mp4MuxSample を作成して追加
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    # マルチプレックス処理を完了
    muxer.finalize()

    # ===== デマルチプレックス処理 =====
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    # トラック情報を取得
    tracks = demuxer.tracks
    assert len(tracks) > 0, "No tracks found"
    assert tracks[0].kind == "video", "Expected video track"

    # サンプルを取得して比較
    demuxed_samples = []
    for demux_sample in demuxer:
        demuxed_samples.append(demux_sample)

    # サンプル数の確認
    assert len(demuxed_samples) == NUM_VIDEO_SAMPLES, (
        f"Expected {NUM_VIDEO_SAMPLES} samples, but got {len(demuxed_samples)}"
    )

    # 各サンプルの比較
    for i, (original, demuxed) in enumerate(zip(original_samples, demuxed_samples)):
        # タイムスタンプの確認
        assert demuxed.timestamp == original["timestamp"], (
            f"Sample {i}: timestamp mismatch. "
            f"Expected {original['timestamp']}, got {demuxed.timestamp}"
        )

        # 尺の確認
        assert demuxed.duration == original["duration"], (
            f"Sample {i}: duration mismatch. "
            f"Expected {original['duration']}, got {demuxed.duration}"
        )

        # サンプルデータの確認
        assert demuxed.data == original["data"], f"Sample {i}: sample data mismatch"

        # トラック情報の確認
        assert demuxed.track.kind == "video"
        assert demuxed.keyframe == original["keyframe"]


def test_mux_demux_roundtrip_with_faststart():
    """faststart オプション付きのラウンドトリップテスト"""
    # ===== マルチプレックス処理 =====
    output_buffer = io.BytesIO()

    # faststart オプションを設定
    estimated_size = Mp4FileMuxerOptions.estimate_maximum_moov_box_size(0, NUM_VIDEO_SAMPLES)
    options = Mp4FileMuxerOptions(reserved_moov_box_size=estimated_size)
    muxer = Mp4FileMuxer(output_buffer, options=options)

    # サンプルを追加
    original_samples = []
    for i in range(NUM_VIDEO_SAMPLES):
        sample_data = create_dummy_sample(i)
        original_samples.append(
            {
                "data": sample_data,
                "timestamp": i * SAMPLE_DURATION,
                "duration": SAMPLE_DURATION,
                "keyframe": True,
            }
        )

        sample_entry = Mp4SampleEntryVp08(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            bit_depth=8,
            chroma_subsampling=1,
        )

        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    # マルチプレックス処理を完了
    muxer.finalize()

    # ===== デマルチプレックス処理 =====
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    # トラック情報を取得
    tracks = demuxer.tracks
    assert len(tracks) > 0, "No tracks found"

    # サンプルを取得して比較
    demuxed_samples = []
    for demux_sample in demuxer:
        demuxed_samples.append(demux_sample)

    # サンプル数の確認
    assert len(demuxed_samples) == NUM_VIDEO_SAMPLES

    # 各サンプルの比較
    for original, demuxed in zip(original_samples, demuxed_samples):
        assert demuxed.timestamp == original["timestamp"]
        assert demuxed.duration == original["duration"]
        assert demuxed.data == original["data"]


def test_video_sample_entry_avc1():
    """AVC1 (H.264) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()

    # オプションなしで初期化
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0)

    # Minimal valid SPS for H.264 Baseline Profile, Level 4.1
    sps_data = bytes(
        [
            0x67,
            0x42,
            0x00,
            0x29,
            0xFF,
            0xE1,
            0x00,
            0x16,
            0x28,
            0x20,
            0x00,
            0x6D,
            0x86,
            0x64,
            0x00,
            0x00,
            0x00,
        ]
    )

    # Minimal valid PPS for H.264
    pps_data = bytes([0x68, 0xCE, 0x06, 0xE2])

    sample_entry = Mp4SampleEntryAvc1(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        avc_profile_indication=0x42,  # Baseline
        avc_level_indication=0x29,  # Level 4.1
        profile_compatibility=0xC0,
        sps_data=[sps_data],
        pps_data=[pps_data],
    )

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理でサンプルエントリーの確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryAvc1)
    assert demux_sample.sample_entry.width == VIDEO_WIDTH
    assert demux_sample.sample_entry.height == VIDEO_HEIGHT


def test_video_sample_entry_hev1():
    """HEV1 (H.265/HEVC) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0)
    sample_entry = Mp4SampleEntryHev1(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        general_profile_idc=2,  # Main 10
        general_level_idc=120,  # Level 4.0
        nalu_types=[33],  # SPS
        nalu_data=[b"dummy"],  # テスト用のダミーデータ
    )

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryHev1)


def test_video_sample_entry_hvc1():
    """HVC1 (H.265/HEVC) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0)
    sample_entry = Mp4SampleEntryHvc1(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        general_profile_idc=2,  # Main 10
        general_level_idc=120,  # Level 4.0
        nalu_types=[33],  # SPS
        nalu_data=[b"dummy"],  # テスト用のダミーデータ
    )

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryHvc1)


def test_video_sample_entry_av01():
    """AV01 (AV1) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0)
    sample_entry = Mp4SampleEntryAv01(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        seq_profile=0,  # Main
        seq_level_idx_0=20,  # Level 2.0
        config_obus=b"",
    )

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryAv01)


def test_video_sample_entry_vp09():
    """VP09 (VP9) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0)
    sample_entry = Mp4SampleEntryVp09(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        profile=0,
        level=31,
        bit_depth=8,
        chroma_subsampling=1,
    )

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryVp09)
    assert demux_sample.sample_entry.width == VIDEO_WIDTH
    assert demux_sample.sample_entry.height == VIDEO_HEIGHT


def test_audio_sample_entry_opus():
    """Opus サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0, size=256)
    sample_entry = Mp4SampleEntryOpus(
        channel_count=2,
        sample_rate=48000,
        sample_size=16,
        pre_skip=312,
        output_gain=0,
    )

    mux_sample = Mp4MuxSample(
        track_kind="audio",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=48000,
        duration=960,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 1
    assert tracks[0].kind == "audio"

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryOpus)
    assert demux_sample.sample_entry.channel_count == 2
    assert demux_sample.sample_entry.sample_rate == 48000


def test_audio_sample_entry_mp4a():
    """MP4A (AAC) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0, size=256)
    # AAC-LC の最小限の DecoderSpecificInfo
    dec_specific_info = bytes([0x11, 0x90])  # AAC-LC, 48kHz, stereo

    sample_entry = Mp4SampleEntryMp4a(
        channel_count=2,
        sample_rate=48000,
        sample_size=16,
        dec_specific_info=dec_specific_info,
    )

    mux_sample = Mp4MuxSample(
        track_kind="audio",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=48000,
        duration=1024,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 1
    assert tracks[0].kind == "audio"

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryMp4a)
    assert demux_sample.sample_entry.channel_count == 2
    assert demux_sample.sample_entry.sample_rate == 48000


def test_audio_sample_entry_flac():
    """FLAC サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0, size=256)
    # 最小限の FLAC STREAMINFO ブロック (34 バイト)
    streaminfo_data = bytes(
        [
            0x00,
            0x10,  # min_block_size = 16
            0x00,
            0x10,  # max_block_size = 16
            0x00,
            0x00,
            0x00,  # min_frame_size = 0
            0x00,
            0x00,
            0x00,  # max_frame_size = 0
            0x0B,
            0xB8,
            0x00,  # sample_rate = 48000 (20 bits) + channels-1 = 1 (3 bits) + bps-1 = 15 (5 bits)
            0xF0,
            0x00,
            0x00,
            0x00,
            0x00,  # total_samples (36 bits)
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,  # MD5 signature (16 bytes)
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )

    sample_entry = Mp4SampleEntryFlac(
        channel_count=2,
        sample_rate=48000,
        sample_size=16,
        streaminfo_data=streaminfo_data,
    )

    mux_sample = Mp4MuxSample(
        track_kind="audio",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=48000,
        duration=4096,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 1
    assert tracks[0].kind == "audio"

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryFlac)
    assert demux_sample.sample_entry.channel_count == 2
    assert demux_sample.sample_entry.sample_rate == 48000


def test_empty_mux_without_options():
    """オプションなしの空のマルチプレックステスト"""
    output_buffer = io.BytesIO()

    # オプションなしで初期化
    muxer = Mp4FileMuxer(output_buffer)
    muxer.finalize()

    # ファイルが生成されていることを確認
    assert len(output_buffer.getvalue()) > 0


def test_empty_mux_with_options():
    """オプション付きの空のマルチプレックステスト"""
    output_buffer = io.BytesIO()

    # オプションを指定
    options = Mp4FileMuxerOptions(
        reserved_moov_box_size=Mp4FileMuxerOptions.estimate_maximum_moov_box_size(0, 0)
    )
    muxer = Mp4FileMuxer(output_buffer, options=options)
    muxer.finalize()

    # ファイルが生成されていることを確認
    assert len(output_buffer.getvalue()) > 0


def test_track_info_properties():
    """TrackInfo のプロパティテスト"""
    track = Mp4TrackInfo(
        track_id=1,
        kind="video",
        duration=1000000,  # 1 秒
        timescale=1000000,
    )

    assert track.track_id == 1
    assert track.kind == "video"
    assert track.duration == 1000000
    assert track.timescale == 1000000


def test_demux_sample_properties():
    """DemuxSample のプロパティテスト"""
    track = Mp4TrackInfo(
        track_id=1,
        kind="video",
        duration=5000000,
        timescale=1000000,
    )
    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)

    demux_sample = Mp4DemuxSample(
        track=track,
        sample_entry=sample_entry,
        keyframe=True,
        timestamp=500000,
        duration=33333,
        data_offset=0,
        data_size=4,
        input_stream=io.BytesIO(b"test"),
    )

    assert demux_sample.timestamp_seconds == 0.5
    assert abs(demux_sample.duration_seconds - 0.033333) < 0.0001
    # composition_time_offset を省略した場合は None
    assert demux_sample.composition_time_offset is None


def test_demux_sample_composition_time_offset():
    """DemuxSample に composition_time_offset を指定した場合の保持を確認"""
    track = Mp4TrackInfo(
        track_id=1,
        kind="video",
        duration=5000000,
        timescale=1000000,
    )
    sample_entry = Mp4SampleEntryVp08(width=1920, height=1080)

    demux_sample = Mp4DemuxSample(
        track=track,
        sample_entry=sample_entry,
        keyframe=True,
        timestamp=500000,
        duration=33333,
        data_offset=0,
        data_size=4,
        input_stream=io.BytesIO(b"test"),
        composition_time_offset=-200,
    )

    assert demux_sample.composition_time_offset == -200


def test_mux_sample_composition_time_offset_default():
    """MuxSample の composition_time_offset を省略した場合は None"""
    sample_entry = Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT)
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(0),
    )
    assert mux_sample.composition_time_offset is None


def test_mux_demux_roundtrip_with_composition_time_offset():
    """composition_time_offset を指定した mux → demux のラウンドトリップ"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # 映像サンプルに ctts 出力用のオフセットを付与
    expected_offsets = [0, 1000, 2000]
    for i, offset in enumerate(expected_offsets):
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=Mp4SampleEntryAvc1(
                width=VIDEO_WIDTH,
                height=VIDEO_HEIGHT,
                avc_profile_indication=0x42,
                avc_level_indication=0x29,
                profile_compatibility=0xC0,
                sps_data=[bytes([0x67, 0x42, 0x00, 0x1E])],
                pps_data=[bytes([0x68, 0xCE, 0x38, 0x80])],
            ),
            keyframe=(i == 0),
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=create_dummy_sample(i),
            composition_time_offset=offset,
        )
        muxer.append_sample(mux_sample)
    muxer.finalize()

    # ラウンドトリップで読み出し
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    actual_offsets = [sample.composition_time_offset for sample in demuxer]

    assert actual_offsets == expected_offsets


def test_options_default_values():
    """Mp4FileMuxerOptions のデフォルト値テスト"""
    options = Mp4FileMuxerOptions()
    assert options.reserved_moov_box_size == 0


def test_options_custom_values():
    """Mp4FileMuxerOptions のカスタム値テスト"""
    options = Mp4FileMuxerOptions(reserved_moov_box_size=8192)
    assert options.reserved_moov_box_size == 8192


def test_multiple_samples_with_faststart():
    """複数サンプルのマルチプレックス/デマルチプレックステスト (faststart 有効)"""
    output_buffer = io.BytesIO()

    # faststart オプション付きで初期化
    estimated_size = Mp4FileMuxerOptions.estimate_maximum_moov_box_size(0, NUM_VIDEO_SAMPLES)
    options = Mp4FileMuxerOptions(reserved_moov_box_size=estimated_size)
    muxer = Mp4FileMuxer(output_buffer, options=options)

    # 複数のサンプルを追加
    for i in range(NUM_VIDEO_SAMPLES):
        sample_data = create_dummy_sample(i, size=2048)
        sample_entry = Mp4SampleEntryVp08(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
        )

        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=(i % 2 == 0),  # 交互にキーフレーム
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=sample_data,
        )
        muxer.append_sample(mux_sample)

    muxer.finalize()

    # デマルチプレックス処理
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    demuxed_samples = list(demuxer)
    assert len(demuxed_samples) == NUM_VIDEO_SAMPLES

    # キーフレーム情報の確認
    for i, sample in enumerate(demuxed_samples):
        expected_keyframe = i % 2 == 0
        assert sample.keyframe == expected_keyframe


def test_demuxer_with_invalid_data():
    """無効なデータを渡した場合のテスト"""
    # ランダムなバイナリデータ（MP4 ではない）
    invalid_data = b"\x00\x00\x00\x10abcd12345678"
    buffer = io.BytesIO(invalid_data)

    demuxer = Mp4FileDemuxer(buffer)

    # 無効なデータの場合、空のリストになる（ブロックしないこと）
    samples = list(demuxer)
    assert samples == []


def test_demuxer_with_empty_data():
    """空のデータを渡した場合のテスト"""
    buffer = io.BytesIO(b"")
    demuxer = Mp4FileDemuxer(buffer)

    # 空のファイルの場合、空のリストになる（ブロックしないこと）
    samples = list(demuxer)
    assert samples == []


def test_subtitle_sample_entry_stpp():
    """STPP (XML 字幕) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0, size=256)
    sample_entry = Mp4SampleEntryStpp(
        namespace="http://www.w3.org/ns/ttml",
        schema_location="http://www.w3.org/ns/ttml#profile",
        auxiliary_mime_types="application/ttml+xml",
    )

    mux_sample = Mp4MuxSample(
        track_kind="subtitle",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000,
        duration=100,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 1
    assert tracks[0].kind == "subtitle"

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryStpp)
    assert demux_sample.sample_entry.namespace == "http://www.w3.org/ns/ttml"
    assert demux_sample.sample_entry.schema_location == "http://www.w3.org/ns/ttml#profile"
    assert demux_sample.sample_entry.auxiliary_mime_types == "application/ttml+xml"
    assert demux_sample.data == sample_data


def test_subtitle_sample_entry_wvtt():
    """WVTT (WebVTT 字幕) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0, size=256)
    sample_entry = Mp4SampleEntryWvtt(config="WEBVTT\n")

    mux_sample = Mp4MuxSample(
        track_kind="subtitle",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000,
        duration=100,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 1
    assert tracks[0].kind == "subtitle"

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryWvtt)
    assert demux_sample.sample_entry.config == "WEBVTT\n"
    assert demux_sample.data == sample_data


def test_subtitle_sample_entry_tx3g():
    """TX3G (3GPP タイムドテキスト) サンプルエントリーのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    sample_data = create_dummy_sample(0, size=256)
    sample_entry = Mp4SampleEntryTx3g(
        display_flags=0,
        background_color_rgba=b"\x00\x00\x00\x00",
        default_text_box=(0, 0, 100, 100),
        default_style=(0, 10, 1, 0, 12, b"\xff\xff\xff\xff"),
        font_table=[(1, b"Serif")],
    )

    mux_sample = Mp4MuxSample(
        track_kind="subtitle",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000,
        duration=100,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 1
    assert tracks[0].kind == "subtitle"

    demux_sample = next(demuxer)
    assert isinstance(demux_sample.sample_entry, Mp4SampleEntryTx3g)
    assert demux_sample.sample_entry.display_flags == 0
    assert demux_sample.sample_entry.background_color_rgba == b"\x00\x00\x00\x00"
    assert demux_sample.sample_entry.default_text_box == (0, 0, 100, 100)
    assert demux_sample.sample_entry.default_style == (0, 10, 1, 0, 12, b"\xff\xff\xff\xff")
    assert demux_sample.sample_entry.font_table == [(1, b"Serif")]
    assert demux_sample.data == sample_data


def test_track_metadata():
    """トラックメタデータ (言語・名前) のテスト"""
    options = Mp4FileMuxerOptions(
        audio_track=Mp4TrackMetadata(language="eng", name="English Audio"),
        video_track=Mp4TrackMetadata(language="und", name="Video"),
        subtitle_track=Mp4TrackMetadata(language="jpn", name="日本語字幕"),
    )

    assert options.audio_track.language == "eng"
    assert options.audio_track.name == "English Audio"
    assert options.video_track.language == "und"
    assert options.video_track.name == "Video"
    assert options.subtitle_track.language == "jpn"
    assert options.subtitle_track.name == "日本語字幕"

    # オプション付きで muxer が生成できること
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer, options=options)
    muxer.finalize()
    assert len(output_buffer.getvalue()) > 0


def test_track_metadata_default():
    """トラックメタデータのデフォルト値のテスト"""
    metadata = Mp4TrackMetadata()
    assert metadata.language == "und"
    assert metadata.name == ""


def test_track_metadata_invalid_language():
    """不正な言語コードは muxer 生成時にエラーになる"""
    options = Mp4FileMuxerOptions(
        audio_track=Mp4TrackMetadata(language="JPN", name="Invalid"),
    )

    try:
        Mp4FileMuxer(io.BytesIO(), options=options)
        assert False, "不正な言語コードがエラーにならない"
    except ValueError as error:
        assert "invalid language code" in str(error)


def test_estimate_maximum_moov_box_size_variadic():
    """estimate_maximum_moov_box_size の可変長引数対応のテスト"""
    # 従来どおり 2 引数呼び出しが動作する
    size_2tracks = estimate_maximum_moov_box_size(0, 5)
    assert size_2tracks > 0

    # 3 トラック (音声・映像・字幕) 指定は 2 トラックより大きくなる
    size_3tracks = estimate_maximum_moov_box_size(100, 100, 100)
    assert size_3tracks > size_2tracks

    # 静的メソッドでも同じシグネチャ
    size_static = Mp4FileMuxerOptions.estimate_maximum_moov_box_size(100, 100, 100)
    assert size_static == size_3tracks


def test_subtitle_mux_demux_mixed_roundtrip():
    """映像・音声・字幕の 3 トラック混在ラウンドトリップのテスト"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # 映像トラック
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="video",
            sample_entry=Mp4SampleEntryVp08(width=1920, height=1080),
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=create_dummy_sample(0),
        )
    )
    # 音声トラック
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="audio",
            sample_entry=Mp4SampleEntryMp4a(
                channel_count=2,
                sample_rate=48000,
                dec_specific_info=b"\x11\x90",
            ),
            keyframe=True,
            timescale=48000,
            duration=1024,
            data=create_dummy_sample(1, size=256),
        )
    )
    # 字幕トラック
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="subtitle",
            sample_entry=Mp4SampleEntryStpp(namespace="http://www.w3.org/ns/ttml"),
            keyframe=True,
            timescale=1000,
            duration=100,
            data=create_dummy_sample(2, size=256),
        )
    )
    muxer.finalize()

    # デマルチプレックス処理で確認
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)

    tracks = demuxer.tracks
    assert len(tracks) == 3
    kinds = [track.kind for track in tracks]
    assert "video" in kinds
    assert "audio" in kinds
    assert "subtitle" in kinds

    demuxed_samples = list(demuxer)
    assert len(demuxed_samples) == 3


# =============================================================================
# append_sample 失敗時のロールバックテスト
# =============================================================================


def test_append_sample_rollback_on_error():
    """append_sample が失敗したときに書き込んだバイトが巻き戻る

    目的: timescale=0 で append_sample が失敗した場合に、write 済みのバイトが
          ストリームから除去され、位置が呼び出し前のままであることを確認する
    検証: 失敗後の tell() 位置と getvalue() の長さが write 前と一致すること
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # timescale=0 は append_sample 内の検証で ValueError になる
    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
        keyframe=True,
        timescale=0,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(0),
    )

    # コンストラクタで初期ボックス群が書き込まれた後の位置と長さを記録する
    position_before = output_buffer.tell()
    length_before = len(output_buffer.getvalue())

    with pytest.raises(ValueError):
        muxer.append_sample(mux_sample)

    # ストリーム位置が呼び出し前のままであること
    assert output_buffer.tell() == position_before, (
        f"ストリーム位置が {position_before} のままであること (実際: {output_buffer.tell()})"
    )
    # 書き込まれたバイトが除去されていること
    assert len(output_buffer.getvalue()) == length_before, (
        f"書き込み済みバイトが除去されていること (長さ {length_before} のまま。実際: {len(output_buffer.getvalue())})"
    )


def test_append_sample_retry_after_rollback():
    """巻き戻し後に補正したサンプルで retry できる

    目的: append_sample が失敗した後、入力の補正により 2 度目が成功し、
          以降の mux が破綻しないことを確認する
    検証: retry 後に finalize した出力を demux して内容が正しいこと
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # timescale=0 で失敗させる
    bad_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
        keyframe=True,
        timescale=0,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(0),
    )
    with pytest.raises(ValueError):
        muxer.append_sample(bad_sample)

    # 補正して retry する
    good_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(1),
    )
    muxer.append_sample(good_sample)
    muxer.finalize()

    # 出力が正常に demux できること
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demuxed_samples = list(demuxer)
    demuxer.close()

    assert len(demuxed_samples) == 1, f"サンプル数が 1 であること (実際: {len(demuxed_samples)})"
    # 巻き戻し後のサンプルメタデータが正しいこと
    assert demuxed_samples[0].timestamp == 0, (
        f"タイムスタンプが 0 であること (実際: {demuxed_samples[0].timestamp})"
    )
    assert demuxed_samples[0].duration == SAMPLE_DURATION, (
        f"duration が {SAMPLE_DURATION} であること (実際: {demuxed_samples[0].duration})"
    )
    assert demuxed_samples[0].data == create_dummy_sample(1), "retry 後のサンプルデータが壊れている"


def test_append_sample_unusable_message_on_non_seekable_stream():
    """非 seekable ストリームでは使用不能メッセージが付加される

    目的: 実パイプのように seek できないストリームで append_sample が失敗した
          場合に、Muxer が使用不能になった旨の案内が例外メッセージに含まれる
          ことを確認する
    検証: 例外メッセージに「破棄すること」の文言が含まれること
    """
    read_fd, write_fd = os.pipe()
    stream = os.fdopen(write_fd, "wb")
    try:
        muxer = Mp4FileMuxer(stream)
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=create_dummy_sample(0),
        )

        # 実パイプは tell() が失敗するため、write 前に使用不能としてエラーになる
        with pytest.raises(RuntimeError) as excinfo:
            muxer.append_sample(mux_sample)

        # 使用不能になった旨の案内がメッセージに含まれること
        assert "The muxer is in an unusable state and must be discarded" in str(excinfo.value), (
            f"使用不能の案内が含まれること (実際: {excinfo.value})"
        )
        # 元の tell() エラーがメッセージに保持されていること
        assert "failed to get stream position for append_sample" in str(excinfo.value), (
            f"tell() の失敗が保持されていること (実際: {excinfo.value})"
        )
    finally:
        stream.close()
        os.close(read_fd)


def test_append_sample_rollback_failure_message():
    """巻き戻しに失敗した場合に使用不能メッセージが付加される

    目的: ロールバックが失敗するストリーム (gzip.GzipFile) で append_sample が
          失敗した場合、例外メッセージに「破棄すること」の案内が付加される
          ことを確認する
    検証: 例外メッセージにロールバック失敗と使用不能の案内、元のエラーが
          含まれること
    """
    buffer = io.BytesIO()
    # GzipFile は write モードで後方 seek ができないため、ロールバックに失敗する
    stream = gzip.GzipFile(fileobj=buffer, mode="wb")
    try:
        muxer = Mp4FileMuxer(stream)
        mux_sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
            keyframe=True,
            timescale=0,
            duration=SAMPLE_DURATION,
            data=create_dummy_sample(0),
        )

        # timescale=0 で失敗し、ロールバック (後方 seek) にも失敗する
        with pytest.raises(RuntimeError) as excinfo:
            muxer.append_sample(mux_sample)

        # ロールバック失敗と使用不能の案内がメッセージに含まれること
        assert "failed to roll back the stream" in str(excinfo.value), (
            f"ロールバック失敗の案内が含まれること (実際: {excinfo.value})"
        )
        assert "The muxer is in an unusable state and must be discarded" in str(excinfo.value), (
            f"使用不能の案内が含まれること (実際: {excinfo.value})"
        )
        # 元のエラーがメッセージに保持されていること
        assert "timescale must be non-zero" in str(excinfo.value), (
            f"元のエラーが保持されていること (実際: {excinfo.value})"
        )
    finally:
        stream.close()


def test_append_sample_core_error_rollback_and_retry():
    """core が失敗する経路でもロールバックして retry できる

    目的: 先頭サンプルで sample_entry 未指定の場合、core.append_sample が
          MissingSampleEntry で失敗するが、ストリームは巻き戻され、sample_entry
          を補正した 2 度目の append_sample が成功することを確認する
    検証: retry 後に finalize した出力を demux して内容が正しいこと
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    # 先頭サンプルで sample_entry 未指定は core の MissingSampleEntry で失敗する
    bad_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=None,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(0),
    )
    with pytest.raises(RuntimeError):
        muxer.append_sample(bad_sample)

    # sample_entry を補正して retry する
    good_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(1),
    )
    muxer.append_sample(good_sample)
    muxer.finalize()

    # 出力が正常に demux できること
    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demuxed_samples = list(demuxer)
    demuxer.close()

    assert len(demuxed_samples) == 1, f"サンプル数が 1 であること (実際: {len(demuxed_samples)})"
    # 巻き戻し後のサンプルメタデータが正しいこと
    assert demuxed_samples[0].timestamp == 0, (
        f"タイムスタンプが 0 であること (実際: {demuxed_samples[0].timestamp})"
    )
    assert demuxed_samples[0].duration == SAMPLE_DURATION, (
        f"duration が {SAMPLE_DURATION} であること (実際: {demuxed_samples[0].duration})"
    )
    assert demuxed_samples[0].data == create_dummy_sample(1), "retry 後のサンプルデータが壊れている"
