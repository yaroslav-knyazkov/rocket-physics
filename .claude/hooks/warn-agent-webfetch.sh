#!/usr/bin/env bash
# PreToolUse hook: advisory warning when orchestrator spawns a built-in
# fleet agent that ships WebFetch/WebSearch in its own fixed toolset.
#
# Why: block-webfetch.sh hard-blocks WebFetch/WebSearch tool_use events
# project-wide (CLAUDE.md, "Веб-поиск и парсинг" -- Firecrawl/Exa only).
# That works fine for project-defined agents (.claude/agents/*.md), whose
# tool lists we control and which never carry WebFetch/WebSearch to begin
# with. It does NOT work cleanly for platform-provided built-in agents
# (claude-code-guide, general-purpose, Explore, Plan, feature-dev:*) --
# their toolset is fixed by the fleet, not editable here. When one of them
# hits the block, it has no Firecrawl/Exa fallback bound in its own
# session and silently degrades to a local-files/training-data-only
# answer instead of surfacing the limitation (incident 2026-08-10: asked
# claude-code-guide about Claude Code docs, got blocked on WebFetch,
# quietly answered from stale training data + local file inspection,
# presented as if authoritative).
#
# This hook does not block the spawn (some of these agents are still
# useful for pure local-code questions). It just reminds the orchestrator,
# BEFORE dispatch, to route anything needing live/current web or docs data
# elsewhere -- or to explicitly instruct the agent in its prompt not to
# silently paper over a WebFetch block.
#
# Parsing: grep/sed instead of python3 -- see block-find.sh for why
# (python3 can resolve to a broken Windows Store stub in some shells).
input="$(cat)"
subtype="$(printf '%s' "$input" | grep -o '"subagent_type"[[:space:]]*:[[:space:]]*"\(\\.\|[^"]\)*"' | head -1 | sed -E 's/^"subagent_type"[[:space:]]*:[[:space:]]*"(.*)"$/\1/')"

if [[ -z "$subtype" ]]; then
  exit 0
fi

known_re='^(claude-code-guide|general-purpose|Explore|Plan|feature-dev:code-architect|feature-dev:code-explorer|feature-dev:code-reviewer)$'
if [[ "$subtype" =~ $known_re ]]; then
  msg="NOTE: '$subtype' is a platform built-in agent shipping its own WebFetch/WebSearch (hard-blocked project-wide by block-webfetch.sh). If this task needs current/live web or docs data, this agent cannot get it -- it will hit the block and may silently answer from stale training data instead of reporting the gap. Prefer: Context7 for library/framework docs, Firecrawl/Exa yourself as orchestrator for pages/search, or delegate to project 'research' agent (has Context7+Exa+Firecrawl). If you still spawn '$subtype', tell it explicitly in the prompt: do not use WebFetch/WebSearch; if blocked, say so instead of quietly falling back to local files or training data."
  esc="$(printf '%s' "$msg" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}' "$esc"
fi
exit 0
