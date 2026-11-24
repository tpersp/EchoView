"""Real mpv ceiling, native bypass and normal speed; synthetic local files only."""
from fractions import Fraction
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from echoview import video_rendering

with tempfile.TemporaryDirectory(prefix='ev-fps-') as directory:
    root=Path(directory);ipc=root/'player.sock'
    clips=[]
    for rate in ('60','24','24000/1001','12','30','25'):
        clip=root/(rate.replace('/','-')+'.mp4')
        subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i',
                        f'color=c=blue:s=64x64:r={rate}:d=5','-c:v','mpeg4','-y',str(clip)],check=True,timeout=15)
        clips.append((rate,clip))
    flags=video_rendering.frame_rate_flags()
    assert flags,'This native check targets Raspberry Pi hardware'
    proc=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--no-audio','--really-quiet',
                           '--idle=yes','--vf=@fixture:lavfi=[null]','--input-ipc-server='+str(ipc),
                           *flags],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    def command(*args):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(2);client.connect(str(ipc))
            client.sendall((json.dumps({'command':args,'request_id':1})+'\n').encode());data=b''
            while True:
                chunk=client.recv(4096)
                assert chunk,'mpv IPC disconnected'
                data+=chunk
                while b'\n' in data:
                    row,data=data.split(b'\n',1);result=json.loads(row)
                    if result.get('request_id')==1:
                        if args[0]=='get_property' and result.get('error')=='property unavailable':return None
                        assert result.get('error')=='success',result
                        return result.get('data')
    try:
        deadline=time.monotonic()+5
        while not ipc.exists() and time.monotonic()<deadline:time.sleep(.02)
        for rate,clip in clips:
            source=float(Fraction(rate))
            expected=min(source,24)
            command('loadfile',str(clip),'replace')
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                fps=command('get_property','estimated-vf-fps')
                pos=command('get_property','time-pos')
                if isinstance(fps,(int,float)) and abs(fps-expected)<.1 and isinstance(pos,(int,float)) and pos>.2:break
                time.sleep(.03)
            assert isinstance(fps,(int,float)) and abs(fps-expected)<.1,(rate,fps)
            filters=command('get_property','vf')
            labels=[item.get('label') for item in filters]
            assert 'fixture' in labels,'Existing filters must survive'
            assert ('echoview_fps_limit' in labels)==(source>24),(rate,labels)
            start=time.monotonic();before=command('get_property','time-pos');time.sleep(.7)
            advanced=command('get_property','time-pos')-before
            assert abs(advanced-(time.monotonic()-start))<.15,(rate,advanced)
            print(f'Native FPS: {rate} -> {fps:g}, normal timeline, native bypass/filter preservation passed.',flush=True)
    finally:
        proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        stderr=proc.stderr.read()
        assert 'Lua error' not in stderr and 'Error loading script' not in stderr,stderr
