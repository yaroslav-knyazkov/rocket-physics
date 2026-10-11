"""Sampled-data / zero-order-hold (ZOH) support (architecture-28-rewrite.md
SS28.8) -- the capability backlog items B11 (state-coupled turbulence) and
B12 (sampled-rate PID airbrake) were both waiting on, and nothing else.

### The problem this module exists to solve

`scipy.integrate.solve_ivp` evaluates its RHS at arbitrary, repeated, and
sometimes-rejected times -- a correct, well-behaved property for an
adaptive solver, but it means nothing that needs "the current value, once,
held constant until the next tick" (a flight computer's measure-compute-
hold cycle; an integral/derivative term that needs its own previous
sample) can be expressed as a pure function of `(t, y, p)` alone. Step 59
builds the fixed-rate, zero-order-hold capability that lets such a
quantity be expressed at all, strictly opt-in (`p.solver.sample_rate_hz >
0.0`, `p.solver.method == "rk4"` -- `sim/integrate.py`'s `run_sim`/
`_run_rk4`) -- no controller and no turbulence model is written here.

### What this module owns vs. what `sim/integrate.py` owns

This module owns the hold *itself* -- a dispatch-style channel registry,
which is a model-selection concern, the same shape as `wind.py`'s
`_MODELS`/`gravity.py`'s `_GRAVITY_MODELS` dicts (architecture.md SS12).
`sim/integrate.py` stays about numerics: it calls `sample()` once at the
start of every tick and holds the returned `Hold` constant across all four
RK4 stages of every substep within that tick (`_run_rk4`'s own docstring
explains why that ordering is what makes this a genuine ZOH, not an
approximation of one -- every discontinuity then lands exactly on a step
boundary, never inside one, so RK4's order is preserved within a tick).

### The channel contract

Each registered channel is `f(t, y, p, prev) -> Any`. `prev` is that
channel's OWN value from the *previous* tick (`None` at the very first
tick, t=0) -- never the whole previous `Hold` bundle. This is the single
most important design detail, and the reason this module does not need a
second rewrite to support B11/B12 later: it is what makes a channel
*recursive*. A PID's integral accumulator, a rate limiter's previous
command, and a Dryden filter's internal state are all expressible as
`f(t_k, y_k, p, prev)` for some channel-specific `prev`. The value type is
deliberately `Any`, not `float`, so a future channel can hold a tuple or
an array of filter states, not just a scalar.

Only one channel is registered today: `"airbrake"` ->
`control.sample_airbrake`, a thin wrapper around today's existing pure,
memoryless `_AIRBRAKE_CONTROLLERS[p.control.airbrake_model]` dispatch
(`sim/control.py`) -- evaluated once per tick instead of once per RHS
call. No controller is written here or in `sim/control.py`.
"""

from typing import Any, NamedTuple, Optional

from sim import control


class Hold(NamedTuple):
    t_sample: float       # the tick these values were computed at
    values: "dict[str, Any]"  # channel name -> held value (float, tuple, or array)


# Module-private dispatch dict (architecture.md SS12), same pattern as
# `control._AIRBRAKE_CONTROLLERS`/`wind._MODELS`: every registered channel
# is evaluated once per tick by `sample()` below; callers of `sample()`
# never learn channels exist individually.
_CHANNELS = {"airbrake": control.sample_airbrake}


def sample(t: float, y, p, prev: "Optional[Hold]") -> Hold:
    """Evaluate every registered channel exactly once, at this tick's own
    `(t, y)` -- the causally correct flight-computer model: measure,
    compute, hold until the next tick (architecture-28-rewrite.md SS28.8.2,
    point 2: "the sample is taken at the tick's start").

    `prev` is the *previous* tick's `Hold` (or `None` at the first tick,
    t=0). Each channel function receives its own previous value out of it
    (`prev.values.get(name)`, or `None` if `prev` itself is `None`) --
    never the whole bundle; see this module's own docstring for why.
    """
    prev_values = prev.values if prev is not None else {}
    values = {
        name: channel(t, y, p, prev_values.get(name))
        for name, channel in _CHANNELS.items()
    }
    return Hold(t_sample=t, values=values)
