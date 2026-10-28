"""Entry point / scenario definition.

Step 4: vertical flight under gravity, constant thrust and a constant axial
aerodynamic force.

Step 7: full Phase 1 output -- trajectory + pitch plots and a printed flight
summary.

Step 14: thrust is now a real (time, thrust) curve (sim/thrust_curve.py,
selected via `motor_curve`) instead of the constant-thrust/T_BURN hack;
the summary now also prints the burnout time from `result.events`.

Step 27: on top of the single-run scenario above (unchanged), a small
model-comparison sweep -- the payoff for the dispatch-dict selection
pattern (architecture.md SS12): `params.replace(p, {<dotted.path>:
<value>})` (architecture-28-rewrite.md SS28.4) per variant, one `run_sim`
each, a printed summary table and an overlay plot. Two comparisons: the
four gravity models, and ISA vs. a real sounding (station LKPR).

Step 58 (architecture-28-rewrite.md SS28.9): this module is scenario
definition only now -- which `Params`, which sweep field/values/title.
The summary printing, plot building, PNG/CSV saving and sweep machinery
(`flight_summary`, `sweep`, `print_sweep_table`, `print_run_summary`,
`save_run_artifacts`, `save_sweep_artifacts`, `run_sweep`) all moved to
`sim/report.py`, the orchestration layer above `sim/plotting.py`.

Step 69 (architecture-30-apps-4-5-and-configs.md SS30.3): this is entry
point 1 of 5 -- the other four live under `apps/`, reached either via
their own `python -m apps....` invocation or their root wrapper
(`run_motor_sweep.py`, `run_airbrake.py`, `run_cfd_conditions.py`,
`run_trade.py`).
"""

from apps.input.demo_scenario import DEMO_SCENARIO
from sim import report
from sim.integrate import run_sim
from sim.params import replace as params_replace


def main() -> None:
    # Step 123 (Phase 2.18, D-139/D-140), moved to apps/input/ at Step 130:
    # the one demo (apps/input/demo_scenario.py -- a real Cesaroni K570 on
    # a 54 mm airframe, mass model ON) instead of the former 0.5 kg toy;
    # single source of truth shared with App 2
    # (apps/analysis/cfd_conditions/select_conditions.py).
    cfg = DEMO_SCENARIO.config
    params = cfg.params
    state0 = cfg.s0

    result = run_sim(params, state0)

    report.print_run_summary(result, params, state0)
    report.save_run_artifacts(result, params)

    # ------------------------------------------------------------------
    # Step 27: model comparison sweeps (architecture.md SS12). Additional
    # output on top of the single run above -- that run and its summary
    # are unaffected by anything below.
    # ------------------------------------------------------------------

    # (a) The three gravity models, at this scenario's own apogee scale
    # (the demo's, ~5.9 km), where roadmap.md Step 27
    # expects them to differ "by a predictable, small amount" -- same base
    # scenario as the single run above (aero.model="constant" here, so
    # gravity is the only thing varying). "linear" was removed at Phase 2.5
    # Step 34.
    report.run_sweep(
        params, "gravity.model", ("constant", "radial", "wgs84"), state0,
        title="Gravity model comparison",
    )

    # (b) ISA vs. a real sounding (station LKPR, data/soundings/example,
    # Step 17), where roadmap.md Step 27 expects the comparison to "show
    # where the real atmosphere matters". Uses aero.model="linearized" so
    # alpha actually drives a nonzero normal-force/moment slope (every
    # aero model is atmosphere-coupled since Step 55 -- architecture.md
    # SS12 -- so "constant" would no longer make this comparison vacuous
    # the way it used to; "linearized" is kept here for its C_N_alpha/
    # C_m_alpha slope, not because "constant" is somehow atmosphere-blind)
    # and h0_m=380.0 to match LKPR's own station elevation, so the flight
    # stays inside the station's measured data -- same setup Step 18's own
    # tests used (tests/test_atmosphere.py's `_AERO_KW`/`common`).
    atmo_base = params_replace(
        params,
        {
            "aero.model": "linearized",
            "aero.C_A0": 0.5,
            "aero.C_N_alpha": 2.0,
            "aero.C_m_alpha": -0.5,
            "site.h0_m": 380.0,
            "soundings.case": "example",
        },
    )
    report.run_sweep(
        atmo_base, "atmosphere.model", ("isa", "sounding"), state0,
        title="Atmosphere model comparison (station LKPR)",
        plot_title="Atmosphere model comparison (LKPR)",
    )


if __name__ == "__main__":
    main()
