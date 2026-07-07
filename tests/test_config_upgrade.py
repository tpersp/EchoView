from echoview import utils


def test_upgrade_config_adds_missing_display_keys_without_overwriting_existing():
    cfg = {
        "displays": {
            "HDMI-1": {
                "mode": "web_page",
                "youtube_mute": False,
            }
        }
    }

    changed = utils.upgrade_config(cfg)

    display = cfg["displays"]["HDMI-1"]
    assert changed is True
    assert display["embed_metadata"] is None
    assert display["web_use_external_browser"] is False
    assert display["youtube_autoplay"] is True
    assert display["youtube_mute"] is False
    assert display["youtube_captions"] is False
    assert display["youtube_quality"] == "default"
    assert display["aspect_filter"] == "any"


def test_upgrade_config_is_noop_when_display_config_is_current():
    cfg = {
        "displays": {
            "HDMI-1": {
                "embed_metadata": {"embed_type": "iframe"},
                "web_use_external_browser": True,
                "youtube_autoplay": False,
                "youtube_mute": False,
                "youtube_captions": True,
                "youtube_quality": "hd1080",
                "aspect_filter": "portrait",
            }
        }
    }

    changed = utils.upgrade_config(cfg)

    assert changed is False
    assert cfg["displays"]["HDMI-1"]["youtube_quality"] == "hd1080"
