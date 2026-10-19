"""App 3 v2 -- motor sweep on `Scenario` + `Motor` (Step 100, Phase 2.17,
dev/docs/architecture-35-paper-alignment.md SS35.4.5, D-113).

Input: one `Scenario` (rocket, site, weather) and a list of `Motor` pieces.
Per motor: `assemble(replace(scenario, motor=m))` -> `run_sim` -> one
`SweepRow`. Ranking: feasible first, then distance to the target apogee (or
highest apogee when no target is given); infeasible rows keep the names of the
constraints they failed. The old `MotorEntry`/`overrides` path in
`compare_motors.py` is untouched.

Definitions worth knowing:

- `tw_liftoff` = peak stand thrust before leaving the rail (whole burn when the
  site has no rail) divided by the launch weight `weight.m * g0`.
- `v_rail_exit` is NaN when the site has no rail; the "rail exit" static margin
  is then taken at `t = 0`.
- `M_max` is the ascent-window maximum flow Mach; it is infeasible
  (`mach_range`) when it exceeds the top of a tabulated aero model's M grid.
- `h_apogee_brake` is the apogee of a second flight with `brake_overrides`
  (dotted `Params` paths applied as `Scenario.overrides`); None without them.

B26 thin slice (D-113): `derive_history(motor)` exports the motor's own
`m(t), l_cg(t), I(t)` (motor-local stations, positive aft of the motor's
forward face; `I` about the motor's own CoG) using the very same composition
and `sim.mass` functions the solver uses, plus a provenance dict (model name,
resolved inputs, SHA-256 of the source file). The solver is unchanged.

Run: `python run_motor_sweep.py --scenario demo --motors cti_k570 --target 5000`
(or `python -m apps.motor_selection.scenario_sweep ...`).
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import configs
from apps.common.artifacts import OUTPUT_DIR
from apps.common.flight_stats import _assert_derivatives_reconstructible, flight_stats
from configs import motors as motor_registry
from configs.schema import Airframe, Motor, Scenario, Sections, _weight_from_pieces, assemble
from sim import aero, mass, motor_file, thrust_curve
from sim.integrate import Result, run_sim
from sim.params import Params, Thrust
from sim.plotting import plot_trajectory_overlay
from sim.report import static_margin_cal

# Constraint names (the strings stored in `SweepRow.failed`).
NO_APOGEE = "no_apogee"
TW_LIFTOFF = "tw_liftoff"
MACH_RANGE = "mach_range"
STATIC_MARGIN = "static_margin"

ROW_FIELDS = (
    "motor", "J_total", "t_burn", "tw_liftoff", "v_rail_exit", "h_apogee", "h_apogee_brake",
    "v_max", "M_max", "q_max", "a_max", "margin_rail_exit", "margin_burnout", "margin_min",
    "m_burnout", "dist_target", "feasible", "failed", "provenance",
)

_NAN = float("nan")


@dataclasses.dataclass(frozen=True)
class Constraints:
    min_tw: float = 5.0            # T/W at liftoff (peak thrust before rail exit / launch weight)
    min_margin_cal: float = 1.0    # minimum static margin over the burn [calibres]


@dataclasses.dataclass(frozen=True)
class SweepRow:
    motor: str
    J_total: float                 # N*s, k_J * curve impulse
    t_burn: float                  # s, burnout event (NaN if none)
    tw_liftoff: float
    v_rail_exit: float             # m/s (NaN: no rail)
    h_apogee: float | None         # m AGL, brake closed
    h_apogee_brake: float | None   # m AGL, brake_overrides applied
    v_max: float
    M_max: float
    q_max: float
    a_max: float                   # m/s^2
    margin_rail_exit: float        # cal
    margin_burnout: float
    margin_min: float              # min over [0, burnout]
    m_burnout: float               # kg
    dist_target: float             # |h_apogee - target| (NaN without target)
    feasible: bool
    failed: tuple[str, ...]
    provenance: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class SweepResult:
    rows: list[SweepRow]                  # ranked
    results: dict[str, Result]            # motor name -> brake-closed flight


@dataclasses.dataclass(frozen=True)
class MotorHistory:
    """Motor-local history. `t` s; `m` kg; `l_cg` m aft of the motor's forward
    face; `I` kg*m^2 about the motor's own CoG."""

    t: np.ndarray
    m: np.ndarray
    l_cg: np.ndarray
    I: np.ndarray
    provenance: dict[str, Any]


# ----------------------------------------------------------------------
# B26 thin slice: provenance + derived history
# ----------------------------------------------------------------------


def _file_sha256(spec: str) -> tuple[str, str]:
    filename = spec.partition("#")[0]
    with open(motor_file._motors_path(filename), "rb") as f:
        return filename, hashlib.sha256(f.read()).hexdigest()


def _cum_impulse(times: np.ndarray, thrusts: np.ndarray, tau: np.ndarray) -> np.ndarray:
    """Exact integral of the piecewise-linear curve (held at `thrusts[0]` before
    `times[0]`, zero after the last point) from 0 to `tau`."""
    tau = np.asarray(tau, dtype=float)
    cb = np.concatenate(([0.0], np.cumsum(0.5 * (thrusts[1:] + thrusts[:-1]) * np.diff(times))))
    head = thrusts[0] * times[0]
    T = np.interp(tau, times, thrusts, left=thrusts[0], right=0.0)
    idx = np.clip(np.searchsorted(times, tau, side="right") - 1, 0, len(times) - 1)
    inside = head + cb[idx] + (tau - times[idx]) * (thrusts[idx] + T) / 2.0
    before = thrusts[0] * np.maximum(tau, 0.0)
    return np.where(tau < times[0], before, np.where(tau >= times[-1], head + cb[-1], inside))


def derive_history(
    motor: Motor, t: "np.ndarray | None" = None, g0: float = 9.80665, n: int = 200
) -> MotorHistory:
    """The motor's own `t, m(t), l_cg(t), I(t)` (see module docstring).

    Built from `configs.schema._weight_from_pieces` on a zero-mass airframe at
    station 0 (so the resolution of header fields, endpoint inversion and
    defaults is the assembly code itself), then `sim.mass` -- the same
    functions `sim.dynamics` calls. The mass follows the solver's law
    `m(t) = max(m_0 - C(t / k_t) / (I_sp g0), m_dry)` with `C` the cumulative
    curve impulse. `t=None` -> breakpoints of the (time-scaled) curve plus `n`
    uniform points.
    """
    if motor.mass_model == "none":
        raise ValueError(f"derive_history: motor {motor.name!r} has mass_model='none'")
    w = _weight_from_pieces(Airframe(m=0.0, I=0.0, l=0.0), Sections(l_motor_fwd=0.0), motor, g0)
    p = Params(weight=w, g0=g0, thrust=motor.thrust)
    spec = motor.thrust.motor_curve
    rec = motor_file.load(spec)
    k_J, k_t = motor.thrust.k_J, motor.thrust.k_t
    if t is None:
        t_end = k_t * float(rec.times[-1])
        t = np.union1d(k_t * rec.times, np.linspace(0.0, t_end, n))
    t = np.asarray(t, dtype=float)

    C = _cum_impulse(rec.times, rec.thrusts, t / k_t)
    m_tot = np.maximum(w.m - C / (w.I_sp * g0), w.m_d)
    m_p = m_tot - w.m_d
    l_cg = mass.cog_position(m_p, p)
    I = mass.moment_of_inertia(m_p, l_cg, p)

    filename, digest = _file_sha256(spec)
    prov = {
        "model": motor.mass_model,
        "motor": motor.name,
        "source_file": filename,
        "source_sha256": digest,
        "inputs": {
            "m_total": float(w.m), "m_prop": float(w.m - w.m_d), "m_dry": float(w.m_d),
            "I_sp": float(w.I_sp), "J": float(rec.total_impulse), "k_J": k_J, "k_t": k_t,
            "l_dry": float(w.l_d), "l_prop": float(w.l_p), "I_dry": float(w.I_d),
            "I_p_spec": None if w.I_p_spec is None else float(w.I_p_spec),
            "g0": g0, "t_burn": float(k_t * rec.times[-1]),
        },
    }
    return MotorHistory(t=t, m=m_tot, l_cg=l_cg, I=I, provenance=prov)


def motor_provenance(motor: Motor, g0: float) -> dict[str, Any]:
    """Provenance for any motor: the full `derive_history` dict when a mass
    model is on, otherwise model name + file hash + scatter factors."""
    if motor.mass_model != "none":
        return derive_history(motor, g0=g0, n=2).provenance
    filename, digest = _file_sha256(motor.thrust.motor_curve)
    return {
        "model": "none", "motor": motor.name, "source_file": filename, "source_sha256": digest,
        "inputs": {"k_J": motor.thrust.k_J, "k_t": motor.thrust.k_t},
    }


# ----------------------------------------------------------------------
# The sweep
# ----------------------------------------------------------------------


def _table_mach_max(p: Params) -> float:
    if p.aero.model == "table" and p.aero.table:
        return float(aero._load_table(p.aero.table).M[-1])
    return math.inf


def _tw_liftoff(result: Result, p: Params) -> float:
    t_lim = result.events.get("rail_exit")
    if t_lim is None:
        t_lim = result.events.get("burnout")
    if t_lim is None:
        t_lim = float(result.t[-1])
    t = np.linspace(0.0, t_lim, 2000)
    peak = max(thrust_curve.thrust_stand(float(ti), p) for ti in t)
    return peak / (p.weight.m * p.g0)


def _margins(result: Result, p: Params) -> tuple[float, float, float]:
    """(rail exit, burnout, min over [0, burnout]) static margin in calibres."""
    t_b = result.events.get("burnout")
    if p.aero.d_ref <= 0.0 or t_b is None:
        return _NAN, _NAN, _NAN
    t_re = result.events.get("rail_exit")
    t_re = 0.0 if t_re is None else min(t_re, t_b)
    grid = np.union1d(np.linspace(0.0, t_b, 200), [t_re])
    t, margin = static_margin_cal(result, p, grid)
    return (
        float(margin[np.searchsorted(t, t_re)]),
        float(margin[-1]),
        float(margin.min()),
    )


def evaluate_motor(
    scenario: Scenario,
    motor: Motor,
    constraints: Constraints = Constraints(),
    target: float | None = None,
    brake_overrides: "dict[str, Any] | None" = None,
) -> tuple[SweepRow, Result]:
    """One motor on the scenario -> (row, brake-closed `Result`)."""
    sc = dataclasses.replace(scenario, motor=motor)
    cfg = assemble(sc)
    p = cfg.params
    _assert_derivatives_reconstructible(p)
    result = run_sim(p, cfg.s0)
    st = flight_stats(result, p)

    h = st.apogee_altitude
    h_brake = None
    if brake_overrides:
        sc_b = dataclasses.replace(sc, overrides={**sc.overrides, **brake_overrides})
        cfg_b = assemble(sc_b)
        res_b = run_sim(cfg_b.params, cfg_b.s0)
        h_brake = flight_stats(res_b, cfg_b.params).apogee_altitude

    rec = motor_file.load(motor.thrust.motor_curve)
    t_b = result.events.get("burnout")
    if p.weight.m_d is not None and t_b is not None:
        m_burnout = float(result.raw.sol(t_b)[6])
    else:
        m_burnout = float(p.weight.m_d if p.weight.m_d is not None else p.weight.m)

    tw = _tw_liftoff(result, p)
    m_rail, m_bo, m_min = _margins(result, p)
    M_max = st.max_mach if st.max_mach is not None else _NAN

    failed = []
    if h is None:
        failed.append(NO_APOGEE)
    if tw < constraints.min_tw:
        failed.append(TW_LIFTOFF)
    if M_max > _table_mach_max(p):
        failed.append(MACH_RANGE)
    if not math.isnan(m_min) and m_min < constraints.min_margin_cal:
        failed.append(STATIC_MARGIN)

    nan_if_none = lambda x: _NAN if x is None else float(x)  # noqa: E731
    row = SweepRow(
        motor=motor.name,
        J_total=float(motor.thrust.k_J * rec.total_impulse),
        t_burn=nan_if_none(t_b),
        tw_liftoff=float(tw),
        v_rail_exit=nan_if_none(st.rail_exit_speed),
        h_apogee=h,
        h_apogee_brake=h_brake,
        v_max=nan_if_none(st.max_velocity),
        M_max=M_max,
        q_max=nan_if_none(st.max_q),
        a_max=nan_if_none(st.max_accel),
        margin_rail_exit=m_rail,
        margin_burnout=m_bo,
        margin_min=m_min,
        m_burnout=m_burnout,
        dist_target=abs(h - target) if (target is not None and h is not None) else _NAN,
        feasible=not failed,
        failed=tuple(failed),
        provenance=motor_provenance(motor, p.g0),
    )
    return row, result


def _rank_key(row: SweepRow, target: float | None):
    if row.h_apogee is None:
        d = math.inf
    elif target is not None:
        d = row.dist_target
    else:
        d = -row.h_apogee
    return (not row.feasible, d)


def sweep_scenario(
    scenario: Scenario,
    motors: Sequence[Motor],
    constraints: Constraints = Constraints(),
    target: float | None = None,
    brake_overrides: "dict[str, Any] | None" = None,
) -> SweepResult:
    """Evaluate every motor; return ranked rows and the flights (by name)."""
    if not motors:  # QA-7
        raise ValueError("sweep_scenario: the motor list is empty")
    names = [m.name for m in motors]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:  # QA-6: results are keyed by motor name, so duplicates would collapse silently
        raise ValueError(f"sweep_scenario: duplicate motor name(s) {dup}")
    pairs = [evaluate_motor(scenario, m, constraints, target, brake_overrides) for m in motors]
    pairs.sort(key=lambda rr: _rank_key(rr[0], target))
    return SweepResult(rows=[r for r, _ in pairs], results={r.motor: res for r, res in pairs})


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------


def _f(x, spec):
    return "      -" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def print_table(rows: list[SweepRow], target: float | None = None) -> None:
    head = (
        f"{'motor':<22}{'J[Ns]':>9}{'tb[s]':>7}{'T/W':>7}{'vrail':>8}{'h[m]':>9}{'h_brk[m]':>10}"
        f"{'vmax':>8}{'Mmax':>7}{'qmax[Pa]':>10}{'amax':>8}{'mg_re':>7}{'mg_bo':>7}{'mg_min':>8}"
        f"{'mbo[kg]':>9}{'d_tgt':>9}  status"
    )
    print(f"\nMotor sweep v2 (ranked: feasible first, then "
          f"{'distance to target ' + format(target, 'g') + ' m' if target is not None else 'apogee'}):")
    print(head)
    print("-" * len(head))
    for r in rows:
        status = "ok" if r.feasible else "INFEASIBLE: " + ",".join(r.failed)
        print(
            f"{r.motor:<22}{_f(r.J_total, '9.1f')}{_f(r.t_burn, '7.2f')}{_f(r.tw_liftoff, '7.1f')}"
            f"{_f(r.v_rail_exit, '8.1f')}{_f(r.h_apogee, '9.1f')}{_f(r.h_apogee_brake, '10.1f')}"
            f"{_f(r.v_max, '8.1f')}{_f(r.M_max, '7.2f')}{_f(r.q_max, '10.0f')}{_f(r.a_max, '8.1f')}"
            f"{_f(r.margin_rail_exit, '7.2f')}{_f(r.margin_burnout, '7.2f')}{_f(r.margin_min, '8.2f')}"
            f"{_f(r.m_burnout, '9.3f')}{_f(r.dist_target, '9.1f')}  {status}"
        )


def save_csv(rows: list[SweepRow], path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("rank",) + ROW_FIELDS)
        for rank, r in enumerate(rows, start=1):
            vals = []
            for name in ROW_FIELDS:
                v = getattr(r, name)
                if name == "failed":
                    v = ";".join(v)
                elif name == "provenance":
                    v = json.dumps(v, sort_keys=True)
                vals.append(v)
            w.writerow([rank] + vals)


def save_overlay(out: SweepResult, path: Path) -> None:
    fig = plot_trajectory_overlay(
        {r.motor: out.results[r.motor] for r in out.rows}, title="Motor sweep v2"
    )
    fig.savefig(path)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def resolve_motor(spec: str) -> Motor:
    """A registered `configs.motors` name, or a RASP file in `data/motors/`
    (`file.eng[#designation]`) whose header supplies the masses (endpoints
    model, uniform-cylinder defaults). CSV curves carry no masses and must be
    registered as a `Motor` piece."""
    if spec in motor_registry.MOTORS:
        return motor_registry.get(spec)
    filename = spec.partition("#")[0]
    ext = os.path.splitext(filename)[1].lower()
    if ext != ".csv" and os.path.exists(motor_file._motors_path(filename)):
        return Motor(
            name=spec, thrust=Thrust(motor_curve=spec), mass_model="endpoints",
            notes="ad-hoc from the RASP file header",
        )
    raise KeyError(
        f"unknown motor {spec!r}; registered: {', '.join(motor_registry.names())} "
        "(or a .eng/.rasp file under data/motors/, optionally 'file#designation')"
    )


def main(argv: "Sequence[str] | None" = None) -> None:
    ap = argparse.ArgumentParser(description="Motor sweep v2 on a Scenario (Step 100).")
    ap.add_argument("--scenario", required=True, help=f"registered scenario ({', '.join(configs.names())})")
    ap.add_argument("--motors", required=True, help="comma-separated registered motor names / RASP files")
    ap.add_argument("--target", type=float, default=None, help="target apogee [m AGL]")
    ap.add_argument("--min-tw", type=float, default=Constraints.min_tw)
    ap.add_argument("--min-margin", type=float, default=Constraints.min_margin_cal, help="calibres")
    ap.add_argument("--out-dir", default=None, help="default: output/")
    args = ap.parse_args(argv)

    scenario = configs.get_scenario(args.scenario)
    if scenario is None:
        raise SystemExit(f"scenario {args.scenario!r} is a flat Config, not a Scenario; cannot swap motors")
    motors = [resolve_motor(s.strip()) for s in args.motors.split(",") if s.strip()]
    out = sweep_scenario(
        scenario, motors, Constraints(args.min_tw, args.min_margin), target=args.target
    )
    print_table(out.rows, args.target)

    out_dir = Path(args.out_dir) if args.out_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"motor_sweep_{args.scenario}.csv"
    png_path = out_dir / f"motor_sweep_{args.scenario}_overlay.png"
    save_csv(out.rows, csv_path)
    save_overlay(out, png_path)
    print(f"\nSaved {csv_path}\nSaved {png_path}")


if __name__ == "__main__":
    main()
