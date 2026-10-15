# -*- coding: utf-8 -*-
"""Тесты для .claude/scripts/wt.py.

Запуск из корня репозитория:
    PYTHONUTF8=1 python -m pytest .claude/scripts/tests/test_wt.py -v

Всё происходит в изолированной песочнице в tmp_path: bare-репозиторий как
origin + клон как «основной репозиторий» + копия wt.py внутри него. Боевой
репозиторий и origin проекта не читаются и не мутируются.

Оба регрессионных теста внизу файла закрывают баги, найденные ручным
прогоном 2026-08-30: sync не пушил ветку после ручного `rebase --continue`,
land падал на `git merge -F -` (merge, в отличие от commit, не читает
сообщение со stdin).
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WT_SRC = Path(__file__).resolve().parents[1] / "wt.py"


def load_wt(path: Path = WT_SRC):
    """Import a copy of wt.py as a module, for tests that stub its internals.

    Used for the database-isolation paths: the admin layer (asyncpg through the
    backend venv) and docker are stubbed, so none of it needs a live Postgres.
    """
    spec = importlib.util.spec_from_file_location("wt_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    # No __pycache__: importing the sandbox copy would otherwise leave an
    # untracked directory in the sandbox main repo, which `doctor` correctly
    # reports as a stray edit.
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = saved
    return mod


wt_mod = load_wt()


# --------------------------------------------------------------------------
# песочница
# --------------------------------------------------------------------------

def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return (proc.stdout or "").strip()


class Sandbox:
    def __init__(self, root: Path):
        self.root = root
        self.origin = root / "origin.git"
        self.main = root / "main"
        self.wt_root = root / "wt"

    def wt(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.main / ".claude" / "scripts" / "wt.py"), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(cwd) if cwd else None,
            env={**_base_env(), "WT_ROOT": str(self.wt_root)},
        )

    def slot(self, slug: str) -> dict:
        return json.loads(
            (self.wt_root / slug / ".wt-slot.json").read_text(encoding="utf-8"))

    def state(self) -> dict:
        p = self.main / ".claude" / "wt-active.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _base_env() -> dict:
    import os
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t",
        "PYTHONUTF8": "1",
    })
    return env


@pytest.fixture()
def sb(tmp_path: Path) -> Sandbox:
    s = Sandbox(tmp_path)
    subprocess.run(["git", "init", "-q", "--bare", str(s.origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(s.origin), str(s.main)],
                   check=True, capture_output=True)
    git(s.main, "config", "user.email", "t@t")
    git(s.main, "config", "user.name", "T")
    scripts = s.main / ".claude" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(WT_SRC, scripts / "wt.py")
    (s.main / "shared.txt").write_text("line1\n", encoding="utf-8")
    # .wt-slot.json пишется в дерево при `new` — в боевом репо он в гитигноре,
    # .env тоже (его в дерево копирует link_local_artifacts)
    (s.main / ".gitignore").write_text(".wt-slot.json\n.env\n",
                                       encoding="utf-8")
    (s.main / "dev").mkdir()
    (s.main / "dev" / "status.json").write_text("{}\n", encoding="utf-8")
    git(s.main, "add", "-A")
    git(s.main, "commit", "-qm", "init")
    git(s.main, "branch", "-M", "main")
    git(s.main, "push", "-qu", "origin", "main")
    return s


def advance_base(sb: Sandbox, content: str, name: str = "shared.txt") -> None:
    (sb.main / name).write_text(content, encoding="utf-8")
    git(sb.main, "add", "-A")
    git(sb.main, "commit", "-qm", f"base moves ({name})")
    git(sb.main, "push", "-q", "origin", "main")


# --------------------------------------------------------------------------
# жизненный цикл
# --------------------------------------------------------------------------

def test_new_creates_branch_worktree_and_pushes(sb: Sandbox):
    r = sb.wt("new", "demo", "--task", "demo task")
    assert r.returncode == 0, r.stderr
    wt = sb.wt_root / "demo"
    assert (wt / "shared.txt").exists()
    assert "wt/demo" in git(sb.main, "branch", "--list", "wt/demo")
    # ветка сразу на origin — локальных-только коммитов в этой схеме не бывает
    assert "wt/demo" in git(sb.main, "ls-remote", "--heads", "origin", "wt/demo")
    st = sb.state()
    assert st["current"] == "demo"
    assert st["worktrees"]["demo"]["base"] == "main"
    # базовая ветка не тронута: worktree взял её из origin, а не переключил
    assert git(sb.main, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_new_refuses_duplicate_slug(sb: Sandbox):
    assert sb.wt("new", "demo").returncode == 0
    r = sb.wt("new", "demo")
    assert r.returncode == 3
    assert "already exists" in r.stderr


def test_commit_pushes_every_time(sb: Sandbox):
    sb.wt("new", "demo")
    (sb.wt_root / "demo" / "a.txt").write_text("a\n", encoding="utf-8")
    r = sb.wt("commit", "-m", "feat: a")
    assert r.returncode == 0, r.stderr
    assert "pushed to origin/wt/demo" in r.stdout
    local = git(sb.wt_root / "demo", "rev-parse", "HEAD")
    remote = git(sb.main, "rev-parse", "refs/remotes/origin/wt/demo")
    assert local == remote


def test_commit_adds_co_author_and_refuses_secrets(sb: Sandbox):
    sb.wt("new", "demo")
    wt = sb.wt_root / "demo"
    (wt / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a")
    assert "Co-Authored-By:" in git(wt, "log", "-1", "--pretty=%B")

    (wt / ".env.production").write_text("SECRET=1\n", encoding="utf-8")
    r = sb.wt("commit", "-m", "oops")
    assert r.returncode == 3
    assert "REFUSED" in r.stdout
    # индекс откачен, ничего не закоммичено
    assert git(wt, "diff", "--cached", "--name-only") == ""


def test_land_blocked_until_synced_then_merges(sb: Sandbox):
    sb.wt("new", "demo", "--task", "demo task")
    wt = sb.wt_root / "demo"
    (wt / "shared.txt").write_text("line1\nfrom-worktree\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: worktree change")

    advance_base(sb, "line1\n", name="basefile.txt")

    blocked = sb.wt("land")
    assert blocked.returncode == 3
    assert "behind origin/main" in blocked.stdout

    assert sb.wt("sync").returncode == 0
    dry = sb.wt("land", "--dry-run")
    assert dry.returncode == 0 and "dry-run" in dry.stdout
    # dry-run ничего не сделал
    assert (sb.wt_root / "demo").exists()

    r = sb.wt("land")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (sb.wt_root / "demo").exists()
    assert sb.state() == {}
    assert git(sb.main, "branch", "--list", "wt/demo") == ""
    assert git(sb.main, "ls-remote", "--heads", "origin", "wt/demo") == ""
    # работа доехала и локально, и в origin, merge-коммитом
    assert "from-worktree" in (sb.main / "shared.txt").read_text(encoding="utf-8")
    assert git(sb.main, "rev-parse", "HEAD") == git(sb.main, "rev-parse", "origin/main")
    assert len(git(sb.main, "rev-parse", "HEAD^@").split()) == 2


def test_land_blocked_by_stray_edits_in_main_repo(sb: Sandbox):
    sb.wt("new", "demo")
    (sb.wt_root / "demo" / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a")
    (sb.main / "stray.txt").write_text("stray\n", encoding="utf-8")

    r = sb.wt("land")
    assert r.returncode == 3
    assert "stray change" in r.stdout
    assert sb.wt("doctor").returncode == 3


def test_drop_guards_unmerged_commits(sb: Sandbox):
    sb.wt("new", "demo")
    (sb.wt_root / "demo" / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a")

    blocked = sb.wt("drop")
    assert blocked.returncode == 3
    assert (sb.wt_root / "demo").exists()

    forced = sb.wt("drop", "--force")
    assert forced.returncode == 0
    assert "recover: git branch" in forced.stdout
    assert not (sb.wt_root / "demo").exists()
    assert sb.state() == {}


def test_read_only_commands_never_mutate(sb: Sandbox):
    sb.wt("new", "demo")
    before = (git(sb.main, "rev-parse", "HEAD"),
              git(sb.wt_root / "demo", "rev-parse", "HEAD"),
              sb.state())
    for cmd in (["status"], ["doctor"], ["list"], ["prompt"]):
        assert sb.wt(*cmd).returncode in (0, 3)
    after = (git(sb.main, "rev-parse", "HEAD"),
             git(sb.wt_root / "demo", "rev-parse", "HEAD"),
             sb.state())
    assert before == after


# --------------------------------------------------------------------------
# регрессии (ручной прогон 2026-08-30)
# --------------------------------------------------------------------------

def test_sync_pushes_after_manual_rebase_continue(sb: Sandbox):
    """Регрессия: ранний выход по `behind == 0` оставлял ветку незапушенной.

    После ручного разрешения конфликта и `rebase --continue` ветка уже
    отребейзена, но расходится с origin. Старый sync печатал «nothing to do»
    и выходил, а land затем блокировался на «unpushed» без объяснимой причины.
    """
    sb.wt("new", "demo")
    wt = sb.wt_root / "demo"
    (wt / "shared.txt").write_text("line1\nfrom-worktree\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: worktree change")
    advance_base(sb, "line1\nfrom-base\n")

    conflicted = sb.wt("sync")
    assert conflicted.returncode == 2
    assert "REBASE CONFLICT" in conflicted.stdout

    (wt / "shared.txt").write_text("line1\nfrom-base\nfrom-worktree\n", encoding="utf-8")
    git(wt, "add", "shared.txt")
    subprocess.run(["git", "-C", str(wt), "rebase", "--continue"],
                   capture_output=True, env={**_base_env(), "GIT_EDITOR": "true"})

    r = sb.wt("sync")
    assert r.returncode == 0, r.stdout + r.stderr
    assert git(wt, "rev-parse", "HEAD") == git(wt, "rev-parse", "origin/wt/demo")
    assert sb.wt("land").returncode == 0


def test_land_merge_message_is_multiline(sb: Sandbox):
    """Регрессия: `git merge -F -` не существует (в отличие от `git commit`)."""
    sb.wt("new", "demo", "--task", "многострочное описание")
    (sb.wt_root / "demo" / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a")
    assert sb.wt("land").returncode == 0
    body = git(sb.main, "log", "-1", "--pretty=%B")
    assert "merge(wt/demo): многострочное описание" in body
    assert "Co-Authored-By:" in body


# --------------------------------------------------------------------------
# параллельные worktree: изоляция ресурсов и выбор дерева
# --------------------------------------------------------------------------

def test_parallel_worktrees_get_distinct_slots(sb: Sandbox):
    sb.wt("new", "one")
    sb.wt("new", "two")
    a, b = sb.slot("one"), sb.slot("two")
    assert a["slot"] != b["slot"]
    # порты не пересекаются ни между деревьями, ни с основным репо (8001/3000)
    ports = {a["backend_port"], a["frontend_port"], b["backend_port"], b["frontend_port"]}
    assert len(ports) == 4
    assert 8001 not in ports and 3000 not in ports
    assert a["redis_db"] != b["redis_db"]
    st = sb.state()["worktrees"]
    assert st["one"]["slot"] == a["slot"] and st["two"]["slot"] == b["slot"]


def test_slot_is_reused_after_land(sb: Sandbox):
    sb.wt("new", "one")
    first = sb.slot("one")["slot"]
    (sb.wt_root / "one" / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a", "--slug", "one")
    assert sb.wt("land", "--slug", "one").returncode == 0
    sb.wt("new", "three")
    assert sb.slot("three")["slot"] == first


def test_ambiguous_slug_is_refused_not_guessed(sb: Sandbox):
    """Главный риск параллельности — молчаливый коммит не того дерева."""
    sb.wt("new", "one")
    sb.wt("new", "two")
    (sb.wt_root / "two" / "b.txt").write_text("b\n", encoding="utf-8")

    blocked = sb.wt("commit", "-m", "feat: b", cwd=sb.root)
    assert blocked.returncode == 3
    assert "--slug" in blocked.stderr
    assert git(sb.wt_root / "two", "status", "--porcelain") != ""

    ok = sb.wt("commit", "-m", "feat: b", "--slug", "two")
    assert ok.returncode == 0
    assert "b.txt" in git(sb.wt_root / "two", "show", "--name-only", "--pretty=", "HEAD")
    assert git(sb.wt_root / "one", "log", "--oneline", "origin/main..HEAD") == ""


def test_slug_inferred_from_cwd(sb: Sandbox):
    sb.wt("new", "one")
    sb.wt("new", "two")
    (sb.wt_root / "two" / "b.txt").write_text("b\n", encoding="utf-8")
    r = sb.wt("commit", "-m", "feat: b", cwd=sb.wt_root / "two" / "dev")
    assert r.returncode == 0, r.stderr
    assert "wt/two" in r.stdout


def test_commit_refuses_tracker_files(sb: Sandbox):
    sb.wt("new", "one")
    wt = sb.wt_root / "one"
    (wt / "dev" / "status.json").write_text('{"x": 1}\n', encoding="utf-8")
    r = sb.wt("commit", "-m", "chore: tracker", "--slug", "one")
    assert r.returncode == 3
    assert "tracker" in r.stdout.lower()
    assert git(wt, "diff", "--cached", "--name-only") == ""


# --------------------------------------------------------------------------
# regressions: a second writer pushes to the same task branch (2026-08-30)
#
# Both holes destroy commits that exist ONLY on origin/<branch>: sync used a
# bare --force-with-lease (the lease compares against the remote-tracking ref
# the fetch one line above had just advanced, so it was satisfied by
# construction), and land never compared HEAD against origin/<branch> at all.
# --------------------------------------------------------------------------

def second_writer_pushes(sb: Sandbox, branch: str, name: str = "theirs.txt") -> str:
    """Another clone -- the user's own terminal, or a parallel agent session --
    commits to the SAME task branch and pushes. Returns their commit sha."""
    clone = sb.root / ("other-" + name.replace(".", "-"))
    subprocess.run(["git", "clone", "-q", "--branch", branch, str(sb.origin), str(clone)],
                   check=True, capture_output=True)
    git(clone, "config", "user.email", "t@t")
    git(clone, "config", "user.name", "T")
    (clone / name).write_text("from the second writer\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "second writer: " + name)
    git(clone, "push", "-q", "origin", branch)
    return git(clone, "rev-parse", "HEAD")


def remote_tip(sb: Sandbox, branch: str) -> str:
    o = git(sb.main, "ls-remote", "origin", branch)
    return o.split()[0] if o else ""


def test_sync_refuses_to_overwrite_a_second_writers_push(sb: Sandbox):
    sb.wt("new", "demo")
    wt = sb.wt_root / "demo"
    (wt / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a")

    theirs = second_writer_pushes(sb, "wt/demo")

    # A local-only commit, exactly what `rebase --continue` by hand leaves
    # behind: the branch now diverges from origin in both directions.
    (wt / "b.txt").write_text("b\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "feat: b")

    r = sb.wt("sync")
    assert r.returncode == 3, r.stdout + r.stderr
    msg = r.stdout + r.stderr
    assert "origin/wt/demo" in msg
    # the message must say what to do, not just "it failed"
    assert "fetch" in msg.lower() and "discard" in msg.lower()
    # their commit is untouched on origin
    assert remote_tip(sb, "wt/demo") == theirs



def test_sync_refuses_after_status_already_fetched_their_commit(sb: Sandbox):
    """The nastier ordering: `wt.py status` fetches, so by the time sync runs
    our belief about origin/<branch> IS their commit and comparing beliefs
    proves nothing. Only "was this tip ever HEAD here?" separates their work
    from our own pre-rebase tip."""
    sb.wt("new", "demo")
    wt = sb.wt_root / "demo"
    (wt / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a")

    theirs = second_writer_pushes(sb, "wt/demo", name="theirs-status.txt")
    sb.wt("status")

    (wt / "b.txt").write_text("b\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "feat: b")

    r = sb.wt("sync")
    assert r.returncode == 3, r.stdout + r.stderr
    assert remote_tip(sb, "wt/demo") == theirs

def test_land_blocked_when_branch_is_behind_its_own_remote(sb: Sandbox):
    sb.wt("new", "demo", "--task", "demo task")
    wt = sb.wt_root / "demo"
    (wt / "a.txt").write_text("a\n", encoding="utf-8")
    sb.wt("commit", "-m", "feat: a")

    theirs = second_writer_pushes(sb, "wt/demo")
    main_before = git(sb.main, "rev-parse", "HEAD")

    r = sb.wt("land")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "LAND BLOCKED" in r.stdout
    assert "behind origin/wt/demo" in r.stdout
    assert "wt.py sync" in r.stdout
    # nothing merged, nothing deleted, their commit still reachable on origin
    assert git(sb.main, "rev-parse", "HEAD") == main_before
    assert wt.exists()
    assert remote_tip(sb, "wt/demo") == theirs
    assert sb.state()["worktrees"].get("demo") is not None


def test_commit_does_not_force_over_a_second_writers_push(sb: Sandbox):
    """The push fallback in `commit` is the same hole: a rejected plain push
    already advances the remote-tracking ref, so a bare lease is satisfied."""
    sb.wt("new", "demo")
    wt = sb.wt_root / "demo"
    theirs = second_writer_pushes(sb, "wt/demo")

    # CLAUDE.md tells the orchestrator to run `wt.py status` before
    # committing, and status fetches -- which is what arms the bare
    # lease with THEIR sha.
    sb.wt("status")

    (wt / "mine.txt").write_text("mine\n", encoding="utf-8")
    r = sb.wt("commit", "-m", "feat: mine")

    assert r.returncode == 3, r.stdout + r.stderr
    assert "PUSH" in r.stdout.upper()
    # the commit itself is kept locally -- only the push is refused
    assert "mine.txt" in git(wt, "show", "--name-only", "--pretty=", "HEAD")
    assert remote_tip(sb, "wt/demo") == theirs


def test_drop_refuses_to_delete_a_branch_whose_commits_live_only_on_origin(sb: Sandbox):
    sb.wt("new", "demo")
    theirs = second_writer_pushes(sb, "wt/demo")

    # Locally there is nothing beyond the base, so the old `base..branch`
    # guard saw an empty branch and deleted it from origin without a word.
    blocked = sb.wt("drop")
    assert blocked.returncode == 3, blocked.stdout + blocked.stderr
    assert "origin/wt/demo" in blocked.stdout
    assert remote_tip(sb, "wt/demo") == theirs
    assert (sb.wt_root / "demo").exists()

    forced = sb.wt("drop", "--force")
    assert forced.returncode == 0, forced.stdout + forced.stderr
    # a recovery command for THEIR tip, not only for the local one
    assert theirs[:7] in forced.stdout


# --------------------------------------------------------------------------
# regression: a tree that only LOOKS isolated (2026-09-02 incident)
#
# `new --db copy` hit `CREATE DATABASE ... TEMPLATE lingua_v2` -> "There are 8
# other sessions using the database". wt.py appended a note and CARRIED ON, so
# the .env in the tree still said lingua_v2 -- the user's working
# database -- while `wt.py status` reported the tree as normal. A routine
# `alembic downgrade -1` inside that tree then dropped a table from it.
#
# No Postgres is needed to reproduce it: the sandbox has no backend venv, so
# the admin layer fails for a different reason and the DEGRADATION is the same.
# --------------------------------------------------------------------------

BASE_DB_URL = "postgresql+asyncpg://lingua:pw@localhost:55432/lingua_v2"


def give_main_repo_env(sb: Sandbox, url: str = BASE_DB_URL) -> Path:
    """.env in the main repo -- the file `new` copies and patches."""
    p = sb.main / ".env"
    p.write_text(f"DATABASE_URL={url}\nREDIS_DB=0\n"
                 f"FRONTEND_URL=http://localhost:3000\n", encoding="utf-8")
    return p


def tree_db_url(sb: Sandbox, slug: str) -> str:
    lines = (sb.wt_root / slug / ".env").read_text(
        encoding="utf-8").splitlines()
    return next(ln.split("=", 1)[1] for ln in lines if ln.startswith("DATABASE_URL="))


def test_new_fails_loud_when_the_isolated_database_cannot_be_created(sb: Sandbox):
    give_main_repo_env(sb)

    r = sb.wt("new", "demo")

    assert r.returncode == 3, r.stdout + r.stderr
    msg = r.stdout + r.stderr
    # the tree must NOT be left pointing at the base database
    assert tree_db_url(sb, "demo") == BASE_DB_URL.replace("lingua_v2",
                                                          "lingua_v2_wt_demo")
    slot = sb.slot("demo")
    assert slot["database"] == ""
    assert slot["intended_database"] == "lingua_v2_wt_demo"
    assert slot["isolation"] == "failed"
    entry = sb.state()["worktrees"]["demo"]
    assert entry["database"] == "" and entry["isolation"] == "failed"
    # the operator is told what to do next, not just that it broke
    assert "dbcreate" in msg and "drop" in msg
    # the tree is left on disk (the branch was already pushed), not silently gone
    assert (sb.wt_root / "demo").exists()


def test_failed_isolation_is_loud_in_status_doctor_and_prompt(sb: Sandbox):
    give_main_repo_env(sb)
    assert sb.wt("new", "demo").returncode == 3

    st = sb.wt("status")
    assert "ISOLATION FAILED" in st.stdout

    doc = sb.wt("doctor")
    assert doc.returncode == 3, doc.stdout
    assert "isolation" in doc.stdout.lower()

    pr = sb.wt("prompt")
    assert "alembic" in pr.stdout.lower()
    assert "forbidden" in pr.stdout.lower()


def test_db_share_stays_a_legitimate_choice_but_is_marked(sb: Sandbox):
    give_main_repo_env(sb)

    r = sb.wt("new", "demo", "--db", "share")

    assert r.returncode == 0, r.stdout + r.stderr
    # share means share: the URL is deliberately left alone
    assert tree_db_url(sb, "demo") == BASE_DB_URL
    assert sb.slot("demo")["isolation"] == "share"

    st = sb.wt("status")
    assert "SHARED WITH MAIN REPO" in st.stdout
    # an explicit choice is not a defect
    assert sb.wt("doctor").returncode == 0
    pr = sb.wt("prompt")
    assert "forbidden" in pr.stdout.lower() and "alembic" in pr.stdout.lower()


def test_tree_without_env_is_not_reported_as_isolated(sb: Sandbox):
    """No .env at all: nothing points anywhere, so this is not the
    incident -- but it is not isolation either, and must not read as normal."""
    r = sb.wt("new", "demo")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sb.slot("demo")["isolation"] == "no-env"
    assert "NOT ISOLATED" in sb.wt("status").stdout


@pytest.mark.parametrize("url", ["", "sqlite:///./app.db"])
def test_env_without_postgres_gets_ports_only_not_a_failure(tmp_path, url):
    """A project without Postgres (no DATABASE_URL, sqlite, ...) is not an
    isolation failure: the tree simply gets ports/redis and no database."""
    wt = tree_with_env(tmp_path, url)
    record, notes, failure = wt_mod.isolate_worktree_env(
        tmp_path, wt, "demo", 1, "copy")
    assert failure == ""
    assert record["isolation"] == "no-env"
    assert any("no Postgres" in n for n in notes)


# --------------------------------------------------------------------------
# `CREATE DATABASE ... TEMPLATE` needs exclusive access to the template;
# pg_dump does not. These exercise the fallback and the diagnosis around it
# with the admin layer (asyncpg via the backend venv) and docker stubbed out,
# so no Postgres and no container are involved.
# --------------------------------------------------------------------------

BUSY = ('ObjectInUseError: source database "lingua_v2" is being accessed by '
        'other users There are 8 other sessions using the database.')

SESSION_ROWS = (
    "24812\tlingua\tpgAdmin 4 - CONN:123\t172.18.0.1\tidle\t"
    "2026-09-02 10:11:12\tSELECT 1\n"
    "24813\tlingua\tuvicorn\t172.18.0.1\tidle in transaction\t"
    "2026-09-02 10:12:00\tSELECT * FROM lessons")


def tree_with_env(tmp_path: Path, url: str = BASE_DB_URL) -> Path:
    """A bare directory shaped like a worktree -- isolate_worktree_env only
    ever touches .env and the slot file, so no git is needed."""
    wt = tmp_path / "tree"
    wt.mkdir(parents=True)
    (wt / ".env").write_text(
        f"DATABASE_URL={url}\nREDIS_DB=0\n", encoding="utf-8")
    return wt


class FakeAdmin:
    """Stands in for pg_admin(): scripted answers + a call log."""

    def __init__(self, template_ok=True, empty_ok=True, sessions=SESSION_ROWS):
        self.template_ok, self.empty_ok, self.sessions = template_ok, empty_ok, sessions
        self.calls: list[tuple] = []

    def __call__(self, repo, url, action, name, template=""):
        self.calls.append((action, name, template))
        if action == "sessions":
            return True, self.sessions
        if action == "drop":
            return True, "DROPPED"
        if template:
            return (True, "CREATED") if self.template_ok else (False, BUSY)
        return (True, "CREATED") if self.empty_ok else (False, "no space left")


def fake_docker(ps_lines: str, exec_rc: int = 0, log: list | None = None,
                counts=("7", "7")):
    """Stands in for run(): answers `docker ps` and `docker exec`.

    `counts` are the public-table counts pg_dump_copy compares afterwards --
    (source, target); equal means the copy is complete.
    """
    seen = []

    def _run(argv, cwd=None, check=False, stdin_text=None):
        if log is not None:
            log.append(argv)
        if argv[:2] == ["docker", "ps"]:
            return 0, ps_lines, ""
        if argv[:2] == ["docker", "exec"]:
            if "information_schema.tables" in argv[-1]:
                seen.append(argv[-1])
                return 0, counts[min(len(seen) - 1, 1)], ""
            return exec_rc, "", "" if exec_rc == 0 else "psql: FATAL: boom"
        raise AssertionError(f"unexpected command: {argv}")
    return _run


ONE_PG = "lingua_redis\tredis:7-alpine\nlingua_postgres\tpostgres:16-alpine"
TWO_PG = ONE_PG + "\nother_pg\tpostgres:15"


def test_busy_template_falls_back_to_pg_dump(tmp_path, monkeypatch, capsys):
    wt = tree_with_env(tmp_path)
    admin = FakeAdmin(template_ok=False)
    monkeypatch.setattr(wt_mod, "pg_admin", admin)
    monkeypatch.setattr(wt_mod, "run", fake_docker(ONE_PG))

    record, notes, failure = wt_mod.isolate_worktree_env(
        tmp_path, wt, "demo", 1, "copy")

    assert failure == ""
    assert record["isolation"] == "isolated"
    assert record["database"] == "lingua_v2_wt_demo"
    assert "lingua_v2_wt_demo" in (wt / ".env").read_text(
        encoding="utf-8")
    # the second create is the EMPTY one -- the fallback, not another template try
    assert ("create", "lingua_v2_wt_demo", "lingua_v2") in admin.calls
    assert ("create", "lingua_v2_wt_demo", "") in admin.calls
    # which path was taken is stated, never silent
    printed = capsys.readouterr().out + "\n".join(notes)
    assert "dump" in printed.lower() and "TEMPLATE" in printed


def test_busy_template_names_who_is_holding_the_database(tmp_path, monkeypatch, capsys):
    wt = tree_with_env(tmp_path)
    monkeypatch.setattr(wt_mod, "pg_admin", FakeAdmin(template_ok=False))
    monkeypatch.setattr(wt_mod, "run", fake_docker(ONE_PG))

    wt_mod.isolate_worktree_env(tmp_path, wt, "demo", 1, "copy")

    printed = capsys.readouterr().out
    assert "24812" in printed and "pgAdmin" in printed  # pg_stat_activity rows
    assert "172.18.0.1" in printed
    # the afternoon-costing detail: that address is the docker bridge, not a host PID
    assert "netstat -ano" in printed and "55432" in printed
    assert "bridge" in printed.lower()


def test_dump_fallback_hides_the_password_from_the_command_line(tmp_path, monkeypatch):
    wt = tree_with_env(tmp_path)
    log: list = []
    monkeypatch.setattr(wt_mod, "pg_admin", FakeAdmin(template_ok=False))
    monkeypatch.setattr(wt_mod, "run", fake_docker(ONE_PG, log=log))

    wt_mod.isolate_worktree_env(tmp_path, wt, "demo", 1, "copy")

    argv = next(a for a in log
                if a[:2] == ["docker", "exec"] and "pg_dump" in a[-1])
    assert "-e" in argv and "PGPASSWORD=pw" in argv
    script = argv[-1]
    assert "pw" not in script.replace("password", "")  # no password in the sh -c
    assert "pg_dump -U lingua -d lingua_v2 --no-owner --no-acl" in script
    assert "psql -q -v ON_ERROR_STOP=1 -U lingua -d lingua_v2_wt_demo" in script


def test_a_copy_that_did_not_land_everything_counts_as_a_failure(tmp_path,
                                                                 monkeypatch):
    """psql exits 0 on an empty input stream, so "the command worked" does not
    mean "the database was copied"."""
    wt = tree_with_env(tmp_path)
    admin = FakeAdmin(template_ok=False)
    monkeypatch.setattr(wt_mod, "pg_admin", admin)
    monkeypatch.setattr(wt_mod, "run", fake_docker(ONE_PG, counts=("7", "0")))

    record, _, failure = wt_mod.isolate_worktree_env(
        tmp_path, wt, "demo", 1, "copy")

    assert record["isolation"] == "failed"
    assert "incomplete" in failure
    assert ("drop", "lingua_v2_wt_demo", "") in admin.calls


def test_failed_dump_drops_the_target_and_fails_loudly(tmp_path, monkeypatch):
    wt = tree_with_env(tmp_path)
    admin = FakeAdmin(template_ok=False)
    monkeypatch.setattr(wt_mod, "pg_admin", admin)
    monkeypatch.setattr(wt_mod, "run", fake_docker(ONE_PG, exec_rc=1))

    record, notes, failure = wt_mod.isolate_worktree_env(
        tmp_path, wt, "demo", 1, "copy")

    assert failure and "dump" in failure.lower()
    assert record["isolation"] == "failed" and record["database"] == ""
    # a half-copied database left behind would make the retry silently wrong
    assert ("drop", "lingua_v2_wt_demo", "") in admin.calls
    assert "lingua_v2_wt_demo" in (wt / ".env").read_text(
        encoding="utf-8")


def test_container_detection_refuses_to_guess(tmp_path, monkeypatch):
    wt = tree_with_env(tmp_path)
    monkeypatch.setattr(wt_mod, "pg_admin", FakeAdmin(template_ok=False))
    monkeypatch.setattr(wt_mod, "run", fake_docker(TWO_PG))

    _, _, failure = wt_mod.isolate_worktree_env(tmp_path, wt, "demo", 1, "copy")

    assert "--pg-container" in failure
    assert "lingua_postgres" in failure and "other_pg" in failure


def test_explicit_pg_container_is_used_as_given(tmp_path, monkeypatch):
    wt = tree_with_env(tmp_path)
    log: list = []
    monkeypatch.setattr(wt_mod, "pg_admin", FakeAdmin(template_ok=False))
    monkeypatch.setattr(wt_mod, "run", fake_docker(TWO_PG, log=log))

    _, _, failure = wt_mod.isolate_worktree_env(
        tmp_path, wt, "demo", 1, "copy", pg_container="chosen_pg")

    assert failure == ""
    assert "chosen_pg" in next(a for a in log if a[:2] == ["docker", "exec"])


def test_empty_mode_failure_does_not_try_to_dump(tmp_path, monkeypatch):
    """--db empty asked for a fresh database, not a copy: there is nothing to
    fall back to, and pretending otherwise would copy data nobody asked for."""
    wt = tree_with_env(tmp_path)
    admin = FakeAdmin(empty_ok=False)
    monkeypatch.setattr(wt_mod, "pg_admin", admin)
    monkeypatch.setattr(wt_mod, "run", fake_docker(ONE_PG))

    record, _, failure = wt_mod.isolate_worktree_env(
        tmp_path, wt, "demo", 1, "empty")

    assert failure and record["isolation"] == "failed"
    assert [c for c in admin.calls if c[0] == "create"] == [
        ("create", "lingua_v2_wt_demo", "")]


def test_isolated_name_is_stable_across_retries():
    """A retry re-derives the name from a URL that already carries the suffix
    (the failed attempt rewrote it), and must not stack a second one."""
    once = wt_mod.worktree_db_name("lingua_v2", "demo")
    assert once == "lingua_v2_wt_demo"
    assert wt_mod.worktree_db_name(once, "demo") == once
    # a different tree's database is still a legitimate base name
    assert wt_mod.worktree_db_name("lingua_v2_wt_other", "demo") == \
        "lingua_v2_wt_other_wt_demo"


def load_sandbox_wt(sb: Sandbox, monkeypatch):
    """The sandbox copy of wt.py, imported so its admin layer can be stubbed.

    Imported rather than run as a subprocess because the command under test
    (`dbcreate`) is exactly the one that must talk to Postgres -- and it must
    be testable without one.
    """
    monkeypatch.setenv("WT_ROOT", str(sb.wt_root))
    return load_wt(sb.main / ".claude" / "scripts" / "wt.py")


def test_dbcreate_retries_the_isolation_step_in_place(sb: Sandbox, monkeypatch):
    """The "free the connections, then retry" path the failure message names:
    no new branch, no new worktree, no lost commits."""
    give_main_repo_env(sb)
    assert sb.wt("new", "demo").returncode == 3
    head_before = git(sb.wt_root / "demo", "rev-parse", "HEAD")

    mod = load_sandbox_wt(sb, monkeypatch)
    monkeypatch.setattr(mod, "pg_admin", FakeAdmin())
    args = mod.build_parser().parse_args(["dbcreate", "--slug", "demo"])
    assert args.func(args) == 0

    assert tree_db_url(sb, "demo").endswith("/lingua_v2_wt_demo")
    assert sb.slot("demo")["isolation"] == "isolated"
    assert sb.state()["worktrees"]["demo"]["database"] == "lingua_v2_wt_demo"
    assert git(sb.wt_root / "demo", "rev-parse", "HEAD") == head_before
    # and the tree stops reading as broken everywhere
    assert "ISOLATION FAILED" not in sb.wt("status").stdout
    assert sb.wt("doctor").returncode == 0
    assert "FORBIDDEN" not in sb.wt("prompt").stdout


def test_dbcreate_still_fails_loudly_when_the_cause_is_not_fixed(sb: Sandbox,
                                                                monkeypatch):
    give_main_repo_env(sb)
    sb.wt("new", "demo")

    mod = load_sandbox_wt(sb, monkeypatch)
    monkeypatch.setattr(mod, "pg_admin", lambda *a, **k: (False, "still busy"))
    args = mod.build_parser().parse_args(["dbcreate", "--slug", "demo"])
    assert args.func(args) == 3

    assert sb.slot("demo")["isolation"] == "failed"
    assert tree_db_url(sb, "demo").endswith("/lingua_v2_wt_demo")


def test_dbdrop_leaves_the_tree_marked_as_not_isolated(sb: Sandbox, monkeypatch):
    """After its database is dropped the tree is in exactly the R1 state: the
    .env names something that no longer exists. It must read that way too."""
    give_main_repo_env(sb)
    sb.wt("new", "demo")
    mod = load_sandbox_wt(sb, monkeypatch)
    monkeypatch.setattr(mod, "pg_admin", FakeAdmin())
    args = mod.build_parser().parse_args(["dbcreate", "--slug", "demo"])
    assert args.func(args) == 0

    drop = mod.build_parser().parse_args(
        ["dbdrop", "--slug", "demo", "--yes"])
    assert drop.func(drop) == 0

    entry = sb.state()["worktrees"]["demo"]
    assert entry["database"] == "" and entry["isolation"] == "failed"
    assert entry["intended_database"] == "lingua_v2_wt_demo"
    assert "ISOLATION FAILED" in sb.wt("status").stdout
    assert sb.wt("doctor").returncode == 3


def test_dbcreate_refuses_to_guess_between_two_trees(sb: Sandbox):
    give_main_repo_env(sb)
    sb.wt("new", "one")
    sb.wt("new", "two")

    r = sb.wt("dbcreate", cwd=sb.root)

    assert r.returncode == 3
    assert "--slug" in r.stderr


def test_non_busy_create_failure_is_not_dumped_over(tmp_path, monkeypatch):
    """Only "the template is in use" has a dump-shaped answer. Anything else
    (no venv, bad credentials, disk full) must surface as itself."""
    wt = tree_with_env(tmp_path)
    admin = FakeAdmin()
    monkeypatch.setattr(wt_mod, "pg_admin",
                        lambda *a, **k: (False, "backend venv not found"))
    monkeypatch.setattr(wt_mod, "run", fake_docker(ONE_PG))

    _, _, failure = wt_mod.isolate_worktree_env(tmp_path, wt, "demo", 1, "copy")

    assert "venv" in failure
