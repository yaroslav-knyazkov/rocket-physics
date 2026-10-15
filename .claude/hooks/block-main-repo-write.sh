#!/usr/bin/env bash
# PreToolUse hook: while a task worktree is active, block Write/Edit inside the
# MAIN repo. All work must land in the worktree (.claude/wt-active.json holds
# its path); the main repo only ever receives the merge commit from wt.py land.
#
# Inactive by design when .claude/wt-active.json is absent -- normal
# non-worktree sessions are untouched.
#
# Parsing is grep/sed, not python3: python3 resolves to a broken Windows Store
# stub in some shells, which would make this hook a silent no-op. Same reason
# as block-find.sh / block-env-edit.sh.

input="$(cat)"

state=".claude/wt-active.json"
[[ -f "$state" ]] || exit 0

file_path="$(printf '%s' "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"\(\\.\|[^"]\)*"' | head -1 | sed -E 's/^"file_path"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')"
[[ -z "$file_path" ]] && exit 0

norm() {
  # backslashes -> slashes, unescape JSON \\ , lowercase
  printf '%s' "$1" | sed -e 's|\\\\|/|g' -e 's|\\|/|g' | tr 'A-Z' 'a-z'
}

p="$(norm "$file_path")"

# Trackers are edited by every task, so a copy inside a worktree conflicts on
# every sync. Their single home is the MAIN repo: the orchestrator writes them
# there and commits right away with `git commit --only <paths>`.
trackers="dev/status.json dev/journal.md dev/project-status.md"

# Anything under an active worktree is fine -- except the trackers (also covers
# the case where a worktree ever lives inside the repo tree).
while IFS= read -r wt; do
  [[ -z "$wt" ]] && continue
  w="$(norm "$wt")"
  case "$p" in
    "$w"|"$w"/*)
      wtrel="${p#"$w"/}"
      for t in $trackers; do
        if [[ "$wtrel" == "$t" ]]; then
          echo "Blocked: '$file_path' is a tracker file inside a worktree. Trackers live only in the MAIN repo -- edit it there and commit it with 'git commit --only'. Inside a worktree it conflicts on every wt.py sync, and wt.py commit refuses it anyway." >&2
          exit 2
        fi
      done
      exit 0 ;;
  esac
done < <(grep -o '"path"[[:space:]]*:[[:space:]]*"\(\\.\|[^"]\)*"' "$state" | sed -E 's/^"path"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')

repo_win="$(pwd -W 2>/dev/null || pwd)"
repo="$(norm "$repo_win")"

# Relative paths resolve against the session cwd == main repo.
rel=""
case "$p" in
  /*|[a-z]:/*)
    case "$p" in
      "$repo"/*) rel="${p#"$repo"/}" ;;
      *) exit 0 ;;              # outside the main repo -- not our business
    esac
    ;;
  *) rel="$p" ;;
esac

# Gitignored scratch plus the trackers, whose only home is the main repo.
for allow in "graphify-out/" "temporary/" ".worktrees/" ".claude/wt-active.json" \
             "dev/.status-backup/" "dev/.docs-backup/" \
             "dev/status.json" "dev/journal.md" "dev/project-status.md"; do
  case "$rel" in
    "$allow"*) exit 0 ;;
  esac
done

active_path="$(grep -o '"path"[[:space:]]*:[[:space:]]*"\(\\.\|[^"]\)*"' "$state" | head -1 | sed -E 's/^"path"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')"

echo "Blocked: '$file_path' is in the MAIN repo, but task worktree '$active_path' is active. Edit the file there instead (same relative path: $active_path/$rel). If this edit truly belongs to the base branch, tell the orchestrator -- it must be a deliberate, separately committed exception." >&2
exit 2
