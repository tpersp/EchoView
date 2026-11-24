from collections import OrderedDict

import pytest

from echoview import presentation as ui


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "20.1", "five", None])
def test_invalid_margin_rejected(value):
    with pytest.raises(ValueError, match="finite percentage"):
        ui.safe_area_settings({"left": value}, strict=True)


def test_safe_area_geometry_for_pal_and_hdmi():
    assert ui.safe_bounds(720, 576, {edge: 5 for edge in ui.EDGES}) == (36, 29, 648, 518)
    assert ui.safe_bounds(1920, 1080, {}) == (0, 0, 1920, 1080)
    assert ui.safe_bounds(720, 480, {"left": 10, "right": 20, "top": 5}) == (72, 24, 504, 456)
    assert ui.safe_bounds(1, 1, {edge: 20 for edge in ui.EDGES}) == (0, 0, 1, 1)


@pytest.mark.parametrize("position", ["top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right", "center"])
def test_overlays_are_contained_with_nonzero_origin_and_long_text(position):
    x, y, width, height = ui.overlay_bounds((36, 29, 648, 518), (1200, 800), position, 10)
    assert x >= 46 and y >= 39
    assert x + width <= 36 + 648 - 10
    assert y + height <= 29 + 518 - 10


def test_pixel_aspect_text_width_correction():
    assert ui.text_stretch(1) == 100
    assert ui.text_stretch(16 / 15) == 94
    assert ui.text_stretch(8 / 9) == 112


def test_pi3_profile_is_opt_in_and_does_not_mutate_global_settings():
    cfg = {"gui": {"background_blur_radius": 20}, "preload_count": 1, "cache_capacity": 15}
    normal, low = ui.resource_settings("standard", cfg), ui.resource_settings("pi3", cfg)
    assert normal["blur_radius"] == 20
    assert normal["cache_capacity"] == 15 and normal["preload_count"] == 1
    assert low["blur_radius"] == low["preload_count"] == 0
    assert low["cache_budget"] == 32 * 1024 * 1024
    assert low["cache_capacity"] == 4
    assert cfg["gui"]["background_blur_radius"] == 20


@pytest.mark.parametrize("size", [(6000, 4000), (4000, 6000), (100000, 50), (100, 100)])
def test_decoded_image_budget_preserves_proportions(size):
    policy = ui.resource_settings("pi3", {})
    width, height = ui.decode_size(*size, policy)
    assert 0 < width <= size[0] and 0 < height <= size[1]
    assert width * height <= policy["decode_pixels"]
    assert max(width, height) <= policy["decode_side"]
    if min(size) >= 100:
        assert width / height == pytest.approx(size[0] / size[1], rel=0.005)


def test_cache_evicts_oldest_by_bytes_and_count_and_handles_disabled_cache():
    cache = OrderedDict((name, {"bytes": size}) for name, size in (("old", 12), ("middle", 9), ("new", 8)))
    assert ui.trim_image_cache(cache, 10, 20) == 17
    assert list(cache) == ["middle", "new"]
    assert ui.trim_image_cache(cache, 1, 20) == 8
    assert list(cache) == ["new"]
    assert ui.trim_image_cache(cache, 0, 20) == 0 and not cache


def test_external_video_safe_area_and_low_resource_options():
    flags = ui.player_presentation_flags({"safe_area": {"left": 5, "bottom": 10}, "resource_profile": "pi3"})
    assert "--video-margin-ratio-left=0.05" in flags
    assert "--video-margin-ratio-bottom=0.1" in flags
    assert "--vd-lavc-threads=2" in flags
    assert not any(flag.startswith("--ytdl-format=") for flag in flags)
    assert ui.player_presentation_flags({}) == []
