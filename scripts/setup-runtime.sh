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
