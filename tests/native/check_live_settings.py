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
    def apply(config,names,kind='spotify'):
        results=[]
        worker=threading.Thread(target=lambda:results.append(request_update(directory,config,names,timeout=2,kind=kind)))
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
    # Clock updates apply independently of media mode and Spotify presentation.
    gif=Path(directory)/'playing.gif'
    Image.new('RGB',(32,32),'red').save(gif,save_all=True,append_images=[Image.new('RGB',(32,32),'blue')],duration=100,loop=0)
    from PySide6.QtGui import QMovie
    movie=QMovie(str(gif)); window.current_movie=movie
    window.foreground_label.setMovie(movie); movie.start()
    for mode in ('random_image','videos','web_page','spotify'):
        window.current_mode=mode
        if mode=='spotify':
            window.spotify_card.set_track(str(path),{'song':'Fixture'},{'spotify_layout':'album_card'},1)
            window.spotify_card.show()
        else:
            window.spotify_card.hide()
        cfg['displays']['fixture']['overlay']={'clock_enabled':True,'clock_font_size':32,
            'clock_position':'top-right','auto_negative_font':True,'font_color':'#123456'}
        before=window.last_displayed_path
        assert apply(cfg,['fixture'],kind='overlay')
        assert window.clock_label.isVisible() and window.clock_label.font().pixelSize()==32
        assert window.clock_label.useDifference is True
        assert window.current_mode==mode and window.winId()==identity
        assert window.current_movie is movie and movie.state()==QMovie.Running
        assert window.last_displayed_path==before and window.spotify_timeline is timeline
        cfg['displays']['fixture']['overlay'].update(clock_enabled=False,auto_negative_font=False,clock_font_size=28)
        assert apply(cfg,['fixture'],kind='overlay')
        assert not window.clock_label.isVisible() and not window.clock_label.useDifference
        assert '#123456' in window.clock_label.styleSheet()
        assert window.slideshow_timer.interval()==timer
    from datetime import datetime as RealDateTime
    class Clock:
        value=RealDateTime(2026,1,1,12,0,0)
        @classmethod
        def now(cls): return cls.value
    viewer.datetime=Clock
    cfg['displays']['fixture']['overlay'].update(clock_enabled=True,clock_format='12',clock_show_seconds=False,clock_font_size=28,clock_position='top-right')
    assert apply(cfg,['fixture'],kind='overlay')
    assert window.clock_label.text()=='12:00 PM'
    Clock.value=RealDateTime(2026,1,1,9,5,6);window.update_clock()
    width=window.clock_label.width();right=window.clock_label.geometry().right()
    assert window.clock_label.text()=='9:05 AM'
    Clock.value=RealDateTime(2026,1,1,10,5,6);window.update_clock()
    assert window.clock_label.text()=='10:05 AM' and window.clock_label.width()>width
    assert abs(window.clock_label.geometry().right()-right)<=1
    cfg['displays']['fixture']['overlay'].update(clock_format='24',clock_show_seconds=True)
    Clock.value=RealDateTime(2026,1,1,0,5,6)
    assert apply(cfg,['fixture'],kind='overlay')
    assert window.clock_label.text()=='00:05:06'
    assert window.winId()==identity and window.slideshow_timer.interval()==timer
    cfg['displays']['fixture']['overlay'].update(clock_blink_separators=True,clock_show_seconds=False)
    Clock.value=RealDateTime(2026,1,1,0,5,6,0)
    assert apply(cfg,['fixture'],kind='overlay')
    assert window.clock_timer.interval()==500 and window.clock_label.separators_visible
    text=window.clock_label.text();geometry=window.clock_label.geometry()
    Clock.value=RealDateTime(2026,1,1,0,5,6,500000);window.update_clock()
    assert not window.clock_label.separators_visible
    assert window.clock_label.text()==text and window.clock_label.geometry()==geometry
    cfg['displays']['fixture']['overlay']['clock_blink_separators']=False
    assert apply(cfg,['fixture'],kind='overlay')
    assert window.clock_timer.interval()==1000 and window.clock_label.separators_visible
    assert window.slideshow_timer.interval()==timer and window.winId()==identity
    cfg['displays']['disconnected']={'mode':'random_image'}
    assert apply(cfg,['fixture','disconnected'],kind='overlay')
    assert not apply(cfg,['disconnected'],kind='overlay')
    assert not apply(cfg,['fixture'],kind='unknown')
    movie.stop(); window.current_movie=None; window.foreground_label.setMovie(None)
    window.close(); app.processEvents()
    print('Native clock live apply passed across images/video/web/Spotify: enable, disable, size, contrast, color, stable window and unchanged media/timers.')
    print('Native live apply passed: same window/timeline/artwork/poll timer, layout/progress changes, stale request rejection and paused fallback preservation.')
