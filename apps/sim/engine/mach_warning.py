"""apps/sim/engine/mach_warning.py -- run-time diagnostic for Mach-blind drag models
(Phase 2.16, Step 92, dev/docs/architecture-33-configs-one-demo.md SS33.12,
D-83).

`aero.model == "constant"` and `"linearized"` carry no Mach dependence, so
their drag is not credible once the flight goes transonic/supersonic.
`warn_if_mach_blind(result)` computes the peak flight Mach number (speed
relative to the air mass over the local speed of sound, from the same
atmosphere/wind models the run used, via `sim.flow.flow_state`) over the
recorded trajectory and, above `MACH_LIMIT`, emits one `MachRangeWarning`.
`"table"` is exempt (it can encode Mach). Pure diagnostic: the `Result`
is never modified, so no numeric output moves.

Called from the end of `sim.integrate.run_sim`, the one seam every entry
point (`run.py` and all five apps) goes through.
"""

from __future__ import annotations

import warnings

import numpy as np

from apps.sim.engine.flow import flow_state

MACH_LIMIT = 0.8
_MACH_INDEPENDENT_MODELS = ("constant", "linearized")


class MachRangeWarning(UserWarning):
    """Peak Mach exceeded `MACH_LIMIT` under a Mach-independent aero model."""


def peak_mach(result) -> tuple[float, float]:
    """`(peak Mach, time [s])` over the recorded samples of `result`."""
    p = result.params
    best_m, best_t = 0.0, float(result.t[0])
    for i, t in enumerate(result.t):
        m = flow_state(float(t), result.y[:, i], p).M
        if m > best_m:
            best_m, best_t = float(m), float(t)
    return best_m, best_t


def warn_if_mach_blind(result, stacklevel: int = 3) -> None:
    """Emit one `MachRangeWarning` if `result` exceeds Mach `MACH_LIMIT`
    under a Mach-independent aero model; otherwise do nothing."""
    model = result.params.aero.model
    if model not in _MACH_INDEPENDENT_MODELS:
        return
    m, t = peak_mach(result)
    if not np.isfinite(m) or m <= MACH_LIMIT:
        return
    warnings.warn(
        f"peak Mach {m:.2f} at t={t:.1f} s exceeds {MACH_LIMIT} with "
        f'Mach-independent aero model "{model}" -- drag is not credible '
        'above ~0.8; use aero.model="table" with Mach-dependent data',
        MachRangeWarning,
        stacklevel=stacklevel,
    )
