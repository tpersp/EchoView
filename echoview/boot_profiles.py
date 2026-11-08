"""Preview, apply and restore explicit Raspberry Pi 3 full-KMS video profiles."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
import uuid

PROFILES = ("keep", "hdmi", "composite-pal", "composite-ntsc")
START = "# BEGIN EchoView video profile: "
END = "# END EchoView video profile"
DISABLED = "# EchoView disabled: "
FILES = ("config.txt", "cmdline.txt")
CONTROLLED = {"enable_tvout", "disable_fw_kms_setup", "hdmi_force_hotplug", "hdmi_ignore_hotplug",
              "hdmi_group", "hdmi_mode", "hdmi_force_mode", "hdmi_timings", "sdtv_mode", "sdtv_aspect",
              "sdtv_disable_colourburst"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def plan_profile(config, cmdline, profile):
    """Pure text transformation. Unrelated directives and section headers survive."""
    if profile not in PROFILES:
        raise ValueError("Unknown video profile.")
    if profile == "keep":
        return config, cmdline
    if len(cmdline.splitlines()) != 1 or not cmdline.strip():
        raise ValueError("cmdline.txt must contain exactly one non-empty kernel command line.")
    newline = "\r\n" if "\r\n" in config else "\n"
    lines = config.splitlines(keepends=True)
    parameters = {}
    clean = []
    managed = False
    starts = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(START):
            if managed or starts:
                raise ValueError("Duplicate video-profile blocks; review config.txt first.")
            starts += 1
            managed = True
            continue
        if stripped == END:
            if not managed:
                raise ValueError("Unmatched video-profile marker.")
            managed = False
            continue
        active = stripped.split("#", 1)[0].strip()
        if re.match(r"include(?:\s|=)", active) or re.match(r"(?:cmdline|os_prefix)\s*=", active):
            raise ValueError("Includes or custom boot paths require manual review; no files changed.")
        overlay = re.match(r"dtoverlay\s*=\s*(vc4-(?:f?kms)-v3d[^,\s]*)(.*)$", active)
        if overlay:
            if overlay[1] != "vc4-kms-v3d":
                raise ValueError("This helper supports the standard vc4-kms-v3d overlay only; migrate custom/FKMS overlays separately.")
            for parameter in overlay[2].lstrip(",").split(","):
                parameter = parameter.strip()
                if not parameter:
                    continue
                key = parameter.split("=", 1)[0]
                if key in ("composite", "nohdmi", "nohdmi0", "nohdmi1"):
                    continue
                if key in parameters and parameters[key] != parameter:
                    raise ValueError("Conflicting KMS parameters require manual review.")
                parameters[key] = parameter
        if managed:
            continue
        assignment = re.match(r"([a-zA-Z0-9_]+)(?::[0-9]+)?\s*=", active)
        if overlay or (assignment and assignment[1] in CONTROLLED):
            clean.append(DISABLED + line)
        else:
            clean.append(line)
    if managed:
        raise ValueError("Unterminated video-profile block.")
    if sum(key.startswith("cma-") for key in parameters) > 1:
        raise ValueError("Conflicting CMA sizes require manual review.")
    composite = profile.startswith("composite-")
    params = list(parameters.values()) + (["composite", "nohdmi"] if composite else [])
    overlay_line = "dtoverlay=vc4-kms-v3d" + ("," + ",".join(params) if params else "")
    if len(overlay_line) > 98:
        raise ValueError("KMS directive exceeds firmware's 98-character line limit.")
    block = [START + profile, "[all]", overlay_line, f"enable_tvout={int(composite)}"]
    if composite:
        block.append("disable_fw_kms_setup=1")
    block.append(END)
    result_config = "".join(clean).rstrip("\r\n") + newline + newline.join(block) + newline
    # Preserve non-video kernel arguments and their ordering. Remove conflicting
    # HDMI/Composite overrides; no firmware sdtv settings are used under KMS.
    # Keep quoted values intact (for example a root label containing spaces).
    token_pattern = re.compile(r"""(?:[^\s"'\\]+|\\.|"(?:\\.|[^"\\])*"|'[^']*')+""")
    tokens = []
    position = 0
    for match in token_pattern.finditer(cmdline):
        if cmdline[position:match.start()].strip():
            raise ValueError("Malformed quoting in kernel command line; no files changed.")
        position = match.end()
        token = match[0]
        if not token.startswith("vc4.tv_norm=") and not re.match(r"video=(?:HDMI-A-\d+|Composite-\d+):", token):
            tokens.append(token)
    if cmdline[position:].strip():
        raise ValueError("Malformed quoting in kernel command line; no files changed.")
    if composite:
        tokens.append("vc4.tv_norm=" + ("PAL" if profile == "composite-pal" else "NTSC"))
    result_cmdline = " ".join(tokens) + ("\r\n" if cmdline.endswith("\r\n") else "\n")
    return result_config, result_cmdline


def detect_boot_dir():
    for directory in (Path("/boot/firmware"), Path("/boot")):
        if all((directory / name).is_file() for name in FILES):
            return directory
    raise ValueError("Cannot locate config.txt and cmdline.txt; specify --boot-dir for a mounted boot partition.")


def read_boot(directory):
    values = {}
    for name in FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected a regular, non-symlink {name} in the boot directory.")
        values[name] = path.read_bytes()
    return values


def preview(directory, before, after):
    for name in FILES:
        diff = difflib.unified_diff(before[name].decode().splitlines(keepends=True),
                                   after[name].decode().splitlines(keepends=True),
                                   fromfile=str(directory / name), tofile=str(directory / name) + " (planned)")
        sys.stdout.writelines(diff)


def atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".echoview-video-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_pair(directory, before, after):
    """Rollback ordinary write failures; persistent backups handle power loss."""
    changed = []
    try:
        for name in FILES:
            if before[name] != after[name]:
                atomic_write(directory / name, after[name])
                changed.append(name)
    except OSError:
        for name in reversed(changed):
            atomic_write(directory / name, before[name])
        raise


def apply_profile(directory, profile, dry_run=False):
    if profile == "keep":
        print("Video profile preserved; boot files unchanged.")
        return None
    directory = Path(directory)
    before = read_boot(directory)
    config, cmdline = plan_profile(before["config.txt"].decode(), before["cmdline.txt"].decode(), profile)
    after = {"config.txt": config.encode(), "cmdline.txt": cmdline.encode()}
    preview(directory, before, after)
    if before == after:
        print("Video profile already applied; no changes or backup needed.")
        return None
    if dry_run:
        print("Dry run: no files or backups written.")
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    backup = directory / "echoview-video-backups" / stamp
    backup.mkdir(parents=True, mode=0o700)
    for name in FILES:
        with (backup / name).open("xb") as target:
            target.write(before[name])
            target.flush()
            os.fsync(target.fileno())
    manifest = {"version": 1, "profile": profile, "files": {
        name: {"before": digest(before[name]), "after": digest(after[name])} for name in FILES}}
    with (backup / "manifest.json").open("x") as target:
        json.dump(manifest, target, indent=2)
        target.flush()
        os.fsync(target.fileno())
    if read_boot(directory) != before:
        raise ValueError("Boot files changed during preview; aborting without applying profile.")
    print(f"Recovery backup: {backup}")
    write_pair(directory, before, after)
    print(f"Applied {profile}. Reboot required; no reboot performed by this helper.")
    return backup


def restore_profile(directory, backup, dry_run=False, force=False):
    directory, backup = Path(directory), Path(backup)
    manifest = json.loads((backup / "manifest.json").read_text())
    if (not isinstance(manifest, dict) or manifest.get("version") != 1
            or not isinstance(manifest.get("files"), dict)
            or set(manifest["files"]) != set(FILES)):
        raise ValueError("Invalid backup manifest.")
    current = read_boot(directory)
    original = read_boot(backup)
    for name in FILES:
        hashes = manifest["files"][name]
        if (not isinstance(hashes, dict) or set(hashes) != {"before", "after"}
                or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                           for value in hashes.values())):
            raise ValueError("Invalid backup file hashes.")
        if digest(original[name]) != hashes["before"]:
            raise ValueError("Backup integrity check failed; no files restored.")
        if not force and digest(current[name]) not in (hashes["before"], hashes["after"]):
            raise ValueError("Boot files have newer edits; review the diff with --dry-run --force-restore before restoring.")
    preview(directory, current, original)
    if dry_run:
        print("Dry run: no files restored.")
        return
    write_pair(directory, current, original)
    print("Original boot files restored. Reboot required; no reboot performed by this helper.")


def validate_model(profile):
    if profile == "keep":
        return
    try:
        model = Path("/proc/device-tree/model").read_text().rstrip("\x00\n")
    except OSError:
        model = ""
    if not model.startswith("Raspberry Pi 3 Model "):
        raise ValueError("Explicit profiles currently target Raspberry Pi 3 only. For offline review use --boot-dir with the Pi 3 boot partition.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--profile", choices=PROFILES, default="keep")
    actions.add_argument("--restore", type=Path, metavar="BACKUP_DIR")
    parser.add_argument("--boot-dir", type=Path, help="Explicit Pi 3 boot partition, including an offline mounted card")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-restore", action="store_true", help="Explicitly allow overwriting newer edits when restoring a verified backup")
    args = parser.parse_args(argv)
    if args.force_restore and not args.restore:
        parser.error("--force-restore requires --restore")
    try:
        if not args.restore and args.profile == "keep":
            apply_profile(None, "keep", args.dry_run)
            return 0
        if not args.boot_dir and not args.restore:
            validate_model(args.profile)
        directory = args.boot_dir or detect_boot_dir()
        if args.restore:
            restore_profile(directory, args.restore, args.dry_run, args.force_restore)
        else:
            apply_profile(directory, args.profile, args.dry_run)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
