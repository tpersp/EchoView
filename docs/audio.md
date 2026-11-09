# Audio setup and troubleshooting

EchoView's installer sets up the audio service as well as client libraries.
On Raspberry Pi OS Lite, libraries alone can allow video to play without a
working default audio output. Both the server and the viewer's user-session
connection are required.

## Installation behavior

- Without an installed PulseAudio server, setup installs PipeWire,
  pipewire-pulse, WirePlumber and RTKit. The PulseAudio compatibility service
  supports applications that use the PulseAudio API.
- An existing PulseAudio installation is retained instead of being replaced by
  a conflicting server. Its user socket is enabled.
- Services are enabled for the configured viewer account. If it has not logged
  in yet, setup starts its systemd user manager and waits up to ten seconds for
  the user bus. It then enables, starts and checks audio services. The installer
  includes `dbus-user-session`; a missing bus is reported as a setup failure.
- The viewer service receives the matching `XDG_RUNTIME_DIR` and
  `DBUS_SESSION_BUS_ADDRESS`, allowing Qt, mpv and Chromium to reach user audio.
- New PipeWire output routes default to nominal 100% line level through
  `~/.config/wireplumber/wireplumber.conf.d/60-echoview-audio.conf`.
  Saved route volumes, mute states and default output selections take precedence.
  Existing copies of this configuration file are left untouched.

Setup does not force HDMI, analog or USB output globally. WirePlumber chooses
among available devices and restores saved choices. With only composite output
active on a Pi with an AV jack, the analog Headphones device is normally the
available local output. Changes to cables or available devices may require a
manual output selection.

The volume fallback applies only when no previous route volume is stored; it
avoids combining a heavily attenuated OS default with the application's volume.
See [WirePlumber's route-volume settings](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/settings.html#device-routes-default-sink-volume).
Application mute and volume controls continue to apply. Local videos and YouTube
have separate mute controls; unmute the media and set its desired volume in the
controller. GIFs and the calibration pattern do not contain audio. Spotify mode
shows playback information; it does not itself receive Spotify audio.

## Check the output

Run these as the viewer user in its session:

```bash
systemctl --user status pipewire pipewire-pulse wireplumber
wpctl status
wpctl get-volume @DEFAULT_AUDIO_SINK@
```

For an existing PulseAudio setup, check `pulseaudio.socket` instead. On PipeWire,
select a listed output with `wpctl set-default <sink-id>`. If appropriate, unmute
with `wpctl set-mute @DEFAULT_AUDIO_SINK@ 0` and adjust the OS volume, for example
`wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0` for nominal line level. These commands
change the selected output or level; keep the TV/amplifier and application volume
at a comfortable setting.

`aplay -l` identifies ALSA hardware. A Pi's analog jack generally appears as
`Headphones`; card numbers can change, so use names rather than hard-coded
indices. A direct ALSA test can isolate the physical connection from the audio
server, but the device may be busy while PipeWire owns it. See the
[Raspberry Pi media documentation](https://www.raspberrypi.com/documentation/computers/os.html#playing-audio-and-video).

If the selected sink receives an active audio stream but the TV stays silent,
check both OS and application mute/volume, the source's audio track, AV cable
pinout, modulator audio input and TV sound-system compatibility. An internal
transmitter test image does not verify the incoming audio cable.

## Validation limits

Mocked installer tests cover package choice, fresh-user manager startup,
active-session startup, failure propagation and preservation of saved settings.
On-device checks cover repeated setup against an existing PipeWire session. Actual analog video audio has been heard
through a connected display chain. A fresh-image installation and cold-boot audio
check remain release validation tasks.
