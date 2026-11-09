"""Read-only update branch discovery from the checkout's origin remote."""
import os
import re
import subprocess
import threading
import time

_cache = {}
_lock = threading.Lock()


def valid_branch(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        return False
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*', value) or '..' in value or '//' in value:
        return False
    return all(part and not part.startswith('.') and not part.endswith(('.', '.lock')) for part in value.split('/'))


def selected_branch(cfg, default='main'):
    saved = cfg.get('update_branch')
    return saved if valid_branch(saved) else default if valid_branch(default) else 'main'


def branch_options(repo, selected, remote=False):
    """Settings render uses local refs; asynchronous refresh queries origin, bounded."""
    key = str(repo)
    with _lock:
        cached = _cache.get(key)
    names = {'main', 'dev', selected}
    if cached:
        names.update(cached[1])
    source = 'cached' if cached else 'local'
    available = True
    try:
        if remote and (not cached or time.monotonic() - cached[0] >= 60):
            result = subprocess.run(['git', 'ls-remote', '--heads', 'origin'], cwd=repo,
                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_SSH_COMMAND': 'ssh -o BatchMode=yes -o ConnectTimeout=5'},
                check=True, capture_output=True, text=True, timeout=8)
            discovered = {line.split('\t', 1)[1][len('refs/heads/'):] for line in result.stdout.splitlines()
                          if '\trefs/heads/' in line}
            source = 'origin'
            with _lock:
                _cache[key] = (time.monotonic(), {n for n in discovered if valid_branch(n)})
        elif not remote:
            result = subprocess.run(['git', 'for-each-ref', '--format=%(refname)', 'refs/remotes/origin/'],
                                    cwd=repo, check=True, capture_output=True, text=True, timeout=2)
            discovered = {line.removeprefix('refs/remotes/origin/') for line in result.stdout.splitlines()
                          if line.startswith('refs/remotes/origin/') and not line.endswith('/HEAD')}
        else:
            discovered = cached[1]
        names.update(n for n in discovered if valid_branch(n))
    except (OSError, subprocess.SubprocessError):
        available = False
    return {'branches': sorted(n for n in names if valid_branch(n)), 'selected': selected,
            'source': source, 'available': available}
