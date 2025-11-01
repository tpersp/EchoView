import os
import pathlib

import pytest

from echoview import embed_utils
from echoview import utils, config
from echoview.web import routes


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "viewerconfig.json"
    monkeypatch.setattr(utils, "CONFIG_PATH", str(cfg_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    monkeypatch.setattr(routes, "CONFIG_PATH", str(cfg_path))
    utils.init_config()
    return cfg_path


def test_refresh_embed_updates_config_and_saved_sites(temp_config, monkeypatch):
    cfg = utils.load_config()
    display_name = next(iter(cfg["displays"]))
    cfg["displays"][display_name]["web_url"] = ""
    cfg["displays"][display_name]["embed_metadata"] = None
    test_url = "https://youtu.be/demo123"
    cfg["saved_websites"] = [test_url]
    utils.save_config(cfg)

    def fake_classify(url):
        assert url == test_url
        return embed_utils.EmbedMetadata(
            embed_type="youtube",
            original_url=url,
            canonical_url="https://www.youtube-nocookie.com/embed/demo123",
            provider="YouTube",
            title="Demo Clip",
            content_type="video",
            video_id="demo123",
            playlist_id=None,
            start_seconds=None,
            thumbnail_url="https://img.youtube.com/vi/demo123/default.jpg",
        )

    monkeypatch.setattr(embed_utils, "classify_url", fake_classify)

    class DummyRequest:
        def __init__(self, payload):
            self._payload = payload

        def get_json(self, silent=True):
            return self._payload

    captured = {}

    def fake_jsonify(data):
        captured["data"] = data
        return data

    monkeypatch.setattr(routes, "request", DummyRequest({"display": display_name, "url": test_url}))
    monkeypatch.setattr(routes, "jsonify", fake_jsonify)

    response = routes.refresh_embed()
    assert captured["data"]["ok"] is True
    assert captured["data"]["metadata"]["title"] == "Demo Clip"

    updated = utils.load_config()
    saved_entries = updated["saved_websites"]
    assert isinstance(saved_entries[0], dict)
    assert saved_entries[0]["url"] == test_url
    assert saved_entries[0]["metadata"]["canonical_url"].startswith("https://www.youtube-nocookie.com/embed/demo123")
    embed_meta = updated["displays"][display_name]["embed_metadata"]
    assert embed_meta["embed_type"] == "youtube"
