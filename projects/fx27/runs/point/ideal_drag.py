"""projects/fx27/runs/point/ideal_drag.py -- fx27 `runs/cspace/
ideal_drag_estimation.py` equivalent (dev/docs/architecture-38-fx27-
port.md SS38.5.4, #14): `estimate_cx` for `pro54_transition` and
`pro75`, target 3000 m AGL.

This is the half of AC-3 where the port's own measured divergence is
largest: `pro54_transition`'s C_x case measured +7.35% against fx27's
0.2351 (accepted by the user, 2026-11, as a documented caveat rather than
a block -- see `dev/docs/fx27-port-progress-notes.md`, "STOP: AC-3
measured failure", for the full diagnosis: this is risk R1, SS38.10,
materialising for the lightest/fastest cspace vehicle, not an
implementation defect). `pro75`'s own case has no such caveat (+1.16%).

Architecture-42 SS42.8 adds 2 dm rows below the dc oracle rows above, via
`estimate_cx_scale` (the Mach-table analogue of `estimate_cx`):
`pro54_transition_dm`/`pro75_dm` against `rockets_ideal.py` Section B1's
own last regen and Section B2's fx27 measured-delta figure. Same "NOT an
oracle" framing as `ideal_mass.py`'s dm rows -- SS40.8: no fresh
target-apogee-solved oracle exists for these dm figures.

Run: `python -m projects.fx27.runs.point.ideal_drag`.
"""

from __future__ import annotations

from projects.fx27.campaigns.cspace.rockets_ideal import (
    PRO54_TRANSITION_DM_IDEAL_DRAG_CX_SCALE,
    PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE,
    PRO54_TRANSITION_IDEAL_DRAG_CX,
    PRO75_DM_IDEAL_DRAG_CX_SCALE,
    PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE,
    PRO75_IDEAL_DRAG_CX,
)
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.solvers.point.estimate import estimate_cx, estimate_cx_scale

TARGET_APOGEE_M = 3000.0

# name -> fx27's own hardcoded solved figure (cspace/rockets_ideal.py)
_FX27_SOLVED: "dict[str, float]" = {
    "pro54_transition": PRO54_TRANSITION_IDEAL_DRAG_CX,
    "pro75": PRO75_IDEAL_DRAG_CX,
}

# name -> known caveat (printed under that row only; see module docstring)
_CAVEAT: "dict[str, str]" = {
    "pro54_transition": (
        "    NOTE: measured error for this vehicle exceeds the 5% band (accepted, user "
        "decision 2026-11) -- see dev/docs/fx27-port-progress-notes.md."
    ),
}

# name -> (this project's own last regen from rockets_ideal.py B1, fx27's own dm
# measured-delta figure from rockets_ideal.py B2 -- NOT a target-apogee-solved
# oracle, SS40.8/architecture-40; kept for provenance only, printed for context,
# never framed as "error vs" the way the dc rows above are). `_CAVEAT` above is
# dc-only and untouched -- it keys off scenario names that never collide with
# these dm names, so no guard is needed to keep it from accidentally firing here.
_OWN_AND_FX27_DM: "dict[str, tuple[float, float]]" = {
    "pro54_transition_dm": (PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE, PRO54_TRANSITION_DM_IDEAL_DRAG_CX_SCALE),
    "pro75_dm": (PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE, PRO75_DM_IDEAL_DRAG_CX_SCALE),
}


def main(argv=None) -> None:
    for name, fx27_value in _FX27_SOLVED.items():
        res = estimate_cx(SCENARIOS[name], target_apogee_agl=TARGET_APOGEE_M)
        err_pct = 100.0 * (res.required - fx27_value) / fx27_value
        print(
            f"{name}: baseline={res.baseline:.4f}, required={res.required:.4f} "
            f"(fx27 solved={fx27_value:.4f}, error {err_pct:+.2f}%), "
            f"achieved apogee={res.achieved_apogee_m:.1f} m, reachable={res.reachable}"
        )
        if name in _CAVEAT:
            print(_CAVEAT[name])

    for name, (own_regen, fx27_measured) in _OWN_AND_FX27_DM.items():
        res = estimate_cx_scale(SCENARIOS_DM[name], target_apogee_agl=TARGET_APOGEE_M)
        drift_pct = 100.0 * (res.required - own_regen) / own_regen
        print(
            f"{name}: baseline={res.baseline:.4f}, required={res.required:.4f} "
            f"(this project's own last regen={own_regen:.4f}, drift {drift_pct:+.2f}%), "
            f"fx27 measured-delta figure={fx27_measured:.4f} [NOT an oracle -- SS40.8: no "
            "target-apogee solve backs this number, provenance only], "
            f"achieved apogee={res.achieved_apogee_m:.1f} m, reachable={res.reachable}"
        )


if __name__ == "__main__":
    main()
