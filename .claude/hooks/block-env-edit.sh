#!/usr/bin/env bash
# PreToolUse hook: block Edit/Write on real .env files (allow .env.example)
input="$(cat)"
file_path="$(printf '%s' "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/')"

if [[ -z "$file_path" ]]; then
  exit 0
fi

base="$(basename "$file_path")"

if [[ "$base" =~ ^\.env(\..+)?$ ]] && [[ "$base" != *.example ]]; then
  echo "Blocked: edit of secret file '$file_path' needs manual review (not via Claude Code)." >&2
  exit 2
fi

exit 0
