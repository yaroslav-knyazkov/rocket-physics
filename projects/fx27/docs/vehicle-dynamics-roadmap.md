# fx27 vehicle-dynamics & optimization roadmap

**Status: pre-stage brainstorming notes**, captured by the orchestrator from a planning
conversation with the user (2026-11-03). Not a `dev/docs/architecture-NN` document, not yet
approved as a committed stage -- no tracker entry (Step/Phase) exists for this work yet. When the
user is ready to turn any one phase below into an actual stage, this file is the starting brief
for `product`/`architect`, not a substitute for their output. Same status/role as the sibling
`airbrake-controller-plan.md` in this same folder.

**Goal, in the user's own words:** understand the rocket's non-controlled (open-loop) behaviour and
optimize rocket parameters to reach a specific target altitude -- default 3000 m AGL. cspace and
euroc are two separate campaigns with separate configuration-choice problems; both eventually feed
into airbrake sizing, then full attitude dynamics, then roll + airbrake closed-loop control.

**Relationship to `airbrake-controller-plan.md`:** that document (owned by a parallel session) is
the fidelity-ladder/controller-tier design for the airbrake *closed-loop control* problem (rungs
0-8, Tier 1/2/3 controllers). This document is the *open-loop vehicle-optimization* track: choosing
the airframe/motor/brake-size, up through full 3D + roll. **F10 below (roll + PID + airbrake
co-tuning) is exactly where the two tracks merge** -- see F10's note before scoping it, so the two
sessions don't design the same merge twice.

## What already exists -- don't rebuild these

- **cspace, constant drag ("dc")**: 3 base rockets (`pro54_transition`, `pro54_equal`, `pro75`) + 4
  idealized mass/drag variants solved for 3000 m AGL (architecture-38, the AC-3 oracle).
- **cspace, Mach-dependent drag ("dm")**: in flight right now, Phase 2.22/Step 145
  (architecture-40) -- 3 dm rockets + 4 idealized dm variants + a `comparison_dc_dm.py` run script.
  No fx27-supplied oracle exists for the dm "ideal" numbers (unlike dc's AC-3) -- sanity-checked
  only, flagged explicitly as a gap in that architecture doc (SS40.9/SS40.11).
- **euroc, constant drag**: 12 airframe configs x 27 candidate motors (24 runnable, 3 deferred),
  single target (3000 m AGL implied by the base config set) -- no Mach-dependent drag yet, no
  9000 m target variant yet.
- **The generic apogee-target root-finder** (`apps/optimization/apogee_targeting/`, Phase 2.21):
  `solve_for_target_apogee` + named wrappers `estimate_airframe_mass`/`estimate_cx` -- this is what
  actually produced every "idealized" number quoted above. It is campaign-agnostic already.
- **Airbrake sizing** (`apps/optimization/airbrake_sizing/solve_cda.py`, wrapped as
  `projects/fx27/point/airbrake.py`, run via `runs/cspace/airbrake.py`) -- static, open-loop brake
  area for a fixed target apogee. Not yet wired to euroc.
- **CFD-condition selection** (`apps/analysis/cfd_conditions/select_conditions.py`) -- already
  answers "which (V, AoA, M, Re) combinations are worth a CFD run," weighted by time-integrated
  dynamic pressure. Pure consumer of `sim/`, campaign/fidelity-agnostic.
- **Weight-vs-aero trade surface** (`apps/analysis/weight_aero_tradeoff/trade_surface.py`) -- the
  2-D `C_dA x mass` iso-apogee exchange-rate surface already exists at the generic `apps/` level.
  **This is very likely most of F8 below already built** -- check it before writing anything new.
- **Dispersion/Monte Carlo** (`apps/analysis/ensemble`) -- for later robustness checkpoints.
- **Sampled airbrake control laws** (`apps/control/flight_software/laws.py`) -- including a
  closed-form drag-aware predicted-apogee estimator already. Owned by the other session's
  controller track, not this one, but it means the "predict where this will land" building block
  for F10 already exists.
- **`apps/sim/engine/aero.py`'s "table" model** -- already Mach-*and*-alpha aware, already carries
  `cop_l1`/`l_p` (CoP location) at every grid point. **F9's static-stability analysis has no new
  physics to write** -- it is a report/consumer over data the engine already produces (see F9).
- **`apps/sim/engine/`'s attitude dynamics** (`_cross_y`/`derivatives`, full rigid-body state) --
  always present; Option C (frozen attitude) is a special-cased `aero.model`, not a separate
  point-mass solver. **F7 (2D/3D) is very likely "turn `omega`/`C_z`/`C_m` back on," not a new
  solver** -- confirm with `architect` before writing new equations of motion (same note
  `airbrake-controller-plan.md` SS0 already makes for its own Rung 5).

## Timeline

### F1 -- cspace dm comparison & configuration choice (in progress, Step 145)
**Status: landing now.** `comparison_dc_dm.py` gives the dc-vs-dm 14-row table. The user has
already ruled out `pro54_equal` ("doesn't seem good enough") -- recommend making that explicit in
the comparison output's default view once dm numbers are in (not a code change yet, just how the
results get read/reported). The actual pro54_transition-vs-pro75 choice is a weight-vs-aero
judgment call the user says they're not sure on yet -- not automatable; **[OPEN]** see F8/trade
surface below, which is exactly the tool for turning "not sure" into a number.

### F2 -- automate the "idealized rocket" workflow (new ask)
**Status: not started.** Today, `rockets_ideal.py`/`rockets_dm.py` hand-type the *solved* mass/C_x
numbers as constants, `dataclasses.replace`d onto the base rocket -- editing the base rocket means
manually re-running the solver and re-typing the result. Two ways to remove that manual step:
  - **(a) Live-compute at import time**: call `solve_for_target_apogee` directly inside
    `rockets_ideal.py`, never hand-type a solved number -- always in sync, but makes module import
    slower (one solve per idealized rocket, every time anything imports the module) and couples
    config-literal modules to a numerical solver (a departure from this project's "config modules
    are plain data, no solver calls" convention elsewhere).
  - **(b) A regenerate-script + committed constants** -- same shape architecture-40 just chose for
    the dm aero tables (SS40.3.3): a one-off tool run manually whenever the base rocket changes,
    writing the solved constants back into the module. Matches existing convention, but the "don't
    forget to re-run it" manual step doesn't fully go away, just moves.

  **Decided (2026-11-03, user)**: (b), a regenerate-script -- same shape as Step 145's aero-table
  generator. Note AC-3's own oracle values stay exactly as hand-typed regardless (they're fx27's
  own already-solved numbers, not this project's output) -- this applies only to *this project's
  own* idealized rockets, never to the oracle constants.

### F3 -- one shared "config" per rocket across fidelity levels (new ask)
**Status: not started, premature to design now.** `apps/sim/schema.py`'s `Rocket`/`Params` shape is
already fidelity-agnostic in principle (Option C point-mass is just `aero.model="constant"` +
zeroed coefficients on the *same* `Rocket`, not a different class) -- there is a real chance most of
this "just works" once 2D lands (F7) without new machinery. Recommend deferring an explicit review
to when F7 actually starts, with `architect`, rather than building a config layer speculatively now.

### F4 -- euroc Mach-dependent drag (blocked on external input)
**Status: blocked.** Needs a colleague's Barrowman-derived drag-vs-Mach curve generator -- outside
this team's control until supplied. Once the curves exist, this is the *same* recipe
architecture-40 just built for cspace (bare `Mach,Cd` curve -> `aero.model="table"` v1 CSV,
`C_N=C_m=0`, `cx_scale` for any idealized/scaled variant) -- expect this to be the fast part once
unblocked.

### F5 -- euroc configuration shortlist for 3000 m and 9000 m, with cost
**Status: not started, depends on F4.** Run the (then Mach-dependent) comparison across all euroc
configs x candidate motors at *both* target altitudes, producing a ranked, costed shortlist.
**[OPEN]**: no cost/price field exists anywhere in `Motor`/`Rocket` today -- this needs a small new
data field (or a sidecar cost table keyed by motor/airframe name), not a structural change. Flag to
`architect` when this phase is scoped; motor price data itself is the user's to supply.

### F6 -- airbrake sizing for the chosen configs (cspace dm + euroc), with two refinements
**Status: not started, depends on F1 (cspace choice) and F5 (euroc shortlist).** Two things the
user flagged that change today's airbrake-sizing recipe:
  - **(a) Overshoot margin.** Don't idealize the base rocket to land exactly on the target; idealize
    it to overshoot by some margin, then size the brake to pull it down to the real target --
    standard airbrake-sizing practice, gives the brake something to actually do. The *margin
    amount* is a design choice, not derivable from physics alone. **[OPEN]** -- needs a number (or a
    rule, e.g. "+X% of target altitude") from the user/architect when this phase is scoped.
  - **(b) Different trigger variable per campaign.** cspace fires the brake after a fixed **time**
    (post-burnout); euroc fires after a fixed **altitude**. Check `apps/control/flight_software/`'s
    existing laws/trigger logic for whether both are already supported generically, or whether this
    needs a small extension -- don't assume either way without checking.

### F7 -- single 2D/3D flight (point-mass -> full attitude dynamics)
**Status: not started.** Per "What already exists" above, this is very likely "turn `omega`/`C_z`/
`C_m` back on" on the *same* engine, not a new solver -- confirm with `architect` first. **Shared
with the other session's controller-plan Rung 5** -- do not scope this twice; whichever session
gets here first should hand the other a pointer rather than redesign it.

### F8 -- CFD-driven weight-vs-C_d optimization
**Status: not started.** The *generic* machinery for this (`apps/analysis/cfd_conditions`,
`apps/analysis/weight_aero_tradeoff/trade_surface.py`) **already exists at the `apps/` level** --
check what it already does before writing anything fx27-specific; this phase may be mostly "wire
fx27's rockets into the existing tool," not new code. **Decided (2026-11-03, user)**: 2D -- so
this phase now depends on F7 landing first (full attitude dynamics), unlike the point-mass-first
default this doc originally recommended. Natural sequencing partner for F9 (both want better
CoP/C_d data, likely from the same Barrowman/CFD source as F4).

### F9 -- stability analysis
**Status: not started.**
  - **Static stability**: CoP-CoG margin -- the engine's "table" aero model already carries CoP
    location (`l1`/`l_p`) at every `(M, alpha)` grid point (Step 99/102). This is very likely a
    reporting script over data the engine already produces, not new physics.
  - **Dynamic stability**: yes, this is a real, established concept -- whether oscillations about
    trim *decay* (not just whether a restoring moment exists), governed by the pitch-damping
    derivative `c_mq` already in the engine (`Aero.c_mq`, Step 44). The user's instinct ("constant
    perturbations, is it stable") maps directly onto this.
  - **Stability-vs-performance trade** ("least securely stable" rocket): an optimization over
    static margin vs. the drag/weight penalty of carrying more margin than needed -- natural fit
    for `apps/optimization/` once the static-stability report above exists.
  - Depends on decent CoP/C_d data (Barrowman or CFD) -- sequence alongside or after F8, not before.

### F10 -- reaction-wheel roll control + PID + 3D integration + airbrake co-tuning
**Status: not started.** Clarified by the user: "roll dynamics" means an **active reaction-wheel
(RW) roll control system**, not passive fin-cant-driven roll. Two coupled sub-models, not one:
  - **Body roll channel**: `I_roll * omega_roll_dot = T_reaction + T_disturbance` -- the body's own
    roll-axis rotational dynamics, driven by the wheel's reaction torque plus whatever aerodynamic/
    manufacturing roll-disturbance torque exists (likely small/placeholder initially, same spirit
    as this project's other "inert until modeled" placeholders).
  - **Wheel's own dynamics**: motor torque limits, the wheel's own momentum storage and
    desaturation budget (a reaction wheel saturates -- how much roll authority is available over
    the whole flight is itself a sizing question, not just a controller-gain question).
  - **Controller**: a PID (first on a simplified/linear roll model per the user's own staging,
    "at the beginning simplified roll dynamics") commanding wheel torque from a roll-angle/rate
    error, tuned first in isolation, then in the full 3D sim.

  This is a genuinely separate control axis from the pitch/airbrake story above and from
  `airbrake-controller-plan.md`'s own fidelity ladder (which is apogee/airbrake-focused, pitch-axis
  only) -- **not automatically covered by "do 3D," needs its own scoping**, including a new
  actuator model (the reaction wheel itself) that nothing in `apps/control/` currently has an
  analogue for (the airbrake is a drag actuator, not a torque actuator).

  **This is also where the two roadmaps explicitly converge**: "fine-tune [roll PID] with the air
  brake controller" means co-tuning against whatever controller tier
  `airbrake-controller-plan.md`'s track lands on (Tier 1/2/3) -- the two loops (roll-via-wheel,
  apogee-via-airbrake) act on different axes/actuators but share the same vehicle state and flight
  timeline, so cross-coupling checks (does roll error perturb the airbrake's apogee prediction via
  attitude, does brake deployment perturb roll via asymmetric flow) are the actual "co-tuning" item,
  not just running two independent PIDs side by side. Recommend: scope the reaction-wheel roll
  dynamics + PID on their own first (a well-bounded, mostly-independent sub-problem), and treat the
  cross-coupled co-tuning step as a joint checkpoint between both sessions' work, not something
  either side designs alone.

## Summary of additions/edits suggested above

1. F2: **decided** -- regenerate-script (same shape as Step 145's aero-table generator).
2. F3: defer to F7's architect review, don't build speculatively now.
3. F5: needs a cost/price data field -- doesn't exist yet.
4. F6: overshoot-margin amount is an open design choice, not derivable; verify trigger-type
   (time vs. altitude) support in `apps/control/flight_software/` before assuming new code is
   needed.
5. F7: shared with the other session's Rung 5 -- coordinate, don't duplicate. Now also a hard
   dependency of F8 (below).
6. F8: **decided** -- 2D (not point-mass-first); depends on F7 landing first. Check
   `apps/analysis/weight_aero_tradeoff/trade_surface.py` first -- likely already does most of
   this generically, just needs the 2D state plumbed through.
7. F9: no new physics needed for static stability (data already in the engine) or dynamic
   stability (c_mq already modeled) -- this is mostly a reporting/analysis layer, not new sim code.
8. F10: roll means a **reaction wheel** (active torque actuator + its own momentum/saturation
   budget), not passive fin-driven roll -- needs a new actuator model, is its own axis not
   subsumed by "3D," and the airbrake co-tuning sub-step is a joint checkpoint with the other
   session, not a solo design.
