#!/bin/sh
set -eu

PUID_RAW="${PUID:-1000}"
PGID_RAW="${PGID:-1000}"

case "$PUID_RAW" in
  ''|*[!0-9]*)
    echo "[Dockraft] WARNING: PUID inválido ('$PUID_RAW'), usando 1000." >&2
    PUID=1000
    ;;
  0)
    echo "[Dockraft] WARNING: PUID=0 (root) bloqueado por seguridad, usando 1000." >&2
    PUID=1000
    ;;
  *)
    PUID="$PUID_RAW"
    ;;
esac

case "$PGID_RAW" in
  ''|*[!0-9]*)
    echo "[Dockraft] WARNING: PGID inválido ('$PGID_RAW'), usando 1000." >&2
    PGID=1000
    ;;
  0)
    echo "[Dockraft] WARNING: PGID=0 (root) bloqueado por seguridad, usando 1000." >&2
    PGID=1000
    ;;
  *)
    PGID="$PGID_RAW"
    ;;
esac

STATE_DIR="${DOCKRAFT_STATE_DIR:-/app/.dockraft_state}"
DATA_PATH="${DATA_DIR:-/server_data}"
BACKUPS_PATH="${BACKUPS_DIR:-/server_backups}"

ensure_owned_dir() {
  target_dir="$1"
  dir_mode="${2:-}"
  mkdir -p "$target_dir"
  # Only walk chown -R when ownership actually differs so normal restarts stay instant.
  if [ -n "$(find "$target_dir" \( ! -uid "$PUID" -o ! -gid "$PGID" \) -print -quit 2>/dev/null || true)" ]; then
    chown -R "$PUID:$PGID" "$target_dir"
  fi
  if [ -n "$dir_mode" ]; then
    chmod "$dir_mode" "$target_dir" 2>/dev/null || true
  fi
}

if [ "$(id -u)" = "0" ]; then
  if [ "$(id -g dockraft)" != "$PGID" ]; then
    groupmod -o -g "$PGID" dockraft
  fi
  if [ "$(id -u dockraft)" != "$PUID" ]; then
    usermod -o -u "$PUID" dockraft
  fi

  ensure_owned_dir "/home/dockraft"
  ensure_owned_dir "$STATE_DIR" "700"
  ensure_owned_dir "$DATA_PATH"
  ensure_owned_dir "$BACKUPS_PATH"

  export HOME="/home/dockraft"
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
fi

mkdir -p "$STATE_DIR" "$DATA_PATH" "$BACKUPS_PATH" 2>/dev/null || true
exec "$@"
