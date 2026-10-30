# Step 32 progress notes (developer)

## Кратко (RU)

- Рабочие заметки разработчика по Step 32 (3D integration harness), подшаги 32.0-32.5.
- Решения D-32.1=C, D-32.2=S2, D-32.3=O2 уже приняты пользователем, не пересматриваются.
- Полный прогон тестов на этой машине идёт заметно дольше ожидаемого (~190-900+ с), что
  соответствует задокументированной в CLAUDE.md ловушке "долгий полный прогон" — не
  считается провалом шага, если пины не сдвинулись.
- По состоянию на последнюю запись: см. секции ниже по каждому подшагу.

Spec: `dev/docs/architecture-37-step32-3d-integration-harness.md`.

---

## Sub-step 32.0 — fix `_s2d`'s pitch recovery (BLOCKING PREREQUISITE)

- **Files touched:** `apps/sim/engine/forces3d.py` (`_s2d`, module docstring), new
  `tests/test_forces3d.py`.
- **What:** replaced `quaternion.to_euler(q)[1]` (arcsin-based, folds at +-90 deg) with
  `atan2(-R[2,0], R[0,0])` on `quaternion.to_dcm(q)`, per D-32.9. No other line in `_s2d`
  touched (r/v/omega/M untouched). Added `import math` to forces3d.py.
- **TDD:** wrote `tests/test_forces3d.py` first (round-trip table 45/85/89.9/90/95/135/170/
  -135 deg + a direct atan2 cross-check + an "other fields unchanged" test), confirmed red
  against the pre-fix `_s2d` (95/135/170/-135 deg folded as predicted), then applied the fix,
  confirmed green.
- **Gate run 1 (point tests):** `python -m pytest tests/test_forces3d.py tests/test_dynamics3d.py tests/test_integrate.py -q`
  -> **38 passed** (3 new + 8 dynamics3d + 27 integrate), 186.26s. No `np.array_equal` pin in
  `test_integrate.py` moved (27 tests, all green, output matches pre-existing warnings only).
- **Gate run 2 (full suite):** `python -m pytest -q` -> **776 passed**, 766.54s (0:12:46), 57
  warnings (all pre-existing `MachRangeWarning`/`AeroRangeWarning` diagnostics, unrelated to
  this diff). No failures. 2D pins (`tests/test_integrate.py`'s 27 tests / 7 `np.array_equal`
  assertions) included in this run and green.
- **Pin risk:** none -- confirmed no `np.array_equal` assertion exists on the 3D path prior to
  this change, and `forces3d` has no importer on the 2D side (verified by grep: only
  `dynamics3d.py` and the new test import it).
- **Status: DONE.** Ready for orchestrator commit.

---

## Sub-step 32.1 -- the projection seam and the event factory

- **Files touched:** `apps/sim/engine/integrate.py` (additive only: `_project_identity`,
  `_events_for`, placed above the five event functions, right after the `Result` NamedTuple),
  new `tests/test_integrate3d.py` (3 tests).
- **What:** `_project_identity(y) -> y` (true no-op). `_events_for(project)` wraps each of the
  five module-level event predicates so the state is first passed through `project`, carrying
  over `.terminal`/`.direction`. No existing function body edited; `_ground_event` /
  `_apogee_event` / `_burnout_event` / `_rail_exit_event` / `_parachute_deploy_event` /
  `run_sim` / `_run_rk4` / `_run_segmented_rk45` are byte-identical (confirmed by inspection --
  the new block was inserted as a pure addition, nothing inside those functions touched).
- **Tests (`tests/test_integrate3d.py`, new file):**
  1. `_project_identity` returns the exact same object (`is`, not just `==`) -- a true no-op.
  2. `_events_for(_project_identity)` matches the five module-level event functions
     attribute-for-attribute (`.terminal`/`.direction`) and value-for-value at a handful of
     representative `(t, y, p)` triples, including points near each event's own zero crossing.
  3. A non-identity projection (`_project_shift`, shifts `VZ` by +100) is actually applied --
     proves the wrapper isn't silently degrading to identity regardless of `project`.
- **Gate run 1 (point tests):** `python -m pytest tests/test_integrate.py tests/test_integrate3d.py -q`
  -> **30 passed** (27 + 3), 175.09s. 2D pins unmoved.
- **Gate run 2 (full suite):** `python -m pytest -q` -> **779 passed** (776 + 3 new seam tests),
  775.07s (0:12:55), same 57 pre-existing warnings. No failures.
- **Pin risk:** none -- new module-level names only, no pinned function body edited.
- **Status: DONE.**

---

## Sub-step 32.2 -- `run_sim_3d`, RK45 path, with eager validation

- **Files touched:** `apps/sim/engine/integrate.py` (new imports `dynamics3d, forces3d, inertia,
  quaternion, state3d`; `run_sim_3d`, `_project_result_for_mach` (D-32.7), a temporary
  `_run_rk4_3d` stub that raises `NotImplementedError` pointing at sub-step 32.3 -- no test
  reaches it yet), `tests/test_integrate3d.py` (+15 tests).
- **What:** first end-to-end 3D flight to the ground, RK45 path only (`rk4` dispatch wired but
  stubbed, see above). Reuses `Result`/`_events_for(forces3d._s2d)` unchanged. Six eager
  `ValueError` guards (D-32.6 items 1-3 + 5, D-32.2's two independent solver-path checks),
  checked in order: actuator model (reused verbatim from `run_sim`) -> `sample_rate_hz > 0.0`
  -> `method == "rk45_seg"` -> `p.roll.model != "none"` -> `p.weight.m_d is not None` ->
  `inertia.validate(p.inertia, roll=p.roll)` (called last so the roll guard above it has
  already forced `roll.model == "none"` by the time it runs, making `inertia.validate`'s own
  roll cross-check inert here -- intentional, not a gap).
- **Import-cycle check:** `python -c "import apps.sim.engine.integrate"` -> `ok`. `forces3d`
  does not import `integrate` (confirmed by inspection, SS37.7/32.2's own note); acyclic.
- **Verticality probe (SS37.9 risk 2, "not optional"):** found a good scenario by direct
  experimentation (see notes below) rather than guessing: the `_P`-style zero-net-moment
  scenario (on-axis thrust, `C_z=C_m=0.0` so `M_y` is identically zero for the WHOLE flight
  regardless of theta/l1/l2 -- same property `tests/test_dynamics3d.py`'s own `_P` relies on)
  at `theta0 in {85, 89, 90} deg` (static-attitude equivalence) plus a separate dynamic
  scenario at `theta0=85 deg, omega0=0.1 rad/s` over its ~66 s flight, which crosses vertical
  several times during ascent AND descent -- asserted via `sin`/`cos` of theta (SS37.6.2: 2D's
  theta is unwrapped, 3D's `atan2` recovery is wrapped at +-180 deg, so raw-theta equality is
  the wrong assertion once theta leaves one period). All equivalence checks passed at
  `rtol=1e-7, atol=1e-4` (trajectory) / `rel_tol=1e-6` (event times) / `atol=1e-4` (sin/cos).
- **Tests added (`tests/test_integrate3d.py`, +15):**
  - `test_run_sim_3d_matches_run_sim_planar_rk45` (SS37.6.1 test 1, theta0=45 deg)
  - `test_run_sim_3d_matches_run_sim_near_the_old_singularity[85.0/89.0/90.0]` (SS37.9 risk 2,
    parametrized)
  - `test_run_sim_3d_matches_run_sim_through_a_descent_that_crosses_vertical` (SS37.9 risk 2,
    dynamic probe; also asserts the scenario itself actually crosses vertical, so a future
    scenario edit that stops doing so fails loudly)
  - `test_run_sim_3d_out_of_plane_components_stay_exactly_zero` (SS37.6.1 test 2, bit-exact)
  - `test_run_sim_3d_terminates_on_ground_impact_not_t_max` (SS37.6.1 test 3)
  - 5 eager-validation tests (SS37.6.1 test 8): inadmissible inertia tensor, 2D roll model on,
    3D variable-mass model on, sampled-data/`rk45_seg` (both conditions in one test), unregistered
    actuator model -- each `pytest.raises(ValueError, match=<substring>)`.
- **Gate run 1 (point tests):** `python -m pytest tests/test_integrate3d.py -q` -> **15 passed**,
  1.34s (fast -- RK45/adaptive, short flights, no `dt`-costly fixed-step work yet).
- **Gate run 2 (full suite):** `python -m pytest -q` -> **791 passed** (779 + 12 new), 790.24s
  (0:13:10), 69 warnings (12 new `MachRangeWarning`s from the new equivalence tests, same
  pre-existing diagnostic, harmless -- plus the 57 pre-existing ones). No failures.
- **Pin risk:** none on the 2D side. No 3D pin exists yet either (that is sub-step 32.3).
- **Status: DONE.**

---

## Sub-step 32.3 -- `run_sim_3d`, `rk4` path + the committed 3D reference pin

- **Files touched:** `apps/sim/engine/integrate.py` (`_run_rk4_3d`, replacing the 32.2 stub --
  the ~55-line mirror of `_run_rk4:364-418`'s crossing-detection block, plus the D-32.4
  quaternion-renormalisation step after each accepted RK4 step), `tests/test_integrate3d.py`
  (+3 tests).
- **What:** fixed-step 3D RK4 with crossing detection (apogee/ground/burnout/rail_exit/
  parachute_deploy, each mirroring `_run_rk4`'s own arithmetic verbatim but reading the state
  through `forces3d._s2d`) + the first `np.array_equal` pin the 3D path has ever had.
- **Pin scenario (found by direct experimentation, not guessed):** a pure ballistic lob --
  `Weight(m=0.5, I=0.05)`, no thrust, no aero, no rotation (`theta0=45 deg`, `vx0=10, vz0=-20`,
  `omega0=0`), `method="rk4", dt=1e-2, t_max=10.0`. Chosen for determinism and speed (~0.15s
  wall time per run; a motor-curve scenario at `dt=1e-2`-`1e-3` would cost an order of magnitude
  more for no extra pin value). Confirmed bit-for-bit deterministic across two consecutive runs
  before committing the literal `y_final`/`t_final`/`events` values into the test.
- **Tests added (+3):**
  - `test_run_sim_3d_rk4_matches_committed_reference_trajectory` (SS37.6.1 test 4): runs the
    pin scenario TWICE, asserts `np.array_equal(y_final)` + `t_final` + `events` both times.
  - `test_run_sim_3d_rk4_quaternion_norm_is_exact_at_every_sample` (SS37.6.1 test 7, `rk4`
    half): `max(abs(norm(q) - 1)) < 1e-15` -- measured `0.0` exactly on the pin scenario (D-32.4's
    renormalisation keeps it exact, not merely bounded).
  - `test_run_sim_3d_rk45_quaternion_norm_drift_is_bounded` (SS37.6.1 test 7, `RK45` half): a
    genuinely rotating scenario (nonzero `omega0`, tensor inertia model, `C_m != 0`) through
    ground impact at `rtol=1e-11, atol=1e-13` -- measured drift `2.84e-11`, comfortably under
    the `1e-9` bound; the *default* solver tolerance was tried first and measured `8.8e-9`
    (over the bound), so the tighter tolerance is load-bearing for this test, not decorative --
    matches `tests/test_dynamics3d.py`'s own precedent for comparisons at this tightness.
- **Gate run 1 (point tests):** `python -m pytest tests/test_integrate.py tests/test_integrate3d.py tests/test_dynamics3d.py tests/test_forces3d.py -q`
  -> first attempt crashed with the KNOWN flaky Windows native access-violation inside scipy's
  compiled RK path (CLAUDE.md: "Redre native crash... Flaky, not diff-related"); re-run ->
  **56 passed** (27+18+8+3), 185.24s. Not treated as a step failure per that documented flake.
- **Gate run 2 (full suite):** `python -m pytest -q` -> **794 passed** (791 + 3 new), 778.07s
  (0:12:58), same warning pattern as before. No failures.
- **Pin risk:** none existing (no `np.array_equal` pin edited or moved); this sub-step CREATES
  the first 3D pin (`rk4`-based, version-stable per CLAUDE.md -- the `RK45` path is
  deliberately never pinned, only tolerance-asserted).
- **Status: DONE.**

---

## Sub-step 32.4 -- rail and parachute attitude freeze in 3D

- **Files touched:** `apps/sim/engine/dynamics3d.py` (`_e_rail_3d` helper; `derivatives_3d`
  gains the freeze branch per D-32.5; module docstring updated), `tests/test_integrate3d.py`
  (+2 tests). `tests/test_dynamics3d.py` NOT touched -- its existing 8 tests are the gate
  (unreachable branch, defaults off), no new RHS-level assertion needed on top of the
  harness-level tests below.
- **What:** `derivatives_3d` now computes `on_the_rail`/`chuted` via `dynamics.on_rail`/
  `forces.parachute_deployed` reused verbatim on one shared `forces3d._s2d(y)` projection, and
  zeroes BOTH `dydt[Q]` and `dydt[OMEGA]` when either is true (the 3D twin of 2D's
  `dydt[THETA]=0`/`dydt[OMEGA]=0`). Translation is NOT frozen: on the rail, the already-computed
  inertial force `F_i` is projected onto the exact 3D rail embedding `_e_rail_3d(p) = (cos eps,
  0, -sin eps)` (built from `dynamics._e_rail(p)` by inserting a zero y-component); under
  canopy, `forces.parachute_drag_inertial` is evaluated on the same 2D projection and embedded
  `(Fx, 0, Fz)`, ADDED to `F_i` (mirrors 2D's `a_chute = (F_i + F_chute)/m` exactly, not routed
  through it). `domega_dt`/`A_b` are computed unconditionally (same shape the 2D RHS has always
  had: the moment is computed every call, only the unconstrained branch uses it) so the
  bit-for-bit-unchanged claim for the default (`L_rail=0`, `recovery off`) case rests on the
  freeze condition being false, not on skipped work.
- **Import-cycle check:** `dynamics3d.py` now also imports `dynamics, forces` (2D modules) on
  top of its existing `forces3d` import. `python -c "import apps.sim.engine.dynamics3d; import apps.sim.engine.integrate"`
  -> `ok`. Neither `dynamics.py` nor `forces.py` imports `dynamics3d`/`integrate` (confirmed by
  inspection) -- acyclic.
- **Negative-control discipline (both new tests):** each test first proves the scenario WOULD
  rotate without the freeze (a real moment from nozzle misalignment + tensor inertia for the
  rail case; a nonzero prescribed `omega` for the parachute case) before asserting it stays
  exactly constant once frozen -- otherwise an exact-zero assertion could pass vacuously if the
  moment/rotation happened to be zero anyway.
- **One blending subtlety found while writing the parachute test** (not anticipated, found by
  direct measurement): the single `rk4` step whose four stages straddle the deploy crossing
  blends frozen and unfrozen RHS evaluations across `k1..k4` (same smooth-predicate mechanism
  `dynamics.py`'s own 2D `chuted` branch already has -- `forces.parachute_deployed` is a
  continuous function of the trial state at each stage, not a refined event), so bit-exact
  equality holds only from TWO samples after the crossing (`idx_dep` and `idx_dep+1` differ at
  the 1-ULP level; `idx_dep+2` onward is exactly `0.0` -- measured directly, documented in the
  test's own comment). The rail test has no equivalent issue because its exact-constant window
  is sliced strictly BEFORE the exit crossing by construction.
- **Tests added (+2):**
  - `test_run_sim_3d_rail_freeze_holds_attitude_exactly_constant` (SS37.6.1 test 5): `q`/`omega`
    bit-exact while on the rail (negative control: a genuine moment is available via
    `misalign_deg=5.0` + `Inertia(model="tensor")`), moves after exit, 2D `rail_exit` time
    matches to `rel_tol=1e-6`.
  - `test_run_sim_3d_parachute_freeze_holds_attitude_exactly_constant` (SS37.6.1 test 6): `q`
    bit-exact from 2 samples after `parachute_deploy` (negative control: `omega0=0.3` actively
    rotates `q` before deploy under `p.inertia.model=="none"`'s prescribed-rate kinematics),
    descent rate matches the 2D terminal value to `rel_tol=1e-9`.
- **Gate run 1 (point tests):** `python -m pytest tests/test_integrate.py tests/test_integrate3d.py tests/test_dynamics3d.py tests/test_forces3d.py -q`
  -> **58 passed** (27+20+8+3), 191.23s. `tests/test_dynamics3d.py` 8/8 unchanged (freeze branch
  unreachable with defaults, confirmed). Sub-step 32.3's `rk4` pin re-verified unmoved (same
  run, same file).
- **Gate run 2 (full suite):** `python -m pytest -q` -> **796 passed** (794 + 2 new), 785.94s
  (0:13:05). No failures.
- **Pin risk:** low, 3D side only, per the ticket's own framing -- the 32.3 `rk4` pin is the
  gate (it must not move; it did not).
- **Status: DONE.**

---

## Sub-step 32.5 -- minimal 3D output (D-32.3/O2)

- **Files touched:** `apps/sim/engine/plotting.py` (+3 functions: `plot_ground_track_3d`,
  `plot_trajectory_3d`, `plot_attitude_history_3d` -- all additive, existing functions
  untouched), `apps/sim/engine/report.py` (+1 function: `flight_summary_3d` -- additive,
  `flight_summary` itself untouched), new `tests/test_plotting3d.py` (+3 tests),
  `tests/test_report.py` (+2 tests).
- **What:** the roadmap's original Step 32 title ("3D output and regression"). All three new
  plotting functions reuse `_dense_time_grid` verbatim (layout-agnostic: reads only
  `r.events`/`r.t`/`r.raw.sol`). `plot_trajectory_3d` uses `altitude = -z` directly rather than
  routing through `gravity.altitude_agl` (which expects a 2D-shaped state) -- documented in the
  function's own docstring as exact only under `gravity_direction="parallel"`, matching
  `run_sim_3d`'s own out-of-scope note on curved gravity. `plot_attitude_history_3d` is the one
  place `quaternion.to_euler`'s "plotting-style output only" contract (restored by sub-step
  32.0/D-32.9) is deliberately exercised. `flight_summary_3d` mirrors `flight_summary` almost
  line-for-line, with every state read routed through `forces3d._s2d` first -- the same
  projection `run_sim_3d`'s own events/Mach diagnostic already use (D-32.1/C, D-32.7); the
  3D `static_margin_cal`/`cm_slope_series`/`stability_check`/`sweep` twins are deliberately
  NOT added (O3 rejected on correctness grounds, SS37.3/SS37.8 -- they rest on `C_z`/`C_m`
  slopes that through `_s2d` would be a planar number wearing a 3D label).
- **Acceptance detail (per the ticket):** `plot_ground_track_3d` on a planar run gives a
  dataseries with `y` bit-exact `0.0` and `x` strictly monotonically increasing -- asserted on
  the data, not the figure.
- **One tolerance finding (not anticipated, found by running the test):** at `Params`'s DEFAULT
  solver tolerance (`rtol=1e-8, atol=1e-10`), `flight_summary`/`flight_summary_3d`'s
  independently-integrated apogee altitudes differed by ~2.7e-6 relative -- just over a naive
  `1e-6` comparison tolerance, a numerical-integration dense-output-grid artifact (two separate
  adaptive solves), not a bug. Fixed by tightening the comparison scenario's solver tolerance
  to `rtol=1e-11, atol=1e-13`, the same precedent `tests/test_integrate3d.py`'s own equivalence
  tests already use for exactly this reason.
- **Gate run 1 (point tests):** `python -m pytest tests/test_plotting.py tests/test_plotting3d.py tests/test_report.py -q`
  -> **19 passed** (10+3+6), 10.68s.
- **Gate run 2 (full suite):** `python -m pytest -q` -> **801 passed** (796 + 5 new), 800.79s
  (0:13:20), 75 warnings (all the same pre-existing `MachRangeWarning`/`AeroRangeWarning`
  diagnostics). No failures.
- **Pin risk:** none (additive functions only; `report.py`'s existing `flight_summary` and the
  sweep/stability functions are not edited; `plotting.py`'s four existing functions are not
  edited).
- **Status: DONE.**

---

## code-review (low effort, run before handoff per project rule)

Ran against the full diff. Two findings, both reviewed and dispositioned:

1. `_warn_if_mach_blind(result, stacklevel=4)` inside `_warn_if_mach_blind`'s own body (line
   ~858) flagged as "dead/unreachable code after a `return`" -- **false positive**, confirmed
   by re-reading the file directly: lines 853-858 are the normal, pre-existing body of the
   `_warn_if_mach_blind` function itself (unchanged by this diff), not code trailing `run_sim`'s
   own `return result` one function up. No action needed.
2. `run_sim_3d` calls `_warn_if_mach_blind(_project_result_for_mach(result))` once per branch
   (`rk4`/`RK45`) -- flagged as minor duplication. **Accepted, not fixed**: this exactly mirrors
   `run_sim`'s own existing three-call-site pattern (one call per branch:
   `rk4`/`rk45_seg`/`RK45`), so it is this file's established convention, not new duplication
   introduced by this diff.

No correctness bugs found in `dynamics3d.py`, `forces3d.py`, `plotting.py`, `report.py`, or the
rest of `integrate.py`.

---

## Final status

All six sub-steps (32.0-32.5) done, each with its own point-test gate and full-suite gate
green, in order, no 2D pin ever moved (`tests/test_integrate.py`'s 27 tests / 7
`np.array_equal` assertions), the 3D `rk4` pin created at sub-step 32.3 unmoved through 32.4
and 32.5. Final full suite: **801 passed, 0 failed**, 800.79s. One flaky, known,
diff-unrelated native access-violation crash hit once (sub-step 32.3's first point-test
attempt) and cleared on re-run, per the documented CLAUDE.md flake.

**Noted, not acted on (flag for the orchestrator):** `git status` at the end of this session
shows `projects/data/README.md` deleted and an untracked `projects/fx27/` directory, neither of
which this session touched (verified: no `Write`/`Edit` call in this session referenced
`projects/`). These were not present in the git-status snapshot given at the start of this
session either. Likely a parallel session or a sync artifact (CLAUDE.md's Yandex.Disk-sync
caveat) -- flagging per the project's git-safety discipline rather than silently leaving it for
a future commit to pick up by accident.

<!-- marker removed: sub-steps 32.0-32.5 all DONE, full suite green at every gate -->
