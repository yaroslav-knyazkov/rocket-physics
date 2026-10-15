#!/usr/bin/env python3
"""Архивация трекера dev/status.json → dev/status-archive.json.

Живой трекер разрастается (порог читаемости инструментами — ~150 KB, см.
CLAUDE.md "Порог архивации"). Раньше срез делался руками; этот скрипт
воспроизводит ту же, уже сложившуюся конвенцию:

  * закрытая стадия → полный текст в archive.stages, в живом остаётся стуб
    {"id": N, "name": ..., "status": ..., "archived": true};
  * старое решение → в archive.decisions, из живого удаляется;
  * top-level ключ завершённого направления → в archive.legacy_keys;
  * закрытая волна внутри живой стадии → в archive.stage_subkeys.<stage>.<sub>,
    в живом на её месте строка-указатель "archived → <файл> stage_subkeys.35.w1";
  * блок archive в живом файле — мета (file/generated/note/счётчики).

Безопасность по умолчанию: без --apply любой режим — dry-run (печатает, что
уедет, и дельту размера, файлы не трогает). Перед записью — бэкап обоих файлов
в dev/.status-backup/. Сначала пишется и перечитывается архив, и только если он
валиден и содержит перенесённое — усекается живой файл. Расхождение содержимого
(id уже в архиве, а в живом лежит не стуб и текст другой) — abort, без записи.
Git-команд скрипт не выполняет.

Использование:
  python .claude/scripts/archive_status.py                          # отчёт
  python .claude/scripts/archive_status.py --stages                 # dry-run
  python .claude/scripts/archive_status.py --stages --apply
  python .claude/scripts/archive_status.py --decisions --cutoff 2026-08-16 --apply
  python .claude/scripts/archive_status.py --keys k1,k2 --apply
  python .claude/scripts/archive_status.py --substages 35:w0,w1,w0_1 --apply
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Windows-консоль (cp1252/cp866) не кодирует кириллицу/юникод-стрелки напрямую —
# переключаем stdout на UTF-8 явно, иначе UnicodeEncodeError на print().
if (sys.stdout.encoding or "").lower() != "utf-8" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE = REPO_ROOT / "dev" / "status.json"
DEFAULT_ARCHIVE = REPO_ROOT / "dev" / "status-archive.json"
BACKUP_DIRNAME = ".status-backup"

STUB_KEYS = {"id", "name", "status", "archived"}
CLOSED_EXACT = {"completed"}
CLOSED_PREFIX = "done"
POINTER_PREFIX = "archived → "

# Верхнеуровневые ключи ядра трекера — не кандидаты на архивацию, показываем
# отдельно от «направленческих» ключей вида stage35_w2 / open_tails_2026-08-23.
CORE_KEYS = {
    "project", "description", "created", "updated", "platform",
    "active_modules", "excluded_modules", "complexity", "current_stage",
    "stages", "decisions", "deferred_decisions", "backlog_ideas",
    "artifacts", "archive",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# формат файла: отступ / переводы строк / финальный \n — сохраняем как в оригинале
# ---------------------------------------------------------------------------

@dataclass
class Fmt:
    indent: Any = 2          # int | str | None (None — компактный дамп)
    newline: str = "\n"
    trailing_newline: bool = False


@dataclass
class Doc:
    path: Path
    data: dict
    fmt: Fmt
    size: int                # байт на диске


def detect_format(raw: str) -> Fmt:
    newline = "\r\n" if "\r\n" in raw else "\n"
    trailing = raw.endswith("\n")
    indent: Any = None
    for line in raw.split("\n")[1:]:
        line = line.rstrip("\r")
        if not line.strip():
            continue
        stripped = line.lstrip(" \t")
        lead = line[: len(line) - len(stripped)]
        if lead:
            indent = "\t" if lead[0] == "\t" else len(lead)
        break
    return Fmt(indent=indent, newline=newline, trailing_newline=trailing)


def render(data: dict, fmt: Fmt) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=fmt.indent)
    if fmt.newline != "\n":
        text = fmt.newline.join(text.split("\n"))
    if fmt.trailing_newline:
        text += fmt.newline
    return text


def rendered_size(data: dict, fmt: Fmt) -> int:
    return len(render(data, fmt).encode("utf-8"))


def load_doc(path: Path) -> Doc:
    raw_bytes = path.read_bytes()
    raw = raw_bytes.decode("utf-8")
    return Doc(path=path, data=json.loads(raw), fmt=detect_format(raw), size=len(raw_bytes))


def write_json_file(path: Path, data: dict, fmt: Fmt) -> int:
    """Атомарная запись: во временный файл рядом, затем os.replace."""
    text = render(data, fmt)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)
    return len(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# мелкие помощники
# ---------------------------------------------------------------------------

def sid(stage: dict) -> str:
    return str(stage.get("id"))


def is_stub(stage: dict) -> bool:
    return stage.get("archived") is True and set(stage) <= STUB_KEYS


def make_stub(stage: dict) -> dict:
    return {
        "id": stage.get("id"),
        "name": stage.get("name"),
        "status": stage.get("status"),
        "archived": True,
    }


def is_closed(stage: dict) -> bool:
    status = stage.get("status")
    if not isinstance(status, str):
        return False
    return status.startswith(CLOSED_PREFIX) or status in CLOSED_EXACT


def jsize(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def decision_label(d: dict) -> Any:
    """Человекочитаемая подпись решения: старые записи используют `question`,
    новые — `topic` (формат журнала решений разъехался, см. CLAUDE.md/дата
    2026-09-23). Берём то, что есть; ничего не переименовываем и не мигрируем."""
    label = d.get("question")
    if label is not None:
        return label
    label = d.get("topic")
    if label is not None:
        return label
    return "(без подписи)"


def decision_digest(d: dict) -> str:
    """Короткий дайджест содержимого решения — сериализация с sorted keys.

    (date, label) одни не годятся в идентичность: часть решений — `topic`-
    стиля, и несколько разных решений могут делить и дату, и подпись. Дайджест
    делает две РАЗНЫЕ записи с одинаковыми (date, label) различными ключами
    (не коллизия), а одну и ту же запись, встреченную дважды (live и архив),
    сводит к одному и тому же ключу (дедуп по-прежнему работает)."""
    text = json.dumps(d, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def decision_key(d: dict) -> tuple:
    return (d.get("date"), decision_label(d), decision_digest(d))


def clip(text: Any, width: int = 52) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= width else s[: width - 1] + "…"


# ---------------------------------------------------------------------------
# план
# ---------------------------------------------------------------------------

MISSING = object()


@dataclass
class Item:
    kind: str        # stage | decision | key | subkey
    label: str
    size: int
    action: str      # archive | restub | dedup
    note: str = ""
    ref: Any = None  # ключ для сверки записанного архива (для decision — (date, label, digest))


@dataclass
class Plan:
    items: list[Item] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    new_live: dict = field(default_factory=dict)
    new_archive: dict = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(self.items)

    def count(self, kind: str) -> int:
        return sum(1 for i in self.items if i.kind == kind)


def archive_ref_path(live: dict, archive_path: Path) -> str:
    """Как архив называется в указателях/мете: берём уже записанное в мете."""
    meta = live.get("archive")
    if isinstance(meta, dict) and isinstance(meta.get("file"), str) and meta["file"]:
        return meta["file"]
    try:
        return archive_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return archive_path.name


def build_plan(live_doc: Doc, arch_doc: Doc, args: argparse.Namespace) -> Plan:
    plan = Plan(
        new_live=copy.deepcopy(live_doc.data),
        new_archive=copy.deepcopy(arch_doc.data),
    )
    live = plan.new_live
    arch = plan.new_archive
    arch.setdefault("stages", [])
    arch.setdefault("decisions", [])
    arch.setdefault("legacy_keys", {})

    if args.stages is not None:
        _plan_stages(plan, live, arch, args.stages)
    if args.decisions:
        _plan_decisions(plan, live, arch, args.cutoff)
    if args.keys:
        _plan_keys(plan, live, arch, args.keys)
    if args.substages:
        _plan_substages(plan, live, arch, args.substages,
                        archive_ref_path(live_doc.data, arch_doc.path))
    return plan


def _plan_stages(plan: Plan, live: dict, arch: dict, wanted: str) -> None:
    only = None
    if wanted != "*":
        only = {s.strip() for s in wanted.split(",") if s.strip()}
    arch_by_id = {sid(s): s for s in arch["stages"]}

    seen = set()
    stubs: list[str] = []
    for idx, stage in enumerate(live.get("stages", [])):
        key = sid(stage)
        seen.add(key)
        if only is not None and key not in only:
            continue
        if is_stub(stage):
            stubs.append(key)
            continue
        if not is_closed(stage):
            if only is not None:
                plan.skipped.append(
                    f"стадия {key}: status={stage.get('status')!r} не закрыт — skip"
                )
            continue

        old = arch_by_id.get(key)
        if old is not None:
            if old == stage:
                live["stages"][idx] = make_stub(stage)
                plan.items.append(Item("stage", key, jsize(stage), "restub",
                                       "уже в архиве, текст совпадает"))
            else:
                plan.conflicts.append(
                    f"стадия {key}: id уже есть в архиве, а в живом файле не стуб "
                    f"и текст отличается — расхождение, разобрать вручную"
                )
            continue

        body = copy.deepcopy(stage)
        arch["stages"].append(body)
        arch_by_id[key] = body
        live["stages"][idx] = make_stub(stage)
        plan.items.append(Item("stage", key, jsize(body), "archive", clip(stage.get("name"))))

    if stubs:
        plan.skipped.append(
            f"стадий уже в архиве (стубы, {len(stubs)}): {', '.join(stubs)}"
        )
    if only:
        for missing in sorted(only - seen):
            plan.skipped.append(f"стадия {missing}: нет в живом файле — skip")


def _plan_decisions(plan: Plan, live: dict, arch: dict, cutoff: str) -> None:
    arch_by_key = {decision_key(d): d for d in arch["decisions"]}
    kept: list[dict] = []
    undated = 0

    for d in live.get("decisions", []):
        raw_date = d.get("date")
        if not isinstance(raw_date, str) or not DATE_RE.match(raw_date):
            undated += 1
            kept.append(d)
            continue
        if raw_date >= cutoff:
            kept.append(d)
            continue

        key = decision_key(d)
        old = arch_by_key.get(key, MISSING)
        if old is not MISSING:
            if old == d:
                plan.items.append(Item("decision", raw_date, jsize(d), "dedup",
                                       "уже в архиве, из живого убрано", ref=key))
            else:
                plan.conflicts.append(
                    f"решение {raw_date} «{clip(decision_label(d), 40)}»: такая же дата и "
                    f"подпись (question/topic) уже в архиве, но содержимое отличается — "
                    f"разобрать вручную"
                )
                kept.append(d)
            continue

        body = copy.deepcopy(d)
        arch["decisions"].append(body)
        arch_by_key[key] = body
        plan.items.append(Item("decision", raw_date, jsize(body), "archive",
                               clip(decision_label(d), 46), ref=key))

    live["decisions"] = kept
    if undated:
        plan.skipped.append(
            f"решений без даты: {undated} — поле date отсутствует или не в формате "
            f"YYYY-MM-DD, такие записи не трогаем"
        )


def _plan_keys(plan: Plan, live: dict, arch: dict, raw_keys: str) -> None:
    names = [k.strip() for k in raw_keys.split(",") if k.strip()]
    legacy = arch["legacy_keys"]

    for name in names:
        if name in CORE_KEYS:
            plan.skipped.append(f"ключ {name}: ключ ядра трекера, архивации не подлежит — skip")
            continue
        if name not in live:
            if name in legacy:
                plan.skipped.append(f"ключ {name}: уже в архиве, в живом файле нет — skip")
            else:
                plan.skipped.append(f"ключ {name}: нет в живом файле — skip")
            continue

        value = live[name]
        old = legacy.get(name, MISSING)
        if old is not MISSING:
            if old == value:
                del live[name]
                plan.items.append(Item("key", name, jsize(value), "dedup",
                                       "уже в архиве, текст совпадает"))
            else:
                plan.conflicts.append(
                    f"ключ {name}: уже есть в legacy_keys архива, но текст в живом файле "
                    f"отличается — расхождение, разобрать вручную"
                )
            continue

        legacy[name] = copy.deepcopy(value)
        del live[name]
        plan.items.append(Item("key", name, jsize(value), "archive"))


def parse_substages(spec: str) -> tuple[dict[str, list[str]], list[str]]:
    """'35:w0,w1 36:x' → ({'35': ['w0','w1'], '36': ['x']}, ошибки)."""
    result: dict[str, list[str]] = {}
    errors: list[str] = []
    for part in spec.split():
        if ":" not in part:
            errors.append(f"--substages: ожидается формат <stage>:<k1,k2>, получено {part!r}")
            continue
        stage_id, _, subs = part.partition(":")
        stage_id = stage_id.strip()
        names = [s.strip() for s in subs.split(",") if s.strip()]
        if not stage_id or not names:
            errors.append(f"--substages: пустая стадия или список подключей в {part!r}")
            continue
        for n in names:
            if n not in result.setdefault(stage_id, []):
                result[stage_id].append(n)
    return result, errors


def _plan_substages(plan: Plan, live: dict, arch: dict, spec: str, ref: str) -> None:
    wanted, errors = parse_substages(spec)
    plan.conflicts.extend(errors)
    if errors:
        return

    stages_by_id = {sid(s): s for s in live.get("stages", [])}
    bucket = arch.get("stage_subkeys")

    for stage_id, subs in wanted.items():
        stage = stages_by_id.get(stage_id)
        if stage is None:
            plan.skipped.append(f"стадия {stage_id}: нет в живом файле — подключи пропущены")
            continue
        for sub in subs:
            pointer = f"{POINTER_PREFIX}{ref} stage_subkeys.{stage_id}.{sub}"
            if sub not in stage:
                plan.skipped.append(f"{stage_id}.{sub}: нет такого подключа в стадии — skip")
                continue
            value = stage[sub]
            if isinstance(value, str) and value.startswith(POINTER_PREFIX):
                plan.skipped.append(f"{stage_id}.{sub}: уже указатель на архив — skip")
                continue

            existing = ((arch.get("stage_subkeys") or {}).get(stage_id) or {}).get(sub, MISSING)
            if existing is not MISSING:
                if existing == value:
                    stage[sub] = pointer
                    plan.items.append(Item("subkey", f"{stage_id}.{sub}", jsize(value),
                                           "restub", "уже в архиве, текст совпадает"))
                else:
                    plan.conflicts.append(
                        f"{stage_id}.{sub}: подключ уже в архиве, но текст в живом файле "
                        f"отличается — расхождение, разобрать вручную"
                    )
                continue

            if bucket is None:
                bucket = arch.setdefault("stage_subkeys", {})
            bucket.setdefault(stage_id, {})[sub] = copy.deepcopy(value)
            stage[sub] = pointer
            plan.items.append(Item("subkey", f"{stage_id}.{sub}", jsize(value), "archive"))


# ---------------------------------------------------------------------------
# мета-блоки
# ---------------------------------------------------------------------------

def subkey_labels(arch: dict) -> list[str]:
    out = []
    for stage_id, subs in (arch.get("stage_subkeys") or {}).items():
        out.extend(f"{stage_id}.{s}" for s in subs)
    return sorted(out)


def update_meta(live: dict, arch: dict, ref: str, today: str) -> None:
    """Пересчитывает мету из архива (он источник правды) + дату живого файла."""
    live["updated"] = today

    meta = live.get("archive")
    if not isinstance(meta, dict):
        meta = {}
        live["archive"] = meta
    meta["file"] = meta.get("file") or ref
    meta["generated"] = today
    meta.setdefault(
        "note",
        "Закрытые стадии (полный текст), старые решения и ключи завершённых направлений "
        "вынесены туда. В stages здесь остались стубы с archived:true — подробности "
        "стадии искать в архиве по тому же id.",
    )
    meta["stages_archived"] = len(arch.get("stages", []))
    meta["decisions_archived"] = len(arch.get("decisions", []))
    meta["legacy_keys_archived"] = sorted(arch.get("legacy_keys", {}))
    labels = subkey_labels(arch)
    if labels or "stage_subkeys_archived" in meta:
        meta["stage_subkeys_archived"] = labels

    arch["generated"] = today
    note = arch.get("_note")
    if isinstance(note, str):
        arch["_note"] = append_archival_date(note, today)


def append_archival_date(note: str, today: str) -> str:
    """Дописывает дату прогона в перечисление «Архивации: ...» внутри _note."""
    m = re.search(r"(Архивации:\s*)([^.]*)(\.)", note)
    if not m:
        return note.rstrip() + f" Архивации: {today}."
    dates = [d.strip() for d in m.group(2).split(",") if d.strip()]
    if today in dates:
        return note
    dates.append(today)
    return note[: m.start()] + m.group(1) + ", ".join(dates) + m.group(3) + note[m.end():]


# ---------------------------------------------------------------------------
# запись
# ---------------------------------------------------------------------------

def backup(paths: list[Path], backup_dir: Path) -> list[Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for p in paths:
        if not p.is_file():  # первый прогон: архива ещё нет — бэкапить нечего
            continue
        dst = backup_dir / f"{p.name}.{stamp}"
        n = 1
        while dst.exists():  # два прогона в одну секунду не должны затирать бэкап
            dst = backup_dir / f"{p.name}.{stamp}-{n}"
            n += 1
        dst.write_bytes(p.read_bytes())
        made.append(dst)
    return made


def verify_archive(path: Path, plan: Plan) -> list[str]:
    """Перечитывает записанный архив с диска и сверяет, что перенесённое там есть."""
    problems: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"архив не перечитывается после записи: {exc}"]

    stage_ids = {sid(s) for s in data.get("stages", [])}
    dec_keys = {decision_key(d) for d in data.get("decisions", [])}
    legacy = data.get("legacy_keys", {})
    subs = {f"{st}.{s}" for st, d in (data.get("stage_subkeys") or {}).items() for s in d}

    for item in plan.items:
        if item.kind == "stage" and item.label not in stage_ids:
            problems.append(f"стадии {item.label} нет в записанном архиве")
        elif item.kind == "key" and item.label not in legacy:
            problems.append(f"ключа {item.label} нет в записанном архиве")
        elif item.kind == "subkey" and item.label not in subs:
            problems.append(f"подключа {item.label} нет в записанном архиве")
        elif item.kind == "decision" and item.ref not in dec_keys:
            problems.append(f"решения от {item.label} нет в записанном архиве")
    return problems


# ---------------------------------------------------------------------------
# вывод
# ---------------------------------------------------------------------------

def print_report(live_doc: Doc, arch_doc: Doc) -> None:
    live = live_doc.data
    lines = []
    lines.append(f"Трекер: {live_doc.path}  —  {kb(live_doc.size)}")
    lines.append(f"Архив:  {arch_doc.path}  —  {kb(arch_doc.size)}")
    lines.append("")

    lines.append("| top-level ключ | тип | размер |")
    lines.append("|---|---|---|")
    for key, value in sorted(live.items(), key=lambda kv: -jsize(kv[1])):
        mark = "" if key in CORE_KEYS else " *"
        lines.append(f"| {key}{mark} | {type(value).__name__} | {kb(jsize(value))} |")
    lines.append("")
    lines.append("`*` — не ключ ядра трекера, кандидат для `--keys`. Размер здесь — "
                 "компактный JSON-дамп ключа в байтах (на диске файл с отступами, "
                 "поэтому сумма больше размера ключей).")
    lines.append("")

    stages = live.get("stages", [])
    stubs = [s for s in stages if is_stub(s)]
    fat = [s for s in stages if not is_stub(s)]
    lines.append(f"Стадии: всего {len(stages)}, из них стубов (уже в архиве) — {len(stubs)}.")
    lines.append("")
    lines.append("| id | статус | размер | кандидат |")
    lines.append("|---|---|---|---|")
    for s in sorted(fat, key=lambda x: -jsize(x)):
        cand = "да (--stages)" if is_closed(s) else "нет — не закрыта"
        lines.append(f"| {sid(s)} | {clip(s.get('status'), 38)} | {kb(jsize(s))} | {cand} |")
    lines.append("")

    subrows = []
    for s in fat:
        for k, v in s.items():
            if isinstance(v, (dict, list)) and jsize(v) >= 2048:
                subrows.append((sid(s), k, jsize(v)))
    if subrows:
        lines.append("Крупные подключи внутри живых стадий (кандидаты для `--substages`):")
        lines.append("")
        lines.append("| стадия | подключ | размер |")
        lines.append("|---|---|---|")
        for stage_id, k, size in sorted(subrows, key=lambda r: -r[2]):
            lines.append(f"| {stage_id} | {k} | {kb(size)} |")
        lines.append("")

    decisions = live.get("decisions", [])
    dated = [d.get("date") for d in decisions if isinstance(d.get("date"), str)]
    undated = len(decisions) - len(dated)
    if dated:
        lines.append(
            f"Решения: {len(decisions)} шт., даты {min(dated)} … {max(dated)}"
            + (f", без даты — {undated} (не архивируются)" if undated else "")
            + f". Общий вес {kb(jsize(decisions))}."
        )
        buckets: dict[str, int] = {}
        for d in dated:
            buckets[d[:7]] = buckets.get(d[:7], 0) + 1
        lines.append("Помесячно: " + ", ".join(f"{m}: {n}" for m, n in sorted(buckets.items())))
        lines.append("Отбор — `--decisions --cutoff YYYY-MM-DD` (строго раньше даты).")
    else:
        lines.append("Решений с датой в живом файле нет.")
    lines.append("")
    lines.append("Ничего не изменено — это отчёт. Действия: --stages / --decisions --cutoff / "
                 "--keys / --substages, запись — только с --apply.")
    print("\n".join(lines))


def print_plan(plan: Plan, live_doc: Doc, arch_doc: Doc, applied: bool,
               new_sizes: tuple[int, int]) -> None:
    lines = []
    if plan.items:
        lines.append("| что | объект | размер | действие |")
        lines.append("|---|---|---|---|")
        titles = {"stage": "стадия", "decision": "решение", "key": "ключ", "subkey": "подключ"}
        for item in plan.items:
            note = f" — {item.note}" if item.note else ""
            lines.append(
                f"| {titles[item.kind]} | {item.label}{note} | {kb(item.size)} | {item.action} |"
            )
        lines.append("")
    for s in plan.skipped:
        lines.append(f"  skip: {s}")
    if plan.skipped:
        lines.append("")

    live_new, arch_new = new_sizes
    lines.append("| файл | было | стало | дельта |")
    lines.append("|---|---|---|---|")
    for label, old, new in (("status.json", live_doc.size, live_new),
                            ("status-archive.json", arch_doc.size, arch_new)):
        sign = "+" if new >= old else "−"
        lines.append(f"| {label} | {kb(old)} | {kb(new)} | {sign}{kb(abs(new - old))} |")
    lines.append("")
    lines.append(
        f"Перенесено: стадий {plan.count('stage')}, решений {plan.count('decision')}, "
        f"ключей {plan.count('key')}, подключей {plan.count('subkey')}."
    )
    if not applied:
        lines.append("")
        lines.append("DRY-RUN — файлы не изменены. Повтори с `--apply`, чтобы записать.")
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Архивация dev/status.json → dev/status-archive.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--live", type=Path, default=DEFAULT_LIVE, help="живой трекер")
    p.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE, help="файл архива")
    p.add_argument("--stages", nargs="?", const="*", default=None, metavar="IDS",
                   help="архивировать закрытые стадии (status done*/completed); "
                        "можно сузить списком id: --stages 31,32")
    p.add_argument("--decisions", action="store_true",
                   help="архивировать решения старше --cutoff")
    p.add_argument("--cutoff", metavar="YYYY-MM-DD",
                   help="граница для --decisions (строго раньше этой даты)")
    p.add_argument("--keys", metavar="k1,k2",
                   help="явный список top-level ключей → legacy_keys")
    p.add_argument("--substages", metavar="35:w0,w1",
                   help="подключи конкретной стадии → stage_subkeys (автодетекта нет)")
    p.add_argument("--apply", action="store_true",
                   help="фактическая запись (без флага — dry-run)")
    p.add_argument("--today", metavar="YYYY-MM-DD", default=date.today().isoformat(),
                   help="дата для updated/generated (по умолчанию сегодня)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.decisions and not args.cutoff:
        print("Ошибка: --decisions требует --cutoff YYYY-MM-DD.", file=sys.stderr)
        return 1
    if args.cutoff and not DATE_RE.match(args.cutoff):
        print(f"Ошибка: --cutoff должен быть YYYY-MM-DD, получено {args.cutoff!r}.", file=sys.stderr)
        return 1
    if not DATE_RE.match(args.today):
        print(f"Ошибка: --today должен быть YYYY-MM-DD, получено {args.today!r}.", file=sys.stderr)
        return 1

    if not args.live.is_file():
        print(f"Ошибка: файл не найден — {args.live}", file=sys.stderr)
        return 1

    live_doc = load_doc(args.live)
    if args.archive.is_file():
        arch_doc = load_doc(args.archive)
    else:
        # Новый проект: архива ещё нет, первая --apply создаст его в формате живого файла.
        arch_doc = Doc(path=args.archive, data={}, fmt=live_doc.fmt, size=0)

    if args.stages is None and not args.decisions and not args.keys and not args.substages:
        print_report(live_doc, arch_doc)
        return 0

    plan = build_plan(live_doc, arch_doc, args)

    if plan.conflicts:
        print("Конфликт — ничего не записано:", file=sys.stderr)
        for c in plan.conflicts:
            print(f"  • {c}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Разберись с расхождением руками (архив — источник правды по перенесённому), "
              "затем запусти снова.", file=sys.stderr)
        return 2

    if not plan.has_changes:
        for s in plan.skipped:
            print(f"  skip: {s}")
        print("Нечего архивировать — по заданным флагам всё уже в архиве. Файлы не тронуты.")
        return 0

    ref = archive_ref_path(live_doc.data, arch_doc.path)
    update_meta(plan.new_live, plan.new_archive, ref, args.today)

    new_live_size = rendered_size(plan.new_live, live_doc.fmt)
    new_arch_size = rendered_size(plan.new_archive, arch_doc.fmt)

    if not args.apply:
        print_plan(plan, live_doc, arch_doc, applied=False,
                   new_sizes=(new_live_size, new_arch_size))
        return 0

    backup_dir = args.live.parent / BACKUP_DIRNAME
    made = backup([args.live, args.archive], backup_dir)

    # Порядок принципиален: сначала архив, потом проверка, и только потом
    # усечение живого файла. Обратный порядок = окно, в котором данные нигде.
    arch_written = write_json_file(args.archive, plan.new_archive, arch_doc.fmt)
    problems = verify_archive(args.archive, plan)
    if problems:
        print("Архив записан, но проверка не прошла — живой файл НЕ тронут:", file=sys.stderr)
        for p in problems:
            print(f"  • {p}", file=sys.stderr)
        print(f"Бэкапы: {', '.join(str(m) for m in made)}", file=sys.stderr)
        return 3

    live_written = write_json_file(args.live, plan.new_live, live_doc.fmt)

    print_plan(plan, live_doc, arch_doc, applied=True,
               new_sizes=(live_written, arch_written))
    print("")
    print(f"Бэкапы: {backup_dir}")
    for m in made:
        print(f"  {m.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
