"""Motor file readers: `.csv` (one record, no metadata) and the RASP
grammar (`.eng` / `.rasp` / anything else, N records per file).

Phase 2.16, Step 76 (architecture-32-motor-separation.md SS32.4, D-63..D-65).
`sim/thrust_curve.py` owns the force-model seam (`thrust(t, s, p)`) and
depends on `sim.atmosphere` for the pressure correction; this module owns
file grammars and the header metadata (`m_prop`, `m_total`, `diameter`,
`length`, `delays`, `manufacturer`) that `configs/schema.py` needs at
assembly time without dragging a force model (and `sim.atmosphere`) into
the config import graph. `Thrust.motor_curve` is already "the file,
extension included" (F7), so no new `Params` field is added: a motor is
named by `"<filename>"` (one record, or the file's only record) or
`"<filename>#<designation>"` (one record out of a multi-record library).

The RASP grammar: `;`-prefixed lines are comments; a header line is a
non-comment line whose first whitespace-separated token does not parse as
a float (`designation diameter_mm length_mm delays m_prop_kg m_total_kg
manufacturer`, `delays` free text, never parsed, `manufacturer` free text
to end of line -- joined back together even when it is itself several
whitespace-separated tokens, e.g. "Cesaroni Technology"); every other non-comment,
non-blank line is a `time thrust` data row (extra columns beyond the first
two are ignored, matching the `.csv` reader's tolerance). A record ends at
the next header line or EOF -- blank lines are not load-bearing, so both
the blank-line-delimited and the run-together conventions parse the same
way. `diameter_mm`/`length_mm` are converted to metres at parse time.
**If a RASP record's first data row has `t > 0`, an explicit `(0.0, 0.0)`
point is prepended** (D-64): the first row is the first *measured* point
after ignition, not a pre-ignition hold, and holding it from `t = 0`
manufactures impulse the motor never produced (SS32.3.1 F5). This prepend
applies to the RASP reader only -- `.csv` loading is unchanged, byte for
byte, so every existing config stays bit-for-bit.
"""

import csv
import dataclasses
import functools
import os

import numpy as np

from sim import datafiles

# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MotorRecord:
    """One motor's curve plus whatever its file told us about it. Every
    metadata field is `None` for a format that does not carry it (every
    `.csv`), never 0.0 -- "unknown" and "zero" are different answers and
    the mass model must be able to tell them apart (SS32.3.3)."""

    designation: str  # "K570", or the filename stem for a .csv
    times: np.ndarray  # s,  ascending, de-duplicated
    thrusts: np.ndarray  # N
    m_prop: float | None = None  # kg   <- RASP header field 5
    m_total: float | None = None  # kg   <- RASP header field 6
    # Conventions audit SS11: the RASP spec gives these two fields in kg
    # despite the field names ("prop-weight"/"total-weight"); some older
    # third-party .eng files in circulation use grams instead, and there is
    # no in-band way to tell one from the other -- not checked here.
    diameter: float | None = None  # m    <- RASP header field 2 (mm in file)
    length: float | None = None  # m    <- RASP header field 3 (mm in file)
    delays: str = ""  #      <- RASP header field 4, free text, never parsed
    manufacturer: str = ""  #      <- RASP header field 7
    source: str = ""  # the file it came from, for error messages

    @property
    def total_impulse(self) -> float:  # N*s -- SS32.3.4's J
        return float(np.trapezoid(self.thrusts, self.times))


# ----------------------------------------------------------------------
# Back-compat shim (Step 120, D-137/F5)
# ----------------------------------------------------------------------


def _motors_path(filename: str) -> str:
    """Resolves exactly like `sim.datafiles.resolve(filename, "motors")`.
    Kept as a thin wrapper around the new resolver because external
    callers (`apps/motor_selection/scenario_sweep.py`,
    `tests/test_scenario_sweep.py`) reach for this private helper
    directly to stat/hash the on-disk motor file, independent of this
    module's own record-parsing cache."""
    return datafiles.resolve(filename, "motors")


# ----------------------------------------------------------------------
# The .csv reader -- moved verbatim from thrust_curve._load_motor_curve
# ----------------------------------------------------------------------


def _read_csv(csv_path: str) -> MotorRecord:
    """Read `csv_path` (already resolved by `sim.datafiles.resolve`) as a
    two-column (time, thrust) CSV.

    The CSV is expected to have a comment/header line (starting with #)
    and then two columns: time [s], thrust [N].  Whitespace is allowed.
    Returns one `MotorRecord` with every metadata field `None`.
    """
    times = []
    thrusts = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].strip().startswith("#"):
                continue
            # Allow extra columns (e.g. units) - we only need the first two.
            t_str, f_str = row[0], row[1]
            times.append(float(t_str))
            thrusts.append(float(f_str))

    if not times:
        raise ValueError(f"No data found in motor curve '{csv_path}'")

    # Sort by time and remove duplicates (keep first occurrence)
    order = np.argsort(times)
    times = np.array(times)[order]
    thrusts = np.array(thrusts)[order]
    _, unique_idx = np.unique(times, return_index=True)
    times = times[unique_idx]
    thrusts = thrusts[unique_idx]

    designation = os.path.splitext(os.path.basename(csv_path))[0]
    return MotorRecord(
        designation=designation,
        times=times,
        thrusts=thrusts,
        source=csv_path,
    )


# ----------------------------------------------------------------------
# The RASP reader -- .eng / .rasp / anything else that isn't .csv
# ----------------------------------------------------------------------


def _is_float(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def _read_rasp(rasp_path: str) -> tuple["MotorRecord", ...]:
    """Read `rasp_path` (already resolved by `sim.datafiles.resolve`) as
    one or more RASP-format records.

    See the module docstring for the grammar. Returns an empty tuple for
    a file with no header lines (e.g. comments only) rather than raising --
    that is a valid, if useless, library of zero records.
    """
    out: list[MotorRecord] = []

    designation = None
    diameter = length = m_prop = m_total = None
    delays = manufacturer = ""
    times: list[float] = []
    thrusts: list[float] = []

    def flush() -> None:
        if designation is None:
            return
        t_arr = np.array(times, dtype=float)
        f_arr = np.array(thrusts, dtype=float)
        if t_arr.size and t_arr[0] > 0.0:
            t_arr = np.concatenate(([0.0], t_arr))
            f_arr = np.concatenate(([0.0], f_arr))
        out.append(
            MotorRecord(
                designation=designation,
                times=t_arr,
                thrusts=f_arr,
                m_prop=m_prop,
                m_total=m_total,
                diameter=diameter,
                length=length,
                delays=delays,
                manufacturer=manufacturer,
                source=rasp_path,
            )
        )

    with open(rasp_path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue  # blank lines are not load-bearing
            if stripped.startswith(";"):
                continue  # comment line, discarded

            tokens = stripped.split()
            if _is_float(tokens[0]):
                # Data row: time, thrust (extra columns ignored).
                if len(tokens) < 2:
                    raise ValueError(
                        f"motor file '{rasp_path}': data row {stripped!r} needs at least "
                        "2 tokens (time, thrust), got 1"
                    )
                times.append(float(tokens[0]))
                thrusts.append(float(tokens[1]))
            else:
                # Header row: starts a new record, flush the previous one.
                if len(tokens) < 7:
                    raise ValueError(
                        f"motor file '{rasp_path}': header row {stripped!r} needs 7 tokens "
                        "(designation diameter_mm length_mm delays m_prop_kg m_total_kg "
                        f"manufacturer), got {len(tokens)}"
                    )
                flush()
                designation = tokens[0]
                diameter = float(tokens[1]) / 1000.0
                length = float(tokens[2]) / 1000.0
                delays = tokens[3]
                m_prop = float(tokens[4])
                m_total = float(tokens[5])
                # Real headers carry multi-word manufacturers ("Cesaroni
                # Technology"); join everything from field 7 on instead of
                # truncating to one token (conventions audit §6 item 1).
                manufacturer = " ".join(tokens[6:])
                times = []
                thrusts = []

    flush()

    return tuple(out)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def _records_impl(abspath: str) -> tuple[MotorRecord, ...]:
    ext = os.path.splitext(abspath)[1].lower()
    if ext == ".csv":
        return (_read_csv(abspath),)
    return _read_rasp(abspath)


_records_cached = functools.lru_cache(maxsize=None)(_records_impl)


def records(filename: str) -> tuple[MotorRecord, ...]:
    """Every record in `data/motors/<filename>`, dispatched on extension:
    `.csv` -> the two-column reader (one record, no metadata);
    `.eng` / `.rasp` / anything else -> the RASP reader (N records).

    `filename` is resolved via `sim.datafiles.resolve` ("motors") before
    the lookup, and the cache sits on the *resolved* absolute path, not
    the raw `filename` string -- a cwd-relative name is never served a
    stale resolution across a change of working directory between two
    calls with the same string (see `sim/datafiles.py`'s docstring)."""
    abspath = datafiles.resolve(filename, "motors")
    return _records_cached(abspath)


records.cache_clear = _records_cached.cache_clear


def _load_impl(abspath: str, fragment: str) -> MotorRecord:
    recs = _records_cached(abspath)

    if fragment:
        for rec in recs:
            if rec.designation == fragment:
                return rec
        available = ", ".join(rec.designation for rec in recs)
        raise KeyError(
            f"unknown motor designation {fragment!r} in {abspath!r}; "
            f"available: {available}"
        )

    if len(recs) == 1:
        return recs[0]

    available = ", ".join(rec.designation for rec in recs)
    raise KeyError(
        f"{abspath!r} has multiple motor records; specify one with "
        f"'#designation'; available: {available}"
    )


_load_cached = functools.lru_cache(maxsize=None)(_load_impl)


def load(spec: str) -> MotorRecord:
    """`"<filename>[#designation]"` -> one record. No fragment and one
    record in the file -> that record. No fragment and several -> KeyError
    listing every designation. Unknown designation -> the same KeyError.

    `spec.partition("#")` splits the fragment *before* any path handling
    (preserved from before Step 120): the filename part is resolved via
    `sim.datafiles.resolve`, the fragment is never touched by path
    resolution. The cache sits on `(resolved abspath, fragment)`, not the
    raw `spec` string, for the same stale-cwd reason as `records()`."""
    filename, _, fragment = spec.partition("#")
    abspath = datafiles.resolve(filename, "motors")
    return _load_cached(abspath, fragment)


load.cache_clear = _load_cached.cache_clear
