"""Bounded network/share recovery. Never modifies NAS files or forces unmounts."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

BOOT_GRACE = 60
NETWORK_RETRY = 15 * 60
CONFIRM_SECONDS = 2
HEALTHY_CONFIRM = 5 * 60
PROBE_UNIT = 'echoview-nas-probe.service'
NETWORK_TYPES = ('cifs', 'nfs', 'nfs4')


def unescape(value):
    for code, char in (('040', ' '), ('011', chr(9)), ('134', chr(92))):
        value = value.replace(chr(92) + code, char)
    return value


def discover_mount(media_root, fstab):
    """Use declared mount metadata only; never resolve/stat a NAS path."""
    root = os.path.abspath(media_root)
    candidates = []
    for line in fstab.splitlines():
        fields = line.split()
        if len(fields) < 4 or line.lstrip().startswith('#') or fields[2] not in NETWORK_TYPES:continue
        path = unescape(fields[1]).rstrip('/')
        if not path or not (root == path or root.startswith(path + '/')):continue
        source = unescape(fields[0])
        if fields[2] == 'cifs' and source.startswith('//'):
            host = source[2:].split('/', 1)[0].strip('[]');port = 445
        elif fields[2].startswith('nfs') and ':' in source:
            host = source[1:].split(']', 1)[0] if source.startswith('[') else source.split(':', 1)[0];port = 2049
        else:continue
        if host:candidates.append(dict(path=path, host=host, port=port))
    return max(candidates, key=lambda item:len(item['path']), default=None)


def media_root(home):
    # Match config.py's small .env loader, without importing the Qt/web package
    # or requiring an optional dotenv dependency in the watchdog interpreter.
    if os.environ.get('IMAGE_DIR'):return os.environ['IMAGE_DIR']
    try:
        lines = (Path(home) / '.env').read_text().splitlines()
    except FileNotFoundError:lines = []
    for line in lines:
        key, separator, value = line.strip().partition('=')
        if separator and key.strip() == 'IMAGE_DIR':
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in (chr(34), chr(39)):
                value = value[1:-1]
            return value
    return str(Path(home) / 'Uploads')


def directory_probe(path):
    # Called only in an isolated, fixed-name transient service. An unkillable
    # filesystem task cannot trap the watchdog or create unlimited probe tasks.
    with os.scandir(path) as entries:next(entries, None)
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        if len(fields) > 6 and unescape(fields[4]) == path and fields[fields.index('-') + 1] in NETWORK_TYPES:return True
    return False  # An empty local directory underneath a missing mount is not healthy.


class StateStore:
    def __init__(self, home):
        self.directory = Path(home) / '.network-watchdog-recovery'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / 'state.json'

    def load(self):
        if not self.path.exists():return {}
        if self.path.stat().st_size > 4096:raise ValueError('Oversized recovery state')
        value = json.loads(self.path.read_text())
        allowed = {'boot', 'reboot_at', 'network_at', 'storage_since', 'mount_at', 'mount_attempts', 'mount', 'storage_rebooted', 'network_rebooted', 'healthy_since'}
        if not isinstance(value, dict) or value.keys() - allowed:raise ValueError('Invalid recovery state')
        for key, number in value.items():
            if key in ('storage_rebooted', 'network_rebooted'):
                if type(number) is not bool:raise ValueError('Invalid recovery state')
            elif key in ('boot', 'mount'):
                if not isinstance(number, str) or len(number) > 1024:raise ValueError('Invalid recovery state')
            elif type(number) not in (int, float) or not math.isfinite(number) or number < 0:raise ValueError('Invalid recovery state')
        return value

    def save(self, state):
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix='.state-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            descriptor = os.open(self.directory, os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        finally:Path(temporary).unlink(missing_ok=True)


class Backend:
    def __init__(self, home):self.home = Path(home)

    def run(self, command, timeout=5):
        try:
            return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):return None

    def log(self, message):
        try:
            from .log_store import append_log
        except ImportError:
            from log_store import append_log
        append_log(os.environ.get('WATCHDOG_LOG', str(self.home / 'viewer.log')), 'Watchdog recovery: ' + message)

    def service_up(self, mount):
        try:
            with socket.create_connection((mount['host'], mount['port']), timeout=2):return True
        except OSError:return False

    def reachable(self, targets):
        return any((result := self.run(['/bin/ping', '-c', '1', '-W', '2', host], timeout=3)) is not None
                   and result.returncode == 0 for host in targets if host)

    def probe(self, mount):
        result = self.run(['systemctl', 'show', PROBE_UNIT, '-p', 'ActiveState', '--value'])
        if result and result.stdout.strip() in ('active', 'activating', 'deactivating'):return False
        result = self.run(['systemd-run', '--quiet', '--collect', '--wait', '--service-type=exec',
                           '--unit=' + PROBE_UNIT, '--property=RuntimeMaxSec=4s',
                           '--property=TimeoutStopSec=1s', '--property=Nice=10',
                           '--property=NoNewPrivileges=yes', '--property=User=' + os.environ.get('WATCHDOG_USER', 'pi'),
                           '--property=StandardOutput=null',
                           '--property=StandardError=null', sys.executable, str(Path(__file__).absolute()),
                           '--probe', mount['path']], timeout=6)
        return result is not None and result.returncode == 0

    def remount(self, mount):
        result = self.run(['systemd-escape', '--path', '--suffix=mount', mount['path']])
        if not result or result.returncode:return False
        unit = result.stdout.strip()
        flags = self.run(['systemctl', 'show', unit, '-p', 'ForceUnmount', '-p', 'LazyUnmount', '-p', 'Job'])
        if not flags or flags.returncode:return False
        values = dict(line.split('=', 1) for line in flags.stdout.splitlines() if '=' in line)
        if values.get('ForceUnmount') != 'no' or values.get('LazyUnmount') != 'no' or values.get('Job', '') not in ('', '0'):
            self.log('Mount busy or configured for forced/lazy unmount; skipping mount restart')
            return False
        # No forced/lazy unmount, no viewer stop, no whole-system mount -a.
        result = self.run(['systemctl', '--no-block', 'restart', unit])
        return result is not None and result.returncode == 0

    def reconnect(self):
        result = self.run(['nmcli', '-t', '-f', 'UUID,DEVICE', 'connection', 'show', '--active'])
        if not result or result.returncode:return False
        for line in result.stdout.splitlines():
            uuid, separator, device = line.partition(':')
            if separator and device not in ('', 'lo') and (Path('/sys/class/net') / device / 'device').exists():
                result = self.run(['nmcli', '--wait', '10', 'connection', 'up', 'uuid', uuid, 'ifname', device], timeout=12)
                return result is not None and result.returncode == 0
        return False

    def pause(self, seconds):
        time.sleep(seconds)

    def reboot(self):
        result = self.run(['systemctl', 'reboot'])
        if result is None or result.returncode:self.log('Reboot request failed; outage guard retained')


class Recovery:
    def __init__(self, state, backend, save, now, uptime):
        self.state, self.backend, self.save, self.now, self.uptime = state, backend, save, now, uptime

    def reset_storage(self):
        for key in ('storage_since', 'mount_at', 'mount_attempts'):self.state.pop(key, None)

    def mark_healthy(self):
        self.reset_storage()
        self.state.pop('network_at', None)
        if self.state.get('storage_rebooted') or self.state.get('network_rebooted'):
            since = self.state.setdefault('healthy_since', self.now)
            if self.now < since:self.state['healthy_since'] = self.now
            elif self.now - since >= HEALTHY_CONFIRM:
                for key in ('storage_rebooted', 'network_rebooted', 'healthy_since'):self.state.pop(key, None)
                self.backend.log('Connectivity/share healthy across checks; reboot guard re-armed')
        else:self.state.pop('healthy_since', None)

    def reboot(self, reason, kind='network'):
        if self.state.get('storage_rebooted') or self.state.get('network_rebooted'):
            self.backend.log('Reboot suppressed until this failure episode recovers: ' + reason);return
        last = self.state.get('reboot_at')
        if self.uptime < BOOT_GRACE or (last is not None and self.now < last):
            self.backend.log('Reboot suppressed by boot grace/backwards clock: ' + reason);return
        self.state['reboot_at'] = self.now
        self.state[kind + '_rebooted'] = True
        self.save(self.state)  # Durable before requesting reboot; survives reboot/clock rollback.
        self.backend.log('Requesting rate-limited reboot: ' + reason)
        self.backend.reboot()

    def storage(self, mount):
        if not mount:return
        if self.state.get('mount') != mount['path']:
            self.reset_storage();self.state['mount'] = mount['path']
        def healthy():
            if 'storage_since' in self.state:self.backend.log('NAS share recovered')
            self.mark_healthy()
        if self.backend.service_up(mount) and self.backend.probe(mount):
            healthy();return
        self.state.pop('healthy_since', None)
        self.state.setdefault('storage_since', self.now)
        self.backend.log('NAS unavailable/unusable; confirming after brief retry')
        self.backend.pause(CONFIRM_SECONDS)
        online = self.backend.service_up(mount)
        if online and self.backend.probe(mount):
            healthy();return
        if online:
            self.backend.log('Share failure confirmed; attempting one quick ordinary mount recovery')
            self.backend.remount(mount)
            self.backend.pause(CONFIRM_SECONDS)
            if self.backend.service_up(mount) and self.backend.probe(mount):
                healthy();return
        self.reboot('NAS remains unavailable/unusable after brief confirmation and quick recovery', kind='storage')

    def network(self, mount, targets):
        if mount and self.backend.service_up(mount):
            self.backend.log('NAS service reachable despite failed pings; no network reboot')
            self.storage(mount);return
        self.state.pop('healthy_since', None)
        if self.now - self.state.get('network_at', 0) >= NETWORK_RETRY:
            self.state['network_at'] = self.now;self.save(self.state)
            self.backend.log('Attempting reconnect of existing active physical network profile')
            self.backend.reconnect()
        if self.backend.reachable(targets):
            self.backend.log('Network targets recovered')
            if mount:self.storage(mount)
            else:self.mark_healthy()
            return
        self.reboot('both network targets remain unreachable after network recovery')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', choices=('storage', 'network'))
    parser.add_argument('--home', default='/home/pi/EchoView')
    parser.add_argument('--target', default='')
    parser.add_argument('--fallback', default='')
    parser.add_argument('--probe')
    args = parser.parse_args()
    if args.probe:
        try:return 0 if directory_probe(args.probe) else 1
        except OSError:return 1
    backend = Backend(args.home)
    try:
        media = media_root(args.home)
        mount = discover_mount(media, Path('/etc/fstab').read_text())
        store = StateStore(args.home)
        with (store.directory / 'state.lock').open('a') as lock:
            try:fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:return 0
            for temporary in store.directory.glob('.state-*'):temporary.unlink(missing_ok=True)
            state = store.load();before = dict(state)
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            if state.get('boot') != boot:
                for key in ('storage_since', 'mount_at', 'mount_attempts', 'network_at', 'healthy_since'):state.pop(key, None)
                state['boot'] = boot
            recovery = Recovery(state, backend, store.save, time.time(), float(Path('/proc/uptime').read_text().split()[0]))
            if args.mode == 'network':recovery.network(mount, [args.target, args.fallback])
            elif mount:recovery.storage(mount)
            else:recovery.mark_healthy()
            if state != before:store.save(state)
    except Exception as error:
        backend.log('Recovery unavailable (' + type(error).__name__ + '); no automatic reboot')
        return 1
    return 0


if __name__ == '__main__':sys.exit(main())
