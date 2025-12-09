import os
import pathlib

from echoview import utils


def test_get_subfolders_ignores_leading_underscore(tmp_path):
    (tmp_path / "Photos").mkdir()
    (tmp_path / "_thumbnails").mkdir()
    (tmp_path / "Trips").mkdir()

    # Point IMAGE_DIR to the temp path for this test
    old_image_dir = utils.IMAGE_DIR
    utils.IMAGE_DIR = str(tmp_path)
    try:
        folders = utils.get_subfolders()
        assert "Photos" in folders
        assert "Trips" in folders
        assert "_thumbnails" not in folders
    finally:
        utils.IMAGE_DIR = old_image_dir


def test_count_files_ignored_folder(tmp_path):
    hidden = tmp_path / "_sys"
    hidden.mkdir()
    (hidden / "a.jpg").write_text("x")
    assert utils.count_files_in_folder(hidden) == 0
