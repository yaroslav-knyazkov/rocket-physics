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
pattern (architecture.md SS12): `dataclasses.replace(p, <field>=<value>)`
per variant, one `run_sim` each, a printed summary table and an overlay
plot. Two comparisons: the four gravity models, and ISA vs. a real
sounding (station LKPR).
"""

import dataclasses
import math

import numpy as np
import matplotlib.pyplot as plt

from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Params
from sim.plotting import plot_time_histories, plot_trajectory, plot_trajectory_overlay
from sim.state import State, X, Z, VX, VZ, THETA, OMEGA


def _flight_summary(result, p) -> dict:
    """Apogee altitude/time, max dynamic pressure ("max-Q") over the whole
    recorded flight, and impact time -- the same quantities `main()`'s
    single-run summary below prints, generalised so `sweep()` can compute
    them per variant.

    `q` is sampled via `sim.flow.flow_state` on the same dense, uniform
    time grid the single-run summary already uses for speed/downrange
    (`result.raw.sol(t_grid)`) -- `flow_state` needs a single state vector
    per call, so this loops over the grid columns.
    """
    apogee_time = result.events["apogee"]
    impact_time = result.events["ground"]
    apogee_altitude = (
        -result.raw.sol(apogee_time)[Z] if apogee_time is not None else None
    )

    t_end = impact_time if impact_time is not None else result.t[-1]
    t_grid = np.linspace(0.0, t_end, 2000)
    y_grid = result.raw.sol(t_grid)

    q_values = np.array(
        [flow_state(t, y_grid[:, i], p).q for i, t in enumerate(t_grid)]
    )
    max_q = float(q_values.max())

    return dict(
        apogee_altitude=apogee_altitude,
        apogee_time=apogee_time,
        max_q=max_q,
        impact_time=impact_time,
    )


def sweep(base_params: Params, field: str, values, s0: State, **run_kwargs) -> dict:
    """Model comparison sweep (architecture.md SS12, roadmap.md Step 27 --
    "the payoff for the selection pattern"): run `run_sim` once per `value`
    of `field`, varying only that one field on `base_params` via
    `dataclasses.replace`, exactly the idiom SS12 gives:

        for gm in ("constant", "linear", "radial", "wgs84"):
            run_sim(dataclasses.replace(p, gravity_model=gm), s0)

    Returns `{value: {"result": Result, "params": Params, **_flight_summary}}`,
    keyed by the model-selection string so callers (the printed table,
    `plot_trajectory_overlay`) can label each variant directly.
    """
    out = {}
    for value in values:
        p = dataclasses.replace(base_params, **{field: value})
        result = run_sim(p, s0, **run_kwargs)
        out[value] = dict(result=result, params=p, **_flight_summary(result, p))
    return out


def _print_sweep_table(title: str, field: str, results: dict) -> None:
    """Plain-text summary table (this project's existing "print a flight
    summary" style, no table library -- roadmap.md Step 27's check)."""
    print(f"\n{title} ({field} sweep):")
    header = f"{field:<14}{'apogee_alt[m]':>16}{'apogee_t[s]':>14}{'max_q[Pa]':>14}{'impact_t[s]':>14}"
    print(header)
    print("-" * len(header))
    for value, d in results.items():
        impact_t = d["impact_time"] if d["impact_time"] is not None else float("nan")
        print(
            f"{value:<14}{d['apogee_altitude']:16.4f}{d['apogee_time']:14.4f}"
            f"{d['max_q']:14.4f}{impact_t:14.4f}"
        )


def main() -> None:
    # Placeholder values, small-model-rocket scale (unchanged from Step 1).
    params = Params(
        m=0.5,      # 0.5 kg dry+propellant mass
        I=0.05,     # kg*m^2, rough estimate for a small rocket
        l1=0.3,     # m, CoP -> CoG distance
        l2=0.4,     # m, CoP -> thrust point distance
        motor_curve="placeholder.csv",  # Step 14: real (time, thrust) curve
        A_x=0.5,    # N, placeholder axial aero force
        A_z=0.0,    # N, placeholder normal aero force
        A_m=0.0,    # N*m, placeholder aero pitching moment
    )

    # At rest on the pad, pointing straight up (theta = pi/2, nose-up
    # from horizontal), z = 0 at the launch point.
    state0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(params, state0)

    apogee_time = result.events["apogee"]
    impact_time = result.events["ground"]
    burnout_time = result.events["burnout"]
    # Evaluate the dense interpolant exactly at the apogee event time
    # rather than taking -min(z) over the adaptive-step samples: RK45's
    # accepted steps rarely land exactly on the apogee, so a raw min()
    # under-estimates it. dense_output=True gives us that interpolant.
    apogee_altitude = -result.raw.sol(apogee_time)[Z]

    # Max speed and downrange-at-impact: sample the dense interpolant on a
    # fine uniform grid over the whole recorded flight (apogee is a
    # non-terminal event, so the interpolant is valid past it too) rather
    # than relying on the sparse adaptive-step points in result.t/result.y.
    t_end = impact_time if impact_time is not None else result.t[-1]
    t_grid = np.linspace(0.0, t_end, 2000)
    y_grid = result.raw.sol(t_grid)
    speed = np.hypot(y_grid[VX], y_grid[VZ])
    max_speed = speed.max()

    if impact_time is not None:
        downrange_impact = result.raw.sol(impact_time)[X]
    else:
        downrange_impact = y_grid[X, -1]

    print(params)
    print(state0)
    print(f"Burnout time:        {burnout_time:.4f} s")
    print(f"Apogee altitude:     {apogee_altitude:.4f} m")
    print(f"Apogee time:         {apogee_time:.4f} s")
    print(f"Max speed:           {max_speed:.4f} m/s")
    print(f"Impact time:         {impact_time:.4f} s")
    print(f"Downrange at impact: {downrange_impact:.4f} m")

    fig_traj = plot_trajectory(result)
    fig_hist = plot_time_histories(result)
    # Always save to files -- this may run in a non-interactive/headless
    # context (e.g. no display), where plt.show() would either do nothing
    # or raise. Saving PNGs guarantees usable artifacts either way.
    fig_traj.savefig("trajectory.png")
    fig_hist.savefig("time_histories.png")
    print("Saved plots to trajectory.png and time_histories.png")

    # Optional one-line CSV dump (architecture.md SS7 "Persistence") for
    # diffing runs -- time, x, z, theta, omega on the same fine grid used
    # above for the summary stats.
    np.savetxt(
        "trajectory.csv",
        np.column_stack(
            [t_grid, y_grid[X], y_grid[Z], y_grid[THETA], y_grid[OMEGA]]
        ),
        delimiter=",",
        header="t,x,z,theta,omega",
        comments="",
    )
    print("Saved trajectory.csv")

    # ------------------------------------------------------------------
    # Step 27: model comparison sweeps (architecture.md SS12). Additional
    # output on top of the single run above -- that run and its summary
    # are unaffected by anything below.
    # ------------------------------------------------------------------

    # (a) The four gravity models, at this scenario's own ~4.6 km apogee
    # scale, where roadmap.md Step 27 expects them to differ "by a
    # predictable, small amount" -- same base scenario as the single run
    # above (aero_model="constant" here, so gravity is the only thing
    # varying).
    gravity_sweep = sweep(
        params, "gravity_model", ("constant", "linear", "radial", "wgs84"), state0
    )
    _print_sweep_table("Gravity model comparison", "gravity_model", gravity_sweep)
    fig_gravity = plot_trajectory_overlay(
        {v: d["result"] for v, d in gravity_sweep.items()},
        title="Gravity model comparison",
    )
    fig_gravity.savefig("gravity_sweep.png")
    print("Saved gravity_sweep.png")

    # (b) ISA vs. a real sounding (station LKPR, data/soundings/example,
    # Step 17), where roadmap.md Step 27 expects the comparison to "show
    # where the real atmosphere matters". Needs aero_model="coefficients"
    # (architecture.md SS12: "constant" ignores the atmosphere entirely,
    # which would make this comparison vacuous) and h0_m=380.0 to match
    # LKPR's own station elevation, so the flight stays inside the
    # station's measured data -- same setup Step 18's own tests used
    # (tests/test_atmosphere.py's `_AERO_KW`/`common`).
    atmo_base = dataclasses.replace(
        params,
        aero_model="coefficients",
        S=0.005,
        d_ref=0.08,
        C_A0=0.5,
        C_N_alpha=2.0,
        C_m_alpha=-0.5,
        h0_m=380.0,
        sounding_case="example",
    )
    atmo_sweep = sweep(atmo_base, "atmosphere_model", ("isa", "sounding"), state0)
    _print_sweep_table(
        "Atmosphere model comparison (station LKPR)", "atmosphere_model", atmo_sweep
    )
    fig_atmo = plot_trajectory_overlay(
        {v: d["result"] for v, d in atmo_sweep.items()},
        title="Atmosphere model comparison (LKPR)",
    )
    fig_atmo.savefig("atmosphere_sweep.png")
    print("Saved atmosphere_sweep.png")

    try:
        plt.show()
    except Exception:
        pass


if __name__ == "__main__":
    main()
