#!/usr/bin/env bash
# Keep asking for attention on the animatronic eye until the session moves on.
#
#     eye-nag.sh alert        a questionnaire is waiting
#     eye-nag.sh suspicious   a command is asking permission
#
# Claude Code fires a Notification when a dialog opens and nothing at all when
# it closes, so this loop cannot wait for an answer. eye-nag-stop.sh ends it,
# wired to PostToolUse, UserPromptSubmit and Stop. Between those three, every
# way a dialog can resolve reaches one of them.
#
# The deadline is the backstop for the case where none of them fires. An eye
# that gives up after 10 minutes is a smaller annoyance than one that keeps
# going until the board is unplugged.
#
# One loop per session, keyed by session id: a prompt answered in one session
# must not silence a question still waiting in another.

set -u

EXPRESSION="${1:-alert}"
STATE_DIR="$HOME/.claude/hooks/eye-nag.d"
PLAY="$HOME/.claude/hooks/eye-express.sh"
# Overridable so the deadline and the period can be tested in seconds rather
# than in the ten minutes the real backstop takes.
DEADLINE_S="${EYE_NAG_DEADLINE_S:-600}"
PERIOD_MIN_S="${EYE_NAG_PERIOD_MIN_S:-5}"
PERIOD_MAX_S="${EYE_NAG_PERIOD_MAX_S:-10}"

payload=$(cat 2>/dev/null || true)
session=$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)
[ -n "$session" ] || session=default
session=${session//[^A-Za-z0-9._-]/_}

mkdir -p "$STATE_DIR" || exit 0

# Drop pid files left behind by a session that died mid-nag.
shopt -s nullglob
for stale in "$STATE_DIR"/*.pid; do
  kill -0 "$(cat "$stale" 2>/dev/null)" 2>/dev/null || rm -f "$stale"
done

pidfile="$STATE_DIR/$session.pid"
if [ -f "$pidfile" ]; then
  old=$(cat "$pidfile" 2>/dev/null)
  if [ -n "$old" ]; then
    kill "$old" 2>/dev/null
    pkill -P "$old" 2>/dev/null
  fi
fi

(
  end=$((SECONDS + DEADLINE_S))
  while [ "$SECONDS" -lt "$end" ]; do
    started=$SECONDS
    "$PLAY" "$EXPRESSION"
    # The gesture itself takes one to two seconds. Subtract it so the period
    # is measured gesture to gesture, not gap to gap.
    period=$(( RANDOM % (PERIOD_MAX_S - PERIOD_MIN_S + 1) + PERIOD_MIN_S ))
    rest=$(( period - (SECONDS - started) ))
    if [ "$rest" -gt 0 ]; then
      sleep "$rest"
    fi
  done
  rm -f "$pidfile"
) >/dev/null 2>&1 &

printf '%s\n' "$!" > "$pidfile"
exit 0
