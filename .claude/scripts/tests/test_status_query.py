# -*- coding: utf-8 -*-
"""Тесты для .claude/scripts/status_query.py.

Запуск из корня репозитория:
    PYTHONUTF8=1 python -m pytest .claude/scripts/tests -v

Всё на синтетических фикстурах в tmp_path: боевые dev/status.json и
dev/status-archive.json тесты не открывают (и вообще ничего не пишут —
скрипт read-only, это отдельно проверяется).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import status_query  # noqa: E402


# --------------------------------------------------------------------------
# фикстуры
# --------------------------------------------------------------------------

POINTER = "archived → dev/status-archive.json stage_subkeys.35.w1"


def make_live() -> dict:
    return {
        "project": "Parlai",
        "updated": "2026-08-26",
        "active_modules": ["backend", "frontend"],
        "excluded_modules": ["security"],
        "current_stage": 35,
        "stages": [
            {"id": 1, "name": "Первая", "status": "done", "archived": True},
            {"id": "4.1", "name": "Дробная", "status": "done", "archived": True},
            {
                "id": 35,
                "name": "Диалоговый движок v2",
                "status": "w0_approved_in_progress",
                "next": "Architect пишет ТЗ",
                "decisions_pending": ["контракт <word>"],
                "w1": POINTER,
                "w4": {
                    "tickets": [
                        {"id": "T1", "title": "Селектор темы", "status": "done"},
                        {"id": "T2", "title": "Память профиля", "status": "todo"},
                    ],
                    "note": "волна в работе",
                },
                "log": [f"строка журнала {i}: длинная запись про ход волны и её приёмку"
                        for i in range(40)],
            },
        ],
        "decisions": [
            {"date": "2026-08-20", "question": "Free Talk scope", "choice": "только пикер"},
            {"date": "2026-08-25", "question": "Роль методолога", "choice": "не вводим сейчас"},
            {"question": "без даты", "choice": "висит"},
        ],
        "deferred_decisions": [
            {"date": "2026-07-30", "topic": "DROP archived_stage10_gate_status",
             "why_not_now": "подстраховка"},
        ],
        "lesson_content_rules": {"rule": "не писать от первого лица"},
    }


def make_archive() -> dict:
    return {
        "_note": "архив",
        "generated": "2026-08-26",
        "stages": [
            {"id": 1, "name": "Первая", "status": "done",
             "summary": "полный текст первой стадии", "artifacts": ["a.md"]},
            {"id": "4.1", "name": "Дробная", "status": "done", "summary": "текст 4.1"},
        ],
        "decisions": [
            {"date": "2026-07-01", "question": "Стек бэкенда", "choice": "FastAPI"},
            {"date": "2026-08-01", "question": "Модель LLM", "choice": "DeepSeek"},
        ],
        "legacy_keys": {
            "pre_a1_track": {"status": "закрыто", "note": "Pre-A1 сдан"},
        },
        "stage_subkeys": {
            "35": {"w1": {"status": "closed", "tickets": ["w1-1", "w1-2"]}},
        },
    }


@pytest.fixture()
def files(tmp_path: Path):
    live = tmp_path / "status.json"
    arch = tmp_path / "status-archive.json"
    live.write_text(json.dumps(make_live(), ensure_ascii=False, indent=2), encoding="utf-8")
    arch.write_text(json.dumps(make_archive(), ensure_ascii=False, indent=1), encoding="utf-8")
    return live, arch


def run(files, *args, expect=0):
    live, arch = files
    argv = ["--status-file", str(live), "--archive-file", str(arch), *args]
    code = status_query.main(argv)
    assert code == expect, f"exit {code} != {expect} для {argv}"
    return code


def out(capsys):
    captured = capsys.readouterr()
    return captured.out + captured.err


# --------------------------------------------------------------------------
# toc
# --------------------------------------------------------------------------

def test_toc_lists_stages_keys_and_decisions(files, capsys):
    run(files, "toc")
    text = out(capsys)
    assert "35" in text
    assert "Диалоговый движок v2" in text
    assert "lesson_content_rules" in text
    assert "2026-08-20" in text and "2026-08-25" in text


def test_toc_marks_archived_stubs(files, capsys):
    run(files, "toc", "--all")
    text = out(capsys)
    line = [l for l in text.split("\n") if l.startswith("| 1 ")][0]
    assert "архив" in line or "стуб" in line


def test_toc_is_compact(files, capsys):
    run(files, "toc")
    assert len(out(capsys).encode("utf-8")) < 2500


def test_toc_json_is_valid(files, capsys):
    run(files, "toc", "--json")
    data = json.loads(out(capsys))
    assert data["command"] == "toc"
    assert any(str(s["id"]) == "35" for s in data["stages"])


def test_current_handles_pointer_string_in_deferred(tmp_path, capsys):
    """Ключ-указатель (дом переехал в md) не должен разбираться на символы."""
    live = make_live()
    live["deferred_decisions"] = "→ dev/PROJECT-STATUS.md §10 (дом с 2026-08-29)"
    lp = tmp_path / "s.json"
    ap = tmp_path / "a.json"
    lp.write_text(json.dumps(live, ensure_ascii=False), encoding="utf-8")
    ap.write_text(json.dumps(make_archive(), ensure_ascii=False), encoding="utf-8")
    run((lp, ap), "current")
    text = out(capsys)
    assert "deferred_decisions: → dev/PROJECT-STATUS.md §10" in text
    assert "  - — →" not in text


# --------------------------------------------------------------------------
# stage
# --------------------------------------------------------------------------

def test_stage_from_live(files, capsys):
    run(files, "stage", "35")
    text = out(capsys)
    assert "Селектор темы" in text
    assert "status.json" in text


def test_stage_falls_back_to_archive_and_marks_source(files, capsys):
    run(files, "stage", "1")
    text = out(capsys)
    assert "полный текст первой стадии" in text
    assert "status-archive.json" in text


def test_stage_id_may_be_string(files, capsys):
    run(files, "stage", "4.1")
    assert "текст 4.1" in out(capsys)


def test_stage_sub_selects_only_requested_keys(files, capsys):
    run(files, "stage", "35", "--sub", "next,decisions_pending")
    text = out(capsys)
    assert "Architect пишет ТЗ" in text
    assert "Селектор темы" not in text


def test_stage_sub_resolves_archive_pointer(files, capsys):
    run(files, "stage", "35", "--sub", "w1")
    text = out(capsys)
    assert "w1-1" in text
    assert "stage_subkeys" in text or "status-archive.json" in text


def test_stage_unknown_id_errors_with_hint(files, capsys):
    run(files, "stage", "36", expect=2)
    text = out(capsys)
    assert "36" in text
    assert "35" in text  # подсказка
    assert "Traceback" not in text


def test_stage_unknown_sub_errors_with_hint(files, capsys):
    run(files, "stage", "35", "--sub", "w44", expect=2)
    text = out(capsys)
    assert "w4" in text
    assert "Traceback" not in text


# --------------------------------------------------------------------------
# key
# --------------------------------------------------------------------------

def test_key_from_live(files, capsys):
    run(files, "key", "lesson_content_rules")
    assert "не писать от первого лица" in out(capsys)


def test_key_from_legacy_keys_marks_source(files, capsys):
    run(files, "key", "pre_a1_track")
    text = out(capsys)
    assert "Pre-A1 сдан" in text
    assert "legacy_keys" in text or "status-archive.json" in text


def test_key_unknown_errors_with_hint_no_traceback(files, capsys):
    run(files, "key", "lesson_content_rule", expect=2)
    text = out(capsys)
    assert "lesson_content_rules" in text
    assert "Traceback" not in text


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------

def test_decisions_date_range(files, capsys):
    run(files, "decisions", "--since", "2026-08-21")
    text = out(capsys)
    assert "Роль методолога" in text
    assert "Free Talk scope" not in text


def test_decisions_until(files, capsys):
    run(files, "decisions", "--until", "2026-08-20")
    text = out(capsys)
    assert "Free Talk scope" in text
    assert "Роль методолога" not in text


def test_decisions_grep(files, capsys):
    run(files, "decisions", "--grep", "методолог")
    text = out(capsys)
    assert "Роль методолога" in text
    assert "Free Talk scope" not in text


def test_decisions_archive_included_and_marked(files, capsys):
    run(files, "decisions", "--archive", "--grep", "FastAPI")
    text = out(capsys)
    assert "Стек бэкенда" in text
    assert "archive" in text


def test_decisions_json(files, capsys):
    run(files, "decisions", "--json")
    data = json.loads(out(capsys))
    assert data["count"] == len(data["decisions"])


# --------------------------------------------------------------------------
# roadmap
# --------------------------------------------------------------------------

def test_roadmap_lists_every_stage_with_name(files, capsys):
    run(files, "roadmap")
    text = out(capsys)
    # стубы тоже с именами — иначе карта id→имя пропала бы из живого файла
    assert "Первая" in text and "Дробная" in text and "Диалоговый движок v2" in text
    assert "Стадии: 3 из 3" in text


def test_roadmap_marks_live_stages(files, capsys):
    run(files, "roadmap")
    text = out(capsys)
    live_row = [l for l in text.splitlines() if "Диалоговый движок" in l][0]
    stub_row = [l for l in text.splitlines() if "Первая" in l][0]
    assert live_row.rstrip().endswith("◆ |")
    assert not stub_row.rstrip().endswith("◆ |")


def test_roadmap_grep_filters(files, capsys):
    run(files, "roadmap", "--grep", "дроб")
    text = out(capsys)
    assert "Дробная" in text and "Первая" not in text
    assert "Стадии: 1 из 3" in text


def test_roadmap_grep_no_match_is_query_error(files, capsys):
    run(files, "roadmap", "--grep", "нетакой", expect=2)
    assert "нет стадий" in out(capsys)


def test_roadmap_json_has_archived_flag(files, capsys):
    run(files, "roadmap", "--json")
    data = json.loads(out(capsys))
    assert data["command"] == "roadmap"
    assert [s["archived"] for s in data["stages"]] == [True, True, False]
    assert data["stages"][0]["name"] == "Первая"


def test_roadmap_is_cheaper_than_toc_all(files, capsys):
    run(files, "roadmap")
    roadmap_len = len(out(capsys))
    run(files, "toc", "--all")
    assert roadmap_len < len(out(capsys))


# --------------------------------------------------------------------------
# current
# --------------------------------------------------------------------------

def test_current_summary(files, capsys):
    run(files, "current")
    text = out(capsys)
    assert "35" in text
    assert "Architect пишет ТЗ" in text
    assert "контракт <word>" in text
    assert "security" in text  # excluded_modules
    assert "DROP archived_stage10_gate_status" in text


def test_current_is_compact(files, capsys):
    run(files, "current")
    assert len(out(capsys).encode("utf-8")) < 2500


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

def test_search_matches_values_in_both_files_with_snippets(files, capsys):
    run(files, "search", "селектор")
    text = out(capsys)
    assert "stages[35]" in text
    assert "Селектор темы" in text


def test_search_matches_keys(files, capsys):
    run(files, "search", "legacy")
    text = out(capsys)
    assert "legacy_keys" in text


def test_search_limit(files, capsys):
    run(files, "search", "е", "--limit", "3")
    rows = [l for l in out(capsys).split("\n") if l.startswith("| ")]
    assert len(rows) <= 3 + 2  # заголовок таблицы + разделитель


def test_search_live_only(files, capsys):
    run(files, "search", "FastAPI", "--live-only", expect=2)
    assert "Traceback" not in out(capsys)


def test_search_archive_only(files, capsys):
    run(files, "search", "FastAPI", "--archive-only")
    text = out(capsys)
    assert "FastAPI" in text
    assert "archive" in text


def test_search_snippet_does_not_dump_whole_node(files, capsys):
    run(files, "search", "Диалоговый")
    text = out(capsys)
    assert "Селектор темы" not in text


# --------------------------------------------------------------------------
# path
# --------------------------------------------------------------------------

def test_path_stage_id_in_brackets(files, capsys):
    run(files, "path", "stages[35].w4.tickets")
    text = out(capsys)
    assert "Селектор темы" in text
    assert "Память профиля" in text


def test_path_list_index(files, capsys):
    run(files, "path", "stages[35].w4.tickets[1].title")
    text = out(capsys)
    assert "Память профиля" in text
    assert "Селектор темы" not in text


def test_path_toplevel_key(files, capsys):
    run(files, "path", "current_stage")
    assert "35" in out(capsys)


def test_path_resolves_pointer(files, capsys):
    run(files, "path", "stages[35].w1")
    assert "w1-1" in out(capsys)


def test_path_bad_segment_errors_with_hint(files, capsys):
    run(files, "path", "stages[35].w9", expect=2)
    text = out(capsys)
    assert "w9" in text
    assert "w4" in text
    assert "Traceback" not in text


def test_path_json(files, capsys):
    run(files, "path", "stages[35].w4.note", "--json")
    data = json.loads(out(capsys))
    assert data["value"] == "волна в работе"


# --------------------------------------------------------------------------
# усечение
# --------------------------------------------------------------------------

def test_max_kb_truncates_with_note(files, capsys):
    run(files, "stage", "35", "--full", "--max-kb", "1")
    text = out(capsys)
    assert len(text.encode("utf-8")) < 3000
    assert "обрезано" in text
    assert "status.json" in text
    assert "stages[35]" in text


def test_max_kb_json_stays_valid(files, capsys):
    run(files, "stage", "35", "--full", "--max-kb", "1", "--json")
    data = json.loads(out(capsys))
    assert data["truncated"] is True
    assert "stages[35]" in data["hint"]


def test_no_truncation_note_when_fits(files, capsys):
    run(files, "path", "current_stage")
    assert "обрезано" not in out(capsys)


# --------------------------------------------------------------------------
# read-only
# --------------------------------------------------------------------------

def test_nothing_is_written(files, tmp_path, capsys):
    live, arch = files
    before = {p: p.read_bytes() for p in (live, arch)}
    listing_before = sorted(p.name for p in tmp_path.iterdir())
    for args in (["toc"], ["current"], ["stage", "35"], ["key", "pre_a1_track"],
                 ["decisions", "--archive"], ["search", "Селектор"], ["path", "stages[35].w4"]):
        run(files, *args)
    capsys.readouterr()
    assert {p: p.read_bytes() for p in (live, arch)} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == listing_before


def test_source_has_no_write_calls():
    src = Path(status_query.__file__).read_text(encoding="utf-8")
    for forbidden in ("write_text", "write_bytes", "os.replace", "mkdir", "subprocess", "shutil"):
        assert forbidden not in src, f"read-only скрипт не должен содержать {forbidden}"


def test_missing_file_errors_cleanly(tmp_path, capsys):
    code = status_query.main(["--status-file", str(tmp_path / "nope.json"), "toc"])
    assert code == 1
    text = out(capsys)
    assert "nope.json" in text
    assert "Traceback" not in text


# --------------------------------------------------------------------------
# markdown: фикстуры
# --------------------------------------------------------------------------

TRACKER_MD = """# PROJECT STATUS — Parlai

Строка шапки: текущая стадия 35.

## 1. Видение продукта

Учим язык разговором.

## 2. Продуктовая карта

### Пользователи и задачи

Взрослые B1.

### Фичи

MoSCoW.

## 8. Риски

| Риск | Влияние | Митигация | Статус |
|------|---------|-----------|--------|
| LLM-латентность > 3 с | высок | streaming | открыт |
| Раздутый scope Stage 1 | средн | список P0 | открыт |
| Зеркалирование grammar_lesson негейтнуто | низк | seed-фикс | **✅ закрыто T-B5 (2026-08-10)** |

> Закрытые риски архивированы 2026-08-08.

## 11. Журнал проекта

> Новые записи — в `dev/journal.md`.
"""

JOURNAL_MD = """# Журнал проекта — Parlai

Формат: `### YYYY-MM-DD — заголовок`, append-only.

### 2026-08-23 — U03 и U04 написаны

Тело первой записи про уроки.

### 2026-08-25 — Free Talk: каталог тем закрыт

Тело второй записи про каталог тем.

### 2026-08-26 — Расширение интересов

Тело третьей записи.
"""

MD_ARCHIVE = """# Архив трекера

## Архивация 2026-08-26 — §11 «Журнал проекта»

### 2026-08-16 — Track A: первые 3 урока fr

Старое тело.

### 2026-08-18 — Track A: Pre-A1 W5 закрыт

Старое тело 2.
"""


@pytest.fixture()
def md_files(tmp_path: Path):
    tracker = tmp_path / "PROJECT-STATUS.md"
    journal = tmp_path / "journal.md"
    archive = tmp_path / "project-status-archive.md"
    tracker.write_text(TRACKER_MD, encoding="utf-8")
    journal.write_text(JOURNAL_MD, encoding="utf-8")
    archive.write_text(MD_ARCHIVE, encoding="utf-8")
    return tracker, journal, archive


def run_md(md_files, *args, expect=0):
    tracker, journal, archive = md_files
    argv = ["--tracker-file", str(tracker), "--journal-file", str(journal),
            "--md-archive-file", str(archive), *args]
    code = status_query.main(argv)
    assert code == expect, f"exit {code} != {expect} для {argv}"
    return code


# --------------------------------------------------------------------------
# md-toc
# --------------------------------------------------------------------------

def test_md_toc_lists_sections_with_sizes(md_files, capsys):
    run_md(md_files, "md-toc")
    text = out(capsys)
    assert "1. Видение продукта" in text
    assert "8. Риски" in text
    assert "шапка" in text
    assert "KB" in text


def test_md_toc_shows_subsections_and_journal(md_files, capsys):
    run_md(md_files, "md-toc")
    text = out(capsys)
    assert "Пользователи и задачи" in text
    assert "записей: 3" in text
    assert "2026-08-23 … 2026-08-26" in text


def test_md_toc_is_compact(md_files, capsys):
    run_md(md_files, "md-toc")
    text = out(capsys)
    assert "Учим язык разговором" not in text     # тел секций в оглавлении нет
    assert "streaming" not in text


def test_md_toc_json(md_files, capsys):
    run_md(md_files, "md-toc", "--json")
    payload = json.loads(out(capsys))
    assert [s["num"] for s in payload["sections"]] == ["0", "1", "2", "8", "11"]
    assert payload["journal"]["entries"] == 3


def test_md_commands_do_not_need_status_json(md_files, capsys):
    """md-* не открывают status.json — иначе субагенту пришлось бы иметь оба файла."""
    tracker, journal, archive = md_files
    code = status_query.main(["--status-file", str(tracker.parent / "no-such.json"),
                              "--tracker-file", str(tracker), "md-toc"])
    assert code == 0
    assert "no-such.json" not in out(capsys)


# --------------------------------------------------------------------------
# md-section
# --------------------------------------------------------------------------

def test_md_section_by_number(md_files, capsys):
    run_md(md_files, "md-section", "1")
    text = out(capsys)
    assert "Учим язык разговором" in text
    assert "Продуктовая карта" not in text        # соседняя секция не захвачена


def test_md_section_zero_is_header(md_files, capsys):
    run_md(md_files, "md-section", "0")
    text = out(capsys)
    assert "PROJECT STATUS — Parlai" in text
    assert "Видение продукта" not in text


def test_md_section_by_title_substring(md_files, capsys):
    run_md(md_files, "md-section", "риск")
    assert "LLM-латентность" in out(capsys)


def test_md_section_titles_only(md_files, capsys):
    run_md(md_files, "md-section", "2", "--titles")
    text = out(capsys)
    assert "Пользователи и задачи" in text
    assert "Взрослые B1" not in text


def test_md_section_unknown_errors_with_hint(md_files, capsys):
    run_md(md_files, "md-section", "99", expect=2)
    text = out(capsys)
    assert "1. Видение продукта" in text
    assert "Traceback" not in text


def test_md_section_json_carries_line_range(md_files, capsys):
    run_md(md_files, "md-section", "8", "--json")
    payload = json.loads(out(capsys))
    assert payload["num"] == "8" and payload["start"] < payload["end"]
    assert "Митигация" in payload["text"]


# --------------------------------------------------------------------------
# md-journal
# --------------------------------------------------------------------------

def test_md_journal_last_one(md_files, capsys):
    run_md(md_files, "md-journal", "--last", "1")
    text = out(capsys)
    assert "Тело третьей записи" in text
    assert "Тело первой записи" not in text


def test_md_journal_titles_only(md_files, capsys):
    run_md(md_files, "md-journal", "--last", "0", "--titles")
    text = out(capsys)
    assert text.count("2026-08-") >= 3
    assert "Тело первой записи" not in text


def test_md_journal_since_until(md_files, capsys):
    run_md(md_files, "md-journal", "--last", "0", "--since", "2026-08-25",
           "--until", "2026-08-25", "--titles")
    text = out(capsys)
    assert "Free Talk" in text
    assert "2026-08-26" not in text


def test_md_journal_grep_matches_body(md_files, capsys):
    run_md(md_files, "md-journal", "--last", "0", "--grep", "каталог тем", "--titles")
    text = out(capsys)
    assert "Free Talk" in text
    assert "U03" not in text


def test_md_journal_no_match_errors(md_files, capsys):
    run_md(md_files, "md-journal", "--grep", "нет такой строки", expect=2)
    assert "Traceback" not in out(capsys)


def test_md_journal_bad_date_errors(md_files, capsys):
    run_md(md_files, "md-journal", "--since", "26-08-25", expect=1)
    assert "YYYY-MM-DD" in out(capsys)


def test_md_journal_archive_requires_filter(md_files, capsys):
    run_md(md_files, "md-journal", "--archive", expect=1)
    assert "--grep" in out(capsys)


def test_md_journal_archive_returns_index_not_bodies(md_files, capsys):
    run_md(md_files, "md-journal", "--archive", "--since", "2026-08-01")
    text = out(capsys)
    assert "2026-08-16" in text and "стр." in text
    assert "Старое тело" not in text


# --------------------------------------------------------------------------
# md-risks
# --------------------------------------------------------------------------

def test_md_risks_open_by_default(md_files, capsys):
    run_md(md_files, "md-risks")
    text = out(capsys)
    assert "LLM-латентность" in text
    assert "Зеркалирование" not in text
    assert "2 из 3" in text


def test_md_risks_all_includes_closed(md_files, capsys):
    run_md(md_files, "md-risks", "--all")
    text = out(capsys)
    assert "Зеркалирование" in text
    assert "[закрыт]" in text


def test_md_risks_grep(md_files, capsys):
    run_md(md_files, "md-risks", "--grep", "scope")
    text = out(capsys)
    assert "Раздутый scope" in text
    assert "LLM-латентность" not in text


def test_md_risks_full_adds_mitigation(md_files, capsys):
    run_md(md_files, "md-risks", "--full")
    text = out(capsys)
    assert "митигация: streaming" in text


def test_md_risks_json_has_open_flag(md_files, capsys):
    run_md(md_files, "md-risks", "--all", "--json")
    payload = json.loads(out(capsys))
    assert payload["total"] == 3
    assert [r["open"] for r in payload["risks"]] == [True, True, False]


def test_md_risks_skips_table_separator_row(md_files, capsys):
    run_md(md_files, "md-risks", "--all", "--json")
    payload = json.loads(out(capsys))
    assert all("---" not in r["risk"] for r in payload["risks"])


def test_md_missing_file_errors_cleanly(tmp_path, capsys):
    code = status_query.main(["--tracker-file", str(tmp_path / "nope.md"), "md-toc"])
    assert code == 1
    text = out(capsys)
    assert "nope.md" in text and "Traceback" not in text


def test_md_nothing_is_written(md_files, tmp_path, capsys):
    before = {p: p.read_bytes() for p in md_files}
    listing_before = sorted(p.name for p in tmp_path.iterdir())
    for args in (["md-toc"], ["md-section", "8"], ["md-journal"], ["md-risks", "--all"],
                 ["md-journal", "--archive", "--since", "2026-08-01"]):
        run_md(md_files, *args)
    capsys.readouterr()
    assert {p: p.read_bytes() for p in md_files} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == listing_before
