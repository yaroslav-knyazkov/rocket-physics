#!/usr/bin/env python3
"""
wt.py -- git worktree lifecycle for the agent team.

Project settings: .claude/wt.config.json (see wt.config.example.json).

Model: one worktree == one task/stage. The orchestrator AND every subagent
work inside that worktree; the base branch stays checked out only in the main
repo and is never edited directly. Every commit is pushed immediately.

    new <slug>      create branch wt/<slug> from origin/<base>, add worktree, push -u
    status          compact state: worktree, base, ahead/behind, dirty, stray edits
    sync            fetch + rebase onto origin/<base> + leased force-push
    commit -m "..." add -A + commit + push, inside the worktree
    land            merge --no-ff into base, push base, remove worktree + branches
    drop            abandon a worktree without landing
    doctor          stray edits in the main repo, state/worktree consistency
    list            all worktrees
    prompt          delegation block to paste into subagent prompts
    dbcreate        (re)create the isolated database of an existing worktree
    dbdrop          drop the isolated database of a worktree (explicit, opt-in)

Parallel worktrees are supported: several may be active at once. Each gets a
slot (1..9) and with it its own backend/frontend ports, redis db index and
Postgres database (when the project has one), so dev servers, tests and
migrations in one tree cannot reach into another. Commands never guess which tree you mean -- the slug comes from
the cwd, or from --slug when the cwd is outside every worktree.

Isolation never degrades. `new --db copy|empty` either gives the tree its own
database or FAILS (exit 3) with the tree parked and its DATABASE_URL pointing
at the database that does not exist -- never at the base one. Silently falling
back to sharing is what let `alembic downgrade -1` inside a "worktree" drop a
table from the user's working database. `--db share` remains a
legitimate, explicitly marked choice; `dbcreate` retries the isolation step
after the cause is fixed.

Exit codes: 0 ok | 1 usage/internal | 2 manual work needed (conflicts) |
            3 precondition failed (dirty tree, not rebased, unpushed, ...)

Read-only commands: status, doctor, list, prompt. Everything else mutates git.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

# Project-specific settings live in .claude/wt.config.json (optional; every key
# has a default below). See wt.config.example.json for the annotated shape.
CONFIG_PATH = Path(__file__).resolve().parent.parent / "wt.config.json"


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"[wt] cannot read {CONFIG_PATH}: {exc}\n")
        sys.exit(1)


CONFIG = _load_config()

BRANCH_PREFIX = "wt/"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,60}$")
CO_AUTHOR = CONFIG.get("co_author",
                       "Co-Authored-By: Claude <noreply@anthropic.com>")

# Paths inside the main repo that agents may still touch while a worktree is
# active. Everything here is gitignored scratch, not project source.
MAIN_REPO_ALLOWLIST = tuple(CONFIG.get("main_repo_allowlist", (
    "graphify-out/",
    "temporary/",
    ".claude/wt-active.json",
    "dev/.status-backup/",
    "dev/.docs-backup/",
)))

# Gitignored local environment a fresh worktree does not get from git but
# cannot run without. "junction" = directory junction on Windows / symlink
# elsewhere (no admin rights needed, no 170 MB copy); "copy" = real copy, for
# small secret-bearing files. Missing sources are skipped silently.
LOCAL_ARTIFACTS = tuple(tuple(x) for x in CONFIG.get("local_artifacts", (
    ("node_modules", "junction"),
    (".venv", "junction"),
    (".env", "copy"),
)))

# The .env whose DATABASE_URL (Postgres only) gets an isolated per-tree
# database, REDIS_DB index and port rewrite. No such file / no Postgres URL ->
# the tree gets ports only, no database isolation.
ENV_FILE = CONFIG.get("env_file", ".env")
# Virtualenv used to run asyncpg for CREATE/DROP DATABASE.
VENV_DIR = CONFIG.get("venv_dir", ".venv")

SECRET_PATTERNS = (
    re.compile(r"(^|/)\.env(\.[^/]*)?$"),
    re.compile(r"(^|/)[^/]*\.local\.json$"),
    re.compile(r"\.(pem|p12|pfx|key)$"),
    re.compile(r"(^|/)id_(rsa|ed25519)$"),
)
SECRET_ALLOW = re.compile(r"\.example$|\.sample$|\.template$")

BIG_FILE_BYTES = 5 * 1024 * 1024

# --- parallel worktrees: resource isolation -------------------------------
# Slot 0 is the main repo (base ports, redis db 0, DATABASE_URL as written in
# the env file). Each worktree takes a free slot and gets its own ports, redis db and
# database, because the shared ones are actively destructive across trees:
# a dev server may kill whatever holds its port, and a migration
# rewrites the schema every other tree is testing against.
SLOT_MIN, SLOT_MAX = 1, 9
BACKEND_PORT_BASE = int(CONFIG.get("backend_port_base", 8000))
FRONTEND_PORT_BASE = int(CONFIG.get("frontend_port_base", 3000))
PORT_STRIDE = int(CONFIG.get("port_stride", 10))
SLOT_FILE = ".wt-slot.json"          # written into the worktree root, gitignored

# How isolated is a tree's database? Recorded in .wt-slot.json and in the state
# file, because "not isolated" has to be visible in status/doctor/prompt rather
# than inferred from an empty name (see the 2026-09-02 incident in the header).
ISOLATION_ISOLATED = "isolated"      # own database, created and reachable
ISOLATION_SHARE = "share"            # --db share: deliberate, migrations banned
ISOLATION_FAILED = "failed"          # asked for isolation, did not get it
ISOLATION_NO_ENV = "no-env"          # no env file / no Postgres URL: no database

# Trackers live in the MAIN repo and are committed there right away
# (git commit --only <paths>). Every task edits them, so a copy inside a
# worktree conflicts on every sync -- refuse to commit them from a worktree.
TRACKER_FILES = tuple(CONFIG.get(
    "tracker_files", ("dev/status.json", "dev/journal.md", "dev/PROJECT-STATUS.md")))


# --------------------------------------------------------------------------
# process helpers
# --------------------------------------------------------------------------


def run(args: list[str], cwd: Path | None = None, check: bool = False,
        stdin_text: str | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        die(f"command failed: {' '.join(args)}\n{proc.stderr.strip()}")
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def git(args: list[str], cwd: Path, check: bool = False,
        stdin_text: str | None = None) -> tuple[int, str, str]:
    return run(["git", "-C", str(cwd), *args], check=check, stdin_text=stdin_text)


def out(msg: str = "") -> None:
    print(msg)


def die(msg: str, code: int = 1) -> "None":
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


# --------------------------------------------------------------------------
# repo / state discovery
# --------------------------------------------------------------------------


def main_repo() -> Path:
    """Main repo root, even when this script copy lives inside a worktree.

    `git rev-parse --git-common-dir` points at <main>/.git from any worktree.
    """
    here = Path(__file__).resolve().parent
    rc, common, err = run(["git", "-C", str(here), "rev-parse",
                           "--path-format=absolute", "--git-common-dir"])
    if rc != 0:
        die(f"not inside a git repository: {err}")
    return Path(common).parent.resolve()


def wt_root(repo: Path) -> Path:
    env = os.environ.get("WT_ROOT")
    if env:
        return Path(env)
    cfg = CONFIG.get("worktree_root")
    if cfg:
        return Path(cfg).expanduser()
    # Default: a sibling folder <repo>-worktrees, outside the repo tree (and
    # outside a cloud-synced project folder only if you configure it so).
    return repo.parent / f"{repo.name}-worktrees"


def state_path(repo: Path) -> Path:
    return repo / ".claude" / "wt-active.json"


def load_state(repo: Path) -> dict:
    p = state_path(repo)
    if not p.exists():
        return {"current": None, "worktrees": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"current": None, "worktrees": {}}
    data.setdefault("current", None)
    data.setdefault("worktrees", {})
    return data


def save_state(repo: Path, state: dict) -> None:
    p = state_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not state.get("worktrees"):
        if p.exists():
            p.unlink()
        return
    if state.get("current") not in state["worktrees"]:
        state["current"] = next(iter(state["worktrees"]), None)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")


def resolve_slug(repo: Path, explicit: str | None) -> str:
    """Which worktree does this command act on?

    Never falls back to "the last created one" when several are active: with
    parallel trees that silently commits tree B under tree A's message. Order:
    explicit --slug, then the tree containing the cwd, then the only tree.
    """
    state = load_state(repo)
    wts = state["worktrees"]
    if not wts:
        die("no active worktree. Create one: python .claude/scripts/wt.py new <slug>", 3)
    if explicit:
        if explicit not in wts:
            die(f"unknown slug {explicit!r}. Active: {', '.join(sorted(wts))}", 3)
        return explicit
    cwd = Path.cwd().resolve()
    for slug, e in wts.items():
        wp = Path(e["path"]).resolve()
        if cwd == wp or wp in cwd.parents:
            return slug
    if len(wts) == 1:
        return next(iter(wts))
    die(f"{len(wts)} worktrees active and the cwd is outside all of them -- "
        f"pass --slug (one of: {', '.join(sorted(wts))})", 3)


def active_entry(repo: Path, slug: str | None = None) -> dict:
    state = load_state(repo)
    slug = resolve_slug(repo, slug)
    entry = dict(state["worktrees"][slug])
    entry["slug"] = slug
    return entry


# --------------------------------------------------------------------------
# git predicates
# --------------------------------------------------------------------------


def current_branch(cwd: Path) -> str:
    _, name, _ = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return name


def dirty_files(cwd: Path) -> list[str]:
    _, o, _ = git(["status", "--porcelain"], cwd)
    return [ln for ln in o.splitlines() if ln.strip()]


def count_commits(cwd: Path, rng: str) -> int:
    rc, o, _ = git(["rev-list", "--count", rng], cwd)
    return int(o) if rc == 0 and o.isdigit() else -1


def branch_exists(cwd: Path, branch: str) -> bool:
    rc, _, _ = git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd)
    return rc == 0


def remote_branch_exists(cwd: Path, branch: str) -> bool:
    rc, o, _ = git(["ls-remote", "--heads", "origin", branch], cwd)
    return rc == 0 and bool(o)


def remote_sha(cwd: Path, branch: str) -> str:
    """What this worktree currently BELIEVES origin/<branch> is.

    The remote-tracking ref, not the remote itself: that belief is exactly the
    value a force-push lease has to be pinned to.
    """
    rc, o, _ = git(["rev-parse", "--verify", "--quiet",
                    f"refs/remotes/origin/{branch}"], cwd)
    return o if rc == 0 else ""


def git_version(cwd: Path) -> tuple[int, int]:
    """(major, minor) of the git binary, or (0, 0) when it cannot be parsed."""
    _, o, _ = git(["--version"], cwd)
    m = re.search(r"(\d+)\.(\d+)", o)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def reflog_tips(cwd: Path, branch: str, limit: int = 200) -> set[str]:
    """Every sha the local branch has pointed at, newest entries first.

    The window is finite (and git expires reflogs after 90 days), so a very old
    tip can fall out of it. That only ever makes the caller refuse a push it
    could have allowed -- the safe direction, and the refusal spells out the
    manual command.
    """
    rc, o, _ = git(["rev-list", "--walk-reflogs", f"--max-count={limit}", branch], cwd)
    return set(o.split()) if rc == 0 else set()


def origin_tip_is_ours(cwd: Path, branch: str, tip: str) -> bool:
    """Is the commit origin/<branch> points at one THIS worktree published?

    The question --force-if-includes answers from the reflog: a tip that was
    HEAD here at some point is ours to rewrite -- that is exactly what a rebase
    does -- while a tip that never was belongs to a second writer and must not
    be forced over. Hand-rolled because the flag needs git >= 2.30 and, as
    measured on git 2.55, is silently a no-op as soon as --force-with-lease
    carries an explicit <expect> value.
    """
    return bool(tip) and tip in reflog_tips(cwd, branch)


def force_push_refused(cwd: Path, branch: str, reason: str) -> str:
    """Refusal text that names the next command instead of "use --force".

    "Someone moved it, inspect before forcing" leaves the operator with no
    command to run and invites a blind --force, which is how the commits get
    lost in the first place.
    """
    p = str(cwd).replace(chr(92), "/")
    return (
        f"refused to force-push {branch} -- nothing was overwritten.\n"
        f"reason: {reason}\n"
        f"Look at what is on origin first:\n"
        f"  git -C {p} fetch origin {branch}\n"
        f"  git -C {p} log --oneline HEAD..origin/{branch}\n"
        f"Then EITHER integrate that work:\n"
        f"  git -C {p} rebase origin/{branch}   # then re-run wt.py sync\n"
        f"OR discard it deliberately, naming the sha you are throwing away:\n"
        f"  git -C {p} push --force-with-lease={branch}:<their sha> origin {branch}"
    )


def push_leased(path: Path, branch: str, expected: str) -> tuple[bool, str]:
    """Force-push <branch>, refusing whenever origin holds work that is not ours.

    Three layers, because no single one covers every sequence:

    1. `expected` is what origin/<branch> was BEFORE this command fetched
       anything. If the ref moved since, a second writer pushed and we stop --
       this is the case a bare --force-with-lease cannot see, since the fetch
       one line earlier already taught the lease their sha.
    2. If origin is ahead of us, its tip must be a commit this worktree
       published earlier (our own pre-rebase tip), not a stranger's commit.
       This covers the sequence where we DID fetch their work (`wt.py status`
       runs a fetch) and would otherwise consider our belief up to date.
    3. The push keeps a lease, so the seconds between check and push are
       covered too: bare lease + --force-if-includes on git >= 2.30, because
       that pair is what makes git itself enforce the reflog rule; an explicit
       <expect> on older git, where the two checks above carry the weight.

    Returns (pushed, refusal text).
    """
    actual = remote_sha(path, branch)
    if expected and actual and actual != expected:
        return False, force_push_refused(
            path, branch,
            f"origin/{branch} moved from {expected[:8]} to {actual[:8]} since this "
            f"worktree last looked at it -- a second writer pushed")
    ahead_of_us = count_commits(path, f"HEAD..origin/{branch}")
    if ahead_of_us > 0 and not origin_tip_is_ours(path, branch, actual):
        return False, force_push_refused(
            path, branch,
            f"{ahead_of_us} commit(s) on origin/{branch} were never HEAD in this "
            f"worktree, so they are somebody else's work, not a rewrite of ours")

    if git_version(path) >= (2, 30):
        flags = ["--force-with-lease", "--force-if-includes"]
    else:
        flags = [f"--force-with-lease={branch}:{actual}"] if actual \
            else ["--force-with-lease"]
    rc, _, err = git(["push", *flags, "origin", branch], path)
    return (True, "") if rc == 0 else (False, force_push_refused(path, branch, err))


def rebase_in_progress(cwd: Path) -> bool:
    _, gd, _ = git(["rev-parse", "--path-format=absolute", "--git-dir"], cwd)
    if not gd:
        return False
    g = Path(gd)
    return (g / "rebase-merge").exists() or (g / "rebase-apply").exists()


def conflicted_files(cwd: Path) -> list[str]:
    _, o, _ = git(["diff", "--name-only", "--diff-filter=U"], cwd)
    return [ln for ln in o.splitlines() if ln.strip()]


def link_local_artifacts(repo: Path, wt: Path, isolate: bool = False) -> list[str]:
    """Wire the fresh worktree to the local env git does not carry.

    isolate=True skips the junctions: node_modules/.venv are shared through
    them, so `npm install` in a tree whose package.json differs silently
    re-installs the dependencies of every other tree.
    """
    notes = []
    for rel, mode in LOCAL_ARTIFACTS:
        src, dst = repo / rel, wt / rel
        if isolate and mode == "junction":
            notes.append(f"{rel}: NOT linked (--isolate) -- install it in the worktree")
            continue
        if not src.exists():
            continue
        if dst.exists():
            notes.append(f"{rel}: already present, skipped")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "junction":
            if os.name == "nt":
                rc, _, err = run(["cmd", "/c", "mklink", "/J", str(dst), str(src)])
            else:
                try:
                    os.symlink(src, dst, target_is_directory=True)
                    rc, err = 0, ""
                except OSError as exc:
                    rc, err = 1, str(exc)
            notes.append(f"{rel}: junction -> main repo" if rc == 0
                         else f"{rel}: JUNCTION FAILED ({err or 'see mklink'}) "
                              f"-- install deps in the worktree manually")
        else:
            try:
                dst.write_bytes(src.read_bytes())
                notes.append(f"{rel}: copied")
            except OSError as exc:
                notes.append(f"{rel}: COPY FAILED ({exc})")
    return notes


def unlink_local_artifacts(wt: Path) -> None:
    """Drop junctions before `git worktree remove`.

    os.rmdir on a junction removes the link only; on a real non-empty
    directory it raises -- so this can never eat the shared node_modules.
    """
    for rel, mode in LOCAL_ARTIFACTS:
        if mode != "junction":
            continue
        p = wt / rel
        try:
            if p.is_symlink():
                p.unlink()
            else:
                os.rmdir(p)
        except OSError:
            pass


# --------------------------------------------------------------------------
# resource isolation (ports / redis db / postgres database)
# --------------------------------------------------------------------------

PG_URL_RE = re.compile(
    r"^(?P<scheme>[a-zA-Z0-9+]+)://(?P<rest>[^/]*)/(?P<db>[^/?]+)(?P<tail>\?.*)?$")

# Actions: create / drop / sessions. Failures print a single machine-readable
# ERR| line and exit non-zero, because the CALLER has to tell "the template is
# busy" (recoverable: dump instead) from everything else -- and asyncpg keeps
# the interesting half ("There are 8 other sessions ...") in exc.detail, not in
# str(exc).
PG_ADMIN_SNIPPET = """
import asyncio, sys, asyncpg

SESSIONS_SQL = '''
SELECT pid,
       coalesce(usename, '?') AS usename,
       coalesce(nullif(application_name, ''), '-') AS application_name,
       coalesce(host(client_addr), 'local') AS client_addr,
       coalesce(state, '-') AS state,
       to_char(backend_start, 'YYYY-MM-DD HH24:MI') AS backend_start,
       left(translate(coalesce(query, ''), chr(10) || chr(13) || chr(9), '   '), 60)
FROM pg_stat_activity
WHERE datname = $1 AND pid <> pg_backend_pid()
ORDER BY backend_start
'''

async def main():
    url, action, name, template = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    conn = await asyncpg.connect(url)
    try:
        if action == 'create':
            exists = await conn.fetchval(
                'SELECT 1 FROM pg_database WHERE datname = $1', name)
            if exists:
                print('EXISTS'); return
            sql = 'CREATE DATABASE "%s"' % name
            if template:
                sql += ' TEMPLATE "%s"' % template
            await conn.execute(sql)
            print('CREATED')
        elif action == 'sessions':
            for row in await conn.fetch(SESSIONS_SQL, name):
                print('\\t'.join(str(v) for v in row))
        else:
            await conn.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = $1 AND pid <> pg_backend_pid()', name)
            await conn.execute('DROP DATABASE IF EXISTS "%s"' % name)
            print('DROPPED')
    finally:
        await conn.close()

try:
    asyncio.run(main())
except Exception as exc:
    detail = getattr(exc, 'detail', '') or ''
    print('ERR|%s|%s|%s' % (type(exc).__name__,
                            str(exc).replace('\\n', ' '),
                            str(detail).replace('\\n', ' ')))
    sys.exit(9)
"""

# Docker image names that mean "this container is the Postgres server".
PG_IMAGE_PREFIX = "postgres"


def slot_ports(slot: int) -> tuple[int, int]:
    return (BACKEND_PORT_BASE + PORT_STRIDE * slot,
            FRONTEND_PORT_BASE + PORT_STRIDE * slot)


def free_slot(state: dict) -> int:
    used = {e.get("slot") for e in state["worktrees"].values()}
    for n in range(SLOT_MIN, SLOT_MAX + 1):
        if n not in used:
            return n
    die(f"all {SLOT_MAX} slots are taken -- land or drop a worktree first", 3)


def env_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def env_get(lines: list[str], key: str) -> str | None:
    for ln in lines:
        if ln.strip().startswith(f"{key}="):
            return ln.split("=", 1)[1].strip()
    return None


def env_set(lines: list[str], key: str, value: str) -> list[str]:
    hit = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"{key}="):
            lines[i], hit = f"{key}={value}", True
    if not hit:
        lines.append(f"{key}={value}")
    return lines


def split_pg_url(url: str) -> tuple[str, str, str] | None:
    """(prefix, database, tail) -- prefix keeps scheme+credentials+host."""
    m = PG_URL_RE.match(url or "")
    if not m:
        return None
    return (f"{m.group('scheme')}://{m.group('rest')}", m.group("db"),
            m.group("tail") or "")


def admin_pg_url(url: str) -> str | None:
    """Same server, database `postgres`, driverless scheme for asyncpg."""
    parts = split_pg_url(url)
    if not parts:
        return None
    prefix, _, _ = parts
    scheme, rest = prefix.split("://", 1)
    return f"{scheme.split('+')[0]}://{rest}/postgres"


def venv_python(repo: Path) -> Path | None:
    for rel in (f"{VENV_DIR}/Scripts/python.exe", f"{VENV_DIR}/bin/python"):
        cand = repo / rel
        if cand.exists():
            return cand
    return None


def pg_credentials(url: str) -> tuple[str, str]:
    """(user, password) out of a Postgres URL, percent-decoding both."""
    parts = split_pg_url(url)
    if not parts:
        return "", ""
    rest = parts[0].split("://", 1)[1]
    if "@" not in rest:
        return "", ""
    creds = rest.rsplit("@", 1)[0]
    user, _, password = creds.partition(":")
    return unquote(user), unquote(password)


def pg_admin(repo: Path, url: str, action: str, name: str,
             template: str = "") -> tuple[bool, str]:
    """CREATE/DROP DATABASE or list sessions through the backend venv.

    (no psql on PATH here -- asyncpg from the project venv is the only client
    this machine has outside the container.) On failure the message keeps the
    exception class AND asyncpg's `detail`, because the "8 other sessions"
    sentence lives only in the latter and is what `create_isolated_database`
    branches on.
    """
    py = venv_python(repo)
    if not py:
        return False, "backend venv not found"
    admin = admin_pg_url(url)
    if not admin:
        return False, f"cannot parse DATABASE_URL ({url[:24]}...)"
    rc, o, err = run([str(py), "-c", PG_ADMIN_SNIPPET, admin, action, name, template])
    if rc != 0:
        for line in reversed(o.splitlines()):
            if line.startswith("ERR|"):
                _, cls, msg, detail = (line.split("|", 3) + ["", "", ""])[:4]
                return False, f"{cls}: {msg} {detail}".strip()[:300]
        return False, (err.splitlines() or ["failed"])[-1][:160]
    # "no sessions" is empty output and a real answer; only the create/drop
    # actions have a default word for "it worked".
    return True, o.strip() or ("" if action == "sessions" else "ok")


def template_is_busy(msg: str) -> bool:
    """Is this the one create failure that a dump can work around?

    `CREATE DATABASE ... TEMPLATE x` demands that nobody else is connected to
    x; pg_dump has no such requirement. Everything else (no venv, bad
    credentials, no disk) has to surface as itself.
    """
    low = msg.lower()
    return ("objectinuseerror" in low or "other session" in low
            or "being accessed by other users" in low)


def docker_pg_container(explicit: str | None = None) -> tuple[str, str]:
    """(container name, error). Never guesses between two candidates."""
    if explicit:
        return explicit, ""
    rc, o, err = run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"])
    if rc != 0:
        first = (err or o or "docker not available").splitlines()[0][:160]
        return "", (f"docker is not usable here ({first}) -- name the container "
                    f"with --pg-container <name> if it runs elsewhere")
    hits = []
    for line in o.splitlines():
        name, _, image = line.partition("\t")
        # ghcr.io/foo/postgres:16 -> postgres:16
        if image.rsplit("/", 1)[-1].startswith(PG_IMAGE_PREFIX):
            hits.append(name.strip())
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return "", ("no running container with a postgres image "
                    "(docker ps) -- pass --pg-container <name>")
    return "", (f"{len(hits)} containers with a postgres image "
                f"({', '.join(hits)}) -- refusing to guess, "
                f"pass --pg-container <name>")


def docker_psql(container: str, password: str, script: str) -> tuple[int, str, str]:
    """Run a shell command in the Postgres container.

    The password travels in the `docker exec` environment (`-e PGPASSWORD=`),
    never inside `script`: whatever is in the script ends up in the container's
    process list, where a password has no business being.
    """
    return run(["docker", "exec", "-e", f"PGPASSWORD={password}",
                container, "sh", "-c", script])


def pg_table_count(container: str, user: str, password: str,
                   db: str) -> int | None:
    """Tables in public.<db>, or None if the question could not be answered."""
    rc, o, _ = docker_psql(
        container, password,
        f"psql -tAq -U {user} -d {db} -c \"SELECT count(*) FROM "
        f"information_schema.tables WHERE table_schema = 'public'\"")
    o = o.strip()
    return int(o) if rc == 0 and o.isdigit() else None


def pg_dump_copy(url: str, base_db: str, target: str,
                 container: str) -> tuple[bool, str]:
    """Copy base_db into target with pg_dump | psql INSIDE the container.

    The host has neither pg_dump nor psql, and -- the reason this path exists
    at all -- unlike `CREATE DATABASE ... TEMPLATE` this needs no exclusive
    access to the source.

    Two deliberate additions to the invocation verified by hand on 2026-09-03:

    * `-v ON_ERROR_STOP=1`, because psql otherwise exits 0 after reporting
      errors on individual statements, and "the copy exited non-zero" is the
      only signal the caller has. Without it a half-restored database would be
      handed over as isolated -- the same "looks fine, is not" failure this
      whole guard exists to remove. `set -o pipefail` is NOT used instead: it
      is a busybox/bash feature and would break outright on a dash-based
      (debian) postgres image.
    * a table count compared against the source afterwards, which is what
      actually catches a pg_dump that produced nothing (an empty stream still
      makes psql exit 0).
    """
    user, password = pg_credentials(url)
    if not user:
        return False, f"no user in DATABASE_URL, cannot run pg_dump ({url[:24]}...)"
    script = (f"pg_dump -U {user} -d {base_db} --no-owner --no-acl "
              f"| psql -q -v ON_ERROR_STOP=1 -U {user} -d {target}")
    rc, o, err = docker_psql(container, password, script)
    if rc != 0:
        tail = (err or o or "see docker").splitlines()
        return False, f"pg_dump | psql in {container} failed: {tail[-1][:160]}"

    src, dst = (pg_table_count(container, user, password, base_db),
                pg_table_count(container, user, password, target))
    if src is None or dst is None:
        return False, (f"the copy reported success but its result could not be "
                       f"verified in {container} (table count unreadable) -- "
                       f"treating that as a failure, not as a copy")
    if dst != src:
        return False, (f"the copy reported success but {target} has {dst} public "
                       f"table(s) against {src} in {base_db} -- incomplete")
    return True, ""


def report_busy_sessions(repo: Path, url: str, base_db: str) -> None:
    """Name who is holding base_db open, and pre-empt the wrong hunt for them.

    client_addr is the docker bridge gateway for every client outside the
    container, so it identifies nothing on its own -- an afternoon was lost to
    reading it as a host address before the netstat line below existed.
    """
    ok, rows = pg_admin(repo, url, "sessions", base_db)
    out(f"database: {base_db} is held open by other sessions -- "
        f"CREATE DATABASE ... TEMPLATE needs it idle:")
    if not ok:
        out(f"    (could not read pg_stat_activity: {rows})")
    elif not rows.strip():
        out("    (pg_stat_activity is empty now -- the holder may have just left; "
            "retry with wt.py dbcreate)")
    else:
        header = ("pid", "user", "application", "client_addr", "state",
                  "since", "query")
        out("    " + " | ".join(header))
        for line in rows.splitlines():
            out("    " + " | ".join(line.split("\t")))
    out("    NOTE: client_addr is the docker bridge gateway (172.x.0.1), NOT a "
        "host process -- every client outside the container shows up as that "
        "one address.")
    out("    To find the host process holding it: "
        "netstat -ano | findstr :55432, match the local port to a PID, then "
        "tasklist /FI \"PID eq <pid>\".")


def base_db_name(db: str, slug: str) -> str:
    """Strip this slug's `_wt_<slug>` suffix, if the name already carries it.

    Retries matter here: after a failed isolation the tree's DATABASE_URL names
    the database that was never created, so a second attempt re-derives the
    name from `<base>_wt_<slug>` and would otherwise ask for
    `<base>_wt_<slug>_wt_<slug>` -- against a template that does not exist.
    """
    safe = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    if db.endswith(f"_wt_{safe}"):
        return db[: -len(f"_wt_{safe}")]
    # Same thing after the 63-char truncation below cut the slug short.
    head, sep, tail = db.rpartition("_wt_")
    if sep and tail and safe.startswith(tail):
        return head
    return db


def worktree_db_name(base_db: str, slug: str) -> str:
    """The database a tree with this slug owns. Postgres caps identifiers at 63."""
    safe = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    return f"{base_db_name(base_db, slug)}_wt_{safe}"[:63]


def create_isolated_database(repo: Path, url: str, base_db: str, target: str,
                             db_mode: str, pg_container: str | None = None
                             ) -> tuple[bool, str, list[str]]:
    """Create <target>, as a copy of <base_db> or empty.

    Returns (ok, failure reason, notes). Never degrades: a caller that asked
    for isolation and gets ok=False must treat the tree as unusable.
    """
    template = base_db if db_mode == "copy" else ""
    ok, msg = pg_admin(repo, url, "create", target, template)
    if ok:
        how = f"TEMPLATE {base_db}" if template else "empty"
        notes = [f"database: {target} ({msg.lower()}, {how})"]
        if msg == "CREATED" and not template:
            notes.append("database: empty -- run `alembic upgrade head` "
                         "in the worktree")
        return True, "", notes
    if not (template and template_is_busy(msg)):
        return False, msg, [f"database: NOT created ({msg})"]

    # --- fallback: dump instead of TEMPLATE ------------------------------
    report_busy_sessions(repo, url, base_db)
    container, err = docker_pg_container(pg_container)
    if not container:
        return False, f"template {base_db} is in use and {err}", [
            "database: NOT created (template busy, no usable container)"]

    ok, msg = pg_admin(repo, url, "create", target, "")
    if not ok:
        return False, f"template busy, and the empty target failed too: {msg}", [
            f"database: NOT created ({msg})"]
    if msg == "EXISTS":
        return False, (
            f"{target} already exists, so a dump into it would merge with "
            f"whatever is in there. Drop it first: python .claude/scripts/wt.py "
            f"dbdrop --database {target} --yes"), [
            f"database: NOT created ({target} already exists)"]

    out(f"database: copying {base_db} -> {target} with pg_dump | psql inside "
        f"{container} (TEMPLATE was refused; this path does not need the "
        f"template idle)...")
    ok, err = pg_dump_copy(url, base_db, target, container)
    if not ok:
        # A half-populated database is worse than none: the retry would look
        # like it worked. Take it back down.
        dropped, dmsg = pg_admin(repo, url, "drop", target)
        return False, err, [
            "database: NOT created (dump copy failed)",
            f"database: {target} dropped again"
            + ("" if dropped else f" -- DROP ALSO FAILED ({dmsg}), remove it by hand")]
    return True, "", [f"database: {target} (created empty, then copied from "
                      f"{base_db} with pg_dump | psql in {container} -- "
                      f"NOT TEMPLATE, which the busy template refused)"]


def isolation_failure_report(slug: str, wt_path: Path, intended: str,
                             reason: str, db_mode: str) -> list[str]:
    """What broke, what state the tree is in, and the two ways out.

    Printed instead of the delegation block: a tree whose database was never
    created must not look like a tree that is ready for agents.
    """
    p = str(wt_path).replace(chr(92), "/")
    lines = [
        f"ISOLATION FAILED -- the worktree {slug} has NO database of its own.",
        f"  reason: {reason}",
        f"  intended database: {intended or '<name could not be derived>'} "
        f"(does not exist)",
        "",
        f"The tree is left on disk, but parked: its {ENV_FILE} now points at "
        "that non-existent database, so anything connecting from it fails with "
        '\'database "..." does not exist\' instead of quietly reaching the main '
        "database. Do NOT edit that URL back -- running alembic against the main "
        "database is exactly how a table was dropped from it on 2026-09-02.",
        "",
        "Next, either fix the cause and retry the isolation step in place:",
        f"  python .claude/scripts/wt.py dbcreate --slug {slug} --db {db_mode}",
        "or abandon the tree:",
        f"  python .claude/scripts/wt.py drop --slug {slug}",
        f"(worktree: {p})",
    ]
    return lines


def isolate_worktree_env(repo: Path, wt: Path, slug: str, slot: int,
                         db_mode: str, pg_container: str | None = None
                         ) -> tuple[dict, list[str], str]:
    """Give the worktree its own ports / redis db / database.

    Returns (slot record, human notes, failure reason). A non-empty failure
    means isolation was requested and NOT achieved -- the caller must fail,
    not carry on: carrying on is what left a tree pointing at the user's
    working database on 2026-09-02.

    The record is also written to <worktree>/.wt-slot.json so run.py and vite
    pick the ports up without knowing anything about wt.py.
    """
    bp, fp = slot_ports(slot)
    notes: list[str] = []
    failure = ""
    env_path = wt / ENV_FILE
    lines = env_lines(env_path)
    database = intended = ""
    mode = ISOLATION_NO_ENV

    if not lines:
        notes.append(f"{ENV_FILE} missing in the worktree -- ports only, "
                     "no db/redis isolation")
    else:
        if db_mode == "share":
            mode = ISOLATION_SHARE
            notes.append("database: SHARED with the main repo (--db share) -- "
                         "alembic and destructive SQL are forbidden in this tree")
        else:
            url = env_get(lines, "DATABASE_URL") or ""
            parts = split_pg_url(url)
            if not url.lower().startswith("postgres"):
                # No Postgres in this project (no URL, sqlite, ...): nothing to
                # isolate at the database level -- ports/redis only.
                notes.append("database: no Postgres DATABASE_URL -- no db isolation")
            elif not parts:
                mode, failure = ISOLATION_FAILED, (
                    f"DATABASE_URL in {env_path} cannot be parsed, so the isolated "
                    f"database name cannot even be derived")
                # Blanked rather than left as is: an unparseable URL is still a
                # URL, and the env file of a worktree is the last thing that
                # should keep pointing wherever the main repo pointed.
                lines = env_set(lines, "DATABASE_URL", "")
                notes.append("database: DATABASE_URL unparseable, blanked")
            else:
                prefix, url_db, tail = parts
                # On a retry the URL already names the database that was never
                # created, so the base has to be recovered from it, not taken
                # as is -- otherwise the template would be a phantom too.
                base_db = base_db_name(url_db, slug)
                intended = worktree_db_name(base_db, slug)
                ok, reason, db_notes = create_isolated_database(
                    repo, url, base_db, intended, db_mode, pg_container)
                notes += db_notes
                # Repointed on BOTH paths. On the failure path this is the whole
                # point: the name does not resolve, so every connection from the
                # tree fails loudly instead of landing on the base database.
                lines = env_set(lines, "DATABASE_URL", f"{prefix}/{intended}{tail}")
                if ok:
                    mode, database = ISOLATION_ISOLATED, intended
                else:
                    mode, failure = ISOLATION_FAILED, reason
        lines = env_set(lines, "REDIS_DB", str(slot))
        for key in ("FRONTEND_URL", "CORS_ORIGINS"):
            val = env_get(lines, key)
            if val:
                lines = env_set(lines, key, val.replace(str(FRONTEND_PORT_BASE), str(fp))
                                             .replace(str(BACKEND_PORT_BASE), str(bp)))
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        notes.append(f"redis db: {slot} (ARQ queue of this tree is separate)")

    record = {"slug": slug, "slot": slot, "backend_port": bp, "frontend_port": fp,
              "redis_db": slot, "database": database,
              "intended_database": intended, "isolation": mode}
    (wt / SLOT_FILE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    notes.append(f"ports: backend {bp}, frontend {fp} (written to {SLOT_FILE})")
    return record, notes, failure


def isolation_mode(entry: dict) -> str:
    """How isolated is this tree's database?

    Tolerates records written before the field existed: a database name meant
    isolated, an empty one meant shared -- which is precisely the ambiguity the
    field removes, since "empty" also covered "creation failed".
    """
    return entry.get("isolation") or (
        ISOLATION_ISOLATED if entry.get("database") else ISOLATION_SHARE)


def db_status_line(entry: dict) -> str:
    """One line for `status`. Anything but real isolation reads as a warning."""
    mode = isolation_mode(entry)
    if mode == ISOLATION_ISOLATED:
        return f"db {entry.get('database')}"
    if mode == ISOLATION_SHARE:
        return "db SHARED WITH MAIN REPO -- migrations forbidden"
    if mode == ISOLATION_FAILED:
        return (f"db ISOLATION FAILED ({entry.get('intended_database') or '?'} was "
                f"never created) -- tree unusable, see wt.py doctor")
    return f"db NOT ISOLATED (no {ENV_FILE} / Postgres DATABASE_URL in this tree)"


def db_prompt_sentence(entry: dict) -> str:
    """The DATABASE line of the delegation block.

    Pasted into every subagent prompt, so it is the last line of defence: when
    the tree is not isolated it has to say so in words the agent will act on.
    """
    mode = isolation_mode(entry)
    if mode == ISOLATION_ISOLATED:
        return (f"DATABASE: this tree owns {entry.get('database')}, isolated from "
                f"the main repo -- migrations and test data here are yours.")
    if mode == ISOLATION_SHARE:
        return ("DATABASE: this tree SHARES the main repo's database (--db share). "
                "Alembic migrations and destructive SQL are FORBIDDEN here -- they "
                "would hit the user's working database.")
    if mode == ISOLATION_FAILED:
        return (f"DATABASE: isolation FAILED for this tree (intended "
                f"{entry.get('intended_database') or '?'}, never created), so "
                f"nothing here can reach Postgres at all. Alembic migrations and "
                f"destructive SQL are FORBIDDEN; report this back instead of "
                f"repointing DATABASE_URL.")
    return (f"DATABASE: this tree has no {ENV_FILE} with a Postgres DATABASE_URL, so no database "
            "of its own. Alembic migrations and destructive SQL are FORBIDDEN here.")


def stray_main_edits(repo: Path) -> list[str]:
    """Changes in the main repo that should have happened in the worktree."""
    stray = []
    for line in dirty_files(repo):
        path = line[3:].strip().strip('"')
        if any(path.startswith(prefix) for prefix in MAIN_REPO_ALLOWLIST):
            continue
        stray.append(line)
    return stray


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_new(args) -> int:
    repo = main_repo()
    slug = args.slug
    if not SLUG_RE.match(slug):
        die("slug must match [a-z0-9][a-z0-9._-]* (e.g. stage35-w5, fix-audio-url)")

    branch = BRANCH_PREFIX + slug
    root = wt_root(repo)
    path = root / slug
    base = args.base or current_branch(repo)

    if branch_exists(repo, branch):
        die(f"branch {branch} already exists. Pick another slug or land/drop the old one.", 3)
    if path.exists():
        die(f"path already exists: {path}", 3)

    rc, _, err = git(["fetch", "origin", base], repo)
    if rc != 0:
        die(f"fetch origin {base} failed: {err}", 3)

    if not remote_branch_exists(repo, base):
        die(f"base branch {base} has no origin counterpart -- push it first", 3)

    ahead = count_commits(repo, f"origin/{base}..{base}")
    if ahead > 0:
        die(f"local {base} is {ahead} commit(s) ahead of origin/{base}. "
            f"Push the base first: git push origin {base}", 3)

    stray = stray_main_edits(repo)

    path.parent.mkdir(parents=True, exist_ok=True)
    rc, _, err = git(["worktree", "add", str(path), "-b", branch, f"origin/{base}"], repo)
    if rc != 0:
        die(f"worktree add failed: {err}", 1)

    rc, _, err = git(["push", "-u", "origin", branch], path)
    if rc != 0:
        out(f"WARN: initial push failed ({err}). Branch exists locally only; "
            f"re-run: git -C {path} push -u origin {branch}")

    state = load_state(repo)
    slot = free_slot(state)
    # .env must be copied before it is patched with the isolated values.
    notes = [] if args.no_link else link_local_artifacts(repo, path, args.isolate)
    record, iso_notes, failure = isolate_worktree_env(
        repo, path, slug, slot, args.db, args.pg_container)
    notes += iso_notes
    state["worktrees"][slug] = {
        "branch": branch,
        "path": str(path).replace("\\", "/"),
        "base": base,
        "task": args.task or "",
        "slot": slot,
        "backend_port": record["backend_port"],
        "frontend_port": record["frontend_port"],
        "redis_db": record["redis_db"],
        "database": record["database"],
        "intended_database": record["intended_database"],
        "isolation": record["isolation"],
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    state["current"] = slug
    save_state(repo, state)

    out(f"worktree  {str(path).replace(chr(92), '/')}")
    out(f"branch    {branch}  (from origin/{base}, tracking origin/{branch})")
    out(f"base      {base}")
    out(f"slot      {slot}  (backend {record['backend_port']}, "
        f"frontend {record['frontend_port']}, redis db {record['redis_db']})")
    for n in notes:
        out(f"env       {n}")
    if stray:
        out(f"WARN      main repo has {len(stray)} uncommitted change(s) NOT carried "
            f"into the worktree (run `wt.py doctor`)")
    if failure:
        # No delegation block: it would invite agents into a tree that cannot
        # talk to a database, and the block is what made the failed isolation
        # of 2026-09-02 read as normal in every subagent prompt.
        out("")
        for ln in isolation_failure_report(slug, path, record["intended_database"],
                                           failure, args.db):
            out(ln)
        return 3
    out("")
    out("Next: pass the worktree path to every agent. Block for prompts:")
    out("")
    _print_prompt_block(repo, slug)
    return 0


def cmd_status(args) -> int:
    repo = main_repo()
    state = load_state(repo)
    if not state["worktrees"]:
        out("no active worktree")
        out(f"main repo {str(repo).replace(chr(92), '/')} on {current_branch(repo)}, "
            f"{len(dirty_files(repo))} dirty file(s)")
        return 0

    for slug, e in state["worktrees"].items():
        path = Path(e["path"])
        mark = "*" if slug == state["current"] else " "
        out(f"{mark} {slug}")
        if not path.exists():
            out(f"    MISSING path {e['path']} -- run `wt.py doctor`")
            continue
        branch, base = e["branch"], e["base"]
        git(["fetch", "origin", base, branch], path)
        behind = count_commits(path, f"HEAD..origin/{base}")
        ahead = count_commits(path, f"origin/{base}..HEAD")
        unpushed = count_commits(path, f"origin/{branch}..HEAD") if \
            remote_branch_exists(path, branch) else -1
        dirty = dirty_files(path)
        out(f"    path    {e['path']}")
        out(f"    branch  {branch}  base {base}")
        out(f"    commits {ahead} ahead of origin/{base}, {behind} behind "
            f"({'needs sync' if behind else 'rebased'})")
        out(f"    push    {'clean' if unpushed == 0 else f'{unpushed} unpushed'}"
            if unpushed >= 0 else "    push    branch not on origin")
        out(f"    dirty   {len(dirty)} file(s)")
        if rebase_in_progress(path):
            out(f"    REBASE IN PROGRESS, conflicts: {', '.join(conflicted_files(path)) or 'none'}")
        if e.get("slot"):
            out(f"    slot    {e['slot']}: backend {e.get('backend_port')}, "
                f"frontend {e.get('frontend_port')}, redis db {e.get('redis_db')}, "
                f"{db_status_line(e)}")
        if e.get("task"):
            out(f"    task    {e['task']}")

    stray = stray_main_edits(repo)
    out(f"main repo on {current_branch(repo)}, "
        f"{len(stray)} stray change(s)" + (" <-- should be in the worktree" if stray else ""))
    return 0


def cmd_sync(args) -> int:
    repo = main_repo()
    e = active_entry(repo, args.slug)
    path, base, branch = Path(e["path"]), e["base"], e["branch"]

    if rebase_in_progress(path):
        out("rebase already in progress. Resolve, then: "
            f"git -C {e['path']} rebase --continue")
        for f in conflicted_files(path):
            out(f"  conflict {f}")
        return 2

    dirty = dirty_files(path)
    if dirty:
        die(f"worktree has {len(dirty)} uncommitted change(s). Commit first: "
            f"wt.py commit -m \"...\"", 3)

    # Captured before ANY fetch in this command: the lease below must be pinned
    # to what we believed origin/<branch> was when we started, otherwise the
    # fetch that is about to run makes the lease agree with a second writer's
    # push and the force overwrites it.
    expected = remote_sha(path, branch)

    rc, _, err = git(["fetch", "origin", base], path)
    if rc != 0:
        die(f"fetch failed: {err}", 3)

    behind = count_commits(path, f"HEAD..origin/{base}")
    if behind == 0:
        out(f"already rebased on origin/{base}")
    else:
        rc, o, err = git(["rebase", f"origin/{base}"], path)
        if rc != 0:
            conflicts = conflicted_files(path)
            out(f"REBASE CONFLICT on {len(conflicts)} file(s):")
            for f in conflicts:
                out(f"  {f}")
            out("")
            out(f"Resolve in the worktree ({e['path']}), then:")
            out(f"  git -C {e['path']} add <files> && git -C {e['path']} rebase --continue")
            out(f"  python .claude/scripts/wt.py sync   # re-run to finish + push")
            out(f"Abort instead: git -C {e['path']} rebase --abort")
            return 2
        out(f"rebased {branch} onto origin/{base} (was {behind} behind)")

    # Push reconciliation runs unconditionally: a manually finished
    # `rebase --continue` also leaves the branch diverged from origin, and
    # `land` refuses anything unpushed.
    git(["fetch", "origin", branch], path)
    if not remote_branch_exists(path, branch):
        rc, _, err = git(["push", "-u", "origin", branch], path)
        out(f"pushed {branch} (new remote branch)" if rc == 0 else f"push failed: {err}")
        return 0 if rc == 0 else 3

    unpushed = count_commits(path, f"origin/{branch}..HEAD")
    diverged = count_commits(path, f"HEAD..origin/{branch}")
    if unpushed == 0 and diverged == 0:
        out(f"origin/{branch} already up to date")
        return 0

    if not expected:
        die(f"origin/{branch} exists on the remote, but this worktree has no "
            f"remote-tracking ref for it -- there is no lease value to push "
            f"against, and forcing blind could drop someone else's commits. "
            f"Fetch and look first: git -C {e['path']} fetch origin {branch}", 3)

    pushed, refusal = push_leased(path, branch, expected)
    if not pushed:
        die(refusal, 3)
    out(f"pushed {branch} (leased force, {unpushed} ahead / {diverged} behind origin)")
    return 0


def _check_secrets(path: Path, staged: list[str]) -> list[str]:
    bad = []
    for f in staged:
        if SECRET_ALLOW.search(f):
            continue
        if any(p.search(f) for p in SECRET_PATTERNS):
            bad.append(f"secret-looking path: {f}")
            continue
        fp = path / f
        try:
            if fp.is_file() and fp.stat().st_size > BIG_FILE_BYTES:
                bad.append(f"large file ({fp.stat().st_size // 1024 // 1024} MB): {f}")
        except OSError:
            pass
    return bad


def cmd_commit(args) -> int:
    repo = main_repo()
    e = active_entry(repo, args.slug)
    path, branch = Path(e["path"]), e["branch"]

    if rebase_in_progress(path):
        die("rebase in progress -- finish or abort it before committing", 3)

    message = args.message
    if args.file:
        message = sys.stdin.read() if args.file == "-" else \
            Path(args.file).read_text(encoding="utf-8")
    if not message or not message.strip():
        die("empty commit message (-m \"...\" or -F -)")
    message = message.rstrip()
    if "Co-Authored-By:" not in message:
        message += "\n\n" + CO_AUTHOR

    git(["add", "-A"], path)
    _, staged_raw, _ = git(["diff", "--cached", "--name-only"], path)
    staged = [s for s in staged_raw.splitlines() if s.strip()]
    if not staged:
        out("nothing to commit")
        return 0

    problems = _check_secrets(path, staged)
    trackers = [f for f in staged if f in TRACKER_FILES]
    if trackers and not args.force:
        git(["reset"], path)
        out("REFUSED -- tracker files staged in a worktree (index reset):")
        for f in trackers:
            out(f"  {f}")
        out("Trackers belong to the MAIN repo: edit them there and commit with "
            "`git commit --only <paths>`. In a worktree they conflict on every sync.")
        return 3
    if problems and not args.force:
        git(["reset"], path)
        out("REFUSED -- suspicious paths staged (index reset):")
        for p in problems:
            out(f"  {p}")
        out("Review manually; re-run with --force only if intentional.")
        return 3

    rc, o, err = git(["commit", "-F", "-"], path, stdin_text=message)
    if rc != 0:
        die(f"commit failed: {err or o}", 1)

    _, stat, _ = git(["show", "--stat", "--oneline", "-s", "HEAD"], path)
    _, sha, _ = git(["rev-parse", "--short", "HEAD"], path)

    # Same capture-before-fetch rule as in sync: `wt.py status` fetches, so by
    # the time commit runs the tracking ref may already carry someone else's
    # commit, and a bare lease would happily overwrite it.
    expected = remote_sha(path, branch)
    rc, _, err = git(["push", "origin", branch], path)
    pushed = rc == 0
    if not pushed:
        # A rejected plain push means origin has something we do not: either our
        # own pre-rebase tip (forcing is intended, that is the rebase flow) or a
        # second writer's commit (forcing destroys it). Fetch first, so the
        # decision and the message describe origin as it is now.
        git(["fetch", "origin", branch], path)
        pushed, refusal = push_leased(path, branch, expected)
        if not pushed:
            out(f"committed {sha} but PUSH FAILED: {err}")
            out(refusal)
            return 3

    out(f"committed {sha}, {len(staged)} file(s), pushed to origin/{branch}")
    return 0


def print_remote_tip_recovery(branch: str, local_tip: str, remote_tip: str) -> None:
    """Recovery command for origin/<branch> when it is not the local tip.

    land and drop both delete the remote branch, and the sha they print is the
    LOCAL one. If the two ever differ, the operator would be left with no way
    back to the commits that only origin had.
    """
    if remote_tip and remote_tip != local_tip:
        out(f"origin/{branch} tip was {remote_tip}, DIFFERENT from the local tip -- "
            f"recover it separately: git branch {branch}-from-origin {remote_tip}")


def cmd_land(args) -> int:
    repo = main_repo()
    e = active_entry(repo, args.slug)
    slug, path, base, branch = e["slug"], Path(e["path"]), e["base"], e["branch"]

    # --- preflight -------------------------------------------------------
    problems: list[str] = []
    if not path.exists():
        die(f"worktree path missing: {e['path']}", 3)
    if rebase_in_progress(path):
        problems.append("rebase in progress in the worktree")
    wt_dirty = dirty_files(path)
    if wt_dirty:
        problems.append(f"worktree has {len(wt_dirty)} uncommitted change(s) "
                        f"-- run wt.py commit")

    git(["fetch", "origin", base, branch], path)
    behind = count_commits(path, f"HEAD..origin/{base}")
    ahead = count_commits(path, f"origin/{base}..HEAD")
    if behind > 0:
        problems.append(f"branch is {behind} commit(s) behind origin/{base} "
                        f"-- run wt.py sync first")
    if ahead == 0:
        problems.append(f"nothing to land: no commits beyond origin/{base}")
    unpushed = count_commits(path, f"origin/{branch}..HEAD")
    if unpushed != 0:
        problems.append(f"{unpushed} unpushed commit(s) on {branch} -- run wt.py commit/sync")
    # The mirror image of `unpushed`, and the dangerous one: landing a branch
    # that is behind its own remote merges the local tip WITHOUT the other
    # writer's commits and then deletes both branches, leaving their work
    # unreachable on origin.
    diverged = count_commits(path, f"HEAD..origin/{branch}")
    if diverged > 0:
        problems.append(f"branch is {diverged} commit(s) behind origin/{branch} "
                        f"(someone else pushed to the task branch) -- run wt.py sync "
                        f"and integrate them before landing")

    main_branch_now = current_branch(repo)
    if main_branch_now != base:
        problems.append(f"main repo is on {main_branch_now}, expected {base}")
    stray = stray_main_edits(repo)
    if stray:
        problems.append(f"main repo has {len(stray)} stray change(s) -- "
                        f"commit or revert them there first (wt.py doctor)")

    if problems:
        out("LAND BLOCKED:")
        for p in problems:
            out(f"  - {p}")
        return 3

    if args.dry_run:
        out(f"dry-run: would merge --no-ff {branch} ({ahead} commits) into {base}, "
            f"push origin {base}, remove worktree {e['path']}"
            f"{'' if args.keep_branch else ', delete local+remote branch'}")
        _, log, _ = git(["log", "--oneline", f"origin/{base}..HEAD"], path)
        for ln in log.splitlines():
            out(f"    {ln}")
        return 0

    # --- land ------------------------------------------------------------
    rc, _, err = git(["fetch", "origin", base], repo)
    if rc != 0:
        die(f"fetch failed: {err}", 3)
    rc, _, err = git(["merge", "--ff-only", f"origin/{base}"], repo)
    if rc != 0:
        die(f"main repo cannot fast-forward {base} to origin/{base}: {err}", 3)

    subject = e.get("task") or slug
    msg = (f"merge({branch}): {subject}\n\n"
           f"{ahead} commit(s) from the task worktree, rebased onto {base}.\n\n"
           f"{CO_AUTHOR}\n")
    # `git merge` has no `-F -`: unlike `git commit`, it cannot read the message
    # from stdin. Passing the multi-line string through -m is safe here because
    # no shell is involved (subprocess without shell=True).
    rc, o, err = git(["merge", "--no-ff", branch, "-m", msg], repo)
    if rc != 0:
        out(f"MERGE FAILED: {err or o}")
        out(f"Main repo may be mid-merge. Inspect: git -C {repo} status")
        return 2

    _, merge_sha, _ = git(["rev-parse", "--short", "HEAD"], repo)
    rc, _, err = git(["push", "origin", base], repo)
    if rc != 0:
        out(f"merged locally as {merge_sha} but PUSH of {base} FAILED: {err}")
        out(f"Retry: git -C {repo} push origin {base}")
        return 3

    _, tip_sha, _ = git(["rev-parse", "--short", branch], repo)
    # Remote-tracking refs are shared between worktrees, so this is the tip the
    # preflight fetch saw. It should equal the local one (the preflight blocks
    # otherwise), but --keep-branch and manual pushes exist: print both when
    # they differ, so every deleted ref has a recovery command.
    _, remote_tip_sha, _ = git(["rev-parse", "--short",
                                f"refs/remotes/origin/{branch}"], repo)
    remote_tip_full = remote_sha(repo, branch)

    # --- cleanup ---------------------------------------------------------
    unlink_local_artifacts(path)
    rc, _, err = git(["worktree", "remove", str(path)], repo)
    if rc != 0:
        out(f"WARN: worktree remove failed ({err}); try "
            f"git -C {repo} worktree remove --force {e['path']}")
    if not args.keep_branch:
        git(["branch", "-d", branch], repo)
        # The preflight fetch happened minutes ago; a plain --delete would drop
        # whatever landed on the branch since, and after a delete nobody can
        # even see what was lost. Under a lease the delete is simply refused
        # and the branch survives -- the merge above is already safe either way.
        lease = [f"--force-with-lease={branch}:{remote_tip_full}"] if remote_tip_full else []
        rc, _, err = git(["push", *lease, "origin", "--delete", branch], repo)
        if rc != 0:
            out(f"WARN: remote branch delete refused, origin/{branch} was left in "
                f"place: {err.splitlines()[-1] if err else 'see git'}")
            out(f"      Someone may have pushed to it after the preflight. Look: "
                f"git -C {repo} fetch origin {branch} && "
                f"git -C {repo} log --oneline {base}..origin/{branch}")

    state = load_state(repo)
    state["worktrees"].pop(slug, None)
    if state.get("current") == slug:
        state["current"] = next(iter(state["worktrees"]), None)
    save_state(repo, state)

    if e.get("database"):
        out(f"database {e['database']} left in place (data may still be useful). "
            f"Drop it: python .claude/scripts/wt.py dbdrop --database "
            f"{e['database']} --yes")
    out(f"landed {branch} -> {base} as merge {merge_sha} ({ahead} commits), pushed")
    out(f"branch tip was {tip_sha}"
        + ("" if args.keep_branch else f" (branch deleted; recover: git branch {branch} {tip_sha})"))
    print_remote_tip_recovery(branch, tip_sha, remote_tip_sha)
    if not state["worktrees"]:
        out("no active worktree left")
    return 0


def cmd_drop(args) -> int:
    repo = main_repo()
    e = active_entry(repo, args.slug)
    slug, path, base, branch = e["slug"], Path(e["path"]), e["base"], e["branch"]

    unmerged = count_commits(repo, f"{base}..{branch}") if branch_exists(repo, branch) else 0
    dirty = dirty_files(path) if path.exists() else []
    # drop deletes the REMOTE branch too, so the local branch is not the whole
    # picture: a second writer's commit lives only on origin/<branch>, where
    # `base..branch` cannot see it. Fetch, then count what only they have.
    origin_only = 0
    if remote_branch_exists(repo, branch):
        git(["fetch", "origin", branch], repo)
        if branch_exists(repo, branch):
            origin_only = max(0, count_commits(
                repo, f"{branch}..refs/remotes/origin/{branch}"))
    if (unmerged > 0 or origin_only > 0 or dirty) and not args.force:
        out("DROP BLOCKED (nothing deleted):")
        if unmerged > 0:
            out(f"  - {unmerged} commit(s) on {branch} not in {base}")
        if origin_only > 0:
            out(f"  - {origin_only} commit(s) on origin/{branch} not in the local "
                f"branch (someone else pushed to it)")
        if dirty:
            out(f"  - {len(dirty)} uncommitted change(s) in the worktree")
        out("Land it (wt.py land) or re-run with --force to abandon.")
        return 3

    if path.exists():
        unlink_local_artifacts(path)
        rc, _, err = git(["worktree", "remove", "--force", str(path)], repo)
        if rc != 0:
            out(f"WARN: worktree remove failed: {err}")
    git(["worktree", "prune"], repo)
    _, tip, _ = git(["rev-parse", "--short", branch], repo)
    _, rtip, _ = git(["rev-parse", "--short", f"refs/remotes/origin/{branch}"], repo)
    if branch_exists(repo, branch):
        git(["branch", "-D", branch], repo)
    if remote_branch_exists(repo, branch):
        git(["push", "origin", "--delete", branch], repo)

    state = load_state(repo)
    state["worktrees"].pop(slug, None)
    if state.get("current") == slug:
        state["current"] = next(iter(state["worktrees"]), None)
    save_state(repo, state)
    if e.get("database"):
        out(f"database {e['database']} left in place. Drop it: "
            f"python .claude/scripts/wt.py dbdrop --database {e['database']} --yes")
    out(f"dropped {slug} (branch {branch} deleted, tip was {tip}; "
        f"recover: git branch {branch} {tip})")
    print_remote_tip_recovery(branch, tip, rtip)
    return 0


def cmd_dbcreate(args) -> int:
    """Redo the isolation step for a tree that already exists.

    The other half of the "fail loud" contract: `new` refuses to hand over a
    tree without its own database, so there has to be a way to fix the cause
    (usually: close the connections holding the template) and retry WITHOUT
    recreating the branch and losing the commits already on it.
    """
    repo = main_repo()
    e = active_entry(repo, args.slug)
    slug, path = e["slug"], Path(e["path"])
    if not path.exists():
        die(f"worktree path missing: {e['path']} -- run wt.py doctor", 3)
    slot = e.get("slot")
    if not slot:
        die(f"worktree {slug} has no slot recorded, so its ports and redis db "
            f"are unknown -- drop and recreate it", 3)

    record, notes, failure = isolate_worktree_env(
        repo, path, slug, slot, args.db, args.pg_container)
    for n in notes:
        out(f"env       {n}")

    state = load_state(repo)
    entry = state["worktrees"][slug]
    entry["database"] = record["database"]
    entry["intended_database"] = record["intended_database"]
    entry["isolation"] = record["isolation"]
    save_state(repo, state)

    if failure:
        out("")
        for ln in isolation_failure_report(slug, path, record["intended_database"],
                                           failure, args.db):
            out(ln)
        return 3
    if record["isolation"] == ISOLATION_ISOLATED:
        out(f"database  {record['database']} -- {slug} is isolated; "
            f"{ENV_FILE} and {SLOT_FILE} updated")
    else:
        out(f"nothing to isolate: {db_status_line(record)}")
    return 0


def cmd_dbdrop(args) -> int:
    """Destructive and therefore never automatic: --yes is mandatory."""
    repo = main_repo()
    name = args.database
    if not name:
        e = active_entry(repo, args.slug)
        name = e.get("database")
        if not name:
            die(f"worktree {e['slug']} has no isolated database", 3)
    url = env_get(env_lines(repo / ENV_FILE), "DATABASE_URL")
    if not url:
        die(f"no DATABASE_URL in the main repo {ENV_FILE}", 3)
    if not args.yes:
        out(f"would DROP DATABASE {name} (all its data) on the server from "
            f"the main repo DATABASE_URL. Re-run with --yes.")
        return 0
    if "_wt_" not in name and not args.force:
        die(f"{name} does not look like a worktree database (no _wt_ in the name). "
            f"Refusing; pass --force if you really mean it.", 3)
    ok, msg = pg_admin(repo, url, "drop", name)
    if not ok:
        die(f"drop failed: {msg}", 1)
    out(f"dropped database {name} ({msg.lower()})")
    state = load_state(repo)
    for slug, e in state["worktrees"].items():
        if e.get("database") == name:
            # The tree now points at a database that does not exist -- the same
            # state a failed creation leaves behind, and it has to read the same
            # way in status/doctor/prompt. Clearing only the name would let the
            # tree look shared again, which is the wrong half of the truth.
            e["database"] = ""
            e["intended_database"] = e.get("intended_database") or name
            e["isolation"] = ISOLATION_FAILED
            out(f"worktree {slug} now has NO database: recreate it with "
                f"`wt.py dbcreate --slug {slug}` or drop the tree")
    save_state(repo, state)
    return 0


def cmd_doctor(args) -> int:
    repo = main_repo()
    state = load_state(repo)
    issues = 0

    stray = stray_main_edits(repo)
    if state["worktrees"] and stray:
        issues += 1
        out(f"[!] {len(stray)} change(s) in the MAIN repo while a worktree is active:")
        for ln in stray[:20]:
            out(f"      {ln}")
        if len(stray) > 20:
            out(f"      ... +{len(stray) - 20} more")
        out("    Fix: move them to the worktree, or commit them to the base "
            "deliberately (they will NOT be part of the task branch).")

    mb = current_branch(repo)
    for slug, e in state["worktrees"].items():
        if not Path(e["path"]).exists():
            issues += 1
            out(f"[!] {slug}: path missing ({e['path']}). "
                f"Fix: git -C {repo} worktree prune, then wt.py drop --force")
        if e["base"] != mb:
            out(f"[i] {slug}: base is {e['base']}, main repo is on {mb}")
        mode = isolation_mode(e)
        if mode == ISOLATION_FAILED:
            issues += 1
            out(f"[!] {slug}: database isolation FAILED -- "
                f"{e.get('intended_database') or 'the isolated database'} was never "
                f"created, so this tree cannot run anything that needs Postgres.")
            out(f"    Fix: free the connections, then "
                f"python .claude/scripts/wt.py dbcreate --slug {slug}")
            out(f"    Or abandon it: python .claude/scripts/wt.py drop --slug {slug}")
        elif mode == ISOLATION_SHARE:
            out(f"[i] {slug}: database SHARED with the main repo (--db share) -- "
                f"alembic and destructive SQL are forbidden in this tree")
        elif mode == ISOLATION_NO_ENV:
            out(f"[i] {slug}: no {ENV_FILE}, so no database of its own")

    slots: dict[int, list[str]] = {}
    for slug, e in state["worktrees"].items():
        if e.get("slot"):
            slots.setdefault(e["slot"], []).append(slug)
    for slot, owners in slots.items():
        if len(owners) > 1:
            issues += 1
            out(f"[!] slot {slot} claimed by {', '.join(owners)} -- same ports and "
                f"database; drop one and recreate it")

    rc, o, _ = git(["worktree", "list", "--porcelain"], repo)
    known = {Path(e["path"]).resolve() for e in state["worktrees"].values()}
    for line in o.splitlines():
        if line.startswith("worktree "):
            p = Path(line[len("worktree "):]).resolve()
            if p != repo.resolve() and p not in known:
                issues += 1
                out(f"[!] untracked worktree on disk: {p} (not in wt-active.json). "
                    f"Fix: git -C {repo} worktree remove {p}")

    if not issues:
        out(f"ok: {len(state['worktrees'])} worktree(s), main repo clean of stray edits")
    return 0 if not issues else 3


def cmd_list(args) -> int:
    repo = main_repo()
    state = load_state(repo)
    rc, o, _ = git(["worktree", "list"], repo)
    out(o)
    if state["worktrees"]:
        out(f"active: {state.get('current')}  (state: {state_path(repo)})")
    return 0


def _print_prompt_block(repo: Path, slug: str | None = None) -> None:
    e = active_entry(repo, slug)
    out("--- copy into every delegation prompt ---")
    out(f"WORKTREE: {e['path']}")
    out(f"All reads, edits, tests and commands go there, using absolute paths under "
        f"that directory. The main repo ({str(repo).replace(chr(92), '/')}) is "
        f"READ-ONLY for you: never Write/Edit/patch anything under it. "
        f"Do not run git commit/push/merge/rebase yourself -- report back and the "
        f"orchestrator commits via wt.py.")
    if e.get("slot"):
        out(f"PORTS: this tree runs on backend {e.get('backend_port')} and frontend "
            f"{e.get('frontend_port')} (see .wt-slot.json in the worktree root) and "
            f"its redis db index is {e.get('redis_db')}. Never hardcode the base ports or "
            f"start servers on them -- other worktrees are running there.")
        out(db_prompt_sentence(e))
    out(f"TRACKERS: do not edit {', '.join(TRACKER_FILES)} here; they belong to the "
        f"main repo and the orchestrator writes them. wt.py commit refuses them.")
    out("--- end ---")


def cmd_prompt(args) -> int:
    _print_prompt_block(main_repo(), args.slug)
    return 0


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wt.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="create task branch + worktree, push -u")
    n.add_argument("slug")
    n.add_argument("--base", help="base branch (default: current branch of main repo)")
    n.add_argument("--task", help="one-line task description (used in the merge message)")
    n.add_argument("--no-link", action="store_true",
                   help="skip wiring node_modules/.venv/.env into the worktree")
    n.add_argument("--isolate", action="store_true",
                   help="own node_modules/.venv instead of junctions to the main repo "
                        "(needed when this task changes dependencies)")
    n.add_argument("--db", choices=("copy", "empty", "share"), default="copy",
                   help="copy: CREATE DATABASE ... TEMPLATE <base>, falling back to "
                        "pg_dump | psql when the template is busy (default); "
                        "empty: fresh db, run alembic yourself; "
                        "share: reuse the main database (no migrations allowed)")
    n.add_argument("--pg-container",
                   help="name of the Postgres docker container (only needed when "
                        "auto-detection finds zero or several)")
    n.set_defaults(func=cmd_new)

    s = sub.add_parser("status", help="compact state")
    s.set_defaults(func=cmd_status)

    y = sub.add_parser("sync", help="rebase onto origin/<base> + force-with-lease push")
    y.add_argument("--slug")
    y.set_defaults(func=cmd_sync)

    c = sub.add_parser("commit", help="add -A + commit + push inside the worktree")
    c.add_argument("-m", "--message")
    c.add_argument("-F", "--file", help="read message from file, '-' for stdin")
    c.add_argument("--force", action="store_true", help="bypass the secret/size guard")
    c.add_argument("--slug")
    c.set_defaults(func=cmd_commit)

    l = sub.add_parser("land", help="merge --no-ff into base, push, clean up")
    l.add_argument("--keep-branch", action="store_true")
    l.add_argument("--dry-run", action="store_true")
    l.add_argument("--slug")
    l.set_defaults(func=cmd_land)

    d = sub.add_parser("drop", help="abandon a worktree without landing")
    d.add_argument("--force", action="store_true")
    d.add_argument("--slug")
    d.set_defaults(func=cmd_drop)

    dc = sub.add_parser("dbcreate",
                        help="(re)create the isolated database of an existing worktree")
    dc.add_argument("--slug")
    dc.add_argument("--db", choices=("copy", "empty"), default="copy",
                    help="copy: pg_dump/TEMPLATE copy of the base database "
                         "(default); empty: fresh database, run alembic yourself")
    dc.add_argument("--pg-container",
                    help="name of the Postgres docker container (only needed when "
                         "auto-detection finds zero or several)")
    dc.set_defaults(func=cmd_dbcreate)

    db = sub.add_parser("dbdrop", help="drop the isolated database of a worktree")
    db.add_argument("--slug")
    db.add_argument("--database", help="explicit name (worktree may be gone already)")
    db.add_argument("--yes", action="store_true", help="required: this destroys data")
    db.add_argument("--force", action="store_true",
                    help="allow a name without _wt_ in it")
    db.set_defaults(func=cmd_dbdrop)

    doc = sub.add_parser("doctor", help="stray edits + state consistency")
    doc.set_defaults(func=cmd_doctor)

    li = sub.add_parser("list", help="all worktrees")
    li.set_defaults(func=cmd_list)

    pr = sub.add_parser("prompt", help="delegation block for subagent prompts")
    pr.add_argument("--slug")
    pr.set_defaults(func=cmd_prompt)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
