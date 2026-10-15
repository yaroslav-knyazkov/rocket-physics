#!/usr/bin/env python3
"""Session token accounting (main thread + all subagents).

Called by hand by the orchestrator at the end of a block (see
.claude/agents/orchestrator.md "## Main thread cost discipline" ->
"### Token summary after a block") -- same trigger as a commit and the
/compact reminder. Not a hook: the Stop hook fires on EVERY turn, not only
at the end of a block, so there is no automatic settings.json wiring --
invoked by hand, the same way telegram_notify.py is invoked by hand for
AskUserQuestion (see .claude/agents/orchestrator.md "## Telegram
notification before AskUserQuestion").

Data source — the raw Claude Code .jsonl logs:
  ~/.claude/projects/<project-slug>/<session_id>.jsonl                 — main thread
  ~/.claude/projects/<project-slug>/<session_id>/subagents/*.jsonl     — subagents
  ~/.claude/projects/<project-slug>/<session_id>/subagents/*.meta.json — agent type per subagent

session_id comes from env CLAUDE_CODE_SESSION_ID (available in the Claude Code
session's Bash tool) — no need to look up/recompute the project slug: session_id
is globally unique, we glob for the file by name across all project folders.

Accounting fix (2026-09): Claude Code writes ONE .jsonl row per content block
of an assistant message (thinking / text / each tool_use), and every row
repeats the SAME message.usage object — except output_tokens, which can be
lower on early streaming-partial rows for the same message. Summing every row
(the old approach) double- to quadruple-counts input/cache tokens. This
version groups rows *per file* by message["id"] and takes max() per usage key
within a group before summing groups — see load_messages() below and
token_usage.notes.md for the full write-up, including why every report
produced before this fix is inflated (~1.8x on non-cache-read).

Headline fix (2026-09): "non-cache-read итого" (input+output+cache_creation)
used to be presented as the top-line cost signal, but cache_read is usually
the largest dollar cost even though it is the cheapest token type — on a
sample session it was 58% of the bill while invisible in that metric. Cost is
now estimated from a human-edited price file (token_prices.json), not pulled
from any billing API — see that file's _comment field for the caveat.

Usage:
  python .claude/scripts/token_usage.py                   # current session (env)
  python .claude/scripts/token_usage.py --session-id ID    # explicit session_id
  python .claude/scripts/token_usage.py --full             # full per-agent ranking
  python .claude/scripts/token_usage.py --json              # machine-readable output
  python .claude/scripts/token_usage.py --live              # cheap mid-block check

--live is meant to be run by the orchestrator *between* SendMessage rounds of a
long-lived subagent chain, to decide whether to break the chain and respawn.
Subagent .jsonl files are appended as agents run and are complete between
rounds, so peak/median context per agent is measurable there, not guesswork —
an agent sitting at/над 200k context costs more per round (cache_write
re-pricing the whole history) than a fresh spawn would. Output is deliberately
compact: this is read by an agent whose context we are trying to save.
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Windows console (cp1252/cp866) cannot encode Cyrillic/unicode arrows directly —
# switch stdout/stderr to UTF-8 explicitly, otherwise print() raises UnicodeEncodeError.
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name)
    if (getattr(_stream, "encoding", "") or "").lower() != "utf-8" and hasattr(_stream, "buffer"):
        setattr(sys, _name, io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="replace"))

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

# usage-key -> price-file component name
COMPONENT_OF = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cache_creation_input_tokens": "cache_write",
    "cache_read_input_tokens": "cache_read",
}

SYNTHETIC_MODEL = "<synthetic>"
MODEL_FAMILIES = ("opus", "sonnet", "haiku")   # substring match, in this order
LONG_CONTEXT_TOKENS = 200_000
LONG_CONTEXT_WARN_FRACTION = 0.10
PRICE_UNITS = 1_000_000   # prices in token_prices.json are USD per this many tokens
DEFAULT_TOP_N = 8

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_PRICE_FILE = SCRIPT_DIR / "token_prices.json"
DEFAULT_AGENTS_DIR = SCRIPT_DIR.parent / "agents"
LIVE_MAX_ROWS = 12
FRONTMATTER_SCAN_LINES = 12


# ---------------------------------------------------------------------------
# per-message extraction (the dedup fix lives here)
# ---------------------------------------------------------------------------

def load_messages(path: Path) -> list[dict]:
    """Parse one .jsonl log file into deduplicated per-message usage records.

    Claude Code writes one row per content block of an assistant message
    (thinking / text / each tool_use), and every row repeats the SAME
    `message.usage` object — except `output_tokens`, which can be lower on
    early streaming-partial rows for the same message. Grouping by
    `message.id` and taking max() per usage key within a group collapses that
    duplication without ever undercounting: max beats "first" (which would
    under-report output_tokens) and "last" (fragile to row order — nothing
    guarantees the final row of a group is the final streaming state).

    Rows without a message.id get a synthetic per-row key (f"_anon{row_index}")
    so they are never merged with each other or with real messages.
    `id(obj)` is deliberately not used as a fallback key: CPython reuses
    object ids after garbage collection, so two unrelated dicts can share an
    id() and would silently collapse into one group.

    Returns one dict per logical message: {"model": str|None,
    "usage": {...4 keys...}, "is_error": bool}. Rows without `message.usage`
    carry no accounting information and are skipped.
    """
    groups: dict[str, dict] = {}
    try:
        with path.open(encoding="utf-8") as f:
            for row_index, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = row.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not usage:
                    continue
                model = msg.get("model")
                is_error = bool(row.get("isApiErrorMessage")) or model == SYNTHETIC_MODEL
                key = msg.get("id") or f"_anon{row_index}"
                group = groups.get(key)
                if group is None:
                    group = {"model": model, "usage": {k: 0 for k in USAGE_KEYS}, "is_error": is_error}
                    groups[key] = group
                else:
                    group["is_error"] = group["is_error"] or is_error
                    if group["model"] is None:
                        group["model"] = model
                for k in USAGE_KEYS:
                    val = usage.get(k) or 0
                    if val > group["usage"][k]:
                        group["usage"][k] = val
    except FileNotFoundError:
        pass
    return list(groups.values())


def net_tokens(usage: dict) -> int:
    return sum(usage[k] for k in USAGE_KEYS)


# ---------------------------------------------------------------------------
# pricing
# ---------------------------------------------------------------------------

def model_family(model: str | None) -> str | None:
    """Map a raw model string (e.g. 'claude-opus-5') to a pricing family by substring."""
    if not model:
        return None
    low = model.lower()
    for fam in MODEL_FAMILIES:
        if fam in low:
            return fam
    return None


def load_prices(path: Path) -> dict:
    """Load the editable price table. Missing/unreadable file -> {} (every cost is 0)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def classify_model(model: str | None, prices: dict) -> tuple[str, dict | None]:
    """(bucket label, price row) for one message's model. Price row is None when unpriced."""
    fam = model_family(model)
    if fam is None:
        return "unknown", None
    return fam, prices.get(fam)


def cost_components(usage: dict, price: dict | None) -> dict[str, float]:
    """USD cost per pricing component for one message's usage; all zero if price is None."""
    if not price:
        return {c: 0.0 for c in COMPONENT_OF.values()}
    return {c: usage[uk] * price.get(c, 0) / PRICE_UNITS for uk, c in COMPONENT_OF.items()}


def cost_usd(usage: dict, price: dict | None) -> float:
    return sum(cost_components(usage, price).values())


# ---------------------------------------------------------------------------
# per-agent / global aggregation
# ---------------------------------------------------------------------------

@dataclass
class AgentReport:
    name: str
    messages: list[dict]           # raw per-message records from load_messages()
    tokens: dict[str, int]         # summed usage keys across every message (incl. error rows, which are all-zero)
    cost: float
    model_mix: list[tuple[str, int]]   # [(family_or_unknown, message_count), ...] sorted desc, error rows excluded
    api_errors: int
    peak_ctx: int = 0
    median_ctx: int = 0
    model_override: str | None = None   # explicit model= passed at spawn time, if any
    model_default: str | None = None    # agent's frontmatter default, if resolvable


def message_context(m: dict) -> int:
    """Context size of one message — cache_read + cache_creation, same definition
    aggregate() uses for the LONG_CONTEXT_TOKENS check. One definition, reused."""
    usage = m["usage"]
    return usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"]


def context_stats(messages: list[dict]) -> tuple[int, int]:
    """(peak_ctx, median_ctx) across non-error messages. Empty input -> (0, 0).

    Median is the value at index len//2 of the sorted list (upper-middle element
    for an even count) — deterministic, no averaging of the two middle values.
    """
    values = sorted(message_context(m) for m in messages if not m["is_error"])
    if not values:
        return 0, 0
    peak = values[-1]
    median = values[len(values) // 2]
    return peak, median


def load_agent_meta(jsonl_path: Path) -> dict:
    """Load a subagent's sibling .meta.json, or {} when missing/unreadable/not a dict."""
    meta_path = jsonl_path.parent / f"{jsonl_path.stem}.meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def agent_display_name(jsonl_path: Path, meta: dict | None = None) -> str:
    """Resolve a subagent's display name from its sibling .meta.json `agentType`.

    Falls back to the file stem (e.g. `agent-a02cdde7822ee23e0`) when the meta
    file is missing, unreadable, or lacks the field. `meta` may be passed in to
    avoid re-reading the file when the caller already loaded it.
    """
    if meta is None:
        meta = load_agent_meta(jsonl_path)
    agent_type = meta.get("agentType") if isinstance(meta, dict) else None
    return agent_type if isinstance(agent_type, str) and agent_type else jsonl_path.stem


def load_frontmatter_default_model(agent_type: str, agents_dir: Path | None = None) -> str | None:
    """Read `model:` from the first lines of `<agents_dir>/<agent_type>.md` frontmatter.

    Missing directory, missing file, or missing field -> None. Never raises —
    the script must stay runnable from any cwd and on machines where the
    agents folder does not exist. `agents_dir` defaults to the module-level
    DEFAULT_AGENTS_DIR, looked up dynamically (not as a function default) so
    tests can monkeypatch the module attribute.
    """
    if agents_dir is None:
        agents_dir = DEFAULT_AGENTS_DIR
    agent_file = agents_dir / f"{agent_type}.md"
    try:
        with agent_file.open(encoding="utf-8") as f:
            for _ in range(FRONTMATTER_SCAN_LINES):
                line = f.readline()
                if not line:
                    break
                match = re.match(r"^model:\s*(\S+)", line)
                if match:
                    return match.group(1)
    except OSError:
        return None
    return None


def build_agent_report(name: str, path: Path, prices: dict,
                        model_override: str | None = None,
                        model_default: str | None = None) -> AgentReport:
    messages = load_messages(path)
    tokens = {k: 0 for k in USAGE_KEYS}
    cost = 0.0
    mix: Counter[str] = Counter()
    api_errors = 0
    for m in messages:
        usage = m["usage"]
        for k in USAGE_KEYS:
            tokens[k] += usage[k]
        if m["is_error"]:
            api_errors += 1
            continue
        label, price = classify_model(m["model"], prices)
        mix[label] += 1
        cost += cost_usd(usage, price)
    peak_ctx, median_ctx = context_stats(messages)
    return AgentReport(name=name, messages=messages, tokens=tokens, cost=cost,
                        model_mix=mix.most_common(), api_errors=api_errors,
                        peak_ctx=peak_ctx, median_ctx=median_ctx,
                        model_override=model_override, model_default=model_default)


@dataclass
class Aggregate:
    grand_tokens: dict[str, int]
    grand_cost: float
    component_cost: dict[str, float]        # input/output/cache_write/cache_read, USD
    family_stats: dict[str, dict]           # label -> {tokens, cost, messages}
    unknown_models: set[str] = field(default_factory=set)
    api_errors: int = 0
    context_over_200k: int = 0
    context_total: int = 0


def aggregate(reports: list[AgentReport], prices: dict) -> Aggregate:
    """Single pass over every message across every agent — the one source of truth.

    Doing this in one place (rather than recomputing sums per-table) guarantees
    the per-component cost split, the per-model table and the grand total always
    add up to the same numbers, which is exactly the property the report needs
    to be trustworthy.
    """
    grand_tokens = {k: 0 for k in USAGE_KEYS}
    component_cost = {c: 0.0 for c in COMPONENT_OF.values()}
    family_stats: dict[str, dict] = {}
    unknown_models: set[str] = set()
    api_errors = 0
    over = 0
    total_ctx = 0

    for rep in reports:
        for m in rep.messages:
            usage = m["usage"]
            for k in USAGE_KEYS:
                grand_tokens[k] += usage[k]
            total_ctx += 1
            if usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"] > LONG_CONTEXT_TOKENS:
                over += 1
            if m["is_error"]:
                api_errors += 1
                continue
            label, price = classify_model(m["model"], prices)
            if price is None:
                unknown_models.add(m["model"] or "(empty model)")
            bucket = family_stats.setdefault(
                label, {"tokens": {k: 0 for k in USAGE_KEYS}, "cost": 0.0, "messages": 0})
            for k in USAGE_KEYS:
                bucket["tokens"][k] += usage[k]
            bucket["messages"] += 1
            parts = cost_components(usage, price)
            for c, v in parts.items():
                component_cost[c] += v
            bucket["cost"] += sum(parts.values())

    grand_cost = sum(component_cost.values())
    return Aggregate(grand_tokens=grand_tokens, grand_cost=grand_cost, component_cost=component_cost,
                      family_stats=family_stats, unknown_models=unknown_models, api_errors=api_errors,
                      context_over_200k=over, context_total=total_ctx)


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------

def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fmt_usd(x: float) -> str:
    return "$" + f"{x:,.2f}".replace(",", " ")


def fmt_ctx(n: int) -> str:
    """Context size as integer thousands, e.g. 273000 -> '273k'."""
    return f"{n / 1000:.0f}k"


def format_mix(mix: list[tuple[str, int]]) -> str:
    return ", ".join(f"{label}×{n}" for label, n in mix) if mix else "—"


def price_ref(path: Path) -> str:
    """Short project-relative reference for the price file, for the disclaimer line."""
    try:
        if path.resolve().parent == SCRIPT_DIR:
            return f".claude/scripts/{path.name}"
    except OSError:
        pass
    return str(path)


def find_session_file(session_id: str, projects_root: Path) -> Path | None:
    matches = list(projects_root.glob(f"*/{session_id}.jsonl"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# model-vs-frontmatter audit
# ---------------------------------------------------------------------------

def _model_tier_rank(family: str | None) -> int | None:
    """Position in MODEL_FAMILIES (0=opus..2=haiku, i.e. lower rank = pricier/bigger tier)."""
    try:
        return MODEL_FAMILIES.index(family)
    except (ValueError, TypeError):
        return None


def build_model_overrides(reports: list[AgentReport], prices: dict) -> list[dict]:
    """Classify each subagent's explicit model= (if any) against its frontmatter default.

    MAIN is never part of this audit (its model is a human choice, frontmatter
    is `inherit`). No `model` key in .meta.json -> no entry at all: that is the
    unambiguous "default was used" case, nothing to flag.

    kind is one of:
      - "redundant"  — override equals the default, the parameter is a no-op
      - "upgrade"    — override is a pricier tier than the default (allowed with a stated reason)
      - "downgrade"  — override is a cheaper tier than the default (forbidden by project rule,
                       except architect on an incremental stage over an already-approved stack)
      - "mismatch"   — different family but direction can't be ranked (unknown family)

    Sorted by absolute cost delta (override vs counterfactual-at-default) descending,
    so the biggest deviation is always the first line; entries without a computable
    delta (redundant, or unpriced default family) sort last.
    """
    out = []
    for r in reports:
        if r.name == "MAIN" or not r.model_override:
            continue
        if r.model_default is None:
            # can't classify without knowing the default — skip silently
            continue
        entry = {
            "name": r.name,
            "model_override": r.model_override,
            "model_default": r.model_default,
            "cost_usd": round(r.cost, 4),
        }
        if r.model_override == r.model_default:
            entry["kind"] = "redundant"
        else:
            override_rank = _model_tier_rank(r.model_override)
            default_rank = _model_tier_rank(r.model_default)
            if override_rank is not None and default_rank is not None and override_rank != default_rank:
                entry["kind"] = "upgrade" if override_rank < default_rank else "downgrade"
            else:
                entry["kind"] = "mismatch"
            default_price = prices.get(r.model_default)
            if default_price is not None:
                counterfactual = sum(
                    cost_usd(m["usage"], default_price) for m in r.messages if not m["is_error"]
                )
                entry["counterfactual_cost_usd"] = round(counterfactual, 4)
        out.append(entry)

    def sort_key(e: dict) -> float:
        if "counterfactual_cost_usd" in e:
            return abs(e["cost_usd"] - e["counterfactual_cost_usd"])
        return 0.0

    out.sort(key=sort_key, reverse=True)
    return out


def render_model_overrides(overrides: list[dict]) -> list[str]:
    """Markdown lines for the 'Модель против дефолта' section — empty if nothing to say."""
    if not overrides:
        return []
    lines = ["", "Модель против дефолта:"]
    for o in overrides:
        if o["kind"] == "redundant":
            lines.append(
                f"- {o['name']}: model={o['model_override']} передан явно, но это и есть "
                "дефолт фронтматтера — параметр лишний."
            )
            continue

        if "counterfactual_cost_usd" in o:
            diff = o["cost_usd"] - o["counterfactual_cost_usd"]
            sign = "−" if diff < 0 else "+"
            money = (f"{fmt_usd(o['cost_usd'])} против ~{fmt_usd(o['counterfactual_cost_usd'])} на дефолте "
                     f"({sign}{fmt_usd(abs(diff))})")
        else:
            money = "цена дефолтного семейства неизвестна"

        base = f"- {o['name']}: {o['model_override']} вместо {o['model_default']} по фронтматтеру — {money}"
        if o["kind"] == "upgrade":
            lines.append(base + ". Апгрейд, нужна причина в decisions.")
        elif o["kind"] == "downgrade":
            lines.append(base + ". Понижение против фронтматтера — по правилу запрещено "
                                 "(исключение: architect на инкрементальной стадии).")
        else:
            lines.append(base + ".")
    return lines


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def render_report(session_id: str, reports: list[AgentReport], agg: Aggregate,
                   price_file: Path, top_n: int, full: bool, prices: dict) -> tuple[list[str], dict]:
    t = agg.grand_tokens
    non_cache_read = t["input_tokens"] + t["output_tokens"] + t["cache_creation_input_tokens"]
    all_in = net_tokens(t)
    total_cost = agg.grand_cost
    ref = price_ref(price_file)

    def pct(x: float) -> str:
        return f"{(x / total_cost * 100):.0f}%" if total_cost else "0%"

    lines = [f"Итог по сессии `{session_id[:8]}…` (главный поток + все саб-агенты):", ""]
    lines += [
        "| Тип | Токены |",
        "|---|---|",
        f"| output | {fmt(t['output_tokens'])} |",
        f"| input (свежий) | {fmt(t['input_tokens'])} |",
        f"| cache_write (запись кэша) | {fmt(t['cache_creation_input_tokens'])} |",
        f"| cache_read (чтение кэша) | {fmt(t['cache_read_input_tokens'])} |",
        f"| **non-cache-read итого** | **≈{fmt(non_cache_read)}** |",
        f"| **всё вместе (вкл. cache_read)** | **≈{fmt(all_in)}** |",
        "",
        "«non-cache-read итого» — прежняя headline-метрика; она отражает лишь часть "
        "реальных затрат. cache_read дешёв за токен, но по объёму обычно доминирует — "
        "стоимость по компонентам ниже.",
        "",
        f"**Оценочная стоимость (`{ref}`): {fmt_usd(total_cost)}**",
        "",
        "| Компонент | Стоимость | Доля |",
        "|---|---|---|",
        f"| cache_read | {fmt_usd(agg.component_cost['cache_read'])} | {pct(agg.component_cost['cache_read'])} |",
        f"| cache_write | {fmt_usd(agg.component_cost['cache_write'])} | {pct(agg.component_cost['cache_write'])} |",
        f"| output | {fmt_usd(agg.component_cost['output'])} | {pct(agg.component_cost['output'])} |",
        f"| input | {fmt_usd(agg.component_cost['input'])} | {pct(agg.component_cost['input'])} |",
        "",
        "По моделям:",
        "",
        "| Модель | Сообщений | Токены (нетто) | Стоимость |",
        "|---|---|---|---|",
    ]
    family_rows = sorted(agg.family_stats.items(), key=lambda kv: -kv[1]["cost"])
    for label, st in family_rows:
        lines.append(f"| {label} | {st['messages']} | {fmt(net_tokens(st['tokens']))} | {fmt_usd(st['cost'])} |")

    ranked = sorted(reports, key=lambda r: (-r.cost, r.name))
    shown = ranked if full else ranked[:top_n]
    lines += [
        "",
        f"Топ {'все' if full else len(shown)} из {len(ranked)} по стоимости:",
        "",
        "| # | Стоимость | Агент | Сообщ. | Модели | cache_write | cache_read | Пик ctx | Медиана ctx |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(shown, 1):
        lines.append(
            f"| {i} | {fmt_usd(r.cost)} | {r.name} | {len(r.messages)} | {format_mix(r.model_mix)} | "
            f"{fmt(r.tokens['cache_creation_input_tokens'])} | {fmt(r.tokens['cache_read_input_tokens'])} | "
            f"{fmt_ctx(r.peak_ctx)} | {fmt_ctx(r.median_ctx)} |"
        )
    if not full and len(ranked) > top_n:
        lines.append("")
        lines.append(f"… ещё {len(ranked) - top_n} агентов — `--full`.")

    lines.append("")
    if agg.api_errors:
        lines.append(f"API-ошибок: {agg.api_errors} (модель `<synthetic>`, стоимость $0, "
                      "не искажают оценку).")
    if agg.unknown_models:
        lines.append("Внимание: неизвестны модели (токены посчитаны, стоимость $0): "
                      + ", ".join(sorted(agg.unknown_models)) + f" — впиши цену в `{ref}`.")
    if agg.context_total and agg.context_over_200k / agg.context_total > LONG_CONTEXT_WARN_FRACTION:
        over_pct = agg.context_over_200k / agg.context_total * 100
        lines.append(
            f"Внимание: у {agg.context_over_200k} из {agg.context_total} сообщений ({over_pct:.0f}%) "
            f"контекст (cache_read+cache_write) превышает {fmt(LONG_CONTEXT_TOKENS)} токенов — "
            f"провайдеры берут надбавку за тир >200k, а `{ref}` тарификацию по тирам не моделирует, "
            "оценка стоимости может быть занижена."
        )
    lines.append(f"Цены — редактируемое предположение в `{ref}`, не тянутся из API.")

    model_overrides = build_model_overrides(reports, prices)
    lines += render_model_overrides(model_overrides)

    main_rep = next((r for r in reports if r.name == "MAIN"), None)
    if main_rep is not None:
        main_non_cache = (main_rep.tokens["input_tokens"] + main_rep.tokens["output_tokens"]
                           + main_rep.tokens["cache_creation_input_tokens"])
        lines.append(
            f"Для справки: главный поток (без саб-агентов) — {len(main_rep.messages)} сообщений, "
            f"~{fmt(main_non_cache)} non-cache-read токенов, {fmt_usd(main_rep.cost)}. "
            f"Саб-агентских вызовов: {len(reports) - 1}."
        )

    data = {
        "session_id": session_id,
        "tokens": t,
        "non_cache_read": non_cache_read,
        "all_in": all_in,
        "cost_usd": round(total_cost, 4),
        "cost_by_component": {k: round(v, 4) for k, v in agg.component_cost.items()},
        "by_model": {
            label: {"messages": st["messages"], "tokens": st["tokens"], "cost_usd": round(st["cost"], 4)}
            for label, st in family_rows
        },
        "agents": [
            {"name": r.name, "cost_usd": round(r.cost, 4), "messages": len(r.messages),
             "model_mix": dict(r.model_mix), "cache_write": r.tokens["cache_creation_input_tokens"],
             "cache_read": r.tokens["cache_read_input_tokens"], "api_errors": r.api_errors,
             "peak_ctx": r.peak_ctx, "median_ctx": r.median_ctx,
             "model_override": r.model_override, "model_default": r.model_default}
            for r in ranked
        ],
        "api_errors": agg.api_errors,
        "unknown_models": sorted(agg.unknown_models),
        "long_context": {"over_200k": agg.context_over_200k, "total": agg.context_total},
        "price_file": str(price_file),
        "model_overrides": model_overrides,
    }
    return lines, data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--session-id",
        default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
        help="Session id (default: $CLAUDE_CODE_SESSION_ID)",
    )
    parser.add_argument(
        "--projects-root", type=Path, default=DEFAULT_PROJECTS_ROOT,
        help="Override ~/.claude/projects (mainly for tests)",
    )
    parser.add_argument(
        "--price-file", type=Path, default=DEFAULT_PRICE_FILE,
        help="Path to the editable USD-per-1M-token price table (default: token_prices.json next to this script)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help=f"show every agent in the cost ranking, not just the top {DEFAULT_TOP_N}",
    )
    parser.add_argument(
        "--json", dest="json_out", action="store_true",
        help="machine-readable JSON output instead of the markdown report",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="compact mid-block check (peak/median ctx per agent) instead of the full report",
    )
    return parser


def render_live(reports_with_paths: list[tuple[AgentReport, Path]]) -> tuple[list[str], dict]:
    """Compact peak-context ranking for a mid-block SendMessage-chain check.

    No token tables, no component split, no price disclaimer — those belong to
    the full report. At most LIVE_MAX_ROWS rows, sorted by peak context desc,
    MAIN always included.
    """
    ranked = sorted(reports_with_paths, key=lambda rp: (-rp[0].peak_ctx, rp[0].name))
    shown = ranked[:LIVE_MAX_ROWS]

    rows = []
    for r, path in shown:
        try:
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
            last_activity = mtime.strftime("%H:%M")
        except OSError:
            last_activity = "—"
        rows.append({
            "name": r.name, "messages": len(r.messages), "peak_ctx": r.peak_ctx,
            "median_ctx": r.median_ctx, "last_activity": last_activity, "cost_usd": round(r.cost, 4),
        })

    lines = ["Live-срез контекста по агентам:", "", "| Агент | Сообщ. | Пик ctx | Медиана ctx | Активность | Стоимость |",
              "|---|---|---|---|---|---|"]
    for row in rows:
        lines.append(
            f"| {row['name']} | {row['messages']} | {fmt_ctx(row['peak_ctx'])} | {fmt_ctx(row['median_ctx'])} | "
            f"{row['last_activity']} | {fmt_usd(row['cost_usd'])} |"
        )
    if len(ranked) > LIVE_MAX_ROWS:
        lines.append("")
        lines.append(f"… ещё {len(ranked) - LIVE_MAX_ROWS} агентов не показано.")

    data = {"agents": rows}
    return lines, data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    session_id = args.session_id
    if not session_id:
        print("Ошибка: session_id не передан и CLAUDE_CODE_SESSION_ID не задан в окружении.", file=sys.stderr)
        return 1

    main_file = find_session_file(session_id, args.projects_root)
    if main_file is None:
        root_display = ("~/.claude/projects" if args.projects_root == DEFAULT_PROJECTS_ROOT
                         else str(args.projects_root))
        print(f"Ошибка: файл сессии {session_id}.jsonl не найден в {root_display}/*/", file=sys.stderr)
        return 1

    prices = load_prices(args.price_file)

    reports = [build_agent_report("MAIN", main_file, prices)]
    report_paths = [main_file]
    subagents_dir = main_file.parent / session_id / "subagents"
    subagent_files = sorted(subagents_dir.glob("*.jsonl")) if subagents_dir.is_dir() else []
    for sf in subagent_files:
        meta = load_agent_meta(sf)
        name = agent_display_name(sf, meta=meta)
        model_override = meta.get("model") if isinstance(meta.get("model"), str) else None
        agent_type = meta.get("agentType") if isinstance(meta.get("agentType"), str) else None
        model_default = load_frontmatter_default_model(agent_type) if agent_type else None
        reports.append(build_agent_report(name, sf, prices,
                                           model_override=model_override, model_default=model_default))
        report_paths.append(sf)

    if args.live:
        lines, data = render_live(list(zip(reports, report_paths)))
        if args.json_out:
            print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        else:
            print("\n".join(lines))
        return 0

    agg = aggregate(reports, prices)
    lines, data = render_report(session_id, reports, agg, args.price_file, DEFAULT_TOP_N, args.full, prices)

    if args.json_out:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
