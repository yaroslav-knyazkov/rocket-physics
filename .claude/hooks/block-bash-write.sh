#!/usr/bin/env bash
# PreToolUse hook (Bash matcher): block file mutations performed *through the
# shell* that the Edit|Write guards would have refused.
#
# Why this exists at all. Two guards hang off the `Edit|Write` matcher:
# block-env-edit.sh (real .env files need manual review) and
# block-main-repo-write.sh (while a task worktree is active, the MAIN repo is
# read-only). Both read `tool_input.file_path` — a field only the Edit/Write
# tools have. A `sed -i`, a `>` redirect, a `tee`, a `cp` or a heredoc goes
# through the Bash tool, carries no file_path, and therefore sails past both.
#
# This is not theoretical. Incident 2026-08-30: with worktree `stage35-w5`
# active, the orchestrator ran
#   sed -i 's/^SQL_ECHO=true[[:space:]]*$/SQL_ECHO=false/' .env
# from dev/backend. That single command tripped *both* protected classes —
# a secret file and a main-repo write during an active worktree — and neither
# hook fired, because neither can see a Bash command. Consequences were benign;
# the hole is not. Worse, Claude Code's "auto mode" instruction actively pushes
# agents toward exactly this shape ("make file changes with sed, heredocs or
# short scripts, rather than the Edit or Write tools"), so the bypass is not a
# rare slip — it is the default behaviour the model is nudged into.
#
# Two independent rules:
#   A. .env protection — always on, no worktree required. Mirrors
#      block-env-edit.sh (`^\.env(\..+)?$`, minus `*.example`).
#   B. main-repo protection — only while .claude/wt-active.json exists.
#      Mirrors block-main-repo-write.sh, including its allowlist.
#
# False-positive policy, deliberately asymmetric: a guard that blocks ordinary
# read-only work gets worked around or switched off, and then it guards
# nothing. So `grep ... >/dev/null`, `cmd 2>&1 | head`, `python script.py` and
# bare `git ...` must pass clean, and a false negative on an obviously harmless
# command is preferred over a false positive. The one place we deliberately
# lean the other way: a write construct is clearly present, a worktree is
# active, and the target cannot be resolved (a variable, a quoted string with
# spaces) — then we block, because "probably fine" is how the incident above
# happened. The message says exactly what to do instead.
#
# Parsing is grep/sed/bash, never python3: python3 resolves to a broken Windows
# Store stub in some shells, which would turn this hook into a silent no-op.
# Same reason as block-find.sh / block-env-edit.sh / block-main-repo-write.sh.
#
# Contract: exit 0 = allow (silent), exit 2 = block with a reason on stderr.
# Nothing else ever exits non-zero — a guard that crashes blocks every tool
# call in the session (incident 2026-08-09, a bad matcher in settings.json did
# precisely that). Every parse below is best-effort and falls through to allow.

input="$(cat)"

cmd="$(printf '%s' "$input" | grep -o '"command"[[:space:]]*:[[:space:]]*"\(\\.\|[^"]\)*"' | head -1 | sed -E 's/^"command"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')"
[[ -z "$cmd" ]] && exit 0

# --- JSON unescape -----------------------------------------------------------
# \n must become a real newline: heredoc bodies are stripped line-wise below.
# \\ is parked on \x01 first so that a literal "\\n" (Windows path) does not
# turn into a newline.
raw="$(printf '%s' "$cmd" | sed -e 's/\\\\/\x01/g' -e 's/\\n/\n/g' -e 's/\\t/ /g' -e 's/\\r//g' -e 's/\\"/"/g' -e 's/\x01/\\/g')"

# --- mask quoted strings -----------------------------------------------------
# Without this, `grep -n "a > b" file` reads as a redirect into `b` and gets
# blocked — the single most likely false positive. Masking is two-pass on
# purpose: a quoted string that is a plain path-like token keeps its content
# (we still need `sed -i 's/x/y/' 'dev/a.py'` to resolve), anything containing
# a space, a redirect char or a `$` collapses to the opaque token @QUOTED@,
# which later classifies as "target unknown".
masked="$(printf '%s\n' "$raw" \
  | sed -E "s/'([^'[:space:]<>|&;\$\`()]+)'/\1/g" \
  | sed -E 's/"([^"[:space:]<>|&;$`()]+)"/\1/g' \
  | sed -E "s/'[^']*'/@QUOTED@/g" \
  | sed -E 's/"[^"]*"/@QUOTED@/g')"

# --- strip heredoc bodies ----------------------------------------------------
# A heredoc body is data, not shell: markdown blockquotes (`> foo`) and pipes
# inside it would otherwise read as redirections. The opening line keeps its
# real redirect (`cat > .env <<EOF`), which is what we actually want to catch.
scan=""
hd_delim=""
while IFS= read -r line; do
  if [[ -n "$hd_delim" ]]; then
    trimmed="$(printf '%s' "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ "$trimmed" == "$hd_delim" ]] && hd_delim=""
    continue
  fi
  scan+="$line"$'\n'
  # `<<<` is a here-string, not a heredoc — the [^<] guard keeps it out.
  hd_re='(^|[^<])<<-?[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)'
  if [[ "$line" =~ $hd_re ]]; then
    hd_delim="${BASH_REMATCH[2]}"
  fi
done < <(printf '%s\n' "$masked")

# --- worktree state ----------------------------------------------------------
# Resolved against the session cwd, exactly like block-main-repo-write.sh.
state=".claude/wt-active.json"
wt_active=0
[[ -f "$state" ]] && wt_active=1

norm() {
  # backslashes -> slashes, unescape JSON \\ , lowercase
  printf '%s' "$1" | sed -e 's|\\\\|/|g' -e 's|\\|/|g' | tr 'A-Z' 'a-z'
}

repo="$(norm "$(pwd -W 2>/dev/null || pwd)")"

wt_paths=()
current_wt=""
if [[ $wt_active -eq 1 ]]; then
  while IFS= read -r w; do
    [[ -n "$w" ]] && wt_paths+=("$(norm "$w")")
  done < <(grep -o '"path"[[:space:]]*:[[:space:]]*"\(\\.\|[^"]\)*"' "$state" 2>/dev/null | sed -E 's/^"path"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')
  cur="$(grep -o '"current"[[:space:]]*:[[:space:]]*"[^"]*"' "$state" 2>/dev/null | head -1 | sed -E 's/^"current"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')"
  # Prefer the worktree the session is actually on, so the "write it here
  # instead" hint points at the right tree when several are live.
  for w in "${wt_paths[@]}"; do
    [[ -n "$cur" && "${w##*/}" == "$(norm "$cur")" ]] && current_wt="$w"
  done
  [[ -z "$current_wt" && ${#wt_paths[@]} -gt 0 ]] && current_wt="${wt_paths[0]}"
fi

# --- effective cwd -----------------------------------------------------------
# `cd <worktree> && sed -i ... file` is legitimate: the relative target lands in
# the worktree, not the main repo. Take the last absolute `cd` in the command
# as the base for relative targets; without one, relative == main repo cwd,
# which is the whole point of rule B.
eff_cwd="$repo"
while IFS= read -r m; do
  d="$(norm "$(printf '%s' "$m" | sed -E 's/^[[:space:]]*cd[[:space:]]+//')")"
  case "$d" in
    /*|[a-z]:/*) eff_cwd="$d" ;;
    @quoted@|*'$'*|*'`'*) ;;                  # unresolvable, keep previous
    *) eff_cwd="${eff_cwd%/}/$d" ;;
  esac
done < <(printf '%s\n' "$scan" | grep -oE '(^|[[:space:];&|(])cd[[:space:]]+[^[:space:];&|()<>]+' | sed -E 's/^[^c]*//' || true)

# --- collect write targets ---------------------------------------------------
targets=()
has_write=0

add_target() { [[ -n "$1" ]] && targets+=("$1"); }

# Output redirection: `>`, `>>`, `>|`, `2>`, `&>`.
# The (^|[^-=<>&]) prefix keeps `->`, `=>` and `2>&1` out; the target char
# class refuses to start on `&`, which is what makes `2>&1` a non-match.
while IFS= read -r m; do
  [[ -z "$m" ]] && continue
  has_write=1
  add_target "$(printf '%s' "$m" | sed -E 's/^[^>]*>+\|?[[:space:]]*//')"
done < <(printf '%s\n' "$scan" | grep -oE '(^|[^-=<>&])[0-9]*>>?\|?[[:space:]]*[^[:space:];&|()<>]+' || true)

# tee (with its option flags), dd of=
while IFS= read -r m; do
  [[ -z "$m" ]] && continue
  has_write=1
  add_target "${m##* }"
done < <(printf '%s\n' "$scan" | grep -oE '(^|[[:space:];&|(])tee([[:space:]]+-[a-zA-Z-]+)*[[:space:]]+[^[:space:];&|()<>]+' || true)

while IFS= read -r m; do
  [[ -z "$m" ]] && continue
  has_write=1
  add_target "${m#*of=}"
done < <(printf '%s\n' "$scan" | grep -oE '(^|[[:space:]])of=[^[:space:];&|()<>]+' || true)

# `python -c "... open(p,'w') ..."` / `python - <<PY`. Best effort, and it runs
# on the *raw* text: masking eats the quotes, and heredoc stripping eats the
# body, but this is precisely where the interesting bit hides.
while IFS= read -r m; do
  [[ -z "$m" ]] && continue
  has_write=1
  add_target "$(printf '%s' "$m" | sed -E "s/^open\([[:space:]]*['\"]([^'\"]+)['\"].*/\1/")"
done < <(printf '%s\n' "$raw" | grep -oE "open\([[:space:]]*['\"][^'\"]+['\"][[:space:]]*,[[:space:]]*['\"][wax][b+t]*['\"]" || true)

while IFS= read -r m; do
  [[ -z "$m" ]] && continue
  has_write=1
  add_target "$(printf '%s' "$m" | sed -E "s/^Path\([[:space:]]*['\"]([^'\"]+)['\"].*/\1/")"
done < <(printf '%s\n' "$raw" | grep -oE "Path\([[:space:]]*['\"][^'\"]+['\"][[:space:]]*\)\.write_(text|bytes)\(" || true)

# A write mode we could not attach a path to still counts as a write.
if printf '%s' "$raw" | grep -qE "open\([^)]*,[[:space:]]*['\"][wax]" ; then
  has_write=1
fi

# --- command-shaped writes: cp / mv / install / ln / rm / truncate / patch / sed
analyze_segment() {
  seg="$1"
  [[ -z "${seg// /}" ]] && return 0
  read -ra toks <<< "$seg"
  n=${#toks[@]}
  [[ $n -eq 0 ]] && return 0

  # skip leading `VAR=x`, sudo, env, time...
  i=0
  while [[ $i -lt $n ]]; do
    tk="${toks[$i]}"
    if [[ "$tk" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then i=$((i + 1)); continue; fi
    case "${tk##*/}" in
      sudo|env|command|time|nohup|nice|exec) i=$((i + 1)); continue ;;
    esac
    break
  done
  [[ $i -ge $n ]] && return 0

  first="${toks[$i]##*/}"
  first="${first%.exe}"

  # Cut the redirection tail: `cp a b > log` must not report `log` as the copy
  # destination (the redirect scan already owns it).
  end=$n
  for ((j = i + 1; j < n; j++)); do
    case "${toks[$j]}" in
      *'>'* | '<' | '<<'*) end=$j; break ;;
    esac
  done

  case "$first" in
    cp | mv | install | ln)
      has_write=1
      last=""
      for ((j = i + 1; j < end; j++)); do
        case "${toks[$j]}" in -*) continue ;; esac
        last="${toks[$j]}"
      done
      if [[ -n "$last" ]]; then add_target "$last"; else add_target "@QUOTED@"; fi
      ;;
    rm | rmdir | shred | truncate | patch)
      has_write=1
      found=0
      for ((j = i + 1; j < end; j++)); do
        case "${toks[$j]}" in -*) continue ;; esac
        add_target "${toks[$j]}"; found=1
      done
      [[ $found -eq 0 ]] && add_target "@QUOTED@"
      ;;
    sed)
      inplace=0
      for ((j = i + 1; j < end; j++)); do
        case "${toks[$j]}" in
          --in-place*) inplace=1 ;;
          --*) ;;
          -*i*) inplace=1 ;;
        esac
      done
      [[ $inplace -eq 0 ]] && return 0
      has_write=1
      # `sed [opts] SCRIPT file...`: without -e/-f the first non-option token is
      # the script, not a file. Skipping it matters — quote masking turns
      # 's/x/y/' into a bare token that otherwise reads as a relative path and
      # blocks a perfectly legal in-worktree edit.
      has_e=0
      for ((j = i + 1; j < end; j++)); do
        case "${toks[$j]}" in
          -e | -f | --expression* | --file*) has_e=1 ;;
        esac
      done
      found=0
      skip=0
      first_arg=1
      for ((j = i + 1; j < end; j++)); do
        tk="${toks[$j]}"
        if [[ $skip -eq 1 ]]; then skip=0; continue; fi
        case "$tk" in
          -e | -f | --expression | --file) skip=1; continue ;;
          -*) continue ;;
        esac
        if [[ $has_e -eq 0 && $first_arg -eq 1 ]]; then first_arg=0; continue; fi
        first_arg=0
        add_target "$tk"; found=1
      done
      [[ $found -eq 0 ]] && add_target "@QUOTED@"
      ;;
  esac
  return 0
}

while IFS= read -r seg; do
  analyze_segment "$seg"
done < <(printf '%s\n' "$scan" | sed -E 's/(\|\||&&)/\n/g' | sed -E 's/[;|&]/\n/g')

[[ $has_write -eq 0 ]] && exit 0

# --- classification ----------------------------------------------------------
# Gitignored scratch plus the trackers, whose only home is the main repo.
# Kept in sync with block-main-repo-write.sh by hand.
allowlist=("graphify-out/" "temporary/" ".worktrees/" ".claude/wt-active.json" \
  "dev/.status-backup/" "dev/.docs-backup/" \
  "dev/status.json" "dev/journal.md" "dev/project-status.md")

# Sets globals `verdict` (allow|indet|enva|main) and, for `main`, `rel`.
# Deliberately not a $(...) call: a command substitution runs in a subshell and
# the `rel` it computes would be lost.
verdict=""
rel=""
classify() {
  t="$1"
  rel=""
  verdict=allow
  [[ -z "$t" ]] && { verdict=indet; return; }
  case "$t" in
    '@QUOTED@' | '@quoted@' | *'$'* | *'`'*) verdict=indet; return ;;
  esac

  p="$(norm "$t")"
  p="${p#./}"

  # Rule A first: a .env is off limits everywhere, worktree or not — same
  # reach as block-env-edit.sh, which does not look at directories either.
  base="${p##*/}"
  case "$base" in
    .env | .env.*)
      [[ "$base" == *.example ]] || { verdict=enva; return; }
      ;;
  esac

  [[ $wt_active -eq 0 ]] && return

  case "$p" in
    /dev/null | /dev/stdout | /dev/stderr | nul | /dev/fd/* | /tmp/* | /tmp) return ;;
  esac

  # Everything becomes absolute, then `..`/`.` are folded out (bounded, so a
  # pathological path can never spin this hook).
  case "$p" in
    /* | [a-z]:/*) ;;
    *) p="${eff_cwd%/}/$p" ;;
  esac
  p="$(printf '%s' "$p" | sed -e 's|/\./|/|g' -e 's|//*|/|g')"
  guard=0
  while [[ "$p" == */../* || "$p" == */.. ]] && [[ $guard -lt 20 ]]; do
    p="$(printf '%s' "$p" | sed -E 's#/[^/]+/\.\.(/|$)#/#')"
    guard=$((guard + 1))
  done
  p="${p%/}"

  for w in "${wt_paths[@]}"; do
    case "$p" in
      "$w" | "$w"/*) return ;;
    esac
  done

  case "$p" in
    "$repo" | "$repo"/*) rel="${p#"$repo"/}" ;;
    *) return ;;                              # outside the main repo — not ours
  esac

  for a in "${allowlist[@]}"; do
    case "$rel" in
      "$a"*) return ;;
    esac
  done

  verdict=main
}

hit_env=""
hit_main=""
hit_main_rel=""
hit_indet=0

for t in "${targets[@]}"; do
  classify "$t"
  case "$verdict" in
    enva) [[ -z "$hit_env" ]] && hit_env="$t" ;;
    main) [[ -z "$hit_main" ]] && { hit_main="$t"; hit_main_rel="$rel"; } ;;
    indet) hit_indet=1 ;;
  esac
done

# A write construct with no target at all is as unresolved as @QUOTED@.
[[ ${#targets[@]} -eq 0 ]] && hit_indet=1

if [[ -n "$hit_env" ]]; then
  echo "Blocked: this Bash command writes to the secret file '$hit_env'. Bash writes bypass block-env-edit.sh, which is why this hook exists. Editing a real .env needs manual review (not via Claude Code) — ask the user to change it, or target a '*.example' file instead." >&2
  exit 2
fi

if [[ -n "$hit_main" ]]; then
  echo "Blocked: this Bash command writes to '$hit_main' in the MAIN repo while task worktree '$current_wt' is active. Bash writes bypass block-main-repo-write.sh. Use the Write/Edit tool, or write to $current_wt/$hit_main_rel. If this edit truly belongs to the base branch, tell the orchestrator -- it must be a deliberate, separately committed exception." >&2
  exit 2
fi

if [[ $hit_indet -eq 1 && $wt_active -eq 1 ]]; then
  echo "Blocked: this Bash command performs a file write, but its target could not be resolved (a variable, a substitution, or a quoted path), and task worktree '$current_wt' is active — so it may land in the MAIN repo, bypassing block-main-repo-write.sh. Use the Write/Edit tool instead, or repeat the command with an absolute path inside $current_wt." >&2
  exit 2
fi

exit 0
