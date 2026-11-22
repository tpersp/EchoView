import json
import socket
import threading
import pytest
from echoview.playback_diagnostics import Diagnostics,mpv_sample,PROPERTIES


@pytest.fixture
def monitor():
    now=[100.];reports=[]
    return Diagnostics(reports.append,clock=lambda:now[0],start=False),now,reports


def test_stalls_buffering_counter_deltas_pause_and_clip_reset(monitor):
    diag,now,reports=monitor
    diag.check_video(1,{'time-pos':1,'frame-drop-count':2})
    assert 'increased by 2' in reports[-1]
    diag.check_video(1,{'time-pos':1,'frame-drop-count':2})
    assert len(reports)==1
    now[0]+=7;diag.check_video(1,{'time-pos':1})
    assert 'timeline-stalled' in reports[-1]
    before=len(reports)
    now[0]+=60;diag.check_video(1,{'time-pos':1,'pause':True})
    assert len(reports)==before
    now[0]+=7;diag.check_video(1,{'time-pos':1,'paused-for-cache':True})
    assert 'video-buffering' in reports[-1]
    before=len(reports)
    diag.check_video(2,{'time-pos':1})
    assert len(reports)==before


def test_gif_delays_pending_images_rate_limit_and_no_static_image_false_alarm(monitor):
    diag,now,reports=monitor
    diag.update(mode='specific_image');diag.check();assert not reports
    diag.update(mode='gif',gif_due=200);diag.check();assert not reports
    now[0]=203;diag.check();assert 'gif-frame-delayed' in reports[-1]
    diag.check();assert len(reports)==1
    diag.update(mode='mixed',image_started=190);diag.check();assert 'image-load-slow' in reports[-1]
    diag.update(mode='specific_image');now[0]+=10;diag.check();assert len(reports)==2


def test_bounded_queue_categories_health_summary_and_failure_isolation(monitor):
    diag,now,reports=monitor
    for _ in range(1000):diag.event('image-load-failed','failed')
    assert diag.messages.qsize()==32
    diag.check();assert len(reports)==1 and diag.suppressed==31
    for index in range(100):diag.emit(f'category-{index}','test')
    assert len(diag.last)==32
    now[0]+=901;diag.update(mode='spotify');diag.check()
    assert 'health: mode=spotify' in reports[-1] and 'viewer_rss_mib=' in reports[-1]
    assert diag.counts=={}
    diag.close();assert diag.closed.is_set()


def test_mpv_protocol_is_read_only_bounded_and_unsupported_properties_are_optional(monkeypatch):
    commands=[]
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def settimeout(self,timeout):assert 0<timeout<=.25
        def connect(self,path):assert path=='private-socket'
        def sendall(self,data):
            commands.extend(json.loads(line) for line in data.splitlines())
            payloads=[{'event':'property-change'}]
            for command in commands:
                payload={'request_id':command['request_id'],'error':'success','data':3}
                if command['command'][1]=='decoder-frame-drop-count':payload['error']='property unavailable'
                payloads.append(payload)
            data=b''.join((json.dumps(item)+'\n').encode() for item in payloads)
            self.parts=[data[:17],data[17:]]
        def recv(self,size):return self.parts.pop(0) if self.parts else b''
    monkeypatch.setattr(socket,'socket',lambda *args:Client())
    sample=mpv_sample('private-socket')
    assert len(commands)==len(PROPERTIES)
    assert all(command['command'][0]=='get_property' for command in commands)
    assert 'decoder-frame-drop-count' not in sample
    assert sample['time-pos']==3


def test_no_false_stall_at_eof_or_on_backward_seek(monitor):
    diag,now,reports=monitor
    diag.check_video(1,{'time-pos':20})
    now[0]+=10;diag.check_video(1,{'time-pos':20,'eof-reached':True})
    now[0]+=10;diag.check_video(1,{'time-pos':1})
    assert not reports


def test_video_short_timeline_lag_speed_and_pause_exclusions(monitor):
    diag,now,reports=monitor
    diag.check_video(1,{'time-pos':1,'speed':1})
    now[0]+=2;diag.check_video(1,{'time-pos':2,'speed':1})
    assert 'video-timeline-lag' in reports[-1]
    diag.check_video(2,{'time-pos':1,'speed':.5})
    before=len(reports)
    now[0]+=2;diag.check_video(2,{'time-pos':2,'speed':.5})
    assert len(reports)==before
    now[0]+=2;diag.check_video(2,{'time-pos':2,'speed':.5,'pause':True})
    now[0]+=2;diag.check_video(2,{'time-pos':2.1,'speed':.5})
    assert len(reports)==before
