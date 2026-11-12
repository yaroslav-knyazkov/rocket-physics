"""projects/fx27/runs/cspace/ideal_mass.py -- fx27 `runs/cspace/
ideal_mass_estimation.py` equivalent (dev/docs/architecture-38-fx27-
port.md SS38.5.4, #13): `estimate_airframe_mass` for `pro54_transition`
and `pro75`, target 3000 m AGL.

This is AC-3's oracle check, run as a script -- the pytest gate lives in
`tests/test_fx27_port.py`. See `dev/docs/fx27-port-progress-notes.md`
("STOP: AC-3 measured failure") for the user-accepted diagnosis of the
`pro54_transition` C_x case's larger error (a different quantity than
this script estimates, but the same underlying divergence): this
script's own two mass figures both measured within 5% and carry no
caveat.

Architecture-42 SS42.8 adds 2 dm rows below the dc oracle rows above:
`pro54_transition_dm`/`pro75_dm` against `rockets_ideal.py` Section B1's
own last regen (this project's own solve) and Section B2's fx27 measured-
delta figure. The dm rows print a different frame -- "NOT an oracle" --
because no fresh target-apogee-solved oracle exists for them (SS40.8):
fx27's own dm figures are a measured mass/drag delta applied to the
rocket, not a root-find against a stated target, so there is no
apples-to-apples "error vs fx27 solved" to report the way the dc rows
above do.

Run: `python -m projects.fx27.runs.cspace.ideal_mass`.
"""

from __future__ import annotations

from projects.fx27.campaigns.cspace.rockets_ideal import (
    PRO54_TRANSITION_DM_IDEAL_MASS_KG,
    PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG,
    PRO54_TRANSITION_IDEAL_MASS_KG,
    PRO75_DM_IDEAL_MASS_KG,
    PRO75_DM_IDEAL_OWN_MASS_KG,
    PRO75_IDEAL_MASS_KG,
)
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.point.estimate import estimate_airframe_mass

TARGET_APOGEE_M = 3000.0

# name -> fx27's own hardcoded solved figure (cspace/rockets_ideal.py)
_FX27_SOLVED: "dict[str, float]" = {
    "pro54_transition": PRO54_TRANSITION_IDEAL_MASS_KG,
    "pro75": PRO75_IDEAL_MASS_KG,
}

# name -> (this project's own last regen from rockets_ideal.py B1, fx27's own dm
# measured-delta figure from rockets_ideal.py B2 -- NOT a target-apogee-solved
# oracle, SS40.8/architecture-40; kept for provenance only, printed for context,
# never framed as "error vs" the way the dc rows above are).
_OWN_AND_FX27_DM: "dict[str, tuple[float, float]]" = {
    "pro54_transition_dm": (PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG, PRO54_TRANSITION_DM_IDEAL_MASS_KG),
    "pro75_dm": (PRO75_DM_IDEAL_OWN_MASS_KG, PRO75_DM_IDEAL_MASS_KG),
}


def main(argv=None) -> None:
    for name, fx27_value in _FX27_SOLVED.items():
        res = estimate_airframe_mass(SCENARIOS[name], target_apogee_agl=TARGET_APOGEE_M)
        err_pct = 100.0 * (res.required - fx27_value) / fx27_value
        print(
            f"{name}: baseline={res.baseline:.4f} kg, required={res.required:.4f} kg "
            f"(fx27 solved={fx27_value:.4f} kg, error {err_pct:+.2f}%), "
            f"achieved apogee={res.achieved_apogee_m:.1f} m, reachable={res.reachable}"
        )

    for name, (own_regen, fx27_measured) in _OWN_AND_FX27_DM.items():
        res = estimate_airframe_mass(SCENARIOS_DM[name], target_apogee_agl=TARGET_APOGEE_M)
        drift_pct = 100.0 * (res.required - own_regen) / own_regen
        print(
            f"{name}: baseline={res.baseline:.4f} kg, required={res.required:.4f} kg "
            f"(this project's own last regen={own_regen:.4f} kg, drift {drift_pct:+.2f}%), "
            f"fx27 measured-delta figure={fx27_measured:.4f} kg [NOT an oracle -- SS40.8: no "
            "target-apogee solve backs this number, provenance only], "
            f"achieved apogee={res.achieved_apogee_m:.1f} m, reachable={res.reachable}"
        )


if __name__ == "__main__":
    main()
