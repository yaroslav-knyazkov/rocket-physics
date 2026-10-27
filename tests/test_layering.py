"""tests/test_layering.py -- structural guards for the Phase 2.19 in-place
restructuring (`sim/` -> `apps/sim/engine/`, `configs/` retires, `apps/`
taxonomy, `data/` splits -- dev/docs/architecture-apps-sim-restructure.md
SS4.4/SS5, Step 126).

Step 126 is pure addition: these three guards are written and verified to
PASS against *today's* tree (nothing has moved yet) so that every later
step in the phase is checked against a safety net that is known-good
before the first `git mv`, not aspirational.

  G1 -- import-direction guard. The engine (`sim/` today, `apps/sim/
       engine/` after a later step) must never import `apps`, `examples`,
       `tests`, `tools`, or `controllers`. This is the project's existing
       "the engine never imports the application layer" rule
       (architecture.md), enforced here for the first time instead of
       resting on a docstring promise.
  G2 -- importability guard. Every `.py` module under the engine,
       `apps/`, `configs/`, `controllers/` must be importable by its
       dotted name. This is the guard that later catches a file orphaned
       by a `git mv` (moved, but nothing imports it any more, and it
       silently rots).
  G3 -- network-isolation guard. Nothing outside `tools/fetch_sounding.py`
       (the project's one intentionally-networked module) may import
       `urllib`, `http`, `socket`, or `requests`.

`ENGINE_DIR` is the one constant a later step repoints (`"sim"` ->
`"apps/sim/engine"`); nothing else in this file should need to change for
that move.

Scope note (G3): the walk below covers the project's own source tree --
`sim/`, `apps/`, `configs/`, `controllers/`, `tools/`, `tests/`,
`examples/`, and the top-level `run_*.py` entry scripts -- not `.claude/`.
`.claude/` is Claude Code harness tooling (CLAUDE.md's "Профиль проекта"
table never lists it as project code), and two of its scripts
(`.claude/scripts/wt.py`, `.claude/hooks/telegram_notify.py`) legitimately
use `urllib` for orchestration (git worktree URL parsing, Telegram
notifications) -- unrelated to the rocket-physics simulation's own
network-isolation invariant. Flagged here rather than silently excluded.
"""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- G1: import-direction guard -------------------------------------------

# The one line a later step repoints: "sim" -> "apps/sim/engine".
ENGINE_DIR = "sim"

# The engine may never import any of these (stdlib / numpy / scipy /
# matplotlib / anything rooted at the engine package itself are fine).
BANNED_ENGINE_IMPORT_ROOTS = frozenset({"apps", "examples", "tests", "tools", "controllers"})

# --- G2: importability guard ------------------------------------------------

# Trees walked for "every module importable by dotted name" (today's
# layout; `apps/sim/engine` folds the engine into `apps/` in a later step).
IMPORTABILITY_ROOTS = (ENGINE_DIR, "apps", "configs", "controllers")

# --- G3: network-isolation guard --------------------------------------------

# The project's one intentionally-networked module (relative to REPO_ROOT,
# forward slashes -- normalised for comparison below).
NETWORK_EXEMPT_FILES = frozenset({"tools/fetch_sounding.py"})

BANNED_NETWORK_IMPORT_ROOTS = frozenset({"urllib", "http", "socket", "requests"})

# Project source roots scanned for G3 -- see the "Scope note" in the
# module docstring for why `.claude/` is not in this list.
NETWORK_SCAN_ROOTS = ("sim", "apps", "configs", "controllers", "tools", "tests", "examples")
# Top-level entry scripts, scanned individually (they are files, not dirs).
NETWORK_SCAN_ROOT_FILES = ("run.py", "run_airbrake.py", "run_cfd_conditions.py", "run_motor_sweep.py", "run_trade.py")


def _iter_py_files(root_dir: Path):
    """Yield every `*.py` file under `root_dir`, skipping `__pycache__`."""
    for path in sorted(root_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _parsed_imports(py_file: Path) -> ast.Module:
    source = py_file.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(py_file))


def _import_roots(tree: ast.Module) -> set[str]:
    """Root module names (first dotted component) of every absolute
    `import`/`from ... import` in `tree`. Relative imports (`from . import
    x`, `level > 0`) are same-package references, not cross-layer imports,
    and are skipped."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _module_dotted_name(py_file: Path) -> str:
    """Dotted module name of `py_file`, relative to `REPO_ROOT` (e.g.
    `apps/common/artifacts.py` -> `apps.common.artifacts`;
    `sim/__init__.py` -> `sim`)."""
    rel = py_file.relative_to(REPO_ROOT).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


# --- G1 ----------------------------------------------------------------


def test_g1_engine_never_imports_application_layer():
    """The engine (`ENGINE_DIR`) never imports `apps`, `examples`, `tests`,
    `tools`, or `controllers` -- the project's "engine never imports the
    application layer" rule, mechanically verified."""
    violations = []
    engine_root = REPO_ROOT / ENGINE_DIR
    for py_file in _iter_py_files(engine_root):
        tree = _parsed_imports(py_file)
        banned_hits = _import_roots(tree) & BANNED_ENGINE_IMPORT_ROOTS
        if banned_hits:
            violations.append((py_file.relative_to(REPO_ROOT), sorted(banned_hits)))

    assert not violations, (
        f"Engine module(s) under '{ENGINE_DIR}/' import banned application-layer "
        f"package(s): {violations}"
    )


# --- G2 ----------------------------------------------------------------


def test_g2_every_module_is_importable_by_dotted_name():
    """Every `.py` module under `sim/`, `apps/`, `configs/`, `controllers/`
    is importable by its dotted name. Catches a file a later `git mv`
    orphans (moved, but nothing imports it any more)."""
    failures = []
    for root_name in IMPORTABILITY_ROOTS:
        root_dir = REPO_ROOT / root_name
        for py_file in _iter_py_files(root_dir):
            dotted = _module_dotted_name(py_file)
            try:
                importlib.import_module(dotted)
            except Exception as exc:  # noqa: BLE001 -- any import failure is the finding
                failures.append((dotted, repr(exc)))

    assert not failures, f"Module(s) failed to import by dotted name: {failures}"


# --- G3 ----------------------------------------------------------------


def test_g3_no_module_imports_networking_outside_fetch_sounding():
    """Nothing outside `tools/fetch_sounding.py` imports `urllib`, `http`,
    `socket`, or `requests` -- the project's "sim/ (and friends) are
    offline and deterministic" invariant, mechanically verified instead of
    resting on a docstring promise."""
    violations = []

    candidates: list[Path] = []
    for root_name in NETWORK_SCAN_ROOTS:
        candidates.extend(_iter_py_files(REPO_ROOT / root_name))
    for file_name in NETWORK_SCAN_ROOT_FILES:
        candidates.append(REPO_ROOT / file_name)

    for py_file in candidates:
        rel_posix = py_file.relative_to(REPO_ROOT).as_posix()
        if rel_posix in NETWORK_EXEMPT_FILES:
            continue
        tree = _parsed_imports(py_file)
        banned_hits = _import_roots(tree) & BANNED_NETWORK_IMPORT_ROOTS
        if banned_hits:
            violations.append((rel_posix, sorted(banned_hits)))

    assert not violations, f"Module(s) outside the network-exempt list import networking: {violations}"
