#!/usr/bin/env bash
# Wait for the configured X session to answer, including authentication.
set -eu
attempts="${ECHOVIEW_DISPLAY_WAIT_SECONDS:-60}"
[[ "$attempts" =~ ^[0-9]+$ && "$attempts" -ge 1 && "$attempts" -le 120 ]] || {
  echo 'ECHOVIEW_DISPLAY_WAIT_SECONDS must be 1–120.' >&2; exit 1;
}
deadline=$((SECONDS + attempts))
while ((SECONDS < deadline)); do
  if timeout 1 xrandr --query >/dev/null 2>&1; then exit 0; fi
  sleep 1
done
echo "X display did not become ready; check DISPLAY, XAUTHORITY and LightDM in the service environment." >&2
exit 1
