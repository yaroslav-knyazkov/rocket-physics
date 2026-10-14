"""Tests for `sim/motor_file.py` (Phase 2.16, Step 76:
architecture-32-motor-separation.md SS32.4).

Covers: the real `.eng` fixture (`data/motors/Cesaroni_2060K570-17A.eng`),
the RASP grammar (headers, multi-record files, the `(0,0)` prepend, the
blank-line-vs-run-together record boundary), the `#designation` fragment
in `load()`, the `KeyError` shapes for an unresolved or ambiguous spec,
and the bit-for-bit gate against the pre-Step-76 `.csv` reader.
"""

import os

import numpy as np
import pytest

from sim import motor_file

_MOTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "motors"
)


def _write_temp_motor_file(name: str, text: str):
    """Write `text` to `data/motors/<name>` and return the path, so the
    caller can `os.remove` it in a `finally` block. Mirrors the existing
    `tests/test_thrust_curve.py::test_thrust_interpolation` pattern of
    using a real (temporary) file under `data/motors/` rather than an
    arbitrary directory, since `sim.motor_file.records` only ever looks
    under `data/motors/`.
    """
    path = os.path.join(_MOTORS_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    return path


# ----------------------------------------------------------------------
# The real .eng fixture
# ----------------------------------------------------------------------


def test_cesaroni_eng_header_metadata():
    """Header `K570  54.0 488.00 7-17 0.99000 1.68500 CTI` parses into
    every metadata field exactly, with units converted mm -> m."""
    rec = motor_file.load("Cesaroni_2060K570-17A.eng")

    assert rec.designation == "K570"
    assert rec.diameter == pytest.approx(0.054)
    assert rec.length == pytest.approx(0.488)
    assert rec.delays == "7-17"
    assert rec.m_prop == pytest.approx(0.99)
    assert rec.m_total == pytest.approx(1.685)
    assert rec.manufacturer == "CTI"


def test_cesaroni_eng_zero_point_prepend():
    """The file has 10 raw (t, F) rows, first row (0.04, 892.67) -- t > 0,
    so the RASP reader prepends an explicit (0.0, 0.0) point (D-64)."""
    rec = motor_file.load("Cesaroni_2060K570-17A.eng")

    assert len(rec.times) == 11
    assert rec.times[0] == 0.0
    assert rec.thrusts[0] == 0.0
    # the original first measured point is still there, right after it
    assert rec.times[1] == pytest.approx(0.04)
    assert rec.thrusts[1] == pytest.approx(892.67)


def test_cesaroni_eng_total_impulse_matches_designation():
    """SS32.3.1 F5: the prepend-(0,0) reading gives 2062.223 N*s, which is
    within ~0.2% of the "2060" in the motor's own designation -- an
    independent sanity check on the parser, not just an assertion against
    a number this test itself picked."""
    rec = motor_file.load("Cesaroni_2060K570-17A.eng")

    assert rec.total_impulse == pytest.approx(2062.223, abs=0.01)


def test_cesaroni_eng_propellant_vs_total_mass():
    rec = motor_file.load("Cesaroni_2060K570-17A.eng")

    assert rec.m_total - rec.m_prop == pytest.approx(0.695)


# ----------------------------------------------------------------------
# .csv records carry no metadata -- None, never 0.0
# ----------------------------------------------------------------------


def test_csv_metadata_fields_are_none_not_zero():
    """"Unknown" (.csv has no header) and "zero" (a motor with no
    propellant) must stay distinguishable (SS32.3.3)."""
    rec = motor_file.load("placeholder.csv")

    assert rec.m_prop is None
    assert rec.m_total is None
    assert rec.diameter is None
    assert rec.length is None
    assert rec.delays == ""
    assert rec.manufacturer == ""
    assert rec.designation == "placeholder"


# ----------------------------------------------------------------------
# Multi-record RASP library: #designation fragment, KeyError shapes
# ----------------------------------------------------------------------


_TWO_RECORD_RASP = """\
; first test motor
TestA 29.0 100.0 4-7-10 0.05 0.10 TestMfg
0.0 10.0
0.5 15.0
1.0 5.0

; second test motor
TestB 38.0 150.0 0 0.08 0.18 TestMfg
0.1 20.0
0.6 25.0
1.2 0.0
"""


def test_two_record_rasp_both_parse():
    name = "test_motor_file_tworec.rasp"
    _write_temp_motor_file(name, _TWO_RECORD_RASP)
    try:
        recs = motor_file.records(name)
        assert len(recs) == 2
        designations = {r.designation for r in recs}
        assert designations == {"TestA", "TestB"}

        by_name = {r.designation: r for r in recs}
        # TestA's first row is already t=0.0 -> no prepend
        assert by_name["TestA"].times[0] == 0.0
        assert len(by_name["TestA"].times) == 3
        # TestB's first row is t=0.1 -> prepend applies
        assert by_name["TestB"].times[0] == 0.0
        assert by_name["TestB"].thrusts[0] == 0.0
        assert len(by_name["TestB"].times) == 4

        assert by_name["TestA"].diameter == pytest.approx(0.029)
        assert by_name["TestB"].diameter == pytest.approx(0.038)
    finally:
        os.remove(os.path.join(_MOTORS_DIR, name))


def test_two_record_rasp_fragment_picks_record():
    name = "test_motor_file_tworec_fragment.rasp"
    _write_temp_motor_file(name, _TWO_RECORD_RASP)
    try:
        rec = motor_file.load(f"{name}#TestB")
        assert rec.designation == "TestB"
        assert rec.m_prop == pytest.approx(0.08)
    finally:
        os.remove(os.path.join(_MOTORS_DIR, name))


def test_two_record_rasp_no_fragment_raises_listing_both():
    name = "test_motor_file_tworec_nofragment.rasp"
    _write_temp_motor_file(name, _TWO_RECORD_RASP)
    try:
        with pytest.raises(KeyError) as excinfo:
            motor_file.load(name)
        message = str(excinfo.value)
        assert "TestA" in message
        assert "TestB" in message
    finally:
        os.remove(os.path.join(_MOTORS_DIR, name))


def test_two_record_rasp_bogus_fragment_raises_listing_both():
    name = "test_motor_file_tworec_bogus.rasp"
    _write_temp_motor_file(name, _TWO_RECORD_RASP)
    try:
        with pytest.raises(KeyError) as excinfo:
            motor_file.load(f"{name}#NoSuchMotor")
        message = str(excinfo.value)
        assert "TestA" in message
        assert "TestB" in message
    finally:
        os.remove(os.path.join(_MOTORS_DIR, name))


# ----------------------------------------------------------------------
# Record boundary edge cases: comments-only file, run-together records
# ----------------------------------------------------------------------


def test_comments_only_file_parses_without_crashing():
    name = "test_motor_file_commentsonly.rasp"
    _write_temp_motor_file(name, "; just a comment\n; another comment\n")
    try:
        recs = motor_file.records(name)
        assert recs == ()
    finally:
        os.remove(os.path.join(_MOTORS_DIR, name))


_RUN_TOGETHER_RASP = """\
RunA 10.0 50.0 0 0.01 0.02 Mfg
0.0 1.0
0.2 2.0
RunB 12.0 60.0 0 0.02 0.03 Mfg
0.0 3.0
0.3 4.0
"""


def test_run_together_records_parse_correctly():
    """No blank line between RunA's last data row and RunB's header --
    the next header line alone ends the previous record."""
    name = "test_motor_file_runtogether.rasp"
    _write_temp_motor_file(name, _RUN_TOGETHER_RASP)
    try:
        recs = motor_file.records(name)
        assert len(recs) == 2
        assert recs[0].designation == "RunA"
        assert recs[1].designation == "RunB"

        assert np.array_equal(recs[0].times, np.array([0.0, 0.2]))
        assert np.array_equal(recs[0].thrusts, np.array([1.0, 2.0]))
        assert np.array_equal(recs[1].times, np.array([0.0, 0.3]))
        assert np.array_equal(recs[1].thrusts, np.array([3.0, 4.0]))
    finally:
        os.remove(os.path.join(_MOTORS_DIR, name))


# ----------------------------------------------------------------------
# Bit-for-bit gate: .csv reading through sim.motor_file must be
# byte-identical to the pre-Step-76 sim.thrust_curve._load_motor_curve
# behaviour, for every existing .csv fixture.
# ----------------------------------------------------------------------

# Captured once (before the Step 76 change) from
# sim.thrust_curve._load_motor_curve for each existing .csv fixture.
_PRE_CHANGE_CSV_ARRAYS = {
    "placeholder.csv": (
        [0.0, 0.05, 0.1, 1.6, 2.0],
        [0.0, 150.0, 90.0, 90.0, 0.0],
    ),
    "synthetic_small.csv": (
        [0.0, 0.05, 0.1, 1.2, 1.4],
        [0.0, 60.0, 30.0, 30.0, 0.0],
    ),
    "synthetic_medium_long.csv": (
        [0.0, 0.06, 0.15, 3.1, 3.4],
        [0.0, 80.0, 52.0, 52.0, 0.0],
    ),
    "synthetic_medium_punchy.csv": (
        [0.0, 0.04, 0.1, 1.1, 1.3],
        [0.0, 220.0, 140.0, 140.0, 0.0],
    ),
    "synthetic_large.csv": (
        [0.0, 0.05, 0.12, 1.8, 2.05],
        [0.0, 420.0, 170.0, 170.0, 0.0],
    ),
}


@pytest.mark.parametrize("filename", sorted(_PRE_CHANGE_CSV_ARRAYS))
def test_csv_bit_for_bit_against_pre_change_capture(filename):
    expected_times, expected_thrusts = _PRE_CHANGE_CSV_ARRAYS[filename]

    rec = motor_file.load(filename)

    assert np.array_equal(rec.times, np.array(expected_times))
    assert np.array_equal(rec.thrusts, np.array(expected_thrusts))


@pytest.mark.parametrize("filename", sorted(_PRE_CHANGE_CSV_ARRAYS))
def test_load_motor_curve_delegation_matches_motor_file(filename):
    """`sim.thrust_curve._load_motor_curve` now delegates to
    `sim.motor_file.load`; confirm the two agree exactly, for every
    existing .csv fixture, closing the loop on the delegation itself."""
    from sim.thrust_curve import _load_motor_curve

    times, thrusts = _load_motor_curve(filename)
    rec = motor_file.load(filename)

    assert np.array_equal(times, rec.times)
    assert np.array_equal(thrusts, rec.thrusts)
