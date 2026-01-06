"""
サンプルエントリーのフィールド保持の property-based testing
"""

import io

from hypothesis import given, settings

from mp4 import (
    Mp4FileDemuxer,
    Mp4FileMuxer,
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
)

from conftest import (
    st_vp08_sample_entry,
    st_vp09_sample_entry,
    st_avc1_sample_entry,
    st_hev1_sample_entry,
    st_hvc1_sample_entry,
    st_av01_sample_entry,
    st_opus_sample_entry,
    st_mp4a_sample_entry,
    st_flac_sample_entry,
    st_sample_data,
)


@given(sample_entry=st_vp08_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_vp08_fields_preserved(sample_entry: Mp4SampleEntryVp08, sample_data: bytes) -> None:
    """VP08 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryVp08)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.bit_depth == sample_entry.bit_depth
    assert restored.chroma_subsampling == sample_entry.chroma_subsampling
    assert restored.video_full_range_flag == sample_entry.video_full_range_flag
    assert restored.colour_primaries == sample_entry.colour_primaries
    assert restored.transfer_characteristics == sample_entry.transfer_characteristics
    assert restored.matrix_coefficients == sample_entry.matrix_coefficients


@given(sample_entry=st_vp09_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_vp09_fields_preserved(sample_entry: Mp4SampleEntryVp09, sample_data: bytes) -> None:
    """VP09 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryVp09)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.profile == sample_entry.profile
    assert restored.level == sample_entry.level
    assert restored.bit_depth == sample_entry.bit_depth
    assert restored.chroma_subsampling == sample_entry.chroma_subsampling
    assert restored.video_full_range_flag == sample_entry.video_full_range_flag


@given(sample_entry=st_avc1_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_avc1_fields_preserved(sample_entry: Mp4SampleEntryAvc1, sample_data: bytes) -> None:
    """AVC1 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryAvc1)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.avc_profile_indication == sample_entry.avc_profile_indication
    assert restored.avc_level_indication == sample_entry.avc_level_indication
    assert restored.profile_compatibility == sample_entry.profile_compatibility
    assert restored.sps_data == sample_entry.sps_data
    assert restored.pps_data == sample_entry.pps_data


@given(sample_entry=st_hev1_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_hev1_fields_preserved(sample_entry: Mp4SampleEntryHev1, sample_data: bytes) -> None:
    """HEV1 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryHev1)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.general_profile_idc == sample_entry.general_profile_idc
    assert restored.general_level_idc == sample_entry.general_level_idc
    assert restored.nalu_types == sample_entry.nalu_types
    assert restored.nalu_data == sample_entry.nalu_data


@given(sample_entry=st_hvc1_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_hvc1_fields_preserved(sample_entry: Mp4SampleEntryHvc1, sample_data: bytes) -> None:
    """HVC1 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryHvc1)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.general_profile_idc == sample_entry.general_profile_idc
    assert restored.general_level_idc == sample_entry.general_level_idc
    assert restored.nalu_types == sample_entry.nalu_types
    assert restored.nalu_data == sample_entry.nalu_data


@given(sample_entry=st_av01_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_av01_fields_preserved(sample_entry: Mp4SampleEntryAv01, sample_data: bytes) -> None:
    """AV01 サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

    mux_sample = Mp4MuxSample(
        track_kind="video",
        sample_entry=sample_entry,
        keyframe=True,
        timescale=1000000,
        duration=33333,
        data=sample_data,
    )
    muxer.append_sample(mux_sample)
    muxer.finalize()

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryAv01)

    assert restored.width == sample_entry.width
    assert restored.height == sample_entry.height
    assert restored.seq_profile == sample_entry.seq_profile
    assert restored.seq_level_idx_0 == sample_entry.seq_level_idx_0
    assert restored.config_obus == sample_entry.config_obus


@given(sample_entry=st_opus_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_opus_fields_preserved(sample_entry: Mp4SampleEntryOpus, sample_data: bytes) -> None:
    """Opus サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

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

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryOpus)

    assert restored.channel_count == sample_entry.channel_count
    assert restored.sample_rate == sample_entry.sample_rate
    assert restored.pre_skip == sample_entry.pre_skip
    assert restored.output_gain == sample_entry.output_gain


@given(sample_entry=st_mp4a_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_mp4a_fields_preserved(sample_entry: Mp4SampleEntryMp4a, sample_data: bytes) -> None:
    """MP4A サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

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

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryMp4a)

    assert restored.channel_count == sample_entry.channel_count
    assert restored.sample_rate == sample_entry.sample_rate
    assert restored.dec_specific_info == sample_entry.dec_specific_info


@given(sample_entry=st_flac_sample_entry(), sample_data=st_sample_data)
@settings(max_examples=100)
def prop_flac_fields_preserved(sample_entry: Mp4SampleEntryFlac, sample_data: bytes) -> None:
    """FLAC サンプルエントリーのフィールドが保持される"""
    output_buffer = io.BytesIO()
    muxer = Mp4FileMuxer(output_buffer)

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

    output_buffer.seek(0)
    demuxer = Mp4FileDemuxer(output_buffer)
    demux_sample = next(demuxer)

    restored = demux_sample.sample_entry
    assert isinstance(restored, Mp4SampleEntryFlac)

    assert restored.channel_count == sample_entry.channel_count
    assert restored.sample_rate == sample_entry.sample_rate
    assert restored.streaminfo_data == sample_entry.streaminfo_data
