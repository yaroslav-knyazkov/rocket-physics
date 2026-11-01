"""projects/fx27 -- port of the sibling project `fx27/simulation` (built on
`rocketpy`, a point-mass 3DOF model) onto this repo's own `apps/` library,
against the same real rocket/motor/launch-site data.

Scoped and designed in `dev/docs/architecture-38-fx27-port.md` (SS38, all
sections). Decision taken at the user gate (SS38.3/SS38.12, D-A): **Option
C** -- a frozen-attitude rigid-body run (`aero.model="constant"`, `C_z=0`,
`C_m=0`, `c_mq=0`, `s0.omega=0`) plus the already-shipped Step 137
diagnostic (`apps._shared.flight_stats.point_mass_flightpath`) reporting a
per-scenario measured bound on how far that approximation is from a true
point mass.

**Read this before trusting any number out of this package**: "point
mass" in these file/function names means Option C above, NOT literal
point-mass physics. This project's engine always carries an attitude
state; there is no alternative solver here. See `point/__init__.py` for
the caveat in full, and `README.md` for how to run everything and what
the numbers mean.

Zero lines of `apps/` changed by this package (SS38.5.0: "Total `apps/`
changes required: zero"). Everything here is `projects/`-only composition
of already-shipped, already-tested public `apps/` functions.
"""
