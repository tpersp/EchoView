"""Persistent update progress with a single background worker per device."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import uuid

from echoview import updates
from echoview.branches import valid_branch

INSTANCE = uuid.uuid4().hex


def _write(repo, state):
    state['updated_at'] = time.time()
    with tempfile.NamedTemporaryFile(mode='w', dir=repo, prefix='.update-state-',
                                     delete=False) as handle:
        temporary = handle.name
        try:
            json.dump(state, handle)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temporary, Path(repo) / '.update-state.json')
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _read(repo):
    try:
        return json.loads((Path(repo) / '.update-state.json').read_text())
    except (OSError, ValueError):
        return {'status': 'idle'}


def _lock(repo):
    handle = (Path(repo) / '.update-job.lock').open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise updates.UpdateError('Another update is already running.') from None
    return handle


def status(repo):
    state = _read(repo)
    if state.get('status') == 'running':
        try:
            handle = _lock(repo)
        except updates.UpdateError:
            pass
        else:
            # A controller exit or power loss can terminate the worker. Never
            # describe an abandoned attempt as running forever or auto-retry it.
            with handle:
                state = _read(repo)
                if state.get('status') == 'running':
                    state.update(status='interrupted', message=(
                        'The update was interrupted. Inspect the device and its '
                        'update logs before retrying; installation may be incomplete.'))
                    _write(repo, state)
    if state.get('status') == 'awaiting_restart' and state.get('origin_instance') != INSTANCE:
        # This confirms controller return, not video/audio rendering readiness.
        state = {**state, 'status': 'completed',
                 'message': 'The controller is back online. Check the display to confirm playback.'}
    return {**state, 'instance': INSTANCE}


def start(repo, branch, config_path, token_path, reboot=False):
    if not valid_branch(branch):
        raise updates.UpdateError('Invalid update branch.')
    handle = _lock(repo)
    state = {'id': uuid.uuid4().hex, 'status': 'running', 'branch': branch,
             'reboot': reboot, 'started_at': time.time(), 'origin_instance': INSTANCE,
             'message': 'Preparing update'}
    try:
        previous = _read(repo)
        if (previous.get('status') == 'awaiting_restart'
                and previous.get('origin_instance') == INSTANCE):
            raise updates.UpdateError('Installation finished; wait for the controller to restart before updating again.')
        _write(repo, state)
        def worker():
            with handle:
                try:
                    def progress(message):
                        state['message'] = message
                        _write(repo, state)
                    backup = updates.update(repo, branch, config_path, token_path,
                                            reboot=reboot, progress=progress)
                    state.update(status='awaiting_restart', backup=backup,
                                 message='Installation finished. Waiting for the device to reconnect.')
                except updates.UpdateError as exc:
                    state.update(status='failed', message=str(exc))
                except Exception:
                    state.update(status='failed', message=(
                        'An unexpected update error occurred. Inspect the device logs before retrying.'))
                _write(repo, state)
        threading.Thread(target=worker, name='echoview-update', daemon=True).start()
    except Exception:
        handle.close()
        raise
    return dict(state)


def check_release(repo, branch):
    """Fetch refs only; do not modify installed files or install packages."""
    if not valid_branch(branch):
        raise updates.UpdateError('Invalid update branch.')
    try:
        updates.run(['git', 'fetch', 'origin',
                     f'+refs/heads/{branch}:refs/remotes/origin/{branch}'], cwd=repo, timeout=30)
        target = updates.run(['git', 'rev-parse', '--verify',
                              f'refs/remotes/origin/{branch}^{{commit}}'], cwd=repo).stdout.strip()
        current = updates.run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
        config = updates.run(['git', 'show', f'{target}:echoview/config.py'], cwd=repo).stdout
        version = re.search(r'^APP_VERSION\s*=\s*[\'"]([^\'"\n]+)', config, re.MULTILINE)
        changes = updates.run(['git', 'log', '-8', '--format=%s', f'{current}..{target}'], cwd=repo).stdout.splitlines()
        return {'branch': branch, 'current_revision': current[:12],
                'target_revision': target[:12], 'version': version.group(1) if version else 'Unknown',
                'available': current != target, 'changes': changes}
    except (OSError, subprocess.SubprocessError) as exc:
        raise updates.UpdateError('Could not check the selected branch. Check the device connection and try again.') from exc
