"""Validate isolated probes with systemd; no recovery/remount/reboot is invoked."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from echoview.watchdog_recovery import Backend,PROBE_UNIT,discover_mount,StateStore

assert os.geteuid()==0,'This native systemd check must run as root'
with tempfile.TemporaryDirectory(prefix='ev-recovery-probe-') as directory:
    backend=Backend(directory)
    local=Path(directory)/'local';local.mkdir()
    assert backend.probe({'path':str(local)}) is False,'Local directory must not masquerade as a NAS mount'
    media=os.environ.get('ECHOVIEW_TEST_MEDIA_ROOT')
    if media:
        mount=discover_mount(media,Path('/etc/fstab').read_text())
        assert mount and backend.service_up(mount)
        started=time.monotonic()
        assert backend.probe(mount),'Declared network share must pass its read-only root-directory probe'
        print('Native share probe passed in',round(time.monotonic()-started,2),'seconds; no media files opened.',flush=True)
    if media:
        from echoview import watchdog_recovery
        (Path(directory)/'.env').write_text('IMAGE_DIR='+media+chr(10))
        env=dict(os.environ);env.pop('IMAGE_DIR',None)
        subprocess.run([sys.executable,str(Path(watchdog_recovery.__file__).absolute()),
                        'storage','--home',directory],env=env,check=True,timeout=20)
        import json
        state=json.loads((Path(directory)/'.network-watchdog-recovery/state.json').read_text())
        assert state['mount']==mount['path'] and 'storage_since' not in state
        print('Native full recovery CLI: environment discovery, isolated probe and state publication passed.',flush=True)
    subprocess.run(['systemd-run','--quiet','--collect','--unit='+PROBE_UNIT,
                    '--property=RuntimeMaxSec=2s','/bin/sleep','2'],check=True,timeout=5)
    started=time.monotonic()
    assert backend.probe({'path':str(local)}) is False
    assert time.monotonic()-started<2,'Busy probe must not spawn/wait for another probe'
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        result=backend.run(['systemctl','show',PROBE_UNIT,'-p','LoadState','--value'])
        if result and result.stdout.strip()=='not-found':break
        time.sleep(.1)
    assert result.stdout.strip()=='not-found','Transient probe unit must be collected'
    store=StateStore(directory);store.save({'reboot_at':1234,'storage_rebooted':True})
    assert store.load()['storage_rebooted'] is True
    assert store.path.stat().st_mode & 0o777==0o600
    print('Native watchdog: local-directory rejection, bounded busy-probe behavior, transient cleanup and private persistent state passed. No remount/reconnect/reboot invoked.',flush=True)
