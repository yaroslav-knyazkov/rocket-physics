# projects/fx27 -- port of `fx27/simulation` onto `apps/`

**What this is.** A port of the sibling project `fx27/simulation` (built on
`rocketpy`, a point-mass 3DOF model) onto this repo's own `apps/` library,
against the same real rocket/motor/launch-site data: two campaigns
(`cspace`, `euroc`), a generic `point/` comparison/estimation layer, and 8
runnable entry points under `runs/` (7 from the original port plus Part
B's `runs/cspace/comparison_dc_dm.py`, dev/docs/architecture-40-fx27-
campaigns-and-dm-drag.md).

Scoped and designed in `dev/docs/architecture-38-fx27-port.md` (SS38, all
sections). Full diagnosis of the one known numeric caveat, and the
developer's working notes, in `dev/docs/fx27-port-progress-notes.md`.
Ported 2026-11.

## Read this before trusting any number out of this package

**"Point mass" in these file/function names does NOT mean literal
point-mass physics.** This repo's engine always carries an attitude
state; there is no alternative solver in this project. Every flight run
through `point/flight.py::run` is **Option C** (the decision taken at the
SS38.3/SS38.12 user gate, D-A): a frozen-attitude rigid body
(`aero.model="constant"`, `C_z=0`, `C_m=0`, `c_mq=0`, `s0.omega=0` -- the
total pitching moment is identically zero, so `theta` stays bit-exactly
at the rail angle for the whole flight) PLUS the already-shipped Step 137
diagnostic (`apps._shared.flight_stats.point_mass_flightpath`, wrapped
here as `point/validity.py`) reporting a measured, per-scenario bound on
how far that approximation is from a true point mass. Pass `--validity`
to any `runs/*` script that supports it to see those numbers
(`alpha_burnout_deg`, `alpha_max_deg @ q>1%`, `still_air_residual_max`).

This is not a weaker approximation of fx27 -- it is the SAME model class
fx27's own `rocketpy.Flight(simulation_mode="3 DOF")` actually runs
(its attitude quaternion is unconditionally frozen, and its aero force
has zero normal/lateral component by construction). See
`dev/docs/architecture-38-fx27-port.md` SS38.2.1/SS38.2.2 for the full
verification.

## The acceptance oracle (AC-3) and its one documented caveat

fx27's own `cspace/rockets_ideal.py` hardcodes the already-solved outputs
of its mass/drag estimators (target apogee 3000 m AGL). This port's
`point/estimate.py::estimate_airframe_mass`/`estimate_cx` were checked
against those four numbers:

| quantity | fx27 figure | measured | error |
|---|---|---|---|
| `estimate_airframe_mass(pro54_transition)` | 4.2864 kg | 4.3840 kg | +2.28% |
| `estimate_cx(pro54_transition)` | 0.2351 | 0.2524 | **+7.35%** |
| `estimate_airframe_mass(pro75)` | 8.0654 kg | 8.1205 kg | +0.68% |
| `estimate_cx(pro75)` | 0.8304 | 0.8400 | +1.16% |

3 of 4 are within 5%. `estimate_cx(pro54_transition)` measures +7.35% --
**accepted as a documented caveat, not a blocker** (user decision,
2026-11). Diagnosis (full detail in `dev/docs/fx27-port-progress-notes.md`,
"STOP: AC-3 measured failure"): not an implementation bug -- forward-
simulating this project's model at fx27's own already-solved values shows
a genuine 0.5-1.7% apogee divergence from fx27 (this port's Option C vs
fx27's true point mass), which the C_x-solve's own sensitivity amplifies
~4.4x for `pro54_transition` specifically -- the lightest, fastest-burning
(peak Mach 1.36), highest-T/W vehicle in the cspace set, exactly the
vehicle the architecture doc's own SS38.3.1 reasoning flags as the most
exposed to this port's one real physics difference from fx27 (force
direction: this port's drag/thrust act along the frozen body axis, fx27's
along the velocity vector). `tests/test_fx27_port.py` encodes this with a
wider, explicitly-commented tolerance for this one case -- see that file,
not a blanket loosening of the other three.

## The Mach > 0.8 caveat (the larger, inherited-from-fx27 one)

Every scenario here uses a **constant** `C_x` (not Mach-dependent). fx27
had the identical modelling defect -- a constant `C_D` through the
transonic region -- it just had nothing to warn about it; this project's
engine emits one `MachRangeWarning` per flight whose peak Mach exceeds
0.8 under `aero.model in ("constant", "linearized")`. Several cspace and
many euroc rows (particularly the N-class motors on 6-7 kg airframes)
comfortably exceed Mach 1. **This is a real accuracy caveat, larger in
magnitude than the point-mass-vs-frozen-attitude question above** -- the
comparison run scripts collect these warnings into one summary line
rather than letting them scatter across the table. Upgrade path:
`aero.model="table"` with real Mach-dependent `C_A` data, if it is ever
supplied.

## The dm aero-table range warning (cspace only, harmless but expected)

Every dm scenario (`campaigns/cspace/rockets_dm.py`) emits one `AeroRangeWarning` per flight: Option
C's frozen-attitude trajectory lets `alpha` grow smoothly from 0 deg near launch, through 90 deg
around apogee, to roughly 166 deg in tail-first descent (gravity turns the velocity vector while
body attitude stays fixed at the rail angle) -- no alpha grid width, up to the aero-table format's
own hard `(-90, +90)` deg bound, can cover that full sweep (SS40.5's grid is `[-89, 89]` deg, as
wide as the format allows). This is **not an accuracy loss for this port specifically**: the dm
table's `C_A` is the same single Mach-only value at every alpha by construction (`C_N=C_m=0`
everywhere, SS40.3), so holding the edge value past the grid's range returns the exact same number
holding inside it would have. It is the same warning class this codebase already documents
elsewhere for other tables in tail-first descent (e.g. `example_v2.csv`, `tests/test_scenario_sweep.py`)
-- not a new defect introduced by this step. Upgrade path, if ever needed: `Aero.table_oob=
"jorgensen"` (the engine's existing large-alpha extension), which needs real large-alpha
aerodynamic data to be worth turning on, not just a wider placeholder grid.

## The 3 deferred motors

Three of the 27 euroc candidate motors have 4-byte `null` CSV stubs
(data not supplied yet): `pro75-2412K1085`, `pro98-9876M1890`,
`pro98-14200N3180`. `campaigns/euroc/motors.py::DEFERRED_MOTORS` names
them; `campaigns/euroc/scenarios.py::generate_scenarios()` excludes every
`(config, motor)` combination using one of them from its runnable set
(24 of 27) and returns the excluded combos separately --
`runs/euroc/comparison.py` prints that list explicitly under the table,
so a reader cannot mistake
24 rows for the full candidate set. Supplying real data later is a CSV
swap (replace the `-todo` stub), not a code change.

## Layout

```
projects/fx27/
  _paths.py          absolute anchors for the motor-CSV/aero-table directories (SS38.4.3/SS40.4.1)
  campaigns/
    cspace/           3 base rockets x 2 motors, 7-row dc comparison set (incl. 4 ideal variants),
                      + rockets_dm.py/scenarios_dm.py (Mach-dependent "dm" variants, SS40.4)
      data/motors/*.csv           2 motors
      data/aero/*.csv              3 Mach-dependent C_A(M) tables (generated+committed, SS40.5)
    euroc/            12 airframe configs x 27 candidate motors, 24 runnable combos
      data/motors/*.csv           27 motors, 3 of them -todo stubs
  point/              the launch-config-agnostic layer: flight run, metrics, comparison
                      table, mass/drag estimation, airbrake sizing, comparison plots,
                      Option C's validity diagnostic (unchanged by SS40)
  runs/
    cspace/           the 6 cspace entry points below
    euroc/            the 2 euroc entry points below
```

## How to run

From the repo root (so the module paths resolve):

```bash
python -m projects.fx27.runs.cspace.point [--scenario NAME] [--validity]
python -m projects.fx27.runs.cspace.comparison [--validity]
python -m projects.fx27.runs.cspace.ideal_mass
python -m projects.fx27.runs.cspace.ideal_drag
python -m projects.fx27.runs.cspace.airbrake
python -m projects.fx27.runs.euroc.comparison [--validity]
python -m projects.fx27.runs.euroc.sweep
python -m projects.fx27.runs.cspace.comparison_dc_dm [--validity]     # new, Part B, SS40.6
```

Every script writes its artifacts (CSV, PNG) to `output/`
(`apps._shared.artifacts.output_dir()`, gitignored) -- never into
`projects/`. `--validity` is opt-in because it costs one extra
~2000-point dense re-evaluation pass per flight (Step 137's own
diagnostic grid).

## Provenance

Every number in `campaigns/cspace/`/`campaigns/euroc/` cites the fx27 source file it came
from in its own module docstring/`notes=` field (site/rail geometry,
motor masses, airframe dry masses) -- the orchestrator's own inventory of
`D:\Projects - Ongoing\fx27\simulation`, taken as ground truth per
`dev/docs/architecture-38-fx27-port.md` SS38.1. Zero-geometry motor
placeholders (`l_case`/`l_prop`/`I_case`/`I_prop0`/`Sections.l_motor_fwd`/
`Airframe.l`/`Lengths.l1`/`l2`) are flagged inert, each with its own
comment, because the total pitching moment under this port's aero config
is identically zero (SS38.2.1) -- **becomes a silent bug if any scenario
here is ever switched to an alpha-dependent aero model** (`"linearized"`
| `"table"`).
