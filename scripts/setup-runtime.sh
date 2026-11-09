#!/usr/bin/env bash
# Source-only installer helpers. Sourcing this file changes no system settings.

install_python_runtime() {
  local runtime_venv="$1"
  local runtime_repo="$2"
  if [[ ! -f "$runtime_repo/requirements.txt" || ! -f "$runtime_repo/requirements-base.txt" || ! -f "$runtime_repo/constraints.txt" ]]; then
    echo "ERROR: Pinned requirements are missing; restore the complete checkout." >&2
    return 1
  fi
  if [[ ! -x "$runtime_venv/bin/python3" ]]; then
    python3 -m venv "$runtime_venv" || return 1
  fi
  "$runtime_venv/bin/python3" "$runtime_repo/echoview/runtime_check.py" --installer || return 1
  "$runtime_venv/bin/python3" -m pip install --upgrade pip || return 1
  # No source compilation fallback for unsupported Qt/architecture combinations.
  "$runtime_venv/bin/python3" -m pip install --only-binary=:all: -r "$runtime_repo/requirements.txt" || return 1
  "$runtime_venv/bin/python3" -m pip check || return 1
  "$runtime_venv/bin/python3" "$runtime_repo/echoview/runtime_check.py" --qt || return 1
}

resolve_update_config() {
  local runtime_repo="$1"
  local runtime_service_user
  ENV_FILE="$runtime_repo/.env"
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Auto-update requires the existing checkout's .env; no configuration was created." >&2
    return 1
  fi
  runtime_service_user="$(systemctl show echoview.service --property=User --value 2>/dev/null)"
  VIEWER_USER="${VIEWER_USER:-${runtime_service_user:-${SUDO_USER:-}}}"
  if [[ -z "$VIEWER_USER" || "$VIEWER_USER" == root ]] || ! id -u "$VIEWER_USER" >/dev/null 2>&1; then
    echo "ERROR: Cannot determine the viewer user; set VIEWER_USER explicitly." >&2
    return 1
  fi
  USER_ID="$(id -u "$VIEWER_USER")"
  # Existing .env is the service's trusted configuration; do not print its contents.
  set -a
  source "$ENV_FILE" || { set +a; return 1; }
  set +a
  if [[ -z "${VIEWER_HOME:-}" || -z "${IMAGE_DIR:-}" ]]; then
    echo "ERROR: Existing .env must define VIEWER_HOME and IMAGE_DIR." >&2
    return 1
  fi
}


install_streaming_runtime() {
  local stream_venv="$1"
  local stream_repo="$2"
  [[ -f "$stream_repo/requirements-streaming.txt" ]] || {
    echo "ERROR: Optional streaming requirements missing." >&2; return 1;
  }
  "$stream_venv/bin/python3" -m pip install --only-binary=:all: -r "$stream_repo/requirements-streaming.txt" || return 1
  "$stream_venv/bin/python3" -m pip check || return 1
  PATH="$stream_venv/bin:$PATH" "$stream_venv/bin/python3" "$stream_repo/echoview/streaming.py" --check || return 1
  printf '%s\n' 'Optional streaming stack enabled; preserve on updates.' > "$stream_repo/.streaming-enabled"
}

# Keep an installed PulseAudio server instead of replacing an existing stack.
audio_uses_pulseaudio() {
  [[ "$(dpkg-query -W -f='${Status}' pulseaudio 2>/dev/null)" == 'install ok installed' ]]
}

install_audio_runtime() {
  if audio_uses_pulseaudio; then
    apt-get install -y rtkit || return 1
  else
    apt-get install -y pipewire pipewire-pulse wireplumber rtkit || return 1
  fi
}

audio_session_ready() {
  [[ -S "/run/user/$1/bus" ]]
}

configure_user_audio() {
  local audio_user="$1" audio_uid="$2"
  local audio_home audio_config audio_group
  local -a audio_enable audio_start audio_command
  audio_home="$(getent passwd "$audio_user" | cut -d: -f6)"
  if [[ "$audio_home" != /* || ! "$audio_uid" =~ ^[0-9]+$ || "$audio_uid" == 0 ]]; then
    echo 'ERROR: Audio setup requires a valid non-root viewer account.' >&2
    return 1
  fi
  audio_command=(runuser -u "$audio_user" -- env
    "XDG_RUNTIME_DIR=/run/user/$audio_uid"
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$audio_uid/bus")
  if audio_uses_pulseaudio; then
    audio_enable=(pulseaudio.socket)
    audio_start=(pulseaudio.socket)
  else
    audio_enable=(pipewire.socket pipewire-pulse.socket wireplumber.service)
    audio_start=(pipewire.service pipewire-pulse.service wireplumber.service)
    audio_config="$audio_home/.config/wireplumber/wireplumber.conf.d/60-echoview-audio.conf"
    # Only sets the fallback for routes with no stored volume. Never reset
    # WirePlumber state or force an output device/volume during an upgrade.
    if [[ ! -e "$audio_config" && ! -L "$audio_config" ]]; then
      "${audio_command[@]}" mkdir -p "$(dirname "$audio_config")" || return 1
      (
        umask 022
        set -o noclobber
        cat > "$audio_config" <<'AUDIO_CONFIG'
# Default for new outputs only; saved per-route volumes take precedence.
wireplumber.settings = {
  device.routes.default-sink-volume = 1.0
}
AUDIO_CONFIG
      ) || return 1
      audio_group="$(id -gn "$audio_user")" || return 1
      chown "$audio_user:$audio_group" "$audio_config" || return 1
    fi
  fi
  # A new account may not have logged in yet. Start its user manager rather
  # than assuming systemctl --user can enable units without a session bus.
  if ! audio_session_ready "$audio_uid"; then
    systemctl start "user@$audio_uid.service" || return 1
    local audio_attempt
    for audio_attempt in {1..10}; do
      audio_session_ready "$audio_uid" && break
      sleep 1
    done
    if ! audio_session_ready "$audio_uid"; then
      echo 'ERROR: Viewer user audio bus is unavailable; check user@UID.service and dbus-user-session.' >&2
      return 1
    fi
  fi
  "${audio_command[@]}" systemctl --user daemon-reload || return 1
  "${audio_command[@]}" systemctl --user enable "${audio_enable[@]}" || return 1
  "${audio_command[@]}" systemctl --user start "${audio_start[@]}" || return 1
  "${audio_command[@]}" systemctl --user is-active --quiet "${audio_start[@]}" || return 1
}
