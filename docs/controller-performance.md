# Responsive media browsing

The controller now renders folder names first and loads one folder at a time,
with at most 48 files per page. Folder search runs locally; filename search and
sorting operate on the selected directory. The current folder and sort order
are reflected in the URL, and the last open folder is remembered in the browser
session. Folder scans are fresh on each request; there is no persistent NAS index
to invalidate. Opening a slow or unavailable folder shows loading/retry feedback
without blocking the navigation page.

Closing a folder cancels its outstanding request, releases previews and stops
videos. Video elements request no preload; images use lazy loading and async
decoding. See the documented
[video preload behavior](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/video#preload).

Displays opens directly to playback controls. Resolution and safe-area forms
remain available in the collapsed output section below. Specific-image choices
load only when that mode or fallback is visible, with search and batches of 48.
A separate hidden form field preserves the saved image when it is outside the
loaded page. Changing folder or aspect reloads choices without submitting or
restarting the viewer. Applying changes still saves settings and restarts the
viewer as before; the button now gives immediate progress feedback.

Display navigation no longer scans every directory for file counts or image
headers. Counts are shown in the selected media folder instead. Stats sampling
runs through the existing asynchronous stats request after DOMContentLoaded,
not during initial page rendering. UI CSS and fonts are bundled locally at the
same versions as before; no third-party CDN or unused Bootstrap JS blocks the
navigation scripts. See
[DOMContentLoaded guidance](https://developer.mozilla.org/en-US/docs/Web/API/Document/DOMContentLoaded_event).

## Pi measurements

Measured on the user's Pi with its existing NAS mount, during HDMI playback:

| Initial request | Before | Revised |
| --- | ---: | ---: |
| Media HTML payload | 2,066,023 bytes | 8,464 bytes |
| Media server response | 0.388 s | 0.031 s |
| Media HTML elements | 20,795 | 124 |
| Media initial video elements | 524 | 0 |
| Displays server response | 0.683 s | 0.252 s |

These are individual observations, not guarantees of browser latency or cold
NAS performance. Browser preview tests through SSH opened the first folder in
about 0.8 s. Media-content requests were blocked during that test; it measures
directory browsing, not thumbnail generation or video playback. The revised
page was staged in a separate loopback-only controller with copied settings;
the live viewer continued playing. No NAS media was changed.

## Verification

Route/helper tests cover pagination, sorting, filename search, ignored folders,
invalid paths, symlink containment, missing mounts, URL encoding and deferred
media/stats work. Real Chromium checks with synthetic files cover folder
open/close, remembered state, pagination, search, error/retry, selected-image
preservation, special characters and absence of automatic video requests. A
separate browser check exercised read-only browsing against the Pi's NAS mount.

Large-directory enumeration and aspect inspection can still take time when
explicitly requested. Thumbnail generation remains a separate optimization
opportunity; this change first removes unnecessary bulk work and network traffic.
