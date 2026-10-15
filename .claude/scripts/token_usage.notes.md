# token_usage.py — implementation notes

Date: 2026-09-03. Files: `.claude/scripts/token_usage.py`, `.claude/scripts/token_prices.json`,
`.claude/scripts/tests/test_token_usage.py`.

## The double-count bug

Claude Code writes **one .jsonl row per content block** of an assistant message — `thinking`,
`text`, and each `tool_use` all get their own row — and every row repeats the exact same
`message.usage` object for that message, with one exception: `output_tokens` can be lower on
early streaming-partial rows before it settles at the final value.

The old `sum_usage()` added `usage` from every row unconditionally, so `input_tokens`,
`cache_creation_input_tokens` and `cache_read_input_tokens` were counted 2-4x depending on how many
content blocks a message had (measured: 455 raw rows with usage in one main-thread file collapsed
to 264 real messages — the same message.id repeated on average ~1.7x, some as high as 3-4x, with
subagent logs adding streaming-partial rows on top).

## Why `max`, not first/last/sum

Fix: group rows **per file** by `message["id"]`, take `max()` per usage key within a group, then
sum the groups.

- `max` because `output_tokens` grows across streaming-partial rows for the same message (observed
  a group with values 4, 4, 337 in raw logs) — the final settled value is always the largest one
  seen, so `max` recovers it regardless of write order.
- Not "first" — the first row of a group can be an early streaming partial and would under-report
  `output_tokens`.
- Not "last" — nothing in the log format guarantees the last-written row of a group is the
  final streaming state; relying on it is fragile to buffering/ordering.
- Cache fields (`cache_creation_input_tokens`, `cache_read_input_tokens`) and `input_tokens` were
  verified to never differ within a group across the sampled session, so `max` is a no-op safety net
  for them and the real work it does is on `output_tokens`.
- Rows without `message.id` get a synthetic per-row key (`f"_anon{row_index}"`), never merged with
  each other. `id(obj)` was deliberately avoided as a fallback key: CPython recycles object ids after
  garbage collection, so two logically distinct message dicts can share the same `id()` and would
  silently collapse into one group, undercounting.

Implementation: `load_messages()` in `token_usage.py`.

## Cost estimate is an editable assumption, not billing data

`token_prices.json` holds USD-per-1M-token prices per model family (`opus`/`sonnet`/`haiku`), matched
against `message.model` by substring. It is **hand-maintained**, not fetched from any pricing API —
see its `_comment` field. When Anthropic changes list prices, or a new model family shows up that
isn't in the file yet, edit the JSON by hand; `token_usage.py` never makes a network call. Model
strings that don't match any known family (or whose family is missing a price row) still get their
tokens counted, just at $0 cost, and the report prints a warning line naming the exact unrecognized
strings so the gap doesn't hide silently.

`<synthetic>` rows (session-limit / API-error placeholders, detected via `isApiErrorMessage` or
`message.model == "<synthetic>"`) are handled separately from "unknown model": their usage is always
zero, they're counted as `API-ошибок: N` and excluded from both the model-mix and the unknown-model
warning, since they aren't a pricing gap — they're the log's own error placeholder.

## Headline metric

The old headline, `non-cache-read итого` (input + output + cache_creation), covered ~42% of the real
dollar cost on the sample session — `cache_read` is the cheapest token type per-unit but the largest
by volume, so it dominates the bill (58% of cost in that session) while being invisible in that
metric. The report now leads with a cost estimate broken down by component (cache_read / cache_write
/ output / input), by model family, and by agent (sorted by cost, not tokens) — token counts are kept
as supporting detail, not the headline.

## Historical comparisons are invalid

**Every token report produced by this script before 2026-09-03 is inflated by roughly 1.8x on
non-cache-read tokens** (measured: raw non-cache-read 33 547 585 vs. correct 18 326 965 on the
session used to diagnose this — inflation 83%). Do not compare a pre-fix number to a post-fix number;
re-run the fixed script against the same session if a like-for-like comparison is needed.

## Verification against a real closed session

`--session-id 13fcbb1d-1685-468f-b0af-478947f119fd --full` (the session was still receiving new rows
from this very developer subagent's own tool calls while this was run, so totals are a bit higher
than the numbers captured at spec-writing time, but the shape matches closely):

- non-cache-read ≈ 19.15M, cache_read ≈ 482.7M, total cost ≈ $392.93 (spec estimate: ≈18.33M /
  ≈469.9M / ≈$390)
- MAIN ≈ $152.00 (spec: ≈$149), top subagent `developer` ≈ $51.95 (spec: ≈$52), `qa` on opus ≈ $48.16
  (spec: ≈$48)
- cost split: cache_read 58%, cache_write 31%, output 11%, input <1% — matches the spec's stated split
  exactly
- 15 `<synthetic>` rows correctly reported as `API-ошибок: 15`, zero unknown-model warnings (no model
  strings outside opus/sonnet/haiku appeared in this session)

## Tests

`PYTHONUTF8=1 python -m pytest .claude/scripts/tests/test_token_usage.py -v` — 26 passed. Full folder
suite (`.claude/scripts/tests`) — 207 passed, nothing else broke.

Covered: multi-block rows sharing one `message.id` collapse to one message; streaming-partial
`output_tokens` (4 → 159) takes the max while cache fields aren't doubled; rows without `message.id`
stay separate; `cost_usd` against a hand-computed value; unknown model family → $0 cost + warning, no
crash; `<synthetic>`/`isApiErrorMessage` rows counted as API errors, not unknown models; per-component
and per-agent costs sum back to the grand total (single-source-of-truth invariant in `aggregate()`);
`agent_display_name` uses `agentType` from the sibling `.meta.json`, falls back to the file stem;
long-context warning fires only past the 10% threshold; read-only guarantee (byte-identical
before/after a run, plus a source grep for write-y calls, same pattern as `status_query.py`).
