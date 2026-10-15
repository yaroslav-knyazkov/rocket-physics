#!/usr/bin/env bash
# PreToolUse hook: hard-block `find` invocations from the Bash tool.
#
# Why: Git for Windows ships GNU `find` in usr\bin, which shadows the
# System32 `find` on PATH. `find /` in MSYS resolves `/` to
# C:\Program Files\Git\, not the disk root — pointless and slow. Worse: if
# the parent bash.exe dies mid-search (tool timeout/cancel), find.exe is
# orphaned, blocks writing to a closed pipe, and hangs forever eating
# memory (see incident 2026-08-07, scripts/cleanup-orphans.ps1).
#
# CLAUDE.md already mandates Glob/Grep instead of shell find/grep for this
# project. The old PreToolUse hook only nudged toward graphify — agents
# kept calling `find /` anyway. This makes it a hard stop.
input="$(cat)"
# Parse via grep/sed, not python3 — python3 resolves to a broken Windows
# Store stub in some shells (silent no-op), which would make this hook a
# silent no-op too. See block-env-edit.sh for the same pattern.
cmd="$(printf '%s' "$input" | grep -o '"command"[[:space:]]*:[[:space:]]*"\(\\.\|[^"]\)*"' | head -1 | sed -E 's/^"command"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')"

if [[ -z "$cmd" ]]; then
  exit 0
fi

# Match `find` as a standalone command token (not findstr/gofind/etc.).
# Regex kept in a variable and referenced unquoted below — inlining it
# literally inside [[ =~ ]] makes bash mis-parse the ( ) | as shell syntax.
find_re='(^|[[:space:];&|(])find([[:space:]]|$)'
if [[ "$cmd" =~ $find_re ]]; then
  echo "Blocked: raw 'find' via Bash is banned in this project (orphans hang, MSYS '/' != disk root). Use Glob or Grep tool instead. If you truly need a filesystem search outside those tools, ask the user first." >&2
  exit 2
fi

exit 0
