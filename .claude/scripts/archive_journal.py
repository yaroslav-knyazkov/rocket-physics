#!/usr/bin/env python
"""Архивация dev/journal.md — дословный перенос старых записей в dev/docs/journal-archive.md.

Журнал append-only и растёт быстрее всех трекеров. За порогом ~150 KB он перестаёт
читаться инструментом целиком, а срез `status_query.py md-journal` этого не лечит:
файл всё равно приходится держать целиком, когда правится структура.

Аналог archive_status.py, но для markdown: то же поведение по умолчанию (dry-run),
тот же принцип «архив — источник правды по перенесённому», тот же бэкап перед записью.

    python .claude/scripts/archive_journal.py                      # отчёт: сколько записей, вес, где порог
    python .claude/scripts/archive_journal.py --cutoff 2026-09-01  # dry-run переноса
    python .claude/scripts/archive_journal.py --cutoff 2026-09-01 --apply

Записи опознаются строго: `^### YYYY-MM-DD — <заголовок>` (тот же формат, что разбирает
status_query.py md-journal). Всё до первой такой строки — преамбула, она остаётся в живом
файле. В архив уходят записи строго РАНЬШЕ --cutoff.

Гарантии:
  * перенос дословный — ни одна строка не переписывается, только перекладывается;
  * сумма строк живого и архива после переноса равна сумме до (проверяется, иначе abort);
  * повторный прогон идемпотентен — уже перенесённые записи опознаются по (дата, заголовок)
    и не дублируются; расхождение текста уже перенесённой записи — abort без записи;
  * перед записью обоих файлов делается бэкап в dev/.docs-backup/.
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ENTRY_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}) — (.+?)\s*$")

REPO = Path(__file__).resolve().parents[2]
JOURNAL = REPO / "dev" / "journal.md"
ARCHIVE = REPO / "dev" / "docs" / "journal-archive.md"
BACKUP_DIR = REPO / "dev" / ".docs-backup"
THRESHOLD_KB = 150

ARCHIVE_HEADER = """# Архив журнала проекта

> **Что это.** Дословный перенос старых записей из `dev/journal.md`, слово в слово, без правок.
> Живой журнал перешагнул порог ~150 KB, после чего перестал читаться инструментом целиком.
>
> **Как читать.** Индекс без тел записей — `python .claude/scripts/status_query.py md-journal --archive`:
> дата, заголовок и номер строки. Тело добирается точечным `Read` с `offset`/`limit`.
> Целиком этот файл не читать — он для того и заведён, чтобы этого не делать.
>
> Пополняется скриптом `.claude/scripts/archive_journal.py`. Руками сюда не дописывать.

---

"""


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    with io.open(path, encoding="utf-8", newline="") as f:
        return f.readlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)


def split_entries(lines: list[str]) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    """-> (преамбула, [(дата, заголовок, строки записи)])."""
    starts = [i for i, ln in enumerate(lines) if ENTRY_RE.match(ln)]
    if not starts:
        return lines, []
    preamble = lines[: starts[0]]
    entries = []
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        m = ENTRY_RE.match(lines[i])
        entries.append((m.group(1), m.group(2), lines[i:end]))
    return preamble, entries


def kb(path: Path) -> float:
    return path.stat().st_size / 1024 if path.exists() else 0.0


def report(journal_entries, archive_entries) -> None:
    print(f"Журнал: {JOURNAL}  —  {kb(JOURNAL):.1f} KB"
          f"{'  ⚠ ЗА ПОРОГОМ ~%d KB' % THRESHOLD_KB if kb(JOURNAL) > THRESHOLD_KB else ''}")
    print(f"Архив:  {ARCHIVE}  —  {kb(ARCHIVE):.1f} KB"
          f"{'  (пока не заведён)' if not ARCHIVE.exists() else ''}")
    print()
    if not journal_entries:
        print("Записей в живом журнале не найдено — проверь формат заголовков `### YYYY-MM-DD — ...`.")
        return
    by_date: dict[str, int] = {}
    for date, _, _ in journal_entries:
        by_date[date] = by_date.get(date, 0) + 1
    print(f"Записей в живом журнале: {len(journal_entries)} "
          f"({journal_entries[0][0]} — {journal_entries[-1][0]})")
    print(f"Записей в архиве: {len(archive_entries)}")
    print()
    print("| дата | записей | вес записей этой даты |")
    print("|---|---:|---:|")
    for date in sorted(by_date):
        w = sum(len("".join(e[2]).encode("utf-8")) for e in journal_entries if e[0] == date)
        print(f"| {date} | {by_date[date]} | {w / 1024:.1f} KB |")
    print()
    print("Перенос: `--cutoff YYYY-MM-DD` (уходят записи строго РАНЬШЕ даты), затем `--apply`.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Архивация dev/journal.md (dry-run по умолчанию).")
    ap.add_argument("--cutoff", help="дата YYYY-MM-DD: записи строго раньше неё уходят в архив")
    ap.add_argument("--apply", action="store_true", help="записать (иначе только показать)")
    args = ap.parse_args()

    if not JOURNAL.exists():
        print(f"Нет файла {JOURNAL}", file=sys.stderr)
        return 1

    j_lines = read_lines(JOURNAL)
    j_pre, j_entries = split_entries(j_lines)
    a_lines = read_lines(ARCHIVE)
    a_pre, a_entries = split_entries(a_lines)

    if not args.cutoff:
        report(j_entries, a_entries)
        return 0

    try:
        datetime.strptime(args.cutoff, "%Y-%m-%d")
    except ValueError:
        print(f"--cutoff должен быть YYYY-MM-DD, получено: {args.cutoff}", file=sys.stderr)
        return 1

    move = [e for e in j_entries if e[0] < args.cutoff]
    keep = [e for e in j_entries if e[0] >= args.cutoff]
    if not move:
        print(f"Раньше {args.cutoff} записей нет — переносить нечего.")
        return 0

    # Идемпотентность: уже перенесённое не дублируем, расхождение — abort.
    known = {(d, t): "".join(body) for d, t, body in a_entries}
    conflicts, fresh = [], []
    for date, title, body in move:
        prev = known.get((date, title))
        if prev is None:
            fresh.append((date, title, body))
        elif prev != "".join(body):
            conflicts.append(f"{date} — {title}")
    if conflicts:
        print("Конфликт — ничего не записано:", file=sys.stderr)
        for c in conflicts:
            print(f"  • запись «{c}» уже в архиве, но её текст в живом файле отличается — "
                  f"разобрать вручную (архив — источник правды по перенесённому)", file=sys.stderr)
        return 2

    pointer = (
        f"> **Архивация {datetime.now():%Y-%m-%d}.** Записи за "
        f"{move[0][0]} — {move[-1][0]} ({len(move)} шт.) перенесены дословно в "
        f"[`docs/journal-archive.md`](docs/journal-archive.md). "
        f"Индекс архива: `python .claude/scripts/status_query.py md-journal --archive`.\n\n"
    )

    new_archive = (a_lines if a_lines else list(io.StringIO(ARCHIVE_HEADER))) + \
                  [ln for _, _, body in fresh for ln in body]
    new_journal = j_pre + list(io.StringIO(pointer)) + [ln for _, _, body in keep for ln in body]

    moved_lines = sum(len(b) for _, _, b in move)
    kept_lines = sum(len(b) for _, _, b in keep)
    if moved_lines + kept_lines != sum(len(b) for _, _, b in j_entries):
        print("Внутренняя ошибка: строки не сходятся, ничего не записано.", file=sys.stderr)
        return 2

    j_new_kb = len("".join(new_journal).encode("utf-8")) / 1024
    a_new_kb = len("".join(new_archive).encode("utf-8")) / 1024
    print(f"Переносится записей: {len(move)} (новых для архива: {len(fresh)}), строк: {moved_lines}")
    print(f"Остаётся в живом: {len(keep)} записей, строк: {kept_lines}")
    print()
    print("| файл | было | стало | дельта |")
    print("|---|---|---|---|")
    print(f"| journal.md | {kb(JOURNAL):.1f} KB | {j_new_kb:.1f} KB | {j_new_kb - kb(JOURNAL):+.1f} KB |")
    print(f"| journal-archive.md | {kb(ARCHIVE):.1f} KB | {a_new_kb:.1f} KB | {a_new_kb - kb(ARCHIVE):+.1f} KB |")

    if not args.apply:
        print("\nDRY-RUN — файлы не изменены. Повтори с `--apply`, чтобы записать.")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(JOURNAL, BACKUP_DIR / f"journal.md.{stamp}")
    if ARCHIVE.exists():
        shutil.copy2(ARCHIVE, BACKUP_DIR / f"journal-archive.md.{stamp}")

    write_lines(ARCHIVE, new_archive)
    write_lines(JOURNAL, new_journal)
    print(f"\nЗаписано. Бэкапы: {BACKUP_DIR} (journal.md.{stamp})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
