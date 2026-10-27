"""Static guard on `pyproject.toml`'s packaging boundary (Phase 2.18,
Step 121: D-138/F7).

CORE (installable) is `sim` + `configs` only -- `apps/`, `tests/`,
`tools/` are deliberately absent from `[tool.setuptools].packages`. This
is a structural check on the committed `pyproject.toml` content, not a
live install simulation (the install-time boundary behaviour itself was
already measured by the architect on a mock repo, per the design doc).
"""

import os
import tomllib

_PYPROJECT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pyproject.toml")


def _load_pyproject() -> dict:
    with open(_PYPROJECT, "rb") as f:
        return tomllib.load(f)


def test_core_packages_are_exactly_sim_and_configs():
    data = _load_pyproject()
    packages = data["tool"]["setuptools"]["packages"]
    assert packages == ["sim", "configs"]


def test_apps_tests_tools_are_not_packaged():
    data = _load_pyproject()
    packages = data["tool"]["setuptools"]["packages"]
    assert "apps" not in packages
    assert "tests" not in packages
    assert "tools" not in packages
