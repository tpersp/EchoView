# Streaming setup and recovery

YouTube uses the original source URL at every mpv launch. Saving a source does
not perform extraction or persist a signed media manifest. Refresh metadata is
an explicit bounded oEmbed request. Legacy saved YouTube manifests are normalized
to the original source before playback.

## Optional player stack

On a supported Pi installation:

```bash
sudo ./setup.sh --with-streaming
```

This installs `requirements-streaming.txt`: yt-dlp 2026.10.26, yt-dlp-ejs 0.8.0
and the official Deno package 2.9.8, with shared constraints. mpv and ffmpeg are
native installer dependencies. Successful installation records `.streaming-enabled`
so later setup updates retain the optional stack. Failure stops setup before
recording success. For an existing development virtualenv:

```bash
.venv/bin/python -m pip install --only-binary=:all: -r requirements-streaming.txt
.venv/bin/python -m pip check
.venv/bin/python -m echoview.streaming --check
```

Diagnostics and `/streaming/status` report missing tools and package versions
without source URLs or executable paths. Playback inherits the session environment
and prepends the active virtualenv to PATH so mpv can find yt-dlp and Deno.
The runtime requirement follows the [yt-dlp EJS guidance](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## Playback behavior

YouTube prefers mpv when the complete optional stack is present. Extraction runs
in its player process, away from the GUI thread. Each interruption gets two retries
at 2 and 5 seconds; 60 seconds of stable playback resets that budget. A 30-second
loading watchdog and bounded network/extractor retries prevent indefinite startup.
A small bundled Lua observer reports fixed playback events without URLs. Switching
modes cancels pending retries and terminates the stream process group.

Normal finite videos end without retrying. Live streams retry interruptions.
Direct HLS uses Qt Multimedia with bounded startup and the same retry policy;
a provider's expired direct URL must be refreshed by its owner. No transcoding
or provider authentication is added.

Extracted YouTube formats prefer H.264/AAC and enforce the chosen quality height.
Default quality follows output height up to 1080p. Resource profiles do not
override the chosen video quality or disable playback. Quality availability and
playback remain dependent on the source.

## Browser fallback

Missing tools or exhausted YouTube retries fall back to a controller-served iframe.
Its real HTTP origin and referrer policy address YouTube's documented
[client identification requirement](https://developers.google.com/youtube/iframe_api_reference#onError).
The controller must be reachable at `http://127.0.0.1:8080`; a custom HTTP(S)
origin can be set with `ECHOVIEW_CONTROLLER_URL`. Unsupported handle-only embeds
show guidance to select external Chromium or supply a video/channel ID URL.
YouTube can still reject playback because of embedding permissions, account,
region or provider restrictions.

External Chromium is used only when its display checkbox is selected. It inherits
DISPLAY and XAUTHORITY and uses the installed browser identity and GPU defaults.
Set `ECHOVIEW_CHROMIUM_FLAGS` for custom Chromium options. Qt uses
`QTWEBENGINE_CHROMIUM_FLAGS`; only the exact historical shipped fake-UA/GPU flag
bundle is normalized. Existing custom settings remain intact. Fresh setup keeps
the Qt sandbox enabled; this restricted development container requires an explicit
`QTWEBENGINE_DISABLE_SANDBOX=1` override for offscreen smoke tests.

## Validation limits

Automated checks cover URL normalization, offline saving, iframe origins,
capabilities, quality selection, cancellation and retry behavior. Real mpv playback
of an offline fixture verifies the Lua observer; a real offscreen Qt viewer checks
queued delivery and watchdog cancellation. These checks do not establish live
YouTube/HLS playback, Pi decoding, browser embedding acceptance, audio output or
RCA/HDMI rendering. Those remain in the deferred hardware/service smoke tests.
