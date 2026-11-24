import io
import threading
import time
from pathlib import Path
from PIL import Image
from echoview.web import video_preview as preview


def test_real_extraction_has_four_frames_and_preserves_source(tmp_path):
    import subprocess, shutil, pytest
    if not shutil.which('ffmpeg'):pytest.skip('ffmpeg not installed')
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=64x48:rate=10:duration=2',
                    '-c:v','mpeg4','-y',str(source)],check=True,timeout=15)
    before=source.read_bytes();target=tmp_path/'preview.jpg'
    preview.render(source,target,False)
    with Image.open(target) as image:assert image.size==(256,144)
    preview.render(source,target,True)
    with Image.open(target) as image:
        assert image.size==(1024,144)
        assert image.crop((0,0,256,144)).tobytes()!=image.crop((768,0,1024,144)).tobytes()
    assert source.read_bytes()==before
    assert not list(tmp_path.glob('*.tmp'))


def test_duplicate_requests_share_work_and_cache_invalidates_on_source_change(tmp_path,monkeypatch):
    source=tmp_path/'clip.mp4';source.write_bytes(b'original')
    directory=tmp_path/'cache';started=threading.Event();release=threading.Event();calls=[]
    def render(source,target,animated):
        calls.append(animated);started.set();assert release.wait(3)
        Image.new('RGB',(256,144)).save(target,'JPEG')
    monkeypatch.setattr(preview,'render',render)
    assert preview.request_preview(source,directory)[1]==202
    assert started.wait(2)
    for _ in range(10):assert preview.request_preview(source,directory)[1]==202
    assert calls==[False]
    release.set()
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        target,status=preview.request_preview(source,directory)
        if status==200:break
        time.sleep(.01)
    assert status==200
    assert preview.request_preview(source,directory)==(target,200)
    source.write_bytes(b'changed source')
    assert preview.request_preview(source,directory)[1]==202
    deadline=time.monotonic()+3
    while len(calls)<2 and time.monotonic()<deadline:time.sleep(.01)
    assert len(calls)==2
    # Finish background work before the temporary directory is removed.
    while preview.request_preview(source,directory)[1]==202 and time.monotonic()<deadline:time.sleep(.01)


def test_cache_retention_and_stale_temporary_cleanup(tmp_path,monkeypatch):
    monkeypatch.setattr(preview,'MAX_BYTES',10);monkeypatch.setattr(preview,'MAX_FILES',2)
    for i in range(5):(tmp_path/f'{i}.jpg').write_bytes(b'12345')
    (tmp_path/'interrupted.tmp').write_bytes(b'partial')
    preview.trim(tmp_path)
    assert len(list(tmp_path.glob('*.jpg')))<=2
    assert sum(p.stat().st_size for p in tmp_path.iterdir())<=10


def test_failed_generation_is_backed_off(tmp_path,monkeypatch):
    source=tmp_path/'bad.mp4';source.touch();calls=[]
    def fail(*args):calls.append(1);raise ValueError('bad media')
    monkeypatch.setattr(preview,'render',fail)
    assert preview.request_preview(source,tmp_path/'cache')[1]==202
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        status=preview.request_preview(source,tmp_path/'cache')[1]
        if status==503:break
        time.sleep(.01)
    assert status==503
    for _ in range(10):assert preview.request_preview(source,tmp_path/'cache')[1]==503
    assert calls==[1]


def test_multiple_requests_cannot_start_parallel_decoders_or_unbounded_jobs(tmp_path,monkeypatch):
    release=threading.Event();started=threading.Event();calls=[];active=[0];peak=[0]
    def render(source,target,animated):
        active[0]+=1;peak[0]=max(peak[0],active[0]);calls.append(source.name);started.set()
        assert release.wait(3)
        Image.new('RGB',(256,144)).save(target,'JPEG');active[0]-=1
    monkeypatch.setattr(preview,'render',render)
    for i in range(16):
        source=tmp_path/f'{i}.mp4';source.touch()
        assert preview.request_preview(source,tmp_path/'cache')[1]==202
    assert started.wait(2)
    assert len(calls)==1
    release.set()
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        with preview._lock:pending=bool(preview._pending)
        if not pending:break
        time.sleep(.01)
    assert not pending and peak==[1] and len(calls)==8


def test_static_poster_does_not_probe_duration_and_uses_keyframe_seek(tmp_path,monkeypatch):
    output=io.BytesIO();Image.new('RGB',(256,144),'blue').save(output,'JPEG')
    commands=[]
    def run(args,timeout):commands.append(args);return output.getvalue()
    monkeypatch.setattr(preview,'_run',run)
    preview.render(tmp_path/'source.mp4',tmp_path/'poster.jpg',False)
    assert len(commands)==1 and commands[0][0]=='ffmpeg'
    assert '-noaccurate_seek' in commands[0]
    assert commands[0][commands[0].index('-skip_frame')+1]=='nokey'


def test_very_short_video_still_has_a_poster(tmp_path):
    import subprocess,shutil,pytest
    if not shutil.which('ffmpeg'):pytest.skip('ffmpeg not installed')
    source=tmp_path/'short.mp4';target=tmp_path/'poster.jpg'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=red:s=64x48:r=24:d=0.2',
                    '-c:v','mpeg4','-y',str(source)],check=True,timeout=15)
    preview.render(source,target,False)
    with Image.open(target) as image:assert image.size==(256,144)
