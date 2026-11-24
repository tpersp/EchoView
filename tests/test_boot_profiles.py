from pathlib import Path
import subprocess

import pytest

from echoview import boot_profiles as boot

FIXTURE = Path(__file__).parent / "fixtures" / "boot"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def partition(tmp_path):
    for name in boot.FILES:
        (tmp_path / name).write_bytes((FIXTURE / name).read_bytes())
    return tmp_path


def originals(directory):
    return {name: (directory / name).read_bytes() for name in boot.FILES}


def active(text):
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


@pytest.mark.parametrize("profile,norm", [("composite-pal", "PAL"), ("composite-ntsc", "NTSC")])
def test_composite_profile_preserves_sections_and_kernel_boot_args(profile, norm):
    config, cmdline = boot.plan_profile((FIXTURE / "config.txt").read_text(), (FIXTURE / "cmdline.txt").read_text(), profile)
    directives = active(config)
    assert directives.count("dtoverlay=vc4-kms-v3d,cma-128,composite,nohdmi") == 1
    assert "enable_tvout=1" in directives
    assert "disable_fw_kms_setup=1" in directives
    assert not any(line.startswith(("hdmi_force_hotplug", "sdtv_mode")) for line in directives)
    assert "[cm4]\notg_mode=1\n[all]\narm_boost=1\n" in config
    assert "dtparam=audio=on" in directives
    assert f"vc4.tv_norm={norm}" in cmdline
    assert "video=HDMI" not in cmdline
    assert "root=PARTUUID=fixture-root" in cmdline and "rootwait" in cmdline
    assert len(cmdline.splitlines()) == 1


@pytest.mark.parametrize("profile", ["hdmi", "composite-pal", "composite-ntsc"])
def test_repeated_transforms_are_idempotent(profile):
    first = boot.plan_profile((FIXTURE / "config.txt").read_text(), (FIXTURE / "cmdline.txt").read_text(), profile)
    assert boot.plan_profile(*first, profile) == first


def test_hdmi_switch_removes_composite_and_preserves_kms_parameters():
    pal = boot.plan_profile((FIXTURE / "config.txt").read_text(), (FIXTURE / "cmdline.txt").read_text(), "composite-pal")
    config, cmdline = boot.plan_profile(*pal, "hdmi")
    assert "dtoverlay=vc4-kms-v3d,cma-128" in active(config)
    assert not any("composite" in value or "nohdmi" in value for value in active(config))
    assert "enable_tvout=0" in active(config)
    assert "vc4.tv_norm" not in cmdline
    assert boot.plan_profile(config, cmdline, "hdmi") == (config, cmdline)


def test_dry_run_creates_no_backups_or_edits(partition):
    before = originals(partition)
    boot.apply_profile(partition, "composite-pal", dry_run=True)
    assert originals(partition) == before
    assert sorted(path.name for path in partition.iterdir()) == sorted(boot.FILES)


def test_apply_repeat_and_restore_original_bytes(partition):
    before = originals(partition)
    (partition / "cmdline.txt").chmod(0o640)
    backup = boot.apply_profile(partition, "composite-pal")
    assert (partition / "cmdline.txt").stat().st_mode & 0o777 == 0o640
    assert originals(backup) == before
    assert boot.apply_profile(partition, "composite-pal") is None
    assert len(list((partition / "echoview-video-backups").iterdir())) == 1
    boot.restore_profile(partition, backup)
    assert originals(partition) == before


def test_backup_is_not_overwritten_on_profile_switch(partition):
    first = boot.apply_profile(partition, "composite-pal")
    first_bytes = originals(first)
    second = boot.apply_profile(partition, "composite-ntsc")
    assert first != second
    assert originals(first) == first_bytes
    boot.restore_profile(partition, second)
    assert "vc4.tv_norm=PAL" in (partition / "cmdline.txt").read_text()


def test_restore_dry_run_and_integrity(partition):
    backup = boot.apply_profile(partition, "hdmi")
    applied = originals(partition)
    boot.restore_profile(partition, backup, dry_run=True)
    assert originals(partition) == applied
    (backup / "config.txt").write_text("damaged backup")
    with pytest.raises(ValueError, match="integrity"):
        boot.restore_profile(partition, backup)
    assert originals(partition) == applied


def test_restore_rejects_new_edits_unless_explicitly_forced(partition):
    before = originals(partition)
    backup = boot.apply_profile(partition, "composite-pal")
    with (partition / "config.txt").open("a") as target:
        target.write("# newer edit\n")
    modified = originals(partition)
    with pytest.raises(ValueError, match="newer edits"):
        boot.restore_profile(partition, backup)
    boot.restore_profile(partition, backup, dry_run=True, force=True)
    assert originals(partition) == modified
    boot.restore_profile(partition, backup, force=True)
    assert originals(partition) == before


def test_write_failure_rolls_back_and_retains_recovery_backup(partition, monkeypatch):
    before = originals(partition)
    write = boot.atomic_write
    failed = []
    def fail_once(path, data):
        if path.name == "cmdline.txt" and not failed:
            failed.append(True)
            raise OSError("simulated write failure")
        write(path, data)
    monkeypatch.setattr(boot, "atomic_write", fail_once)
    with pytest.raises(OSError, match="simulated"):
        boot.apply_profile(partition, "composite-pal")
    assert originals(partition) == before
    backups = list((partition / "echoview-video-backups").iterdir())
    assert len(backups) == 1 and (backups[0] / "manifest.json").exists()
    assert not list(partition.glob(".echoview-video-*"))


def test_partial_application_can_be_restored_after_interruption(partition):
    before = originals(partition)
    backup = boot.apply_profile(partition, "composite-pal")
    (partition / "cmdline.txt").write_bytes(before["cmdline.txt"])
    boot.restore_profile(partition, backup)
    assert originals(partition) == before


@pytest.mark.parametrize("config", ["include usercfg.txt\n", "cmdline=custom.txt\n", "os_prefix=custom/\n", "dtoverlay=vc4-fkms-v3d\n", "dtoverlay=vc4-kms-v3d-pi4\n", boot.START + "hdmi\n", boot.END + "\n", "dtoverlay=vc4-kms-v3d,cma-128,cma-256\n"])
def test_ambiguous_config_rejected_before_any_write(partition, config):
    (partition / "config.txt").write_text(config)
    before = originals(partition)
    with pytest.raises(ValueError):
        boot.apply_profile(partition, "composite-pal")
    assert originals(partition) == before
    assert not (partition / "echoview-video-backups").exists()


@pytest.mark.parametrize("cmdline", ["", "root=test\nquiet\n"])
def test_invalid_kernel_command_line_is_rejected(cmdline):
    with pytest.raises(ValueError, match="one non-empty"):
        boot.plan_profile("[all]\n", cmdline, "hdmi")


def test_crlf_and_missing_final_config_newline():
    for config in ("[all]\r\ndtoverlay=vc4-kms-v3d\r\n", "[all]\ndtoverlay=vc4-kms-v3d"):
        result = boot.plan_profile(config, "root=test\r\n", "composite-pal")
        assert result[1].endswith("\r\n")
        assert boot.plan_profile(*result, "composite-pal") == result


def test_keep_is_byte_preserving_without_requiring_boot_files(tmp_path):
    assert boot.plan_profile("original\r\n", "", "keep") == ("original\r\n", "")
    assert boot.apply_profile(None, "keep") is None
    assert not list(tmp_path.iterdir())


def test_symlink_boot_files_are_rejected(partition, tmp_path_factory):
    target = tmp_path_factory.mktemp("target") / "config.txt"
    target.write_text("[all]\n")
    (partition / "config.txt").unlink()
    (partition / "config.txt").symlink_to(target)
    with pytest.raises(ValueError, match="non-symlink"):
        boot.apply_profile(partition, "hdmi")


def test_installer_dry_run_is_standalone_and_does_not_write(partition):
    before = originals(partition)
    result = subprocess.run(["bash", str(ROOT / "setup.sh"), "--video-profile", "composite-pal", "--boot-dir", str(partition), "--dry-run"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "composite,nohdmi" in result.stdout and "Dry run" in result.stdout
    assert originals(partition) == before
    assert not (partition / "echoview-video-backups").exists()


def test_installer_rejects_unknown_profile_without_mutation(partition):
    before = originals(partition)
    result = subprocess.run(["bash", str(ROOT / "setup.sh"), "--video-profile", "invalid", "--boot-dir", str(partition), "--dry-run"], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert originals(partition) == before


def test_model_gate_rejects_non_pi3(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda self: "Raspberry Pi 4 Model B Rev 1.5\x00")
    with pytest.raises(ValueError, match="Pi 3 only"):
        boot.validate_model("composite-pal")
    boot.validate_model("keep")


def test_boot_path_detection_prefers_firmware_then_legacy(monkeypatch):
    monkeypatch.setattr(Path, "is_file", lambda path: str(path).startswith("/boot/firmware/"))
    assert boot.detect_boot_dir() == Path("/boot/firmware")
    monkeypatch.setattr(Path, "is_file", lambda path: str(path) in ("/boot/config.txt", "/boot/cmdline.txt"))
    assert boot.detect_boot_dir() == Path("/boot")


def test_other_connector_overrides_are_preserved():
    config, cmdline = boot.plan_profile("dtoverlay=vc4-kms-v3d\n", "root=fixture video=DSI-1:800x480 video=Composite-1:720x576e vc4.tv_norm=NTSC vc4.tv_norm=PAL\n", "composite-pal")
    assert "video=DSI-1:800x480" in cmdline
    assert "video=Composite-1:" not in cmdline
    assert cmdline.count("vc4.tv_norm=") == 1


@pytest.mark.parametrize("manifest", ["[]", '{"version": 1, "files": {"config.txt": {}, "cmdline.txt": {}}}'])
def test_invalid_backup_manifest_rejected_without_edits(partition, manifest):
    backup = boot.apply_profile(partition, "composite-pal")
    applied = originals(partition)
    (backup / "manifest.json").write_text(manifest)
    with pytest.raises(ValueError, match="Invalid backup"):
        boot.restore_profile(partition, backup)
    assert originals(partition) == applied


def test_installer_restore_is_standalone_without_system_setup(partition):
    before = originals(partition)
    backup = boot.apply_profile(partition, "composite-pal")
    applied = originals(partition)
    preview = subprocess.run(["bash", str(ROOT / "setup.sh"), "--restore-video", str(backup), "--boot-dir", str(partition), "--dry-run"], capture_output=True, text=True, timeout=10)
    assert preview.returncode == 0, preview.stderr
    assert originals(partition) == applied
    restore = subprocess.run(["bash", str(ROOT / "setup.sh"), "--restore-video", str(backup), "--boot-dir", str(partition)], capture_output=True, text=True, timeout=10)
    assert restore.returncode == 0, restore.stderr
    assert originals(partition) == before


def test_quoted_kernel_arguments_preserve_internal_whitespace():
    _, cmdline = boot.plan_profile("dtoverlay=vc4-kms-v3d\n", 'root="LABEL=My  Disk" console=tty1 video=HDMI-A-1:1920x1080D\n', "composite-pal")
    assert 'root="LABEL=My  Disk"' in cmdline
    assert "console=tty1" in cmdline
    assert "video=HDMI" not in cmdline


def test_malformed_kernel_quotes_are_rejected():
    with pytest.raises(ValueError, match="Malformed quoting"):
        boot.plan_profile("[all]\n", 'root="LABEL=unfinished\n', "composite-pal")
