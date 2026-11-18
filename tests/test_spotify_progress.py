import pytest
from echoview.spotify_progress import ProgressTimeline


def test_progress_continues_locally_without_more_samples():
    p = ProgressTimeline()
    p.sample('a', 1000, 180000, 10, 10)
    assert p.position(10.05) == pytest.approx(1050)
    assert p.position(13) == 4000
    assert p.position(1000) == 180000


@pytest.mark.parametrize('reported', [5500, 6500])
def test_small_drift_is_corrected_without_a_jump_or_backwards_motion(reported):
    p = ProgressTimeline()
    p.sample('a', 1000, 180000, 10, 10)
    before = p.position(15)
    p.sample('a', reported, 180000, 15, 15)
    assert p.position(15) == before
    values = [p.position(15 + i / 20) for i in range(41)]
    assert values == sorted(values)
    assert values[-1] == reported + 2000


def test_seeks_and_new_tracks_snap_without_blending_unrelated_positions():
    p = ProgressTimeline()
    p.sample('a', 20000, 180000, 10, 10)
    p.sample('a', 90000, 180000, 15, 15)
    assert p.position(15) == 90000
    p.sample('b', 100, 200000, 16, 16)
    assert p.position(16) == 100
    p.sample('b', 100, 200000, 20, 20)  # Seek backwards.
    assert p.position(20) == 100
    p.clear()
    assert p.position(100) == 0


def test_shared_cached_sample_does_not_restart_correction():
    p = ProgressTimeline()
    p.sample('a', 1000, 180000, 10, 10)
    p.sample('a', 5500, 180000, 15, 15)
    p.sample('a', 5500, 180000, 15, 16)
    assert p.position(17) == 7500


def test_delayed_artwork_response_is_projected_to_current_time():
    p = ProgressTimeline()
    p.sample('a', 1000, 180000, 10, 12)
    assert p.position(12) == 3000
