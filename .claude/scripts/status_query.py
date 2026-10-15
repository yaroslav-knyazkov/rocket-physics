#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Окно в трекер проекта: срез dev/status.json вместо чтения файла целиком.

Живой трекер ~150 KB (~37k токенов на одно чтение), архив ~470 KB. Каждый
спавн субагента, читающий их целиком, платит эту цену заново. Скрипт отдаёт
только запрошенный кусок — типичный ответ 1-3 KB.

Скрипт строго read-only: открывает оба файла на чтение и печатает в stdout,
больше ничего (ни файлов, ни каталогов, ни git). Это его ключевое свойство —
его можно давать субагентам без ограничений.

Подкоманды:
  toc                      оглавление: стадии, top-level ключи, счётчики решений
  current                  «что знать на входе»: текущая стадия, открытые пункты
  stage <id> [--sub k1,k2] стадия целиком или только указанные подключи
  key <name>               top-level ключ (в архиве — legacy_keys)
  decisions [--since ...]  отбор решений по дате/подстроке
  search <substr>          поиск по ключам и значениям обоих файлов, сниппетами
  path <expr>              точечный доступ: stages[35].w4.tickets

Markdown-трекер (dev/PROJECT-STATUS.md, dev/journal.md) — те же принципы:
  md-toc                   оглавление трекера: секции, размеры, строки
  md-section <N|подстрока> одна секция трекера целиком (или её подзаголовки)
  md-journal [--last N]    записи журнала: свежие / по дате / по подстроке
  md-risks [--all]         §8 «Риски» строками: по умолчанию только открытые

Примеры:
  python .claude/scripts/status_query.py toc
  python .claude/scripts/status_query.py current
  python .claude/scripts/status_query.py stage 35 --sub next,w4
  python .claude/scripts/status_query.py decisions --since 2026-08-01 --archive
  python .claude/scripts/status_query.py search "селектор темы" --limit 10
  python .claude/scripts/status_query.py path "stages[35].w4.tickets" --json
  python .claude/scripts/status_query.py md-toc
  python .claude/scripts/status_query.py md-section 7
  python .claude/scripts/status_query.py md-journal --last 3 --titles
  python .claude/scripts/status_query.py md-risks --grep миграц

Коды возврата: 0 — ок; 1 — ошибка аргументов или файлов; 2 — не найдено
(стадия/ключ/путь/совпадения), в сообщении подсказка ближайших вариантов.
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# Windows-консоль (cp1252/cp866) не кодирует кириллицу и стрелку «→» —
# переключаем stdout/stderr на UTF-8 явно, иначе UnicodeEncodeError на print().
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name)
    if (getattr(_stream, "encoding", "") or "").lower() != "utf-8" and hasattr(_stream, "buffer"):
        setattr(sys, _name, io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="replace"))

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATUS = REPO_ROOT / "dev" / "status.json"
DEFAULT_ARCHIVE = REPO_ROOT / "dev" / "status-archive.json"
DEFAULT_TRACKER = REPO_ROOT / "dev" / "PROJECT-STATUS.md"
DEFAULT_JOURNAL = REPO_ROOT / "dev" / "journal.md"
DEFAULT_MD_ARCHIVE = REPO_ROOT / "dev" / "docs" / "project-status-archive.md"

DEFAULT_MAX_KB = 24
FOLD_BYTES = 1024          # подключ стадии крупнее — в `stage <id>` сворачиваем в строку
DECISIONS_LIMIT = 25       # решений в одном ответе по умолчанию (самые свежие)
STUB_KEYS = {"id", "name", "status", "archived"}
POINTER_PREFIX = "archived → "
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEGMENT_RE = re.compile(r"([^.\[\]]+)|\[([^\]]*)\]")


class QueryError(Exception):
    """Не нашли то, что просили. Печатается без traceback, exit code 2."""

    def __init__(self, message: str, hints: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.hints = hints or []


class SystemExitError(Exception):
    """Проблема с аргументами/файлами: exit code 1, тоже без traceback."""


# ---------------------------------------------------------------------------
# мелкие помощники (сознательно продублированы из archive_status.py — там они
# соседствуют с пишущим кодом, а этот скрипт должен быть read-only «на глаз»)
# ---------------------------------------------------------------------------

def sid(stage: dict) -> str:
    """id стадий разнотипны (int 35 и str '4.1'/'21b') — сравниваем по str."""
    return str(stage.get("id"))


def is_stub(stage: dict) -> bool:
    return stage.get("archived") is True and set(stage) <= STUB_KEYS


def is_pointer(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(POINTER_PREFIX)


def jsize(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def clip(text: Any, width: int = 60) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= width else s[: width - 1] + "…"


def load(path: Path, what: str) -> dict:
    if not path.is_file():
        raise SystemExitError(f"{what} не найден — {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExitError(f"{what} не читается ({path}): {exc}")


def suggest(name: str, candidates: list[str], limit: int = 6) -> list[str]:
    """Подсказка «может, ты имел в виду»: подстрока, затем difflib."""
    low = name.lower()
    out = [c for c in candidates if low in c.lower() or c.lower() in low]
    for c in difflib.get_close_matches(name, candidates, n=limit, cutoff=0.4):
        if c not in out:
            out.append(c)
    if not out:
        out = candidates[:limit]
    return out[:limit]


def short_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# рендер значений: мини-YAML, компактнее JSON с отступами и читаемее для агента
# ---------------------------------------------------------------------------

def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_value(value: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        if not value:
            lines.append(pad + "{}")
        for k, v in value.items():
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}{k}:")
                lines.extend(render_value(v, indent + 1))
            elif isinstance(v, str) and "\n" in v:
                lines.append(f"{pad}{k}:")
                lines.extend(pad + "  " + s for s in v.split("\n"))
            elif isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}: " + ("{}" if isinstance(v, dict) else "[]"))
            else:
                lines.append(f"{pad}{k}: {_scalar(v)}")
    elif isinstance(value, list):
        if not value:
            lines.append(pad + "[]")
        for item in value:
            if isinstance(item, (dict, list)) and item:
                block = render_value(item, indent + 1)
                lines.append(f"{pad}- {block[0].lstrip()}")
                lines.extend(block[1:])
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    elif isinstance(value, str):
        lines.extend(pad + s for s in value.split("\n"))
    else:
        lines.append(pad + _scalar(value))
    return lines


# ---------------------------------------------------------------------------
# результат команды: данные для --json, строки для --md, откуда взято
# ---------------------------------------------------------------------------

@dataclass
class Result:
    data: dict
    lines: list[str] = field(default_factory=list)
    source: str = ""
    hint_path: str = ""


@dataclass
class Ctx:
    live: dict
    archive: dict
    live_name: str
    archive_name: str
    args: argparse.Namespace

    def stage_ids(self) -> list[str]:
        ids = [sid(s) for s in self.live.get("stages", [])]
        for s in self.archive.get("stages", []):
            if sid(s) not in ids:
                ids.append(sid(s))
        return ids

    def find_stage(self, stage_id: str) -> tuple[dict, str]:
        """Стадия + источник. Стуб в живом → полный текст берём из архива."""
        live_hit = next((s for s in self.live.get("stages", []) if sid(s) == stage_id), None)
        arch_hit = next((s for s in self.archive.get("stages", []) if sid(s) == stage_id), None)
        if live_hit is not None and not is_stub(live_hit) and not self.args.archive:
            return live_hit, self.live_name
        if arch_hit is not None:
            return arch_hit, self.archive_name
        if live_hit is not None:
            return live_hit, f"{self.live_name} (стуб; полного текста в архиве нет)"
        raise QueryError(
            f"стадии {stage_id} нет ни в живом файле, ни в архиве",
            suggest(stage_id, self.stage_ids()),
        )

    def resolve_pointer(self, pointer: str) -> tuple[Any, str]:
        """'archived → dev/status-archive.json stage_subkeys.35.w1' → значение."""
        dotted = pointer.split()[-1]
        node: Any = self.archive
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                raise QueryError(f"указатель на архив не разрешается: {pointer!r}")
        return node, f"{self.archive_name} {dotted}"


# ---------------------------------------------------------------------------
# toc
# ---------------------------------------------------------------------------

def date_range(records: list[dict]) -> str:
    dates = sorted(d.get("date") for d in records if isinstance(d.get("date"), str))
    if not dates:
        return "без дат"
    return f"{dates[0]} … {dates[-1]}"


def cmd_toc(ctx: Ctx) -> Result:
    live, arch = ctx.live, ctx.archive
    stages = live.get("stages", [])
    stubs = [s for s in stages if is_stub(s)]
    fat = [s for s in stages if not is_stub(s)]

    lines = [
        f"{ctx.live_name} {kb(jsize(live))} · {ctx.archive_name} {kb(jsize(arch))}",
        f"Стадии: {len(stages)} (живых {len(fat)}, стубов {len(stubs)} — полный текст в архиве)",
        "",
        "| id | статус | размер | имя |",
        "|---|---|---|---|",
    ]
    rows = list(stages) if ctx.args.all else fat
    for s in rows:
        size = "архив" if is_stub(s) else kb(jsize(s))
        lines.append(
            f"| {sid(s)} | {clip(s.get('status'), 30)} | {size} | {clip(s.get('name'), 48)} |"
        )
    if stubs and not ctx.args.all:
        lines.append("")
        lines.append("стубы (текст в архиве, `stage <id>`): " + ", ".join(sid(s) for s in stubs))
    lines.append("")
    lines.append("| top-level ключ | тип | размер |")
    lines.append("|---|---|---|")
    small: list[str] = []
    for k, v in sorted(live.items(), key=lambda kv: -jsize(kv[1])):
        if jsize(v) < 512 and not ctx.args.all:
            small.append(k)
            continue
        lines.append(f"| {k} | {type(v).__name__} | {kb(jsize(v))} |")
    if small:
        lines.append("")
        lines.append("мелкие ключи (<0.5 KB): " + ", ".join(small))
    lines.append("")
    live_dec = live.get("decisions", []) or []
    arch_dec = arch.get("decisions", []) or []
    lines.append(f"decisions: живых {len(live_dec)} ({date_range(live_dec)}), "
                 f"в архиве {len(arch_dec)} ({date_range(arch_dec)})")
    legacy = arch.get("legacy_keys", {}) or {}
    subs = sum(len(v) for v in (arch.get("stage_subkeys") or {}).values())
    lines.append(f"архив: стадий {len(arch.get('stages', []))}, legacy_keys {len(legacy)}, "
                 f"подключей {subs} (`key <name>` и `stage <id> --sub <k>` достанут оттуда сами)")

    data = {
        "command": "toc",
        "files": {ctx.live_name: jsize(live), ctx.archive_name: jsize(arch)},
        # стубы отдаём без имени и размера (имя — в архиве, `stage <id>`): 45 имён
        # по 100+ кириллических символов удваивали бы вес оглавления. --all — с ними.
        "stages": [
            {"id": s.get("id"), "status": s.get("status"), "archived": True}
            if is_stub(s) and not ctx.args.all else
            {"id": s.get("id"), "name": clip(s.get("name"), 90), "status": s.get("status"),
             "size": jsize(s), "archived": bool(is_stub(s))}
            for s in stages
        ],
        "top_level_keys": {k: {"type": type(v).__name__, "size": jsize(v)}
                           for k, v in live.items()},
        "decisions": {
            "live": {"count": len(live_dec), "range": date_range(live_dec)},
            "archive": {"count": len(arch_dec), "range": date_range(arch_dec)},
        },
        "archive": {
            "stages": len(arch.get("stages", [])),
            "legacy_keys_count": len(legacy),
            # 112 имён — 4 KB; полный список только по --all, обычно хватает `search`
            "legacy_keys": sorted(legacy) if ctx.args.all else None,
            "stage_subkeys": {k: sorted(v)
                              for k, v in (arch.get("stage_subkeys") or {}).items()},
        },
    }
    return Result(data, lines, ctx.live_name, "toc")


# ---------------------------------------------------------------------------
# current
# ---------------------------------------------------------------------------

def cmd_current(ctx: Ctx) -> Result:
    live = ctx.live
    cur = live.get("current_stage")
    lines: list[str] = []
    data: dict = {"command": "current", "current_stage": cur}

    stage = None
    if cur is not None:
        stage = next((s for s in live.get("stages", []) if sid(s) == str(cur)), None)
    if stage is not None:
        lines.append(f"current_stage: {cur} — {clip(stage.get('name'), 90)}")
        lines.append(f"status: {stage.get('status')}")
        if stage.get("next"):
            lines.append(f"next: {clip(stage.get('next'), 200)}")
        data["stage"] = {"id": stage.get("id"), "name": stage.get("name"),
                         "status": stage.get("status"), "next": stage.get("next")}
        big = [f"{k} ({kb(jsize(v))})" for k, v in stage.items()
               if isinstance(v, (dict, list)) and jsize(v) >= 1024]
        if big:
            lines.append(f"крупные подключи: {', '.join(big)} — `stage {cur} --sub <k>`")
            data["stage"]["subkeys"] = big
    else:
        lines.append(f"current_stage: {cur} (стадии с таким id в живом файле нет)")

    pending: list[str] = []
    for s in live.get("stages", []):
        for k, v in s.items():
            if "pending" in k and v:
                for item in (v if isinstance(v, list) else [v]):
                    pending.append(f"стадия {sid(s)} · {k}: {clip(item, 120)}")
    if pending:
        lines.append("")
        lines.append("ожидают решения:")
        lines.extend("  - " + p for p in pending[:10])
        if len(pending) > 10:
            lines.append(f"  … ещё {len(pending) - 10}")
    data["pending"] = pending

    deferred = live.get("deferred_decisions", []) or []
    if isinstance(deferred, str):
        # ключ-указатель (дом переехал) — печатаем как есть, не разбирая строку на символы
        lines.append("")
        lines.append(f"deferred_decisions: {clip(deferred, 220)}")
        deferred = []
    if deferred:
        lines.append("")
        lines.append(f"deferred_decisions ({len(deferred)}) — целиком `key deferred_decisions`:")
        for d in deferred[:10]:
            label = d.get("topic") or d.get("question") if isinstance(d, dict) else d
            lines.append(f"  - {d.get('date', '—') if isinstance(d, dict) else '—'} "
                         f"{clip(label, 110)}")
        if len(deferred) > 10:
            lines.append(f"  … ещё {len(deferred) - 10}")
    data["deferred_decisions"] = [
        {"date": d.get("date"), "topic": d.get("topic") or d.get("question")}
        for d in deferred if isinstance(d, dict)
    ]

    lines.append("")
    lines.append("active_modules: "
                 + (", ".join(map(str, live.get("active_modules", []) or [])) or "—"))
    lines.append("excluded_modules: "
                 + (", ".join(map(str, live.get("excluded_modules", []) or [])) or "—"))
    data["active_modules"] = live.get("active_modules", [])
    data["excluded_modules"] = live.get("excluded_modules", [])

    dec = [d for d in (live.get("decisions", []) or []) if isinstance(d.get("date"), str)]
    last = sorted(dec, key=lambda d: d["date"])[-3:]
    if last:
        lines.append("")
        lines.append("последние решения:")
        for d in reversed(last):
            lines.append(f"  - {d['date']} {clip(d.get('question'), 110)}")
    data["last_decisions"] = [{"date": d.get("date"), "question": d.get("question")}
                              for d in reversed(last)]
    lines.append(f"updated: {live.get('updated')}")
    return Result(data, lines, ctx.live_name, "current")


# ---------------------------------------------------------------------------
# stage
# ---------------------------------------------------------------------------

def cmd_roadmap(ctx: Ctx) -> Result:
    """Плоская карта стадий id | имя | статус — замена §3 «Roadmap» в PROJECT-STATUS.md.

    Живые и стубы одинаково: имя стуб сохраняет, поэтому карта полная и без архива.
    """
    stages = ctx.live.get("stages", [])
    grep = (getattr(ctx.args, "grep", None) or "").lower()
    rows = [s for s in stages
            if not grep or grep in f"{sid(s)} {s.get('name','')} {s.get('status','')}".lower()]
    if not rows:
        raise QueryError(f"нет стадий под фильтр {grep!r}",
                         ["без --grep — вся карта", "`toc` — размеры и живые стадии"])
    lines = [
        f"Стадии: {len(rows)} из {len(stages)} "
        f"(живых {sum(1 for s in stages if not is_stub(s))}, стубов "
        f"{sum(1 for s in stages if is_stub(s))} — детали `stage <id>`)",
        "",
        "| id | имя | статус |",
        "|---|---|---|",
    ]
    for s in rows:
        mark = "" if is_stub(s) else " ◆"
        lines.append(f"| {sid(s)} | {clip(s.get('name'), 110)} | {clip(s.get('status'), 40)}{mark} |")
    lines.append("")
    lines.append("◆ — живая стадия (полное состояние в status.json, `stage <id>`); "
                 "остальные заархивированы.")
    data = {
        "command": "roadmap",
        "stages": [{"id": s.get("id"), "name": s.get("name"), "status": s.get("status"),
                    "archived": bool(is_stub(s))} for s in rows],
    }
    return Result(data, lines, ctx.live_name)


def cmd_stage(ctx: Ctx) -> Result:
    stage_id = ctx.args.id
    stage, source = ctx.find_stage(stage_id)
    hint = f"stages[{stage_id}]"

    if not ctx.args.sub:
        # Стадия целиком — это десятки KB. По умолчанию крупные подключи не
        # разворачиваем: строка-заглушка с размером и командой добора.
        body = stage
        folded: list[str] = []
        if not ctx.args.full:
            body = {}
            for k, v in stage.items():
                # длинные строки (заметки на 3-4 KB) сворачиваем наравне с узлами
                if isinstance(v, (dict, list, str)) and not is_pointer(v) \
                        and jsize(v) >= FOLD_BYTES:
                    body[k] = f"<{type(v).__name__}, {kb(jsize(v))}> — `stage {stage_id} --sub {k}`"
                    folded.append(k)
                else:
                    body[k] = v
        pointers = [k for k, v in stage.items() if is_pointer(v)]
        lines = [f"# стадия {stage_id} — {clip(stage.get('name'), 90)}  "
                 f"({source}, вся стадия {kb(jsize(stage))})"]
        lines.extend(render_value(body))
        if pointers:
            lines.append("")
            lines.append(f"подключи лежат в архиве и здесь не развёрнуты: {', '.join(pointers)}"
                         f" — `stage {stage_id} --sub {pointers[0]}`")
        if folded:
            lines.append("")
            lines.append(f"свёрнуто по размеру: {', '.join(folded)} — "
                         f"`stage {stage_id} --sub <k>` или `--full` целиком")
        return Result({"command": "stage", "id": stage.get("id"), "source": source,
                       "folded": folded, "stage": body}, lines, source, hint)

    wanted = [s.strip() for s in ctx.args.sub.split(",") if s.strip()]
    missing = [w for w in wanted if w not in stage]
    if missing:
        raise QueryError(
            f"в стадии {stage_id} нет подключей: {', '.join(missing)}",
            suggest(missing[0], list(stage)),
        )
    lines = [f"# стадия {stage_id} · {', '.join(wanted)}  ({source})"]
    out: dict = {}
    for w in wanted:
        value = stage[w]
        origin = source
        if is_pointer(value):
            value, origin = ctx.resolve_pointer(value)
        lines.append("")
        lines.append(f"## {w}" + (f"  ({origin})" if origin != source else ""))
        lines.extend(render_value(value))
        out[w] = value
    return Result({"command": "stage", "id": stage.get("id"), "source": source, "sub": out},
                  lines, source, f"{hint}.{wanted[0]}" if len(wanted) == 1 else hint)


# ---------------------------------------------------------------------------
# key
# ---------------------------------------------------------------------------

def cmd_key(ctx: Ctx) -> Result:
    name = ctx.args.name
    legacy = ctx.archive.get("legacy_keys", {}) or {}
    if name in ctx.live and not ctx.args.archive:
        value, source, hint = ctx.live[name], ctx.live_name, name
    elif name in legacy:
        value, source, hint = legacy[name], f"{ctx.archive_name} legacy_keys", f"legacy_keys.{name}"
    elif name in ctx.archive:
        value, source, hint = ctx.archive[name], ctx.archive_name, name
    else:
        raise QueryError(
            f"ключа {name} нет ни в живом файле, ни в legacy_keys архива",
            suggest(name, list(ctx.live) + list(legacy)),
        )
    lines = [f"# {name}  ({source}, {kb(jsize(value))})"]
    lines.extend(render_value(value))
    return Result({"command": "key", "name": name, "source": source, "value": value},
                  lines, source, hint)


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

def cmd_decisions(ctx: Ctx) -> Result:
    a = ctx.args
    pool: list[tuple[dict, str]] = [(d, "live") for d in (ctx.live.get("decisions") or [])]
    if a.archive:
        pool.extend((d, "archive") for d in (ctx.archive.get("decisions") or []))

    needle = (a.grep or "").lower()
    picked: list[tuple[dict, str]] = []
    undated = 0
    for d, src in pool:
        date = d.get("date")
        dated = isinstance(date, str) and DATE_RE.match(date)
        if (a.since or a.until) and not dated:
            undated += 1
            continue
        if a.since and date < a.since:
            continue
        if a.until and date > a.until:
            continue
        if needle and needle not in json.dumps(d, ensure_ascii=False).lower():
            continue
        picked.append((d, src))

    picked.sort(key=lambda p: (p[0].get("date") or ""))
    total = len(picked)
    if a.limit and total > a.limit:      # свежие важнее — режем с головы списка
        picked = picked[-a.limit:]
    lines = [f"решений: {total}"
             + (f", показано {len(picked)} (--limit)" if total > len(picked) else "")
             + (f" (пропущено без даты: {undated})" if undated else "")]
    if not a.full:
        lines.append("")
        lines.append("| дата | где | вопрос | выбор |")
        lines.append("|---|---|---|---|")
    for d, src in picked:
        if a.full:
            lines.append("")
            lines.append(f"## {d.get('date', '—')}  ({src})")
            lines.extend(render_value(d))
        else:
            choice = d.get("choice") or d.get("decision") or d.get("answer") or "—"
            lines.append(f"| {d.get('date', '—')} | {src} | {clip(d.get('question'), 80)} "
                         f"| {clip(choice, 60)} |")
    if picked and not a.full:
        lines.append("")
        lines.append("полный текст — `--full` (дороже), сузить — `--since/--until/--grep`")
    data = {"command": "decisions", "count": len(picked), "total": total,
            "decisions": [dict(d, _source=src) for d, src in picked]}
    return Result(data, lines, ctx.live_name, "decisions")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def walk(node: Any, prefix: str = "") -> Iterator[tuple[str, str | None, Any]]:
    """Обход дерева: (путь, имя ключа или None, значение). Элементы списков со
    своим id адресуются по id — как стадии в трекере."""
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            yield path, k, v
            yield from walk(v, path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            tag = str(item["id"]) if isinstance(item, dict) and "id" in item else str(i)
            path = f"{prefix}[{tag}]"
            yield path, None, item
            yield from walk(item, path)


def snippet(text: str, needle: str, span: int = 80) -> str:
    pos = text.lower().find(needle)
    start = max(0, pos - span)
    end = min(len(text), pos + len(needle) + span)
    frag = " ".join(text[start:end].split())
    return ("…" if start else "") + frag + ("…" if end < len(text) else "")


def cmd_search(ctx: Ctx) -> Result:
    needle = ctx.args.substr.lower()
    limit = ctx.args.limit if ctx.args.limit > 0 else 10 ** 9   # 0 — без лимита
    sources: list[tuple[dict, str]] = []
    if not ctx.args.archive_only:
        sources.append((ctx.live, "live"))
    if not ctx.args.live_only:
        sources.append((ctx.archive, "archive"))

    hits: list[tuple[str, str, str]] = []
    total = 0
    for doc, label in sources:
        for path, key, value in walk(doc, ""):
            frag = None
            # значение информативнее имени ключа — сначала оно
            if isinstance(value, str) and needle in value.lower():
                frag = snippet(value, needle)
            elif key is not None and needle in key.lower():
                frag = "[ключ] " + clip(json.dumps(value, ensure_ascii=False), 120)
            elif isinstance(value, (int, float)) and not isinstance(value, bool) \
                    and needle in str(value).lower():
                frag = str(value)
            if frag is None:
                continue
            total += 1
            if len(hits) < limit:
                hits.append((path, label, frag.replace("|", "¦")))

    if not hits:
        where = ("живом файле" if ctx.args.live_only
                 else "архиве" if ctx.args.archive_only else "обоих файлах")
        raise QueryError(f"в {where} нет совпадений с {ctx.args.substr!r}")

    lines = [f"совпадений: {total}" + (f", показано {len(hits)}" if total > len(hits) else ""),
             "", "| путь | где | сниппет |", "|---|---|---|"]
    lines.extend(f"| {p} | {label} | {clip(frag, 170)} |" for p, label, frag in hits)
    if total > len(hits):
        lines.append("")
        lines.append(f"показаны первые {limit} (--limit); узел целиком — `path <путь>`")
    data = {"command": "search", "total": total,
            "hits": [{"path": p, "source": s, "snippet": f} for p, s, f in hits]}
    return Result(data, lines, "live+archive", "search")


# ---------------------------------------------------------------------------
# path
# ---------------------------------------------------------------------------

def parse_path(expr: str) -> list[tuple[str, str]]:
    """'stages[35].w4.tickets[1]' → [('key','stages'),('item','35'),...]."""
    segments: list[tuple[str, str]] = []
    pos = 0
    for m in SEGMENT_RE.finditer(expr):
        if m.start() != pos and expr[pos:m.start()] != ".":
            raise SystemExitError(f"не разбирается выражение пути: {expr!r}")
        pos = m.end()
        if m.group(1) is not None:
            segments.append(("key", m.group(1)))
        else:
            segments.append(("item", m.group(2)))
    if not segments or pos != len(expr):
        raise SystemExitError(f"не разбирается выражение пути: {expr!r}")
    return segments


def cmd_path(ctx: Ctx) -> Result:
    root, source = ((ctx.archive, ctx.archive_name) if ctx.args.archive
                    else (ctx.live, ctx.live_name))
    node: Any = root
    walked = ""
    for kind, token in parse_path(ctx.args.expr):
        if is_pointer(node):
            node, source = ctx.resolve_pointer(node)
        if kind == "key":
            if not isinstance(node, dict) or token not in node:
                keys = [str(k) for k in node] if isinstance(node, dict) else []
                raise QueryError(f"нет ключа {token!r} по пути {walked or '<корень>'}",
                                 suggest(token, keys))
            node = node[token]
            walked = f"{walked}.{token}" if walked else token
        else:
            if not isinstance(node, list):
                raise QueryError(f"{walked or '<корень>'} — не список, "
                                 f"индекс [{token}] неприменим")
            hit = next((x for x in node
                        if isinstance(x, dict) and str(x.get("id")) == token), None)
            if hit is None:
                if not token.lstrip("-").isdigit():
                    ids = [str(x.get("id")) for x in node if isinstance(x, dict) and "id" in x]
                    raise QueryError(f"в списке {walked} нет элемента с id {token!r}",
                                     suggest(token, ids))
                idx = int(token)
                if not -len(node) <= idx < len(node):
                    ids = [str(x.get("id")) for x in node if isinstance(x, dict) and "id" in x]
                    raise QueryError(f"в списке {walked} {len(node)} элементов, элемента с id "
                                     f"{token} нет и индекс {idx} вне границ", suggest(token, ids))
                hit = node[idx]
            node = hit
            walked = f"{walked}[{token}]"
    if is_pointer(node):
        node, source = ctx.resolve_pointer(node)

    lines = [f"# {ctx.args.expr}  ({source}, {kb(jsize(node))})"]
    lines.extend(render_value(node))
    return Result({"command": "path", "expr": ctx.args.expr, "source": source, "value": node},
                  lines, source, ctx.args.expr)


# ---------------------------------------------------------------------------
# markdown: PROJECT-STATUS.md / journal.md
# ---------------------------------------------------------------------------
# Трекер и журнал — тоже дорогие файлы (68 KB и 48 KB), и читать их целиком
# субагенту так же незачем, как status.json. Разбор строгий, не эвристика:
# секции трекера — `^## <N>. <title>`, записи журнала — `^### YYYY-MM-DD — ...`
# (формат нормализован при расщеплении 2026-08-26). Строка, не подошедшая под
# шаблон, в срез не попадёт — это видно по счётчикам в `md-toc`.

MD_SECTION_RE = re.compile(r"^## (\d+)\.\s+(.+?)\s*$")
MD_SUBSECTION_RE = re.compile(r"^### +(.+?)\s*$")
JOURNAL_ENTRY_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}) — (.+?)\s*$")
ANY_DATE_HEADING_RE = re.compile(r"^(#{2,4}) .*?(\d{4}-\d{2}-\d{2})")
TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
CLOSED_RE = re.compile(r"закрыт|снят|✅|устарел", re.IGNORECASE)
MD_ARCHIVE_MIN_FILTER = "--archive требует хотя бы один фильтр: --grep / --since / --until"


def read_md(path: Path, what: str) -> list[str]:
    if not path.is_file():
        raise SystemExitError(f"{what} не найден — {path}")
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExitError(f"{what} не читается ({path}): {exc}")


@dataclass
class MdSection:
    num: str
    title: str
    start: int          # 1-based номер строки заголовка
    lines: list[str]

    @property
    def end(self) -> int:
        return self.start + len(self.lines) - 1

    @property
    def size(self) -> int:
        return len("\n".join(self.lines).encode("utf-8"))

    @property
    def subs(self) -> list[str]:
        return [m.group(1) for m in (MD_SUBSECTION_RE.match(x) for x in self.lines) if m]


def split_md_sections(lines: list[str]) -> tuple[MdSection, list[MdSection]]:
    """Шапка (всё до первой `## N.`) + пронумерованные секции."""
    starts: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        m = MD_SECTION_RE.match(line)
        if m:
            starts.append((i, m.group(1), m.group(2)))
    head_end = starts[0][0] if starts else len(lines)
    head = MdSection("0", "шапка (до первой секции)", 1, lines[:head_end])
    sections: list[MdSection] = []
    for pos, (i, num, title) in enumerate(starts):
        stop = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        sections.append(MdSection(num, title, i + 1, lines[i:stop]))
    return head, sections


def cmd_md_toc(ctx: Ctx) -> Result:
    tracker = Path(ctx.args.tracker_file)
    lines = read_md(tracker, "трекер PROJECT-STATUS.md")
    head, sections = split_md_sections(lines)
    total = len("\n".join(lines).encode("utf-8"))
    name = short_path(tracker)

    out = [f"# {name} — {kb(total)}, {len(lines)} строк, секций: {len(sections)}", ""]
    data: dict[str, Any] = {"file": name, "bytes": total, "lines": len(lines), "sections": []}
    for sec in [head] + sections:
        subs = sec.subs
        tail = f" | подзаголовки: {', '.join(clip(s, 40) for s in subs[:6])}" if subs else ""
        out.append(f"{sec.num:>2}. {sec.title} — {kb(sec.size)}, строки {sec.start}-{sec.end}{tail}")
        data["sections"].append({"num": sec.num, "title": sec.title, "bytes": sec.size,
                                 "start": sec.start, "end": sec.end, "subs": subs})

    journal = Path(ctx.args.journal_file)
    if journal.is_file():
        jlines = read_md(journal, "журнал")
        entries = [m for m in (JOURNAL_ENTRY_RE.match(x) for x in jlines) if m]
        jsz = len("\n".join(jlines).encode("utf-8"))
        dates = [m.group(1) for m in entries]
        rng = f"{dates[0]} … {dates[-1]}" if dates else "без записей"
        out += ["", f"журнал {short_path(journal)} — {kb(jsz)}, записей: {len(entries)} ({rng})"]
        data["journal"] = {"file": short_path(journal), "bytes": jsz,
                           "entries": len(entries), "range": rng}

    out += ["", "Дальше: `md-section <N>` — секция целиком, `md-journal --last 3` — свежие "
                "записи, `md-risks` — открытые риски."]
    return Result(data=data, lines=out, source=name, hint_path="")


def cmd_md_section(ctx: Ctx) -> Result:
    tracker = Path(ctx.args.tracker_file)
    lines = read_md(tracker, "трекер PROJECT-STATUS.md")
    head, sections = split_md_sections(lines)
    want = str(ctx.args.which).strip()
    name = short_path(tracker)

    pool = [head] + sections
    hit = next((s for s in pool if s.num == want), None)
    if hit is None:
        low = want.lower()
        matches = [s for s in pool if low in s.title.lower()]
        if len(matches) == 1:
            hit = matches[0]
        elif len(matches) > 1:
            raise QueryError(f"«{want}» подходит нескольким секциям",
                             [f"{s.num}. {s.title}" for s in matches])
    if hit is None:
        raise QueryError(f"секции «{want}» в {name} нет",
                         suggest(want, [f"{s.num}. {s.title}" for s in pool]))

    body = list(hit.lines)
    if getattr(ctx.args, "titles", False):
        body = [hit.lines[0]] + [x for x in hit.lines[1:] if MD_SUBSECTION_RE.match(x)]
    return Result(
        data={"file": name, "num": hit.num, "title": hit.title, "start": hit.start,
              "end": hit.end, "bytes": hit.size, "text": "\n".join(body)},
        lines=body,
        source=name,
        hint_path=f"строки {hit.start}-{hit.end}",
    )


def cmd_md_journal(ctx: Ctx) -> Result:
    args = ctx.args
    if args.archive:
        return journal_archive_index(ctx)

    path = Path(args.journal_file)
    lines = read_md(path, "журнал")
    name = short_path(path)

    starts = [(i, m.group(1), m.group(2))
              for i, m in ((i, JOURNAL_ENTRY_RE.match(x)) for i, x in enumerate(lines)) if m]
    if not starts:
        raise QueryError(f"в {name} нет записей формата `### YYYY-MM-DD — заголовок`")

    entries = []
    for pos, (i, date, title) in enumerate(starts):
        stop = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        entries.append({"date": date, "title": title, "start": i + 1, "end": stop,
                        "lines": lines[i:stop]})

    if args.since:
        entries = [e for e in entries if e["date"] >= args.since]
    if args.until:
        entries = [e for e in entries if e["date"] <= args.until]
    if args.grep:
        low = args.grep.lower()
        entries = [e for e in entries
                   if low in e["title"].lower() or low in "\n".join(e["lines"]).lower()]
    if not entries:
        raise QueryError(f"в {name} нет записей под фильтр "
                         f"(since={args.since}, until={args.until}, grep={args.grep})")

    total_found = len(entries)
    if args.last and args.last > 0:
        entries = entries[-args.last:]

    if args.titles:
        body = [f"{e['date']} — {e['title']}  [строки {e['start']}-{e['end']}]" for e in entries]
    else:
        body = []
        for e in entries:
            body += e["lines"]
    header = (f"[{name}: записей под фильтр {total_found}, показано {len(entries)}"
              f"{' (самые свежие)' if args.last else ''}]")
    payload = []
    for e in entries:
        item = {k: v for k, v in e.items() if k != "lines"}
        if not args.titles:
            item["text"] = "\n".join(e["lines"])
        payload.append(item)
    return Result(
        data={"file": name, "matched": total_found, "entries": payload},
        lines=[header, ""] + body,
        source=name,
        hint_path="",
    )


def journal_archive_index(ctx: Ctx) -> Result:
    """Архив журнала (1.9 MB) не парсим строго — форматы заголовков там разные.

    Отдаём индекс: дата + заголовок + номер строки, полный текст берётся
    точечно (диапазоном строк). Без фильтра индекс огромен, поэтому
    --grep/--since/--until обязательны хотя бы один.
    """
    args = ctx.args
    if not (args.grep or args.since or args.until):
        raise SystemExitError(f"{MD_ARCHIVE_MIN_FILTER} (архив ~2 MB, полный индекс бессмыслен)")

    # Два дома у архивного журнала: исторические записи (до 2026-09-06) уехали в
    # project-status-archive.md вместе с архивацией трекера, свежие архивации пишет
    # archive_journal.py в отдельный journal-archive.md. Индексируем оба, иначе срез
    # молча теряет половину истории.
    paths = [Path(args.md_archive_file)]
    journal_archive = REPO_ROOT / "dev" / "docs" / "journal-archive.md"
    if journal_archive.exists() and journal_archive not in paths:
        paths.append(journal_archive)

    hits = []
    names = []
    for path in paths:
        if not path.exists():
            continue
        lines = read_md(path, "архив трекера")
        name = short_path(path)
        names.append(name)
        for i, line in enumerate(lines):
            m = ANY_DATE_HEADING_RE.match(line)
            if not m:
                continue
            date = m.group(2)
            if args.since and date < args.since:
                continue
            if args.until and date > args.until:
                continue
            if args.grep and args.grep.lower() not in line.lower():
                continue
            hits.append({"date": date, "file": name, "line": i + 1, "heading": line.strip()})
    where = " + ".join(names) if names else "архив"
    if not hits:
        raise QueryError(f"в {where} нет заголовков с датой под фильтр")

    hits.sort(key=lambda h: (h["date"], h["file"], h["line"]))
    limit = args.last if args.last and args.last > 0 else 40
    shown = hits[-limit:]
    multi = len(names) > 1
    body = [
        f"{h['date']}  {(h['file'] + ' ') if multi else ''}стр.{h['line']:>6}  {clip(h['heading'], 100)}"
        for h in shown
    ]
    return Result(
        data={"files": names, "matched": len(hits), "hits": shown},
        lines=[f"[{where}: заголовков под фильтр {len(hits)}, показано {len(shown)}]",
               "", *body, "",
               "Полный текст записи — по номеру строки в указанном файле."],
        source=where,
        hint_path="",
    )


def parse_md_table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Строки markdown-таблицы → (шапка, строки). Разделитель и пустые пропускаем."""
    header: list[str] = []
    rows: list[list[str]] = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|") or TABLE_SEP_RE.match(s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not header:
            header = cells
        else:
            rows.append(cells)
    return header, rows


def cmd_md_risks(ctx: Ctx) -> Result:
    args = ctx.args
    tracker = Path(args.tracker_file)
    lines = read_md(tracker, "трекер PROJECT-STATUS.md")
    _, sections = split_md_sections(lines)
    name = short_path(tracker)

    sec = next((s for s in sections if "риск" in s.title.lower()), None)
    if sec is None:
        raise QueryError(f"секции рисков в {name} не найдено",
                         [f"{s.num}. {s.title}" for s in sections])
    _, rows = parse_md_table(sec.lines)
    if not rows:
        raise QueryError(f"в секции «{sec.title}» нет строк таблицы")

    items = []
    for cells in rows:
        status = cells[-1] if cells else ""
        items.append({"risk": cells[0] if cells else "",
                      "impact": cells[1] if len(cells) > 2 else "",
                      "mitigation": cells[2] if len(cells) > 3 else "",
                      "status": status,
                      "open": not bool(CLOSED_RE.search(status))})

    total = len(items)
    if not args.all:
        items = [it for it in items if it["open"]]
    if args.grep:
        low = args.grep.lower()
        items = [it for it in items if any(low in str(v).lower() for v in it.values())]
    if not items:
        raise QueryError(f"в «{sec.title}» нет рисков под фильтр")

    width = 200 if args.full else 110
    body = [f"# {sec.num}. {sec.title} — {len(items)} из {total} "
            f"({'все' if args.all else 'только открытые'})", ""]
    for it in items:
        mark = "открыт" if it["open"] else "закрыт"
        body.append(f"- [{mark}] {clip(it['risk'], width)}"
                    + (f" | влияние: {clip(it['impact'], 40)}" if it["impact"] else ""))
        if args.full and it["mitigation"]:
            body.append(f"    митигация: {clip(it['mitigation'], 300)}")
        if args.full:
            body.append(f"    статус: {clip(it['status'], 300)}")
    if not args.full:
        body += ["", f"Полный текст таблицы — `md-section {sec.num}`, развёрнутые "
                     f"митигации — `md-risks --full`."]
    return Result(data={"file": name, "section": sec.num, "total": total, "risks": items},
                  lines=body, source=name, hint_path=f"строки {sec.start}-{sec.end}")


# ---------------------------------------------------------------------------
# вывод и усечение
# ---------------------------------------------------------------------------

def emit(result: Result, args: argparse.Namespace) -> None:
    limit = max(1, int(args.max_kb)) * 1024
    hint = f"{result.source} {result.hint_path}".strip()

    if args.json_out:
        # компактно: --json читает машина, отступы здесь — чистый расход токенов
        text = json.dumps(result.data, ensure_ascii=False, separators=(",", ":"))
        raw = text.encode("utf-8")
        if len(raw) <= limit:
            print(text)
            return
        preview = raw[:limit].decode("utf-8", errors="ignore")
        print(json.dumps({
            "truncated": True,
            "bytes_total": len(raw),
            "bytes_shown": len(preview.encode("utf-8")),
            "source": result.source,
            "hint": hint,
            "note": f"обрезано {kb(len(raw) - limit)} из {kb(len(raw))}, полный текст: {hint}; "
                    f"запроси точечнее (--sub / path) или подними --max-kb",
            "preview": preview,
        }, ensure_ascii=False, separators=(",", ":")))
        return

    text = "\n".join(result.lines)
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        print(text)
        return
    cut = raw[:limit].decode("utf-8", errors="ignore")
    if "\n" in cut:
        cut = cut[: cut.rfind("\n")]
    shown = len(cut.encode("utf-8"))
    print(cut)
    print(f"[обрезано {kb(len(raw) - shown)} из {kb(len(raw))}, полный текст: {hint} — "
          f"запроси точечнее (--sub / path) или подними --max-kb]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

S = argparse.SUPPRESS

GLOBAL_DEFAULTS: dict[str, Any] = {
    "json_out": False,
    "md": False,
    "archive": False,
    "status_file": DEFAULT_STATUS,
    "archive_file": DEFAULT_ARCHIVE,
    "tracker_file": DEFAULT_TRACKER,
    "journal_file": DEFAULT_JOURNAL,
    "md_archive_file": DEFAULT_MD_ARCHIVE,
    "max_kb": DEFAULT_MAX_KB,
    "all": False,
}


def common_parser() -> argparse.ArgumentParser:
    """Глобальные флаги — принимаются и до, и после подкоманды.

    Все default=SUPPRESS: иначе дефолт подпарсера затирал бы значение, заданное
    перед подкомандой. Реальные дефолты проставляются в main из GLOBAL_DEFAULTS.
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--json", dest="json_out", action="store_true", default=S,
                   help="машинный вывод (валидный JSON, в т.ч. при усечении)")
    p.add_argument("--md", action="store_true", default=S,
                   help="человекочитаемый вывод (по умолчанию)")
    p.add_argument("--archive", action="store_true", default=S,
                   help="читать/искать в архиве")
    p.add_argument("--status-file", type=Path, default=S, help="путь к живому трекеру")
    p.add_argument("--archive-file", type=Path, default=S, help="путь к архиву")
    p.add_argument("--tracker-file", type=Path, default=S,
                   help="путь к dev/PROJECT-STATUS.md (для md-*)")
    p.add_argument("--journal-file", type=Path, default=S,
                   help="путь к dev/journal.md (для md-journal)")
    p.add_argument("--md-archive-file", type=Path, default=S,
                   help="путь к dev/docs/project-status-archive.md (для md-journal --archive)")
    p.add_argument("--max-kb", type=int, default=S,
                   help=f"потолок вывода в KB (по умолчанию {DEFAULT_MAX_KB}); "
                        f"при превышении вывод усекается с явной пометкой")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = common_parser()
    p = argparse.ArgumentParser(
        prog="status_query.py",
        parents=[common],
        description="Read-only срез dev/status.json и dev/status-archive.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command", metavar="<команда>")

    t = sub.add_parser("toc", parents=[common], help="оглавление трекера (дешёвый вход)")
    t.add_argument("--all", action="store_true", default=S,
                   help="показать и стадии-стубы построчно")

    rm = sub.add_parser("roadmap", parents=[common],
                        help="карта стадий id | имя | статус (замена §3 трекера)")
    rm.add_argument("--grep", metavar="SUBSTR", help="подстрока в id, имени или статусе")

    sub.add_parser("current", parents=[common],
                   help="текущая стадия, открытые пункты, модули")

    st = sub.add_parser("stage", parents=[common], help="стадия целиком или её подключи")
    st.add_argument("id", help="id стадии как в трекере: 35, 4.1, 21b")
    st.add_argument("--sub", metavar="k1,k2",
                    help="только указанные подключи; подключ-указатель на архив "
                         "разворачивается автоматически")
    st.add_argument("--full", action="store_true",
                    help=f"не сворачивать подключи крупнее {FOLD_BYTES} B (дорого)")

    k = sub.add_parser("key", parents=[common], help="top-level ключ живого файла")
    k.add_argument("name")

    d = sub.add_parser("decisions", parents=[common], help="отбор решений")
    d.add_argument("--since", metavar="YYYY-MM-DD", help="дата >= (включительно)")
    d.add_argument("--until", metavar="YYYY-MM-DD", help="дата <= (включительно)")
    d.add_argument("--grep", metavar="SUBSTR", help="подстрока в любом поле решения")
    d.add_argument("--full", action="store_true", help="полный текст, а не строка-сводка")
    d.add_argument("--limit", type=int, default=DECISIONS_LIMIT,
                   help=f"сколько решений показать, самые свежие ({DECISIONS_LIMIT}); 0 — все")

    f = sub.add_parser("search", parents=[common], help="поиск по ключам и значениям")
    f.add_argument("substr")
    f.add_argument("--limit", type=int, default=20, help="сколько совпадений показать (20)")
    f.add_argument("--live-only", action="store_true")
    f.add_argument("--archive-only", action="store_true")

    pa = sub.add_parser(
        "path", parents=[common], help="точечный доступ по выражению пути",
        description="Выражение вида stages[35].w4.tickets[1].title. В квадратных скобках для "
                    "списка словарей — ЗНАЧЕНИЕ поля id (stages[35] — стадия с id 35, а не "
                    "36-й элемент списка); если элемента с таким id нет и токен числовой, он "
                    "трактуется как индекс.")
    pa.add_argument("expr")

    sub.add_parser("md-toc", parents=[common],
                   help="оглавление dev/PROJECT-STATUS.md (дешёвый вход в markdown-трекер)")

    ms = sub.add_parser("md-section", parents=[common],
                        help="секция трекера по номеру или подстроке заголовка")
    ms.add_argument("which", metavar="N|подстрока",
                    help="номер секции (7), 0 — шапка, либо подстрока заголовка (риск)")
    ms.add_argument("--titles", action="store_true",
                    help="только заголовок секции и её подзаголовки")

    mj = sub.add_parser("md-journal", parents=[common], help="записи dev/journal.md")
    mj.add_argument("--last", type=int, default=3,
                    help="сколько последних записей показать (3); 0 — все под фильтр")
    mj.add_argument("--since", metavar="YYYY-MM-DD", help="дата >= (включительно)")
    mj.add_argument("--until", metavar="YYYY-MM-DD", help="дата <= (включительно)")
    mj.add_argument("--grep", metavar="SUBSTR", help="подстрока в заголовке или теле записи")
    mj.add_argument("--titles", action="store_true",
                    help="только даты и заголовки записей (самый дешёвый режим)")

    mr = sub.add_parser("md-risks", parents=[common], help="§8 «Риски» строками")
    mr.add_argument("--all", action="store_true", default=S,
                    help="показать и закрытые риски (по умолчанию только открытые)")
    mr.add_argument("--full", action="store_true", help="с митигациями и полным статусом")
    mr.add_argument("--grep", metavar="SUBSTR", help="подстрока в любом поле риска")
    return p


HANDLERS = {
    "toc": cmd_toc, "roadmap": cmd_roadmap, "current": cmd_current, "stage": cmd_stage, "key": cmd_key,
    "decisions": cmd_decisions, "search": cmd_search, "path": cmd_path,
    "md-toc": cmd_md_toc, "md-section": cmd_md_section, "md-journal": cmd_md_journal,
    "md-risks": cmd_md_risks,
}

MD_COMMANDS = {"md-toc", "md-section", "md-journal", "md-risks"}


def needs_archive(args: argparse.Namespace) -> bool:
    """Архив (472 KB) разбираем только там, где он реально может понадобиться."""
    if args.command in MD_COMMANDS:
        return False
    if args.command in ("toc", "stage", "key", "path"):
        return True
    if args.command == "search":
        return not getattr(args, "live_only", False)
    return bool(args.archive)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for name, default in GLOBAL_DEFAULTS.items():
        if not hasattr(args, name):
            setattr(args, name, default)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1

    try:
        for flag in ("since", "until"):
            value = getattr(args, flag, None)
            if value and not DATE_RE.match(value):
                raise SystemExitError(f"--{flag} должен быть YYYY-MM-DD, получено {value!r}")
        if getattr(args, "live_only", False) and getattr(args, "archive_only", False):
            raise SystemExitError("--live-only и --archive-only взаимоисключающие")

        md_only = args.command in MD_COMMANDS
        live = {} if md_only else load(args.status_file, "живой трекер")
        archive = load(args.archive_file, "архив") if needs_archive(args) else {}
        ctx = Ctx(live=live, archive=archive,
                  live_name=short_path(args.status_file),
                  archive_name=short_path(args.archive_file),
                  args=args)
        emit(HANDLERS[args.command](ctx), args)
        return 0
    except SystemExitError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except QueryError as exc:
        print(f"Не найдено: {exc.message}", file=sys.stderr)
        if exc.hints:
            print(f"Ближайшие варианты: {', '.join(exc.hints)}", file=sys.stderr)
        print("Оглавление — `status_query.py toc`, поиск — `status_query.py search <substr>`.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
