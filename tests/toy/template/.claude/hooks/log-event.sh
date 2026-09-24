#!/bin/sh
# Append the hook event name (the first argument) to .hooklog in the project directory.
# Claude Code sends the event as JSON on stdin; read it so the pipe is drained, then ignore it.
cat >/dev/null
dir="${CLAUDE_PROJECT_DIR:-.}"
printf '%s\n' "${1:-unknown}" >> "$dir/.hooklog"
exit 0
