import io

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
    Mp4TrackInfo,
    Mp4DemuxSample,
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
