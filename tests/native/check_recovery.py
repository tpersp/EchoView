"""Native current-state recovery transitions with synthetic media only."""
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='ev-recovery-') as directory:
    os.environ['VIEWER_HOME']=os.environ['IMAGE_DIR']=directory
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    from echoview import viewer,recovery
    from echoview.spotify_state import state_directory
    app=QApplication([])
    display={'mode':'calibration'};cfg={'displays':{'fixture':display}}
    viewer.load_config=lambda:cfg
    window=viewer.DisplayWindow('fixture',display,app.primaryScreen())
    assert window.recovery_state()['problem'] is None
    window.clear_foreground_label('No images found')
    assert window.recovery_state()['problem']=='media_empty'
    path=Path(directory)/'synthetic.png';Image.new('RGB',(64,64),'blue').save(path)
    window.request_foreground_image(str(path))
    deadline=time.monotonic()+3
    while window.current_pixmap is None and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert window.recovery_state()['problem'] is None
    window.current_mode='spotify';window.spotify_status='authorization_required'
    assert window.recovery_state()['problem']=='spotify_auth'
    window.spotify_status='paused'
    assert window.recovery_state()['problem'] is None
    window.diag_image_started=time.monotonic()-11;window.diag_image_request=window.image_request_id
    assert window.recovery_state()['problem']=='media_slow'
    window.diag_image_started=0
    window.diagnostics.close();window.diagnostics.thread.join(timeout=1)
    clock=[100.];window.diagnostics.clock=lambda:clock[0]
    window.diagnostics.check_video(123,{'time-pos':1})
    clock[0]+=7;window.diagnostics.check_video(123,{'time-pos':1})
    window.current_mode='videos';window.current_video_proc=SimpleNamespace(pid=123,poll=lambda:None)
    assert window.recovery_state()['problem']=='video_stalled'
    clock[0]+=2;window.diagnostics.check_video(123,{'time-pos':3})
    assert window.recovery_state()['problem'] is None
    window.current_video_proc=None
    from echoview.config import VIEWER_HOME
    viewer.EchoViewGUI._publish_recovery(SimpleNamespace(windows=[window]))
    snapshot=recovery.read(state_directory(VIEWER_HOME))
    assert snapshot and snapshot['displays'][0]['name']=='fixture'
    assert snapshot['displays'][0]['problem'] is None
    window.close()
    import shutil
    shutil.rmtree(state_directory(VIEWER_HOME))
    print('Native recovery: media failure/success, Spotify authorization/pause, slow loads, video stall/recovery and bounded current-state publishing passed.')

# Exercise the real application constructor too; no display/media assignments.
import subprocess
subprocess.run([sys.executable,'-c',"""
import os,tempfile,shutil
with tempfile.TemporaryDirectory(prefix='ev-status-start-') as home:
 os.environ['VIEWER_HOME']=os.environ['IMAGE_DIR']=home
 from echoview import viewer,recovery
 from echoview.spotify_state import state_directory
 viewer.load_config=lambda:{'displays':{}}
 viewer.discover_monitors=lambda:{}
 viewer.reconcile_displays=lambda *args:False
 viewer.screen_assignments=lambda *args:[]
 gui=viewer.EchoViewGUI()
 assert gui.recovery_timer.isActive()
 assert recovery.read(state_directory(home))['displays']==[]
 gui.recovery_timer.stop();gui.watchdog.stop();gui.preview_encoder.close()
 shutil.rmtree(state_directory(home))
 print('Native recovery application startup and status timer passed.')
"""],check=True,timeout=15)
