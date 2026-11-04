"""Step 146 (Phase 2.17, continuation of Milestone M3 -- Steps 103/107/108;
dev/docs/architecture-controller-reconciliation.md S3/S4): the first
scripted, closed-loop flight that exercises all four already-landed pieces
TOGETHER on one run:

  1. a Tier-1 sampled control law (apps/control/flight_software/laws.py's
     `proportional_drag`/`pi_apogee`);
  2. the real alpha-beta state estimator
     (apps/control/flight_software/estimator.py's `step(..., model=
     "alpha_beta")`, reached through the law above, never called directly
     by this module);
  3. noisy/lagged/quantised baro sensing (apps.sim.engine.params.Sensors,
     read by apps.sim.engine.sensors.measure through sim.control's own
     sample_airbrake dispatch);
  4. the rate/range/delay-limited actuator (apps.sim.engine.params.Actuator
     (model="full")).

Per S3/S4, this is PURE integration/wiring: all four pieces are already
individually built, registered, and tested; `apps.sim.engine.control.
sample_airbrake`'s own dispatch already threads a registered law's output
through `sensors.measure` and `p.actuator.model` in the SAME call -- no
code in `apps/sim/engine/` changes here, and no new physics/law/estimator
model is added. What this module adds is (a) a thin, reusable entry point
(`run_closed_loop`) that runs one such flight and reduces it to a flat
metrics dict, in the SAME shape `apps.analysis.ensemble.run_ensemble`'s own
`evaluate(config) -> dict[str, float]` callables already return (SS35.4.4/
Step 105's `EnsembleResult` convention -- not a new metrics vocabulary),
and (b) `_replay_actuator_trajectory`, which reconstructs the per-tick
actuator POSITION history `apps.sim.engine.integrate.Result` does not
itself carry.

Why a replay, not a second integration: `_run_rk4`'s own sampled-data loop
(apps/sim/engine/integrate.py) already calls `sampling.sample` once per
tick internally, as a deterministic, pure function of `(t, y, prev)` --
the sensor noise draw is itself deterministic, keyed only by `(p.sensors.
baro_seed, tick index)` (apps.sim.engine.sensors.measure's own
`np.random.default_rng([seed, k])`), not by wall-clock or call order.
Re-driving the exact same `sampling.sample`/`control.airbrake_deploy_
fraction` calls post-hoc, fed from the already-computed dense trajectory
(`result.raw.sol`), therefore reproduces the SAME per-tick values
`_run_rk4` computed internally and discarded -- a faithful replay of
already-done work, not a new simulation.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

from apps.sim.engine import control, gravity, sampling
from apps.sim.engine.integrate import Result, run_sim
from apps.sim.engine.state import State


@dataclasses.dataclass(frozen=True)
class HarnessResult:
    """One closed-loop run's outcome.

    `metrics` is a flat `dict[str, float]` -- the SAME shape
    `apps.analysis.ensemble.run_ensemble`'s own `evaluate(config)` callables
    return, so a later tuning/ensemble step (Step 147, per architecture-
    controller-reconciliation.md S4) can plug
    `lambda cfg: run_closed_loop(cfg, s0).metrics` straight into
    `run_ensemble` without inventing a second metrics vocabulary. Keys:

      - "apogee_m": apogee altitude AGL [m], via `apps.sim.engine.gravity.
        altitude_agl` (correct under every `p.gravity.direction`, not just
        the default "parallel" -- NaN if the flight never reached one --
        `result.events["apogee"] is None`).
      - "apogee_error_m": `apogee_m - p.control.airbrake_target_apogee_m`
        (signed; NaN propagates from `apogee_m`).
      - "actuator_saturation_fraction": fraction of the ACTIVE control
        window's own replayed sample ticks whose actuator position sits AT
        `p.actuator.f_min` or `p.actuator.f_max` (`[0.0, 1.0]`; NaN if the
        flight never had an active window -- see `_active_window` below).
        Restricted to `[burnout, apogee]` (`result.events`), NOT the whole
        flight: outside that window a registered sampled law is never
        called (`sample_airbrake`'s own `_in_coast_window` gate) and the
        actuator sits idle at `f_min` for the rest of the flight (ascent
        before burnout, descent after apogee) -- counting those idle ticks
        as "saturated" would swamp the metric with time the actuator was
        never actually being commanded at all, found during this module's
        own code-review pass (comparison-table evidence: the two
        actuator-rate rows on the oracle's gentle gain differed by <0.3%
        in this metric when measured over the whole flight, because ~73%
        of ticks were simply idle). Under `p.actuator.model == "ideal"`
        this still reflects the registered LAW's own `np.clip(..., 0.0,
        1.0)` output sitting exactly at a rail (laws.py's own clip, same
        `[0.0, 1.0]` bounds as `Actuator`'s defaults) -- NOT a real
        actuator rate/range limit, which "ideal" has none of at all.
      - "actuator_travel": total unsigned distance the actuator position
        covers over the SAME active window, `sum(abs(diff(actuator_f)))`
        -- `0.0` for a window with fewer than two ticks (including "no
        active window at all").

    `result` is the underlying `apps.sim.engine.integrate.Result` (raw
    trajectory, events, `.raw.sol`) for a caller that wants more than the
    four summary metrics. `actuator_t`/`actuator_f` are the reconstructed
    per-tick actuator position trajectory the metrics above are reduced
    from -- exposed so a caller can plot/inspect it directly.
    """

    result: Result
    metrics: "dict[str, float]"
    actuator_t: np.ndarray
    actuator_f: np.ndarray


def _actuator_position(hold_value: Any) -> float:
    """The scalar deployment fraction out of one tick's own `"airbrake"`
    sampling channel value (apps.sim.engine.sampling.Hold.values["airbrake"]):
    a plain `float` under `Actuator(model="ideal")` (no f_min/f_max clip --
    `control._actuator_ideal` returns the raw law command unmodified); an
    `AirbrakeHold` (`.f_k`, the ramp's own position AT this tick's start)
    under `"full"`. `control.SampledLawHold.actuator_hold` is unwrapped
    first -- the same unwrap `control.airbrake_deploy_fraction` itself
    already performs for this exact nesting.
    """
    if isinstance(hold_value, control.SampledLawHold):
        hold_value = hold_value.actuator_hold
    if isinstance(hold_value, control.AirbrakeHold):
        return float(hold_value.f_k)
    return float(hold_value)


def _replay_actuator_trajectory(result: Result, p) -> "tuple[np.ndarray, np.ndarray]":
    """Reconstruct the per-tick actuator position `f_b(t_k)` across the
    whole flight (see the module docstring for why this replay is
    faithful) by re-driving `apps.sim.engine.sampling.sample` tick by tick
    off the ALREADY-COMPUTED dense trajectory (`result.raw.sol`).

    Requires `p.solver.sample_rate_hz > 0.0` -- every piece this harness
    wires together only exists inside the sampled-data loop
    (`apps.sim.engine.integrate._run_rk4`'s own `sampling_on` branch); no
    extra guard here beyond that (house no-validation convention, SS7) --
    a `sample_rate_hz <= 0.0` call raises `ZeroDivisionError` on the next
    line, a clear enough signal.

    `n_ticks` is the number of ticks `_run_rk4`'s own `while t < t_max`
    loop actually sampled -- `floor(t_end/T_s) + 1`, EXCEPT in the one
    edge case where the flight ran all the way to `p.solver.t_max` AND
    that happens to be an exact multiple of `T_s`: `_run_rk4`'s own loop
    condition (`t < t_max`, strict) never takes a fresh sample exactly AT
    `t_max`, so the naive formula would replay one phantom tick nothing
    inside `_run_rk4` ever computed (found during this module's own
    code-review pass; not reachable by any scenario in this ticket's own
    tests, all of which end earlier via a ground/apogee-terminal event
    landing strictly inside a tick, never exactly on a `t_max` boundary).
    """
    T_s = 1.0 / p.solver.sample_rate_hz
    t_end = float(result.t[-1])
    n_ticks = int(t_end // T_s) + 1
    if math.isclose(t_end, p.solver.t_max, rel_tol=0.0, abs_tol=1e-9) and math.isclose(
        (n_ticks - 1) * T_s, t_end, rel_tol=0.0, abs_tol=1e-9
    ):
        n_ticks -= 1
    ts = np.arange(n_ticks, dtype=float) * T_s

    hold = None
    positions = np.empty(n_ticks, dtype=float)
    for k, t_k in enumerate(ts):
        y_k = result.raw.sol(float(t_k))
        hold = sampling.sample(float(t_k), y_k, p, prev=hold)
        positions[k] = _actuator_position(hold.values["airbrake"])
    return ts, positions


def _active_window(result: Result) -> "tuple[float, float] | None":
    """`[burnout, apogee]` (`result.events`) -- the ONLY stretch of the
    flight a registered sampled law is ever called in (`sample_airbrake`'s
    own `_in_coast_window` gate, apps/sim/engine/control.py: unpowered AND
    pre-apogee). `None` if either event never fired (no meaningful active
    window exists -- e.g. the motor never achieved burnout, or the flight
    never reached an apogee)."""
    burnout_t, apogee_t = result.events["burnout"], result.events["apogee"]
    if burnout_t is None or apogee_t is None:
        return None
    return burnout_t, apogee_t


def _metrics(result: Result, p, actuator_t: np.ndarray, actuator_f: np.ndarray) -> "dict[str, float]":
    apogee_t = result.events["apogee"]
    apogee_m = (
        float("nan") if apogee_t is None else float(gravity.altitude_agl(result.raw.sol(apogee_t), p))
    )
    apogee_error_m = apogee_m - p.control.airbrake_target_apogee_m

    window = _active_window(result)
    f_window = np.empty(0) if window is None else actuator_f[(actuator_t >= window[0]) & (actuator_t <= window[1])]
    if f_window.size == 0:
        saturation_fraction, travel = float("nan"), float("nan")
    else:
        a = p.actuator
        saturated = (f_window <= a.f_min) | (f_window >= a.f_max)
        saturation_fraction = float(np.mean(saturated))
        travel = float(np.sum(np.abs(np.diff(f_window))))

    return {
        "apogee_m": apogee_m,
        "apogee_error_m": apogee_error_m,
        "actuator_saturation_fraction": saturation_fraction,
        "actuator_travel": travel,
    }


def run_closed_loop(p, s0: State) -> HarnessResult:
    """Run one flight with `p` as given (`run_sim`, unchanged), then
    reconstruct the actuator's own per-tick position trajectory
    (`_replay_actuator_trajectory`) and reduce the run to the four summary
    metrics above (`_metrics`). The caller is responsible for building `p`
    with whichever of the four pieces it wants active -- this function
    adds no defaults of its own beyond what `apps.sim.engine.params.Params`
    already has (every field already defaults to its own documented
    off/inert value).
    """
    result = run_sim(p, s0)
    actuator_t, actuator_f = _replay_actuator_trajectory(result, p)
    metrics = _metrics(result, p, actuator_t, actuator_f)
    return HarnessResult(result=result, metrics=metrics, actuator_t=actuator_t, actuator_f=actuator_f)
