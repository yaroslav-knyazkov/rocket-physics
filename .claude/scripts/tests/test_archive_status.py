# -*- coding: utf-8 -*-
"""Тесты для .claude/scripts/archive_status.py.

Запуск из корня репозитория:
    PYTHONUTF8=1 python -m pytest .claude/scripts/tests -v

Все тесты работают на синтетических файлах в tmp_path. Боевые
dev/status.json / dev/status-archive.json не читаются и не мутируются.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive_status  # noqa: E402


# --------------------------------------------------------------------------
# фикстуры
# --------------------------------------------------------------------------

def write_json(path: Path, data, indent: int, newline: str = "\r\n", trailing: bool = False) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    text = newline.join(text.split("\n"))
    if trailing:
        text += newline
    path.write_text(text, encoding="utf-8", newline="")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


STUB = {"id": 1, "name": "Первая", "status": "done", "archived": True}

FULL_STAGE_2 = {
    "id": 2,
    "name": "Вторая",
    "status": "done",
    "complexity": "medium",
    "qa_note": "всё зелено, 120 тестов",
    "docs": ["dev/docs/a.md", "dev/docs/b.md"],
}

FULL_STAGE_3 = {
    "id": "3.1",
    "name": "Третья",
    "status": "completed",
    "note": "закрыта отдельным решением",
}

LIVE_STAGE_35 = {
    "id": 35,
    "name": "Диалоговый движок",
    "status": "in_progress",
    "w0": {"status": "closed", "text": "волна ноль" * 20},
    "w0_1": {"status": "closed", "text": "волна ноль-один" * 20},
    "w1": {"status": "closed", "text": "волна один" * 20},
    "w2": {"status": "open", "text": "волна два, ещё живая"},
}

OPEN_STAGE = {
    "id": 34,
    "name": "Живая",
    "status": "in_progress",
    "note": "работа идёт",
}


def make_live():
    return {
        "project": "Parlai",
        "updated": "2026-08-20",
        "current_stage": "35",
        "stages": [dict(STUB), dict(FULL_STAGE_2), dict(FULL_STAGE_3), dict(OPEN_STAGE),
                   json.loads(json.dumps(LIVE_STAGE_35))],
        "decisions": [
            {"date": "2026-07-01", "question": "старое решение", "choice": "A", "approved": True},
            {"date": "2026-08-01", "question": "решение на границе", "choice": "B"},
            {"date": "2026-08-20", "question": "свежее решение", "choice": "C"},
            {"question": "решение без даты", "choice": "D"},
        ],
        "artifacts": {"docs": "dev/docs"},
        "archive": {
            "file": "dev/status-archive.json",
            "generated": "2026-08-19",
            "note": "Закрытые стадии вынесены туда.",
            "stages_archived": 1,
            "decisions_archived": 0,
            "legacy_keys_archived": [],
        },
        "old_direction_status": {"status": "done", "text": "закрытое направление"},
        "another_old_key": "просто строка",
        "live_direction": {"status": "open"},
    }


def make_archive():
    return {
        "_note": "Архив dev/status.json. Архивации: 2026-08-19.",
        "generated": "2026-08-19",
        "stages": [
            {"id": 1, "name": "Первая", "status": "done", "detail": "полный текст первой стадии"},
        ],
        "decisions": [],
        "legacy_keys": {},
    }


@pytest.fixture
def repo(tmp_path):
    """Пара файлов live/archive в tmp_path + аргументы путей для main()."""
    live = tmp_path / "status.json"
    arch = tmp_path / "status-archive.json"
    write_json(live, make_live(), indent=2)
    write_json(arch, make_archive(), indent=1)
    return {
        "live": live,
        "arch": arch,
        "backup_dir": tmp_path / ".status-backup",
        "args": ["--live", str(live), "--archive", str(arch), "--today", "2026-08-26"],
    }


def snapshot(repo):
    return repo["live"].read_bytes(), repo["arch"].read_bytes()


# --------------------------------------------------------------------------
# report / dry-run — ничего не пишут
# --------------------------------------------------------------------------

def test_report_writes_nothing(repo, capsys):
    before = snapshot(repo)
    rc = archive_status.main(repo["args"])
    out = capsys.readouterr().out
    assert rc == 0
    assert snapshot(repo) == before
    assert not repo["backup_dir"].exists()
    assert "stages" in out
    # кандидаты видны, уже заархивированная стадия помечена skip
    assert "2" in out and "3.1" in out


def test_dry_run_stages_writes_nothing(repo, capsys):
    before = snapshot(repo)
    rc = archive_status.main(repo["args"] + ["--stages"])
    out = capsys.readouterr().out
    assert rc == 0
    assert snapshot(repo) == before
    assert not repo["backup_dir"].exists()
    assert "--apply" in out


def test_dry_run_keys_writes_nothing(repo):
    before = snapshot(repo)
    rc = archive_status.main(repo["args"] + ["--keys", "old_direction_status,another_old_key"])
    assert rc == 0
    assert snapshot(repo) == before


# --------------------------------------------------------------------------
# стадии
# --------------------------------------------------------------------------

def test_stage_moves_fully_and_leaves_stub(repo):
    rc = archive_status.main(repo["args"] + ["--stages", "--apply"])
    assert rc == 0

    live = read_json(repo["live"])
    arch = read_json(repo["arch"])

    by_id = {str(s["id"]): s for s in live["stages"]}
    assert by_id["2"] == {"id": 2, "name": "Вторая", "status": "done", "archived": True}
    assert by_id["3.1"] == {"id": "3.1", "name": "Третья", "status": "completed", "archived": True}
    # живая стадия не тронута
    assert by_id["34"] == OPEN_STAGE
    assert by_id["35"]["w1"]["status"] == "closed"
    # порядок стадий сохранён
    assert [str(s["id"]) for s in live["stages"]] == ["1", "2", "3.1", "34", "35"]

    arch_by_id = {str(s["id"]): s for s in arch["stages"]}
    assert arch_by_id["2"] == FULL_STAGE_2
    assert arch_by_id["3.1"] == FULL_STAGE_3
    assert arch_by_id["1"]["detail"] == "полный текст первой стадии"  # старое не затёрто

    # мета пересчитана
    assert live["archive"]["stages_archived"] == 3
    assert live["archive"]["generated"] == "2026-08-26"
    assert live["updated"] == "2026-08-26"
    assert arch["generated"] == "2026-08-26"


def test_idempotent_second_run_is_noop(repo):
    assert archive_status.main(repo["args"] + ["--stages", "--apply"]) == 0
    after_first = snapshot(repo)

    rc = archive_status.main(repo["args"] + ["--stages", "--apply"])
    assert rc == 0
    live_after, arch_after = snapshot(repo)
    arch = read_json(repo["arch"])
    assert len(arch["stages"]) == 3
    assert [str(s["id"]) for s in json.loads(live_after.decode("utf-8"))["stages"]] == \
           ["1", "2", "3.1", "34", "35"]
    # второй прогон не должен ничего дублировать; содержимое стабильно
    assert (live_after, arch_after) == after_first


def test_conflict_id_in_archive_but_full_body_in_live_aborts(repo):
    arch = make_archive()
    arch["stages"].append({"id": 2, "name": "Вторая", "status": "done", "qa_note": "ДРУГОЙ текст"})
    write_json(repo["arch"], arch, indent=1)
    before = snapshot(repo)

    rc = archive_status.main(repo["args"] + ["--stages", "--apply"])
    assert rc != 0
    assert snapshot(repo) == before  # ничего не записано
    assert not repo["backup_dir"].exists()


def test_conflict_message_names_the_item(repo, capsys):
    arch = make_archive()
    arch["stages"].append({"id": 2, "name": "Вторая", "status": "done", "qa_note": "ДРУГОЙ текст"})
    write_json(repo["arch"], arch, indent=1)
    archive_status.main(repo["args"] + ["--stages", "--apply"])
    captured = capsys.readouterr()
    assert "2" in (captured.out + captured.err)
    assert "онфликт" in (captured.out + captured.err)


# --------------------------------------------------------------------------
# top-level ключи
# --------------------------------------------------------------------------

def test_keys_archived(repo):
    rc = archive_status.main(repo["args"] + ["--keys", "old_direction_status,another_old_key", "--apply"])
    assert rc == 0
    live = read_json(repo["live"])
    arch = read_json(repo["arch"])

    assert "old_direction_status" not in live
    assert "another_old_key" not in live
    assert "live_direction" in live
    assert arch["legacy_keys"]["old_direction_status"] == {"status": "done", "text": "закрытое направление"}
    assert arch["legacy_keys"]["another_old_key"] == "просто строка"
    assert live["archive"]["legacy_keys_archived"] == ["another_old_key", "old_direction_status"]


def test_unknown_key_is_reported_not_fatal(repo, capsys):
    rc = archive_status.main(repo["args"] + ["--keys", "no_such_key", "--apply"])
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "no_such_key" in out
    assert rc == 0
    assert read_json(repo["arch"])["legacy_keys"] == {}


def test_key_dedup_when_identical(repo):
    """Ключ уже в архиве и текст совпадает — не конфликт: из живого убираем, архив не трогаем."""
    arch = make_archive()
    arch["legacy_keys"]["another_old_key"] = "просто строка"
    write_json(repo["arch"], arch, indent=1)

    rc = archive_status.main(repo["args"] + ["--keys", "another_old_key", "--apply"])
    assert rc == 0
    assert "another_old_key" not in read_json(repo["live"])
    assert read_json(repo["arch"])["legacy_keys"] == {"another_old_key": "просто строка"}


def test_stages_subset_by_id(repo):
    rc = archive_status.main(repo["args"] + ["--stages", "3.1", "--apply"])
    assert rc == 0
    live = read_json(repo["live"])
    by_id = {str(s["id"]): s for s in live["stages"]}
    assert by_id["3.1"].get("archived") is True
    assert by_id["2"] == FULL_STAGE_2  # не входила в список — не тронута
    assert [str(s["id"]) for s in read_json(repo["arch"])["stages"]] == ["1", "3.1"]


def test_stages_subset_skips_open_stage(repo, capsys):
    rc = archive_status.main(repo["args"] + ["--stages", "34", "--apply"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "34" in out
    assert read_json(repo["live"])["stages"][3] == OPEN_STAGE


def test_key_conflict_aborts(repo):
    arch = make_archive()
    arch["legacy_keys"]["another_old_key"] = "другое значение"
    write_json(repo["arch"], arch, indent=1)
    before = snapshot(repo)
    rc = archive_status.main(repo["args"] + ["--keys", "another_old_key", "--apply"])
    assert rc != 0
    assert snapshot(repo) == before


# --------------------------------------------------------------------------
# подключи стадии
# --------------------------------------------------------------------------

def test_substages_leave_pointer_string(repo):
    rc = archive_status.main(repo["args"] + ["--substages", "35:w0,w1", "--apply"])
    assert rc == 0
    live = read_json(repo["live"])
    arch = read_json(repo["arch"])

    st35 = [s for s in live["stages"] if str(s["id"]) == "35"][0]
    assert isinstance(st35["w1"], str)
    assert st35["w1"].startswith("archived → ")
    assert st35["w1"].endswith("stage_subkeys.35.w1")
    assert st35["w0"].endswith("stage_subkeys.35.w0")
    # не перечисленные подключи не тронуты
    assert st35["w0_1"]["status"] == "closed"
    assert st35["w2"]["status"] == "open"
    # порядок ключей стадии сохранён
    assert list(st35.keys()) == list(LIVE_STAGE_35.keys())

    assert arch["stage_subkeys"]["35"]["w1"] == LIVE_STAGE_35["w1"]
    assert arch["stage_subkeys"]["35"]["w0"] == LIVE_STAGE_35["w0"]
    assert live["archive"]["stage_subkeys_archived"] == ["35.w0", "35.w1"]


def test_substages_idempotent(repo):
    assert archive_status.main(repo["args"] + ["--substages", "35:w1", "--apply"]) == 0
    before = snapshot(repo)
    assert archive_status.main(repo["args"] + ["--substages", "35:w1", "--apply"]) == 0
    assert snapshot(repo) == before


def test_substages_unknown_stage_reported(repo, capsys):
    rc = archive_status.main(repo["args"] + ["--substages", "99:w1", "--apply"])
    out = capsys.readouterr().out
    assert "99" in out
    assert rc == 0
    assert "stage_subkeys" not in read_json(repo["arch"])


# --------------------------------------------------------------------------
# решения
# --------------------------------------------------------------------------

def test_decisions_cutoff(repo):
    rc = archive_status.main(repo["args"] + ["--decisions", "--cutoff", "2026-08-15", "--apply"])
    assert rc == 0
    live = read_json(repo["live"])
    arch = read_json(repo["arch"])

    dates = [d.get("date") for d in live["decisions"]]
    assert dates == ["2026-08-20", None]  # старые уехали, запись без даты осталась
    assert [d["date"] for d in arch["decisions"]] == ["2026-07-01", "2026-08-01"]
    assert live["archive"]["decisions_archived"] == 2


def test_decisions_cutoff_is_exclusive(repo):
    archive_status.main(repo["args"] + ["--decisions", "--cutoff", "2026-08-01", "--apply"])
    arch = read_json(repo["arch"])
    assert [d["date"] for d in arch["decisions"]] == ["2026-07-01"]


def test_decisions_without_date_are_reported(repo, capsys):
    archive_status.main(repo["args"] + ["--decisions", "--cutoff", "2026-08-15"])
    out = capsys.readouterr().out
    assert "без даты" in out


def test_decisions_requires_cutoff(repo):
    before = snapshot(repo)
    rc = archive_status.main(repo["args"] + ["--decisions", "--apply"])
    assert rc != 0
    assert snapshot(repo) == before


def test_decisions_idempotent(repo):
    assert archive_status.main(repo["args"] + ["--decisions", "--cutoff", "2026-08-15", "--apply"]) == 0
    before = snapshot(repo)
    assert archive_status.main(repo["args"] + ["--decisions", "--cutoff", "2026-08-15", "--apply"]) == 0
    assert snapshot(repo) == before
    assert len(read_json(repo["arch"])["decisions"]) == 2


# --------------------------------------------------------------------------
# решения topic-стиля (2026-09-23: журнал решений разъехался — часть записей
# несёт `question`, часть `topic`; старый ключ (date, question) схлопывал все
# topic-записи одной даты в (date, None) и ложно конфликтовал между собой)
# --------------------------------------------------------------------------

def test_decisions_distinguishes_same_date_topic_style_entries(repo):
    """Two different topic-style decisions sharing a date must not collide:
    the one already in the archive is deduped, the other one is recognised
    as new and archived — no phantom conflict."""
    live = make_live()
    live["decisions"].append(
        {"date": "2026-07-10", "topic": "Тема A", "choice": "X"}
    )
    live["decisions"].append(
        {"date": "2026-07-10", "topic": "Тема A", "choice": "Y"}
    )
    write_json(repo["live"], live, indent=2)

    arch = make_archive()
    arch["decisions"].append({"date": "2026-07-10", "topic": "Тема A", "choice": "X"})
    write_json(repo["arch"], arch, indent=1)

    rc = archive_status.main(repo["args"] + ["--decisions", "--cutoff", "2026-08-15", "--apply"])
    assert rc == 0

    arch_after = read_json(repo["arch"])
    live_after = read_json(repo["live"])

    # оба topic-решения с 2026-07-10 ушли из живого файла...
    assert not any(d.get("date") == "2026-07-10" for d in live_after["decisions"])
    # ...но в архиве осталась ровно одна старая (X) и добавилась ровно одна новая (Y)
    same_date = [d for d in arch_after["decisions"] if d.get("date") == "2026-07-10"]
    assert sorted(d["choice"] for d in same_date) == ["X", "Y"]
    assert len(same_date) == 2


def test_decision_conflict_message_falls_back_to_topic_not_none(repo, capsys, monkeypatch):
    """When a real conflict does fire, the message must show the topic label,
    never the literal 'None' that d.get('question') alone would produce."""
    monkeypatch.setattr(archive_status, "decision_digest", lambda d: "forced-collision")

    arch = make_archive()
    arch["decisions"].append({"date": "2026-07-10", "topic": "Пивот стека", "choice": "A"})
    write_json(repo["arch"], arch, indent=1)

    live = make_live()
    live["decisions"].append({"date": "2026-07-10", "topic": "Пивот стека", "choice": "B"})
    write_json(repo["live"], live, indent=2)

    before = snapshot(repo)
    rc = archive_status.main(repo["args"] + ["--decisions", "--cutoff", "2026-08-15", "--apply"])
    out = capsys.readouterr()
    text = out.out + out.err

    assert rc != 0
    assert snapshot(repo) == before  # конфликт — ничего не записано
    assert "Пивот стека" in text
    assert "None" not in text


# --------------------------------------------------------------------------
# бэкапы и формат
# --------------------------------------------------------------------------

def test_backup_created_before_write(repo):
    original_live = repo["live"].read_bytes()
    original_arch = repo["arch"].read_bytes()

    assert archive_status.main(repo["args"] + ["--stages", "--apply"]) == 0

    backups = sorted(repo["backup_dir"].iterdir())
    names = [p.name for p in backups]
    assert any(n.startswith("status.json.") for n in names)
    assert any(n.startswith("status-archive.json.") for n in names)

    live_bak = [p for p in backups if p.name.startswith("status.json.")][0]
    arch_bak = [p for p in backups if p.name.startswith("status-archive.json.")][0]
    assert live_bak.read_bytes() == original_live
    assert arch_bak.read_bytes() == original_arch


def test_formatting_preserved(repo):
    assert archive_status.main(repo["args"] + ["--stages", "--apply"]) == 0

    live_raw = repo["live"].read_bytes()
    arch_raw = repo["arch"].read_bytes()

    assert b"\r\n" in live_raw and b"\r\n" in arch_raw
    assert live_raw.count(b"\n") == live_raw.count(b"\r\n")  # нет голых LF
    assert arch_raw.count(b"\n") == arch_raw.count(b"\r\n")
    assert not live_raw.endswith(b"\n")  # как в оригинале — без финального перевода строки
    assert not arch_raw.endswith(b"\n")

    live_text = live_raw.decode("utf-8")
    arch_text = arch_raw.decode("utf-8")
    assert live_text.startswith('{\r\n  "project"')   # отступ 2, как был
    assert arch_text.startswith('{\r\n "_note"')      # отступ 1, как был
    assert "\\u" not in live_text  # ensure_ascii=False


def test_trailing_newline_preserved_when_present(tmp_path):
    live = tmp_path / "status.json"
    arch = tmp_path / "status-archive.json"
    write_json(live, make_live(), indent=2, newline="\n", trailing=True)
    write_json(arch, make_archive(), indent=4, newline="\n", trailing=True)

    rc = archive_status.main(["--live", str(live), "--archive", str(arch),
                              "--today", "2026-08-26", "--stages", "--apply"])
    assert rc == 0
    live_raw = live.read_bytes()
    arch_raw = arch.read_bytes()
    assert live_raw.endswith(b"\n") and b"\r" not in live_raw
    assert arch_raw.endswith(b"\n") and b"\r" not in arch_raw
    assert arch_raw.decode("utf-8").startswith('{\n    "_note"')  # отступ 4 сохранён


def test_archive_written_before_live(repo, monkeypatch):
    """Живой файл не должен быть усечён, если запись архива провалилась."""
    original = snapshot(repo)
    real_write = archive_status.write_json_file

    def failing_write(path, *a, **kw):
        if path == repo["live"]:
            raise RuntimeError("bang")
        return real_write(path, *a, **kw)

    monkeypatch.setattr(archive_status, "write_json_file", failing_write)
    with pytest.raises(RuntimeError):
        archive_status.main(repo["args"] + ["--stages", "--apply"])

    assert repo["live"].read_bytes() == original[0]  # живой цел
    assert read_json(repo["arch"])["stages"]  # архив уже дописан — данные не потеряны


def test_combined_flags_single_pass(repo):
    rc = archive_status.main(repo["args"] + [
        "--stages", "--decisions", "--cutoff", "2026-08-15",
        "--keys", "another_old_key", "--substages", "35:w1", "--apply",
    ])
    assert rc == 0
    live = read_json(repo["live"])
    arch = read_json(repo["arch"])
    assert live["archive"]["stages_archived"] == 3
    assert live["archive"]["decisions_archived"] == 2
    assert live["archive"]["legacy_keys_archived"] == ["another_old_key"]
    assert live["archive"]["stage_subkeys_archived"] == ["35.w1"]
    assert len(arch["stages"]) == 3 and len(arch["decisions"]) == 2
    # один бэкап-набор на прогон, не по одному на секцию
    assert len(list(repo["backup_dir"].iterdir())) == 2
