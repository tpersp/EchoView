import json
from pathlib import Path

import pytest

from echoview import utils


def test_save_config_publishes_complete_json(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "dark"}')
    monkeypatch.setattr(utils, "CONFIG_PATH", str(path))
    replace = utils.os.replace

    def checked_replace(src, dst):
        assert json.loads(path.read_text()) == {"theme": "dark"}
        assert json.loads(Path(src).read_text()) == {"theme": "light"}
        replace(src, dst)

    monkeypatch.setattr(utils.os, "replace", checked_replace)
    utils.save_config({"theme": "light"})
    assert json.loads(path.read_text()) == {"theme": "light"}
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("failure", ["serialization", "sync", "replace"])
def test_failed_save_preserves_existing_config(monkeypatch, tmp_path, failure):
    path = tmp_path / "settings.json"
    original = '{"theme": "dark"}'
    path.write_text(original)
    monkeypatch.setattr(utils, "CONFIG_PATH", str(path))

    def fail(*args):
        raise OSError("disk failure")

    cfg = {"theme": object()} if failure == "serialization" else {"theme": "light"}
    if failure == "sync":
        monkeypatch.setattr(utils.os, "fsync", fail)
    elif failure == "replace":
        monkeypatch.setattr(utils.os, "replace", fail)
    with pytest.raises((TypeError, OSError)):
        utils.save_config(cfg)
    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]
