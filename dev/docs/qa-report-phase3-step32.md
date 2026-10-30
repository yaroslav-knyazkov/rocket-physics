# QA Report — Phase 3, Step 32 (3D integration harness + minimal 3D output)

## Кратко (RU)

- Независимая QA по Step 32 (`fa8d460`), все 8 пунктов задания оркестратора проверены.
- **Вердикт: PASS**, с одним minor-дефектом (не блокер).
- Пункт 1 (2D-путь не тронут): подтверждено `git diff` — 0 удалённых строк в `integrate.py`, обе
  вставки строго вне тел пяти событий/`run_sim`/`_run_rk4`/`_run_segmented_rk45`.
- Пункт 2: `tests/test_integrate.py` отдельно — 27/27, предупреждения те же, что и раньше.
- Пункт 3: сценарий 3D rk4-пина — чистый баллистический бросок (`Aero.S=0.0` по умолчанию,
  тяги нет), детерминирован и дёшев. Пин выбран корректно.
- Пункт 4: негативные контроли freeze-тестов реальны (без freeze состояние реально двигалось бы);
  «блендинг» на границе parachute_deploy (bit-exact только через 2 сэмпла) — объяснимый
  безобидный артефакт фиксированного шага RK4 на гладком предикате, не баг.
- **Пункт 5 — единственная находка (minor):** эмпирически (через monkey-patch `_s2d` на старую
  `arcsin`-версию без правки файлов) показано, что тест «пересечение вертикали» НЕ поймал бы
  баг SS37.0.4 — сценарий `_P` использует `Aero.S=0.0`, так что весь аэро-момент/сила тождественно
  нулевые и folding не влияет на динамику. Сам баг корректно пойман отдельным тестом
  `tests/test_forces3d.py`. Дефект — только в формулировке докстринга/заметок разработчика
  («would have failed hard before the fix» — неверно для этого теста), не в покрытии кода.
  Предложено: поправить комментарий (~2-3 строки), мерж не блокирует.
- Пункт 6: оба «accepted, not fixed» решения разработчика (code-review) подтверждены верными при
  независимой проверке кода.
- Пункт 7: полный прогон — **801 passed, 0 failed**, 812.64с, совпадает с цифрами разработчика и
  оркестратора.
- Пункт 8: докстринг `plot_trajectory_3d` про `altitude=-z` точен и достаточен.

---

## Scope

Commit under test: `fa8d460` ("Step 32 (Phase 3): 3D integration harness + minimal 3D output").
Ticket: `dev/docs/architecture-37-step32-3d-integration-harness.md` (SS37.2/SS37.3 decisions,
SS37.6 regression requirements, SS37.7 sub-step breakdown).
Developer notes: `dev/docs/step-32-progress-notes.md`.

Decisions to verify (not re-litigate): D-32.1=C (projection seam), D-32.2=S2 (`rk4`+`RK45` only),
D-32.3=O2 (minimal additive 3D output).

---

## 1. 2D path untouched (`integrate.py`) -- PASS

`git diff fa8d460~1 fa8d460 -- apps/sim/engine/integrate.py` shows **0 removed lines**
(`grep -c "^-[^-]"` = 0) and exactly 3 insertion-only hunks:
- `@@ -97,6 +97,14 @@` -- new imports only, above `class Result`.
- `@@ -106,6 +114,60 @@` -- `_project_identity`/`_events_for` inserted between `class Result` and
  `def _ground_event`, i.e. strictly before the first pinned function. The five event predicate
  bodies (`_ground_event`, `_apogee_event`, `_burnout_event`, `_rail_exit_event`,
  `_parachute_deploy_event`), `run_sim`, `_run_rk4`, `_run_segmented_rk45` are all byte-identical
  (0 removed lines is conclusive proof -- a body edit cannot exist without at least one removed
  line in a unified diff).
- `@@ -794,3 +856,287 @@` -- everything else (`run_sim_3d`, `_run_rk4_3d`, `_project_result_for_mach`)
  appended strictly after the pre-existing end of file.

Independently re-verified; matches the orchestrator's own spot-check and the developer's own claim.
`apps/sim/engine/forces3d.py` and `apps/sim/engine/dynamics3d.py` *do* have real body edits
(expected -- `_s2d`'s pitch recovery and `derivatives_3d`'s freeze branch are the whole point of
sub-steps 32.0/32.4), but neither file carries a 2D `np.array_equal` pin, so this is in scope and
correctly disclosed in the commit message / progress notes.

## 2. `tests/test_integrate.py` in isolation -- PASS

`python -m pytest tests/test_integrate.py -q` -> **27 passed**, 13 warnings, 181.63s. Warnings are
the same pre-existing `MachRangeWarning` diagnostics the file always emits (`rk45_seg` branches at
Mach 0.90/0.93 with the "constant" aero model) -- no new warning, no tolerance drift, output
matches the developer's own gate-run report. The 7 `np.array_equal` pins (D-77) are included in
this run and green.

## 3. The 3D `rk4` reference pin scenario (sub-step 32.3) -- PASS

`_RK4_PIN_P = with_solver(Params(weight=Weight(m=0.5, I=0.05)), method="rk4", dt=1e-2, t_max=10.0)`,
`theta0=45 deg, vx0=10, vz0=-20, omega0=0` (`tests/test_integrate3d.py:349-362`). Checked the
`Params` defaults directly (`apps/sim/engine/params.py`): `Thrust.motor_curve=""` (no motor file
loaded -> zero thrust) and, critically, `Aero.S=0.0` by default (not just `C_x/C_z/C_m=0.0`) --
`A_x = q*S*C_x`, `A_z = q*S*C_z` (`forces.py:197-198`), both identically `0.0` regardless of
anything else. So this really is a pure ballistic lob: gravity + the `rk4` stepper + the
quaternion machinery only, nothing else. That makes it:
- **Deterministic**: no scipy adaptive step-size search, no file I/O (no motor curve/aero table
  read), no floating-point-order-sensitive accumulation beyond the in-house `rk4`'s own fixed
  arithmetic, which `CLAUDE.md`/D-77 already treat as version-stable (unlike scipy's `RK45`).
- **Portable**: no dependency on `projects/examples/data/` fixtures, no network, no OS-specific
  path.
- **Cheap**: ~0.15 s wall time per run (`dt=1e-2` over a ~4 s flight), and the test runs it twice
  to confirm bit-for-bit determinism before the literal pin values were committed -- the right
  discipline for a brand-new pin.

This is a well-chosen pin scenario. No concerns.

## 4. Rail/parachute freeze negative controls (sub-step 32.4) -- PASS, with one documented artifact noted (not a defect)

Both new tests in `tests/test_integrate3d.py` genuinely prove the freeze does something:
- **Rail test** (`test_run_sim_3d_rail_freeze_holds_attitude_exactly_constant`): uses
  `misalign_deg=5.0` + `Inertia(model="tensor")` so a real, nonzero moment is available; asserts
  `q`/`omega` bit-exact while on the rail, **then explicitly asserts `omega` has moved away from
  zero 50 samples after rail exit** (line 480) -- a real negative control, not vacuous.
- **Parachute test** (`test_run_sim_3d_parachute_freeze_holds_attitude_exactly_constant`): uses
  `p.inertia.model == "none"` (prescribed-rate kinematics) with `omega0=0.3`, and explicitly
  asserts `q` is NOT close at `idx_dep` vs. the initial sample (line 519) -- proving `q` was
  actively rotating before deploy, so the post-freeze exact-constant assertion is not trivially
  true.

**Blending subtlety reviewed:** the documented 2-sample delay to bit-exactness after
`parachute_deploy` (`idx_dep`/`idx_dep+1` differ at 1 ULP, `idx_dep+2` on is exactly `0.0`) is a
real, benign numerical artifact, not a sign of a deeper bug. `forces.parachute_deployed` is a
smooth, RHS-evaluable predicate (not a scipy-refined root), so in a fixed-step `rk4` the single
step whose 4 stages (`k1..k4`) straddle the deploy crossing necessarily blends one or more
frozen-RHS evaluations with one or more unfrozen ones within that one step's weighted average --
by construction this cannot produce an exactly-zero result for that boundary step, only a very
small residual. This is the same discontinuous-smooth-predicate-in-a-fixed-step-RK4 mechanism the
2D `chuted` branch (`dynamics.py`) already has; this project has simply never pinned/measured it
at 1-ULP resolution on the 2D side, so there is no existing precedent test to cross-check against,
but the explanation is physically and numerically sound on its own terms, and it is accurately
documented in the test's own comment. Not a blocker. (Minor, optional follow-up: a matching
1-ULP-level test on the 2D `chuted`/`on_rail` branches would make this an A/B-confirmed pattern
rather than an isolated 3D observation -- backlog-worthy, not a defect.)

## 5. Verticality probe tests (sub-step 32.2) -- CONCERN (minor): docstring claim empirically false, but the real bug is caught elsewhere

**Checked independently, not taken on trust.** Did not just read the docstrings -- monkey-patched
`forces3d._s2d` back to the pre-fix `arcsin`-based `quaternion.to_euler` recovery in a scratch
script (no repo file touched) and re-ran the exact scenario of
`test_run_sim_3d_matches_run_sim_through_a_descent_that_crosses_vertical` (theta0=85 deg,
omega0=0.1 rad/s, ~66 s flight, crosses vertical repeatedly). **Result: the sin/cos comparison
still passes bit-for-bit under the pre-fix buggy `_s2d`** (`sin ok: True, cos ok: True`,
ground-event times agree to 1.3e-8 s). The docstring's claim ("this would have failed hard before
sub-step 32.0's fix", `tests/test_integrate3d.py:227`) is **not true for this test**.

**Root cause, traced:** the shared `_P` scenario (`tests/test_integrate3d.py:141-146`) sets
`aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0)` but does **not** set `Aero.S` (reference area), which
defaults to `0.0`. `A_x = q*S*C_x`, `A_z = q*S*C_z` (`forces.py:197-198`) are therefore both
identically `0.0` regardless of `alpha`/`theta`, and `moment_body_3d`'s `M_y` is `0.0` for the
same reason the scenario's own comment already gives for `C_z=C_m=0`. Since `_s2d`'s folded
`theta` is consumed **only** by `aero_force_body_3d`/`moment_body_3d` (via `flow_fb_coeffs_3d` ->
`aero.coefficients`), and both are unconditionally zero here, the fold bug has **zero** causal
path into this scenario's dynamics -- translation comes from gravity + quaternion-rotated thrust
(not through `_s2d`), and rotation comes from prescribed `omega` directly (`inertia.model=="none"`,
not through `_s2d` either). The same reasoning applies to the three parametrized
`theta0 in {85, 89, 90} deg` static tests (`test_run_sim_3d_matches_run_sim_near_the_old_singularity`)
-- doubly so there, since 85/89 deg sit *inside* `arcsin`'s valid range and 90 deg is the exact
boundary the old table itself measured as round-trip-exact, so those three would not have folded
even with a nonzero `S`.

**This is not a correctness gap in the shipped fix.** The actual SS37.0.4 bug *is* caught, directly
and unambiguously, by `tests/test_forces3d.py::test_s2d_recovers_pitch_without_arcsin_folding`
(round-trips 45/85/89.9/90/95/135/170/-135 deg through `_s2d` itself and asserts to `1e-12`) --
verified that 95/135/170/-135 deg are genuinely outside `arcsin`'s range and would fold under the
old code. That test is exactly what D-32.9 required ("the SS37.0.4 table itself becomes a test")
and it is correct and sufficient on its own.

**What SS37.9 risk 2 actually asked for** ("Verticality probe still needed after the fix... the
expected answer is 'no degradation' -- which has to be measured, not assumed") is a *different*
claim than "catches the bug" -- it is a *non-regression* probe for the harness-level equivalence
near the old singularity, and that is what these tests correctly measure and pass. The spec's own
intent is satisfied; only the **progress-notes' and in-test docstring's characterization**
("would have failed hard before the fix") is incorrect for the harness-level tests.

**Disposition: minor defect (documentation/traceability only, no code or test-coverage gap).**
Recommend the developer correct the misleading comment in
`tests/test_integrate3d.py:220-230` (and the matching claim in
`dev/docs/step-32-progress-notes.md`, sub-step 32.2 section) to say these tests measure
*no-degradation near the old singularity* (SS37.9 risk 2), and point to
`tests/test_forces3d.py` as the test that actually exercises the SS37.0.4 bug. No code change
needed; `~2` line comment fix.

## 6. "Accepted, not fixed" code-review findings -- AGREE with both dispositions

Read `apps/sim/engine/integrate.py` directly rather than trusting the developer's self-report.

1. **"Dead/unreachable code after a `return`" (the `_warn_if_mach_blind` body).** Confirmed false
   positive: `run_sim`'s own `return result` is at line 850, and lines 853-858 are simply
   `_warn_if_mach_blind`'s own, separate, pre-existing function body (unchanged by this diff), not
   trailing code inside `run_sim`. Agree: no action needed.
2. **Duplicated `_warn_if_mach_blind(...)` call per solver branch.** Confirmed by grep:
   `run_sim` calls it 3 times (lines 814, 819, 849 -- one per `rk4`/`rk45_seg`/`RK45` branch,
   pre-existing), `run_sim_3d` calls it 2 times (lines 1107, 1139 -- one per `rk4`/`RK45` branch,
   matching D-32.2/S2's scope). `run_sim_3d` is following `run_sim`'s own established
   one-call-per-branch convention exactly, not introducing new duplication. Agree: accepted, not
   a defect.

## 8. `plot_trajectory_3d`'s `altitude = -z` docstring claim -- PASS, clearly documented

Read `apps/sim/engine/plotting.py`'s new `plot_trajectory_3d` docstring and cross-checked against
`apps/sim/engine/gravity.py::altitude_agl`'s own docstring. The claim ("Altitude is `-z` directly,
NOT routed through `gravity.altitude_agl`... under the default `gravity_direction="parallel"`
`altitude_agl` is exactly `-y[Z]` anyway... exact for 'parallel' and NOT attempted for the curved-
ground variants") is accurate: `altitude_agl`'s own docstring states "Under the default
`gravity_direction = "parallel"` this is `-y[Z]` bitwise." The new function's docstring states the
exactness condition explicitly, names the out-of-scope case (curved gravity) explicitly, and points
at why (`run_sim_3d` untested against curved gravity, SS37.8). This is clear enough for a future
reader not to misuse it under a curved-gravity scenario -- no silent wrong-number risk. No runtime
guard (warning/assert) exists if someone *does* call it under curved gravity, but that is
consistent with this project's existing convention of docstring-only scope statements for additive,
minimal-output functions (D-32.3/O2's own framing), not a gap specific to this function. No defect.

## 7. Full suite, foreground wait -- PASS

`python -m pytest -q` -> **801 passed, 0 failed**, 75 warnings, 812.64s (0:13:32). All warnings are
the same pre-existing `MachRangeWarning`/`AeroRangeWarning` diagnostics (Mach-independent aero
model used above its credible range, aero table out-of-bounds held at edge values) -- none new,
none diff-related. Matches the developer's own final gate (801 passed) and the orchestrator's
independent 13-chunk re-run. No native access-violation flake hit on this run (the known Windows
`scipy`-internal flake, `CLAUDE.md`, is unrelated to this diff and did not reproduce here).

---

## Summary

| # | Checklist item | Verdict |
|---|---|---|
| 1 | 2D path untouched in `integrate.py` | PASS |
| 2 | `tests/test_integrate.py` isolated run | PASS (27/27, unchanged warnings) |
| 3 | 3D `rk4` pin scenario quality | PASS |
| 4 | Rail/parachute freeze negative controls + blending subtlety | PASS (artifact is benign) |
| 5 | Verticality probe tests actually catch the bug? | CONCERN (minor) -- see below |
| 6 | Two "accepted, not fixed" code-review dispositions | AGREE with both |
| 7 | Full suite | PASS (801/801, 0 failed) |
| 8 | `plot_trajectory_3d`'s `altitude=-z` docstring | PASS, clearly documented |

**Overall: PASS, with one minor, non-blocking defect.**

### Defect D-QA-32-1 (minor, documentation/traceability only)

- **Where:** `tests/test_integrate3d.py` lines ~220-230 (docstring of
  `test_run_sim_3d_matches_run_sim_through_a_descent_that_crosses_vertical`, and by extension the
  two neighbouring `near_the_old_singularity` tests), plus `dev/docs/step-32-progress-notes.md`'s
  sub-step 32.2 section ("this would have failed hard before sub-step 32.0's fix").
- **Steps to reproduce the finding:** monkey-patch `apps.sim.engine.forces3d._s2d` back to the
  pre-fix `arcsin`-based `quaternion.to_euler(q)[1]` recovery (no repo file edited -- patched the
  module attribute in a throwaway script) and re-run the exact scenario/assertions of the
  "crosses vertical" test. The sin/cos comparison still passes bit-for-bit.
- **Expected (per the test's own docstring):** the test fails against the pre-fix `_s2d`.
- **Actual:** the test passes identically, because the shared `_P` scenario has `Aero.S=0.0`
  (unset, defaults to zero), making `aero_force_body_3d`/`moment_body_3d` (the only consumers of
  `_s2d`'s folded `theta`) return `0.0` regardless of the fold -- the fold bug has no causal path
  into this scenario's dynamics.
- **Severity: minor.** No shipped-code defect and no real test-coverage gap: the SS37.0.4 bug is
  independently and correctly caught by
  `tests/test_forces3d.py::test_s2d_recovers_pitch_without_arcsin_folding` (direct round-trip at
  95/135/170/-135 deg, outside `arcsin`'s range). The harness-level verticality tests still have
  standing value as a *non-degradation* probe (SS37.9 risk 2's actual requirement: "the expected
  answer is 'no degradation' -- which has to be measured, not assumed"), which they correctly
  measure and pass. Only the stated *reason* for the test ("would have failed before the fix") is
  incorrect.
- **Suggested fix:** reword the docstring/comment to describe a non-degradation probe near the old
  singularity and cross-reference `tests/test_forces3d.py` as the test that exercises the actual
  bug. ~2-3 line comment change, no production code or test logic change needed. Does not block
  merge/acceptance of Step 32 on its own.

### Secondary observations (not defects, backlog-worthy)

- The 2-sample blending delay to bit-exactness after `parachute_deploy` (sub-step 32.4) is a real,
  benign, physically-explained numerical artifact (smooth predicate straddling an RK4 step's 4
  stages) -- correctly documented in the test's own comment. No equivalent 1-ULP-level test exists
  on the 2D `chuted`/`on_rail` branch to cross-confirm the same mechanism there; would be a cheap,
  nice-to-have confirmation, not required for this step.

<!-- STATUS marker removed below: all 8 checklist items reviewed, full suite independently
     re-run and confirmed 801/801, one minor defect filed (D-QA-32-1), no blockers. -->


