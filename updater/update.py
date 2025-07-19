import os
import subprocess

REPO_URL = "https://github.com/tpersp/EchoView.git"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(cmd: str):
    return subprocess.run(cmd, shell=True, cwd=ROOT_DIR,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          text=True)


def perform_update():
    """Update application from the upstream GitHub repository.

    JSON files are backed up and restored so user settings remain.
    Any local changes are discarded.
    """
    backups = {}
    for dirpath, _, filenames in os.walk(ROOT_DIR):
        for name in filenames:
            if name.endswith('.json'):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, ROOT_DIR)
                with open(full, 'rb') as fh:
                    backups[rel] = fh.read()

    # ensure remote exists
    res = _run('git remote get-url origin')
    if res.returncode != 0:
        _run(f'git remote add origin {REPO_URL}')

    # fetch and reset
    _run('git fetch origin')

    # try resetting to current branch, fall back to main/master
    branch_res = _run('git rev-parse --abbrev-ref HEAD')
    branch = branch_res.stdout.strip() or 'main'
    if _run(f'git reset --hard origin/{branch}').returncode != 0:
        _run('git reset --hard origin/main')
        _run('git reset --hard origin/master')

    _run('git clean -fd')

    # restore json files
    for rel, data in backups.items():
        path = os.path.join(ROOT_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(data)

    return True


if __name__ == '__main__':
    perform_update()
