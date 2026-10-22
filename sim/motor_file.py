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
# Internal: path resolution
# ----------------------------------------------------------------------


def _motors_path(filename: str) -> str:
    # This file's parent directory is <repo>/sim/, so we go up one level
    # to get the repo root, same as sim/thrust_curve.py did before Step 76.
    repo_root = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(repo_root, "data", "motors", filename)


# ----------------------------------------------------------------------
# The .csv reader -- moved verbatim from thrust_curve._load_motor_curve
# ----------------------------------------------------------------------


def _read_csv(filename: str) -> MotorRecord:
    """Read `data/motors/<filename>` as a two-column (time, thrust) CSV.

    The CSV is expected to have a comment/header line (starting with #)
    and then two columns: time [s], thrust [N].  Whitespace is allowed.
    Returns one `MotorRecord` with every metadata field `None`.
    """
    csv_path = _motors_path(filename)

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
        raise ValueError(f"No data found in motor curve '{filename}'")

    # Sort by time and remove duplicates (keep first occurrence)
    order = np.argsort(times)
    times = np.array(times)[order]
    thrusts = np.array(thrusts)[order]
    _, unique_idx = np.unique(times, return_index=True)
    times = times[unique_idx]
    thrusts = thrusts[unique_idx]

    designation = os.path.splitext(os.path.basename(filename))[0]
    return MotorRecord(
        designation=designation,
        times=times,
        thrusts=thrusts,
        source=filename,
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


def _read_rasp(filename: str) -> tuple["MotorRecord", ...]:
    """Read `data/motors/<filename>` as one or more RASP-format records.

    See the module docstring for the grammar. Returns an empty tuple for
    a file with no header lines (e.g. comments only) rather than raising --
    that is a valid, if useless, library of zero records.
    """
    rasp_path = _motors_path(filename)

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
                source=filename,
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
                        f"motor file '{filename}': data row {stripped!r} needs at least "
                        "2 tokens (time, thrust), got 1"
                    )
                times.append(float(tokens[0]))
                thrusts.append(float(tokens[1]))
            else:
                # Header row: starts a new record, flush the previous one.
                if len(tokens) < 7:
                    raise ValueError(
                        f"motor file '{filename}': header row {stripped!r} needs 7 tokens "
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


@functools.lru_cache(maxsize=None)
def records(filename: str) -> tuple[MotorRecord, ...]:
    """Every record in `data/motors/<filename>`, dispatched on extension:
    `.csv` -> the two-column reader (one record, no metadata);
    `.eng` / `.rasp` / anything else -> the RASP reader (N records)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return (_read_csv(filename),)
    return _read_rasp(filename)


@functools.lru_cache(maxsize=None)
def load(spec: str) -> MotorRecord:
    """`"<filename>[#designation]"` -> one record. No fragment and one
    record in the file -> that record. No fragment and several -> KeyError
    listing every designation. Unknown designation -> the same KeyError."""
    filename, _, fragment = spec.partition("#")
    recs = records(filename)

    if fragment:
        for rec in recs:
            if rec.designation == fragment:
                return rec
        available = ", ".join(rec.designation for rec in recs)
        raise KeyError(
            f"unknown motor designation {fragment!r} in {filename!r}; "
            f"available: {available}"
        )

    if len(recs) == 1:
        return recs[0]

    available = ", ".join(rec.designation for rec in recs)
    raise KeyError(
        f"{filename!r} has multiple motor records; specify one with "
        f"'#designation'; available: {available}"
    )
