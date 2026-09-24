#!/bin/sh
# PreToolUse hook for Bash: block any command that contains "rm ".
# Claude Code sends the tool call as JSON on stdin; pull out the "command" field.
input=$(cat)
cmd=$(printf '%s' "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
case "$cmd" in
  *"rm "*)
    echo "Deleting files is not allowed in this assignment. Leave the file in place." >&2
    exit 2
    ;;
esac
exit 0
