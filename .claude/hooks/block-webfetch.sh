#!/usr/bin/env bash
# PreToolUse hook: hard-block WebFetch/WebSearch tool calls.
#
# Why: CLAUDE.md mandates Firecrawl (page scrape) / Exa (general search)
# instead of WebFetch/WebSearch, project-wide, for orchestrator AND any
# subagent (including built-in fleet agents like claude-code-guide,
# general-purpose, Explore, feature-dev:* that ship with WebFetch/WebSearch
# in their default toolset). Docs-only rule kept getting missed before
# spawning those agents (incident 2026-08-09) — this makes it a hard stop
# instead of a reminder.
#
# No input parsing needed: matcher already scopes this to WebFetch/WebSearch
# tool_use events, so any call reaching this hook is blocked outright.
cat >/dev/null
echo "Blocked: WebFetch/WebSearch banned in this project. Use Firecrawl (mcp__firecrawl__firecrawl_scrape, конкретная страница) or Exa (mcp__exa__web_search_exa, общий поиск) instead. See CLAUDE.md, 'Веб-поиск и парсинг'. If YOU (this agent) do not have those MCP tools bound in your own toolset, do NOT silently fall back to local files/training data and present that as a full answer -- STOP and tell the orchestrator this task needs live web/docs access you don't have, so it can be routed to Firecrawl/Exa/research instead." >&2
exit 2
