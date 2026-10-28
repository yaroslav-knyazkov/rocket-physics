"""apps/sim/engine/datafiles.py -- Data-file/directory path resolution: one 3-rule function, shared by
every loader that reads from `data/<kind>/` (`apps/sim/engine/motor_file.py`,
`apps/sim/engine/aero.py`, `apps/sim/engine/soundings.py`).

Phase 2.18, Step 120 (D-137/F5). Before this step, each of the three
loaders carried its own 2-line "resolve relative to this repo's own
`data/`" helper, hardcoding `os.path.dirname(os.path.dirname(__file__))`
as the only possible base. That is correct for a *bare* filename (a
config referring to one of this library's own bundled data files) but
silently wrong for anything an external user supplies once this project
is installed as a package (Step 121): an absolute path got this repo's
own path grafted onto it via `os.path.join` (a POSIX-style absolute path
like `/some/file` is especially dangerous here -- `os.path.join` keeps
only the last absolute-looking component's root, silently discarding the
repo root but keeping *this machine's* drive letter), and a path meant to
be relative to the *user's* current working directory was instead always
resolved against this library's own install location.

Three rules, in priority order:

1. `given` is absolute (`os.path.isabs`) -> used exactly as given. This
   also covers a POSIX-style root-absolute path on Windows (`/foo/bar`
   is absolute per `os.path.isabs`, even with no drive letter) -- it is
   returned unchanged, never run through `os.path.join`/`os.path.abspath`
   again, so no drive letter is silently grafted onto it.
2. `given` contains a path separator but is not absolute -- e.g.
   `"sub/myfile.csv"`, `"./myfile.csv"` -- -> resolved against the
   *caller's* current working directory (`os.getcwd()`, read at call
   time, never cached), not this repo's own location. An external user's
   cwd-relative path.
3. `given` is a bare name (no separator at all) -> this library's own
   bundled `examples/data/<kind>/<given>`, preserved byte-for-byte for every name
   already registered/tested in this repo -- today's only behaviour,
   now one of three.

Caching note (see the three call sites): rule 2's resolution depends on
`os.getcwd()` at call time, so a cache keyed on the raw `given` string
would silently serve a stale resolution if the cwd changes between two
calls with the same relative string. Each call site resolves first (this
function, uncached) and caches on the *resolved* absolute path.

Phase 2.19 (Step 127, dev/docs/architecture-apps-sim-restructure.md
SS4.4/SS5): the import-time check below (`BundledDataMissingError`) was
added one step before `_BUNDLED`'s target actually moved, so that a
later `git mv` of `data/` that forgot to update `_BUNDLED` would fail
loudly here instead of resolving bare data-file names to a silently
missing directory until some unrelated loader tripped over a
`FileNotFoundError` far from the actual cause.

Step 129 is that move: `_BUNDLED` now points at `<repo>/examples/data`
(bundled example motors/aero/soundings fixtures, read by the test suite
and this repo's own example scenarios), not `<repo>/data` (gitignored,
the user's own personal data -- see `data/README.md`). `tests/datadir.py`
holds the test-side mirror of this same `examples/data` anchor.
"""

import os


class BundledDataMissingError(RuntimeError):
    """`apps/sim/engine/datafiles.py`'s `_BUNDLED` directory (bare-name data lookups,
    rule 3 above) does not exist. Raised at import time so a later `git
    mv` of `data/` that forgets to update `_BUNDLED` fails immediately
    and loudly here, instead of resolving bare data-file names to a
    silently-missing directory until some unrelated loader trips over a
    `FileNotFoundError` far from the actual cause."""


_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "examples", "data")

if not os.path.isdir(_BUNDLED):
    raise BundledDataMissingError(
        f"apps/sim/engine/datafiles.py expects its bundled data directory at {_BUNDLED!r} "
        "(bare-name motor/aero/soundings lookups resolve here, rule 3 of this "
        "module's docstring) -- it does not exist. If `data/` just moved, "
        "update `_BUNDLED` in apps/sim/engine/datafiles.py to match its new location."
    )


def resolve(given: str, kind: str) -> str:
    """Resolve a data-file/dir name for `kind` in {"motors", "aero",
    "soundings"}. See the module docstring for the three rules."""
    if os.path.isabs(given):
        return given
    if os.sep in given or "/" in given:
        return os.path.abspath(given)
    return os.path.join(_BUNDLED, kind, given)
