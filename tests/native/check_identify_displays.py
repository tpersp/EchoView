"""Transient labels and live playback with real Qt and generated media only."""
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='ev-identify-') as directory:
    os.environ['VIEWER_HOME']=os.environ['IMAGE_DIR']=directory
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PIL import Image
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from echoview import viewer
    from echoview.web.spotify_auth import fingerprint
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    display={'mode':'calibration'}
    cfg={'displays':{'fixture':display,'offline':{'mode':'videos'}}}
    viewer.load_config=lambda:cfg
    window=viewer.DisplayWindow('fixture',display,app.primaryScreen())
    path=Path(directory)/'generated.gif'
    frames=[Image.new('RGB',(48,48),color) for color in ('red','blue','green')]
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=40,loop=0)
    window.show_foreground_image(str(path));movie=window.current_movie
    changes=[];movie.frameChanged.connect(changes.append)
    gui=SimpleNamespace(window_by_connector={'fixture':window},cfg=cfg)
    request={'kind':'identify','config':fingerprint(cfg),'displays':['fixture','offline']}
    assert viewer.EchoViewGUI._apply_live_visual_request(gui,request)
    badge=window.identification_badge
    assert badge.isVisible() and badge.text()=='fixture'
    assert badge.windowFlags() & Qt.WindowStaysOnTopHint
    assert badge.windowFlags() & Qt.WindowTransparentForInput
    assert badge.testAttribute(Qt.WA_ShowWithoutActivating)
    assert app.primaryScreen().geometry().contains(badge.geometry())
    assert badge.timer.isActive()
    window.identify_display();assert window.identification_badge is badge
    until=time.monotonic()+5.5
    while time.monotonic()<until:app.processEvents();time.sleep(.01)
    assert not badge.isVisible() and not badge.timer.isActive()
    assert window.current_movie is movie and len(changes)>40
    assert window.current_mode=='calibration' and cfg['displays']['fixture']==display
    window.identify_display();assert badge.isVisible()
    window.close();app.processEvents()
    assert not badge.isVisible() and not badge.timer.isActive()
    print('Native identification: correct screen/name, topmost input-transparent label, repeated request reuse, five-second expiry, GIF continuity and close cleanup passed.')

# Exercise installation/startup of the second request channel too.
import subprocess
subprocess.run([sys.executable,'-c',"""
import os,tempfile,shutil
with tempfile.TemporaryDirectory(prefix='ev-identify-start-') as home:
 os.environ['VIEWER_HOME']=os.environ['IMAGE_DIR']=home
 from echoview import viewer
 from echoview.spotify_state import state_directory
 viewer.load_config=lambda:{'displays':{}}
 viewer.discover_monitors=lambda:{}
 viewer.reconcile_displays=lambda *args:False
 viewer.screen_assignments=lambda *args:[]
 gui=viewer.EchoViewGUI()
 assert gui.identification_updates.channel=='identify' and gui.visual_updates.channel=='visual'
 assert gui.visual_timer.isActive()
 gui.visual_timer.stop();gui.recovery_timer.stop();gui.watchdog.stop();gui.preview_encoder.close()
 shutil.rmtree(state_directory(home))
 print('Native identification request-channel startup passed.')
"""],check=True,timeout=15)
