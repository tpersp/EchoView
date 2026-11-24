"""Complete shuffle passes across scheduled folders and small caches; synthetic only."""
from collections import Counter
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='ev-shuffle-') as home:
    os.environ['VIEWER_HOME']=os.environ['IMAGE_DIR']=home
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    from echoview import viewer
    from echoview.spotify_state import state_directory
    root=Path(home);folders=['A','B','C'];expected=[]
    for folder in folders:
        (root/folder).mkdir()
        for number in range(20):
            path=root/folder/f'{number}.gif'
            Image.new('RGB',(16,16),'red').save(path,save_all=True,append_images=[Image.new('RGB',(16,16),'blue')],duration=60,loop=0)
            expected.append(str(path))
    display={'mode':'scheduled','image_interval':60,'schedule':[{'time':'06:00','folders':folders,'shuffle':True}]}
    cfg={'cache_capacity':4,'displays':{'fixture':display}}
    viewer.load_config=lambda:cfg
    viewer.datetime=SimpleNamespace(now=lambda:datetime(2026,11,22,7))
    viewer.random.seed(42)
    app=QApplication([]);window=viewer.DisplayWindow('fixture',display,app.primaryScreen())
    window.slideshow_timer.stop();window.schedule_timer.stop();window.diagnostic_timer.stop()
    def wait():
        deadline=time.monotonic()+3
        while window.diag_image_started and time.monotonic()<deadline:app.processEvents();time.sleep(.003)
        assert not window.diag_image_started and window.current_movie is not None
    wait();seen=[window.last_displayed_path]
    for _ in range(179):
        next_prefetched=window.image_list[(window.index+1)%len(window.image_list)]
        window.next_image();wait()
        assert window.last_displayed_path==next_prefetched
        seen.append(window.last_displayed_path)
    for start in (0,60,120):assert Counter(seen[start:start+60])==Counter(expected)
    assert seen[59]!=seen[60] and seen[119]!=seen[120]
    assert seen[:60]!=seen[60:120]
    assert len(window.image_cache)<=4 and len(window.image_list)==60
    assert window.recovery_state()['playlist_items']==60
    window.diagnostics.close();window.diagnostics.thread.join(timeout=1)
    window.current_mode='videos';window.disp_cfg['shuffle_videos']=True
    videos=[str(root/folder/'synthetic.mp4') for folder in folders]
    window.image_list=list(videos);window.index=0
    original_popen=viewer.subprocess.Popen
    viewer.subprocess.Popen=lambda *args,**kwargs:SimpleNamespace(pid=999999,poll=lambda:0)
    played=[]
    try:
        for _ in range(12):
            window.play_next_video();window.mpv_poll_timer.stop();played.append(window.last_displayed_path)
    finally:viewer.subprocess.Popen=original_popen
    for start in range(0,12,3):assert Counter(played[start:start+3])==Counter(videos)
    assert all(played[index-1]!=played[index] for index in (3,6,9))
    window.current_video_proc=None;window.current_mode='spotify';window.spotify_info=None
    window.disp_cfg.update(fallback_mode='mixed',mixed_folders=folders,shuffle_mode=True)
    window.fallback_image_list=[];window.fallback_index=-1
    fallback=[]
    for _ in range(120):
        window.spotify_fallback_due=0;window.render_spotify('');wait();fallback.append(window.last_displayed_path)
    assert Counter(fallback[:60])==Counter(expected) and Counter(fallback[60:])==Counter(expected)
    assert fallback[59]!=fallback[60]
    assert window.recovery_state()['playlist_items']==60
    window.close()
    import shutil
    shutil.rmtree(state_directory(home),ignore_errors=True)
    print('Native shuffle: all 60 GIFs across three folders per pass despite four-item cache; fresh cycles, boundary avoidance, correct prefetch, video and Spotify fallback passed.')
