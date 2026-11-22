"""Current recovery status from bounded local snapshots and mount metadata."""
import json
import os
from pathlib import Path
import re
import time

from echoview.live_settings import atomic_json

MAX_BYTES=65536
FRESH_SECONDS=20
PROBLEMS={
    'media_empty':('No playable media selected','Choose available media or check the selected folders.','media'),
    'media_failed':('Media could not load','Check the selected file and media connection.','media'),
    'media_slow':('Media is taking longer to load','Check the media connection. Playback will continue when loading completes.','retry'),
    'schedule_invalid':('Playback schedule needs attention','Check the schedule times and selected folders.','displays'),
    'video_loading':('Video has not started','Check the media connection and selected video.','retry'),
    'video_unsupported':('Video player is unavailable','Check the installation and restart the viewer.','restart'),
    'video_failed':('Video playback failed','Check the media connection and selected video.','media'),
    'video_buffering':('Video is buffering','The player is waiting for media data.','retry'),
    'video_stalled':('Video playback has stopped advancing','Restart the viewer if playback does not recover.','restart'),
    'web_failed':('Web playback failed','Check the page or stream address and network connection.','displays'),
    'browser_failed':('Browser playback stopped','Restart the viewer to reopen the configured page.','restart'),
    'spotify_auth':('Spotify needs authorization','Reconnect your Spotify account.','spotify'),
    'spotify_offline':('Spotify connection interrupted','Retrying automatically. Check the network connection.','spotify'),
    'spotify_denied':('Spotify access was denied','Check the account and app access settings.','spotify'),
    'spotify_limited':('Spotify requests are temporarily limited','Waiting before retrying automatically.','spotify'),
}


def publish(directory, rows):
    # One bounded file for the whole viewer, regardless of tracks or uptime.
    safe=[]
    for row in rows[:64]:
        safe.append({key:row[key] for key in ('name','mode','problem','uses_media') if key in row})
    value=dict(at=time.time(),pid=os.getpid(),displays=safe)
    if len(json.dumps(value).encode())<=MAX_BYTES:
        atomic_json(directory,'recovery.json',value)


def read(directory, now=None):
    try:
        with (Path(directory)/'recovery.json').open('rb') as stream:data=stream.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:return None
        value=json.loads(data)
        age=(time.time() if now is None else now)-float(value['at'])
        if not 0<=age<=FRESH_SECONDS or (type(value['pid']) is not int or value['pid']<=0) or not isinstance(value['displays'],list):return None
        try:os.kill(value['pid'],0)
        except ProcessLookupError:return None
        except PermissionError:pass
        return value
    except (OSError,ValueError,TypeError,KeyError,OverflowError):return None


def unescape(value):
    return re.sub(r'\\([0-7]{3})',lambda match:chr(int(match[1],8)),value)


def storage_missing(image_dir, fstab, mounts):
    """Inspect local metadata only; never stat, list, open or resolve NAS paths."""
    image_dir=os.path.abspath(image_dir)
    expected=[]
    for line in fstab.splitlines():
        fields=line.split()
        if line.lstrip().startswith('#') or len(fields)<3:continue
        if fields[2] not in ('cifs','nfs','nfs4','fuse.sshfs','sshfs'):continue
        target=os.path.abspath(unescape(fields[1]))
        if os.path.commonpath([image_dir,target])==target:expected.append(target)
    if not expected:return False
    target=max(expected,key=len)
    mounted=set()
    for line in mounts.splitlines():
        fields=line.split()
        if len(fields)>5:mounted.add(os.path.normpath(unescape(fields[4])))
    return target not in mounted


def status(cfg, snapshot, missing=False):
    issues=[]
    storage_issue=dict(code='storage_missing',title='Media storage is disconnected',
                       detail='Reconnect storage before restarting the viewer.',action='retry',display='')
    if snapshot is None:
        media_modes=('random_image','specific_image','mixed','videos','scheduled')
        needs=any(display.get('mode') in media_modes or
                  (display.get('mode')=='spotify' and display.get('fallback_mode','random_image')!='none')
                  for display in cfg.get('displays',{}).values())
        if missing and needs:issues.append(storage_issue)
        issues.append(dict(code='viewer_unavailable',title='Viewer status is unavailable',
                    detail='The viewer may be starting or not responding.',action='restart',display=''))
        return dict(viewer=None,issues=issues)
    configured=cfg.get('displays',{})
    rows=[row for row in snapshot['displays'][:64] if isinstance(row,dict) and isinstance(row.get('name'),str) and row.get('name') in configured]
    rows=[row for row in rows if row.get('mode')==configured[row['name']].get('mode') or configured[row['name']].get('mode')=='scheduled']
    needs_storage=any(row.get('uses_media') is True for row in rows)
    if missing and needs_storage:
        issues.append(storage_issue)
    for row in rows:
        problem=row.get('problem')
        if missing and needs_storage and isinstance(problem,str) and problem in ('media_slow','media_empty','media_failed'):continue
        if isinstance(problem,str) and problem in PROBLEMS:
            title,detail,action=PROBLEMS[problem]
            issues.append(dict(code=problem,title=title,detail=detail,action=action,display=row['name']))
    return dict(viewer=snapshot['pid'],issues=issues)
