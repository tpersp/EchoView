#!/usr/bin/env bash
# Network watchdog for EchoView
# Pings a target multiple times and reboots only after sustained failures.

set -euo pipefail

PING_BIN="/bin/ping"
IP_BIN="/usr/sbin/ip"
AWK_BIN="/usr/bin/awk"
DATE_BIN="/bin/date"
TEE_BIN="/usr/bin/tee"
MKDIR_BIN="/bin/mkdir"
CHOWN_BIN="/bin/chown"
CHMOD_BIN="/bin/chmod"
TOUCH_BIN="/usr/bin/touch"
DIRNAME_BIN="/usr/bin/dirname"
SYSTEMCTL_BIN="/bin/systemctl"
REBOOT_BIN="/sbin/reboot"
SEQ_BIN="/usr/bin/seq"
ID_BIN="/usr/bin/id"
GETENT_BIN="/usr/bin/getent"

WATCHDOG_CONF="${WATCHDOG_CONF:-/home/pi/EchoView/network-watchdog.conf}"
if [ -f "$WATCHDOG_CONF" ]; then
  # shellcheck disable=SC1090
  . "$WATCHDOG_CONF"
fi

WATCHDOG_USER="${WATCHDOG_USER:-pi}"
WATCHDOG_UID="${WATCHDOG_UID:-1000}"
WATCHDOG_GID="${WATCHDOG_GID:-1000}"
WATCHDOG_LOG="${WATCHDOG_LOG:-/home/pi/EchoView/viewer.log}"
WATCHDOG_TARGET="${WATCHDOG_TARGET:-}"
WATCHDOG_ATTEMPTS="${WATCHDOG_ATTEMPTS:-5}"
WATCHDOG_FAIL_THRESHOLD="${WATCHDOG_FAIL_THRESHOLD:-3}"

is_positive_int() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

log() {
  local msg="${1:-}"
  printf '%s - %s\n' "$("$DATE_BIN" -Iseconds)" "$msg" | "$TEE_BIN" -a "$WATCHDOG_LOG" >/dev/null
}

ensure_log_file() {
  local dir owner=""
  dir=$("$DIRNAME_BIN" "$WATCHDOG_LOG")
  "$MKDIR_BIN" -p "$dir"
  "$TOUCH_BIN" "$WATCHDOG_LOG"

  if "$ID_BIN" -u "$WATCHDOG_USER" >/dev/null 2>&1; then
    owner="$WATCHDOG_USER:$WATCHDOG_USER"
  elif "$GETENT_BIN" passwd "$WATCHDOG_UID" >/dev/null 2>&1; then
    owner="$WATCHDOG_UID:$WATCHDOG_GID"
  fi

  if [ -n "$owner" ]; then
    "$CHOWN_BIN" "$owner" "$WATCHDOG_LOG"
  fi

  "$CHMOD_BIN" 664 "$WATCHDOG_LOG"
}

detect_default_target() {
  local gateway addr ip o1 o2 o3

  gateway=$("$IP_BIN" -4 route show default 2>/dev/null | "$AWK_BIN" '$1=="default"{print $3; exit}')
  if [ -n "$gateway" ]; then
    echo "$gateway"
    return
  fi

  addr=$("$IP_BIN" -4 addr show scope global up 2>/dev/null | "$AWK_BIN" '/inet /{print $2; exit}')
  if [ -n "$addr" ]; then
    ip=${addr%%/*}
    IFS='.' read -r o1 o2 o3 _ <<< "$ip"
    if [ -n "${o1:-}" ] && [ -n "${o2:-}" ] && [ -n "${o3:-}" ]; then
      echo "${o1}.${o2}.${o3}.1"
      return
    fi
  fi

  echo "1.1.1.1"
}

reboot_system() {
  log "FAIL watchdog triggering reboot via systemctl"
  if ! "$SYSTEMCTL_BIN" reboot; then
    "$REBOOT_BIN"
  fi
}

main() {
  ensure_log_file

  local target attempts threshold successes=0 failures=0 consecutive=0

  target="$WATCHDOG_TARGET"
  if [ -z "$target" ]; then
    target="$(detect_default_target)"
    log "INFO watchdog target not set; defaulting to $target"
  else
    log "INFO watchdog target configured as $target"
  fi

  attempts="$WATCHDOG_ATTEMPTS"
  if ! is_positive_int "$attempts"; then
    attempts=5
  fi

  threshold="$WATCHDOG_FAIL_THRESHOLD"
  if ! is_positive_int "$threshold"; then
    threshold=3
  fi

  if (( threshold > attempts )); then
    threshold="$attempts"
  fi

  for i in $("$SEQ_BIN" 1 "$attempts"); do
    if "$PING_BIN" -c 1 -W 2 "$target" >/dev/null 2>&1; then
      successes=$((successes + 1))
      consecutive=0
    else
      failures=$((failures + 1))
      consecutive=$((consecutive + 1))
      log "WARN ping attempt $i/$attempts to $target failed (consecutive $consecutive/$threshold)"

      if (( consecutive >= threshold )); then
        log "FAIL consecutive failure threshold reached ($consecutive/$threshold); rebooting"
        reboot_system
        exit 0
      fi
    fi
  done

  if (( successes == 0 )); then
    log "FAIL $attempts ping attempts to $target failed; rebooting"
    reboot_system
    exit 0
  fi

  log "OK $target reachable ($successes/$attempts successes, $failures failures)"
}

main "$@"
