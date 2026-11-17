"""Check selection with real Qt; creates only temporary media, never starts playback.

    QT_QPA_PLATFORM=offscreen python tests/native/check_single_video.py
"""
import os
from pathlib import Path
import sys
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix='echoview-single-video-') as temp:
        os.environ['VIEWER_HOME'] = temp
        os.environ['IMAGE_DIR'] = temp
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from PySide6.QtWidgets import QApplication
        from echoview import viewer

        clip = Path(temp) / 'selected.mp4'
        other = Path(temp) / 'other.mp4'
        clip.touch()
        other.touch()
        app = QApplication([])
        display = {'mode': 'calibration', 'aspect_filter': 'any'}
        cfg = {'resource_profile': 'standard', 'displays': {'fixture': display}}
        viewer.load_config = lambda: cfg
        window = viewer.DisplayWindow('fixture', display, app.primaryScreen())
        window.current_mode = 'videos'
        window.disp_cfg.update(mode='videos', specific_video=clip.name)
        window.build_local_image_list()
        assert window.image_list == [str(clip)]
        assert window.build_mpv_command(str(clip))[-1] == str(clip)
        window.disp_cfg['specific_video'] = ''
        window.build_local_image_list()
        assert set(window.image_list) == {str(clip), str(other)}
        window.disp_cfg['specific_video'] = 'missing.mp4'
        window.build_local_image_list()
        assert window.image_list == []
        window.close()
        app.processEvents()
        print('Real Qt: single-video selection, whole-folder restoration and missing-file handling passed; playback was not started.')


if __name__ == '__main__':
    main()
