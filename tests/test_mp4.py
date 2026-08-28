import gzip
import io
import pickle
import socket
import struct

import pytest

from mp4 import (
    Mp4DemuxSample,
    Mp4Exception,
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


def test_mux_sample_rejects_int_data():
    """Mp4MuxSample の data に int / bool を渡すと TypeError になる

    目的: bytes(12345) が b"\\x00" * 12345 を返す仕様により、型ミスの int が
          静かにゼロ埋めバイト列に変換される問題を検出する
    検証: data=12345 / data=True で TypeError が発火すること
    """
    # int は bytes(12345) がゼロ埋めバイト列を返すため型ミスとして弾く
    with pytest.raises(TypeError, match="expected bytes"):
        Mp4MuxSample(
            track_kind="video",
            sample_entry=None,
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=12345,
        )
    # bool も同様に bytes(True) が 1 バイトのゼロ列を返すため弾く
    with pytest.raises(TypeError, match="expected bytes"):
        Mp4MuxSample(
            track_kind="video",
            sample_entry=None,
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=True,
        )


def test_mux_sample_accepts_bytes_like_data():
    """Mp4MuxSample の data に bytes-like や list[int] を渡すと従来どおり動作する

    目的: extract_bytes のフォールバック (list[int]) と buffer protocol 経路
          (bytearray / memoryview) が型チェック追加後も機能することを確認する
    検証: 各入力が正しいバイト列に変換されること
    """
    # list[int] はフォールバックの意図された用途なので従来どおり動作する
    sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=None,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=[1, 2, 3],
    )
    assert sample.data == b"\x01\x02\x03"
    # bytearray / memoryview は buffer protocol 経由で従来どおり動作する
    sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=None,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=bytearray(b"abc"),
    )
    assert sample.data == b"abc"
    sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=None,
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=memoryview(b"xyz"),
    )
    assert sample.data == b"xyz"


def test_extract_bytes_rejects_int_in_sample_entries():
    """SampleEntry 系コンストラクタの bytes 引数に int を渡すと TypeError になる

    目的: extract_bytes を使う主要経路 (config_obus / dec_specific_info /
          streaminfo_data / sps_data / nalu_data) で型ミスの int が静かに
          ゼロ埋めバイト列に変換されないことを確認する
    検証: 各コンストラクタで int を渡すと TypeError が発火すること
    """
    with pytest.raises(TypeError, match="expected bytes"):
        Mp4SampleEntryAv01(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            seq_profile=0,
            seq_level_idx_0=0,
            config_obus=12345,
        )
    with pytest.raises(TypeError, match="expected bytes"):
        Mp4SampleEntryMp4a(
            channel_count=2,
            sample_rate=48000,
            dec_specific_info=12345,
        )
    with pytest.raises(TypeError, match="expected bytes"):
        Mp4SampleEntryFlac(
            channel_count=2,
            sample_rate=48000,
            streaminfo_data=12345,
        )
    # extract_bytes_list 経路 (sps_data の各要素が bytes に変換される)
    with pytest.raises(TypeError, match="expected bytes"):
        Mp4SampleEntryAvc1(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            avc_profile_indication=0x42,
            avc_level_indication=0x29,
            profile_compatibility=0xC0,
            sps_data=[12345],
        )
    # extract_bytes_list 経路 (nalu_data の各要素が bytes に変換される)
    with pytest.raises(TypeError, match="expected bytes"):
        Mp4SampleEntryHev1(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            general_profile_idc=1,
            general_level_idc=120,
            nalu_types=[32],
            nalu_data=[12345],
        )


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


def test_sample_entry_value_range_validation_vp08():
    """Vp08 の値域検証

    目的: vpcC のビット幅 (bit_depth 4 ビット / chroma_subsampling 3 ビット) と
          bit_depth の意味論的値域 (8 / 10 / 12) を超える値が黙って切り捨てられない
          ことを確認する
    検証: ビット幅超・意味論的値域超の値で ValueError が発火すること
    """
    # bit_depth は 4 ビット幅 (0..=15)。16 はシフトで u8 から折り返し黙って 0 になる
    with pytest.raises(ValueError, match="bit_depth"):
        Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT, bit_depth=16)
    # bit_depth は 4 ビット幅内だが、意味論的に 8 / 10 / 12 のみ
    with pytest.raises(ValueError, match="bit_depth"):
        Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT, bit_depth=9)
    # chroma_subsampling は 3 ビット幅 (0..=7)。8 はビット 3 が bit_depth 側に混入する
    with pytest.raises(ValueError, match=r"chroma_subsampling must be 0\.\.=0x7, got 0x8"):
        Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT, chroma_subsampling=8)


def test_sample_entry_value_range_validation_vp09():
    """Vp09 の値域検証

    目的: vpcC の値域検証 (VpccBox を Vp08 と共有する) が Vp09 でも機能することを
          確認する。検証内容は test_sample_entry_value_range_validation_vp08 と同一
    検証: ビット幅超・意味論的値域超の値で ValueError が発火すること
    """
    with pytest.raises(ValueError, match="bit_depth"):
        Mp4SampleEntryVp09(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            profile=0,
            level=0,
            bit_depth=16,
        )
    with pytest.raises(ValueError, match="bit_depth"):
        Mp4SampleEntryVp09(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            profile=0,
            level=0,
            bit_depth=9,
        )
    with pytest.raises(ValueError, match="chroma_subsampling"):
        Mp4SampleEntryVp09(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            profile=0,
            level=0,
            chroma_subsampling=8,
        )


def test_sample_entry_value_range_validation_avc1():
    """Avc1 の値域検証

    目的: avcC のビット幅 (length_size_minus_one 2 ビット / chroma_format 2 ビット /
          bit_depth_*_minus8 3 ビット) を超える値が黙って切り捨てられないことを
          確認する
    検証: 上限超の値で ValueError が発火すること
    """
    base = dict(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        avc_profile_indication=0x42,
        avc_level_indication=0x29,
        profile_compatibility=0xC0,
    )
    # length_size_minus_one は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="length_size_minus_one"):
        Mp4SampleEntryAvc1(**base, length_size_minus_one=4)
    # chroma_format は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="chroma_format"):
        Mp4SampleEntryAvc1(**base, chroma_format=4)
    # bit_depth_luma_minus8 は 3 ビット幅 (0..=7)
    with pytest.raises(ValueError, match="bit_depth_luma_minus8"):
        Mp4SampleEntryAvc1(**base, bit_depth_luma_minus8=8)
    # bit_depth_chroma_minus8 は 3 ビット幅 (0..=7)
    with pytest.raises(ValueError, match="bit_depth_chroma_minus8"):
        Mp4SampleEntryAvc1(**base, bit_depth_chroma_minus8=8)


def test_sample_entry_value_range_validation_hev1():
    """Hev1 の値域検証

    目的: hvcC のビット幅を超える値が黙って切り捨て・隣接ビットを汚染しないことを
          確認する
    検証: 上限超の値で ValueError が発火すること
    """
    base = dict(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        general_profile_idc=1,
        general_level_idc=120,
    )
    # general_profile_idc は 5 ビット幅 (0..=31)
    with pytest.raises(ValueError, match="general_profile_idc"):
        Mp4SampleEntryHev1(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            general_profile_idc=32,
            general_level_idc=120,
        )
    # general_profile_space は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="general_profile_space"):
        Mp4SampleEntryHev1(**base, general_profile_space=4)
    # general_tier_flag は 1 ビット幅 (0..=1)
    with pytest.raises(ValueError, match="general_tier_flag"):
        Mp4SampleEntryHev1(**base, general_tier_flag=2)
    # general_constraint_indicator_flags は 48 ビット幅
    with pytest.raises(ValueError, match="general_constraint_indicator_flags"):
        Mp4SampleEntryHev1(**base, general_constraint_indicator_flags=1 << 48)
    # chroma_format_idc は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="chroma_format_idc"):
        Mp4SampleEntryHev1(**base, chroma_format_idc=4)
    # bit_depth_luma_minus8 は 3 ビット幅 (0..=7)
    with pytest.raises(ValueError, match="bit_depth_luma_minus8"):
        Mp4SampleEntryHev1(**base, bit_depth_luma_minus8=8)
    # bit_depth_chroma_minus8 は 3 ビット幅 (0..=7)
    with pytest.raises(ValueError, match="bit_depth_chroma_minus8"):
        Mp4SampleEntryHev1(**base, bit_depth_chroma_minus8=8)
    # min_spatial_segmentation_idc は 12 ビット幅 (0..=0xFFF)
    with pytest.raises(ValueError, match="min_spatial_segmentation_idc"):
        Mp4SampleEntryHev1(**base, min_spatial_segmentation_idc=0x1000)
    # parallelism_type は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="parallelism_type"):
        Mp4SampleEntryHev1(**base, parallelism_type=4)
    # constant_frame_rate は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="constant_frame_rate"):
        Mp4SampleEntryHev1(**base, constant_frame_rate=4)
    # num_temporal_layers は 3 ビット幅 (0..=7)
    with pytest.raises(ValueError, match="num_temporal_layers"):
        Mp4SampleEntryHev1(**base, num_temporal_layers=8)
    # temporal_id_nested は 1 ビット幅 (0..=1)
    with pytest.raises(ValueError, match="temporal_id_nested"):
        Mp4SampleEntryHev1(**base, temporal_id_nested=2)
    # length_size_minus_one は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="length_size_minus_one"):
        Mp4SampleEntryHev1(**base, length_size_minus_one=4)
    # nalu_types は 6 ビット幅 (0..=63)
    with pytest.raises(ValueError, match="nalu_types"):
        Mp4SampleEntryHev1(
            **base,
            nalu_types=[64],
            nalu_data=[b"nalu"],
        )


def test_sample_entry_value_range_validation_hvc1():
    """Hvc1 の値域検証

    目的: hevc_pyclass! マクロで展開される Hvc1 にも Hev1 と同じ値域検証が
          入っていることを確認する
    検証: 上限超の値で ValueError が発火すること
    """
    with pytest.raises(ValueError, match="general_profile_idc"):
        Mp4SampleEntryHvc1(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            general_profile_idc=32,
            general_level_idc=120,
        )


def test_sample_entry_value_range_validation_av01():
    """Av01 の値域検証

    目的: av1C のビット幅を超える値が黙って切り捨て・隣接ビットを汚染しないことを
          確認する
    検証: 上限超の値で ValueError が発火すること
    """
    base = dict(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        seq_profile=0,
        seq_level_idx_0=0,
        config_obus=b"",
    )
    # seq_profile は 3 ビット幅 (0..=7)
    with pytest.raises(ValueError, match="seq_profile"):
        Mp4SampleEntryAv01(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            seq_profile=8,
            seq_level_idx_0=0,
            config_obus=b"",
        )
    # seq_level_idx_0 は 5 ビット幅 (0..=31)
    with pytest.raises(ValueError, match="seq_level_idx_0"):
        Mp4SampleEntryAv01(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            seq_profile=0,
            seq_level_idx_0=32,
            config_obus=b"",
        )
    # seq_tier_0 は 1 ビット幅 (0..=1)
    with pytest.raises(ValueError, match="seq_tier_0"):
        Mp4SampleEntryAv01(**base, seq_tier_0=2)
    # high_bitdepth は 1 ビット幅 (0..=1)
    with pytest.raises(ValueError, match="high_bitdepth"):
        Mp4SampleEntryAv01(**base, high_bitdepth=2)
    # twelve_bit は 1 ビット幅 (0..=1)
    with pytest.raises(ValueError, match="twelve_bit"):
        Mp4SampleEntryAv01(**base, twelve_bit=2)
    # monochrome は 1 ビット幅 (0..=1)
    with pytest.raises(ValueError, match="monochrome"):
        Mp4SampleEntryAv01(**base, monochrome=2)
    # chroma_subsampling_x / y は 1 ビット幅 (0..=1)
    with pytest.raises(ValueError, match="chroma_subsampling_x"):
        Mp4SampleEntryAv01(**base, chroma_subsampling_x=2)
    with pytest.raises(ValueError, match="chroma_subsampling_y"):
        Mp4SampleEntryAv01(**base, chroma_subsampling_y=2)
    # chroma_sample_position は 2 ビット幅 (0..=3)
    with pytest.raises(ValueError, match="chroma_sample_position"):
        Mp4SampleEntryAv01(**base, chroma_sample_position=4)
    # initial_presentation_delay_minus_one は 4 ビット幅 (0..=15)
    with pytest.raises(ValueError, match="initial_presentation_delay_minus_one"):
        Mp4SampleEntryAv01(
            **base,
            initial_presentation_delay_present=True,
            initial_presentation_delay_minus_one=16,
        )
    # present=false でも構築時に弾かれる (コアに渡らない値も一貫して検証する)
    with pytest.raises(ValueError, match="initial_presentation_delay_minus_one"):
        Mp4SampleEntryAv01(
            **base,
            initial_presentation_delay_present=False,
            initial_presentation_delay_minus_one=16,
        )


def test_sample_entry_value_range_boundaries_accepted():
    """値域の上限ちょうどはエラーにならず roundtrip できる

    目的: 値域検証の境界が「上限ちょうどは通過・上限 +1 は拒否」であることを
          直接テストで固定する (PBT は境界値を必ず生成するとは限らないため)
    検証: 上限ちょうどの値でコンストラクタが成功し、roundtrip で値が保持されること
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    sample_entry = Mp4SampleEntryVp08(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        bit_depth=12,
        chroma_subsampling=7,  # 3 ビット幅の上限
    )
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=TIMESCALE,
            duration=SAMPLE_DURATION,
            data=create_dummy_sample(0),
        )
    )
    muxer.finalize()

    output_buffer.seek(0)
    restored = next(Mp4FileDemuxer(output_buffer)).sample_entry
    assert isinstance(restored, Mp4SampleEntryVp08)
    assert restored.chroma_subsampling == 7, (
        f"上限ちょうどの chroma_subsampling が保持されること (実際: {restored.chroma_subsampling})"
    )


def test_sample_entry_value_range_validation_mp4a():
    """Mp4a の値域検証

    目的: esds の buffer_size_db (24 ビット) を超える値が黙って破棄されないことを
          確認する
    検証: 上限超の値で ValueError が発火すること
    """
    with pytest.raises(ValueError, match="buffer_size_db"):
        Mp4SampleEntryMp4a(
            channel_count=2,
            sample_rate=48000,
            dec_specific_info=b"",
            buffer_size_db=0x1000000,
        )


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


def test_track_info_zero_timescale_raises_value_error():
    """timescale=0 の TrackInfo は ValueError になる

    目的: timescale=0 は timestamp_seconds / duration_seconds の 0 除算で
          inf / nan を生むため、コンストラクタで弾かれることを確認する
    検証: Mp4TrackInfo(timescale=0) で ValueError が発火すること
    """
    with pytest.raises(ValueError, match="timescale must be non-zero"):
        Mp4TrackInfo(
            track_id=1,
            kind="video",
            duration=1000,
            timescale=0,
        )


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
    # frozen のため Py フィールドへの代入が readonly attribute で拒否される
    # (frozen クラスでは Py フィールドが Py_READONLY の member_descriptor になる。
    # 一般の getter フィールドは frozen の有無に関わらず not writable になるため、
    # ここでは frozen 固有の挙動を検証する)
    with pytest.raises(AttributeError, match="readonly attribute"):
        demux_sample.track = None


def test_demux_sample_data_cached():
    """DemuxSample の遅延読み込みがキャッシュされる

    目的: data アクセスが 1 回目で読み込み・キャッシュされ、2 回目以降は
          キャッシュを返すことを確認する (frozen + Mutex の interior mutability)
    検証: 同一インスタンスの .data が 2 回アクセスしても同一オブジェクトになること
    """
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

    assert demux_sample.data is demux_sample.data, "2 回目の data アクセスがキャッシュを返すこと"


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
    """EOF に達した無効なデータは空リストになる

    目的: moov 発見前に EOF に達するデータ (32 バイト未満) はパースエラーに
          ならず「トラック 0 本の正常終了」になることを確認する
    検証: 16 バイトの無効データで空リストになること (パースエラーの
          RuntimeError 化は 32 バイト以上のデータでのみ発生する)
    """
    # ランダムなバイナリデータ（MP4 ではない）
    invalid_data = b"\x00\x00\x00\x10abcd12345678"
    buffer = io.BytesIO(invalid_data)

    demuxer = Mp4FileDemuxer(buffer)

    # 無効なデータの場合、空のリストになる（ブロックしないこと）
    samples = list(demuxer)
    assert samples == []


def test_demuxer_reports_parse_error():
    """パースエラーが RuntimeError として報告される

    目的: 破損データのパースエラーが StopIteration / 空リストに隠蔽されず、
          Python 側に RuntimeError として届くことを確認する
    検証: 32 バイト以上の不正データで tracks アクセスと反復の両方が
          RuntimeError を発生させ、エラー後の tracks が空リスト・以後の反復が
          StopIteration で終わること
    """
    # ftyp 型不一致になる 32 バイト以上の不正データ
    invalid_data = b"\x00" * 40

    # tracks アクセスでパースエラーが報告される
    demuxer = Mp4FileDemuxer(io.BytesIO(invalid_data))
    with pytest.raises(RuntimeError, match="Failed to decode MP4 box"):
        _ = demuxer.tracks
    # エラー後のデマクサーは tracks が空リスト・以後の反復が StopIteration
    assert demuxer.tracks == [], "エラー後の tracks が空リストであること"
    with pytest.raises(StopIteration):
        next(iter(demuxer))

    # 反復でもパースエラーが報告される
    demuxer = Mp4FileDemuxer(io.BytesIO(invalid_data))
    with pytest.raises(RuntimeError, match="Failed to decode MP4 box"):
        for _ in demuxer:
            pass

    # エラー後のデマクサーは tracks が空リスト・以後の反復が StopIteration
    assert demuxer.tracks == [], "エラー後の tracks が空リストであること"
    with pytest.raises(StopIteration):
        next(iter(demuxer))


def test_demuxer_reports_sample_table_error():
    """SampleTableError も RuntimeError として報告される

    目的: サンプルテーブルの不整合 (stsc の first_chunk 改変) による
          SampleTableError が Python 側に RuntimeError として届くことを確認する
    検証: 正規 MP4 の stsc の first_chunk を書き換えると "Sample table error"
          を含む RuntimeError が発火すること
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    sample_entry = Mp4SampleEntryVp08(width=640, height=480)
    for i in range(3):
        muxer.append_sample(
            Mp4MuxSample(
                track_kind="video",
                sample_entry=sample_entry,
                keyframe=(i == 0),
                timescale=30000,
                duration=1001,
                data=create_dummy_sample(i),
            )
        )
    muxer.finalize()

    mp4_bytes = bytearray(output_buffer.getvalue())
    # stsc ボックス: size(4) + type(4) + version/flags(4) + entry_count(4) + first_chunk(4)
    stsc_pos = mp4_bytes.find(b"stsc")
    assert stsc_pos >= 0, "stsc ボックスが存在すること"
    mp4_bytes[stsc_pos + 16 : stsc_pos + 20] = (5).to_bytes(4, "big")

    demuxer = Mp4FileDemuxer(io.BytesIO(bytes(mp4_bytes)))
    with pytest.raises(RuntimeError, match="Sample table error"):
        _ = demuxer.tracks


def test_demuxer_feed_error_state_after_error():
    """feed 経路のエラー後も tracks が空リスト・以後の反復が StopIteration

    目的: feed_required_input 中のエラー (ループ上限超過) 後も、DecodeError と
          同じ状態遷移 (tracks 空リスト + ended) になることを確認する
    検証: ループ上限を超える破損データで RuntimeError が発生し、エラー後の
          tracks が空リスト・以後の反復が StopIteration で終わること
    """
    # ftyp + 28 バイトの free ボックスを 10001 個並べる (ループ上限 10000 を超える)
    ftyp = bytes(
        [
            0x00,
            0x00,
            0x00,
            0x14,
            0x66,
            0x74,
            0x79,
            0x70,
            0x69,
            0x73,
            0x6F,
            0x6D,
            0x00,
            0x00,
            0x02,
            0x00,
            0x69,
            0x73,
            0x6F,
            0x6D,
        ]
    )
    box = struct.pack(">I", 28) + b"free" + b"\x00" * 20
    invalid_data = ftyp + box * 10001

    demuxer = Mp4FileDemuxer(io.BytesIO(invalid_data))
    with pytest.raises(RuntimeError, match="too many iterations"):
        _ = demuxer.tracks

    assert demuxer.tracks == [], "エラー後の tracks が空リストであること"
    with pytest.raises(StopIteration):
        next(iter(demuxer))


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


def test_subtitle_sample_entry_stpp_rejects_null_characters():
    """STPP の null 文字入り入力は ValueError になる (panic しない)

    目的: Utf8String は null 文字を含む文字列を拒否する (None を返す) ため、
          expect による panic ではなく ValueError として報告されることを確認する
    検証: 3 フィールドそれぞれに null 文字入り入力を渡すと ValueError が発火すること
    """
    # namespace に null 文字を含む
    with pytest.raises(ValueError, match="namespace must not contain null characters"):
        Mp4SampleEntryStpp(namespace="http://www.w3.org/ns/ttml\u0000example")
    # schema_location に null 文字を含む
    with pytest.raises(ValueError, match="schema_location must not contain null characters"):
        Mp4SampleEntryStpp(
            namespace="http://www.w3.org/ns/ttml",
            schema_location="http://www.w3.org/ns/ttml#profile\u0000",
        )
    # auxiliary_mime_types に null 文字を含む
    with pytest.raises(ValueError, match="auxiliary_mime_types must not contain null characters"):
        Mp4SampleEntryStpp(
            namespace="http://www.w3.org/ns/ttml",
            auxiliary_mime_types="application/ttml+xml\u0000",
        )
    # null 文字を含まない正規の入力は従来どおり構築できる
    sample_entry = Mp4SampleEntryStpp(
        namespace="http://www.w3.org/ns/ttml",
        schema_location="http://www.w3.org/ns/ttml#profile",
        auxiliary_mime_types="application/ttml+xml",
    )
    assert sample_entry.namespace == "http://www.w3.org/ns/ttml"
    assert sample_entry.schema_location == "http://www.w3.org/ns/ttml#profile"
    assert sample_entry.auxiliary_mime_types == "application/ttml+xml"


# null 入り stpp ボックスのデマルチプレックス挙動を検証するための定数・ヘルパー
_STPP_NAMESPACE = "http://www.w3.org/ns/ttml"
_STPP_SCHEMA_LOCATION = "http://www.w3.org/ns/ttml#profile"
_STPP_AUX_MIME_TYPES = "application/ttml+xml"
_STPP_NAMESPACE_BYTES = _STPP_NAMESPACE.encode()


def _build_stpp_subtitle_mp4() -> bytes:
    """STPP 字幕トラックを 1 本含む正規 MP4 のバイト列を生成

    サンプルデータは create_dummy_sample で生成する。これは "stpp" という
    バイト列を含まないため、後段の find による stpp ボックスの位置特定が
    正しく 1 箇所だけに一致する前提を満たす。
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    sample_entry = Mp4SampleEntryStpp(
        namespace=_STPP_NAMESPACE,
        schema_location=_STPP_SCHEMA_LOCATION,
        auxiliary_mime_types=_STPP_AUX_MIME_TYPES,
    )
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="subtitle",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=1000,
            duration=100,
            data=create_dummy_sample(0, size=256),
        )
    )
    muxer.finalize()
    return output_buffer.getvalue()


def _corrupt_stpp_namespace(mp4_bytes: bytes, mode: str) -> bytes:
    """stpp ボックスの namespace 領域を破損させた MP4 のバイト列を返す

    mode が "single" なら namespace 途中の 1 バイトを null 置換し、
    "consecutive" なら namespace 領域全体を null 化する。

    単一 null がデコードエラー (InsufficientBuffer) になるのは、フィールドずれの
    結果として残った auxiliary_mime_types の先頭 4 バイトが unknown box の巨大な
    size と解釈されるためであり、この文字列内容に暗黙に依存している。
    """
    data = bytearray(mp4_bytes)
    # テスト用に構築したファイルは stpp ボックスが 1 個だけ、かつサンプルデータに
    # "stpp" というバイト列が現れない前提で find で位置を特定する
    stpp_pos = data.find(b"stpp")
    assert stpp_pos >= 0, "stpp ボックスが見つからないこと"
    # stpp ボックスの先頭は size(4) + type(4) なので、type 位置から 4 戻る
    box_start = stpp_pos - 4
    # ペイロードはヘッダ (size 4 + type 4) + reserved(6) + data_reference_index(2)
    # を除いた先頭が namespace の null 終端文字列になる
    ns_start = box_start + 8 + 6 + 2
    # 破損対象が期待した namespace の先頭であることを自己検証する
    assert data[ns_start : ns_start + 4] == _STPP_NAMESPACE_BYTES[:4], (
        "破損位置が namespace 先頭でないこと"
    )
    ns_len = len(_STPP_NAMESPACE_BYTES)
    if mode == "single":
        data[ns_start + ns_len // 2] = 0x00
    elif mode == "consecutive":
        for i in range(ns_start, ns_start + ns_len):
            data[i] = 0x00
    else:
        raise AssertionError(f"不明なモード: {mode}")
    return bytes(data)


def test_stpp_demux_reports_single_null_corruption():
    """stpp の namespace 途中の null 置換は RuntimeError になる (現状挙動の特性化)

    目的: 破損した null 入り stpp ボックスのうち、文字列領域内の 1 バイトを
          null 置換する破損 (単一 null) のデマルチプレックス挙動を特性化する。
          コアの Utf8String::decode は null で読み止めてフィールドを短縮する
          だけで、null 自体を検出するわけではない。このため後続フィールドが
          ずれ、残りのバイトを unknown box として読む際にペイロード境界を
          超えて InsufficientBuffer (デコードエラー) になる。これは単一 null
          の位置やレイアウトに依存する現状挙動の特性化であり、null の検出
          そのものを保証するものではない
    検証: namespace 途中の 1 バイトを null 置換した MP4 のデマルチプレックスが
          "Failed to decode MP4 box" を含み、stpp ボックス名が示された
          RuntimeError を報告すること
    注記: コア側で null 検出を実装した場合は、このエラー種別や match 対象が
          変わり得るため、その時点で検証内容を更新すること
    """
    mp4_bytes = _build_stpp_subtitle_mp4()
    corrupted = _corrupt_stpp_namespace(mp4_bytes, "single")
    demuxer = Mp4FileDemuxer(io.BytesIO(corrupted))
    with pytest.raises(RuntimeError, match="Failed to decode MP4 box.*\\[stpp\\]"):
        _ = demuxer.tracks


def test_stpp_demux_reports_consecutive_null_corruption():
    """stpp の namespace 全体の null 化は RuntimeError になる (コア 2026.5.0 追従)

    目的: 従来はフィールド先頭からの連続 null が空文字列として読まれ、
          残りバイトが可変サイズの unknown box として成功するため、
          エラーなしで欠損値 (空文字列) が返る黙っての誤パースだった。
          コア 2026.5.0 で UnknownBox のデコードがコンテナ内部の可変長
          ボックス (size=0 のゼロ埋め) を拒否するようになり、この破損は
          デコードエラーとして報告される。旧特性化テストの注記が求めていた
          「エラーになる」正の検証への置き換え
    検証: namespace 領域全体を null 化した MP4 のデマルチプレックスが
          "Failed to decode MP4 box" を含み、stpp ボックス名が示された
          RuntimeError を報告すること
    注記: Utf8String::decode 自体は依然として null で読み止めるため、
          null 検出そのものを保証するものではない。コア側で null 検出を
          実装した場合は、このエラー種別や match 対象がかわり得るため、
          その時点で検証内容を更新すること
    """
    mp4_bytes = _build_stpp_subtitle_mp4()
    corrupted = _corrupt_stpp_namespace(mp4_bytes, "consecutive")
    demuxer = Mp4FileDemuxer(io.BytesIO(corrupted))
    with pytest.raises(RuntimeError, match="Failed to decode MP4 box.*\\[stpp\\]"):
        _ = demuxer.tracks


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

    with pytest.raises(ValueError, match="invalid language code"):
        Mp4FileMuxer(io.BytesIO(), options=options)


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


def test_append_sample_after_finalize_preserves_output():
    """finalize 後の append_sample が出力ファイルを破壊しない

    目的: finalize 後の append_sample は write に進む前にエラーを返し、
          mdat ペイロードを上書きしないことを確認する
    検証: finalize 直後の出力バッファの内容が、失敗した append_sample の前後で
          一致すること (ロールバックによる truncate が実行されないこと)
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(0),
    )
    muxer.append_sample(sample)
    muxer.finalize()

    before = output_buffer.getvalue()

    with pytest.raises(RuntimeError, match="finalized"):
        muxer.append_sample(sample)

    after = output_buffer.getvalue()
    assert after == before, (
        f"finalize 後の append_sample で出力内容が破壊されないこと "
        f"(破壊前 {len(before)} バイト / 破壊後 {len(after)} バイト)"
    )


def test_append_sample_after_finalize_preserves_output_with_faststart():
    """faststart でも finalize 後の append_sample が出力ファイルを破壊しない

    目的: reserved_moov_box_size 指定時 (faststart) でも、finalize 後の
          append_sample が write 前にエラーを返し、出力を破壊しないことを確認する
    検証: faststart レイアウトで finalize 直後の出力バッファの内容が、
          失敗した append_sample の前後で一致すること
    """
    output_buffer = io.BytesIO()
    options = Mp4FileMuxerOptions(
        reserved_moov_box_size=1024 * 1024,
    )
    muxer = Mp4FileMuxer(output_buffer, options)
    sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(0),
    )
    muxer.append_sample(sample)
    muxer.finalize()

    before = output_buffer.getvalue()

    with pytest.raises(RuntimeError, match="finalized"):
        muxer.append_sample(sample)

    after = output_buffer.getvalue()
    assert after == before, (
        f"faststart でも finalize 後の append_sample で出力内容が破壊されないこと "
        f"(破壊前 {len(before)} バイト / 破壊後 {len(after)} バイト)"
    )


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

    目的: seek できないストリーム (socket.socketpair 由来) で append_sample が
          失敗した場合に、Muxer が使用不能になった旨の案内が例外メッセージに
          含まれることを確認する
    検証: 例外メッセージに「破棄すること」の文言が含まれること
    注記: POSIX の実パイプも同様に tell() が失敗するが、Windows のパイプは
          tell() が成功するため、プラットフォーム非依存の socket を使う
    """
    sock_a, sock_b = socket.socketpair()
    stream = sock_a.makefile("wb")
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

        # socket は tell() が失敗するため、write 前に使用不能としてエラーになる
        with pytest.raises(RuntimeError) as excinfo:
            muxer.append_sample(mux_sample)

        # 使用不能になった旨の案内がメッセージに含まれること
        assert "The muxer is in an unusable state and must be discarded" in str(excinfo.value), (
            f"使用不能の案内が含まれること (実際: {excinfo.value})"
        )
    finally:
        stream.close()
        sock_b.close()


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


def test_mp4_exception_is_exported():
    """Mp4Exception が mp4.Mp4Exception としてアクセスできる

    目的: 破損データ検出エラーの型分類用例外が公開されていることを確認する
    検証: import 経由でクラスにアクセスでき、RuntimeError のサブクラスであること
    """
    assert isinstance(Mp4Exception, type)
    assert issubclass(Mp4Exception, RuntimeError), (
        "Mp4Exception は RuntimeError のサブクラスであること"
    )


def test_mp4_exception_module_and_pickle():
    """Mp4Exception の module と pickle ラウンドトリップ

    目的: __module__ が mp4.mp4_ext になっていること (pickle と repr のため) と、
          pickle でシリアライズ → 復元できることを確認する
    検証: __module__ の値と pickle ラウンドトリップの成功
    """
    assert Mp4Exception.__module__ == "mp4.mp4_ext", (
        f"__module__ が mp4.mp4_ext であること (実際: {Mp4Exception.__module__})"
    )
    restored = pickle.loads(pickle.dumps(Mp4Exception))
    assert restored is Mp4Exception, "pickle ラウンドトリップで同一クラスが復元されること"


def test_mp4_exception_caught_for_corrupted_sample_data():
    """破損データ検出エラーが Mp4Exception として発火する

    目的: MAX_SAMPLE_SIZE ガードが Mp4Exception を発生させ、isinstance(e,
          RuntimeError) も真であることを確認する
    検証: Mp4DemuxSample を data_size=2**30+1 で直接構築して .data を呼ぶと
          Mp4Exception が発火し、RuntimeError のサブクラスとして捕捉できること
    """
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
        data_size=2**30 + 1,
        input_stream=io.BytesIO(b"x"),
    )

    with pytest.raises(Mp4Exception, match="Sample data size too large") as excinfo:
        _ = demux_sample.data
    assert isinstance(excinfo.value, RuntimeError), (
        "Mp4Exception は RuntimeError のサブクラスとして捕捉できること"
    )


def test_mp4_exception_caught_for_sample_data_size_mismatch():
    """読み込みサイズ不一致エラーが Mp4Exception として発火する

    目的: 破損 MP4 のサンプルサイズが実ファイルサイズを超える場合の検出エラー
          (Failed to read sample data) が Mp4Exception として発火することを確認する
    検証: Mp4DemuxSample を data_size=4 で構築し、2 バイトしかない BytesIO を渡して
          .data を呼ぶと Mp4Exception が発火すること
    """
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
        input_stream=io.BytesIO(b"xx"),
    )

    with pytest.raises(Mp4Exception, match="Failed to read sample data") as excinfo:
        _ = demux_sample.data
    assert isinstance(excinfo.value, RuntimeError), (
        "Mp4Exception は RuntimeError のサブクラスとして捕捉できること"
    )


def test_mp4_exception_caught_for_corrupted_stsz():
    """__next__ の MAX_SAMPLE_SIZE ガードが Mp4Exception として発火する

    目的: 破損 MP4 の stsz ボックスが巨大な sample_size を持つ場合に、イテレーション
          中の __next__ ガードが Mp4Exception を発生させることを確認する
    検証: 正規 MP4 の stsz の sample_size フィールドを 2**30+1 に書き換えて demux
          すると Mp4Exception が発火すること
    """
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)
    sample_entry = Mp4SampleEntryVp08(width=640, height=480)
    muxer.append_sample(
        Mp4MuxSample(
            track_kind="video",
            sample_entry=sample_entry,
            keyframe=True,
            timescale=30000,
            duration=1001,
            data=create_dummy_sample(0),
        )
    )
    muxer.finalize()

    mp4_bytes = bytearray(output_buffer.getvalue())
    # find(b"stsz") は type フィールドの先頭位置を返す。
    # stsz ボックスは type 直後に version/flags(4) + sample_size(4) + sample_count(4) が続く。
    stsz_pos = mp4_bytes.find(b"stsz")
    assert stsz_pos >= 0, "stsz ボックスが存在すること"
    # sample_size を巨大値に書き換える (固定サイズ形式に相当し、すべてのサンプルが対象になる)
    mp4_bytes[stsz_pos + 8 : stsz_pos + 12] = (2**30 + 1).to_bytes(4, "big")

    demuxer = Mp4FileDemuxer(io.BytesIO(bytes(mp4_bytes)))
    with pytest.raises(Mp4Exception, match="Sample data size too large") as excinfo:
        for _ in demuxer:
            pass
    assert isinstance(excinfo.value, RuntimeError), (
        "Mp4Exception は RuntimeError のサブクラスとして捕捉できること"
    )


def test_mp4_exception_caught_for_required_input_size():
    """Required input size ガードが Mp4Exception として発火する

    目的: 破損 MP4 の largesize が巨大な場合に、feed_required_input のサイズガードが
          Mp4Exception を発生させることを確認する
    検証: size=1 (largesize 使用) + ftyp + largesize=2**63+16 のバイト列を demux
          すると Mp4Exception が発火すること
    """
    # ボックスサイズ 1 は largesize フィールド (8 バイト) を使うことを意味する。
    # 末尾の 16 バイトは ftyp ボックス本体であり、読み込み要求サイズ (32 バイト)
    # を満たすフィラーを兼ねる。これが欠けると EOF 判定でループが終了し、
    # サイズガードに到達しない。
    data = struct.pack(">I", 1) + b"ftyp" + struct.pack(">Q", 2**63 + 16) + b"\x00" * 16
    demuxer = Mp4FileDemuxer(io.BytesIO(data))
    with pytest.raises(Mp4Exception, match="Required input size too large") as excinfo:
        for _ in demuxer:
            pass
    assert isinstance(excinfo.value, RuntimeError), (
        "Mp4Exception は RuntimeError のサブクラスとして捕捉できること"
    )


def test_mp4_exception_not_raised_for_other_errors():
    """破損データ以外のエラーは RuntimeError のままである

    目的: 内部状態エラー (muxer is closed / demuxer is closed) が Mp4Exception に
          変換されないことを確認する
    検証: close() 後の append_sample と close() 後の demux が type(e) is
          RuntimeError のまま発火すること
    """
    muxer = Mp4FileMuxer(io.BytesIO())
    muxer.close()
    sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=Mp4SampleEntryVp08(width=VIDEO_WIDTH, height=VIDEO_HEIGHT),
        keyframe=True,
        timescale=TIMESCALE,
        duration=SAMPLE_DURATION,
        data=create_dummy_sample(0),
    )
    with pytest.raises(RuntimeError, match="muxer is closed") as excinfo:
        muxer.append_sample(sample)
    assert type(excinfo.value) is RuntimeError, (
        "Mp4Exception ではなく RuntimeError そのものであること"
    )

    demuxer = Mp4FileDemuxer(io.BytesIO(b"x"))
    demuxer.close()
    with pytest.raises(RuntimeError, match="demuxer is closed") as excinfo:
        _ = demuxer.tracks
    assert type(excinfo.value) is RuntimeError, (
        "Mp4Exception ではなく RuntimeError そのものであること"
    )
