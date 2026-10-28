"""Step 108 (architecture-35-paper-alignment.md SS35.4.4, D-115): the
baro-pressure sensing channel a registered sampled law
(apps/control/flight_software/) reads through -- the REAL sensor,
replacing Step 107's own `sim.control._ideal_measurement` stub at its
one call site (sim/control.py's sample_airbrake, SS107.12).

Pipeline, in order: true pressure (sim.atmosphere.air_state, whichever
tier is active) -> ISA pressure-altitude inversion (sim.atmosphere.
isa_pressure_altitude) -> first-order lag (closed form, same style as
sim.control._ramp) -> Gaussian noise (counter-based, architecture-35
SS35.4.4: "np.random.default_rng([seed, k])") -> quantisation. All four
Sensors fields default to inert, so sim.sensors.measure reproduces the
truth altitude bit-for-bit under the default "isa" atmosphere tier.

sim/ layering: this module is part of sim/ (reads sim.atmosphere,
sim.control's Measurement type), NOT apps/control/flight_software/ --
the sensor's own physics belongs with the plant, same status as
sim.control's actuator model (Step 103). apps/control/flight_software/
never sees the true state `y`; it only ever sees this module's own
`Measurement` output.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, NamedTuple, Optional

import numpy as np

from sim import atmosphere

if TYPE_CHECKING:
    from sim.control import Measurement


class SensorState(NamedTuple):
    t_prev: Optional[float] = None
    h_lag_prev: Optional[float] = None


def measure(t: float, y: np.ndarray, p, prev: "Optional[SensorState]") -> "tuple[Measurement, SensorState]":
    """`(Measurement, new_state)`. Called once per tick, only while
    sim.control._in_coast_window(t, y, p) holds (sample_airbrake's own
    gate, unchanged from Step 107) -- `prev` is this channel's own
    SensorState from the previous such call, or None at the first one.

    §108.3.4/§108.8 item 5's own flagged fallback: `Measurement` is
    imported HERE, lazily, rather than at module top -- a genuine
    circular import (`sim/control.py`'s top-level `from sim import
    sensors` racing this module's own top-level `from sim.control import
    Measurement`, whichever module a caller happens to import first)
    confirmed at implementation time. Same precedent `sim/control.py`'s
    own docstring already documents for the opposite direction
    (`sim.aero`/`sim.flow`/`sim.forces` deferring their own `from sim
    import wind`/`from sim import control` inside the function that
    needs it) -- no shape change to where `Measurement` lives, unlike the
    ticket's OTHER listed fallback (moving the class into this module).
    """
    from sim.control import Measurement

    s = p.sensors
    air = atmosphere.air_state(t, y, p)
    h_press = atmosphere.isa_pressure_altitude(air.p) - getattr(p.site, "h0_m", 0.0)

    if prev is None or prev.t_prev is None or s.baro_tau_s <= 0.0:
        h_lag = h_press
    else:
        dt = t - prev.t_prev
        if dt <= 0.0:
            # Found during code review (not in the ticket's own listed
            # code): a repeated/out-of-order tick (dt <= 0.0) would send
            # `-dt/tau` strongly positive, and `math.exp` of a large
            # positive argument raises `OverflowError` -- a hard crash,
            # not a graceful degradation. Same guard, same "hold the
            # previous estimate unchanged" convention, as
            # apps/control/flight_software/estimator.py's own
            # `_step_alpha_beta` dt<=0.0 branch (this ticket, sibling
            # code path) already uses for the identical class of input.
            h_lag = prev.h_lag_prev
        else:
            h_lag = h_press + (prev.h_lag_prev - h_press) * math.exp(-dt / s.baro_tau_s)

    if s.baro_sigma_m != 0.0:
        k = int(round(t * p.solver.sample_rate_hz))
        rng = np.random.default_rng([s.baro_seed, k])
        h_noisy = h_lag + rng.normal(0.0, s.baro_sigma_m)
    else:
        h_noisy = h_lag

    if s.baro_resolution_m > 0.0:
        h_out = round(h_noisy / s.baro_resolution_m) * s.baro_resolution_m
    else:
        h_out = h_noisy

    return Measurement(h_baro=float(h_out)), SensorState(t_prev=t, h_lag_prev=h_lag)
