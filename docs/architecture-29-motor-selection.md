# Architecture §29 — Motor-selection app (Steps 61-62)

## Summary

Design proposal (not approved, no code written) for the app the user asked for on 2026-10-12: feed in
a list of motors, get back the trajectories, ranked by **apogee** (the one study variable for now),
with a richer per-motor stats bundle than `sim.report.flight_summary` offers — max/avg velocity, max
acceleration, burnout time, max-Q, impact time, downrange. It is designed as a **separate consumer
app** (`apps/motor_selection/`, "App 3"), following the `apps/cfd_conditions/select_conditions.py`
precedent: it imports `sim/` as a library, adds no physics, and changes **nothing** under `sim/` —
which is also the user's explicit instruction ("make it as a separate thing; that also concerns
optimizers").

Two steps, one commit each. **Step 61** is the sweep itself plus four synthetic motor-curve fixtures
under `data/motors/`; **Step 62** adds the per-motor configuration methodology the user asked for as
phase two (each motor entry also carries dry-rocket-parameter overrides — smaller motor, smaller
casing). Step 62 is deliberately *additive*: one new dataclass field with a default and one new
config module, so with every override empty it reproduces Step 61's printed table byte-for-byte.
Key finding for Step 62: `sim/params.py`'s `replace(p, {...})` already accepts an arbitrary number
of dotted-path keys in one call (`params.py:194-219`), so the per-motor override schema needs **no
change to `sim/params.py`** at all.

The load-bearing design decision is the **measurement window**: every kinematic/aerodynamic extremum
is taken over the **ascent only** (launch → the `apogee` event), not the whole flight, because
roadmap Step 55 already recorded that this project's own scenarios can put max speed *during
descent* (attitude frozen nose-up, real axial drag accelerating a tail-first fall). Ten decision
forks are flagged for the user in §29.10 (numbered **D-18 … D-27**, continuing §28's D-1 … D-17)
rather than settled here.

**Airbrake, out of scope and recorded for traceability:** the orchestrator informed me that the
user's same message also asked for airbrake capability as `C_dA_total = C_dA_rocket + C_dA_airbrake`,
and that it has been independently confirmed to **already exist** in `sim/forces.py`'s
`aero_force_body` (Step 49, committed) in exactly that additive-under-a-shared-`q` form, off by
default. Nothing about the airbrake is designed, specced or changed in this document.

---

## Contents

- [§29.1 Scope, method, and what this app is not](#291-scope-method-and-what-this-app-is-not)
- [§29.2 Findings from reading the current code (the facts this design rests on)](#292-findings-from-reading-the-current-code-the-facts-this-design-rests-on)
- [§29.3 Step 61 — module layout, naming, data flow](#293-step-61--module-layout-naming-data-flow)
- [§29.4 The stats bundle — definitions, windows, grid, formulas](#294-the-stats-bundle--definitions-windows-grid-formulas)
- [§29.5 Motor-curve fixtures under `data/motors/`](#295-motor-curve-fixtures-under-datamotors)
- [§29.6 Output — printed table, CSV, overlay plot](#296-output--printed-table-csv-overlay-plot)
- [§29.7 Step 62 — per-motor configuration schema](#297-step-62--per-motor-configuration-schema)
- [§29.8 Config format — the fork, and the recommendation](#298-config-format--the-fork-and-the-recommendation)
- [§29.9 Implementation tickets (Steps 61, 62)](#299-implementation-tickets-steps-61-62)
- [§29.10 Decision points for the user (D-18 … D-27)](#2910-decision-points-for-the-user-d-18--d-27)
- [§29.11 Risks](#2911-risks)
- [§29.12 Rejected options, and the backlog items this opens](#2912-rejected-options-and-the-backlog-items-this-opens)

---

## 29.1 Scope, method, and what this app is not

This is **incremental architecture on an already-approved stack** (Python 3.12 + numpy + scipy +
matplotlib, flat `sim/` package, dispatch-dict model selection, `apps/` for consumer tools) — not a
greenfield design and not a stack pivot, so no grilling interview and no new dependency. Everything
below was derived by reading the current code: `sim/params.py`, `sim/report.py`, `sim/integrate.py`,
`sim/dynamics.py`, `sim/thrust_curve.py`, `sim/flow.py`, `sim/plotting.py`, `sim/state.py`, `run.py`,
`apps/cfd_conditions/select_conditions.py`, `data/motors/placeholder.csv`,
`tests/test_thrust_curve.py`, plus the installed package versions measured in this tree. Where a
claim is load-bearing, the file and line it came from is named in §29.2 so it can be re-checked
rather than taken on trust.

**What the app answers.** "Of these N motors, flown on *this* airframe under *this* one environment,
which gives the highest apogee — and what does each one cost me in peak velocity, peak acceleration,
peak dynamic pressure and flight time?"

**What it is, structurally.** A pure *consumer* of `sim/`. It builds one `Params` per motor via
`sim.params.replace`, calls `sim.integrate.run_sim(p, s0)` once per motor, post-processes each
`Result`, and prints/saves a table ranked by apogee. No new physics, no `sim/` edits, no new
dependency. It is the third such tool in the repo (after `tools/fetch_sounding.py` and "App 2", the
CFD condition selector), and the second under `apps/`.

### Scope — what this first version deliberately does NOT do

Written in the same explicit scope/non-scope style `select_conditions.py`'s own docstring uses.

- **One fixed condition set per sweep run.** The user's phrasing is "for a single defined
  conditions": the launch state `s0`, the site, atmosphere, wind, recovery and solver settings are
  **the baseline's, fixed, not swept**. The only thing that varies across rows is the motor (Step 61)
  and the per-motor vehicle overrides (Step 62). A second sweep dimension (motor × wind, motor ×
  launch angle) is a different tool and is not built here — see **B16** in §29.12.
- **No optimizer.** This is brute-force enumeration of a list the user wrote, which is the degenerate
  case of an optimizer, and deliberately so: the user asked for optimizers to be separate things that
  *use* the simulation. The app therefore exposes one pure function, `evaluate_motor(entry, baseline,
  s0) -> MotorRun` (§29.3), as the objective-function seam a future optimizer app imports. No search,
  no gradients, no continuous design variables here.
- **No motor database and no `.eng`/RASP import.** Motors are whatever CSV files exist under
  `data/motors/` in the format `sim/thrust_curve.py` already reads. Importing real ThrustCurve.org
  `.eng` data is the obvious follow-up and is listed as **B14**, not built.
- **Constant mass.** The baseline keeps the Step-36 mass model off (`Weight.m_d is None`), so
  `Weight.m` is the launch mass held constant for the whole flight — a conservative-on-apogee
  simplification, and *the same* simplification `run.py` and App 2 already make. Step 62's schema can
  turn the mass model on per motor, but doing so honestly needs per-motor propellant mass and `I_sp`,
  which a two-column thrust curve does not carry (**B15**).
- **Ascent-window extrema.** See §29.4: this is a scope call with physics behind it, not an
  implementation shortcut.
- **No uncertainty / Monte Carlo / dispersion.** One deterministic trajectory per motor.
- **No airbrake, recovery or rail work.** All three already exist in `sim/` and are reachable purely
  by configuring the baseline `Params`; none is touched, designed or re-specced here.

---

## 29.2 Findings from reading the current code (the facts this design rests on)

**F1 — `replace()` already does everything Step 62 needs.** `sim/params.py:194-219`: `replace(p,
{"gravity.model": "wgs84", "aero.S": 0.005})` groups the changes by first dotted segment, rebuilds
*only* the touched groups via `dataclasses.replace`, and passes single-segment keys (`"g0"`) straight
through to `Params`. An arbitrary number of keys across an arbitrary number of groups in one call is
the documented, implemented behaviour. **Consequence: Step 62 requires no change to `sim/params.py`.**
Error behaviour, also by construction and worth knowing: a bad *group* name fails at
`getattr(p, group_name)` with `AttributeError`; a bad *field* name fails inside
`dataclasses.replace` with `TypeError`. Both are loud and immediate — no validation layer is needed
or wanted (architecture.md §7, "no input validation").

**F2 — the run entry point and the `Result` shape.** `run_sim(p, s0)` (`sim/integrate.py:420`) is
strict: no kwargs, every solver setting read from `p.solver`. `Result` is a `NamedTuple` of
`(t, y, events, raw, params)` (`integrate.py:82-87`); `events` has exactly the keys `"apogee"`,
`"ground"`, `"burnout"`, `"rail_exit"`, `"parachute_deploy"`, each a float time or `None`
(`integrate.py:487-493`).

**F3 — stale comment, flagged not fixed.** `integrate.py:84` annotates `Result.y` as "shape (6, N)",
but the state has been 7-component since Step 36 (`sim/state.py:30`: `X, Z, VX, VZ, THETA, OMEGA, M
= range(7)`, and `run_sim` integrates `np.array(s0)`). This is a comment-only defect with no
behavioural consequence, and `sim/` is out of scope for these two steps: the app indexes rows by the
`sim.state` constants and never by a hardcoded row count, so it is immune either way. Recorded here
so that a future `sim/` pass can fix it deliberately.

**F4 — what `sim.report` already gives, and over which window.** `flight_summary(result, p)`
(`report.py:33-64`) returns exactly four quantities — `apogee_altitude`, `apogee_time`, `max_q`,
`impact_time` — and takes `max_q` over the **whole recorded flight** (`t_end = impact_time`,
`report.py:50-57`). `print_run_summary` (`report.py:136-139`) likewise takes max speed over the whole
flight. `sweep(base_params, path, values, s0)` (`report.py:67-90`) varies exactly **one** dotted path
over a list of values and attaches `flight_summary` per variant. So: the right loop shape already
exists, but neither the payload (four fields) nor the single-path signature fits this app, and
Step 62's multi-key-per-entry requirement makes the divergence structural rather than cosmetic.

**F5 — why the whole-flight window is the wrong ranking window here.** `docs/roadmap.md:1522-1527`
(Step 55's recorded finding): in the committed `run.py` scenario, `C_m = 0.0` means there is no
restoring moment, so `theta` stays frozen nose-up through a tail-first post-apogee descent, and the
now-real axial drag *accelerates* that fall — the printed max speed (414.7 m/s) occurs during
**descent**, not ascent. Any motor-ranking table built on whole-flight velocity or whole-flight
max-Q would therefore be reporting a descent artifact of the scenario's attitude simplification in
the column the user wants to read as "how fast does this motor make my rocket go". §29.4's
ascent-window rule exists for this measured reason.

**F6 — the dense-grid post-processing pattern is integrator-agnostic.** Both integration paths expose
`result.raw.sol(t)`: RK45's own dense output, and `_LinearInterpolant` for `method="rk4"`
(`integrate.py:213-236`). `flight_summary`, `print_run_summary`, `save_run_artifacts`,
`plotting._dense_time_grid` and App 2 all use the same `t_grid = np.linspace(...)` +
`result.raw.sol(t_grid)` idiom, with `2000` as the established grid size. Caveat to document in the
app: under `method="rk4"` that interpolant is piecewise **linear**, so grid-sampled extrema are only
as good as `p.solver.dt` — the app does not forbid `rk4`, it just inherits that accuracy.

**F7 — acceleration is directly available from the RHS, exactly.**
`dynamics.derivatives(t, y, p, hold=None)` (`dynamics.py:196`) returns `dydt` whose `[VX]`/`[VZ]`
entries are `a_i = F_i / m` (`dynamics.py:268`) with `F_i = weight_inertial + to_inertial(thrust +
aero)` (`dynamics.py:245`). So re-evaluating `derivatives` on a grid gives the **exact** inertial
acceleration the integrator itself saw, including gravity — no finite differencing, no cancellation
error, and no smearing of the thrust curve's kinks (the curve is piecewise linear in `t`, so a
numerical derivative across the ignition spike is precisely where finite differences are worst).

**F8 — post-hoc re-evaluation is consistent, *except* in sampled mode.** `flow_state` is a pure,
deterministic function of `(t, y, p)` — the Step 56 purity argument is recorded in
`dynamics.py:229-239`, including the fact that the Dryden realization is frozen per seed by
`lru_cache`. The same therefore holds for `derivatives`. The one exception is `p.solver.sample_rate_hz
> 0.0` (Step 59): during such a run the RHS saw a `Hold` recomputed once per tick, and a post-hoc
`derivatives(t, y, p)` call with `hold=None` cannot reconstruct it, so the recomputed acceleration
would silently not be the acceleration that produced the trajectory. **The app rejects
`p.solver.sample_rate_hz != 0.0` with a `ValueError`** rather than reporting a number it cannot stand
behind. (Step 59's own caveat — a sampled run is a *different dynamical system*, not a refinement of
the same one — is the same point from the other side.)

**F9 — the motor-curve format, precisely.** `thrust_curve._load_motor_curve(name)`
(`thrust_curve.py:41-77`) reads `data/motors/<name>` with `csv.reader`, skips empty rows and rows
whose **first cell starts with `#`**, takes columns 0 and 1 as `t [s]`, `F [N]`, allows extra
columns, then sorts by time and drops duplicate times. `thrust(t, s, p)` (`thrust_curve.py:85`)
interpolates with `left=thrusts[0]`, `right=0.0` — exactly the first value before the first point,
exactly `0.0` after the last. `p.thrust.motor_curve == ""` short-circuits to `0.0`. With
`Thrust.A_e == 0.0` (the default) the Step-16 pressure correction is bit-exactly inert.

**F10 — `data/motors/` has exactly one file, and the existing test pins it by name.**
`data/motors/placeholder.csv` (162.75 N·s, 5 rows, header comments). `tests/test_thrust_curve.py:58-66`
loads `"placeholder.csv"` explicitly and asserts `np.trapezoid(thrusts, times) == 162.75`. No test
globs the directory, so **adding fixtures cannot affect the existing suite**, and `np.trapezoid` is
the house impulse integrator with an established "state the impulse in the header, pin it in a test"
discipline (§29.5 keeps both).

**F11 — environment facts, measured in this tree (cached here so nobody re-checks).** Python
3.12.10, numpy **2.5.3**, scipy 1.18.1; `requirements.txt` pins `numpy>=2.5,<3`, `scipy>=1.18,<2`,
`matplotlib>=3.11,<4`, `pytest>=8`. `numpy.trapezoid` exists; **`numpy.trapz` does not** (removed in
numpy 2.x) — `hasattr(numpy, "trapz") is False` was verified directly, and
`tests/test_thrust_curve.py:64` already uses `np.trapezoid`. **PyYAML is not installed and not a
dependency** (relevant to D-23). No new dependency is proposed by either step.

**F12 — how an app under `apps/` is invoked.** `apps/` contains no `__init__.py` anywhere (verified);
it works as an implicit namespace package, so the established invocation is
`python -m apps.cfd_conditions.select_conditions` **from the repo root** (verified by import in this
tree). Running the file by path (`python apps/.../x.py`) puts the *script's* directory on `sys.path`
instead of the repo root and would break `import sim`. The new app therefore documents
`python -m apps.motor_selection.compare_motors` in its docstring.

**F13 — artifact conventions.** `output/` is gitignored wholesale (`.gitignore`), created on demand.
App 2 resolves it as `Path(__file__).parent.parent.parent / "output"` and writes
`output/cfd_conditions.csv`. `sim.plotting.plot_trajectory_overlay(results: dict[str, Result], title)`
(`plotting.py:58`) takes `Result` objects keyed by label and returns a 2-panel `Figure` — directly
reusable for a per-motor overlay with **zero** `sim/` change (`report.save_sweep_artifacts` wraps the
same function but expects the `{value: {"result": ...}}` dict shape `report.sweep` produces, so the
app calls `plot_trajectory_overlay` directly instead of bending its data into that shape).

**F14 — there is no test coverage for `apps/` today.** A grep over `tests/` for `apps` returns one
unrelated comment. So the App-2 precedent is "a consumer app ships without tests" — see D-25, where I
recommend departing from it for this app specifically, because Step 61 introduces genuinely new
*numerical* code (the stats bundle), which is the thing this project otherwise always pins.

---

## 29.3 Step 61 — module layout, naming, data flow

### Directory structure (new files only)

```
apps/
  cfd_conditions/
    select_conditions.py            # App 2, untouched
  motor_selection/                  # NEW (Step 61)
    compare_motors.py               # App 3: entries -> runs -> stats -> ranked table
    motors.py                       # NEW at Step 62 only: the per-motor config literal
data/
  motors/
    placeholder.csv                 # existing, untouched
    synthetic_small.csv             # NEW (Step 61)
    synthetic_medium_punchy.csv     # NEW (Step 61)
    synthetic_medium_long.csv       # NEW (Step 61)
    synthetic_large.csv             # NEW (Step 61)
tests/
  test_motor_selection.py           # NEW (Step 61), see D-25
output/
  motor_selection.csv               # generated, gitignored
  motor_selection_overlay.png       # generated, gitignored
```

**Naming** (D-24): directory `motor_selection` (noun phrase naming the question, like
`cfd_conditions`), module `compare_motors.py` (verb-noun, like `select_conditions.py`), docstring
headed `"""App 3 -- motor selection sweep.` to continue the sibling's own "App 2" label.

### The objects

```python
@dataclasses.dataclass(frozen=True)
class MotorEntry:
    """One candidate motor, as configured by the user."""
    name: str            # label for the table / legend / CSV; free text
    motor_curve: str     # file under data/motors/, e.g. "synthetic_large.csv"
    # Step 62 adds exactly one field here:
    # overrides: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class MotorStats:
    """The per-motor stats bundle (§29.4). Every field is a float or None;
    None means "the flight never produced this event"."""
    apogee_altitude: float | None   # m AGL, the ranking criterion
    apogee_time: float | None       # s
    max_velocity: float | None      # m/s, ascent window
    avg_velocity: float | None      # m/s, time-average over the ascent window
    max_accel: float | None         # m/s^2, ascent window, |dv/dt| incl. gravity
    max_accel_g: float | None       # max_accel / p.g0 [-]
    max_q: float | None             # Pa, ascent window
    total_impulse: float | None     # N*s, delivered, numerically integrated
    burnout_time: float | None      # s, from result.events
    impact_time: float | None       # s, from result.events (full flight)
    downrange_impact: float | None  # m, at impact (full flight)


@dataclasses.dataclass(frozen=True)
class MotorRun:
    """Everything one row of the table knows: the input, the Params it
    produced, the trajectory, and the reduced stats. Same role as the
    `{"result": ..., "params": ..., **summary}` dict `sim.report.sweep`
    returns, as a named object instead."""
    entry: MotorEntry
    params: Params
    result: Result
    stats: MotorStats
```

### The functions (the whole public surface of the app)

```python
def build_params(entry: MotorEntry, baseline: Params) -> Params
    # Step 61: params.replace(baseline, {"thrust.motor_curve": entry.motor_curve})
    # Step 62: params.replace(baseline, {"thrust.motor_curve": ..., **entry.overrides})

def flight_stats(result: Result, p: Params) -> MotorStats   # §29.4, pure post-processing

def evaluate_motor(entry: MotorEntry, baseline: Params, s0: State) -> MotorRun
    # build_params -> run_sim -> flight_stats. THE objective-function seam:
    # one entry in, one scored run out, no printing, no I/O, no global state.

def compare_motors(entries, baseline: Params, s0: State) -> list[MotorRun]
    # pre-flight validation pass (see below), then one evaluate_motor per
    # entry, returned sorted by apogee descending.

def print_motor_table(runs: list[MotorRun]) -> None          # §29.6
def save_motor_csv(runs: list[MotorRun], path: Path) -> None # §29.6
def save_overlay(runs: list[MotorRun], path: Path) -> None   # §29.6
def main() -> None                                           # demo scenario + all three outputs
```

**Pre-flight validation pass, before any integration.** `compare_motors` first calls `build_params`
for **every** entry and only then starts integrating. Rationale: a typo in entry #7's override path
raises `AttributeError`/`TypeError` from `replace` (F1) — getting that failure after six completed
integrations instead of in the first millisecond is a pure waste of the user's time. This costs four
lines and is the only "validation" the app does; it adds no checks of its own, it just *moves the
existing ones earlier*.

**The two guards, both raising `ValueError` with an explanatory message:**

1. `p.solver.sample_rate_hz != 0.0` → refuse (F8: post-hoc `derivatives` re-evaluation cannot
   reconstruct the per-tick `Hold`, so `max_accel` would not be the acceleration that flew).
2. (Step 62) `"thrust.motor_curve" in entry.overrides` → refuse. One selector, one place. This
   project has already been bitten by exactly this shape of defect: Phase 2.11 exists partly because
   `aero_model` and `aero_table` were "two uncoordinated selectors for the same thing"
   (`roadmap.md:1419-1420`). Silently letting an override win — or silently letting the explicit
   field win — is the same trap at a smaller scale.

### Data flow

```
 MotorEntry (name, curve [, overrides])          baseline: Params        s0: State
        |                                               |                   |
        +----------------- build_params ----------------+                   |
                              | Params (one per entry)                      |
                              +------------------- run_sim -----------------+
                                                     | Result
                                       flight_stats  |   (one ascent grid; derivatives,
                                                     |    flow_state, thrust re-evaluated)
                                                     v
                                                 MotorRun
                                                     |
                      sorted by stats.apogee_altitude, descending
                                                     |
             +---------------------+-----------------+--------------------+
             v                     v                                      v
      print_motor_table     save_motor_csv                          save_overlay
      (stdout table)        output/motor_selection.csv   output/motor_selection_overlay.png
```

---

## 29.4 The stats bundle — definitions, windows, grid, formulas

This section is the actual substance of Step 61 and the ticket should be implemented from it
literally. Every choice below is a scope call with a reason; where the reason is contestable it is
also a numbered decision in §29.10.

### 29.4.1 The measurement window (D-19)

Two windows, and the rule is per-quantity, not per-table:

| Quantity | Window | Why |
|---|---|---|
| `apogee_altitude`, `apogee_time` | the `apogee` event instant | already event-defined |
| `max_velocity`, `avg_velocity`, `max_accel`, `max_q`, `total_impulse` | **ascent: `[0, t_apogee]`** | F5: whole-flight extrema can be descent artifacts of the frozen-attitude simplification |
| `burnout_time` | event | `result.events["burnout"]` |
| `impact_time`, `downrange_impact` | **full flight** | they *are* end-of-flight quantities |

The ascent rule is the same scope call App 2 already made for the same family of reasons
(`select_conditions.py`'s "Ascent only (the user's own scope call)" section), and it has a useful
side effect worth stating in the app's docstring: **the ranking and every ascent column are
unaffected by the recovery configuration.** Turning a parachute on or off changes only
`impact_time`/`downrange_impact`, so a motor comparison does not have to agree on a recovery system
first.

### 29.4.2 The sampling grid

```python
_ASCENT_GRID_N = 2000   # the house dense-grid size (F6)
_BURN_GRID_N   = 2000   # refinement over the burn only (see below)

t_apogee = result.events["apogee"]
t_burn   = result.events["burnout"]

t_grid = np.linspace(0.0, t_apogee, _ASCENT_GRID_N)
if t_burn is not None and 0.0 < t_burn < t_apogee:
    t_grid = np.union1d(t_grid, np.linspace(0.0, t_burn, _BURN_GRID_N))

y_grid = result.raw.sol(t_grid)          # shape (7, len(t_grid))
```

**Why the burn-window refinement.** A uniform 2000-point grid over an ascent of, say, 25 s has
`dt ≈ 12.5 ms`, while a motor's ignition spike is ~50 ms wide — the peak acceleration would be
sampled a handful of times and systematically **under**-reported, which is exactly the number an
airframe-loads question depends on. Adding a second 2000-point grid over `[0, t_burnout]` gives
sub-millisecond resolution where all the structure is, at a cost of one extra `np.linspace` and
~2000 extra RHS evaluations (~0.1 s per motor at the Step-56-measured 47 µs/RHS). `np.union1d`
sorts and de-duplicates, so the result is a single strictly increasing, **non-uniform** grid — which
is why `avg_velocity` below must be a proper time integral and not `speed.mean()`.

Rejected alternative: pulling the motor curve's own knot times into the grid (which would capture a
piecewise-linear curve's peak *exactly*) requires `thrust_curve._load_motor_curve`, a private `sim/`
function. Not worth reaching across that boundary for an O(dt²) improvement on an already-refined
grid; if it is ever wanted, promoting that loader to public is a one-line `sim/` change, not an app
change.

### 29.4.3 Velocity

```python
speed = np.hypot(y_grid[VX], y_grid[VZ])          # sim.state VX/VZ indices
max_velocity = float(speed.max())
avg_velocity = float(np.trapezoid(speed, t_grid) / (t_grid[-1] - t_grid[0]))
```

`max_velocity` is the inertial speed `|v|`, not airspeed `V = |v_rel|` — these differ only under
wind, and the baseline for this app's demo has no wind; the table column is labelled `v_max[m/s]`
and the docstring states it is ground-frame speed. (Airspeed is one `flow_state(...).V` away on the
same grid if the user ever wants it; not added now, to keep the table narrow.)

`avg_velocity` is the **time-average of speed over the ascent** (D-22), computed with
`np.trapezoid` (F11: `np.trapz` does not exist on numpy 2.5) because the grid is non-uniform. The
two alternatives — `apogee_altitude / apogee_time` (an average *vertical* speed, which for a
vertical flight equals this only if speed were constant) and path-length over time (identical to
this one up to the integration rule) — are listed in D-22. A mean of a non-uniform grid would be
wrong by the ratio of the refined to the coarse spacing and is explicitly not what is specified.

### 29.4.4 Acceleration (D-20, D-21)

```python
dydt = np.array([dynamics.derivatives(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])
accel = np.hypot(dydt[:, VX], dydt[:, VZ])
max_accel   = float(accel.max())
max_accel_g = max_accel / p.g0
```

- **Source: re-evaluation of the RHS, not a finite difference of the velocity grid** (F7). It is the
  exact acceleration the integrator used, it costs one function call per grid point, it needs no
  differencing stencil, and it does not smear the thrust curve's kinks. It is also the established
  house pattern: `report.flight_summary` loops `flow_state` over a dense grid, and App 2 loops
  `flow_state` over 4000 points; looping `derivatives` is the same move against a different model
  function.
- **Semantics: inertial `|dv/dt|`, gravity included** — the literal time derivative of the state's
  velocity, so it is consistent with the trajectory and with `avg/max_velocity` on the same grid.
  It is *not* sensed/load-factor acceleration (what an accelerometer or the airframe's structure
  feels, `(F_thrust + F_aero)/m`), which differs by exactly one `g` in direction-dependent fashion.
  The column header therefore says `a_max[g]` with the docstring spelling out "inertial, includes
  gravity"; D-21 records the fork and notes that the sensed variant is `accel_vector -
  forces.weight_inertial(t, y, p)/m` — one extra public call on the same grid — if the user prefers
  it.
- `max_accel_g` divides by `p.g0` (the `Params` field, `9.80665` by default), not a literal.

### 29.4.5 Dynamic pressure, impulse, apogee altitude, impact

```python
q = np.array([flow_state(t, y_grid[:, i], p).q for i, t in enumerate(t_grid)])
max_q = float(q.max())

T = np.array([thrust_curve.thrust(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])
total_impulse = float(np.trapezoid(T, t_grid))

apogee_altitude = float(gravity.altitude_agl(result.raw.sol(t_apogee), p))

impact_time = result.events["ground"]
downrange_impact = (
    float(result.raw.sol(impact_time)[X]) if impact_time is not None else float(y_grid[X, -1])
)
```

- `max_q` reuses `sim.flow.flow_state` exactly as `flight_summary` does — same model, same call
  shape, different window (§29.4.1).
- `apogee_altitude` uses `gravity.altitude_agl(y, p)` at the event instant, identical to
  `flight_summary`/`print_run_summary`: it is `-y[Z]` bit-for-bit under the default
  `gravity.direction = "parallel"` and the curved-ground reading otherwise, and it must *not* be
  re-derived as `-min(z)` over samples (the reason is in `report.py:122-129`).
- `total_impulse` is the **delivered** impulse over the ascent grid, i.e. `thrust_curve.thrust`
  integrated, which includes the Step-16 pressure correction when `A_e != 0`. Because thrust is
  exactly `0.0` after the last curve point (F9) the ascent window captures all of it. It agrees with
  the fixture's stated nominal to ~0.1 % (grid resolution, not a modelling difference) and is **not**
  a substitute for the exact knot-wise trapezoid `tests/test_thrust_curve.py` already pins; it is in
  the table because it is the single most explanatory column next to apogee (§29.5's equal-impulse
  pair is pointless without it).
- `downrange_impact` falls back to the last ascent-grid sample when the flight never hits the ground
  inside `t_max` — the same "fall back to the last recorded sample" convention `report.py:141-144`
  uses.

### 29.4.6 Degenerate flights

A motor that cannot lift the airframe gives `events["apogee"] is None` (the integrator's `t < 0.1 s`
apogee guard plus a terminal ground event). This is a **legitimate study result** — "this motor is
too small for this rocket" — not an error, so:

- `flight_stats` returns a `MotorStats` with every ascent field `None` when `t_apogee is None`, and
  fills `burnout_time`/`impact_time` from the events anyway.
- `print_motor_table` renders `None` as `nan` (`float("nan")` under a `:12.2f` format), and the CSV
  writes an empty cell.
- Ranking puts such rows **last**, with the sort key
  `key=lambda r: (r.stats.apogee_altitude is not None, r.stats.apogee_altitude if r.stats.apogee_altitude is not None else float("-inf"))`
  and `reverse=True`. Ties keep Python's stable-sort input order, i.e. the user's config order.
- A `motor_curve=""` entry (zero thrust everywhere, F9) must therefore run and report, not crash —
  and that is a cheap test.

---

## 29.5 Motor-curve fixtures under `data/motors/`

Four new synthetic curves, in the same spirit and the same format as `data/motors/placeholder.csv`
and `data/aero/example.csv` (synthetic-but-plausible placeholder data, heavily commented, "not
measured"). Format per F9: `#` comment header, then `t_s,thrust_N` rows. Each header states class,
total impulse, average thrust, burn time and peak, and **the stated total impulse is the exact
trapezoidal integral of the rows**, so each fixture gets the same one-line pin
`tests/test_thrust_curve.py` already applies to `placeholder.csv` (F10).

The set is chosen to span ~8.5× in total impulse *and* to contain one **equal-impulse pair with
different burn profiles** — that pair is the whole physical point of the app: with real
dynamic-pressure-scaled drag (Step 55), total impulse alone does not determine apogee, and the
table is what shows it.

| File | Class | Rows `(t_s, F_N)` | Total impulse (exact trapezoid) | Avg thrust | Burn | Peak |
|---|---|---|---|---|---|---|
| `synthetic_small.csv` | E | `(0,0) (0.05,60) (0.10,30) (1.20,30) (1.40,0)` | **39.75 N·s** | 28.4 N | 1.40 s | 60 N |
| `synthetic_medium_punchy.csv` | H | `(0,0) (0.04,220) (0.10,140) (1.10,140) (1.30,0)` | **169.2 N·s** | 130.2 N | 1.30 s | 220 N |
| `synthetic_medium_long.csv` | H | `(0,0) (0.06,80) (0.15,52) (3.10,52) (3.40,0)` | **169.54 N·s** | 49.9 N | 3.40 s | 80 N |
| `synthetic_large.csv` | I | `(0,0) (0.05,420) (0.12,170) (1.80,170) (2.05,0)` | **338.0 N·s** | 164.9 N | 2.05 s | 420 N |

Arithmetic, so the developer can re-derive rather than trust (segment trapezoids, in order):

- small: `1.5 + 2.25 + 33.0 + 3.0 = 39.75`
- medium_punchy: `4.4 + 10.8 + 140.0 + 14.0 = 169.2`
- medium_long: `2.4 + 5.94 + 153.4 + 7.8 = 169.54`
- large: `10.5 + 20.65 + 285.6 + 21.25 = 338.0`

The two H-class curves are matched to **0.2 %** (169.2 vs 169.54 N·s), deliberately close but not
bit-equal: forcing exact equality needs an unround sustain level or an unround knot time, and the
pair's purpose is the profile contrast (1.3 s punchy vs 3.4 s sustainer), whose effect on apogee is
far larger than 0.2 % of impulse. The header comments say so explicitly, so the near-equality cannot
later be mistaken for sloppiness.

`placeholder.csv` stays untouched and remains usable as a fifth entry (162.75 N·s, H-class
boundary), which is one more reason not to renumber or reshape it.

### The demo baseline (D-26)

`main()` needs a baseline rocket. It is **not** `run.py`'s 0.5 kg toy, for a measured reason: 338 N·s
on 0.5 kg is an ideal Δv of ~676 m/s, i.e. ~Mach 2, where a constant `C_x = 0.5` is not a defensible
aerodynamic model and the ISA extrapolation ceiling (B13) starts to matter. A 1.5 kg airframe keeps
**every** fixture subsonic (largest motor: ideal Δv ≈ 225 m/s before gravity and drag losses,
≲ Mach 0.7) and keeps the smallest motor just barely flyable, which is itself informative:

```python
baseline = Params(
    weight=Weight(m=1.5, I=0.08),                  # launch mass, mass model OFF (m_d=None)
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),  # replaced per entry; never read as-is
    aero=Aero(S=0.00442, d_ref=0.075, l_ref=0.75,  # 75 mm body: S = pi*d^2/4 = 0.004418 m^2
              C_x=0.5, C_z=0.0, C_m=0.0),
)
s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
```

Thrust-to-weight against `m*g0 = 14.71 N`: small 4.1 peak / 2.0 sustain, medium_long 5.4 / 3.5,
medium_punchy 15.0 / 9.5, large 28.6 / 11.6. All four leave the pad; the small one is deliberately
marginal.

`C_z = C_m = 0.0` makes this a vertical, attitude-frozen 1-D shot — the same simplification `run.py`
and App 2 already carry, appropriate for a motor comparison (one variable at a time) and, per F5,
the reason the ascent window is mandatory. The app's docstring states this, and states that the
runtime baseline is the **caller's** concern: `compare_motors(entries, baseline, s0)` takes it as an
argument and `main()`'s literal is a demo, not "the" rocket.

**This document pins no expected apogee values.** Any number here would be a prediction, not a
verified fact; the Step 61 ticket's Check asks for ordering/consistency properties and one
closed-form assertion instead, and the implementer records the actual table in their report.

---

## 29.6 Output — printed table, CSV, overlay plot

### Printed table

Plain text, fixed-width, no table library — the `sim.report.print_sweep_table` /
`select_conditions.print_conditions_table` house style. Rows in ranked order (apogee descending),
which unlike App 2's time-ordered table *is* the answer to the question.

```python
header = (
    f"{'motor':<22}{'impulse[Ns]':>12}{'apogee[m]':>12}{'apogee_t[s]':>13}"
    f"{'v_max[m/s]':>12}{'v_avg[m/s]':>12}{'a_max[g]':>10}"
    f"{'burnout_t[s]':>14}{'max_q[Pa]':>12}{'impact_t[s]':>13}{'downrange[m]':>14}"
)
print(f"\nMotor comparison (ranked by apogee; ascent-window extrema):")
print(header)
print("-" * len(header))
# per row: f"{name:<22}{imp:12.2f}{apo:12.2f}{apo_t:13.3f}{vmax:12.2f}{vavg:12.2f}"
#          f"{ag:10.2f}{bt:14.3f}{mq:12.1f}{it:13.3f}{dr:14.2f}"   (None -> float("nan"))
```

Eleven columns, ~146 characters wide. That is wider than a default terminal and is an accepted
trade: the user asked for the full parameter list per motor in one place, and the alternative
(splitting into two stacked blocks) makes the ranking harder to read. A one-line footnote under the
table restates the two conventions that are otherwise invisible: *extrema are ascent-window
(launch → apogee); `a_max` is inertial acceleration including gravity.*

### CSV

`output/motor_selection.csv`, written with `csv.writer` exactly as `save_conditions_csv` does
(F13). One row per motor in the same ranked order, with **all twelve** stats columns — including
`max_accel` in m/s² (which the printed table omits in favour of `g`) and the motor-curve filename, so
the CSV is self-describing:

```
rank,name,motor_curve,impulse_Ns,apogee_m,apogee_t_s,v_max_ms,v_avg_ms,a_max_ms2,a_max_g,burnout_t_s,max_q_Pa,impact_t_s,downrange_m
```

Step 62 adds one more column, `overrides`, as a `;`-joined `path=value` string — not a nested
structure, because a CSV cell should stay a scalar; its job is traceability ("which row was flown
with which casing"), not round-tripping.

### Overlay plot

`output/motor_selection_overlay.png` via `sim.plotting.plot_trajectory_overlay({run.entry.name:
run.result for run in runs}, title="Motor comparison")` + `fig.savefig(path)` (F13) — the existing
two-panel path/altitude-vs-time figure, keyed by motor name, zero `sim/` change, one line of app
code. Deliberately **not** routed through `report.save_sweep_artifacts`, which expects
`report.sweep`'s `{value: {"result": ...}}` dict shape; building that shape just to reuse a
`mkdir` + `savefig` would be contortion. No `plt.show()` — Step 58 removed it from `sim/report.py`
for a reason (it hung two verification runs).

---

## 29.7 Step 62 — per-motor configuration schema

The user's phase two, verbatim: "add configuration methodology (i.e. for each motor I can also
select dry rocket parameters (for smaller motors the casing is smaller))".

### The schema

One entry per motor: a label, a curve, and an **open dict of dotted-path `Params` overrides**.

```python
@dataclasses.dataclass(frozen=True)
class MotorEntry:
    name: str
    motor_curve: str
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)   # <-- the only new field
```

```python
def build_params(entry: MotorEntry, baseline: Params) -> Params:
    if "thrust.motor_curve" in entry.overrides:
        raise ValueError(...)        # one selector, one place -- §29.3
    return params.replace(baseline, {"thrust.motor_curve": entry.motor_curve, **entry.overrides})
```

That is the **entire** mechanism, and it is why F1 matters: `replace` already takes an arbitrary
number of dotted keys across arbitrary groups in one call, rebuilding only the groups it touches, so
no untouched field of a partially-overridden group can be silently reset to its default. **No change
to `sim/params.py` is required or proposed.** Unknown paths fail loudly and immediately (F1), and the
pre-flight validation pass (§29.3) makes them fail before the first integration.

The override dict is deliberately **open** — any `"group.field"` the user wants, not an enumerated
whitelist of "the dry-rocket parameters". An enumerated subset would have to be extended every time
the user wants to vary something else (nozzle exit area per motor, a per-motor rail length, a
per-motor `A_e`/`p_ref`), and the open dict costs nothing extra because `replace` already validates
by construction.

### Why `MotorEntry` is the right home for per-motor vehicle data

`data/motors/*.csv` is, and stays, pure thrust-versus-time: that is what `sim/thrust_curve.py` reads
and the only thing it reads. A motor's *vehicle* consequences — casing mass, casing length, the body
diameter it forces, the resulting CoG/CoP geometry — are not properties of the thrust curve, they are
properties of *this airframe with that motor installed*. Putting them in the config entry (and not in
the curve file, and not in a parallel motor-metadata table under `data/`) keeps one clean boundary:
**`data/` holds measured/synthetic physics, the app config holds the design decisions about this
vehicle.** It also means the curve files stay compatible with everything that already reads them.

### What a configured entry looks like

Step 62's demo config, with the smaller motors getting a smaller, lighter airframe — exactly the
user's "for smaller motors the casing is smaller":

```python
MOTORS = [
    MotorEntry(
        name="E small (39.75 Ns)",
        motor_curve="synthetic_small.csv",
        overrides={
            "weight.m": 0.90,      # 38 mm casing, lighter airframe  [kg]
            "weight.I": 0.045,     # pitch MOI about the CoG         [kg m^2]
            "aero.S":   0.00114,   # 38 mm body: pi*d^2/4            [m^2]
            "aero.d_ref": 0.038,   # moment/static-margin reference  [m]
            "aero.l_ref": 0.55,    # Reynolds reference length       [m]
            "lengths.l1": 0.22,    # CoP -> CoG                      [m]
            "lengths.l2": 0.30,    # CoG -> thrust point             [m]
        },
    ),
    MotorEntry(name="H punchy (169.2 Ns)",  motor_curve="synthetic_medium_punchy.csv", overrides={}),
    MotorEntry(name="H sustainer (169.5 Ns)", motor_curve="synthetic_medium_long.csv", overrides={}),
    MotorEntry(
        name="I large (338 Ns)",
        motor_curve="synthetic_large.csv",
        overrides={
            "weight.m": 2.40,      # 98 mm casing, heavier airframe
            "weight.I": 0.160,
            "aero.S":   0.00754,   # 98 mm body
            "aero.d_ref": 0.098,
            "aero.l_ref": 1.10,
            "lengths.l1": 0.38,
            "lengths.l2": 0.52,
        },
    ),
]
```

The two H-class entries keep `overrides={}` **on purpose**: they are the equal-impulse pair (§29.5),
and the comparison only isolates burn-profile effects if the airframe is identical between them.
That also means the Step 61 → Step 62 bit-for-bit gate below has non-trivial rows to check.

Field names above are `sim/params.py`'s actual nested names, read from the file, not assumed:
`Weight(m, I, m_d, l_d, l_p, I_d, I_sp)`, `Aero(model, S, d_ref, l_ref, C_x, C_z, C_m, C_A0,
C_N_alpha, C_m_alpha, table, c_mq)`, `Lengths(l1, l2, u_B, u_C, misalign_deg)`.

### The variable-mass option, specified but not enabled (B15)

The honest version of "smaller motor, smaller casing" eventually means the Step-36 variable-mass
model: `{"weight.m_d": ..., "weight.l_d": ..., "weight.l_p": ..., "weight.I_d": ...,
"weight.I_sp": ...}` — five more keys in the same dict, **zero** new code, because `m_d is not None`
is the model's own gate (`params.py:50`, `dynamics.py:257-266`). It is not enabled in Step 62's demo
config for a data reason, not a code reason: `I_sp` and propellant mass are per-motor physical data
that a two-column thrust curve does not carry (F9), so switching it on means either inventing those
numbers or extending the motor data format — **B15**, out of scope. §29.7 records the key set so
that when real motor data arrives, enabling it is a config edit.

### Step 62's bit-for-bit gate

Because the new field has a default and `build_params` degenerates to Step 61's single-key call when
`overrides == {}`, the gate is exact and cheap: **run Step 61's own demo config under Step 62's code
and the printed table and CSV must be byte-identical.** This is the house standard for an additive
step (Steps 50/52/53/56/57/58 all used some form of it) and it is why Step 62 is a separate commit
rather than a fold-in to Step 61.

---

## 29.8 Config format — the fork, and the recommendation

This is D-23, and it deserves its own section because the orchestrator explicitly asked for the
reasoning rather than a preference.

The project's convention for ***`Params` inputs*** is CSV under `data/<kind>/`: `data/motors/*.csv`
(time, thrust), `data/aero/example.csv` (Mach-indexed coefficient table), `data/soundings/<case>/*.csv`
(station profiles). But every one of those files is **tabular physical data**: a fixed column schema,
homogeneous float columns, many rows of the same kind of thing, read by a dedicated `sim/` loader.

A per-motor override list is a different shape: a **short, sparse, heterogeneous key-value map**
(different keys per entry, values that are floats *and* strings *and* possibly `None`), which is
configuration of the model, not data for it. The project already has a convention for *that* too,
established at Step 58 when `run.py` was reduced to "scenario definition only": **scenario
configuration is Python**, a literal in the module, with comments justifying each number.
`select_conditions.py`'s `main()` does the same.

**Recommendation: a Python literal in `apps/motor_selection/motors.py`.** Concretely because:

1. `None` is a *meaningful value* in this schema — `weight.m_d = None` is the mass-model off switch
   (F1/`params.py:50`). CSV cannot express it without a sentinel convention and a parser that knows
   about it; JSON can (`null`), YAML can.
2. Values are heterogeneous (`"aero.model": "table"`, `"aero.table": "example.csv"`,
   `"weight.m": 1.5`), so a CSV route needs a per-cell type-coercion layer — exactly the
   input-validation burden this project deliberately does not carry (architecture.md §7).
3. The key set is open and per-entry sparse. CSV forces either a wide sparse table with one column
   per possible dotted path (brittle, grows forever) or a long `name,path,value` format (three joins
   to read one entry).
4. Comments. Every number in this repo's data files and scenario literals is justified in a comment
   next to it; "0.00114 — 38 mm body, pi d^2/4" is the whole point. JSON cannot carry that at all.
5. A typo is caught by Python itself, at the same place and with the same traceback as the rest of
   the project's configuration.
6. Zero new dependency, zero parser, zero format documentation.

And the cost is bounded by design: **the app's internals never take a file path.**
`compare_motors(entries, baseline, s0)` takes `list[MotorEntry]`. So the format is a one-function
seam — if a non-programmer (or a future optimizer app, or a GUI) ever needs to supply entries, adding
`load_motors_json(path) -> list[MotorEntry]` is a ~15-line addition that changes nothing else. That
is the reason not to agonise over this fork now: it is reversible at near-zero cost, which is itself
an argument for the cheapest option today.

Options and trade-offs are tabulated in D-23.

---

## 29.9 Implementation tickets (Steps 61, 62)

Mirrors the Files/Spec/Do/Check/Commit shape every roadmap step uses; `docs/roadmap.md`'s new
"Phase 2.12" section carries the same two tickets.

### [Step 61] Motor-selection sweep app (App 3) + synthetic motor fixtures

- **Module/boundaries:** new `apps/motor_selection/compare_motors.py`; new
  `data/motors/{synthetic_small,synthetic_medium_punchy,synthetic_medium_long,synthetic_large}.csv`;
  new `tests/test_motor_selection.py` (+ one impulse-pin test per fixture, in
  `tests/test_thrust_curve.py`, following the existing `test_thrust_curve_total_impulse` shape — see
  D-25). **No `sim/` file, no `run.py`, no existing `data/` file.**
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true (touches only new files plus one append to `tests/test_thrust_curve.py`)
- **Spec slice:** `architecture-29-motor-selection.md` §29.2 (findings), §29.3 (layout, objects,
  functions, guards), §29.4 (the stats bundle — implement literally), §29.5 (fixtures + baseline),
  §29.6 (outputs). Nothing outside §29.2-§29.6 is needed.
- **Do:** the four fixtures; `MotorEntry`/`MotorStats`/`MotorRun`; `build_params`, `flight_stats`,
  `evaluate_motor`, `compare_motors`, `print_motor_table`, `save_motor_csv`, `save_overlay`, `main()`;
  both guards (`sample_rate_hz != 0.0`; pre-flight `build_params` pass before any integration);
  ranking with `None`-apogee last. Module docstring in the App-2 register: what question it answers,
  the explicit scope/non-scope list from §29.1, the two conventions from §29.4.1/§29.4.4, and the
  `python -m apps.motor_selection.compare_motors` invocation (F12).
- **Check:**
  - Full suite green and **unchanged in count** apart from the step's own new tests (F10 guarantees
    the new CSVs cannot perturb anything existing: the only motor-curve test loads
    `placeholder.csv` by name).
  - Each new fixture's `np.trapezoid(thrusts, times)` equals the impulse stated in its header
    (§29.5's exact values: 39.75 / 169.2 / 169.54 / 338.0 N·s).
  - One **closed-form** stats assertion, the step's most load-bearing: for a vertical run just after
    ignition (where `V ≈ 0`, hence drag ≈ 0), the computed acceleration magnitude equals
    `T(t)/m - g0` to a stated tolerance — this is what proves the `derivatives`-re-evaluation path
    has the right indices, the right frame and the right units.
  - Cross-check, loose tolerance: `max_accel` from `derivatives` agrees with a finite difference
    (`np.gradient(speed, t_grid)`) of the same velocity grid. The two must not disagree grossly; they
    are not expected to agree tightly (that is the point of D-20).
  - Ordering/consistency invariants: the returned list is non-increasing in `apogee_altitude` with
    `None` last; `0 < apogee_time < impact_time`; `0 < avg_velocity <= max_velocity`;
    `burnout_time < apogee_time` for every fixture.
  - Overrides-free `build_params` leaves every other `Params` field equal to the baseline's (the
    `replace` no-silent-reset property, F1).
  - Degenerate paths do not crash: an entry with `motor_curve=""` reports `nan`s and ranks last.
  - `p.solver.sample_rate_hz = 1000.0` raises `ValueError` from the app (F8), *before* `run_sim`.
  - `python -m apps.motor_selection.compare_motors` from the repo root prints the ranked table and
    writes both artifacts under `output/`; the actual table is pasted into the step report (this
    design pins no apogee values — §29.5).
- **Commit:** "Step 61 (Phase 2.12): motor-selection sweep app (App 3) + synthetic motor fixtures"

### [Step 62] Per-motor configuration methodology (dry-rocket overrides)

- **Module/boundaries:** `apps/motor_selection/compare_motors.py` (one new dataclass field, one
  guard, one `build_params` line, one CSV column); new `apps/motor_selection/motors.py`;
  `tests/test_motor_selection.py`. **No `sim/` file.**
- **Assignee:** developer
- **depends_on:** [Step 61]
- **parallel_safe:** false (edits Step 61's own module)
- **Spec slice:** `architecture-29-motor-selection.md` §29.7 (schema, demo config, variable-mass
  option, the bit-for-bit gate), §29.8 (why the config is a Python literal). §29.3's function
  signatures for context.
- **Do:** add `MotorEntry.overrides: dict[str, Any] = field(default_factory=dict)`; `build_params`
  becomes the single multi-key `replace` call; raise `ValueError` if `"thrust.motor_curve"` appears in
  `overrides`; move the demo config into `apps/motor_selection/motors.py` as `MOTORS` (§29.7's
  literal, with the two H-class entries left override-free on purpose); add the `overrides` CSV
  column as a `;`-joined `path=value` string. Record in the module docstring that this needed **no**
  change to `sim/params.py`, and why (F1).
- **Check:**
  - **Bit-for-bit gate:** Step 61's demo config run under Step 62's code produces a byte-identical
    printed table and CSV (every `overrides` empty). This is the step's primary check.
  - An entry with `{"weight.m": 0.9, "aero.S": 0.00114}` produces a `Params` with exactly those two
    fields changed and **every** other field — including the rest of `Weight` and `Aero` — equal to
    the baseline's.
  - `overrides={"thrust.motor_curve": "x.csv"}` raises `ValueError`.
  - A typo'd group (`"wieght.m"`) raises `AttributeError` and a typo'd field (`"weight.mass"`) raises
    `TypeError`, both from `replace`, and both **before any integration runs** (the pre-flight pass).
  - Full suite green; `python -m apps.motor_selection.compare_motors` with `MOTORS` from §29.7 prints
    a table whose per-motor airframes differ, pasted into the step report.
- **Commit:** "Step 62 (Phase 2.12): per-motor configuration methodology (dry-rocket overrides)"

---

## 29.10 Decision points for the user (D-18 … D-27)

Numbering continues `architecture-28-rewrite.md` §28.12, which used D-1 … D-17.

**D-18 — where the richer stats live.** *Purpose: compute max/avg velocity, max acceleration,
burnout, impulse per motor.*

| Option | Pros | Cons |
|---|---|---|
| (a) extend `sim.report.flight_summary` with the extra fields | `run.py` and any future sweep get them free; one implementation of each quantity | touches `sim/`; `print_sweep_table`'s columns and `docs/PROJECT-STATUS.md`'s pinned sweep tables were just re-pinned at Step 60, and widening them forces another re-pin; forces one window convention on both tools, and §29.4.1's ascent window is **not** what `flight_summary`'s existing whole-flight `max_q` uses |
| **(b) compute all stats locally in the app (recommended)** | `sim/` strictly untouched → regression risk is structurally zero; matches the user's "separate thing" instruction most literally; the app owns its own window convention and can state it in its own docstring; no re-pinning of anything | ~25 lines of grid-sampling code that rhyme with `flight_summary`'s (not shared) |
| (c) hybrid: call `flight_summary` for its four fields, add the rest locally | avoids re-deriving the apogee-altitude subtlety | **mixes windows inside one table row** — `max_q` whole-flight next to ascent-window velocities (F4/F5), the exact inconsistency §29.4.1 exists to prevent; also a second 2000-point `flow_state` pass |

**Recommendation: (b).** The duplication is small and shallow (one `linspace`, one `sol()`, one
`max()`), whereas the coupling (a) and the inconsistency (c) introduce are not. I am confident enough
in this one to have designed §29.4 around it; the fork is listed because it is the one the
orchestrator named.

**D-19 — measurement window.** (a) ascent only for extrema, full flight for impact/downrange
(**recommended**, §29.4.1, grounded in F5's recorded Step-55 finding); (b) whole flight for
everything (simpler, one window — but the velocity column can report a descent artifact); (c) both
windows as separate columns (most informative, ~16 columns wide, and invites the user to read the
wrong one).

**D-20 — acceleration source.** (a) re-evaluate `dynamics.derivatives` on the grid
(**recommended** — exact RHS, no differencing, F7, same house pattern as `flight_summary`'s
`flow_state` loop; ~0.1 s per motor); (b) finite-difference the velocity grid (no extra model calls,
but O(h²)-plus-cancellation error and it smears the thrust curve's kinks, which is where the peak
*is*); (c) both, with (a) reported and (b) as a test-only cross-check (**this is what the Step 61
Check bullet does** — the cross-check costs nothing in the shipping path).

**D-21 — acceleration semantics.** (a) inertial `|dv/dt|`, gravity included (**recommended**:
literally the derivative of the reported velocity, consistent with the same grid, one call); (b)
sensed/load-factor `(F_thrust + F_aero)/m` (what an accelerometer and the airframe feel — arguably
what a rocketeer means by "max acceleration"; needs `forces.weight_inertial` subtracted off, one
extra public call); (c) both columns. If the user's interest is **structural loads**, (b) is the
physically right column and the change is ~3 lines; I recommend (a) only because it is the
self-consistent default and the two differ by ~1 g.

**D-22 — "avg velocity" definition.** (a) time-average of `|v|` over the ascent,
`trapezoid(speed, t)/Δt` (**recommended** — the literal reading of "average velocity", and
window-consistent with `v_max`); (b) `apogee_altitude / apogee_time` (average *vertical* speed —
cheaper, and a different quantity under any non-vertical flight); (c) path length / time (identical
to (a) up to the integration rule for a monotone-direction flight; no added information).

**D-23 — config format for Step 62.** *Purpose: hold one entry per motor = curve + an open dict of
dotted-path `Params` overrides.*

| Option | Pros | Cons |
|---|---|---|
| **(a) Python literal in `apps/motor_selection/motors.py` (recommended)** | zero dependency, zero parser; `None`, strings and floats all expressible; comments next to every number (house discipline); typos caught by Python; matches the Step-58 "scenario definition is code" convention and `select_conditions.py`'s `main()` | config is code — not editable by a non-programmer |
| (b) JSON under `apps/motor_selection/motors.json` | stdlib, typed (`null`/number/string), editable without Python, maps 1:1 onto the override dict | **no comments** — and this repo justifies every number in a comment; a second place where a dotted path can be mistyped, failing as a parse error rather than a Python error; ~15 lines of loader |
| (c) CSV under `data/` | matches the existing convention for `Params` *inputs* | wrong shape: those files are dense tabular physics, this is a sparse heterogeneous key-value map; needs a wide-sparse or long `name,path,value` layout plus per-cell type coercion and a `None` sentinel — a hand-rolled validation layer the project deliberately avoids |
| (d) YAML | comments **and** types | **new dependency** (PyYAML is not installed, F11); the project has added none for data loading so far (soundings are hand-parsed CSV) |

**Recommendation: (a)**, and note the cost is reversible: the app takes `list[MotorEntry]`, never a
path, so (b) can be bolted on later as one loader function without touching anything else (§29.8).

**D-24 — naming/placement.** (a) `apps/motor_selection/compare_motors.py` (**recommended**:
directory = the question, module = verb-noun, mirroring `cfd_conditions/select_conditions.py`);
(b) `apps/motor_sweep/sweep_motors.py` (says "sweep", which is this repo's own word for the pattern
— but reads as mechanism rather than purpose); (c) `apps/motor_trade/trade_motors.py` (the
aerospace term of art, "trade study" — least discoverable for this user).

**D-25 — tests for an app.** (a) add `tests/test_motor_selection.py` (**recommended**: Step 61
introduces new *numerical* code — windows, grids, a re-evaluated RHS — and this project pins every
number it computes; the closed-form pad-acceleration assertion is cheap and would catch a frame or
index error immediately); (b) follow the App-2 precedent and ship no tests (consistent with the
sibling, and nothing under `sim/` changes — but then the stats bundle is the only unpinned numeric
code in the repo); (c) tests for the pure helpers only (`build_params`, ranking), none that
integrate (fast, misses exactly the part most likely to be wrong). **Note for the orchestrator:**
`tests/` is yours; the ticket lists the file, strike it if you prefer (b).

**D-26 — demo baseline rocket.** (a) a 1.5 kg / 75 mm baseline in `main()` (**recommended**: keeps
all four fixtures subsonic, where this scenario's constant `C_x = 0.5` is defensible; §29.5 gives the
literal and the T/W numbers); (b) reuse `run.py`'s 0.5 kg toy for comparability with App 2's
precedent (but 338 N·s on 0.5 kg is ~Mach 2 with a constant drag coefficient — a number the model
cannot stand behind); (c) ship no baseline at all and require the caller to pass one (purest, but
then `python -m ...` has nothing to demo, which breaks this repo's "every app runs out of the box"
pattern).

**D-27 — artifacts.** (a) table + CSV + overlay PNG (**recommended**: the PNG is one line via the
existing `plot_trajectory_overlay`, F13, and a motor comparison is exactly what an overlay is for);
(b) table + CSV only (no matplotlib import in the app); (c) table only.

---

## 29.11 Risks

1. **Ascent-window convention is invisible in a pasted table.** Someone reads `v_max` as
   "max speed of the flight" and compares it to `run.py`'s printed max speed (whole-flight, F4/F5)
   and concludes one of them is broken. *Mitigation:* the footnote under the printed table, the CSV's
   column names, the module docstring, and §29.4.1 all say it; the step report must paste the
   footnote along with the table.
2. **`max_accel` depends on grid resolution, and the peak lives in a ~50 ms spike.** §29.4.2's
   burn-window refinement reduces this to sub-millisecond spacing, but it is still a sampled maximum,
   not an analytic one. *Mitigation:* documented in the function docstring; the exact-knot upgrade
   path (promote `_load_motor_curve`) is named in §29.4.2 if a number ever looks suspicious.
3. **`method="rk4"` silently degrades every stat.** Its interpolant is piecewise linear (F6), so
   grid-sampled extrema inherit `p.solver.dt`. *Mitigation:* documented; not forbidden (forbidding it
   would block a legitimate cross-check). Only `sample_rate_hz != 0.0` is a hard error, and for a
   correctness reason, not an accuracy one (F8).
4. **The fixture set is synthetic.** The ranking it produces is a demonstration of the tool, not
   advice about real motors. *Mitigation:* every header says "synthetic, not measured" in the
   `data/aero/example.csv` register; B14 names the real-data path.
5. **Per-motor overrides can silently change several things at once.** That is the feature, and it is
   also how a user accidentally compares two different rockets and calls it a motor comparison.
   *Mitigation:* the CSV's `overrides` column records exactly what each row flew with, and §29.7's
   demo config keeps the equal-impulse pair override-free on purpose.
6. **Constant mass flatters the heavy motors.** With the mass model off, a 338 N·s motor's propellant
   mass is carried to apogee, which is conservative on apogee but not uniformly so across the set, so
   the *ranking* could in principle differ from a variable-mass run. *Mitigation:* stated in the
   non-scope list; B15 is the fix and §29.7 pre-specifies the key set it needs.
7. **Wide table.** ~146 characters wraps in a default terminal. Accepted (D-27/§29.6); the CSV is the
   machine-readable copy.

---

## 29.12 Rejected options, and the backlog items this opens

**Rejected: generalise `sim.report.sweep` to take per-variant override dicts.** It is the same loop
shape, and `sweep(base, path, values, s0)` is one signature change away from `sweep(base,
list_of_change_dicts, s0)`. Rejected because it touches a tested `sim/` API and its printed-table
companion for the benefit of exactly one caller, and because the payload differs anyway (D-18). The
app's own `compare_motors` is ~10 lines; the coupling would outlive the saving.

**Rejected: an `optimizer` layer in this app.** The user asked for optimizers to be separate things
that use the simulation. `evaluate_motor` is the seam; nothing more is built now (§29.1).

**Rejected: a motor metadata table under `data/motors/`** (propellant mass, casing mass, `I_sp` per
curve). It is the right eventual home for B15's data, but inventing the format before there is real
data to put in it is exactly the kind of speculative schema this project has avoided. §29.7 instead
records which `Params` keys that data would feed.

**Rejected: sweeping the environment in the same run** (motor × wind, motor × launch angle). The
user said "for a single defined conditions"; a 2-D sweep is a different table, a different ranking
question and a different tool (B16).

**Rejected: a new dependency** for config (PyYAML), tables (`tabulate`/`rich`) or data frames
(pandas). The project's standing decisions (architecture.md §22 items 3-4) and F11's measured
environment both say no; the plain-text table style is an established house convention, not an
accident.

### Proposed new backlog items

- **B14 — real motor data (`.eng`/RASP import, a motor database).** `data/motors/` holds synthetic
  curves only. ThrustCurve.org publishes `.eng` files (header line with diameter, length, delay,
  propellant and total mass, then `t F` pairs) — a ~40-line converter into this project's existing
  CSV format, in the spirit of `tools/fetch_sounding.py`, would make App 3 answer the user's question
  about *actual* motors. The header's propellant/total-mass fields are also exactly what B15 needs.
- **B15 — per-motor mass/geometry metadata and the variable-mass model.** Enabling Step 36's mass
  model per motor needs propellant mass and `I_sp` per motor, which a two-column curve does not
  carry (F9). Needs a data-format decision (sidecar CSV, extra header comment keys, or B14's `.eng`
  header). Zero new *code* beyond that: five more override keys (§29.7).
- **B16 — two-dimensional sweeps (motor × environment).** Motor against wind, launch angle, site
  elevation or rail length, with the same stats bundle. Mechanically a nested loop over
  `evaluate_motor`, but a genuinely different output format (a matrix, not a ranked list) and a
  different question, so it is a separate tool, not a flag on this one.
