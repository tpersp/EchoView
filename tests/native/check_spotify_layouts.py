"""Native layouts with synthetic artwork. No Spotify API or NAS access."""
from pathlib import Path
import os
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-layouts-') as directory:
    os.environ['VIEWER_HOME'] = directory
    os.environ['IMAGE_DIR'] = directory
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PIL import Image, ImageDraw
    from PySide6.QtWidgets import QApplication
    from echoview.spotify_card import SpotifyCard
    from echoview.spotify_client import Playback
    from echoview import viewer
    image = Image.new('RGB',(600,600),'#162d45')
    draw = ImageDraw.Draw(image)
    draw.ellipse((70,70,530,530), fill='#78d8bc')
    draw.ellipse((180,180,420,420),fill='#162d45')
    draw.ellipse((270,270,330,330),fill='#edf2f7')
    path = Path(directory)/'art.png'; image.save(path)
    app = QApplication([])
    card = SpotifyCard()
    info = {'song':'Midnight in Motion','artist':'The Echoes','album':'After Hours','device_name':'Living room'}
    for layout in ('album_card','poster'):
        for width,height in ((1280,720),(720,1280),(640,480)):
            card.resize(width,height); card.show()
            card.set_track(str(path),info,{'spotify_layout':layout,'spotify_show_device':True},1.0)
            assert card.labels[3].text() == 'Playing on Living room'
            app.processEvents()
            assert card.rect().contains(card.artwork.geometry())
            for label in card.labels:
                assert card.rect().contains(label.geometry())
            assert not card.artwork.pixmap().isNull()
            if width==1280:
                card.grab().save(f'/tmp/echoview-{layout}-preview.png')
    card.set_track('',info,{'spotify_layout':'poster'},1.0)
    assert not card.labels[3].text()
    card.set_track('',{}, {'spotify_show_device':True},1.0)
    assert not card.labels[3].text()
    assert card.artwork.text() == 'Artwork unavailable'
    card.set_track(str(path),{'song':'<b>Plain text title</b>','artist':'Artist '*30,'album':'Album '*30},
                   {'spotify_layout':'album_card','rotate':90},1.25)
    app.processEvents()
    card.close()
    display={'mode':'calibration','spotify_show_progress':True,'fallback_mode':'none'}
    viewer.load_config=lambda:{'displays':{'fixture':display}}
    window=viewer.DisplayWindow('fixture',display,app.primaryScreen())
    window.current_mode='spotify'
    gif = Path(directory)/'fallback.gif'
    Image.new('RGB',(32,32),'red').save(gif,save_all=True,append_images=[Image.new('RGB',(32,32),'blue')],duration=100,loop=0)
    from PySide6.QtGui import QMovie
    movie = QMovie(str(gif)); movie.start()
    window.current_movie = movie
    for layout in ('album_card','poster','classic'):
        window.disp_cfg['spotify_layout']=layout
        window.disp_cfg['spotify_show_device']=True
        window.spotify_fetch_id=window.spotify_fetch_pending=1
        window.handle_spotify_result(1,Playback('playing',song='Fixture',artist='Artist',album='Album',device_name='Living room',
                                    art_path=str(path),progress_ms=1000,duration_ms=180000,
                                    fetched_time=time.monotonic(),next_poll_at=time.monotonic()+60))
        app.processEvents()
        assert window.current_movie is None
        assert movie.state() == QMovie.NotRunning
        assert window.spotify_card.isVisible() == (layout!='classic')
        assert window.foreground_label.isVisible() == (layout=='classic')
        if layout=='classic':
            assert 'Playing on Living room' in window.spotify_info_label.text()
        else:
            assert window.spotify_card.labels[3].text() == 'Playing on Living room'
        window.disp_cfg['spotify_show_device']=False
        window.render_spotify(str(path))
        if layout=='classic':
            assert 'Playing on Living room' not in window.spotify_info_label.text()
        else:
            assert not window.spotify_card.labels[3].text()
    window.disp_cfg['spotify_layout']='album_card'; window.render_spotify(str(path))
    window.spotify_fetch_id=window.spotify_fetch_pending=2
    window.handle_spotify_result(2,Playback('paused',next_poll_at=time.monotonic()+60))
    assert not window.spotify_card.isVisible()
    assert window.foreground_label.isVisible()
    window.close(); app.processEvents()
    print('Native layouts passed: landscape/portrait/4:3, missing artwork, long text, rotation, classic switching and fallback cleanup.')
