"""Real read-only mpv IPC with synthetic media and no display/audio output."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from echoview.playback_diagnostics import mpv_sample,Diagnostics
from echoview.log_store import append_log
with tempfile.TemporaryDirectory(prefix='ev-diag-') as directory:
    root=Path(directory);video=root/'synthetic.mp4';socket=root/'player.sock';log=root/'viewer.log'
    subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10:d=8',
                    '-c:v','mpeg4','-y',str(video)],check=True,timeout=15)
    proc=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--no-audio','--really-quiet',
                           '--input-ipc-server='+str(socket),'--',str(video)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+5
        while not socket.exists() and time.monotonic()<deadline:time.sleep(.02)
        first={}
        while time.monotonic()<deadline and not isinstance(first.get('time-pos'),(int,float)):
            first=mpv_sample(str(socket),metadata=True);time.sleep(.02)
        assert isinstance(first.get('time-pos'),(int,float)),first
        assert first['pid']==proc.pid and first['width']==64 and first['height']==64
        time.sleep(.4)
        second=mpv_sample(str(socket))
        assert second['time-pos']>first['time-pos'],(first,second)
        reports=[];diagnostics=Diagnostics(reports.append,start=False)
        diagnostics.update(mode='videos',socket=str(socket),video_key=proc.pid,video_started=time.monotonic())
        diagnostics.check()
        assert diagnostics.video_ready==proc.pid and diagnostics.video['metadata']['width']==64
        assert not any('stalled' in message for message in reports)
        for index in range(200):assert append_log(log,f'synthetic diagnostic {index}',max_bytes=512)
        assert all(item.stat().st_size<=512 for item in root.glob('viewer.log*'))
        assert proc.poll() is None,'Monitoring must not stop playback'
        print('Native diagnostics: real mpv properties read-only, advancing playback, no false stall, bounded rotation passed. No NAS or live display was accessed.')
    finally:
        proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
