"""Native static artwork backgrounds and in-place changes; synthetic media only."""
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-art-background-') as directory:
    os.environ['VIEWER_HOME']=os.environ['IMAGE_DIR']=directory
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    from echoview.spotify_card import SpotifyCard
    from echoview.spotify_client import Playback
    from echoview import viewer
    app=QApplication([])
    path=Path(directory)/'art.png';Image.new('RGB',(64,64),'orange').save(path)
    info={'song':'Fixture','artist':'Artist','art_colors':('#ff0000','#0000ff')}
    card=SpotifyCard();card.resize(1280,720);card.show()
    for layout in ('album_card','poster'):
        for width,height in ((1280,720),(720,1280)):
            card.resize(width,height)
            for mode in ('black','artwork','gradient'):
                options={'spotify_layout':layout,'spotify_background_mode':mode,'spotify_background_dim':50}
                card.set_track(str(path),info,options,1)
                app.processEvents()
                image=card.grab().toImage()
                left=image.pixelColor(2,2);right=image.pixelColor(image.width()-3,2)
                if mode=='black':assert left.name()=='#101620'
                else:assert left.red()>120 and left.blue()<5
                if mode=='gradient':assert right.blue()>120 and right.red()<5
    key=card.pixmap.cacheKey()
    card.set_track(str(path),info,options,1)
    assert card.pixmap.cacheKey()==key
    card.set_track('',{},dict(options,spotify_background_mode='gradient'),1)
    assert card.artwork.text()=='Artwork unavailable'
    card.close()

    display={'mode':'calibration','spotify_show_progress':True,'fallback_mode':'none'}
    cfg={'displays':{'fixture':display},'gui':{'background_blur_radius':0}}
    viewer.load_config=lambda:cfg
    window=viewer.DisplayWindow('fixture',display,app.primaryScreen())
    window.current_mode='spotify';window.disp_cfg['spotify_background_mode']='gradient'
    window.disp_cfg['spotify_background_dim']=50
    window.spotify_fetch_id=window.spotify_fetch_pending=1
    window.handle_spotify_result(1,Playback('playing',song='Fixture',art_path=str(path),art_colors=info['art_colors'],
        progress_ms=24000,duration_ms=194000,fetched_time=time.monotonic(),next_poll_at=time.monotonic()+60))
    deadline=time.monotonic()+3
    while window.current_pixmap is None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.005)
    assert window.current_pixmap is not None
    identity=window.winId();timeline=window.spotify_timeline;timer=window.slideshow_timer.interval();pixmap=window.current_pixmap.cacheKey()
    assert window.bg_label.pixmap().isNull()
    image=window.bg_label.grab().toImage()
    assert image.pixelColor(2,2).red()>120 and image.pixelColor(image.width()-3,2).blue()>120
    for mode,dim in (('artwork',30),('gradient',80),('black',65)):
        window.apply_spotify_visual_settings(dict(window.disp_cfg,spotify_background_mode=mode,spotify_background_dim=dim))
        assert window.winId()==identity and window.spotify_timeline is timeline
        assert window.slideshow_timer.interval()==timer and window.current_pixmap.cacheKey()==pixmap
    assert not window.bg_label.pixmap().isNull(), 'Existing classic background must be restored'
    window.disp_cfg['spotify_layout']='album_card'
    window.apply_spotify_visual_settings(dict(window.disp_cfg,spotify_background_mode='gradient'))
    assert window.spotify_card.isVisible()
    assert 'qlineargradient' in window.spotify_card.background_key
    from echoview.preview_capture import capture_background
    width,height,rgba=capture_background(window)
    captured=Image.frombytes('RGBA',(width,height),rgba)
    assert captured.getpixel((2,2))[0]>50 and captured.getpixel((width-3,2))[2]>50
    window.spotify_fetch_id=window.spotify_fetch_pending=2
    window.handle_spotify_result(2,Playback('paused',next_poll_at=time.monotonic()+60))
    assert not window.spotify_card.isVisible()
    assert 'qlineargradient' not in window.bg_label.styleSheet()
    window.close()
    print('Spotify backgrounds: all layouts/orientations, real gradient pixels, bounded artwork reuse, missing cover, live changes and fallback cleanup passed.')
