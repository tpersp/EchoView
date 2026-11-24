from pathlib import Path
import json
from types import SimpleNamespace
import pytest
from echoview.watchdog_recovery import Recovery,StateStore,Backend,discover_mount,GRACE,RETRY,COOLDOWN

MOUNT={'path':'/mnt/media','host':'nas','port':445}


class Fake:
    def __init__(self):self.up=True;self.healthy=False;self.online=False;self.events=[]
    def service_up(self,mount):return self.up
    def probe(self,mount):self.events.append('probe');return self.healthy
    def remount(self,mount):self.events.append('remount');return False
    def reconnect(self):self.events.append('reconnect');return True
    def reachable(self,targets):return self.online
    def reboot(self):self.events.append('reboot')
    def log(self,message):pass


def runner(state,backend,now,saves=None,uptime=10000):
    return Recovery(state,backend,lambda data:(saves.append(dict(data)) if saves is not None else None),now,uptime)


def test_offline_nas_never_probes_remounts_or_reboots():
    state={};backend=Fake();backend.up=False
    for tick in range(100):runner(state,backend,10000+tick*300).storage(MOUNT)
    assert backend.events==[] and 'storage_since' not in state


def test_healthy_mount_does_not_change_playback_and_clears_failure_state():
    state={'storage_since':1,'mount_attempts':2,'mount':'/mnt/media'};backend=Fake();backend.healthy=True
    runner(state,backend,10000).storage(MOUNT)
    assert backend.events==['probe'] and 'storage_since' not in state and 'mount_attempts' not in state


def test_share_grace_then_three_spaced_mount_attempts_then_guarded_reboot():
    state={};backend=Fake();saves=[]
    runner(state,backend,10000,saves).storage(MOUNT)
    runner(state,backend,10000+GRACE-1,saves).storage(MOUNT)
    assert 'remount' not in backend.events
    for tick in range(3):runner(state,backend,10000+GRACE+tick*RETRY,saves).storage(MOUNT)
    assert backend.events.count('remount')==3 and 'reboot' not in backend.events
    when=10000+GRACE+3*RETRY
    runner(state,backend,when,saves).storage(MOUNT)
    assert backend.events.count('reboot')==1 and saves[-1]['reboot_at']==when
    runner(state,backend,when+300,saves).storage(MOUNT)
    assert backend.events.count('reboot')==1


def test_mount_success_recovers_on_next_run_without_reboot():
    state={'mount':'/mnt/media','storage_since':1};backend=Fake()
    runner(state,backend,10000).storage(MOUNT);backend.healthy=True
    runner(state,backend,10300).storage(MOUNT)
    assert backend.events.count('remount')==1 and 'reboot' not in backend.events


def test_reboot_cooldown_persists_across_store_reload_and_clock_rollback(tmp_path):
    store=StateStore(tmp_path);backend=Fake();state={}
    runner(state,backend,10000,[],uptime=100).reboot('test');assert 'reboot' not in backend.events
    recovery=Recovery(state,backend,store.save,10000,10000);recovery.reboot('test')
    for now in (9000,10001,10000+COOLDOWN-1):
        Recovery(store.load(),backend,store.save,now,10000).reboot('test')
    assert backend.events.count('reboot')==1
    recovered=store.load();recovered.pop('network_rebooted')  # A new, recovered-then-failed episode.
    Recovery(recovered,backend,store.save,10000+COOLDOWN,10000).reboot('test')
    assert backend.events.count('reboot')==2
    assert len(store.path.read_bytes())<4096 and not list(store.directory.glob('.state-*'))


def test_network_reconnect_is_attempted_before_reboot_and_rate_limited():
    state={};backend=Fake();backend.up=False
    runner(state,backend,10000).network(MOUNT,['nas','gateway'])
    assert backend.events==['reconnect','reboot']
    runner(state,backend,10300).network(MOUNT,['nas','gateway'])
    assert backend.events==['reconnect','reboot']


def test_recovered_network_avoids_reboot():
    state={};backend=Fake();backend.up=False;backend.online=True
    runner(state,backend,10000).network(MOUNT,['nas','gateway'])
    assert backend.events==['reconnect']


def test_nas_service_reachable_despite_failed_pings_prevents_network_reset():
    state={};backend=Fake();backend.healthy=True
    runner(state,backend,10000).network(MOUNT,['nas','gateway'])
    assert backend.events==['probe']


def test_discovery_uses_fstab_not_filesystem_probes(monkeypatch):
    monkeypatch.setattr(Path,'stat',lambda *a,**kw:pytest.fail('No filesystem probing'))
    fstab='//nas/share /mnt/media cifs credentials=/secret 0 0\n/dev/root / ext4 defaults 0 0\n'
    assert discover_mount('/mnt/media/folder',fstab)==MOUNT
    assert discover_mount('/mnt/media-other',fstab) is None
    assert discover_mount('/local/uploads',fstab) is None
    assert discover_mount('/anything','nas:/ / nfs defaults 0 0') is None


def test_busy_probe_does_not_spawn_another_process(monkeypatch,tmp_path):
    backend=Backend(tmp_path);calls=[]
    def run(args,timeout=5):calls.append(args);return SimpleNamespace(returncode=0,stdout='deactivating\n')
    monkeypatch.setattr(backend,'run',run)
    assert backend.probe(MOUNT) is False
    assert len(calls)==1 and calls[0][0]=='systemctl'


def test_remount_never_uses_forced_or_lazy_unmount(monkeypatch,tmp_path):
    backend=Backend(tmp_path);calls=[]
    def run(args,timeout=5):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='mnt-media.mount\n' if args[0]=='systemd-escape' else 'ForceUnmount=no\nLazyUnmount=no\nJob=\n')
    monkeypatch.setattr(backend,'run',run)
    assert backend.remount(MOUNT)
    assert calls[-1]==['systemctl','--no-block','restart','mnt-media.mount']
    def forced(args,timeout=5):return SimpleNamespace(returncode=0,stdout='mnt-media.mount\n' if args[0]=='systemd-escape' else 'ForceUnmount=yes\nLazyUnmount=no\nJob=\n')
    monkeypatch.setattr(backend,'run',forced);monkeypatch.setattr(backend,'log',lambda message:None)
    assert backend.remount(MOUNT) is False


def test_corrupt_state_rejected_instead_of_resetting_reboot_limit(tmp_path):
    store=StateStore(tmp_path)
    for text in ('bad','[]','{"reboot_at":"bad"}','{"reboot_at":NaN}'):
        store.path.write_text(text)
        with pytest.raises(ValueError):store.load()


def test_no_reboot_loop_even_after_cooldown_without_a_healthy_episode():
    state={};backend=Fake();backend.up=False
    runner(state,backend,10000).network(MOUNT,['nas','gateway'])
    for index in range(1,10):runner(state,backend,10000+index*COOLDOWN).network(MOUNT,['nas','gateway'])
    assert backend.events.count('reboot')==1


def test_storage_reboot_latch_survives_offline_nas_and_clears_only_when_share_works():
    state={'mount':'/mnt/media','storage_rebooted':True};backend=Fake();backend.up=False
    runner(state,backend,10000).storage(MOUNT);assert state['storage_rebooted']
    backend.up=True
    runner(state,backend,11000).storage(MOUNT);assert state['storage_rebooted']
    backend.healthy=True
    runner(state,backend,12000).storage(MOUNT);assert 'storage_rebooted' not in state
