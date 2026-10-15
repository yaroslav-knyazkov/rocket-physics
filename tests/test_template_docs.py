"""Step 82 (Phase 2.16, SS32.8): every config template documents every field.

For each of the five `_TEMPLATE_*.py` files:
  * the module docstring carries `### <TypeName>` tables whose row set equals
    `{f.name for f in dataclasses.fields(T)}` -- for the type the template
    constructs and for every nested group it uses (a new field added to
    `sim/params.py` or `configs/schema.py` and never documented fails here);
  * every table row's REQ/OPT cell is exactly `REQ` or `OPT`;
  * every inline comment inside a module-level constructor call matches
    `^#\\s(REQ|OPT),\\s`, and every keyword argument carries one;
  * the module imports cleanly and is absent from its registry.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import io
import re
import tokenize
from pathlib import Path

import pytest

import configs.motors
import configs.rockets
import configs.scenarios
import configs.schema
import configs.sites
import configs.weather
import sim.params

# (module path, piece attribute, registry package)
TEMPLATES = [
    ("configs.rockets._TEMPLATE_rocket", "ROCKET", configs.rockets),
    ("configs.motors._TEMPLATE_motor", "MOTOR", configs.motors),
    ("configs.sites._TEMPLATE_site", "SITE", configs.sites),
    ("configs.weather._TEMPLATE_weather", "WEATHER", configs.weather),
    ("configs.scenarios._TEMPLATE_scenario", "SCENARIO", configs.scenarios),
]

# Pieces that have their own template: referenced, not tabled, in another one.
# Compared by class NAME, not identity: tests/test_motor_pieces.py drops
# `configs.*` from sys.modules and re-imports it, so a template loaded after
# that holds instances of fresh class objects, and an isinstance check
# against classes captured at this module's import time would miss them.
_OTHER_PIECES = frozenset({"Rocket", "Motor", "LaunchSite", "Weather"})

_COMMENT_RE = re.compile(r"^#\s(REQ|OPT),\s")
_HEADING_RE = re.compile(r"^### (\w+)\s*$")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _parse_tables(doc: str) -> dict[str, list[list[str]]]:
    """`{type name: [row cells, ...]}` for every `### Type` table in `doc`."""
    tables: dict[str, list[list[str]]] = {}
    current = None
    for line in doc.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            current = m.group(1)
            tables[current] = []
            continue
        if current is None or not line.startswith("|"):
            continue
        cells = [c.strip() for c in _UNESCAPED_PIPE.split(line.strip())[1:-1]]
        if cells[0] == "field" or set(cells[0]) <= {"-"}:
            continue  # header / separator row
        tables[current].append(cells)
    return tables


def _resolve(name: str):
    for ns in (configs.schema, sim.params):
        if hasattr(ns, name):
            return getattr(ns, name)
    raise AssertionError(f"table heading ### {name} names no known dataclass")


def _load(module_path: str, attr: str):
    mod = importlib.import_module(module_path)
    return mod, getattr(mod, attr)


@pytest.mark.parametrize("module_path,attr,pkg", TEMPLATES)
def test_tables_cover_every_field(module_path, attr, pkg):
    mod, piece = _load(module_path, attr)
    tables = _parse_tables(mod.__doc__)
    top = type(piece).__name__
    assert top in tables, f"{module_path} docstring has no '### {top}' table"

    for type_name, rows in tables.items():
        names = [r[0] for r in rows]
        assert len(names) == len(set(names)), f"{type_name}: duplicate rows"
        expected = {f.name for f in dataclasses.fields(_resolve(type_name))}
        assert set(names) == expected, (
            f"{module_path} ### {type_name}: undocumented={expected - set(names)}, "
            f"stale={set(names) - expected}"
        )
        for r in rows:
            assert len(r) == 5, f"{type_name}.{r[0]}: expected 5 cells, got {len(r)}"
            assert r[1] in ("REQ", "OPT"), f"{type_name}.{r[0]}: cell is {r[1]!r}"

    # every nested dataclass group the piece holds must have its own table
    for f in dataclasses.fields(piece):
        value = getattr(piece, f.name)
        if dataclasses.is_dataclass(value) and type(value).__name__ not in _OTHER_PIECES:
            assert type(value).__name__ in tables, (
                f"{module_path}: nested group {f.name} ({type(value).__name__}) has no table"
            )


def _constructor_calls(tree: ast.Module) -> list[ast.Call]:
    return [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
    ]


@pytest.mark.parametrize("module_path,attr,pkg", TEMPLATES)
def test_inline_comments_follow_convention(module_path, attr, pkg):
    mod = importlib.import_module(module_path)
    src = Path(mod.__file__).read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)

    # inline = a COMMENT token with code before it on the same line
    inline: dict[int, str] = {}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            row = tok.start[0]
            if lines[row - 1][: tok.start[1]].strip():
                inline[row] = tok.string

    calls = _constructor_calls(tree)
    assert calls, "no module-level constructor call found"
    checked = 0
    for call in calls:
        for row in range(call.lineno, call.end_lineno + 1):
            if row in inline:
                assert _COMMENT_RE.match(inline[row]), f"{module_path}:{row}: {inline[row]!r}"
                checked += 1
        for node in ast.walk(call):
            if not isinstance(node, ast.Call):
                continue
            for i, kw in enumerate(node.keywords):
                # a nested group's comment sits on its opening line; a leaf's
                # anywhere up to the next sibling keyword (a parenthesised
                # value's closing `),  # ...` line is past value.end_lineno)
                if isinstance(kw.value, ast.Call):
                    rows = [kw.value.lineno]
                else:
                    stop = node.keywords[i + 1].value.lineno - 1 if i + 1 < len(node.keywords) else node.end_lineno
                    rows = range(kw.value.lineno, max(stop, kw.value.end_lineno) + 1)
                assert any(r in inline for r in rows), f"{module_path}:{kw.value.lineno}: keyword {kw.arg!r} has no inline comment"
    assert checked > 0


@pytest.mark.parametrize("module_path,attr,pkg", TEMPLATES)
def test_template_imports_and_is_unregistered(module_path, attr, pkg):
    mod, piece = _load(module_path, attr)
    assert piece.name not in pkg.names()
