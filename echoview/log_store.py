"""Bounded, process-safe application logs, shared with the network watchdog."""
from datetime import datetime
import fcntl
import os
from pathlib import Path
import sys

MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 3
MAX_ENTRY_BYTES = 8192


def append_log(path, message, *, max_bytes=MAX_BYTES, backups=BACKUPS):
    """Keep active and archived files bounded, including pre-existing large logs.

    No logging failure may interrupt playback. The stable lock file coordinates
    threads/processes across renames; all writers must use this function.
    """
    try:
        if type(max_bytes) is not int or max_bytes<128 or type(backups) is not int or not 1<=backups<=10:
            return False
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        message=str(message)[:MAX_ENTRY_BYTES]
        data = (f'{datetime.now().isoformat(timespec="seconds")}: {message}\n').encode('utf-8',errors='replace')
        data = data[:min(MAX_ENTRY_BYTES,max_bytes)-1].rstrip(b'\n') + b'\n'
        fd = os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR,0o664)
        try:
            if os.geteuid()==0 and path.exists():
                owner=path.stat();os.fchown(fd,owner.st_uid,owner.st_gid);os.fchmod(fd,0o664)
            fcntl.flock(fd,fcntl.LOCK_EX)
            owner = path.stat() if path.exists() else None
            for item in [path]+[Path(f'{path}.{i}') for i in range(1,backups+1)]:
                if item.exists() and item.stat().st_size>max_bytes:
                    with item.open('r+b') as stream:
                        stream.seek(-max_bytes,os.SEEK_END)
                        tail=stream.read(max_bytes)
                        stream.seek(0);stream.write(tail);stream.truncate()
            if path.exists() and path.stat().st_size+len(data)>max_bytes:
                for number in range(backups,0,-1):
                    source=path if number==1 else Path(f'{path}.{number-1}')
                    if source.exists():os.replace(source,Path(f'{path}.{number}'))
            with path.open('ab') as stream:
                if os.geteuid()==0 and owner is not None:
                    os.fchown(stream.fileno(),owner.st_uid,owner.st_gid)
                    os.fchmod(stream.fileno(),owner.st_mode & 0o777)
                stream.write(data)
        finally:
            os.close(fd)
        return True
    except (OSError,ValueError,TypeError):
        return False


if __name__=='__main__':
    # Standalone stdlib-only entry point for the shell watchdog; stdin is data.
    sys.exit(0 if len(sys.argv)==2 and append_log(sys.argv[1],sys.stdin.read(MAX_ENTRY_BYTES)) else 1)
