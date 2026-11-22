"""Bounded local diagnostics; no source media reads, screenshots or network API."""
import json
import math
import queue
import socket
import threading
import time

PROPERTIES = ('time-pos','speed','pause','paused-for-cache','eof-reached','frame-drop-count',
              'decoder-frame-drop-count','vo-delayed-frame-count','demuxer-cache-duration')


def mpv_sample(path):
    """Read only allowlisted properties; never send playback control commands."""
    result={}
    deadline=time.monotonic()+.25
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(.25)
        client.connect(path)
        client.sendall(b''.join((json.dumps({'command':['get_property',name],'request_id':i})+'\n').encode()
                                for i,name in enumerate(PROPERTIES)))
        pending=b'';received=set();total=0
        while len(received)<len(PROPERTIES) and time.monotonic()<deadline:
            client.settimeout(max(.001,deadline-time.monotonic()))
            chunk=client.recv(4096)
            if not chunk:break
            total+=len(chunk)
            if total>32768:raise ValueError('Oversized IPC response')
            pending+=chunk
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1)
                item=json.loads(line)
                if not isinstance(item,dict):raise ValueError('Invalid IPC response')
                index=item.get('request_id')
                if type(index) is int and 0<=index<len(PROPERTIES):
                    received.add(index)
                    if item.get('error')=='success':result[PROPERTIES[index]]=item.get('data')
    return result


class Diagnostics:
    """One background worker per display; bounded messages and issue categories."""
    def __init__(self, report, clock=time.monotonic, start=True):
        self.report,self.clock=report,clock
        self.video_issue=None
        self.video_ready=None
        self.lock=threading.Lock()
        self.state={};self.last={};self.video={};self.video_key=None
        self.messages=queue.Queue(maxsize=32)
        self.closed=threading.Event()
        self.summary_at=clock()+900
        self.counts={};self.suppressed=0
        self.thread=None
        if start:
            self.thread=threading.Thread(target=self._run,name='playback-diagnostics',daemon=True)
            self.thread.start()

    def update(self, **state):
        with self.lock:self.state=dict(state)

    def event(self, category, detail):
        # Caller supplies fixed categories and numeric metadata, never source URLs.
        try:self.messages.put_nowait((category,str(detail)[:512]))
        except queue.Full:pass

    def emit(self, category, detail):
        now=self.clock()
        if len(self.last)>=32 and category not in self.last:return
        self.counts[category]=self.counts.get(category,0)+1
        if now-self.last.get(category,float('-inf'))<60:
            self.suppressed+=1;return
        self.last[category]=now
        self.report(f'{category}: {detail}')

    def check_video(self, key, sample):
        now=self.clock()
        if key!=self.video_key:
            self.video_ready=None
            self.video_key=key;self.video={'changed':now,'position':None,'counts':{}}
        previous=self.video
        self.video_issue=None
        if sample.get('paused-for-cache') is True:
            previous.setdefault('cache_since',now)
            if now-previous['cache_since']>=5:self.video_issue='video_buffering'
            self.emit('video-buffering','player paused for cache')
        else:previous.pop('cache_since',None)
        for name in ('frame-drop-count','decoder-frame-drop-count','vo-delayed-frame-count'):
            value=sample.get(name)
            if type(value) not in (int,float) or not math.isfinite(value):continue
            before=previous['counts'].get(name,0)
            if value>before:self.emit('video-'+name,f'player={key}; increased by {value-before:g}; total={value:g}')
            previous['counts'][name]=value
        position=sample.get('time-pos')
        if type(position) not in (int,float) or not math.isfinite(position):return
        self.video_ready=key
        paused=sample.get('pause') is True or sample.get('paused-for-cache') is True or sample.get('eof-reached') is True
        speed=sample.get('speed')
        if (not paused and not previous.get('paused',False) and previous['position'] is not None
                and type(speed) in (int,float) and math.isfinite(speed) and speed>0
                and speed==previous.get('speed')):
            elapsed=now-previous.get('sampled',now)
            advanced=position-previous['position']
            if elapsed>0 and advanced>=0 and elapsed*speed-advanced>=max(.75,elapsed*speed*.1):
                self.emit('video-timeline-lag',f'player={key}; advanced {advanced:.2f}s over {elapsed:.2f}s; speed={speed:g}')
        previous.update(sampled=now,paused=paused,speed=speed)
        if paused or previous['position'] is None or abs(position-previous['position'])>.01:
            previous['changed']=now
        elif now-previous['changed']>=6:
            self.video_issue='video_stalled'
            self.emit('video-timeline-stalled',f'player={key}; position unchanged for {now-previous["changed"]:.1f}s')
        previous['position']=position

    def check(self):
        self.video_issue=None
        for _ in range(32):
            try:category,detail=self.messages.get_nowait()
            except queue.Empty:break
            self.emit(category,detail)
        with self.lock:state=dict(self.state)
        now=self.clock()
        if state.get('gif_due') and now-state['gif_due']>2:
            self.emit('gif-frame-delayed',f'frame overdue by {now-state["gif_due"]:.1f}s')
        if state.get('image_started') and now-state['image_started']>5:
            self.emit('image-load-slow',f'load/check pending for {now-state["image_started"]:.1f}s; current media retained')
        if state.get('socket'):
            try:
                sample=mpv_sample(state['socket'])
                self.check_video(state.get('video_key'),sample)
                if sample.get('time-pos') is None and now-state.get('video_started',now)>15:
                    if now-state.get('video_started',now)>30:self.video_issue='video_loading'
                    self.emit('video-startup-pending','player has not supplied a playback timeline')
            except (OSError,ValueError,TypeError):
                if now-state.get('video_started',now)>15:self.emit('video-telemetry-unavailable','player IPC unavailable; playback unaffected')
        elif state.get('qt_video'):
            self.check_video(('qt',state.get('video_key')),state['qt_video'])
        else:self.video_key=None;self.video={}
        if now>=self.summary_at:
            self.summary_at=now+900
            try:
                import psutil
                rss=psutil.Process().memory_info().rss//(1024*1024)
            except Exception:rss='unavailable'
            self.report(f'health: mode={state.get("mode","unknown")}; events={sum(self.counts.values())}; suppressed={self.suppressed}; viewer_rss_mib={rss}')
            self.counts={};self.suppressed=0

    def _run(self):
        while not self.closed.wait(2):
            try:self.check()
            except Exception:pass  # Diagnostics cannot interrupt playback.

    def close(self):
        self.closed.set()  # Never wait for IPC or disk I/O on the GUI thread.
