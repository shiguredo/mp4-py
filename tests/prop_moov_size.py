"""
estimate_maximum_moov_box_size の property-based testing
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from mp4 import estimate_maximum_moov_box_size


@given(
    audio_count=st.integers(min_value=0, max_value=10000),
    video_count=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=200)
def prop_estimate_moov_size_non_negative(audio_count: int, video_count: int) -> None:
    """moov サイズの推定値は常に非負"""
    size = estimate_maximum_moov_box_size(audio_count, video_count)
    assert size >= 0


@given(
    audio_count=st.integers(min_value=0, max_value=10000),
    video_count=st.integers(min_value=0, max_value=10000),
    delta=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=200)
def prop_estimate_moov_size_monotonic(audio_count: int, video_count: int, delta: int) -> None:
    """サンプル数が増えると推定サイズも増加（単調性）"""
    size_base = estimate_maximum_moov_box_size(audio_count, video_count)
    size_more_audio = estimate_maximum_moov_box_size(audio_count + delta, video_count)
    size_more_video = estimate_maximum_moov_box_size(audio_count, video_count + delta)

    assert size_more_audio >= size_base
    assert size_more_video >= size_base


@given(
    audio_count=st.integers(min_value=0, max_value=10000),
    video_count=st.integers(min_value=0, max_value=10000),
    subtitle_count=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=200)
def prop_estimate_moov_size_three_tracks(
    audio_count: int, video_count: int, subtitle_count: int
) -> None:
    """3 トラック指定の推定値は常に非負で、2 トラックに字幕を足すと増加する"""
    size_three = estimate_maximum_moov_box_size(audio_count, video_count, subtitle_count)
    assert size_three >= 0

    # 字幕サンプル数を加えると推定サイズも増加（単調性）
    size_no_subtitle = estimate_maximum_moov_box_size(audio_count, video_count)
    assert size_three >= size_no_subtitle
