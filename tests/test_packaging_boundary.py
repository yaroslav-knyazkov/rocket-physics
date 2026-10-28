"""Static guard on `pyproject.toml`'s packaging mechanism (Phase 2.18,
Step 121: D-138/F7 -- originally "CORE is `sim` + `configs` only";
Phase 2.19, Step 128: FK1=R2 retired the packaging mechanism entirely).

The project is not `pip install`-ed in the working interpreter and
everything works anyway, so `[build-system]`/`[project]`/
`[tool.setuptools]` were removed from `pyproject.toml` before any files
move (Step 128) -- rewriting a `packages` list at every later step would
have been pure overhead for a mechanism nothing here exercises.
`requirements.txt` is the single dependency declaration now. This file's
job flips from "packaging boundary is exactly sim+configs" to "packaging
config does not exist" -- the regression test catching a later step
*reintroducing* `[tool.setuptools]` without an explicit decision, not a
live install simulation either way.
"""

import os
import tomllib

_PYPROJECT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pyproject.toml")


def _load_pyproject() -> dict:
    with open(_PYPROJECT, "rb") as f:
        return tomllib.load(f)


def test_pyproject_has_no_build_system_table():
    data = _load_pyproject()
    assert "build-system" not in data


def test_pyproject_has_no_project_table():
    data = _load_pyproject()
    assert "project" not in data


def test_pyproject_has_no_setuptools_packaging_config():
    data = _load_pyproject()
    assert "tool" not in data or "setuptools" not in data.get("tool", {})
