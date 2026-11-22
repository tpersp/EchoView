"""Bounded local diagnostics; no source media reads, screenshots or network API."""
import hashlib
import json
import os
import math
import queue
import socket
import threading
import time

PROPERTIES = ('pid','time-pos','speed','pause','paused-for-cache','eof-reached','frame-drop-count',
              'decoder-frame-drop-count','vo-delayed-frame-count','demuxer-cache-duration')

COUNTERS=('frame-drop-count','decoder-frame-drop-count','vo-delayed-frame-count')
METADATA=('width','height','container-fps','display-fps','hwdec-current')


def media_identity(source):
    """Identify an already-selected source without opening or stat-ing it."""
    source=str(source)
    reference=hashlib.sha256(source.encode('utf-8',errors='surrogatepass')).hexdigest()[:16]
    if os.path.isabs(source) and '://' not in source:
        return f'clip={reference}; file={json.dumps(os.path.basename(source)[:120],ensure_ascii=False)}'
    return f'stream={reference}'


def mpv_sample(path, *, metadata=False):
    """Read only allowlisted properties; never send playback control commands."""
    result={}
    properties=PROPERTIES+METADATA if metadata else PROPERTIES
    deadline=time.monotonic()+.25
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(.25)
        client.connect(path)
        client.sendall(b''.join((json.dumps({'command':['get_property',name],'request_id':i})+'\n').encode()
                                for i,name in enumerate(properties)))
        pending=b'';received=set();total=0
        while len(received)<len(properties) and time.monotonic()<deadline:
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
                if type(index) is int and 0<=index<len(properties):
                    received.add(index)
                    if item.get('error')=='success':result[properties[index]]=item.get('data')
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
        self.ipc_failures=0
        self.thread=None
        if start:
            self.thread=threading.Thread(target=self._run,name='playback-diagnostics',daemon=True)
            self.thread.start()

    def update(self, **state):
        state['observed_at']=self.clock()
        with self.lock:self.state=dict(state)

    def event(self, category, detail):
        # Caller supplies fixed categories and numeric metadata, never source URLs.
        try:self.messages.put_nowait((category,str(detail)[:512]))
        except queue.Full:pass

    def emit(self, category, detail):
        now=self.clock()
        if len(self.last)>=32 and category not in self.last:return False
        self.counts[category]=self.counts.get(category,0)+1
        if now-self.last.get(category,float('-inf'))<60:
            self.suppressed+=1;return False
        self.last[category]=now
        self.report(f'{category}: {detail}')
        return True

    def _select_video(self, key, context=''):
        if key==self.video_key:return
        if self.video and self.video.get('problem'):
            totals=', '.join(f'{name}={self.video["counts"].get(name,0):g}' for name in COUNTERS)
            self.emit('video-summary',f'{self._video_context()}; observed_s={self.clock()-self.video["started"]:.1f}; last_observed {totals}')
        self.video_key=key;self.video_ready=None;self.video_issue=None;self.ipc_failures=0
        self.video={'started':self.clock(),'changed':self.clock(),'position':None,'counts':{},
                    'reported':{},'context':context,'metadata':{},'metadata_read':False} if key is not None else {}

    def _video_context(self):
        text=f'player={self.video_key}'
        if self.video.get('context'):text+='; '+self.video['context']
        values=self.video.get('metadata',{})
        for name,value in values.items():text+=f'; {name}={value}'
        return text

    def _telemetry_failure(self, started):
        self.ipc_failures+=1
        # Clip hand-offs and single slow IPC replies are not playback failures.
        if self.ipc_failures>=3 and self.clock()-started>15:
            self.emit('video-telemetry-unavailable',f'{self._video_context()}; {self.ipc_failures} consecutive failed samples; playback not assessed')

    def check_video(self, key, sample, context=''):
        now=self.clock()
        self._select_video(key,context)
        previous=self.video
        self.video_issue=None
        if sample.get('paused-for-cache') is True:
            previous.setdefault('cache_since',now)
            if now-previous['cache_since']>=5:self.video_issue='video_buffering'
            if self.video_ready==key or now-previous['cache_since']>=2:
                previous['problem']=True
                self.emit('video-buffering',f'{self._video_context()}; observed pause at least {now-previous["cache_since"]:.1f}s')
        else:previous.pop('cache_since',None)
        for name in COUNTERS:
            value=sample.get(name)
            if type(value) not in (int,float) or not math.isfinite(value) or value<0:continue
            before=previous['counts'].get(name)
            baseline,reported_at=previous['reported'].setdefault(name,(0,now))
            if before is not None and value<before:
                previous['reported'][name]=(value,now)
            elif value>baseline:
                previous['problem']=True
                delta=f'initial_total={value:g}' if before is None else f'observed_delta={value-baseline:g} over {now-reported_at:.1f}s; total={value:g}'
                if self.emit('video-'+name,f'{self._video_context()}; {delta}'):
                    previous['reported'][name]=(value,now)
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
                previous['problem']=True
                self.emit('video-timeline-lag',f'{self._video_context()}; advanced {advanced:.2f}s over {elapsed:.2f}s; speed={speed:g}')
        previous.update(sampled=now,paused=paused,speed=speed)
        if paused or previous['position'] is None or abs(position-previous['position'])>.01:
            previous['changed']=now
        elif now-previous['changed']>=6:
            self.video_issue='video_stalled'
            previous['problem']=True
            self.emit('video-timeline-stalled',f'{self._video_context()}; position unchanged for {now-previous["changed"]:.1f}s')
        previous['position']=position

    def check(self):
        self.video_issue=None
        for _ in range(32):
            try:category,detail=self.messages.get_nowait()
            except queue.Empty:break
            self.emit(category,detail)
        with self.lock:state=dict(self.state)
        now=self.clock()
        age=now-state.get('observed_at',now)
        fresh=0<=age<=5
        if fresh and state.get('image_started') and now-state['image_started']>5:
            self.emit('image-load-slow',f'load/check pending for {now-state["image_started"]:.1f}s; current media retained')
        if fresh and state.get('socket'):
            key=state.get('video_key')
            self._select_video(key,state.get('media',''))
            try:
                sample=mpv_sample(state['socket'],metadata=not self.video['metadata_read'])
                with self.lock:current=self.state
                # A new GUI snapshot can arrive while IPC is in flight.
                if current.get('video_key')!=key or current.get('socket')!=state['socket']:return
                if sample.get('pid')!=key:
                    self._telemetry_failure(state.get('video_started',now))
                    self.video['position']=None
                else:
                    self.ipc_failures=0
                    if type(sample.get('time-pos')) in (int,float):
                        if not self.video['metadata_read']:
                            values={name:value for name in METADATA if type(value:=sample.get(name)) in (int,float) and math.isfinite(value)}
                            hw=sample.get('hwdec-current')
                            if isinstance(hw,str) and len(hw)<=32 and all(c.isalnum() or c in '_-' for c in hw):values['hwdec-current']=hw
                            self.video['metadata']=values;self.video['metadata_read']=True
                        self.check_video(key,sample,state.get('media',''))
                    elif self.video_ready is None and not sample.get('eof-reached') and now-state.get('video_started',now)>15:
                        if now-state.get('video_started',now)>30:self.video_issue='video_loading'
                        self.emit('video-startup-pending',f'{self._video_context()}; player has not supplied its first playback timeline')
                    else:
                        # Missing/EOF data after playback is not a new startup.
                        self.video['position']=None
            except (OSError,ValueError,TypeError):
                with self.lock:current=self.state
                if current.get('video_key')==key and current.get('socket')==state['socket']:
                    self._telemetry_failure(state.get('video_started',now))
                self.video['position']=None
        elif fresh and state.get('qt_video'):
            self.check_video(('qt',state.get('video_key')),state['qt_video'])
        elif fresh:self._select_video(None)
        elif self.video:self.video['position']=None
        if now>=self.summary_at:
            self.summary_at=now+900
            try:
                import psutil
                rss=psutil.Process().memory_info().rss//(1024*1024)
            except Exception:rss='unavailable'
            self.report(f'health: mode={state.get("mode","unknown")}; events={sum(self.counts.values())}; suppressed={self.suppressed}; viewer_rss_mib={rss}; snapshot_age_s={max(0,age):.1f}')
            self.counts={};self.suppressed=0

    def _run(self):
        while not self.closed.wait(2):
            try:self.check()
            except Exception:pass  # Diagnostics cannot interrupt playback.
        try:self._select_video(None)
        except Exception:pass

    def close(self):
        self.closed.set()  # Never wait for IPC or disk I/O on the GUI thread.
