#!/usr/bin/env bash
# Install the session hooks so the eye reacts when Claude Code wants an answer.
#
#     tools/install-hooks.sh
#     CLAUDE_HOME=~/.config/claude tools/install-hooks.sh
#
# Copies hooks/ into the Claude Code hook directory and registers it in
# settings.json. Runs clean twice: it drops its own entries before adding
# them, so a second run updates rather than doubling the eye's reactions.
#
# Hooks are read at session start, and a new session inside a running app does
# not reread them. Quit the app and start it again.

set -euo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SOURCE="$(cd "$(dirname "$0")/../hooks" && pwd)"
TARGET="$CLAUDE_HOME/hooks"
SETTINGS="$CLAUDE_HOME/settings.json"

if [ ! -d "$CLAUDE_HOME" ]; then
  echo "No Claude Code directory at $CLAUDE_HOME. Set CLAUDE_HOME." >&2
  exit 1
fi

mkdir -p "$TARGET"
for script in "$SOURCE"/*.sh; do
  install -m 755 "$script" "$TARGET/"
  echo "-> $TARGET/$(basename "$script")"
done

backup="$SETTINGS.bak-$(date +%Y%m%d-%H%M%S)"
[ -f "$SETTINGS" ] && cp "$SETTINGS" "$backup" && echo "-> $backup"

TARGET="$TARGET" SETTINGS="$SETTINGS" python3 - <<'PY'
import json
import os
from pathlib import Path

target = os.environ["TARGET"]
settings = Path(os.environ["SETTINGS"])
nag = f"{target}/eye-nag.sh"
stop = f"{target}/eye-nag-stop.sh"

config = json.loads(settings.read_text()) if settings.exists() else {}
hooks = config.setdefault("hooks", {})


def entry(command, args=None):
    hook = {"type": "command", "command": command}
    if args:
        hook["args"] = args
    hook.update({"async": True, "timeout": 10})
    return {"hooks": [hook]}


def drop_ours(event):
    kept = []
    for group in hooks.get(event, []):
        remaining = [h for h in group.get("hooks", []) if h.get("command") not in (nag, stop)]
        if remaining:
            group["hooks"] = remaining
            kept.append(group)
    if kept:
        hooks[event] = kept
    else:
        hooks.pop(event, None)


for event in ("Notification", "PostToolUse", "UserPromptSubmit", "Stop"):
    drop_ours(event)

hooks.setdefault("Notification", []).extend([
    {"matcher": "elicitation_dialog", **entry(nag, ["alert"])},
    {"matcher": "permission_prompt", **entry(nag, ["suspicious"])},
])
hooks.setdefault("PostToolUse", []).append({"matcher": "*", **entry(stop)})
hooks.setdefault("UserPromptSubmit", []).append(entry(stop))
hooks.setdefault("Stop", []).append(entry(stop))

settings.write_text(json.dumps(config, indent=2) + "\n")
print(f"-> {settings}")
PY

echo
echo "Quit the Claude Code app and start it again. Hooks load at session start."
