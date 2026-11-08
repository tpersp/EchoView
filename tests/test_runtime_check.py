import os
from pathlib import Path
import subprocess

from echoview.runtime_check import compatibility_errors

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/setup-runtime.sh"


def test_arm_bookworm_rejected_before_install():
    errors = compatibility_errors("Linux", "aarch64", (3, 11), (2, 36), {"ID": "debian", "VERSION_CODENAME": "bookworm"}, True)
    assert any("glibc 2.39" in error for error in errors)
    assert any("Trixie" in error for error in errors)


def test_trixie_arm64_target_and_development_host():
    assert not compatibility_errors("Linux", "aarch64", (3, 13), (2, 41), {"ID": "debian", "VERSION_CODENAME": "trixie"}, True)
    assert not compatibility_errors("Linux", "x86_64", (3, 12), (2, 39), {"ID": "ubuntu"})
    assert compatibility_errors("Linux", "x86_64", (3, 12), (2, 39), {"ID": "ubuntu"}, True)


def test_unsupported_architecture_python_and_libc():
    assert compatibility_errors("Linux", "armv7l", (3, 11), (2, 36), {})
    assert compatibility_errors("Linux", "aarch64", (3, 10), (2, 41), {})
    assert compatibility_errors("Linux", "aarch64", (3, 14), (2, 41), {})
    assert compatibility_errors("Linux", "aarch64", (3, 13), (), {})


def fake_runtime(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("-r requirements-base.txt\n")
    (repo / "requirements-base.txt").write_text("Flask==3.1.3\n")
    (repo / "constraints.txt").write_text("Flask==3.1.3\n")
    runtime = tmp_path / "venv"
    (runtime / "bin").mkdir(parents=True)
    executable = runtime / "bin/python3"
    executable.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$TASK_LOG"
case "$*" in
  *"pip install --only-binary"*) exit "${TASK_INSTALL_RESULT:-0}" ;;
esac
exit 0
''')
    executable.chmod(0o755)
    return repo, runtime, tmp_path / "commands.log"


def run_install(tmp_path, result):
    repo, runtime, log = fake_runtime(tmp_path)
    response = subprocess.run(["bash", "-c", 'source "$1"; install_python_runtime "$2" "$3"', "test", str(HELPER), str(runtime), str(repo)],
        env={**os.environ, "TASK_LOG": str(log), "TASK_INSTALL_RESULT": str(result)}, capture_output=True, text=True, timeout=10)
    return response, log.read_text()


def test_install_failure_stops_before_success_checks(tmp_path):
    response, commands = run_install(tmp_path, 42)
    assert response.returncode != 0
    assert "--only-binary=:all:" in commands
    assert "pip check" not in commands
    assert "--qt" not in commands


def test_install_verifies_environment(tmp_path):
    response, commands = run_install(tmp_path, 0)
    assert response.returncode == 0
    assert "--installer" in commands
    assert "pip check" in commands
    assert "--qt" in commands


def test_update_preserves_custom_configuration_and_non_pi_user(tmp_path):
    content = 'VIEWER_HOME="/custom/viewer"\nIMAGE_DIR="/custom/media"\nSPOTIFY_CACHE_PATH="/custom/token"\n'
    env_file = tmp_path / ".env"
    env_file.write_text(content)
    command = '''source "$1"
systemctl() { printf 'viewer\\n'; }
id() { printf '1001\\n'; }
unset VIEWER_USER
resolve_update_config "$2" || exit 1
printf '%s\\n' "$VIEWER_USER" "$VIEWER_HOME" "$IMAGE_DIR" "$SPOTIFY_CACHE_PATH"
'''
    result = subprocess.run(["bash", "-c", command, "test", str(HELPER), str(tmp_path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["viewer", "/custom/viewer", "/custom/media", "/custom/token"]
    assert env_file.read_text() == content


def test_update_missing_configuration_fails_without_creating_it(tmp_path):
    result = subprocess.run(["bash", "-c", 'source "$1"; resolve_update_config "$2"', "test", str(HELPER), str(tmp_path)], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not (tmp_path / ".env").exists()


def test_optional_stream_install_marks_only_success(tmp_path):
    repo, runtime, log = fake_runtime(tmp_path)
    (repo / "requirements-streaming.txt").write_text("yt-dlp==2026.10.26\n")
    command = 'source "$1"; install_streaming_runtime "$2" "$3"'
    for status in (42, 0):
        result = subprocess.run(["bash", "-c", command, "test", str(HELPER), str(runtime), str(repo)],
            env={**os.environ, "TASK_LOG": str(log), "TASK_INSTALL_RESULT": str(status)}, capture_output=True, text=True, timeout=10)
        if status:
            assert result.returncode != 0
            assert not (repo / ".streaming-enabled").exists()
        else:
            assert result.returncode == 0
            assert (repo / ".streaming-enabled").exists()
    assert "streaming.py --check" in log.read_text()
