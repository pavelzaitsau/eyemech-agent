#!/usr/bin/env bash
# Stop the eye nagging. The other half of eye-nag.sh.
#
#     eye-nag-stop.sh          stop this session's loop, session id from stdin
#     eye-nag-stop.sh --all    stop every session's loop
#
# PostToolUse, UserPromptSubmit and Stop all run this, so it fires on almost
# every turn. It returns before reading stdin or starting jq when no loop is
# running, which is the normal case.

set -u

STATE_DIR="$HOME/.claude/hooks/eye-nag.d"

stop_one() {
  local pidfile=$1 pid
  [ -f "$pidfile" ] || return 0
  pid=$(cat "$pidfile" 2>/dev/null)
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null
    # Killing the subshell leaves its in-flight sleep or curl behind, and that
    # curl would land one more gesture after the answer arrived.
    pkill -P "$pid" 2>/dev/null
  fi
  rm -f "$pidfile"
}

shopt -s nullglob
running=("$STATE_DIR"/*.pid)
(( ${#running[@]} )) || exit 0

if [ "${1:-}" = "--all" ]; then
  for pidfile in "${running[@]}"; do
    stop_one "$pidfile"
  done
  exit 0
fi

payload=$(cat 2>/dev/null || true)
session=$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)
[ -n "$session" ] || session=default
session=${session//[^A-Za-z0-9._-]/_}

stop_one "$STATE_DIR/$session.pid"
exit 0
