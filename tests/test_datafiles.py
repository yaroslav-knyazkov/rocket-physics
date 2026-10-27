"""Tests for `sim/datafiles.py` (Phase 2.18, Step 120: D-137/F5).

Covers the 3-rule path resolver in isolation (bare name -> bundled,
absolute -> unchanged, cwd-relative -> resolved against `os.getcwd()`)
and one end-to-end check that the `#designation` fragment logic in
`sim.motor_file.load()` still works once the filename part resolves to
an absolute path outside the repo.
"""

import os
import shutil

import pytest

from sim import datafiles, motor_file

_REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
_DATA = os.path.join(_REPO_ROOT, "data")


# ----------------------------------------------------------------------
# Rule 3: bare name -> this repo's own bundled data/<kind>/<name>
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,name",
    [
        ("motors", "Cesaroni_2060K570-17A.eng"),
        ("aero", "example.csv"),
        ("soundings", "example"),
    ],
)
def test_bare_name_resolves_to_bundled_data_dir(kind, name):
    resolved = datafiles.resolve(name, kind)
    assert resolved == os.path.join(_DATA, kind, name)


# ----------------------------------------------------------------------
# Rule 1: absolute path -> used exactly as given
# ----------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["motors", "aero", "soundings"])
def test_windows_absolute_path_returned_unchanged(kind, tmp_path):
    given = str(tmp_path / "somefile.ext")
    assert os.path.isabs(given)  # sanity: tmp_path is Windows-absolute here

    resolved = datafiles.resolve(given, kind)

    assert resolved == given


@pytest.mark.parametrize("kind", ["motors", "aero", "soundings"])
def test_posix_style_absolute_path_is_not_grafted_onto_repo_drive(kind):
    """`/some/abs/path` is absolute per `os.path.isabs` even on Windows
    (no drive letter, but it has a root) -- rule 1 must return it exactly
    as given, never routed through `os.path.join`/`os.path.abspath`
    again, which would silently graft this repo's own drive letter onto
    it (the pre-Step-120 bug this resolver closes)."""
    given = "/some/abs/path"
    assert os.path.isabs(given)  # sanity, documents the Windows quirk

    resolved = datafiles.resolve(given, kind)

    assert resolved == given
    assert resolved.startswith("/")
    assert _REPO_ROOT.replace("\\", "/") not in resolved.replace("\\", "/")


# ----------------------------------------------------------------------
# Rule 2: a relative path containing a separator -> cwd-relative
# ----------------------------------------------------------------------


@pytest.mark.parametrize("given", ["sub/myfile.csv", "./myfile.csv"])
@pytest.mark.parametrize("kind", ["motors", "aero", "soundings"])
def test_cwd_relative_path_resolves_against_getcwd_not_repo_data(
    given, kind, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)

    resolved = datafiles.resolve(given, kind)

    assert resolved == os.path.abspath(given)
    assert resolved.startswith(str(tmp_path))
    # Must NOT have landed under this repo's own bundled data dir.
    assert not resolved.startswith(os.path.join(_DATA, kind))


# ----------------------------------------------------------------------
# End to end: "file.eng#K570" spec survives an absolute path unchanged
# ----------------------------------------------------------------------


def test_designation_fragment_survives_absolute_path_end_to_end(tmp_path):
    external_dir = tmp_path / "external_motors"
    external_dir.mkdir()
    dest = external_dir / "my_motor.eng"
    shutil.copyfile(
        os.path.join(_DATA, "motors", "Cesaroni_2060K570-17A.eng"), dest
    )

    abspath = str(dest)
    assert os.path.isabs(abspath)

    spec = f"{abspath}#K570"
    rec = motor_file.load(spec)

    assert rec.designation == "K570"
    assert rec.m_prop == pytest.approx(0.99)
    assert rec.m_total == pytest.approx(1.685)
    assert rec.manufacturer == "CTI"
