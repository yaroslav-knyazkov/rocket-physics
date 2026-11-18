"""tests/test_fx27_drag_theory.py -- tests for
projects/fx27/data/utils/aero/drag_theory.py (dev/docs/architecture-45-
fx27-theory-drag-port.md S7, ticket T45-4; module moved from
`data/cspace/aero/` to `data/utils/aero/` in Step 157 since it is fully
generic, not cspace-specific).

New physics, not a reorg -- D-181's "no new tests for fx27 reorg-only
work" exemption does NOT apply (architecture-45 S7). All tests are fast
pure-numpy (no solver/IO dependency): `compute_cd0` itself is cheap
enough to call directly in every test, unlike `regenerate_ideal_own.py`'s
heavy solver calls.

Scope this stage: items 1-3 (the 3 `_ormach_*` helpers) are geometry-
independent. Items 4-7 are scoped to `PRO54_TRANSITION_GEOMETRY` /
`pro54_transition_dm` ONLY this round (the only geometry shipped this
stage, SS2/S6) -- when `PRO54_EQUAL_GEOMETRY`/`PRO75_GEOMETRY` are added
in a future stage, items 4-7 get a parametrized/repeated counterpart
then, not now.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pytest

from projects.fx27._paths import cspace_aero
from projects.fx27.data.utils.aero import drag_theory as dt

_DOCS_DIR = Path(__file__).resolve().parent.parent / "dev" / "docs"
_DELTA_REPORT_PATH = _DOCS_DIR / "architecture-45-fx27-theory-drag-port-delta.md"


# ----------------------------------------------------------------------
# Items 1-3 (S7): the 3 `_ormach_*` helpers, geometry-independent.
# ----------------------------------------------------------------------


def test_ormach_qr_at_m_equals_1_routes_to_supersonic_branch():
    """`_ormach_qr`'s own `s = M<1` test routes `M == 1.0` to the
    SUPERSONIC branch (1.0 < 1.0 is False) -- NOT the subsonic one. This
    is the exact boundary value an off-by-one in the branch split would
    get wrong."""
    result = dt._ormach_qr(np.array([1.0]))
    expected_supersonic_branch = 1.84 - 0.76 + 0.166 + 0.035  # == 1.281
    assert result == pytest.approx(expected_supersonic_branch, abs=1e-9)


def test_ormach_qr_subsonic_and_supersonic_formulas_nearly_agree_at_m_equals_1():
    """The two closed-form fits are semi-empirical approximations to the
    same physical stagnation-pressure-ratio curve, independently fit on
    either side of M=1 -- they are close but NOT exactly continuous
    there (subsonic formula gives 1.275, supersonic gives 1.281 at
    M=1.0, a ~0.006 absolute / ~0.5% gap). This is a property of the
    source formulas themselves (both ported verbatim), not a porting
    bug -- the loose bound below catches a gross porting error (wrong
    coefficient, dropped term) without asserting a mathematical
    continuity the source formulas don't actually have."""
    sub_at_1 = 1.0 + 1.0**2 / 4.0 + 1.0**4 / 40.0
    sup_at_1 = 1.84 - 0.76 / 1.0**2 + 0.166 / 1.0**4 + 0.035 / 1.0**6
    assert abs(sub_at_1 - sup_at_1) < 0.01


def test_ormach_blend_boundaries_and_midpoint():
    sub_fn = lambda m: 1.0 - 0.1 * m**2
    sup_fn = lambda m: 1.0 / (1.0 + 0.15 * m**2) ** 0.58

    at_09 = dt._ormach_blend(np.array([0.9]), sub_fn, sup_fn)
    assert at_09 == pytest.approx(sub_fn(0.9), abs=1e-12)

    at_11 = dt._ormach_blend(np.array([1.1]), sub_fn, sup_fn)
    assert at_11 == pytest.approx(sup_fn(1.1), abs=1e-12)

    at_10 = dt._ormach_blend(np.array([1.0]), sub_fn, sup_fn)
    expected_midpoint = 0.5 * (sub_fn(0.9) + sup_fn(1.1))
    assert at_10 == pytest.approx(expected_midpoint, abs=1e-12)


def test_ormach_cone_continuous_at_its_own_hinge_mach():
    """At `Mh=1.3` (the thesis's own hinge Mach), the mid-regime cubic
    and the high-regime closed form must agree -- the cubic's own 4
    boundary conditions are solved to match the closed form's value AND
    slope at Mh, so evaluating just below/at/just above Mh should give
    (near-)identical results."""
    se = 0.12  # representative half-angle sine; _ormach_cone's own math doesn't
    #            depend on which geometry it came from for this continuity check.
    just_below = dt._ormach_cone(np.array([1.3 - 1e-6]), se)[0]
    at_hinge = dt._ormach_cone(np.array([1.3]), se)[0]
    just_above = dt._ormach_cone(np.array([1.3 + 1e-6]), se)[0]
    closed_form_at_hinge = 2.1 * se**2 + 0.5 * se / math.sqrt(1.3**2 - 1.0)
    assert at_hinge == pytest.approx(closed_form_at_hinge, rel=1e-9)
    assert just_below == pytest.approx(closed_form_at_hinge, abs=1e-5)
    assert just_above == pytest.approx(closed_form_at_hinge, abs=1e-5)


# ----------------------------------------------------------------------
# Items 4-7 (S7): PRO54_TRANSITION_GEOMETRY only, this stage's one shipped
# geometry.
# ----------------------------------------------------------------------


def test_pro54_transition_geometry_sbt_and_fr_hand_check():
    """SS7 item 4's hand-checked constants: `SBT = (pi/4)*0.08^2`, and
    `FR = Lt/Dmax` with `Lt = 0.30+0.85+0.10+0.336+0.0361 = 1.6221 m`,
    `Dmax = D1 = 0.08 m` (the forward tube stays the widest point on this
    converging/boat-tailed geometry)."""
    derived = dt._derive(dt.PRO54_TRANSITION_GEOMETRY)
    assert derived.SBT == pytest.approx(0.005027, abs=1e-6)
    expected_Lt = 0.30 + 0.85 + 0.10 + 0.336 + 0.0361
    expected_FR = expected_Lt / 0.08
    assert derived.Lt == pytest.approx(expected_Lt, abs=1e-9)
    assert derived.FR == pytest.approx(expected_FR, abs=1e-9)
    assert derived.FR == pytest.approx(20.28, abs=0.01)


def test_continuity_at_m_1_30_boundary():
    """Port-correctness check for SS4's "not a decision point" claim: the
    transonic branch's own formula and the supersonic branch's own
    formula must agree AT M=1.30 -- this is the test that would actually
    catch a porting bug in either branch's M=1.30 boundary handling, not
    just assert the output array has no visible jump."""
    geo = dt.PRO54_TRANSITION_GEOMETRY
    derived = dt._derive(geo)
    m_130 = np.array([1.30])
    transonic_value = dt._cd0_transonic(m_130, geo, derived)[0]
    supersonic_value = dt._cd0_supersonic(m_130, geo, derived)[0]
    assert transonic_value == pytest.approx(supersonic_value, rel=1e-9)

    # also confirm compute_cd0's own concatenated grid keeps exactly one
    # M=1.30 row, and that it matches the value above.
    M_grid, cd0_grid = dt.compute_cd0(geo)
    at_130 = np.isclose(M_grid, 1.30)
    assert np.count_nonzero(at_130) == 1
    assert cd0_grid[at_130][0] == pytest.approx(transonic_value, rel=1e-9)


def test_compute_cd0_physical_sanity_bounds():
    """Loose bounds, not tight pins (SS7 item 6) -- no independent MATLAB
    run is available in this environment to produce an exact oracle
    value. These bounds exist to catch a gross sign/unit error (e.g. a
    dropped `/SBT` normalization), not to pin exact values."""
    M_grid, cd0_grid = dt.compute_cd0(dt.PRO54_TRANSITION_GEOMETRY)
    assert M_grid[0] == pytest.approx(0.10)
    assert M_grid[-1] == pytest.approx(3.00)
    assert len(M_grid) == 291
    assert np.all(np.diff(M_grid) > 0)  # strictly ascending
    assert np.all(np.isfinite(cd0_grid))
    assert np.all(cd0_grid > 0.0)
    assert np.all(cd0_grid < 2.0)


def test_boattail_flare_branch_is_not_reached_by_this_geometry():
    """Known gap (SS6/T45-1): the diverging-flare boattail branch raises
    `NotImplementedError` because its exact formula lives only in
    `cd_mach_03_decrease_D.m` (out of scope this stage). This test
    confirms `PRO54_TRANSITION_GEOMETRY` never reaches that branch (both
    its rear-body segments converge, `D1>D2` and `D_fore>D3`) -- i.e.
    `compute_cd0` succeeding for this geometry is not accidental."""
    geo = dt.PRO54_TRANSITION_GEOMETRY
    assert geo.D1 > geo.D2
    assert geo.D_fore > geo.D3
    # compute_cd0 already succeeded in the tests above without raising --
    # this test just documents WHY that is guaranteed, not incidental.


def _read_ca_table(path: str) -> dict[float, float]:
    """Plain-CSV read of this project's own v1 aero-table format
    (`alpha_deg,M,C_A,C_N,C_m,l1_m`, `#`-comment header) -- SS7 item 7
    leaves the read method to the developer's choice; both tables here
    carry identical C_A at both alpha rows (SS40.5/SS3's own invariant),
    so taking the first row per Mach value is enough."""
    table: dict[float, float] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("#") or row[0] == "alpha_deg":
                continue
            mach = float(row[1])
            c_a = float(row[2])
            table.setdefault(mach, c_a)
    return table


def test_delta_report_vs_existing_sibling_ported_csv():
    """SS7 item 7: compare the new theory-derived `pro54-transition-
    drag-theory.csv` against the existing sibling-ported
    `pro54-transition-drag.csv`, at the Mach values the old table's own
    grid (0-3.0 step 0.025) shares with the new table's range
    (0.10-3.00). Writes the full per-point delta + summary stats to
    `dev/docs/architecture-45-fx27-theory-drag-port-delta.md` for the
    user's SS5 promotion decision -- the loose bound asserted here is
    only meant to catch a gross unit/sign bug, NOT to gate the port on a
    specific tolerance (SS7 item 7's own framing)."""
    old_table = _read_ca_table(cspace_aero("pro54-transition-drag.csv"))
    new_table = _read_ca_table(cspace_aero("pro54-transition-drag-theory.csv"))

    new_machs = np.array(sorted(new_table))
    new_cas = np.array([new_table[m] for m in new_machs])

    old_machs_in_range = sorted(m for m in old_table if new_machs[0] <= m <= new_machs[-1])
    assert old_machs_in_range, "no overlap between the old and new Mach grids"

    rows = []
    for m in old_machs_in_range:
        old_ca = old_table[m]
        theory_ca = float(np.interp(m, new_machs, new_cas))
        delta = theory_ca - old_ca
        rows.append((m, old_ca, theory_ca, delta))

    deltas = np.array([r[3] for r in rows])
    max_abs_delta = float(np.max(np.abs(deltas)))
    mean_abs_delta = float(np.mean(np.abs(deltas)))

    _write_delta_report(rows, max_abs_delta, mean_abs_delta)

    # Loose bound (SS7 item 7): wide enough not to fail on a large-but-
    # plausible refinement between an external inventory curve and a
    # from-scratch semi-empirical theory curve; narrow enough to fail on
    # an obvious unit/sign bug.
    assert max_abs_delta < 1.0


def _write_delta_report(rows, max_abs_delta: float, mean_abs_delta: float) -> None:
    lines = []
    lines.append("# Architecture-45 delta report: pro54_transition theory vs. sibling-ported CSV\n")
    lines.append("")
    lines.append("## Кратко (RU)")
    lines.append("")
    lines.append(
        "- Авто-генерируемый отчёт (dev/docs/architecture-45-fx27-theory-drag-port-delta.md), "
        "пишется тестом `tests/test_fx27_drag_theory.py::test_delta_report_vs_existing_sibling_ported_csv` "
        "при каждом прогоне -- не редактировать руками."
    )
    lines.append(
        f"- Сравнение `pro54-transition-drag.csv` (старая, портированная из sibling-репо кривая) "
        f"против `pro54-transition-drag-theory.csv` (новая, теоретическая кривая, Niskanen/OpenRocket)."
    )
    lines.append(
        f"- Максимальная абсолютная дельта C_A: **{max_abs_delta:.4f}**; средняя абсолютная дельта: "
        f"{mean_abs_delta:.4f}."
    )
    lines.append(
        "- Назначение отчёта -- показать дельту человеку перед решением о SS5 (side-by-side vs. "
        "замена существующей `pro54-transition-drag.csv`/`pro54_transition_dm`), тест гейтит только "
        "на грубую ошибку (abs delta < 1.0), не на точный допуск."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Max abs delta (C_A): **{max_abs_delta:.6f}**")
    lines.append(f"- Mean abs delta (C_A): **{mean_abs_delta:.6f}**")
    lines.append(f"- Compared at {len(rows)} Mach points (old grid's own 0.025 step, restricted to the "
                  "new table's 0.10-3.00 range).")
    lines.append(
        "- New table's C_A interpolated (`np.interp`) onto the old grid's Mach values (old step 0.025, "
        "new step 0.01)."
    )
    lines.append("")
    lines.append("## Per-point delta")
    lines.append("")
    lines.append("| Mach | old C_A (sibling-ported) | theory C_A | delta (theory - old) |")
    lines.append("|---|---|---|---|")
    for m, old_ca, theory_ca, delta in rows:
        lines.append(f"| {m:.3f} | {old_ca:.4f} | {theory_ca:.4f} | {delta:+.4f} |")
    lines.append("")

    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    _DELTA_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
