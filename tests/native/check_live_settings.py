"""Native in-place Spotify apply with request/ack; no API or real media."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import tempfile
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-live-') as directory:
    os.environ['VIEWER_HOME']=directory; os.environ['IMAGE_DIR']=directory
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    from echoview import viewer
    from echoview.spotify_client import Playback
    from echoview.live_settings import request_update,VisualSettingsReceiver
    cfg={'displays':{'fixture':{'mode':'calibration','spotify_show_progress':True,'fallback_mode':'none'}}}
    viewer.load_config=lambda:cfg
    app=QApplication([])
    window=viewer.DisplayWindow('fixture',cfg['displays']['fixture'],app.primaryScreen())
    window.current_mode='spotify'
    path=Path(directory)/'art.png'; Image.new('RGB',(64,64),'teal').save(path)
    window.spotify_fetch_id=window.spotify_fetch_pending=1
    window.handle_spotify_result(1,Playback('playing',song='Fixture',art_path=str(path),duration_ms=180000,
                                progress_ms=42000,fetched_time=time.monotonic(),next_poll_at=time.monotonic()+60))
    identity=window.winId(); timeline=window.spotify_timeline
    timer=window.slideshow_timer.interval(); fid=window.spotify_fetch_id
    gui=SimpleNamespace(window_by_connector={'fixture':window},cfg=cfg)
    receiver=VisualSettingsReceiver(directory,lambda req:viewer.EchoViewGUI._apply_live_visual_request(gui,req))
    def apply(config,names):
        results=[]
        worker=threading.Thread(target=lambda:results.append(request_update(directory,config,names,timeout=2)))
        worker.start()
        while worker.is_alive(): receiver.poll(); app.processEvents(); time.sleep(.01)
        worker.join(); return results[0]
    cfg['displays']['fixture'].update(mode='spotify',spotify_layout='poster',spotify_font_size=24)
    assert apply(cfg,['fixture'])
    assert window.spotify_card.isVisible()
    assert window.winId()==identity and window.spotify_fetch_id==fid
    assert window.spotify_timeline is timeline
    assert window.slideshow_timer.interval()==timer
    assert window.spotify_card.path==str(path)
    assert window.spotify_info['song']=='Fixture'
    cfg['displays']['fixture'].update(spotify_layout='classic',spotify_show_progress=False)
    assert apply(cfg,['fixture'])
    assert not window.spotify_card.isVisible() and not window.spotify_progress_bar.isVisible()
    assert not window.spotify_progress_timer.isActive()
    assert window.winId()==identity and window.spotify_timeline is timeline
    stale=deepcopy(cfg); stale['displays']['fixture']['spotify_font_size']=99
    assert not apply(stale,['fixture'])
    assert window.disp_cfg['spotify_font_size']==24
    assert not apply(cfg,['missing'])
    # While paused, changing presentation must not rotate the fallback image.
    window.spotify_info=None
    before=window.last_displayed_path
    cfg['displays']['fixture']['spotify_font_size']=28
    assert apply(cfg,['fixture'])
    assert window.last_displayed_path==before
    window.close(); app.processEvents()
    print('Native live apply passed: same window/timeline/artwork/poll timer, layout/progress changes, stale request rejection and paused fallback preservation.')
