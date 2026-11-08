# Raspberry Pi 3 composite video boot profiles

The helper selects the boot output for a Raspberry Pi 3 using full KMS. It does
not yet provide a hardware-validated end-to-end CRT experience.
[Display settings](display-settings.md) and
[presentation settings](presentation-settings.md) supply connector assignment,
aspect correction, safe areas and calibration for later hardware testing. The supported installation
candidate remains Raspberry Pi OS Trixie 64-bit with X11; Pi hardware testing is
pending. Pi 4/5/Zero and custom/FKMS configurations need separate validation.

| Profile | Boot behavior |
| --- | --- |
| `keep` (default) | Preserve existing boot files byte-for-byte; no backup created |
| `hdmi` | Full KMS with HDMI detection; disable composite output |
| `composite-pal` | Full KMS composite, disable HDMI, select PAL |
| `composite-ntsc` | Full KMS composite, disable HDMI, select NTSC |

On-device explicit profiles are gated to Pi 3. The `--boot-dir` option explicitly
targets a Pi 3 boot partition for offline previews or recovery, including a card
mounted on another computer. It bypasses model detection, so select the intended
Pi 3 card yourself. No hardware output can be verified from a mounted card.

The KMS overlay uses `composite,nohdmi`, `enable_tvout=1` and
`disable_fw_kms_setup=1` for composite. The selected `vc4.tv_norm=PAL` or `NTSC`
is appended to the existing single-line kernel command line. It does not use
legacy `sdtv_mode` recipes. Sources:
[Raspberry Pi composite documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html#composite-video-mode),
[firmware overlay parameters](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README).

## Preview and select

First preview without sudo; this standalone path performs no package installs,
service changes, file writes or reboot:

```bash
python3 -m echoview.boot_profiles --profile composite-pal --dry-run
# Equivalent installer preview:
bash setup.sh --video-profile composite-pal --dry-run
```

Apply only the boot profile without rerunning setup:

```bash
sudo python3 -m echoview.boot_profiles --profile composite-pal
```

Or explicitly select it during initial setup or an update:

```bash
sudo bash setup.sh --video-profile composite-pal
sudo bash setup.sh --auto-update --video-profile composite-ntsc
```

Running normal setup or `--auto-update` without `--video-profile` keeps the
existing output configuration, including a manually configured composite mode.
Repeated application of the same profile makes no further edits or backups.
Auto-update and the standalone helper do not reboot; reboot the Pi explicitly
when ready. Initial setup retains its existing final reboot behavior.

Preview against an offline card or fixture directory:

```bash
python3 -m echoview.boot_profiles --boot-dir /path/to/pi3-boot --profile composite-pal --dry-run
```

The helper auto-detects `/boot/firmware` and then `/boot` when `--boot-dir` is
omitted. Both `config.txt` and `cmdline.txt` must be regular, non-symlink files.

## What changes

Explicit selection disables conflicting active video directives by commenting
them, then adds a clearly marked `[all]` profile block. This includes forced HDMI
hotplug/resolution, legacy composite settings and old KMS directives. Unrelated
settings, section headers and ordinary KMS options (for example `cma-128`) remain.
The new profile applies globally to this boot card; device-specific video
conditional settings are replaced too. Review the diff before applying it to a
custom multi-model card. `hdmi` means automatic HDMI/KMS configuration, not exact
restoration of your old custom HDMI settings; use the backup for exact recovery.

The helper removes existing HDMI-A/Composite connector overrides and duplicate
`vc4.tv_norm` arguments from the kernel command line; root/console and other
connector arguments retain their ordering. Kernel whitespace is normalized to
one line. `include`, custom `cmdline`/`os_prefix`, FKMS/custom KMS overlays,
conflicting CMA settings, malformed managed blocks or multi-line kernel command
lines fail before any backup or boot edits. Review these custom configurations
manually instead of assuming the helper can interpret their dependencies.

## Backups and recovery

Each change prints a fresh backup path under the selected boot partition:

```text
echoview-video-backups/TIMESTAMP-UNIQUE_ID/
```

It contains exact original bytes for both boot files and a SHA-256 manifest
covering originals and applied files. Existing backups are never overwritten.
Each target file is replaced atomically. Ordinary write errors trigger rollback;
a power loss cannot atomically cover both files, so keep the printed backup path
and use restoration if interrupted. Boot files should not be edited concurrently
with this helper.

Preview and restore that backup:

```bash
sudo python3 -m echoview.boot_profiles --restore /boot/firmware/echoview-video-backups/BACKUP --dry-run
sudo python3 -m echoview.boot_profiles --restore /boot/firmware/echoview-video-backups/BACKUP
# Equivalent standalone installer recovery:
sudo bash setup.sh --restore-video /boot/firmware/echoview-video-backups/BACKUP
```

Restoration verifies backup contents first and accepts original/applied states
(including a partial write). If files contain newer manual edits or later
profiles, it refuses to overwrite them. Review with `--dry-run --force-restore`
and, only if desired, explicitly restore with `--force-restore`. To recover
without a working display, SSH into the Pi or mount the card on another computer
and add `--boot-dir /path/to/mounted-boot`. Restore steps do not run the full
installer, require the application environment, or reboot automatically.

To switch back to standard HDMI without restoring old custom settings:

```bash
sudo python3 -m echoview.boot_profiles --profile hdmi
```

## Hardware validation still required

Use a Pi-compatible 3.5 mm TRRS AV-to-RCA cable with the correct pinout; generic
AV cables can differ. Verify the TV's PAL/NTSC support. Composite audio routing
is separate and unchanged by these video profiles.

For both PAL and NTSC: cold-boot a Pi 3 with the TV connected, verify HDMI is
inactive, inspect the reported connector/mode, test an OS calibration image,
then test EchoView images/GIFs and video. Check for colour, stable sync and
cropping. Repeat setup/update with the default `keep` profile, restore the
backup, and verify HDMI after a cold boot. These checks are pending; fixture
and recovery tests prove file handling, not the electrical video signal.
