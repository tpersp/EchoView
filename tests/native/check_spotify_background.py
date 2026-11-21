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
    from PySide6.QtWidgets import QApplication, QWidget
    from echoview.spotify_card import SpotifyCard
    from echoview.spotify_client import Playback
    from echoview import viewer
    app=QApplication([])
    # Paint through a parent window, not card.grab(): direct grabs can force
    # stylesheet backgrounds that a custom QWidget never paints on screen.
    parent=QWidget();parent.resize(640,360);parent.setStyleSheet('background-color:black;')
    child=SpotifyCard(parent);child.setGeometry(0,0,640,360)
    child.set_track('',{'song':'Fixture','art_colors':('#ff0000','#0000ff')},
                    {'spotify_background_mode':'gradient','spotify_background_dim':50},1)
    parent.show();app.processEvents()
    parent_image=parent.grab().toImage()
    assert parent_image.pixelColor(2,2).red()>120
    assert parent_image.pixelColor(637,2).blue()>120
    child.set_track('',{'art_colors':('#ff0000','#0000ff')},
                    {'spotify_background_mode':'artwork','spotify_background_dim':50},1)
    app.processEvents()
    assert parent.grab().toImage().pixelColor(637,2).red()>120
    parent.close()
    path=Path(directory)/'art.png';Image.new('RGB',(64,64),'orange').save(path)
    info={'song':'Fixture','artist':'Artist','art_colors':('#ff0000','#0000ff')}
    card=SpotifyCard();card.resize(1280,720);card.show()
    for layout in ('album_card','poster'):
        for width,height in ((1280,720),(720,1280)):
            card.resize(width,height)
            for mode in ('black','artwork','gradient','blurred'):
                options={'spotify_layout':layout,'spotify_background_mode':mode,'spotify_background_dim':50}
                card.set_track(str(path),info,options,1)
                app.processEvents()
                image=card.grab().toImage()
                left=image.pixelColor(2,2);right=image.pixelColor(image.width()-3,2)
                if mode=='black':assert left.name()=='#000000'
                elif mode=='blurred':assert 120<=left.red()<=129 and 75<=left.green()<=90 and left.blue()<5
                else:assert left.red()>120 and left.blue()<5
                if mode=='gradient':assert right.blue()>120 and right.red()<5
    from echoview.spotify_background import BlurredArtwork
    from PySide6.QtCore import QSize
    cached=BlurredArtwork()
    result=cached.get(card.pixmap,50,QSize(640,360))
    assert cached.image.width()<=96 and cached.image.height()<=96
    assert cached.get(card.pixmap,50,QSize(640,360)).cacheKey()==result.cacheKey()
    assert cached.get(card.pixmap,80,QSize(640,360)).toImage().pixelColor(2,2).red()<60
    from PySide6.QtGui import QPixmap
    assert cached.get(QPixmap(),50,QSize(640,360)).isNull()
    assert cached.image is None and cached.output is None
    from PIL import ImageDraw
    split=Image.new('RGB',(96,96),'red');ImageDraw.Draw(split).rectangle((48,0,95,95),fill='blue')
    split_path=Path(directory)/'split.png';split.save(split_path)
    softened=cached.get(QPixmap(str(split_path)),0,QSize(96,96)).toImage()
    centre=softened.pixelColor(48,48)
    assert centre.red()>80 and centre.blue()>80, 'Cover boundary must be genuinely blurred'
    assert softened.pixelColor(2,2).red()>240

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
    for mode,dim in (('blurred',50),('artwork',30),('gradient',80),('black',65)):
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
