# Rocket Trajectory Simulation — Project Status

## Summary
Personal-use rocket trajectory simulator, built from scratch in Python (no RocketPy).
Physics spec lives in `main.tex` (source of truth, updated by the user as derivations evolve).
Approach: incremental, step-by-step, one small piece at a time, committed individually.

- Phase 1: 2D planar rigid-body sim (translation + pitch rotation), all force/model parameters
  as constants (no real thrust curve, no wind, no varying atmosphere yet).
- Phase 2: replace constants with real models (thrust curve + mass depletion, atmosphere,
  wind, aerodynamic coefficients as functions).
- Phase 3: extend to 3D (full 6-DOF).

## Scope notes (per user)
- Single user, personal tool — no need for input validation/normalization, multi-user config, etc.
- Everything currently in `main.tex` should be reflected in code; models start as constants.
- Commit after every completed step (small, reviewable increments).

## Phase 2.13 — Apps 4-5, shared app layer, reusable configs, git-flow — COMPLETE (2026-10-13)

**All 7 steps done, each independently verified by the orchestrator (full test suite re-run,
`git diff`/`git status` review, direct execution, byte-identical-output re-checks via git-stash
round-trips where the gate called for it) before committing — never taken on a developer's
self-report alone:**

- Step 63 `932c285` — `configs/` package (`Config`/`Variant`, explicit registry, three seed
  configs). 306/306 tests.
- Step 64 `fd68de6` — `apps/common/` (shared `flight_stats`/`artifacts`/`cli`), promoted verbatim
  out of App 3. Byte-identical App-3 output confirmed. 307/307 tests.
- Step 65 `1b3c785` — airbrake deployment triggers in `sim/control.py` (the phase's only `sim/`
  change, D-36-revised, user-approved). F17 equivalence re-verified directly (3.8e-8 m agreement).
  314/314 tests.
- Step 66 `e211073` — App 4, airbrake `C_dA`/deploy-time sizing against the real solver, replacing
  the `temp/` MATLAB prototype. Round-trip pin re-verified directly (1.2e-8 m² agreement). 331/331.
- Step 67 `9fddb2a` — App 5 mode (b), the weight-vs-aero trade surface + exchange rate. Interrupted
  once by a session usage-limit reset mid-task; resumed the same agent from its on-disk files per
  standing policy rather than restarting. 121/121 grid points flew, exchange rate -3.7 to -33.8
  mm²/g across the grid, 39.04 s wall-clock (orchestrator's own re-run). 342/342 tests.
  **Final test count: 353/353.**
- Step 68 `0b37876` — App 5 mode (a), named-configuration comparison. The load-bearing mode(a)/
  mode(b) cross-check agreed to ~0.1-0.3% relative — the two App-5 modes do not disagree where
  they overlap. 349/349 tests.
- Step 69 `5f72f44` — migrated `run.py`/App 2/App 3 onto `configs/`, bit-for-bit. All three
  migrated entry points byte-identical pre/post (independently re-captured via git-stash
  round-trip, not just trusted). Two remaining root wrappers added
  (`run_motor_sweep.py`/`run_cfd_conditions.py`) — all "five run files" the user asked for are now
  `ls`-visible at the repo root. 353/353 tests.

**Headline capability delivered**: airbrake `C_dA` sizing (and deploy-time sizing) against the
real solver with three selectable deployment triggers; a weight-vs-aero trade surface *and* a
named-configuration comparison tool; a shared, reusable, git-history-tracked `configs/` package
usable by every app; five `ls`-visible run files at the repo root; git-flow branching adopted
(`develop` + `feature/phase2.13-apps-and-configs`, 9 commits on the feature branch including the
design commit, not yet merged — awaiting the user's go-ahead to land).

Full decision log (D-28 through D-42, D-36-revised parts 1-3): `status.json`'s
`phase2_13_apps_configs.decisions_log`. Design doc: `docs/architecture-30-apps-4-5-and-configs.md`.

Requested by the user on 2026-10-13, mirroring their own Notion "To Do" list reorganized 2026-10-10
("single simulation / motor sweep / air brake parameters determination / cfd input parameters
determination / cfd optimization (weight vs aerodynamics)"): five "run files," of which three
already existed (`run.py`, `apps/motor_selection/` "App 3", `apps/cfd_conditions/` "App 2") — the
new work is "App 4" (airbrake `C_dA` sizing, modernizing two `temp/` MATLAB scratch files the user
pointed at) and "App 5" (a weight-vs-aero trade-off tool), plus a shared config-reuse system and
adopting git-flow branching. Design: `docs/architecture-30-apps-4-5-and-configs.md`
(`architecture.md` §30 pointer). Steps 63-69, continuing the sequence (last used: 62).

**Decisions approved by the user (2026-10-13), all via AskUserQuestion, all on the architect's own
recommendation except where noted:**
- D-28 shared ascent-window stats bundle promoted to `apps/common/flight_stats.py` (App 3 re-exports
  `MotorStats = FlightStats`, zero test edits).
- **D-29 (user choice)** — four thin root wrappers (`run_motor_sweep.py`, `run_airbrake.py`,
  `run_cfd_conditions.py`, `run_trade.py`) added alongside unchanged `run.py`, so all "five run
  files" are literally `ls`-visible at the repo root.
- **D-30/D-31 (user choice)** — `configs/` package, Python-literal modules (same convention as
  Step 62's `motors.py`, D-23), two shapes: `Config` (a full params+`s0` baseline) and `Variant` (a
  named override dict, generalizing `MotorEntry.overrides`) so App 3's motor-keyed deltas and App
  5's named-scenario comparisons both fit.
- D-32 `run.py`/App 2/App 3's demo baseline migrate onto `configs/` behind a bit-for-bit
  (byte-identical-output) gate (Step 69); `apps/motor_selection/motors.py` stays put.
- D-33 `--config NAME`/`--list-configs` CLI via `apps/common/cli.py` on the new apps/wrappers.
- D-34 App 4 solves for the scalar `C_dA_airbrake` (not `airbrake_S_max`/`airbrake_Cd` jointly —
  the sim only ever uses their product, so solving both is ill-posed); `airbrake_Cd` is a fixed
  design input, `S_max` is back-computed and reported.
- D-35 App 4 search method: `scipy.optimize.brentq` root-find on `apogee(C_dA) - target` (exploits
  measured strict monotonicity; `minimize_scalar`/`fminbnd`-style squared-residual search available
  as a `method=` fallback for a literal MATLAB cross-check).
- **D-36 REVISED — three parts, all resolved by direct user answer, not just architect
  recommendation:**
  - **Part 1:** the user's own "three airbrake laws" (after burnout / after a specified time /
    after apogee) genuinely conflict with "no sim file touched" for 2 of the 3 — confirmed by
    reading `sim/control.py` (the existing `"proportional"` law hardcodes the post-burnout/
    pre-apogee window in its body; no parameter choice reaches a time trigger or a post-apogee
    trigger). **User chose: small, isolated `sim/` change** — `sim/params.py` +2 defaulted
    `Control` fields, `sim/control.py` +~35 lines (a trigger dispatch dict + one "full open" law),
    same shape this codebase already uses for the parachute's timer/apogee triggers
    (`sim/forces.py`'s `parachute_deployed`). Bit-for-bit safe by construction; `_proportional_airbrake`
    itself is untouched. This is the phase's *only* `sim/` step (Step 65).
  - **Part 2:** a post-apogee-triggered brake provably cannot be sized against an apogee target
    (measured: apogee flat to 2.4mm across the whole `C_dA` range once apogee-gated — the trigger
    fires only strictly after the apogee instant, so there is no signal to optimize). **User chose:
    implement the trigger, but App 4 detects the flat objective and refuses to solve, with a clear
    explanation** (root cause is a separate, already-known gap — backlog B17/B23, frozen-attitude
    tail-first descent behaves nonphysically in this simulator today).
  - **Part 3:** App 4 also solves for *deploy time* at a fixed known `C_dA` (apogee is measured
    monotone in deploy time too — same `brentq` seam, ~10 extra lines). **User chose: yes, support
    both solve targets.**
- D-37 App 4 runs the full launch-to-apogee flight per iterate (not a mid-flight-state-injected
  reduction matching the MATLAB precedent literally — measured faithful and simpler; a restart-from-
  burnout optimization is backlog B21 for if/when runtime becomes a real cost).
- **D-38 (user choice)** — App 5 builds **both modes**: the weight-vs-aero trade surface (b) first
  (a reusable 2D `apogee(C_dA, mass)` grid + exchange rate), then named-configuration comparison (a)
  second (reusing the new `Config`/`Variant` system, for cases differing in more than mass+drag).
- D-39 trade surface axes: `C_dA` swept via `aero.C_x` at fixed `aero.S` (measured: apogee is an
  exact function of the product `S*C_x`, so one scalar legitimately represents drag) × `weight.m`.
- D-40 the surface is recomputed on demand (CSV + contour PNG under gitignored `output/`,
  `apogee_at()`/`exchange_rate()` as the query API) — not committed as a `data/` input, since
  `data/` in this repo means measured/synthetic physical input, and a 121-point surface recomputes
  in ~5.8s.
- D-41 pinned tests per new step (round-trip/monotonicity/axis-invariance checks), same standing as
  every other step in this project.
- D-42 app naming: `apps/airbrake_sizing/solve_cda.py`, `apps/weight_aero_tradeoff/
  {trade_surface,compare_configs}.py`.

Git-flow adopted the same day, orchestrator-side (not a step): `develop` branch off the prior
`master` trunk; `feature/phase2.13-apps-and-configs` off `develop` for this phase's work; `temp/`
(the two scratch MATLAB files that were this phase's own airbrake precedent) added to
`.gitignore`. Commits `25a512c` (git-flow adoption), architect's design commit to follow.

Steps 63 (`configs/` package), 64 (`apps/common/` promotion) and 67 (trade surface) are
parallel-safe against each other and against Step 65; only Step 66 (App 4) blocks on Step 65
landing first. Implementation proceeds sequentially per this project's standing "one step, one
commit, full regression suite after each" rule regardless of what could technically run in
parallel.

## Phase 2.12 — motor-selection app — COMPLETE (2026-10-13), Step 30 still paused, unchanged by it

**Both steps (S61–S62) done, each independently verified by the orchestrator, not taken on any
agent's self-report alone** — commits `06dcffd` (S61) and the S62 commit immediately below this
section's own update. New `apps/motor_selection/compare_motors.py` (App 3): sweeps a baseline rocket
across a list of `motor_curve` files, ranks by apogee, reports max/avg velocity, max acceleration,
burnout/apogee/impact time, downrange and max-Q per motor over an ascent-only measurement window. 4
new synthetic `data/motors/*.csv` fixtures (small/medium_punchy/medium_long/large), including a
deliberate equal-impulse pair (169.2 vs 169.54 N·s) that demonstrates the tool's actual point — a
punchy short burn reaches 409.6 m vs a long slow burn's 360.8 m at (almost) the same total impulse,
because real dynamic-pressure-scaled drag punishes time spent fighting gravity more than it punishes
peak thrust. 15 new pinned-value tests in `tests/test_motor_selection.py` (S61: 260 → 279, all green);
zero `sim/` files touched. One finding surfaced, not fixed (out of scope for S61, recorded as
**Backlog B17**): a `motor_curve=""` entry under the demo's actual constant-aero baseline drives
`solve_ivp` to fail after an unconstrained tail-first high-speed free-fall — a `sim/`-level
numerical-stability gap in the spirit of the already-recorded Step-55/F5 finding, not an `apps/` bug.

**S62 — per-motor dry-rocket configuration** (the "smaller motor, smaller casing" ask): `MotorEntry`
gains an `overrides: dict[str, Any]` field (default empty, so every S61 entry is bit-for-bit
unchanged), merged into one `sim.params.replace` call alongside `thrust.motor_curve` — needed **zero**
`sim/` changes, since `replace` already accepted arbitrary multi-key dotted paths. `thrust.motor_curve`
is reserved: an override that also sets it raises `ValueError` pre-flight (one selector, one place —
the same lesson as the `aero_model`/`aero_table` defect from Phase 2.11). New
`apps/motor_selection/motors.py`: a commented Python literal (`MOTORS: list[MotorEntry]`) per the
user-approved D-23 — the small motor gets a lighter/38 mm-body casing (0.9 kg), the large motor a
heavier/98 mm-body one (2.4 kg), the two equal-impulse H-class motors deliberately left override-free
so their comparison still isolates burn-profile effects. 10 new tests (279 → 289, all green); zero
`sim/` files touched. Verified independently: small motor's own lighter rocket apogees at 69.6 m (vs
18.6 m on the shared un-overridden baseline); large motor's own heavier rocket apogees at 543.9 m (vs
996.8 m on the shared baseline — its own extra mass outweighs the thrust advantage in this
configuration, a genuine trade-off result, not a bug).

**Next: Step 30 (3D rotational EOM) remains the next queued item**, still waiting on the user's review
of `docs/latex/research/3d_equations_of_motion.md`.

User request (2026-10-12): a standalone app,
separate from `sim/` ("optimizers shouldn't be built into simulation but a separate thing that uses
simulation"), that sweeps a list of motor thrust curves against one fixed rocket/launch condition,
ranks by highest apogee, and reports a fuller flight-stat bundle per motor (max/avg velocity, max
acceleration, burnout/apogee/impact time, downrange, max-Q) than `sim/report.py`'s existing
`flight_summary` gives (apogee alt/time, max-Q, impact time only). Once that works, extend it so each
motor entry can also carry its own dry-rocket parameter overrides (smaller motors → smaller/lighter
casing) — leverages `sim.params.replace`'s existing multi-dotted-path support, confirmed to need no
`sim/` change at all.

**Same request also asked to implement airbrake-as-additive-`C_dA`** (`C_dA_total = C_dA_rocket +
C_dA_airbrake`). Confirmed by the orchestrator reading `sim/forces.py`/`sim/control.py` directly: this
already exists, already committed (**Step 49**, pre-Phase-2.11) — `A_brake =
q*Cd_brake*S_max*deploy_fraction`, additive into the axial force alongside `q*S*C_x`, bit-for-bit off
by default (`airbrake_S_max=0.0`). The user's own stated next step ("later it's gonna go as one
combined C_dA") is already anticipated in `sim/control.py`'s own docstring (the Step-57
`aero_coeff_delta`/`C_x` seam). **No new work for this** — confirmed done, not re-implemented.

Architect design: `docs/architecture-29-motor-selection.md` (`architecture.md` §29 pointer);
`roadmap.md` Phase 2.12, Steps 61–62; backlog **B14/B15/B16** added. Full decision log in
`status.json`'s `phase2_12_motor_selection` block — 9 decisions total, 3 put to the user
(measurement window = ascent-only for extrema; max-acceleration meaning = inertial `|dv/dt|`; Step
62's config format = a Python literal, not JSON/CSV/YAML), 6 accepted on the architect's
recommendation without escalation (stats computed locally in the new app, not `sim/`; acceleration via
re-evaluating `sim.dynamics.derivatives` on the grid, not finite-differencing; avg velocity = trapezoid
of `|v|`; `apps/motor_selection/compare_motors.py` naming; ship `tests/test_motor_selection.py`;
synthetic 1.5 kg/75 mm demo baseline rocket, not a reuse of `run.py`'s 0.5 kg toy).

**Plan — Steps 61–62, one commit each:**
- S61 — `apps/motor_selection/compare_motors.py` (new): baseline `Params` × a list of `motor_curve`
  files, one `run_sim` per motor, ranked-by-apogee table with the ascent-window stat bundle above;
  2–3 new synthetic `data/motors/*.csv` fixtures (today there is only `placeholder.csv`);
  `tests/test_motor_selection.py` with pinned-value checks. No `sim/` file touched.
- S62 — per-motor dry-rocket override config: `list[MotorEntry]`, each `motor_curve` + an open dotted-
  path override dict, built via `sim.params.replace`'s existing multi-key support. Depends on S61
  (edits its module); not parallelizable with it.

Backlog **B17** (not fixed, out of scope): the `sim/`-level `solve_ivp` numerical-stability gap noted
above under S61.

## Phase 2.11 rewrite pass — COMPLETE (2026-10-10), Step 30 still paused, unchanged by it

**All 10 steps (S50–S60) done, each independently re-verified by the orchestrator, not taken on any
agent's self-report alone** — commits `2120ed1`/`beaf99b`/`6d14b7a`/`b1f6c2e`/`3373b06`/`8b8a343`/
`2720c82`/`00d7219`/`78a7e55`/`37f0b68`/`50e1b6f`. Full per-step log below. Headline result: the
`"constant"` aero model bug the user originally reported is fixed (it now correctly scales with
dynamic pressure); backlog **B11**/**B12** are unblocked by a new opt-in sampled-data integrator
(neither law/model is written yet); `Params` is now 12 composed groups; `run.py` is scenario
definition only. One finding surfaced, not yet acted on: the committed scenario's `C_m=0.0` gives it
no restoring moment, so it now falls tail-first with real (not placeholder) drag accelerating the
descent — see the S55 entry below for detail. **Next: Step 30 (3D rotational EOM) resumes**, exactly
where it was paused before this pass started.

User request (2026-10-10): fix bugs and rewrite `Params`/`sim/aero.py`/`run.py`/the LaTeX **before**
resuming Step 30 (3D rotational EOM review), which stays paused and untouched throughout. Architect
design: `docs/architecture-28-rewrite.md` (architecture.md §28 pointer). Approved by the user the
same day; full decision log in `status.json`'s `phase2_11_rewrite` block.

**Confirmed bug, user-identified:** `aero_model="constant"` uses raw-Newton placeholders
(`A_x`/`A_z`/`A_m`), never scaled by dynamic pressure — the only aero model that ignores the
atmosphere. Measured blast radius of fixing it: exactly 3 call sites in the whole repo use nonzero
values there (one test, `run.py`'s scenario, `apps/cfd_conditions`'s scenario); everything else is
bit-for-bit since zero coefficients produce zero force either way. A second, independent defect
found during design: `aero_model` and `aero_table` are two uncoordinated selectors for the same
thing, and `dynamics.py`'s `cop_l1` call already ignores the `aero_model` switch entirely — fixed by
making all three (`constant`/`linearized`/`table`) one coherent dispatch.

**Plan — Steps 50-60, one commit each:**
- S50-52 — `Params` → 12 composed groups (`Weight/Thrust/Lengths/Aero/Gravity/Site/Atmosphere/
  Soundings/Wind/Recovery/Control/Solver`); 3-commit migration with a transitional shim (sim/ first,
  then tests/run.py/apps/, then delete the shim). Phase 3's `dynamics3d.py`/`forces3d.py` are in
  scope for the rename (small: `p.m`/`p.m_d` → `p.weight.m`/`p.weight.m_d`) — Step 30's own content
  is not touched.
- S53 — `Solver` group; `run_sim(p, s0)` becomes the only signature, no override kwargs.
- S54 — *(architect)* LaTeX notation pass, lands before S55 so the doc doesn't contradict the code
  (same ordering lesson as Step 46's blocker).
- S55 — the aero three-way dispatch itself (`constant`/`linearized`/`table`), replacing
  `A_x`/`A_z`/`A_m` with coefficients (`C_x`/`C_z`/`C_m`) × a shared reference area `Aero.S` (not a
  new field `A` — avoids reintroducing a symbol collision with the nose-tip point/`A_x,A_z,A_m`/
  `vec(A_f)` that a prior doc pass deliberately removed). **The one deliberately non-bit-for-bit
  step** — re-pins one test's closed form, `run.py`'s printed numbers, and `apps/`'s scenario.
- S56 — collapse 3×`flow_state` per RHS call down to 1× (perf/cleanliness, bit-for-bit).
- S57 — control-coefficient seam (structure only, identity by default) — so a future
  airbrake/guidance law can perturb `C_x`/`C_z`/`C_m`/CoP directly, not just add a separate drag
  area. No controller written yet.
- S58 — `run.py` reduced to scenario definition only; summary/plot/CSV/sweep machinery moves to new
  `sim/report.py`.
- S59 — **opt-in sampled-data/zero-order-hold integration mode** — unblocks backlog **B11**
  (state-coupled turbulence) and **B12** (sampled-data PID airbrake), both previously blocked on
  `solve_ivp`'s pure-function-of-`(t,y,p)` contract. Flagged as the largest, riskiest step in the
  pass, its own commit, strictly opt-in (bit-for-bit by default).
- S60 — *(architect)* tracker/roadmap/LaTeX close-out.

**Already done (housekeeping, ahead of S50):** `apps/cfd_conditions/select_conditions.py` (never
committed — "App 2," the CFD condition selector) committed as-is (commit `c22d8b7`); the design doc
committed (commit `03918e2`); `docs/latex/*.{aux,pdf,log,...}` build artifacts added to `.gitignore`
(commit `e460b61`).

**S50 done (commit `2120ed1`), independently re-verified by the orchestrator** (not taken on the
developer's self-report alone): full suite 245/245 both before and after; `python run.py`'s
`output/trajectory.csv` byte-identical before vs after (git stash round-trip); stdout identical
except the one necessarily-changed printed `Params` repr line (flat → nested shape). `sim/forces.py`
confirmed still reading `Aero.C_x/C_z/C_m` as raw, un-scaled-by-q placeholders under
`aero.model == "constant"` — the bug fix is still S55's job, not this step's.

**S51 done (commit `beaf99b`), independently re-verified by the orchestrator, twice** (a session-limit
interruption hit mid-pass; resumed with no work lost). `tests/`/`run.py`/`apps/` fully migrated off
`Params.flat` to native nested construction and the dotted-path `replace()` helper — including bare
flat-attribute reads inside test bodies (`p.m`, `p.R_e`, `p.gravity_model`,
`d["params"].gravity_model`, etc.), a scope point the orchestrator's own dispatch had
underspecified and the developer correctly flagged rather than guessed. Verification: 245/245 both
rounds; `output/trajectory.csv` byte-identical; a from-scratch AST-based scan (not text grep)
confirms zero residual bare flat-attribute reads outside `sim/`. Two sanctioned stdout text changes
(not numbers): `run.py`'s sweep-table headers now read `gravity.model`/`atmosphere.model`.

**S52 done (commit `6d14b7a`), independently re-verified by the orchestrator.** Deleted
`Params.flat`/`_FLAT_TO_GROUP`/the ~50 flat `@property` aliases — `Params` is a plain
auto-generated-`__init__` dataclass again. Proof the S50/S51 migration was complete: zero test edits
needed, and `run.py`'s entire stdout came back byte-identical (not just `trajectory.csv`/the repr
line as at S50→S51 — this time nothing at all differs, since this step changes neither). 245/245.

**S53 done (commit `b1f6c2e`), independently re-verified by the orchestrator.** `run_sim` is now
strictly `run_sim(p, s0)` — all 67 call sites migrated (28 mechanical, 39 via `params.with_solver(p,
...)`); `test_result_params_is_p_on_both_integrator_paths` corrected to assert against the
`with_solver(...)`-built object, not the stale original `p`, exercising D-10's actual guarantee
instead of a now-meaningless one. 245/245; `run.py`'s stdout and `trajectory.csv` came back
completely byte-identical (zero diff), same as Step 52 — this step changes no physics.

**S54 done (commit `3373b06`), independently re-verified by the orchestrator, doc-only.**
`models.tex` restated around `Constant`/`Linearized`/`Table` as three equally-first-class models;
`Constant` now explicitly documented as `q`-scaled ("reads the atmosphere exactly as the other two
do"); `C_x≡C_A`/`C_z≡C_N` bridge added; `c_mq` documented as applying under all three. Two collateral
corrections flagged and made (`analysis.tex`'s `c_mq` paragraph, `main.tex`'s CFD-pipeline bullet).
Verified independently with a from-scratch label/cross-reference/brace/environment script (not just
the architect's self-report): 57 labels/0 duplicates, 186 refs/48 targets/0 dangling, clean brace and
environment balance in all 4 files. No LaTeX toolchain here — structural check only; **compile
locally before treating as final**, same standing caveat as every prior doc pass.

**S55 done (commit `8b8a343`), independently re-verified by the orchestrator — this is the actual bug
fix the user asked for.** `sim/aero.py` gains `AeroCoeffs` + a `_AERO_MODELS` dispatch dict
(`constant`/`linearized`/`table`); `"constant"` is finally `q`-scaled (`q·S·C_x` etc.) instead of
being raw, atmosphere-independent Newtons; `"linearized"` is bit-for-bit the old `"coefficients"`;
`forces.py`'s `if/elif` blocks are gone; `dynamics.py`'s F2 leak (table-driven CoP disagreeing with
constant-driven force) is closed. **Deliberately non-bit-for-bit** (2nd time in this project's
history, after Step 46): `run.py`'s scenario apogee drops from ~4.6 km to ~666.5 m, since `C_x=0.5`
now produces real drag instead of an inert 0.5 N placeholder. The developer found and correctly
re-pinned 4 more affected sites than the architect's original blast-radius estimate had counted
(`test_control.py`'s airbrake fixture among them). 247/247 verified independently; `run.py`'s printed
output matched exactly; the dispatch/bundle/closed-form re-derivation/`architecture.md` diff were all
reviewed line-by-line against spec, not taken on trust.

**Finding, flagged not hidden:** the committed scenario has `C_m=0.0` (no restoring moment), so
`theta` stays frozen nose-up through a tail-first post-apogee descent — the (alpha-independent) axial
drag now *accelerates* that fall instead of opposing it, giving a printed max speed (414.7 m/s) during
descent, not ascent. A pre-existing scenario-design simplification, only consequential now that the
drag is real. Explicitly out of S55's scope to fix (would mean changing the scenario's own physics) —
worth the user's attention separately from this rewrite.

**S56 done (commit `2720c82`), independently re-verified by the orchestrator.** `dynamics.derivatives`
now computes `flow_state` once per RHS call and threads it into `aero_force_body`/`aero_moment_y`
(both gain a required `flow` parameter); `forces3d.py`'s 2D-compat adapter updated to match
(mechanical only, no new 3D physics). Strictly bit-for-bit: `flow_state` confirmed genuinely pure
(Dryden turbulence's RNG draw is cached per seed, consumed once for the process's lifetime).
~44% faster per RHS evaluation measured (83.55µs→47.01µs); the full suite itself ran ~198s vs ~320s
for the same 247 tests as a side effect. `trajectory.csv`/stdout byte-identical (zero diff).

**S57 done (commit `00d7219`), independently re-verified by the orchestrator.** `sim/control.py` gains
`_AERO_COEFF_CONTROLLERS`/`aero_coeff_delta`; `sim/aero.py`'s `coefficients()` calls through as the
single choke point (forces, moment, damping, and `dynamics.py`'s CoP arm all see one consistent,
controlled coefficient set — the exact F2-leak shape Step 55 just closed stays closed). Only `"none"`
(identity) is registered — no controller written. Circular import resolved via this codebase's own
existing precedent (deferred import, same shape as `flow.py`/`forces.py`'s `sim.wind` cycle). Two new
tests prove the default is genuinely `is`-identity and that a delta reaches all four consumers via
closed-form checks. 249/249; `trajectory.csv`/stdout byte-identical (zero diff).

**S58 done (commit `78a7e55`), independently re-verified by the orchestrator.** `run.py` is now
scenario-definition only; `sim/report.py` holds everything else (`flight_summary`/`sweep`/
`print_sweep_table`/`print_run_summary`/`save_run_artifacts`/`save_sweep_artifacts` + a `run_sweep`
convenience wrapper). `plt.show()` dropped (a known hang risk since Step 45). Step 55's deliberate
`aero.model="linearized"` atmosphere-sweep override preserved with its reasoning intact, despite the
architecture doc's own illustrative snippet suggesting otherwise. 249/249; `trajectory.csv`
byte-identical; stdout differs only by the now-absent `plt.show()` warning lines.

**S59 done (commit `37f0b68`), independently re-verified by the orchestrator with extra scrutiny
given its flagged risk level — the largest step in the pass.** `_run_rk4` refactored (not copied) to
support an opt-in zero-order-hold mode: a `Hold` (new `sim/sampling.py`) is recomputed once per
fixed-rate tick and held constant across all 4 RK4 stages of every substep inside that tick, keeping
the RHS smooth within a tick. Gated by `p.solver.sample_rate_hz > 0.0` + requires `p.solver.method ==
"rk4"` (raises otherwise); non-integer `T_s/dt` raises rather than silently rounding. `hold=None`
threaded through the full RHS chain — every pre-Step-59 call site unaffected. No controller, no
turbulence model written — just the capability B11/B12 were both blocked on. 11 new tests, including
one proving `prev` is threaded exactly once per tick (not per substep/stage) — the single most
load-bearing assertion in the step. Measured ~74× slower than RK45 (almost entirely inherent to
fixed-step RK4, not the ZOH machinery itself, measured at ~1% overhead). 260/260; default
(`sample_rate_hz=0.0`) confirmed bit-for-bit via git-stash round-trip; core driver logic, `sim/
sampling.py`, and the hold-consumption code all read and checked directly against spec line-by-line.

**S60 done, doc/tracker-only, the final step of the pass.** Four deliverables: (1) Phase 2.11
recorded in `roadmap.md` as a full phase section (Steps 50-60, each with Files/Spec/Do/Check/Commit
in this file's established shape), plus the Summary, dependency-diagram and dependency-prose entries
the other phases have; (2) `PROJECT-STATUS.md`'s Step-27 "Actual printed sweep tables" record
**re-pinned** against a real headless `python run.py` in this tree, with the four separate reasons it
had drifted enumerated — items 1-2 pre-existing (the `linear` row removed at Step 34; the
unattributed Steps-28-44 `max_q`/`impact_t` drift found during Step 45's verification), items 3-4
this pass's own and intended (Step 55's real drag, Step 58's header rename). The re-pin resolves the
*record*; it does **not** explain the Steps-28-44 drift, which still has no cause and would need its
own look — stated plainly rather than claimed as a fix; (3) backlog **B11** and **B12** moved from
*blocked on a different integration strategy* to *unblocked by Step 59, model/law not written*, with
the remaining work named in each case (the Dryden filter and its state for B11; the PID's signal,
gains and anti-windup for B12) — **no law and no turbulence model written**, per the step's scope;
(4) `architecture-28-rewrite.md` §28.10 items **8-9** applied to `main.tex` — the two sentences
deliberately deferred at Step 54 because neither could be written truthfully until Step 59 existed.
A third site carrying the same now-false "needs a different integration strategy" claim (the
commanded-gimbal backlog bullet) was found and corrected as flagged collateral, the same way Step 54
handled its two. Checked structurally only (labels/`\autoref` targets/brace and environment
balance) — **no LaTeX toolchain here, compile locally before treating as final**. No `sim/`,
`tests/`, `run.py`, `apps/` or `status.json` touched; Step 30 and
`docs/latex/research/3d_equations_of_motion.md` untouched, as throughout the pass.

**Phase 2.11 is complete: all ten steps of `architecture-28-rewrite.md` §28.11 (S50-S60) are done,
each committed individually and each independently re-verified by the orchestrator rather than
accepted on the implementer's self-report.** The user-identified bug is fixed (S55), the second
defect found while designing the fix is fixed with it (the `aero_model`/`aero_table` double selector
and `dynamics.py`'s `cop_l1` leak), and B11/B12 are unblocked without either law being written.
Test count 245 → 260 across the pass; exactly one step (55) deliberately not bit-for-bit, every other
step proved bit-for-bit by execution.

**Next:** Step 30 resumes exactly where it was paused — waiting on the user's review of
`docs/latex/research/3d_equations_of_motion.md`. Nothing in this pass changed that, and nothing in
this pass touched it.

## Current stage
**Phase 2 COMPLETE** (all 19 mandatory steps, see below). **Phase 2.5 (Steps 33-37) COMPLETE**,
**Phase 2.6 (Steps 38-40) COMPLETE**, **Phase 2.7 (Steps 41-44) COMPLETE**, **Phase 2.8 (Step 45)
COMPLETE**, **Phase 2.9 (Step 46) COMPLETE**, **Phase 2.10 (Steps 47-49) COMPLETE** — 2D is now
feature-complete against the backlog (everything left needs new data, new theory, or a 3D degree of
freedom) — and **Phase 2.11 (Steps 50-60) COMPLETE** (2026-10-10, the rewrite pass: see the section
above). **Phase 3 (3D, full 6-DOF) STARTED 2026-10-04**: Step 28 (quaternion algebra, commit
`26cbf1b`) and Step 29 (3D state + translational dynamics, commit `2d9acb5`) are done and
independently verified. **Step 30 (3D rotational dynamics) is blocked**, waiting on the user's review
of `docs/latex/research/3d_equations_of_motion.md` — a proposed inertia-tensor/Euler's-equations
extension to `main.tex`, drafted by the orchestrator rather than invented unilaterally, since
`main.tex` has no 3D content at all yet. 260/260 tests passing (245 before Phase 2.11; the pass added
15). Backlog items B1, B2, B4, B5 and B8
are done (promoted at earlier
phases); remaining backlog: B3 gridded EGM gravity, B6 crosswind (parked for Phase 3, now with a
second item waiting on it — Step 46's Dryden cross-wind `v`), B7 vertical wind (parked; Step 46
narrowed but did not close the gap — the verified `Φ_w` turbulence formula exists, the mean
updraft/downdraft question does not), B9 a real `c_mq` value (researched 2026-09-28 — user chose to
keep the Step 44 test fixture rather than adopt OpenRocket's method), B10 turbulence on wind tiers 2/3
and B11 state-coupled turbulence (both opened by Step 46), B12 sampled-data/PID control (opened by
Step 49 — the airbrake controller is a pure, memoryless proportional law for the same
solver-determinism reason B11 exists; **B11 and B12 are both now unblocked by Phase 2.11's Step 59**,
which ships the opt-in zero-order-hold integration mode they were both blocked on — but neither the
turbulence model nor the PID law is written, so both items stay open with the *model/law* as the
remaining work rather than the solver), B13 ISA-extrapolation robustness (a benign but real gap found,
not introduced, during Step 48's verification — see roadmap.md). Also outstanding, as the user's own
follow-up, not blocking anything: `latex/sections-ai/models.tex` §Wind > Analytic still documents the
pre-Step-46 placeholder gust formula. B13 (ISA extrapolation robustness, found during Step 48's
verification) and B12 (sampled-data/PID control, opened by Step 49) are also open, B13 already fixed
same day (commit `657ff36`). Phase 3 is scoped per the user's own instruction to
simulation/optimization/guidance only — CFD stays 2D-only; the Step 49 airbrake controller is this
project's one 2D control loop, direction/guidance control is Phase 3's to build, once it has an
out-of-plane DOF. Next: the user's review of the Step 30 EOM proposal. See "Phase 3 progress" and
"Phase 2.10 milestone: COMPLETE" below. Steps 33-35:
- Step 33 — doc restructuring: `main.tex` split into `latex/main.tex` +
  `latex/sections/{rocket-2d,models}.tex`; added the `§Current assumptions` section; filled
  previously-empty stubs; AI-authored text marked with `\ai{}`. No code changes. Commit `3aaec51`.
- Step 34 — removed the `linear` gravity model (dominated by `radial`, no advantage; went negative
  above `h=R_e/2`). `gravity_model="linear"` now raises `KeyError`. Commit `6d48576`.
- Step 35 — aero force now resolved in **body axis**, not wind axis (was double-applying the
  relative-wind rotation; the two conventions only agreed at α=0). Also fixed, in the same commit,
  an unbounded-α hang in `sim/aero.py`'s constant-fallback `C_N`/`C_m` (linear `C_N_alpha*alpha`
  → `C_N_alpha*sin(alpha)`, since an unperturbed vertical flight can coast tail-first through
  `V=0` at apogee and land exactly on `atan2`'s branch cut). Commit `6fa46f2`.

Step 36 — variable mass: CoG/moment-of-inertia travel. `m` is now the 7th integrated state
component (`dm/dt = -T_ref(t)/(I_sp·g0)`). `l_B(t)`/`I(t)` (parallel-axis, two-lumped-mass model)
recomputed every RHS call from `m(t)` and new `Params` constants `m_d,l_d,l_p,I_d,I_sp`. Gated by
`p.m_d` (`None` = off, default) — every existing scenario reproduces prior behavior exactly.
116/116 tests passing. Commit `2610cd8`. **Two open modeling questions flagged for review**
(developer made the conservative, spec-literal choice for both rather than guess, per this
project's history with Step 15/25):
1. Should `p.l1`/`p.l2` (CoP-to-CoG / CoP-to-thrust moment arms) also travel with `l_B(t)`?
   `main.tex` only gives formulas for `l_B(t)`/`I(t)`, nothing for the attachment points, and its
   own §Current assumptions still lists `l1,l2` as fixed — left fixed for now.
2. `I_p(t)` (propellant's own moment of inertia) needs a proportionality constant not given by
   Step 36's 4 new constants — implemented as `(I_d/m_d)*m_p(t)` (same specific MOI as the dry
   structure), documented as a placeholder matching `main.tex`'s own "uniform density, fixed
   shape" `\todo`.

Step 37 — non-inertial (Coriolis/centrifugal) correction. `sim/rotation.py` (new):
`omega_components(lat0_deg, azimuth_deg)` — Earth's Ω decomposed in the launch tangent-plane frame
per the architect's derivation (`latex/sections/models.tex`, commit `a98f283`, verified to 4.4e-16
against an independent 3D calculation). Key finding: in-plane Coriolis is driven entirely by Ω's
out-of-plane component, so a due-North/South launch (or the poles) gets exactly zero in-plane
Coriolis even though the true effect is maximal there (just lateral, which a 2D model can't
represent) — documented as an explicit closure, same precedent as the existing crosswind closure
in §Wind. Implemented per user-approved **scope Option B**: in-plane Coriolis added to
`sim/dynamics.py`'s translational derivatives, gated by new `Params.earth_rotation` (bool, default
`False`, bit-for-bit inert) — *plus* the discarded lateral component computed and exposed as a
labeled diagnostic (not fed into the physics), so the blind spot is visible instead of silent. The
residual centrifugal term (Option D) was deliberately **not** implemented, per the user's explicit
choice — documented as a closed decision, not a gap. 123/123 tests passing (7 new). Commit
`9af29c7`.

Verified: `earth_rotation=False` is bit-for-bit inert regardless of `lat0_deg`/`azimuth_deg`;
in-plane Coriolis matches the closed form independently re-derived in the test (~2.81×10⁻² m/s² at
`lat0=50°, azimuth=90°, V=300 m/s`, matching the architect's ~2.8×10⁻² report); the existing
~4.6 km-apogee scenario deflects ~8.4 m downrange at apogee with Coriolis on at that geometry,
matching `models.tex`'s own order-of-magnitude estimate ("order 10 m over a 30 s powered ascent");
the in-plane term is exactly zero at `azimuth=0°/180°` for every latitude tested, with the lateral
diagnostic nonzero there instead — the documented blind spot, and the exact property the
diagnostic exists to demonstrate.

**Process note:** the developer caught and correctly resolved a contradiction in the orchestrator's
own dispatch instructions for this step (the detailed scope description said the lateral
diagnostic must be nonzero at `azimuth=0°/180°`; a later "Checks" bullet, copied loosely from
`roadmap.md`'s older wording, said the opposite). Resolved by re-deriving from `models.tex` itself
— the authoritative source — rather than taking either instruction on faith, and verified
numerically. No harm done, but a reminder to double-check dispatch prompts for internal
consistency, not just against the spec.

## Report finalization pass (2026-09-27, not a numbered roadmap step)

Documentation-only pass over `latex/main.tex` + `sections/{rocket-2d,models}.tex` after Phase 2.5
closed, at the user's request. No code changes; nothing under `sim/` or `tests/` touched. Done by
the architect in two runs (a rate-limit interruption in between; no partial edits were lost — the
tree was clean before the retry).

**Two real bugs found and fixed in `rocket-2d.tex` §Analytical analysis** (both pre-existing user
text, both independently re-derived and cross-checked against the running code before being
touched — same discipline as Steps 15/25/37):
1. **θ sign convention.** The force equations assumed θ measured from the vertical
   (`-mg cosθ`/`mg sinθ`), contradicting §Frames' stated — and code-matching — convention of θ
   measured from the horizontal. Corrected to `-mg sinθ`/`mg cosθ`, verified against
   `sim/frames.py`'s `R_body_to_inertial`. No code change needed; `sim/dynamics.py` already
   implements the correct form.
2. **C/D point-label swap in the moment equation.** Had the thrust point `C` and the aerodynamic
   reference point `D` interchanged between the two terms (`(u_B-u_D)T ... + (l_B-l_C)A_z` instead
   of `(u_B-u_C)T ... + (l_B-l_D)A_z`). Verified against `sim/dynamics.py`'s actual cross-product
   terms numerically. Independent of bug 1 (moments are taken about the CoG, weight doesn't
   appear). The user's own pre-existing todo — "write that `l_C` is irrelevant" — only holds under
   the corrected form, which is corroborating evidence this was a transcription slip. Propagates
   mechanically into the static-stability derivative and the SM formula (`l_B-l_C` → `l_B-l_D`),
   same structure otherwise.

**Structural changes:**
- `models.tex` subsections reordered so every model's inputs precede its use (Atmosphere → Wind →
  Relative wind/AoA → Gravity → Non-inertial corrections → Thrust → Mass/MOI → Aerodynamics),
  fixing 4 forward-references.
- New **§Backlog and future work** (end of `main.tex`): thrust-axis misalignment/control,
  wing-body aero/analytic CoP/airframe/air brake, dimensionless stability margin, dynamic
  stability analysis — each as "what it is / waiting on what" — plus an index pointing at
  deferrals already stated elsewhere (grain geometry, moist air, vertical wind, aero-coefficient
  CFD expansion — all left untouched, verified byte-identical to `HEAD`).
- §Current assumptions rewritten — it was stale after Steps 36/37 (still claimed constant
  mass/CoG/I and zero Earth-rotation term).
- Three follow-up decisions the user chose from a comparison table:
  1. **Symbol collision** (reference area/length written `A,l` in one place, `S,d_ref` in
     another): renamed to `S`/`d_ref` throughout §Analytical analysis to match `models.tex`/the
     simulator. Exposed and fixed two related gaps along the way — `A_m`'s magnitude equation was
     missing from `models.tex` despite the code computing it (added), and the Reynolds number's
     `l_ref` was a redundant second reference length (renamed to `d_ref`).
  2. **Point-label mismatch** (report's A/B/C/D vs. code's `l1`/`l2`): documented the bridge only
     (`l_1 = l_D - l_B`, `SM = -l_1`); no code rename. Left as a future roadmap step if ever wanted.
  3. **Cross-references**: every section/subsection across all three files is now labelled, and
     all ~90 textual "§ Name > Subname" references converted to `\autoref`.

**Not verified:** no LaTeX toolchain is available in this environment, so nothing was compiled —
only checked statically (brace/environment balance, every `\autoref` target defined, zero leftover
textual `\S Capital` references). **Compile locally (two passes) and do a visual read-through
before treating this as final.**

Also surfaced by the architect, not fixed (genuinely out of scope for Step 37): `rocket-2d.tex`
§Analytical analysis's force equations assume θ measured from the vertical, conflicting with
§Frames and the actual code (θ measured from horizontal, nose-up) — a pre-existing inconsistency
in the user's own older text. Flagged for a small dedicated fix step later, not urgent.

**Phase 2.5 milestone: COMPLETE.** All 5 steps (33-37) done and committed individually. Phase 3
(3D, full 6-DOF) has not been started.

## Phase 3 progress (started 2026-10-04)

Scope per the user: simulation/optimization/guidance only — CFD and the Step 49 airbrake controller
stay 2D-only.

- **Step 28 — Quaternion algebra** (commit `26cbf1b`). New `sim/quaternion.py`, pure algebra, no
  `Params`/`State` dependency: scalar-first Hamilton-product quaternions, `multiply`/`conjugate`/
  `normalise`/`rotate_vector`/`to_dcm`/`from_euler`/`to_euler` (3-2-1 yaw-pitch-roll)/`q_dot`. The
  orchestrator independently hand-derived that `to_dcm`'s pitch-only reduction matches
  `sim/frames.py`'s `R_body_to_inertial(theta)` exactly — the load-bearing check — rather than
  trusting the subagent's own claim.
- **Step 29 — 3D state and translational dynamics** (commit `2d9acb5`). New `sim/state3d.py`
  (13-component `[r,v,q,omega]` state), `sim/forces3d.py`, `sim/dynamics3d.py` — additive only, no
  2D file touched. Attitude held fully constant (`dq/dt=0`, `domega/dt=0` identically) for this step,
  mirroring Phase 1's own Step-4 precedent (translation-only staging before real rotation is added at
  Step 30). The one real design decision: `forces3d.py` builds a disposable 2D-compatible state view
  per call and calls the existing 2D force functions verbatim rather than duplicating their formulas.
  This agent session was interrupted once by an API session-limit error mid-task; resumed from its
  own saved progress with no work lost. The orchestrator independently re-verified with matched tight
  solver tolerances on both sides (not the agent's own slightly mismatched comparison): the 3D
  translation matches the 2D trajectory to ~4e-7 and out-of-plane drift is exactly `0.0`.
- **Step 30 — 3D rotational dynamics — BLOCKED.** Needs an inertia-tensor/Euler's-equations
  extension to `main.tex`, which has no 3D content at all. Per the user's choice, the orchestrator
  drafted a proposal rather than inventing the physics unilaterally:
  `docs/latex/research/3d_equations_of_motion.md` — quaternion kinematics (done at Step 28), the
  axisymmetric-inertia-tensor simplification (already implicit in the existing 2D mass model, not a
  new assumption), Euler's equations for that case reducing exactly to today's 2D scalar equation at
  zero roll rate, and the one genuinely new required input (axial moment of inertia $I_a$, no default
  possible) left as an open fork for the user. **Waiting on the user's review before Step 30
  proceeds.**

**Verification:** every step's full diff independently reviewed against its spec before being
accepted; full pytest suite independently re-run by the orchestrator after each step (243/243, then
245/245).

## Phase 2.10 milestone: COMPLETE (2026-10-04) — Steps 47-49 implemented and committed

User request, designed directly by the orchestrator rather than the architect agent (explicit
instruction: "design the rail and parachute dynamics on your own"), with a control-engineering
addition folded in before implementation began ("add a somehow way to do control engineering...
feedback rn is going to be airbrake but also create base for direction control (guided)... control
engineering can go in 3D"). Full design: `architecture.md` §27.

- **Step 47 — Launch rail constraint** (commit `372115a`, promotes backlog B1). A kinematic
  constraint, not a new force: while `on_rail(y,p)`, the already-computed acceleration is projected
  onto a fixed rail-direction unit vector and `theta`/`omega` are frozen, instead of the unconstrained
  equations. `L_rail = 0.0` (default) is the off switch, bit-for-bit every prior step. Non-terminal
  `rail_exit` event, both integration paths.
- **Step 48 — Recovery / parachute** (commit `8529c72`, promotes backlog B2). Reuses Step 47's
  "freeze theta/omega" mechanism, but the chute drag is a full vector computed directly in the
  inertial frame (not routed through body axes — a round canopy's drag doesn't depend on attitude).
  `parachute_model = "none"` (default) and `parachute_S = 0.0` are two independent off switches.
  Descent speed verified live to converge within 0.4% of the analytic terminal velocity.
- **Step 49 — Control-engineering scaffold: feedback airbrake** (commit `05821ad`). New
  `sim/control.py`: a dict-dispatch pattern for pure, memoryless feedback controllers (the
  determinism constraint — no per-call memory, no sampled-data loop, without a different integration
  strategy — opens backlog **B12**). One controller: a proportional law on predicted apogee driving
  an airbrake's deploy fraction. This dispatch shape *is* the "base for direction control" asked for
  — no unused guidance stub was written, since direction/guidance control is explicitly Phase 3's job
  per the user's own scope split.

**Verification:** each step's full diff independently reviewed against its `architecture.md` §27
subsection before being accepted; the full pytest suite independently re-run by the orchestrator after
every step (224/224, then 229/229, then 235/235); a live, independent script (not just the subagents'
own tests) reproduced every headline physical claim directly from the running code (rail exit
speed/attitude, parachute terminal velocity, airbrake apogee reduction and saturation).

**Finding, recorded not hidden:** Step 48's verification surfaced a latent (pre-existing, not
introduced) robustness gap in `sim/atmosphere.py` — an unbounded ISA extrapolation that `solve_ivp`'s
adaptive-step error estimator can occasionally probe at a discontinuous force onset, producing a
`RuntimeWarning` on a rejected trial step that never reaches the accepted solution. Confirmed benign
(full suite passes normally; fails only when the warning is artificially promoted to a hard error).
Opened as backlog **B13** rather than silently fixed out of scope or ignored.

**Next:** Phase 3 (3D, full 6-DOF), scoped per the user's own instruction to simulation/optimization/
guidance only — CFD and the Step 49 airbrake controller stay 2D-only.

## Phase 2.9 milestone: COMPLETE (2026-10-02) — Step 46 implemented and committed

User request: "add wind gusts and turbulence power models." Turned out to be closing a real
spec-vs-implementation gap rather than greenfield work — `architecture.md` §16 had promised "amplitudes
from a von Kármán/Dryden-like spectrum" since Step 21, but the implementation shipped was a half-normal
random weighting with no spectral shape and no altitude dependence, never actually that.

- **Step 46 — Dryden turbulence spectrum for tier-1 wind gusts** (spec `3193802`, implementation
  `34e1127`). Replaces `sim/wind.py`'s `_gust_realization`/`_gust` with the real MIL-F-8785C /
  MIL-HDBK-1797 Dryden model: altitude-dependent scale length `L_u` and intensity `σ_u` (AGL, via the
  existing `gravity.altitude_agl`), amplitudes drawn from the published PSD and renormalized to an
  exact `Σw² == 2` variance identity (correcting a real Step-21 bug along the way — its own
  normalization was off by `√2`), and **two** horizontal components (`u` along-wind, `v` cross-wind)
  composed as a *vector* perturbation of the mean wind instead of one scalar added to its speed (which
  also removes the old non-negativity clamp — with a vector perturbation, a negative along-component
  is the correct physics of a gust reversing the local flow, not a bug to guard against).
  `Params.gust_sigma`/`gust_seed` removed; `turbulence_model` ("none"|"dryden"),
  `turbulence_sigma_high_ms`, `turbulence_ref_speed_ms`, `turbulence_seed` added. Default
  (`turbulence_model="none"`) reproduces every prior result bit-for-bit — the only step since 38 that
  is deliberately **not** bit-for-bit for every configuration (a run with the old gusts on changes,
  by design, since nothing in the repo pinned a value from that placeholder scheme).

- **Formulas verified against two primary sources, read directly rather than reconstructed.** A
  research pass (`latex/research/dryden_turbulence_model.md`) fetched and visually read a NASA Langley
  conference paper (Madden, NTRS 20190000875, the Dryden PSD equations) and a UAV-wind-modeling
  dissertation chapter (Cole & Wickenheiser, arXiv:1905.09954, the MIL-F-8785C low-altitude
  scale-length/intensity table) as rendered pages. This caught a real transcription hazard before it
  reached the spec: an initial tool-summarized reading of a different source had misread the
  scale-length formula as a product (`h·(0.177+0.000823h)^1.2`) instead of a quotient; both primary
  sources, read directly, confirmed it is a quotient. Same verify-before-trust standard as the B9
  `c_mq` research pass.

- **Four design forks, resolved by the user before speccing:** (1) spectrum choice — Dryden, not von
  Kármán (its `^(5/6)` PSD would need its own verification pass); (2) altitude dependence — real
  MIL-spec formulas, not a flat constant; (3) the Taylor frozen-turbulence reference airspeed `V` (the
  rocket's true airspeed spans 0 to supersonic, incompatible with the solver-determinism constraint
  that forbids any RHS dependence on it) — a **fixed** `turbulence_ref_speed_ms`, documented as a known
  simplification whose damage is precisely bounded: after renormalization `V` and `L` enter the model
  only through the ratio `L/V`, so `V` affects *only* the spectrum's break frequency, never the
  delivered intensity; (4) the isotropic intensity above 2000 ft AGL (MIL-spec gives only a chart, no
  formula) — a user-set `Params` field, not a hardcoded light/moderate/severe preset.

- **A genuine blocker, surfaced rather than silently resolved.** The architect found
  `latex/sections-ai/models.tex` §Wind > Analytic still documents the Step-21 placeholder verbatim,
  contradicting the new spec in three places (the scalar perturbation, the non-negativity clamp, the
  off-switch). Working rule 1 makes the LaTeX the source of truth and it is the user's own document, so
  implementation was blocked until the user chose: nominate the research note + `architecture.md` §26
  as the interim physics reference, with `models.tex` to be brought in line later by the user's own
  edit — not a developer's. `models.tex` itself remains unedited; that is still outstanding as the
  user's follow-up, not part of this step.

- **Verification, independent of the implementing agent's self-report** (this project's standing
  practice, repeated here): full suite re-run by the orchestrator directly — 220/220 passed. Every
  pinned number in `architecture.md` §26.11 (the 9-row altitude scale-length/intensity table including
  three exact boundary values, the frequency-grid constants, the headline `(u,v,w_x,w_y)` state at
  `t=3.7s`, the 3-seed sensitivity table, the exact `Σw²/2 == 1` invariants) reproduced by running the
  live code directly against the spec's table — matched to the last digit, nothing needed reconciling.
  `run.py` re-run and confirmed numerically unchanged (the committed scenario uses `wind_model="none"`,
  structurally unaffected — only the printed `Params` repr differs, showing the renamed fields).
  Turbulence-on cost measured at ~2.2× solver steps (the spec's own worst-case estimate was ~10×, gated
  at "stop and report if worse than ~30×") — no constant tuning needed.

- **Named, bounded uncertainty, not swept under the rug:** the `L_v` factor-of-two convention. Some
  editions/renderings of MIL-F-8785C write the lateral/vertical PSDs in terms of `2L_v`/`2L_w`; the
  research note's `L_u = L_v` pairing is self-consistent with the PSD form it transcribed (both
  integrate to `σ²` exactly either way — normalization alone cannot discriminate between the two
  conventions), but only the spectrum's break frequency can tell them apart. A pinned break-frequency
  test exists specifically so a future correction (one line: `L_v = L_u/2`, `σ_v` unaffected) would be
  a loud test failure, not a silent drift.

- **Two backlog items opened:** **B10** (turbulence on the measured wind tiers 2/3 — needs `W20` and
  an AGL altitude a measured sounding doesn't carry, plus a double-counting question against the
  sounding's own resolved shear) and **B11** (state-coupled turbulence using true instantaneous
  airspeed instead of a fixed reference — the "gold standard," incompatible with the solver-determinism
  constraint without a fundamentally different integration strategy).

## Phase 2.8 milestone: COMPLETE (2026-09-28) — Step 45 implemented and committed

Promotes Backlog **B8** — the half of `models.tex` eq. `h_true` that Step 42 (Phase 2.7) deliberately
left behind — in full, and one item beyond it by explicit user instruction.

- **Step 45 — curved altitude everywhere** (spec `7390f73`, implementation `355a170`).
  `altitude_agl`/`altitude_msl` move from `sim/flow.py` to `sim/gravity.py`
  (`altitude_agl(y, p) = -ground_depth(0.0, y, p)`, one unary minus, no re-typed trigonometry — the
  altitude models read and the surface the impact event finds can never disagree) and become
  curvature-aware, replacing every flat `-y[Z]`-style altitude computation in the package:
  `gravity.py`'s `_g_radial`/`_g_wgs84`; `atmosphere.py`'s **three** independently inlined `h_msl`
  copies (`_isa_air_state`/`_sounding_air_state`/`_field_air_state`); `wind.py`'s tier-1/2/3 (three
  copies — tiers 2/3 change because wind and atmosphere read the *same* sounding file at the *same*
  level, and curving only one would sample two different rows of one profile for one state).
  `sim/soundings.py` needed no change, confirmed by inspection rather than assumed.

  **The reported/plotted altitude is in scope too, by explicit user override.** The architect's
  original spec recommended leaving `run.py`'s printed apogee altitude and `sim/plotting.py`'s three
  plotted altitude series at flat `-z`, as Step 42 had — the user overrode this: *"I want convention
  to be radial. I want stuff to be physically correct."* The spec was expanded mid-flight to cover
  it: `integrate.Result` gains a fifth field, `params` (the `Params` that produced the run — chosen
  over a `p` argument on the plotting functions because `plot_trajectory_overlay` takes one `Params`
  per variant in a sweep, so a single `p` parameter would be wrong in general); `run.py`'s **two**
  independent apogee-altitude readouts (`_flight_summary`, used by `sweep()`, and `main()`, which
  does not call `_flight_summary`) both convert; `plotting.py`'s three `altitude = -y[Z]` sites
  become `altitude_agl(y, r.params)`. The event **triggers** are explicitly untouched —
  `_apogee_event` still fires at `y[VZ] == 0` in the launch frame; only the altitude *value* reported
  at that instant changes. A documented consequence, not a defect: on a curved run the reported
  altitude at `t_apogee` is *not* the maximum of the curved altitude over the flight
  (`dh_true/dt = +0.47 m/s` at the apogee of a representative tilted trajectory) — redefining apogee
  as `max h_true` is explicitly a separate, un-taken decision.

  **The orthogonality consequence is named, not smuggled in.** Curvature lives only in
  `gravity.curvature_radius(p)`, keyed off `p.gravity_direction` — so `_g_radial`/`_g_wgs84`'s
  altitude input now depends on the *direction* model, meaning `gravity_direction="elliptical"`
  moves the gravity *magnitude* even with `gravity_model` unchanged. This does not collapse the
  Step-38 dispatch (the two dicts stay separate, `g()` still dispatches purely on `gravity_model`) —
  it is a shared *input*, not a shared *dispatch* — and it is asserted by a dedicated test so a
  future reader cannot silently "restore orthogonality." `p.R_e` (the geocentric falloff radius) and
  `curvature_radius(p)` (a radius of curvature) remain two different quantities, never substituted
  for one another — for `"elliptical"` they differ by ~20 km.

  Bit-for-bit under the default `gravity_direction="parallel"` was confirmed by **execution, not
  just by reading the diff**: `git stash` on Step 45's changes, re-run `run.py` against the exact
  pre-Step-45 code, and diff its printed output against the post-Step-45 run — byte-for-byte
  identical. 220/220 tests passing (33 new), including a tilted (`x≠0` throughout)
  every-altitude-consumer-exercising regression pinned against pre-Step-45 values on both integrator
  paths, since the vertical default (`x≡0`) can't distinguish a converted from an unconverted call
  site. Exactly one test-file reorganization occurred (the permitted one): `test_flow.py`'s two
  altitude tests moved to `test_gravity.py`, gaining the `p` argument their new import requires.

  **A separate, pre-existing finding surfaced during the bit-for-bit check, recorded rather than
  fixed here:** `run.py`'s printed sweep tables no longer match `PROJECT-STATUS.md`'s Step-27
  "Actual printed sweep tables" record — `apogee_alt`/`apogee_t` still agree closely, but `max_q`
  and `impact_t` have drifted by several percent in both sweeps. Confirmed unrelated to Step 45 by
  the same stash-and-diff method (the drift is present identically in the pre-Step-45 code), so it
  was introduced somewhere across Steps 28-44 and never re-verified against the Step-27 record since
  — that record was already known to be partly stale (it still lists the `linear` gravity model,
  removed at Step 34). Not investigated further, per the architect's own instruction not to absorb
  it into this step's commit; flagged in `roadmap.md`'s Step 45 entry for a future dedicated look.

**Recovery note:** the developer session implementing Step 45 was terminated by a session-limit API
error after getting the full suite to 220/220, but before its planned final `run.py` verification and
before any commit. The orchestrator recovered directly: reviewed the entire diff against the spec
file-by-file (every file matched the spec's call-site tables exactly, no improvisation found),
re-ran the full suite independently (220/220, unchanged), then hit a second, unrelated snag while
running the `run.py` verification itself — two background invocations both silently hung after
writing their output files, traced to `run.py`'s trailing `plt.show()` blocking on a GUI backend in
this headless session (the files were already correct; only the printed stdout was lost to the
hang). Resolved by killing the stuck processes and re-running with `MPLBACKEND=Agg`, which also
enabled the stash-and-diff bit-for-bit proof described above.

**Verification:** every commit's full suite independently re-run by the orchestrator, not taken on
the developer session's self-report alone. Final count: 220/220.

**B9 research note (2026-09-28, no code change):** separately from Step 45, the pitch-damping
coefficient `c_mq` (Step 44's scaffold, still `0.0` default) was researched against Nielsen's
*Missile Aerodynamics*, Barrowman's 1966 thesis, the classical Munk/Bryson slender-body closed form,
and OpenRocket/Niskanen's strip-theory method — the last verified directly against its GitHub source
rather than trusted from memory, and found to need fin/body planform geometry this project doesn't
track, plus an explicit `×3` calibration factor and a hard cap at the static moment ("higher damping
yields much more realistic apogee turn" — its own source comment). Presented to the user with these
findings; decision: keep the Step 44 test fixture, no `Params`/code change. Write-up:
`latex/research/c_mq_pitch_damping.md`; tracker entry: `roadmap.md`'s B9.

## Phase 2.7 milestone: COMPLETE (2026-09-28) — Steps 41, 42, 43, 44 implemented and committed

Physics rewrite of the same session (`latex/main.tex` + `latex/sections-ai/{rocket-2d,models,
analysis}.tex`, renamed from `latex/sections/`) introduced four pieces of physics not yet in
code; all four are now implemented, tested, and committed, one step at a time as usual.

- **Step 41 — elliptical gravity direction** (commit `f5d0120`). `gravity_direction="elliptical"`:
  the WGS84 ellipsoid normal, approximated near the launch point by its osculating sphere in the
  flight-plane azimuth `χ` (Euler/Meusnier radius of curvature `R_χ(φ₀,χ)`). Reuses the existing
  `lat0_deg`/`azimuth_deg` fields — no new `Params`. "radial" and "elliptical" now share one
  `_dir_curved` body via a new `curvature_radius(p)` seam; "radial" evaluates the exact same
  expression on the same operands as before (bit-for-bit). 162/162 tests (12 new).
- **Step 42 — curved-ground impact condition** (commit `bdc7e07`). New `gravity.ground_depth(t,y,p)`
  reuses Step 41's `curvature_radius` seam and replaces the literal `y[Z]` read in both the RK45
  ground event and the RK4 integrator's manual crossing detection. Scoped to the impact/apogee
  event only, per the user's explicit choice (atmosphere/wind/gravity-magnitude altitude lookups
  deliberately still read `h=-z`; the full swap is Backlog B8). Two traps handled explicitly: the
  curved formula does **not** algebraically degenerate to `-z` for `"parallel"` at finite `R_e`
  (only as `R→∞`), so there's a real `R is None` branch, not a hopeful limit; and `ground_depth` is
  built DOWN-positive to match `y[Z]`'s own sign convention, since a naive `h_true` substitution
  (up-positive) would have made the solver hunt for the wrong crossing and never terminate.
  168/168 tests (7 new).
- **Step 43 — lateral offsets `u_B`, `u_C`** (commit `ad359eb`). New `Params.u_B`/`u_C` (both
  `0.0` default). The CoG-to-aero-point and CoG-to-thrust-point displacement vectors in
  `sim/dynamics.py` gain a lateral component each; the two new moment terms from `analysis.tex`
  eq. `moment_full` land in two *different* cross products with different companion terms, matched
  against the real code rather than assumed. Bit-for-bit at `u_B=u_C=0.0`, verified in combination
  with the aero table and thrust misalignment already active, not just in isolation. 175/175 tests
  (7 new).
- **Step 44 — pitch-damping `c_mq` scaffold** (commit `ff10242`). New `Params.c_mq` (`0.0`
  default), a new `sim/aero.py::C_mq(alpha,M,p)` (table-driven with a constant fallback — an
  absent table column falls back to `p.c_mq` rather than a literal `0.0`, a deliberate, documented
  exception to this module's usual "table wins completely" rule), wired into `forces.aero_moment_y`
  (confirmed as the real moment-assembly site, not `dynamics.py`). The damping term is computed
  division-free (`0.25·ρ·V·S·d_ref²·ω·c_mq`) specifically to avoid a `0.0·∞ = nan` trap at `V=0`,
  which every unperturbed flight passes through at apogee — this project hit that exact class of
  bug once already, at Step 35. `c_mq=0.0` bit-for-bit. **One real physics bug was caught before
  any of this was written**: the LaTeX's Dynamic Stability section had `c_mq`'s stability sign in
  the textbook convention, which is inverted relative to this project's own `A_m`/`c_m` sign
  (positive = nose-down, decided 2026-09-19) — the architect derived the correct sign
  (`c_mq > 0` is damping here) from three independent angles, the user confirmed the fix, and
  `analysis.tex` was corrected before Step 44's tests could encode the wrong sign permanently.
  187/187 tests (12 new), including a trajectory-level check that damped/undamped/anti-damped
  envelope-decay ratios come out strictly ordered.

**Recovery note:** the first developer session implementing these steps was terminated mid-Step-42
by a session-limit API error, before its first commit. Rather than losing the work, the
orchestrator recovered it directly: ran the suite on the leftover working-tree changes (166/168),
found and fixed three test-authoring bugs (a missing import, a pinned constant with the wrong
sign — confirmed independently before touching it, magnitudes matched to 6 significant figures —
and an `is`-identity check on a numpy scalar that can never pass, `y[1] is y[1]` being `False` even
trivially), reran to 168/168, then split the single uncommitted diff into the two proper commits
(41 and 42) along the boundaries the crashed session had already left clearly marked in its own
code comments. A fresh developer session then completed 43 and 44 without incident.

**Verification:** every commit's full suite independently re-run by the orchestrator, not taken on
either developer session's self-report alone. Final count: 187/187.

## Phase 2.6 doc/derivation pass (2026-09-27) — Steps 38-40 spec'd, code not yet implemented

At the user's request: implement gravity direction varying with downrange distance (Backlog B4),
thrust-axis misalignment, and humid-air density (Backlog B5) — plus two restructuring requests
folded in: reorder `models.tex` to **Gravity → Thrust → Mass → Aerodynamics → Atmosphere → other**
(Wind/Relative wind/Non-inertial), and promote "Analytical analysis" out of `rocket-2d.tex` into
its own `latex/sections/analysis.tex`. Done by the architect, documentation/derivation only — no
code changes yet (that's Steps 38-40, next).

**Restructuring:**
- `models.tex` subsections reordered per the user's explicit force-grouped order (a deliberate
  reversal of the report-finalization pass's dependency-first order) — this reintroduces forward
  references (§Thrust cites §Atmosphere's `p_amb`, §Aerodynamics cites §Atmosphere's ρ and §Other's
  `alpha`, further down in the document). Flagged transparently in the doc rather than silently
  "corrected" back, since `\autoref` resolves regardless of definition order.
- New `latex/sections/analysis.tex`: "Analytical analysis" promoted to its own top-level section
  (kept `\label{sec:analysis}` so every existing cross-reference survives). Fills the long-standing
  `\todo{actual section with thrust and no-thrust stability}` with an organized derivation across
  three configurations — **no thrust**, **aligned thrust**, **misaligned thrust** — plus the static
  stability analysis, in the user's requested order, with a small comparison table at the end of
  §Moment tying the three configurations together (user confirmed keeping this layout over an
  alternative that groups the three moment cases contiguously).

**New physics, derived (not yet coded):**
1. **Step 38 — gravity direction vs. downrange.** The local vertical rotates by `φ = x/R_e` from
   the launch vertical; `weight_inertial`'s direction becomes `(-sinφ, cosφ)` instead of the fixed
   `(0,1)`. Gated by a new `gravity_direction: str = "parallel" | "radial"` field (orthogonal to
   `gravity_model`'s magnitude selection, dispatch-dict pattern matching every other named-model
   field). Direction-only — no change to altitude bookkeeping, stays independent of the existing
   Coriolis correction (their own "independent and comparable, don't multiply" framing already in
   the doc). Verified numerically against the real `sim/dynamics.py`/`sim/frames.py` before being
   written up (e.g. the rotated-weight contribution to `dvx/dt`/`dvz/dt` reproduced exactly, zero
   contribution to `domega/dt`).
2. **Step 39 — thrust-axis misalignment.** A fixed nozzle cant angle `δ`
   (`thrust_misalign_deg: float = 0.0`), giving `T = T·(cosδ x̂_r + sinδ ẑ_r)`. Verified that
   `sim/dynamics.py`'s existing generic cross-product machinery needs **no code change at all** —
   it already produces exactly `(l1+l2)·T·sinδ` once `thrust_body` returns a vector with a nonzero
   `ẑ_r` component (the "future gimbal drops in with no structural change" comment in `dynamics.py`
   was literally true). Scoped to misalignment only, not a commanded/control-law gimbal (that stays
   backlog).
3. **Step 40 — humid-air density**, approved by the user: an optional `Td_K` (dewpoint, kelvin)
   sounding CSV column, gated by `humid_air: bool = False`, applying the standard Magnus/virtual-
   temperature correction (`ρ = p/(R_d·T_v)`) in the sounding/field tiers only — ISA stays dry-air
   by definition. Absent column → all-NaN → dry-air fallback, zero cost to every existing data
   file. Verified against a real sounding row (~0.5-1.25% density reduction, temperate to hot-humid
   conditions) and Magnus-formula reference values.

**Not verified:** no LaTeX toolchain in this environment — not compiled, only structurally checked
(51 labels, 191 cross-references, 0 dangling, 0 duplicates across all 4 files). **Compile locally
before treating this as final**, same caveat as the report-finalization pass.

**Next:** developer implements Steps 38, 39, 40 in that order, one commit each, full regression
suite after each. Steps 38 and 39 both touch `sim/forces.py` and must be done sequentially, not in
parallel, despite being physically independent corrections. Exact function signatures/`Params`
fields/formulas for all three are pinned in `architecture.md` §23.1/§23.2/§23.3 and in the
architect's dispatch — no developer should need to re-derive anything, only implement and test.

## Phase 2.6 milestone: COMPLETE (2026-09-27) — Steps 38, 39, 40 implemented and committed

All three steps done sequentially (38→39 both touch `sim/forces.py`, done one at a time as
planned), each independently verified by the orchestrator (diff review + a from-scratch `pytest`
run) before committing — not taken on the developer's self-report alone.

- **Step 38 — non-parallel gravity** (commit `da77aa6`). `sim/gravity.py` gains
  `z_hat_g(t,y,p)`, dispatching on new `Params.gravity_direction` ("parallel" default = the fixed
  `(0,1)` every prior step used; "radial" = `(-sin(x/R_e), cos(x/R_e))`), orthogonal to the
  existing `gravity_model` magnitude dispatch. `weight_inertial` now multiplies by it instead of
  the hard-coded `(0,1)`. 128/128 tests (5 new): `"parallel"` bit-for-bit regardless of `R_e`/`x`;
  `z_hat_g` stays unit-norm; `"radial"`'s translational shift matches the closed form
  `[-g·sinφ, g·(cosφ-1)]` exactly; `domega/dt` is **exactly** (not approximately) unchanged, since
  weight passes through the CoG and contributes no moment regardless of direction.
- **Step 39 — thrust-axis misalignment** (commit `f3089aa`). `thrust_body` gains
  `Params.thrust_misalign_deg` (default `0.0`), returning `T·(cosδ, sinδ)` instead of the on-axis
  `(T, 0)`. `sim/dynamics.py` needed **zero functional change** — its existing generic
  cross-product moment machinery already produces `(l1+l2)·T·sinδ`, independently re-verified
  numerically before trusting the architect's claim. Fixed manufacturing-grade misalignment only,
  not a commanded/control-law gimbal (that stays backlog). 134/134 tests (6 new): bit-for-bit at
  `δ=0`; moment shift matches the closed form exactly; shift is exactly zero post-burnout; the
  shift is identical at two different angles of attack (confirming a constant `δ` shifts the trim
  point without touching the static-stability slope `∂θ̈/∂α`); a statically stable airframe trims
  toward the sign of `δ` instead of diverging, and reversing `δ`'s sign mirrors it.
- **Step 40 — humid-air density** (commit `069abce`), the sounding-CSV-format extension approved
  by the user beforehand. New optional `Td_K` (dewpoint, kelvin) column, absent = all-NaN = dry
  fallback. `sim/soundings.py` carries `Td` through `Sounding`/`SoundingState`/`ResampledCase` and
  tier-3 IDW/RBF combination — the RBF stacking arithmetic was rewritten explicitly (4→5 blocks)
  specifically to make an off-by-one slicing mistake visible at the diff level, and a dedicated
  test exercises exactly that. `sim/atmosphere.py` gains `sat_vapor_pressure`/
  `virtual_temperature`/`moist_density` (Magnus formula; `R_d/R_v` computed, never hard-coded);
  applied in the sounding/field tiers only when `Params.humid_air` is set and dewpoint is finite —
  ISA stays dry-air by definition, untouched. 150/150 tests (16 new). One correction the developer
  found and flagged rather than silently accepting: the dispatch prompt's reference value
  `sat_vapor_pressure(20°C) = 2333.4 Pa` was a typo against the stated formula — independently
  re-derived to `2333.4406 Pa` (50-digit precision) and pinned to the verified value instead.

**Also landed in the same block, doc/derivation-only** (commit `17da67b`, before the three code
steps): `models.tex` reordered to **Gravity → Thrust → Mass → Aerodynamics → Atmosphere → other**
(a deliberate, user-requested reversal of the report-finalization pass's dependency-first order —
reintroduces some forward-references, flagged transparently rather than "corrected" back); and
"Analytical analysis" promoted out of `rocket-2d.tex` into its own `latex/sections/analysis.tex`
(label `sec:analysis` preserved), filling the long-standing `\todo{actual section with thrust and
no-thrust stability}` with an organized derivation across no-thrust / aligned / misaligned-thrust
configurations.

**Not verified:** still no LaTeX toolchain in this environment — the doc pass was structurally
checked only (51 labels, 191 cross-references, 0 dangling/duplicate). **Compile locally before
treating the report as final**, same standing caveat as every prior doc pass this project has had.

**Test suite: 150/150 passing**, up from 123 at the start of this block (5 + 6 + 16 new, one step
at a time, each independently re-run by the orchestrator before its commit).

## Gravity models complete (all 4 main.tex variants)
Step 10-11 finished all four gravity variants (constant/linear/radial/wgs84). Next steps move to
atmosphere.

## Phase 2 progress
- Step 9 — `sim/flow.py` (Flow: V, alpha, u_hat, n_hat; wind stubbed at zero until Step 21).
  `aero_force_body` now uses actual relative wind instead of fixed body axes. 13/13 tests passing
  (6 new). Ascent leg unchanged (apogee 1650.7038 m / 18.5071 s, exact match to Step 8). Impact
  time changed 35.9856s -> 37.8688s and max speed 188.88 -> 178.30 m/s — this is the intended
  physics fix: previously drag always added to the fall during descent (nose up, moving down);
  now it correctly opposes the actual relative wind and slows the fall, as roadmap Step 9 intended
  ("makes the descent leg physical for the first time"). Commit `79af229`.
- Step 10 — `sim/gravity.py`: constant/linear/radial models via `Params.gravity_model` string +
  dispatch dict (approved pattern). `Params` gains `gravity_model` (default "constant", preserves
  all behavior) and `R_e` (Earth radius, 6.371e6 m). 20/20 tests passing (7 new). Default-model
  regression exact match to Step 9. At current scenario altitude (~1650m) linear/radial differ
  from constant by ~0.39 m; at h=100km they diverge by ~7.5e-4 relative, as physically expected.
  Commit `1f8c641`.
- Step 11 — `sim/gravity.py`: 4th variant "wgs84" (Somigliana normal gravity + second-order
  free-air correction, standard published NIMA TR8350.2 constants). `Params` gains
  `lat0_deg`, `lon0_deg`, `h0_m`, `azimuth_deg` (site block, per architecture.md §18, safe
  defaults, no behavior change for other models). 26/26 tests passing. Spot-checks: equator
  9.7803253 m/s^2, pole 9.8321849 m/s^2 (both match published constants to 7 sig figs — the pole
  value is a derived cross-check, not an input, giving high confidence the formula is correct),
  45° mid-latitude 9.8061978 m/s^2, decreasing with altitude as expected. Commit `f53a0f8`.
- Step 12 — `sim/atmosphere.py`: full 7-layer ISA (troposphere through mesosphere), `AirState`
  (rho, p, T, a, mu). Fixed g_isa=9.80665 kept separate from the user's selected gravity model
  (correct per the standard's own definition). NOT yet wired into flow/forces/dynamics (that's
  Step 13). 36/36 tests passing. Sea-level values match standard reference exactly (rho=1.225,
  p=101325, T=288.15K, a=340.29 m/s, mu=1.789e-5 Pa*s); tropopause and 5000m checks correct.
  Commit `09950ce`.
- Step 13 — `sim/flow.py`, `sim/forces.py`, `sim/params.py`: Flow gains air, q=½ρV², M=V/a,
  Re=ρVl_ref/μ; added aero_model with "constant" and "coefficients" (A_x = qS·C_A0,
  A_z = qS·C_Nα·α, A_m = qS·d_ref·C_mα·α); added S, d_ref, l_ref, C_A0, C_N_alpha, C_m_alpha to
  Params. Verified that aero_model="constant" reproduces Step 12 exactly; with "coefficients"
  drag vanishes at V=0, reverses on descent and falls with altitude. Commit `9b558c1`.
- Step 14 — `sim/thrust_curve.py` (new): time/thrust table via `lru_cache`d loader + `np.interp`,
  zero after the last point. Removed the `T_BURN` constant-thrust hack from `sim/forces.py`
  entirely — `thrust_body` now calls `thrust_curve.thrust(t, s, p)`. Added `motor_curve: str = ""`
  to `Params` (default reproduces the "no thrust" case, matching every other Phase 2 field's
  Phase-1-preserving-default pattern; `run.py`'s scenario now sets `motor_curve="placeholder.csv"`
  explicitly, since the old `T=50.0` field is no longer read by `thrust_body` at all). Added a
  `burnout` event to both integrators in `sim/integrate.py` (`Result.events["burnout"]`), including
  a real scipy `solve_ivp` gotcha found and fixed along the way: an event function that stays
  *exactly* zero over an extended interval (post-burnout, or the whole flight with no curve) gets
  classified as both a rising and falling edge by scipy's `<=`/`>=` event logic, causing spurious
  detections at t=0; fixed with a tiny epsilon shift (`_BURNOUT_EPS = 1e-9` N) on the RK45 path
  only (the hand-written RK4 path does a direct numeric comparison and doesn't need it).
  `data/motors/placeholder.csv` is a small illustrative solid-motor-shaped curve (ignition spike to
  150N, settle to 90N, flat sustain, linear tail-off to 0 by t=2.0s; stated total impulse
  162.75 N·s, verified by `np.trapezoid` in `tests/test_thrust_curve.py`). 47/47 tests passing (4
  new thrust-curve tests + 3 new burnout-event tests in `tests/test_integrate.py`; `T_BURN`'s old
  regression test in `tests/test_dynamics.py` updated to use the new curve, since the field it used
  to set, `T`, is now inert). This step intentionally changes the trajectory versus Step 13 (a real
  motor curve replacing a fake constant-thrust rectangle is the point of the step) — there is no
  bit-for-bit regression claim here, unlike the gravity/atmosphere/aero model-selection steps.
  Commit `0d184bf`.
- Step 16 — `sim/thrust_curve.py`, `sim/params.py`: altitude pressure correction on top of the
  curve lookup, `T(t,h) = T_ref(t) + A_e*(p_ref - p_amb)` with `p_amb` from
  `atmosphere.air_state(t, s, p).p`. `Params` gains `A_e` (default 0.0, nozzle exit area) and
  `p_ref` (default 101325.0 Pa). The correction is guarded to only apply while `T_ref(t) > 0`
  (motor actually flowing) — otherwise `A_e*(p_ref - p_amb)` would manufacture nonzero thrust from
  ambient pressure alone during coast/pre-ignition, breaking the clean zero-after-burnout cutoff
  Step 14's burnout event depends on. `A_e = 0.0` (the default, used by `run.py`'s scenario)
  short-circuits before touching the atmosphere model at all, reproducing Step 14 bit-for-bit
  regardless of `p_ref` or `atmosphere_model` — confirmed via `run.py` (identical printed summary:
  burnout 2.0000s, apogee 4609.2267m/30.1209s, max speed 304.0110 m/s, impact 62.4745s). 50/50
  tests passing (3 new: inert-at-default, sign/magnitude-correct pressure boost mid-burn verified
  against the exact ISA sea-level pressure, still-zero after burnout with `A_e != 0`).
  Commit `0882da3`.
- Step 17 — `sim/soundings.py` (new): shared data layer for atmosphere tiers 2/3 AND wind tiers
  2/3 (no physics wired in yet — pure infrastructure). `Sounding` NamedTuple per architecture.md
  §17 (station/lat/lon/elev/time_utc + h/p/T arrays + u/v ENU wind components derived at load time
  from wdir/wspd via the standard meteorological convention). `load_case(case)` (`lru_cache`d,
  globs `data/soundings/<case>/*.csv`). `interp_altitude(sounding, h) -> SoundingState(p,T,rho,a,mu,u,v)`
  — the tier-2 (single-station) altitude-interpolation seam Steps 18/22 will call: T linear in h,
  p linear in ln(p), u/v linear in h, rho/a/mu derived (reusing `atmosphere.py`'s own physical
  constants, not duplicated). Below the lowest data point: continues with the sounding's own local
  lapse rate from its first two points (isothermal fallback for a degenerate single-row file).
  Above the highest data point: an ISA-*shaped* profile re-anchored at the sounding's own top point
  so T/p stay continuous at the seam (reuses `atmosphere.py`'s layer-crossing algorithm, walking
  forward from the new anchor rather than sea level). Worked example committed at
  `data/soundings/example/LKPR_202605011200.csv` (extends architecture.md §17's own literal LKPR
  example up through the tropopause, hand-crafted, ISA-like-but-not-identical — no live weather
  API, offline only). 62/62 tests passing (12 new): the roadmap's stated check (an ISA-derived
  synthetic sounding round-trips through the loader/interpolator to within 0.5% of
  `atmosphere.air_state` between its nodes), wind ENU conversion at the four cardinal directions,
  continuity at both extrapolation seams, physical sanity (finite, positive, monotone p/rho) well
  above the data range, the local-lapse-rate below-range behavior, the single-row degenerate case,
  and `load_case` caching/missing-case-error behavior. Commit `cc77846`.
- Step 18 — `sim/atmosphere.py`, `sim/params.py`: tier 2, `"sounding"` — `_sounding_air_state`
  loads `p.sounding_case` via `soundings.load_case` (first station only; multi-station combination
  is Step 20), computes `h_msl` the same way tier 1 does, and repackages
  `soundings.interp_altitude`'s `p/T/rho/a/mu` into `AirState` (drops `u`/`v` — wind.py's concern,
  Step 22). `Params` gains `sounding_case: str = ""`. Default `atmosphere_model="isa"` unchanged.
  66/66 tests passing (4 new): the ISA-derived synthetic case matches `"isa"` to ~0.05% between
  nodes (well inside the 0.5% bound); a full trajectory run with that synthetic case matches the
  `"isa"` run's apogee/impact to ~0.01-0.02%; with the real worked example (LKPR, elevation 380m),
  the station's actual numbers are warmer and lower-density than ISA predicts at that altitude
  (measured ~0.71% lower density), and a full trajectory run confirms the physically expected
  consequence — less drag, apogee ~0.47% higher, impact time ~0.98% shorter — checked as a strict
  directional assertion, not just `!=`. Commit `26f1f8f`.
- Step 19 — `sim/soundings.py`, `sim/params.py`: tier-3 horizontal combination across stations,
  pure infrastructure (not wired into `atmosphere.py`/`wind.py` yet — Steps 20/23). `_resample_case`
  resamples every station of a case onto a common altitude grid at load time (cached on
  `(case, grid_top_m, grid_step_m)`), reusing `interp_altitude` level-by-level rather than
  duplicating its interpolation/extrapolation rules. `project_latlon` does the equirectangular
  tangent-plane projection centred on the launch site. `interp_field_at(case, E, N, h, p)` weights
  the resampled stations at a tangent-plane point (`"idw"` default — `wᵢ ∝ 1/(dᵢ²+ε²)` — or
  `"rbf"` via `scipy.interpolate.RBFInterpolator`), combines with a dot product, then feeds the
  combined profile back through `interp_altitude` for the final altitude lookup.
  `interp_field(case, y, h, p)` is the convenience wrapper from the rocket's own state vector
  (ground position `(x·sin A, x·cos A)`) — this is the exact seam Steps 20/23 call. `Params` gains
  `horizontal_interp` (default `"idw"`), `grid_top_m` (30000.0), `grid_step_m` (100.0),
  `idw_epsilon_m` (500.0). 72/72 tests passing (6 new): one station reproduces tier 2 exactly;
  querying at one station's own coordinates among several is dominated by (but, correctly per the
  IDW+epsilon math, not identical to) that station, checked against an exact analytic bound, not a
  loose tolerance; two identical-profile stations combine to that same profile everywhere,
  including far outside both; the rocket-ground-position wrapper agrees with the explicit-point
  seam; an `"rbf"` smoke test inside a 3-station triangle; and projected-vs-haversine distance
  <0.1% — with an explicitly documented, verified caveat that this bound holds for cardinal-direction
  offsets at any distance up to 100 km and moderate diagonals (~35 km), but a diagonal pushed all
  the way to 100 km can exceed 0.1% (an expected property of the equirectangular/plate-carree
  approximation architecture.md §17 itself specifies, not a bug — flagged rather than silently
  narrowed). Commit `9d6e791`.
- Step 20 — `sim/atmosphere.py`: tier 3, `"field"` — `_field_air_state` delegates to
  `soundings.interp_field(p.sounding_case, y, h_msl, p)` (Step 19's horizontal-combination
  machinery) and repackages the result into `AirState`, same as tier 2 minus wind. First
  atmosphere model whose output depends on `y[X]`, not just `y[Z]`. No new `Params` fields (all of
  `sounding_case`/`horizontal_interp`/`grid_top_m`/`grid_step_m`/`idw_epsilon_m` already existed
  from Steps 18/19). New multi-station example: `data/soundings/field_example/` — FLDA (lat 48.0,
  lon 16.0, T0=293.15K/p0=102000Pa, warm/high-pressure) and FLDB (lat 48.0, lon 16.5, ~37km due
  east, T0=288.15K/p0=99000Pa, cooler/low-pressure), both sharing the standard troposphere lapse
  rate, kept purely cardinal (east-west only) per Step 19's own note about diagonal placements
  degrading the tangent-plane projection's accuracy. 74/74 tests passing (2 new): a single-station
  case reproduces the `"sounding"` tier exactly through the full `air_state` seam; with the
  two-station case, density along a ground-track sweep from FLDA to FLDB decreases monotonically —
  the correct direction given FLDA is actually denser than FLDB at every shared altitude (pressure
  offset dominates despite FLDA also being warmer), confirmed from the stations' real numbers, not
  asserted blindly. Commit `f818573`.
- Step 21 — `sim/wind.py` (new), `sim/flow.py`, `sim/params.py`: tier 1, `"analytic"` —
  `wind_inertial` dispatches on `p.wind_model` (`"none"` default, zeros; `"analytic"` power-law
  shear `W(h) = wind_ref_ms*(max(h,h_ref)/h_ref)^shear_exp`, AGL not MSL, clamped below `h_ref`).
  Meteorological `wdir - azimuth` projection onto the flight plane per architecture.md §16;
  cross-plane component computed and discarded via `wind_horizontal_enu` (exposed for Phase 3 to
  reuse unchanged). Optional deterministic gusts: a frozen sum of 8 sinusoids with phases/weights
  drawn once from `np.random.default_rng(gust_seed)`, cached per seed; `gust_sigma=0.0` skips the
  RNG entirely. `flow._wind_inertial` now delegates here instead of the inline zeros stub. `Params`
  gains `wind_model`, `wind_ref_ms`, `wind_dir_deg`, `wind_ref_h_m`, `wind_shear_exp`, `gust_sigma`,
  `gust_seed`. 81/81 tests passing (7 new): `"none"` reproduces the pre-Step-21 stub bit-for-bit
  (verified by monkeypatching the old stub back in and diffing a full trajectory, not a pinned
  baseline); a pure headwind raises `V` by exactly the wind speed; the four cardinal directions
  give the derived-not-guessed sign (headwind/tailwind/crosswind/crosswind); headwind and tailwind
  of equal speed bracket the still-air apogee in the correct order (needed an inclined launch —
  purely vertical flight makes headwind/tailwind indistinguishable, since `|v_rel|` depends on
  `w_x²` when the rocket's own downrange velocity is negligible); gust determinism (bit-for-bit
  identical across repeated calls) and `gust_sigma=0.0` exactness. Flagged in passing (not a Step
  21 bug): the `C_N_alpha`/`C_m_alpha`/`l1` combination shared by earlier test modules is
  pitch-unstable the moment `alpha != 0` is ever engaged — invisible before this step since every
  prior one kept `theta` pinned with zero wind; worth remembering for Step 25. Commit `7e15296`.
- Step 22 — `sim/wind.py`: tier 2, `"sounding"` — `_sounding_wind` loads `p.sounding_case` via
  `soundings.load_case` (first station only, same convention as the atmosphere tiers) and
  `soundings.interp_altitude` for `(u, v)` ENU wind at `h_msl = -y[Z] + p.h0_m` (MSL, not AGL —
  a measured station profile is tied to real altitude, unlike tier 1's ground-referenced shear).
  Projects ENU `(u, v)` onto the flight plane via `w_along = u·sin(A) + v·cos(A)`,
  `w_cross = u·cos(A) - v·sin(A)` — derived from first principles and verified algebraically
  consistent with tier 1's `w_x = -W·cos(wdir-azimuth)`/`w_y = -W·sin(wdir-azimuth)` by
  substituting tier 1's own ENU conversion and reducing via the cos/sin angle-difference
  identities. No new file format, loader, or `Params` field — reuses Step 17/18's machinery
  entirely. 86/86 tests passing (6 new, `tests/test_wind.py` now 12): a synthetic constant-wind
  sounding matches the analytic model at `shear_exp=0` (including strictly-between-node
  interpolation); a synthetic pure-veering profile (wdir sweeping 0→45→90°) shifts the downrange
  component exactly as `-W·cos(wdir)` predicts; the real `example` (LKPR) case's wind genuinely
  veers 210°→265° from 380m to 10000m, confirmed against hand-computed expected values at each
  data row; MSL (not AGL) altitude convention confirmed via `h0_m`. Commit `1c10109`.
- Step 23 — `sim/wind.py`: tier 3, `"field"` — `_field_wind` delegates to
  `soundings.interp_field(p.sounding_case, y, h_msl, p)` (Step 19's horizontal-combination
  machinery, same call `atmosphere._field_air_state` makes at Step 20) and reuses tier 2's exact
  ENU→flight-plane projection unchanged. 6 executable lines, as the roadmap itself predicted
  ("reusing the Step 19 weighting machinery unchanged... a handful of lines"). No new `Params`
  fields. This closes out all three wind tiers (analytic/sounding/field), mirroring the atmosphere
  tiers exactly. 88/88 tests passing (2 new): a single-station case reproduces the `"sounding"`
  tier exactly through the full `wind_inertial` seam; a new synthetic two-station case with
  genuinely opposing wind directions (0°/180°, cardinal N-S placement) shows the along-plane wind
  component increasing strictly monotonically across an 11-point ground-track sweep, negative near
  one station and positive near the other, crossing zero exactly once. Commit `b1fb9fb`.

## Step 24 — skipped for now (optional, deferred as non-trivial)
Step 24 (time interpolation between sounding snapshots) is marked optional in the roadmap. Skipped
rather than attempted this pass: it needs a "group multiple time-snapshots per physical station"
concept that doesn't exist yet in `sim/soundings.py` — right now every CSV file in a case is
treated as an independent *spatial* station, so feeding it two snapshots of the *same* station
would currently be silently double-counted by the tier-3 IDW average as two different stations at
the same location. That's a real design decision, not "a handful of lines" — deferred until there's
an actual multi-snapshot dataset to design against.

## Sign-convention correction (pre-Step-25, 2026-09-20/21)
The architect flagged (`architecture.md` §19/§22 item 5) that `main.tex`'s original geometry
(`Aa = -l1·x̂_r`) makes a linear normal aero force **divergent**, not restoring, for any positive
`l1` — static stability needs the CoP aft of the CoG. Per the user: `l1`/`l2` are meant to stay
**positive** throughout (both measured from the nose tip), so the fix is not "make `l1` negative"
but a corrected geometry: `main.tex`'s `Geometry` subsection now has `Aa = +l1·x̂_r`
(`aA = -l1·x̂_r`, `aB = -(l1+l2)·x̂_r`) — commit `ac2cff2`. The corresponding code fix landed as its
own dedicated commit before Step 25:
- `sim/dynamics.py`: `aA`/`aB` now built as `(-p.l1, 0)` / `(-(p.l1+p.l2), 0)`, matching the
  corrected `main.tex`.
- `tests/test_forces.py`: the Step 6 regression test's closed form re-derived and flipped to
  `M_y = -l1·A_z - A_m` (from `+l1·A_z - A_m`), independently re-derived via `_cross_y`, not just
  asserted.
- Scanned every test using the flagged unstable fixture (`l1=0.3, C_N_alpha=2.0, C_m_alpha=-0.5`,
  first noticed by Step 21's developer) — none needed changes: each either never calls
  `dynamics.derivatives`/`run_sim` directly, keeps `theta` pinned with zero/symmetric wind so
  `alpha` stays 0 throughout, or is a differential comparison (old-stub-vs-new, isa-vs-sounding,
  RK4-vs-RK45) where the sign cancels out on both sides.
- New test demonstrates the actual physical fix directly (not just algebra): an off-axis launch
  (`alpha0 = -0.15 rad`) with `aero_model="coefficients"`, `C_N_alpha=2.0`, `l1=0.3` stays
  **bounded** (`|alpha|` never exceeds its initial magnitude by more than ~1%, oscillatory) under
  the corrected sign, versus reaching `alpha(1.0s) ≈ -2.19 rad` (~14.6× the initial magnitude, past
  ±π/2) with the old sign reconstructed for contrast. Honest caveat, confirmed not assumed: this
  model has no pitch-rate damping yet (arrives with Step 25's real coefficients), so a bounded
  undamped oscillator — not literal decay to zero — is the correct, verified characterization of
  "restoring" here.
- `run.py` provably unaffected (its scenario has `A_z=0, A_m=0`, `aero_model="constant"`) —
  confirmed byte-for-byte identical stdout before/after.
- 89/89 tests passing (1 new). Commit `c2e7537`.

## Phase 2 progress (continued)
- Step 25 — `sim/aero.py` (new): `C_A(α,M)`, `C_N(α,M)`, `C_m(α,M)`, `cop_l1(α,M)` — table-driven
  via `p.aero_table` (own design, since architecture.md §19 leaves the exact column format
  unspecified: `alpha_deg,M,C_A,C_N,C_m,l1_m` rows, rectangular `(M,α)` grid, `np.interp` in α
  within each bracketing M row then linearly blended across the M bracket, clamped — not
  extrapolated — outside the M range), with the existing `Params` constants (`C_A0`, `C_N_alpha`,
  `C_m_alpha`, `l1`) as the exact fallback when `p.aero_table==""` (default). New
  `data/aero/example.csv`: synthetic, illustrative fin-rocket-shaped table (transonic drag hump,
  peak normal-force slope near M=1, restoring `C_m`, CoP moving aft with Mach), every row keeping
  `l1_m > 0` (stable per the just-corrected sign convention). `sim/forces.py`'s `"coefficients"`
  regime now calls `aero.C_A`/`C_N`/`C_m` instead of inline formulas (bit-for-bit unchanged when no
  table). `sim/dynamics.py`'s `derivatives()` now computes `l1_aero = aero.cop_l1(flow.alpha,
  flow.M, p)` for `aA` (the CoP position) only — `aB` (the thrust exit point, a fixed mechanical
  point on the body) deliberately stays on the constant `p.l1`, since coupling it to the moving CoP
  would invent an unspecified thrust-misalignment effect outside this step's scope. This needed one
  extra `flow_state` call in `dynamics.py` beyond a pure constant-to-function swap — flagged as a
  small, deliberate exception to the roadmap's general "dynamics.py doesn't change in Phase 2"
  note, not a structural change. 96/96 tests passing (7 new): table lookup verified against an
  independent hand computation of the same bilinear formula; exact-grid-point lookup with zero
  interpolation error; edge-clamping (no extrapolation); malformed non-rectangular table rejected
  with `ValueError`; no-table path reproduces every pre-Step-25 formula bit-for-bit including
  through the full `dynamics.derivatives()` seam; a decisive check that `dynamics.py` actually uses
  the table's `l1` and not a deliberately-absurd stale `p.l1=999.0`; and a full-trajectory
  weathercocking check extending the sign-fix commit's off-axis scenario through the real
  table-driven path. Same honesty finding as the sign-fix commit, re-verified with the real table
  (not assumed): `alpha(t)` stays bounded and oscillatory (`[-0.150, -0.0998, 0.0548, 0.0433,
  -0.0930, -0.0636]` rad over `t=0..5s`), not decaying to zero — this model still has no
  pitch-rate-damping term anywhere, so genuine decay isn't physically achievable at this step
  regardless of the table's nonlinearity. Commit `c4fe830`.
- Step 26 — `tools/fetch_sounding.py` (new, approved by the user — the only part of the project
  that touches the network): a hand-run CLI, never imported by `sim/`, fetching from the
  University of Wyoming radiosonde archive's current live endpoint
  (`https://weather.arcc.uwyo.edu/wsgi/sounding` — the older `weather.uwyo.edu` host has moved;
  discovered by fetching it directly since a research subagent's session lacked Firecrawl this
  time). `robots.txt` there disallows `/wsgi`, the actual data endpoint — used anyway with the
  user's explicit, informed approval (a hand-run, occasional, single-request tool, not the
  bulk/automated crawling robots.txt is aimed at), documented transparently in the script's
  docstring and in every file's `# source:` line. Splits network I/O (`fetch_raw`) from pure logic
  (`parse_response`/`resample_rows`/`format_canonical`) so the parsing path is unit-testable
  offline. Resamples the archive's ~1-second-resolution response (thousands of rows) down to a
  configurable altitude step (default 250 m, nearest-sample) before writing the canonical CSV
  format. Handles the archive's "no data" case (confirmed live: HTTP 404 with a plain-text body,
  not the 200 originally assumed) as a clear `SoundingFetchError`. 109/109 tests passing (13 new,
  all offline against a captured response fixture — no live network call in the automated suite).
  Live end-to-end verification (station 72672, 2024-01-15 12:00Z): 5040 raw rows → 122 resampled,
  written to `data/soundings/example_live/72672_202401151200.csv` (kept, committed, as a genuine
  real-data worked example alongside the earlier hand-crafted ones), loads with zero edits via
  `sim.soundings.load_case`, physically sane values throughout (elevation 1699m closely matches
  station 72672/KRIW's real ~1697m elevation — a good independent sanity check the unit
  conversions and metadata convention are correct). Commit `00a576a`.
- Step 27 — `run.py`, `sim/plotting.py`: the payoff for the whole model-selection pattern
  (architecture.md §12). `run.py` gains `sweep(base_params, field, values, s0)` — the exact
  `dataclasses.replace(p, <field>=<value>)` idiom §12 itself specifies, one `run_sim` per variant
  — plus a plain-text summary table (apogee altitude/time, max dynamic pressure "max-Q" sampled via
  `flow_state` on the same dense grid the single-run summary already uses, impact time) and
  `sim/plotting.py` gains `plot_trajectory_overlay` (flight-path + altitude-vs-time panels, one
  line per variant, same dense-output convention as the existing plot functions). Two sweeps run by
  default: the four gravity models (at this scenario's own ~4.6 km apogee) and `"isa"` vs the real
  LKPR sounding (`data/soundings/example`, `aero_model="coefficients"` so the atmosphere is
  actually load-bearing). The original single-run scenario and its printed summary are completely
  unaffected (confirmed byte-identical). 114/114 tests passing (5 new): sweep produces one `Result`
  per variant with sane summaries; gravity apogee ordering is physically predictable
  (`constant < linear ≈ radial < wgs84` at this scale, `wgs84` highest partly because the default
  `lat0_deg=0.0` equator start has `γ₀(0)=9.7803 < g=9.80665`); atmosphere sweep confirms the real
  sounding gives higher apogee and lower max-Q than ISA (less dense air, less drag — consistent
  with Step 18's own finding); a direct check that gravity-model divergence is small (`<1%`) at
  ~4.6 km but clearly visible (`~8×` larger) at 100 km, exactly the roadmap's stated check; overlay
  plot returns a valid figure. Commit `9291b32`.

  **Actual printed sweep tables — re-pinned 2026-10-10 (Phase 2.11, Step 60).** Captured from a
  real headless `MPLBACKEND=Agg python -u run.py` in this tree at commit `3f081a3` (i.e. with all of
  Steps 50-59 in), not transcribed from any step report:
  ```
  Gravity model comparison (gravity.model sweep):
  gravity.model    apogee_alt[m]   apogee_t[s]     max_q[Pa]   impact_t[s]
  ------------------------------------------------------------------------
  constant              666.5064        9.4498   105350.1105       17.8740
  radial                666.5328        9.4507   105349.8006       17.8758
  wgs84                 667.0246        9.4633   105374.5378       17.9011

  Atmosphere model comparison (station LKPR) (atmosphere.model sweep):
  atmosphere.model   apogee_alt[m]   apogee_t[s]     max_q[Pa]   impact_t[s]
  --------------------------------------------------------------------------
  isa                   682.3777        9.5833    23068.9022       26.5922
  sounding              685.1438        9.6047    23003.8544       26.6500
  ```
  **Why this record moved, and what it supersedes.** The numbers above are not a correction of an
  error in Step 27's own work; four separate, individually documented changes landed on top of it,
  and the record had simply never been re-pinned since:
  1. **Step 34** removed the `linear` gravity model outright, so the gravity sweep has three rows,
     not four. (Known stale since then.)
  2. **Steps 28-44, unattributed** — a drift in `max_q`/`impact_t` of several percent in both
     sweeps, found during Step 45's verification and *proved* unrelated to Step 45 by a
     stash-and-diff, but never traced to its actual cause. This re-pin **resolves the record, not
     the question**: where that drift came from is still unexplained, and if it ever matters it
     needs its own look (`roadmap.md`'s Step 45 entry carries the same note).
  3. **Step 55** (the aero bug fix, commit `8b8a343`) — the deliberately non-bit-for-bit step. With
     `aero.model="constant"` now genuinely `q`-scaled, the scenario's `C_x=0.5` produces real drag
     instead of an inert 0.5 N placeholder, so apogee drops ~4.6 km → ~666.5 m and `max_q` roughly
     doubles (54.9 kPa → 105.4 kPa) at the much lower, denser-air trajectory. This is the dominant
     change in the gravity sweep. The **atmosphere** sweep moved far less (682.3775 → 682.3777 m)
     because it carries Step 55's deliberate `aero.model="linearized"` override — preserved with its
     reasoning intact at Step 58 — so its coefficients were already `q`-scaled before the fix; its
     `impact_t` shift (25.91 → 26.59 s) is item 2's drift, not item 3's.
  4. **Step 58** (commit `78a7e55`) — column header text only: `gravity_model` → `gravity.model`,
     `atmosphere_model` → `atmosphere.model`, following the nested `Params` of Steps 50-52.

  Items 1 and 2 were pre-existing drift this pass did not cause; items 3 and 4 are this pass's own,
  and intended. All four are now resolved together by the single re-pin above.

## Phase 2 milestone: COMPLETE
Every model family in `main.tex` §Models is implemented and selectable via a `Params` string field:
4 gravity variants, 3 atmosphere tiers, 3 wind tiers, a real thrust curve with pressure correction,
and Mach/α-dependent aero coefficients with CoP travel — plus the shared real-data infrastructure
(sounding format/loader/altitude-interpolation/horizontal-interpolation) backing the tier-2/3
variants of both atmosphere and wind, an offline fetch helper for real sounding data, and a
comparison-sweep tool that makes the point of having multiple models actually visible. 19 mandatory
steps, all committed individually as the working rules require. 2 steps (15, 24) remain optional
and deferred, not blocking. Phase 3 (3D, 6-DOF) has not been started.

## Phase 2 milestone reached
Steps 9-23 and 25-26 all complete (Step 15 optional/blocked, Step 24 optional/deferred). Every
model family in `main.tex` §Models is now implemented and selectable: gravity (4 variants),
atmosphere (3 tiers), wind (3 tiers), thrust curve + pressure correction, and Mach/α-dependent aero
coefficients with CoP travel. Only Step 27 (the comparison-sweep payoff step) remains to close out
Phase 2.

## Step 15 — skipped for now (optional, still blocked)
Step 15 (propellant depletion / variable mass) is marked optional in the roadmap's dependency
graph and remains blocked: `main.tex` §Current assumptions still states "CoG doesn't change",
which directly contradicts a time-varying `I(t)`/`l1(t)`/`l2(t)`. Re-checked 2026-09-20 before
starting Step 16 — still unchanged. Proceeding straight to Step 16 (pressure correction), which
does not depend on Step 15. Revisit Step 15 if/when the user updates `main.tex` with the CoG/
inertia-shift derivation.

## Phase 2 scope (expanded per user request 2026-09-19)
- Gravity: constant, linear, radial (inverse-square), WGS84 real-data — selectable via
  `Params.gravity_model` string.
- Atmosphere: ISA / real single-station sounding / real multi-station spatially-interpolated —
  goal is rho, Reynolds number, Mach number.
- Wind: same three-tier structure (analytic / single-station / multi-station interpolated),
  sharing data infrastructure (`sim/soundings.py`) with atmosphere.
- Launch rail and recovery moved to a Backlog section (deferred, not deleted).
- `main.tex` updated (commit `9895505`) with relative-wind/AoA derivation and Gravity/Atmosphere/
  Wind model specs. `architecture.md`/`roadmap.md` revised for Phase 2 (commit `84b70f2`):
  Steps 9-27 + Backlog (B1-B6).

## Phase 2 decisions log (2026-09-19)
- Model selection: `Params` string field + dispatch dict per family (not pure §4 single-body
  seam, not strategy objects) — keeps one public function per family, makes model comparison
  trivial, self-documents in printed/CSV output.
- Real-data format: one unified sounding CSV per station/time (T, p, wind together), folder =
  "case" under `data/soundings/`. Shared loader/interpolator for atmosphere AND wind tiers 2-3.
- No pandas — `numpy.genfromtxt` + a small header parser. `requirements.txt` unchanged.
- No live weather API — manual CSV drop into `data/soundings/` for now. An optional offline
  fetch script (`tools/fetch_sounding.py`, stdlib urllib, no dependency) may be added later as
  its own approved step; `sim/` never touches the network.

## Known issue flagged by architect (not blocking yet)
Sign convention check needed before Step 25 (aero coefficients): per `main.tex`'s geometry
(`Aa = -l1*x_hat_r`), a normal aero force produces a **divergent** moment when `l1 > 0` — static
stability requires `l1 < 0` (CoP aft of CoG). The old roadmap had this backwards. Revisit before
Step 25.

## Milestone
All of `main.tex` (as of Step 6) is implemented in code: translation + rotation, all
forces/moments, everything as constants. Confirmed by 7 passing tests (frames, forces, and an
independent RK4-vs-RK45 cross-check) plus multiple regression checks across steps. Full 2D
trajectory + pitch plots and flight summary in place (Step 7). Two independent integrators
(scipy RK45 and a hand-written RK4) agree on the same physics (Step 8), proving `dynamics.py`
itself — not just the solver — is correct.

## Completed steps
- Step 1 — scaffolding: `Params`/`State` containers, `run.py` prints them. Commit `4c3f836`.
- Step 2 — vertical point-mass flight under constant thrust + gravity (theta frozen at pi/2,
  no aero). Sign convention validated: apogee altitude/time match the analytic closed form
  (`a = T/m - g`) to ~1e-7 relative error. Introduced a temporary `T_BURN = 2.0s` constant in
  `sim/dynamics.py` (Step-2-only device, to be replaced by the real thrust curve in Step 11).
  Commit `2024207`.
- Step 3 — altitude and vertical-velocity plots vs. time (`sim/plotting.py`), sampled from the
  dense `solve_ivp` interpolant. `run.py` saves `output.png` (gitignored) and calls `plt.show()`.
  Trajectory shape confirmed numerically (monotonic climb, peak at apogee, monotonic descent to
  impact). Added `.gitignore` (pycache, generated PNGs). Commit `3c5f261`.
- Step 4 — `sim/forces.py` (weight_inertial, thrust_body, aero_force_body, aero_moment_y, per
  architecture.md's model-swap seam); `dynamics.py` refactored to build forces from it (rotation
  matrix at theta=pi/2 written inline, not yet in frames.py — that's Step 5). Constant axial drag
  `A_x` now lowers apogee (1650.70 m vs Step 3's 1839.43 m); regression-checked A_x=0 reproduces
  Step 3 exactly. Commit `68eb716`.
- Step 5 — `sim/frames.py` (R_body_to_inertial, to_inertial, to_body — the only trig in the
  codebase); `dynamics.py` refactored to use it instead of inline cos/sin. First tests added
  (`tests/test_frames.py`, 4 passing: identity at theta=0, nose-to-up at theta=pi/2, orthogonality,
  round-trip). `theta` still fixed (not yet integrated). Step 4 regression reproduced exactly;
  tilted trajectory (theta0=60°) demonstrated non-zero downrange motion (throwaway check, not
  committed to run.py). Commit `f794ec8`.
- Step 6 — rotational dynamics: `theta`/`omega` are now real integrated states, moment
  `M_y = cross_y(aB,T) + cross_y(aA,A_f) + A_m` about the CoG (cross products written explicitly,
  not pre-simplified, so a future gimbal/misalignment drops in cleanly). 2 new tests
  (`tests/test_forces.py`: thrust moment is exactly zero on-axis; moment matches closed form
  `l1*A_z - A_m` to 1e-12). Regression: theta stays exactly constant when A_z=A_m=0 (current
  placeholder), apogee/impact unchanged from Step 5. Demonstrated correct-direction pitch-over
  (positive A_m -> nose down) via throwaway check. Commit `d5226ac`.
- Step 7 — `plot_trajectory` (downrange vs altitude, equal aspect) and extended
  `plot_time_histories` (2x2: altitude, speed, pitch deg, pitch-rate deg/s) added to
  `sim/plotting.py`. `run.py` prints a full flight summary (apogee altitude/time, max speed,
  impact time, downrange at impact) and saves `trajectory.png`, `time_histories.png`,
  `trajectory.csv` (all gitignored). With current placeholder (vertical launch, A_z=0):
  downrange at impact = 0 m, as expected. Commit `81615c6`.
- Step 8 — hand-written fixed-step RK4 integrator (`method="rk4"` in `run_sim`), independent of
  `scipy.integrate.solve_ivp`. Cross-check test confirms RK4 and RK45 agree on apogee
  altitude/time and impact time to well within grid-resolution tolerance (apogee time diff
  ~2e-4 s, impact time diff ~4e-4 s, apogee altitude diff ~0.036 m at dt=1e-4s) — proves
  `dynamics.py` itself is correct, independent of which integrator drives it. RK45 remains the
  default; `run.py`'s output is byte-for-byte unchanged. Commit `53a3894`.

## Phase 1 — closed out
8/8 steps done. Everything currently in `main.tex` is implemented, tested, plotted. Next: Phase 2
(Steps 9-17), replacing constants with real models one at a time.

## Active modules
architect (done for now), developer (implementation, one roadmap step at a time). Everything
else (product, qa, security, documentation) — on hold, not needed for this scope unless it grows.

## Links
- `main.tex` — physics derivation (source of truth, user-maintained, re-check before every step)
- `architecture.md` — project structure + tech stack (approved)
- `roadmap.md` — step-by-step build plan, 22 steps across 3 phases (approved) — **this is the
  ticket list**, no separate task.md

## Decisions log
- 2026-09-19 — Architecture approved as recommended: z-down (NED-like) inertial frame,
  `scipy.integrate.solve_ivp` as integrator, fixed-signature `f(t, state, params)` seam for
  Phase 2 model swaps, quaternions for Phase 3 attitude, minimal pytest physics-sanity tests.
- 2026-09-19 — Physics confirmed by user: `ẑ_g` points down (`W = m·g·ẑ_g` correct as-is);
  positive `A_m` pitches the nose down (restoring/stabilizing moment).
- 2026-09-19 — CoG kept fixed for now (matches current `main.tex`); user will update `main.tex`
  with the CoG/inertia-shift derivation before Phase 2 Step 12 (propellant depletion).

## Known future main.tex updates needed (not blocking now)
- Aero force direction (`A_f`) is currently hard-coded against body axes — valid only nose-first;
  Step 9 (relative wind / angle of attack) needs a `main.tex` update to generalize this.
- CoG/inertia shift from propellant depletion — needed before Step 12.
- Thrust model (`§Models > Thrust`) is still a stub — needed before Steps 11/13.
