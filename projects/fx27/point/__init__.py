"""projects/fx27/point/ -- the launch-config-agnostic layer, fx27's own
`point/` package re-expressed over `apps/` (dev/docs/architecture-38-fx27-
port.md SS38.5.1-SS38.5.8, ticket FX27-3).

**"Point mass" in this package's module/function names does NOT mean
literal point-mass physics.** This repo's engine always carries an
attitude state; there is no alternative solver here. Every flight run
through `flight.run` is Option C (SS38.3/SS38.12, D-A): a frozen-attitude
rigid body (`aero.model="constant"`, `C_z=0`, `C_m=0`, `c_mq=0`,
`s0.omega=0` -- the total pitching moment is identically zero, SS38.2.1,
so `theta` stays bit-exactly at the rail angle for the whole flight) PLUS
the already-shipped Step 137 diagnostic
(`apps._shared.flight_stats.point_mass_flightpath`, wrapped here as
`validity.check_validity`) reporting a measured, per-scenario bound on how
far that approximation is from a true point mass.

The acceptance oracle for this approximation is AC-3 (SS38.9):
`estimate.estimate_airframe_mass`/`estimate_cx` must reproduce fx27's own
four hardcoded solved figures within 5%. If a reviewer wants true
point-mass physics as a modelling capability in its own right, that is
Option B (SS38.3.2) -- a new engine RHS, out of scope here and NOT what
running these modules gives you.

Zero lines of `apps/` are changed by this package (SS38.5.0): every
module below is a composition of already-shipped, already-tested public
`apps/` functions. No import of any `_`-prefixed `apps` internal name
(AC-10) -- `estimate.py` goes through `Scenario` -> `assemble`, never
`apps.sim.engine.params.replace`, for anything that varies mass (SS38.4.2).
"""
