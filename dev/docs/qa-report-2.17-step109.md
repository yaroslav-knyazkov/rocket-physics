# QA Report — Step 109 (Phase 2.17): 2D roll dynamics with a reaction wheel

## Кратко (RU)

- **Вердикт: PASS.** Независимая проверка всех заявленных изменений Step 109 (развязанная 2D-степень свободы крена + реактивный маховик) не нашла дефектов.
- Сверка `git diff --stat` с собственным списком файлов тикета — совпадение без остатка; код во всех 6 исходных файлах (`sim/state.py`, `sim/roll.py`, `sim/dynamics.py`, `sim/integrate.py`, `sim/params.py`, `configs/schema.py`/шаблон) побайтово соответствует спеке.
- **Пробел №1 (байт-в-байт CSV до/после) закрыт буквально**, не через прокси: создан временный `git worktree` на HEAD (до Step 109, без касания рабочего дерева), прогнан `run.py` там и в текущем дереве — CSV идентичны (MD5 совпадает).
- **Пробел №2 (3 «протухших» пина)** — все три правки (`test_forces.py`, `test_integrate.py`, `test_actuator.py`) проверены на сохранение исходного смысла теста; особо проверен `test_actuator.py` — переписанный тест защищает тот же инвариант («в плоском векторе состояния нет лишнего от актуатора»), а не просто подогнан под прохождение.
- Физика (сохранение момента, насыщение маховика, развязка crena/тангажа под `rk4`) пересчитана самостоятельно с нуля — ошибка сохранения момента 1.7e-18 (на 3 порядка туже требования тикета), насыщение совпадает с замкнутой формой до 6 знаков, развязка под rk4 — побитовое совпадение.
- Полный прогон тестов самостоятельно: **780 passed, 0 failed** — совпадает с самоотчётом разработчика.
- LaTeX-диф (5 файлов) — целиком совпадает с тем, что архитектор уже написал по §109.8; разработчик не добавил ничего сверх этого.
- Побочное наблюдение (не дефект Step 109): во время сессии параллельный процесс добросил неотслеживаемый файл `rocket-3d.tex` в общее рабочее дерево — не трогает ничего из Step 109, просто для информации оркестратора.

## Scope

Independent verification of uncommitted Step 109 changes on branch `feature/sim-paper-alignment`, against `dev/docs/task-109-roll-reaction-wheel.md`. No commits made; read-only git inspection only.

## 1. File-list audit (git diff --stat vs §109.6/§109.9 ticket list)

`git status --porcelain` / `git diff --stat` against the ticket's own file list (§109.6, §109.9, §109.11 DoD checklist):

Tracked modified: `configs/rockets/_TEMPLATE_rocket.py`, `configs/schema.py`, `sim/dynamics.py`, `sim/integrate.py`, `sim/params.py`, `sim/state.py`, `tests/test_actuator.py`, `tests/test_forces.py`, `tests/test_integrate.py`, plus 5 LaTeX files (`appendix.tex`, `assumptions.tex`, `backlog.tex`, `models.tex`, `other-dynamics.tex` — these are the architect's own pre-existing uncommitted LaTeX changes per §109.8, not developer work).

New untracked: `sim/roll.py`, `tests/test_roll.py` (both expected), plus doc files `dev/docs/task-109-roll-reaction-wheel.md` (the ticket itself), `dev/docs/qa-report-2.17-step109.md` (this report), and three files unrelated to Step 109 (`dev/docs/task-30-3d-rotational-dynamics.md`, `dev/docs/latex/research/3d-readiness-proposal.md`, `dev/docs/latex/research/model-development-candidates.md`, `docs/`) — these appear to be artifacts of a different/concurrent research pass, not this developer's work; they touch no tracked Step-109 file and are flagged only for completeness, not as a defect.

**Result: PASS.** Exactly the files the ticket names were touched; nothing outside the list changed; no claimed file is missing a change (verified `sim/roll.py` and `tests/test_roll.py` exist and are non-empty, see below).

## 2. Per-file diff review against spec text

Read full diffs for every tracked file and compared line-by-line against the ticket's literal code blocks:

- `sim/state.py`: `GAMMA/OMEGA_X/OMEGA_W = 7, 8, 9`, `N_BASE=7`/`N_ROLL=10`, `width(p)`, `to_vector(s,p)` — byte-for-byte match to §109.5's code block. Existing `range(7)` line untouched.
- `sim/roll.py`: all 8 public functions present (`aero_moment_x`, `wheel_torque`, `wheel_momentum`, `wheel_saturated`, `airframe_inertia`, `known_roll_models`, `known_roll_laws`, `derivatives_roll`), 3 laws (`_no_torque`/`_rate_null`/`_angle_hold`), both clamps (two-sided torque, one-sided speed) — matches §109.4 exactly, including the division-free aero form.
- `sim/dynamics.py`: `dydt = np.zeros(width(p))`, predicates hoisted (`on_the_rail`/`chuted`/`attitude_frozen`) exactly as §109.6.2's code block, roll block appended after `dydt[M] = dm_dt` matching §109.6.3 verbatim (including the one-sided freeze-only-airframe / wheel-keeps-running logic). Confirmed `sim/roll.py` is not imported by anything it shouldn't be and does not import `sim.dynamics` (checked — only imports `sim.state`).
- `sim/integrate.py`: all three `y0 = np.array(s0, dtype=float)` sites replaced with `y0 = to_vector(s0, p)` (confirmed at `_run_rk4`, `_run_segmented_rk45`, `run_sim`'s RK45 path). Eager validation block matches §109.7.2 verbatim, including the load-bearing ordering (model check before law/inertia checks). `Result.y` docstring comment fixed from stale "(6, N)" to "(width, N)".
- `sim/params.py`: `Roll` dataclass matches §109.3.1 verbatim (all defaults, including `inf` for `tau_max`/`omega_w_max`); `Aero.C_l`/`C_l_p` match §109.3.2; `Params` docstring group-count note updated; `roll` field registered.
- `configs/schema.py` + `_TEMPLATE_rocket.py`: `Roll` imported and wired onto `Rocket`, `assemble()` passes `roll=sc.rocket.roll`, template documents every field REQ/OPT with units — matches §109.7b.

**Result: PASS.** No deviation found between code and the ticket's literal specification in any of the six source files.

## 3. Verification of the 3 self-flagged "stale structural pin" edits (gap #2)

- `tests/test_forces.py` (`y0 = np.array(s0)` → `to_vector(s0, p)` at the `_buggy_derivatives`/`solve_ivp` site): correct and necessary — `_buggy_derivatives` is a reconstructed pre-fix 7-wide function; feeding it a bare `np.array(s0)` would now be 10-wide (State grew 3 fields) and mismatch `solve_ivp`'s y0/dydt shapes. `p.roll.model` defaults to "none" at this site, so `to_vector` returns the same 7 values as the old `np.array(s0)` — bit-for-bit preserved. Confirmed correct.
- `tests/test_integrate.py` (`np.array(s0)` → `to_vector(s0, p)` in `test_rk45_seg_degenerate_t_max_zero_does_not_crash_raw_sol`): same reasoning, same correctness — `r.raw.sol(t)` stays 7-wide, comparison needs a width-matched array. Confirmed correct.
- `tests/test_actuator.py::test_state_vector_length_is_unchanged_by_the_actuator` — **checked the original intent directly** (docstring, pre- and post-edit). The test protects: "the actuator's rate/range/delay state lives entirely in `AirbrakeHold`'s `prev`, never in the integrated state vector — the FLAT vector the integrator sees stays 7 components." The original assertion `len(State._fields) == 7` was a *proxy* for that (true only because `State` happened to have exactly 7 fields at the time). Step 109 breaks the proxy (`State` now has 10 fields) without breaking the actual invariant. The rewrite — `assert p.roll.model == "none"`, `assert width(p) == 7`, `assert len(to_vector(_launch_state(), p)) == 7` — checks the real invariant directly (the flat vector the integrator actually sees, under the project's own default), not the NamedTuple's raw arity. This is a genuine improvement, not a rewrite-to-pass: it would still fail if a future actuator change leaked state into the flat vector, which is what the test existed to catch. **Confirmed correct and intent-preserving.**

Additionally audited (ticket's own table, sites it flagged as "harmless if only indexed by name" and not requiring an edit): `tests/test_forces.py:958`, `tests/test_qa_phase217_m1.py:54`, `tests/test_control.py:96/118/262/394-396/493/587` — all construct `np.array(State(...))`, now 10-wide by construction (State's new defaults). Grepped all three files for `solve_ivp`/`len(y)`/`.shape` — zero hits. Every one of these arrays is only ever indexed by the named index constants (`M`, `X`, etc.) or passed to functions (`derivatives`, `aero_force_body`, `flow_state`) that do the same. None is length-compared or fed into `solve_ivp`. The developer's decision to leave these untouched is correct — no latent defect found.

**Result: PASS.** All 3 edits verified to preserve original test intent; the untouched "harmless" sites independently re-verified harmless.

## 4. Gap #1 — the literal byte-identical CSV check (§109.10.3.3), actually performed

The developer's proxy argument ("780 pins passed unchanged") is reasonable circumstantial evidence but is not the same claim as §109.10.3.3's literal one, and the ticket explicitly calls for the literal check. Performed it directly, without touching the working tree:

1. `git worktree add --detach <scratchpad>/baseline-wt HEAD` — HEAD (`dc1a6bf`, "QA: Phase 2.17 Step 108 report... PASS") is the true pre-Step-109 state, since every Step 109 change is uncommitted. A detached worktree checks out a second, independent copy of the tracked files at that commit into a path outside the project tree (scratchpad) — it does **not** touch a single file in the working tree being reviewed, and nothing in it is a destructive git op (no reset/checkout--/clean/stash).
2. Ran `python run.py` in that clean baseline worktree → `output/trajectory.csv` (2001 lines, demo scenario, roll untouched since it didn't exist yet).
3. Ran `python run.py` in the current working tree (with every uncommitted Step 109 change in place, `roll.model` still defaulting to `"none"`) → `output/trajectory.csv`.
4. `diff` reports **zero differences**; MD5 of both files is identical (`4262f92e09b710696d311bd1589525e9`). Console summary numbers (apogee altitude, apogee time, max speed, impact time, the two sweep tables) are also identical line-for-line.
5. Removed the worktree (`git worktree remove --force <path>`) immediately after; confirmed via `git status`/`git worktree list` that the main working tree's uncommitted changes were untouched throughout and after.

**Result: PASS — literal check performed, true byte-identity confirmed.** This supersedes the proxy argument entirely; no "is the proxy sufficient" judgment call is needed since the direct check was both practical and clean (the worktree mechanism made "avoid disturbing the working tree" free, not a tradeoff).

**Unrelated observation (not a Step 109 defect):** during this session a concurrent process added a new untracked file, `dev/docs/latex/sections-ai/rocket-3d.tex`, to the shared working tree (absent at session start, present by the time of this check) — evidently a parallel agent's Step-30/3D research output. It does not modify any tracked file and is outside Step 109's file list entirely; flagged for the orchestrator's awareness per `CLAUDE.md`'s guidance to recheck `git status` after background activity, not as a finding against this developer's work.

## 5. Independent recompute of acceptance checks (§109.10.1, §109.10.2, §109.10.4)

Wrote a standalone script (not reusing `tests/test_roll.py`) reproducing the exact scenarios from the ticket and recomputed from scratch:

- **§109.10.1 momentum exchange** (`model="wheel"`, `C_l=C_l_p=0`, `law="angle_hold"`, `gamma_cmd=0.5`, `I_x=0.02`, `I_w=2e-4`, `kp=0.01`, `kd=0.002`, at rest): `max |I_x*omega_x + h_w|` over the whole flight = **1.73e-18** — three orders tighter than the ticket's own "a few ×1e-12" bound. No linear drift (checked at t=0, t/3, t/2, t_end — all ~0 or exactly 0), ruling out a sign error in eq. (2)/(3); no jump, ruling out a clamp misfiring. `omega_x` and `h_w` opposite-signed once significant, confirmed.
- **§109.10.2 saturation**: same setup, `omega_w_max=50`. The limit is reached (`max|omega_rel| = 50.0000094`, essentially exactly the bound given integration tolerance). `omega_x` plateaus at **0.500000094**, matching the closed-form prediction `I_w*omega_w_max/I_x = 0.5` to 6 significant figures.
- **§109.10.4 decoupling under rk4**: reran the Test-6 scenario independently (`rk4`, `dt=0.01`, nonzero initial `gamma/omega_x/omega_w`, nonzero `kd`): `r_off.y` shape `(7, 201)`, `r_on.y[:7]` shape `(7, 201)`, `np.array_equal` → **True**, max abs diff → **0.0**. Exact bit-identity confirmed independently.
- **width(p) for every registered config**: enumerated `configs/rockets/` programmatically (only `demo.py` is registered besides the `_TEMPLATE_` file, which is not importable as a config) — `demo.py`'s `ROCKET.roll.model == "none"` → `width(p) == 7`. No config anywhere enables roll, matching §109.7b's claim.

**Result: PASS** on all four independently-recomputed checks; no discrepancy from the developer's reported numbers.

## 6. Full suite — independent re-run

`python -m pytest -q`, `run_in_background`, polled in capped loops (per `CLAUDE.md`'s ~240 s/call rule, never idle-waited on a notification):

```
780 passed, 56 warnings in 693.73s (0:11:33)
```

**Exact match** to the developer's self-reported "780 passed, 0 failed" (765 baseline + 15 new `tests/test_roll.py`). 56 warnings are all pre-existing categories (`MachRangeWarning`, `AeroRangeWarning`) unrelated to Step 109, not new. 0 failures, 0 errors.

**Result: PASS.**

## 7. Dynamics.py pitch-plane behavioral-equivalence check (item 4 of the task)

Read the full diff of `sim/dynamics.py` (§2 above) line-by-line, not just the test outcome:

- Every pre-existing line inside the `on_the_rail`/`chuted`/`else` branches is **byte-identical** to before, except the variable names `on_rail(y, p)` → `on_the_rail` and `forces.parachute_deployed(t, y, p)` → `chuted`, which are pure hoists of calls already being made (both `on_rail`/`parachute_deployed` are documented as pure functions of `(t, y, p)`; verified by reading their definitions — neither mutates state or has side effects). This is a call-count-only refactor with the Step 56 precedent cited; it is not a behavioral change for roll-off or roll-on flights.
- `dydt = np.zeros(7)` → `dydt = np.zeros(width(p))`: when `p.roll.model == "none"` (the default, verified structurally in §5 above for the only registered config), `width(p)` returns exactly `7` (`sim/state.py`'s `N_BASE`), so this line is a no-op change in every existing scenario — confirmed not "coincidentally zero" but **structurally gated**: `width()` is a one-line string comparison (`N_ROLL if p.roll.model != "none" else N_BASE`), not a derived/defaulted quantity that could silently drift.
- The roll block itself is behind `if p.roll.model != "none":` — an explicit, unconditional gate on the same field that already gates `width()`. With the default, the block's body (including the `roll.derivatives_roll` call and the `attitude_frozen` zeroing) is **never executed at all** for any existing scenario — not "computes and discards", genuinely skipped. Confirmed by reading the gate directly; this is a structural guarantee, not a numerical coincidence (e.g. not "L_x happens to be 0.0 so it doesn't matter" — the block doesn't run).
- `dydt[GAMMA]`/`dydt[OMEGA_X]`/`dydt[OMEGA_W]` writes are inside that same gate, and since `dydt = np.zeros(7)` when off, indices 7-9 don't even exist on the array in that case — writing to them would raise `IndexError`, so the gate is load-bearing in a way that would fail loudly (not silently) if ever miswired.

**Result: PASS.** The pitch-plane equations have zero behavioral change when roll is off — confirmed structurally gated (unreachable code path, index-out-of-range if ever reached), not merely "defaults to zero."

---

## Overall verdict

**PASS.** Every independently-verified claim in Step 109's implementation holds:

- File-list audit: exact match to the ticket, no stray changes, no missing edits.
- Code review against the ticket's own literal specification: byte-for-byte match in all six source files (`sim/state.py`, `sim/roll.py`, `sim/dynamics.py`, `sim/integrate.py`, `sim/params.py`, `configs/schema.py`/`_TEMPLATE_rocket.py`).
- All 3 self-flagged "stale pin" test edits verified to preserve original test intent, including a direct read of `test_actuator.py`'s original invariant and confirmation the rewrite still protects it.
- Gap #1 (the literal pre/post `run.py` CSV check) closed directly via a detached `git worktree` at HEAD — true byte-identity confirmed (MD5 match), not just the pin-count proxy.
- §109.10.1/109.10.2/109.10.4 physics/numerics acceptance checks independently recomputed from scratch (not re-reading developer's numbers) — all pass, momentum-exchange error 1.7e-18 (three orders tighter than the ticket's own bound), saturation plateau matches closed form to 6 sig. figs., rk4 decoupling bit-identical.
- `sim/dynamics.py`'s roll block read directly and confirmed structurally gated (unreachable when off, index-out-of-range if miswired) rather than "coincidentally zero."
- Full suite independently re-run: 780 passed, 0 failed — exact match to developer's self-report.
- LaTeX diff (5 files) reviewed in full and matches §109.8's description exactly; no developer-phase LaTeX edits found beyond the architect's own pre-existing work.

**No defects found.** No blocker, major, or minor issues to report back to the developer.

**One observation, not a defect:** a concurrent process added an untracked LaTeX file (`dev/docs/latex/sections-ai/rocket-3d.tex`) and, during this QA session, also modified `dev/docs/latex/main.tex` (+13 lines: a new `\input{sections-ai/rocket-3d}` block and three new bibliography entries — `wertz`, `hibbeler`, `stevenslewis`) in the shared working tree. Confirmed by reading the diff: this is unambiguously Step-30/3D-research LaTeX work by a different, concurrently-running agent — it does not touch `sec:roll`, `other-dynamics.tex`'s roll subsection, or any other Step-109 content. Flagged for orchestrator awareness only, per `CLAUDE.md`'s guidance to recheck `git status`/`git diff --stat` after background agent activity before writing over or committing anything.



