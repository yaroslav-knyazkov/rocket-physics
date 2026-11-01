"""projects/fx27/runs/cspace_ideal_drag.py -- fx27 `runs/cspace/
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

Run: `python -m projects.fx27.runs.cspace_ideal_drag`.
"""

from __future__ import annotations

from projects.fx27.cspace.rockets_ideal import PRO54_TRANSITION_IDEAL_DRAG_CX, PRO75_IDEAL_DRAG_CX
from projects.fx27.cspace.scenarios import SCENARIOS
from projects.fx27.point.estimate import estimate_cx

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


if __name__ == "__main__":
    main()
