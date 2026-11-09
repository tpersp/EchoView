"""Bounded update stages. Callers report the failing stage without command output."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from echoview.branches import valid_branch


class UpdateError(RuntimeError):
    pass


def run(args, cwd=None, timeout=60):
    return subprocess.run(args, cwd=cwd, timeout=timeout, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def restart_services():
    try:
        run(['sudo', '-n', 'systemctl', 'restart', 'echoview.service'], timeout=100)
        run(['sudo', '-n', 'systemctl', 'is-active', '--quiet', 'echoview.service'])
        # Never wait for the controller to terminate its own request worker.
        run(['sudo', '-n', 'systemctl', '--no-block', 'restart', 'controller.service'])
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError('Service restart failed. Inspect the service journal and retry.') from exc


def update(repo, branch, config_path, token_path, reboot=False):
    if not valid_branch(branch):
        raise UpdateError("Invalid update branch.")
    repo = Path(repo)
    stage = 'Update lock'
    try:
        with (repo / '.update.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UpdateError('Another update is already running.') from exc
            stage = 'Configuration backup'
            if not (repo / '.env').is_file():
                raise UpdateError('Existing .env is missing; restore it before updating.')
            # Never allow reset to overwrite tracked installation data or local work.
            stage = 'Checkout validation'
            if run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=repo).stdout.strip():
                raise UpdateError('Local tracked changes exist. Save them before updating.')
            files = [repo / '.env', Path(config_path), Path(token_path)]
            for path in files:
                if path.is_relative_to(repo):
                    tracked = run(['git', 'ls-files', '--', str(path.relative_to(repo))], cwd=repo).stdout.strip()
                    if tracked:
                        raise UpdateError('Installation configuration is tracked by Git; move it out before updating.')
            stage = 'Configuration backup'
            backup_root = repo / '.update-backups'
            backup_root.mkdir(mode=0o700, exist_ok=True)
            os.chmod(backup_root, 0o700)
            backup = Path(tempfile.mkdtemp(prefix='before-', dir=backup_root))
            for index, path in enumerate(files):
                if path.is_file():
                    target = backup / f'{index}-{path.name}'
                    shutil.copyfile(path, target)
                    target.chmod(0o600)
            stage = 'Git fetch'
            run(['git', 'fetch', 'origin', f'+refs/heads/{branch}:refs/remotes/origin/{branch}'], cwd=repo, timeout=180)
            revision = run(['git', 'rev-parse', '--verify', f'refs/remotes/origin/{branch}^{{commit}}'], cwd=repo).stdout.strip()
            for path in files:
                if path.is_relative_to(repo):
                    if run(['git', 'ls-tree', '--name-only', revision, '--', str(path.relative_to(repo))], cwd=repo).stdout.strip():
                        raise UpdateError('Target revision tracks installation configuration; update refused.')
            previous = run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
            (backup / 'previous-revision').write_text(previous + '\n')
            stage = 'Git reset'
            run(['git', 'reset', '--hard', revision], cwd=repo)
            # Always reconcile dependencies: requirements/constraints/helpers can change alone.
            stage = 'Installer'
            run(['sudo', '-n', 'bash', 'setup.sh', '--auto-update'], cwd=repo, timeout=1800)
            stage = 'Reboot request' if reboot else 'Service restart'
            if reboot:
                run(['sudo', '-n', 'systemctl', '--no-block', 'reboot'])
            else:
                restart_services()
            return backup.name
    except UpdateError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError(f'{stage} failed. No completion was reported; inspect logs and the private .update-backups directory.') from exc
