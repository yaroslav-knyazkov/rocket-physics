"""projects/fx27/runs/point/06_cspace_ideal_mass_dm.py -- roadmap
General id 1.6 (see projects/fx27/_docs/roadmap.md). dm-only half of the
old consolidated runs/point/ideal_mass.py (architecture-42 SS42.8):
`pro54_transition_dm`/`pro75_dm` against `rockets_ideal.py` Section B1's
own last regen (this project's own solve) and Section B2's fx27 measured-
delta figure. These rows print a different frame -- "NOT an oracle" --
because no fresh target-apogee-solved oracle exists for them (SS40.8):
fx27's own dm figures are a measured mass/drag delta applied to the
rocket, not a root-find against a stated target, so there is no
apples-to-apples "error vs fx27 solved" to report the way the dc-only
`02_cspace_ideal_mass_dc.py` does.

Run: `python -m projects.fx27.runs.point.06_cspace_ideal_mass_dm`.
"""

from __future__ import annotations

from projects.fx27.data.cspace.rockets_ideal import (
    PRO54_TRANSITION_DM_IDEAL_MASS_KG,
    PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG,
    PRO75_DM_IDEAL_MASS_KG,
    PRO75_DM_IDEAL_OWN_MASS_KG,
)
from projects.fx27.data.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.solvers.point.estimate import estimate_airframe_mass

TARGET_APOGEE_M = 3000.0

# name -> (this project's own last regen from rockets_ideal.py B1, fx27's own dm
# measured-delta figure from rockets_ideal.py B2 -- NOT a target-apogee-solved
# oracle, SS40.8/architecture-40; kept for provenance only, printed for context,
# never framed as "error vs" the way the dc rows are).
_OWN_AND_FX27_DM: "dict[str, tuple[float, float]]" = {
    "pro54_transition_dm": (PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG, PRO54_TRANSITION_DM_IDEAL_MASS_KG),
    "pro75_dm": (PRO75_DM_IDEAL_OWN_MASS_KG, PRO75_DM_IDEAL_MASS_KG),
}


def main(argv=None) -> None:
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
