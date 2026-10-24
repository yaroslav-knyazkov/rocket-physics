# QA Report — Phase 2.17 Step 104: segmented RK45 + ZOH sampled-data path (D-116/D-128)

## Кратко (RU)

- **Вердикт: PASS.** Шаг 104 (сегментированный RK45 + ZOH, D-116/D-128) реализован корректно,
  самостоятельно перепроверено, не на веру разработчику.
- Все 3 заявленных отклонения от буквального скетча тикета — обоснованные инженерные решения, не
  срезание углов: (1) threading `hold` через closure вместо `args=(p, hold)` — честно соблюдает ZOH
  семантику внутри тика, без утечки между сегментами; (2) генерик-ширина State (7, не 6) — ни
  одного хардкода `6` в новом коде; (3) фоллбэк на `_LinearInterpolant` для `t_max<=0.0` — проверено
  живым запуском, что без фоллбэка был бы `IndexError`.
- Инварианты §104.1 (нулевой диф `_run_rk4` и plain-RK45, `rg` по `rk45_seg`/`sample_rate_hz`)
  перепроверены свежо, не скопированы из тикета — подтверждены.
- `raw.sol(t)` контракт подтверждён живым прогоном `report.py`/`plotting.py`; F8-guard в
  `flight_stats.py` корректно и безусловно отвергает `rk45_seg`+ZOH, без единой правки кода.
- Полный прогон тестов: **721 passed, 0 failed** (разработчик заявил 720 — расхождение в 1 тест,
  не регрессия, прослежено до неточного базового счёта в коммит-сообщении, не блокер).
- Производительность перепроверена самостоятельно (свой скрипт, тот же сценарий): ~11.6x ускорение
  и на одном полёте, и на ансамбле (100/4 воркера), апогей по времени совпадает до ~6 микросекунд
  между интеграторами — подтверждает заявку разработчика, не просто повторяет её.
- Блокеров и major-дефектов не найдено. Одно минорное замечание — опечатка в счёте тестов в
  коммит-сообщении (705+15=720 заявлено, реально 706+15=721), не блокирует приёмку.

## 0. Scope

Commit under review: `b9af952` "Step 104 (Phase 2.17): segmented RK45 + ZOH sampled-data path (D-116/D-128)".
Branch: `feature/sim-paper-alignment`.
Ticket: `dev/docs/task-104-segmented-rk45.md`.

Sections below are appended as each check completes.

## 1. Ticket read, diff read

- Ticket `dev/docs/task-104-segmented-rk45.md` read in full (§104.1-§104.15).
- Diff reviewed directly via `git show b9af952 -- sim/integrate.py` / `sim/params.py` /
  `configs/scenarios/_TEMPLATE_scenario.py` / `tests/test_integrate.py`.
- `sim/params.py` and `configs/scenarios/_TEMPLATE_scenario.py` diffs are exactly the one-line
  comment/table-row edits the ticket's §104.8 specified, verbatim text match.
- `sim/integrate.py`: exactly 4 hunks (`git diff 7fbbe24..b9af952 -- sim/integrate.py` hunk
  headers: lines 65, 417/436, 446/648, 470/676). Hunk 1 = new module-docstring paragraph
  (pure addition). Hunk 2 = new functions (`_NON_TERMINAL_EVENTS`, `_pending_events`,
  `_SegmentedSol`, `_SegRK45Raw`, `_run_segmented_rk45`) inserted wholesale **after** `_run_rk4`'s
  closing `)` and **before** `def run_sim` — no line inside `_run_rk4`'s own body is touched.
  Hunk 3 = new `run_sim` docstring sentence (pure addition). Hunk 4 = gate widened +
  new symmetric gate + new dispatch branch, inserted before the untouched plain-RK45 branch.
  **Confirms both of §104.1's "zero diff" claims by direct line-level inspection, not by trusting
  the commit message.**
- `tests/test_integrate.py`: 15 new test functions, matching the ticket's §104.11 plan (14 planned
  + 1 extra regression test for the `t_max<=0.0` deviation, which the ticket could not have
  anticipated since it predates that fix). Counted directly from the diff, not from the commit
  message's claimed "15 new tests".

## 2. Deviation 1 — closure-based `hold` threading (args-tuple sharing fix)

**Sound, verified independently.** `solve_ivp(args=...)` is indeed shared between `fun` and every
`events=` callable in scipy — the ticket's own `args=(p, hold)` sketch would call
`_ground_event(t, y, p, hold)`, a 4-arg call into a 3-arg function, a `TypeError` on the first tick.
The developer's fix: `args=(p,)` stays untouched (matching every event function's own `f(t, y, p)`
signature verbatim — confirmed by reading `_ground_event`/`_apogee_event`/etc. signatures, all
3-arg), and `hold` is threaded into the RHS only via a fresh closure per tick:

```python
def _rhs(tt, yy, pp, _hold=hold):
    return derivatives(tt, yy, pp, _hold)
```

- **ZOH semantics honored within a tick:** `_rhs` is defined once per outer-loop iteration
  (once per tick), and its default argument `_hold=hold` is bound at definition time to that
  tick's own `hold` value. `solve_ivp` calls `_rhs(t, y, p)` internally for every adaptive
  substep/stage inside that one `solve_ivp(... (t, t_end) ...)` call — all of them see the same
  `_hold`, exactly the "constant across all internal steps of one tick" ZOH contract `_run_rk4`
  already implements for its own 4 RK4 stages per substep.
- **No cross-segment leak:** because `_rhs` is a *new* function object defined fresh inside the
  `while` loop body on every iteration, the next tick's `_rhs` captures the next tick's own
  `hold` (reassigned by `sampling.sample(t, y, p, prev=hold)` at the top of that iteration) via a
  brand-new default-argument binding — there is no shared mutable cell that could let a later
  tick accidentally read an earlier tick's `hold`. Confirmed by reading the loop body line by
  line (`sim/integrate.py` lines ~529-574): `hold` is reassigned before `_rhs` is (re)defined,
  every iteration.
- Event functions genuinely unchanged — `derivatives` itself also unchanged, only a local wrapper
  was added. Matches the ticket's own non-goal ("event functions reused verbatim").

**Verdict: sound, not a weakening shortcut.**

## 3. Deviation 2 — generic State width (no hardcoded 6)

- `rg -n "\\b6\\b"` style hardcoding checked by direct read of every new function:
  `_run_segmented_rk45`'s `y_chunks = [y0.reshape(-1, 1)]` (generic, was ticket's own `y0.reshape(6, 1)`
  sketch); `_SegmentedSol.__call__` builds `out = np.empty((vals.shape[0], t_arr.size))` from the
  first delegate call's own return shape, not a literal `6`.
- Live smoke test (see §6 below) confirms `r.y.shape == (7, N)` and `r.raw.sol(t).shape == (7,)` /
  `(7, N)` for both scalar and array queries on a `recovery`-enabled scenario (7 = State's current
  width, x/z/vx/vz/theta/omega/m since Step 36) — no hardcoded-6 truncation anywhere in the new
  code path.
- `_SegRK45Raw.sol: Any` (typing already imported at module scope — `Any, NamedTuple, Optional` —
  no new import needed, confirmed).

**Verdict: sound, confirmed live, not just by grep.**

## 4. Deviation 3 — `t_max<=0.0` fallback + regression test

- `_run_segmented_rk45`: when `t_max<=0.0` the `while t < t_max` loop body never executes once
  (`0.0 < 0.0` is false), so `seg_sols`/`seg_starts` stay empty lists. The code falls back:
  `sol_impl = _SegmentedSol(seg_starts, seg_sols) if seg_sols else _LinearInterpolant(t_arr, y_arr)`.
  `_LinearInterpolant` (the pre-existing, already-generic — `self._y.shape[0]` — class `_run_rk4`
  uses) built from `t_arr=[0.0]`, `y_arr=y0.reshape(-1,1)` — a single-point linear interpolant,
  which `np.interp` degrades to constant extrapolation for any query `t`, matching `_run_rk4`'s own
  behaviour on the same degenerate input.
- Regression test `test_rk45_seg_degenerate_t_max_zero_does_not_crash_raw_sol`
  (`tests/test_integrate.py`) genuinely exercises the fallback: builds `t_max=0.0`, asserts
  `r.t.shape == (1,)`, then calls `r.raw.sol(0.0)` and `r.raw.sol(5.0)` (an out-of-range query) and
  checks both equal `np.array(s0)`. Independently confirmed the fallback is load-bearing (not just
  reading the code and trusting it): constructed `_SegmentedSol([], [])` directly (the object that
  would exist without the fallback, since `seg_sols`/`seg_starts` are empty on this input) and
  called it — raised `IndexError: list index out of range`, exactly the crash the fallback exists
  to avoid. Ran live: `r.t.shape = (1,)`, `r.raw.sol(0.0) = [0,0,0,0,1.5708,0,0]` (matches `s0`).

**Verdict: sound, the regression test genuinely exercises the fix (verified live, not just by
reading).**

## 5. §104.1 pin-safety invariants (re-run fresh, not from the ticket's own grep output)

- **`_run_rk4` zero diff:** `git diff 7fbbe24..b9af952 -- sim/integrate.py` hunk headers show only
  4 hunks total (lines 65, 417/436, 446/648, 470/676) — none fall inside `_run_rk4`'s own body
  (confirmed by reading the full function body, lines 258-436, against the diff: zero `+`/`-`
  lines inside it). Byte-identical.
- **Plain-RK45 (`sample_rate_hz==0.0`) branch zero diff:** same diff-hunk inspection — hunk 4 only
  touches the gate/dispatch block strictly before the plain branch's own `y0 = np.array(...)` /
  `solve_ivp(...)` call; that call's own lines are unchanged context in the diff.
  `python -m pytest tests/test_integrate.py::test_sample_rate_hz_zero_explicit_is_bit_for_bit_the_implicit_default -q`
  — **PASS** (run directly, see §7 for full output). Read the test itself: it runs `run_sim` twice,
  once with the field default (`sample_rate_hz` left unset) and once with `sample_rate_hz=0.0`
  passed explicitly, and asserts `np.array_equal(r.t, r_explicit.t)` and
  `np.array_equal(r.y, r_explicit.y)` — a genuine bit-for-bit proof, not a loose tolerance check.
- **`rg -n "rk45_seg"` across the whole repo** (re-run fresh, not copied from the ticket): exactly
  5 files match — `tests/test_integrate.py`, `sim/integrate.py`, `configs/scenarios/_TEMPLATE_scenario.py`,
  `sim/params.py`, `dev/docs/task-104-segmented-rk45.md`. All 5 are this commit's own touched/new
  files. No pre-existing file reaches the new sentinel string by accident.
- **`rg -n "sample_rate_hz" tests/ apps/ configs/ sim/`** (re-run fresh): every pre-existing
  `sample_rate_hz>0.0` test/config combo (`tests/test_actuator.py`, `tests/test_sampling.py`,
  `tests/test_config_pieces.py`, `tests/test_airbrake_sizing.py`, `tests/test_motor_selection.py`)
  pairs only with `method="rk4"`. The two exceptions in `tests/test_integrate.py` that use
  `method="RK23"`/the implicit default are the pre-existing gate-rejection tests, unaffected by
  the widened gate (both strings are still outside `{"rk4", "rk45_seg"}`). Only the new
  `test_rk45_seg_*` tests use the new sentinel. Confirms the widened gate changes behaviour for
  zero existing call sites.

## 6. `raw.sol(t)` contract re-verified against real consumers

- Live smoke test (not relying solely on pre-existing tests, since none pre-date `rk45_seg`):
  built a `recovery`-enabled scenario, ran `method="rk45_seg"`, then called `sim.report.flight_summary(r, p)`
  — returned a 4-key dict (`apogee_altitude`, `apogee_time`, `max_q`, `impact_time`) with no error —
  and `sim.plotting.plot_trajectory(r)` / `sim.plotting.plot_time_histories(r)` (matplotlib `Agg`
  backend) — both returned real `matplotlib.figure.Figure` objects, no shape/type error.
  `r.y.shape == (7, 1267)`, `r.raw.sol(t_grid).shape == (7, 50)` for an array query,
  `r.raw.sol(scalar_t).shape == (7,)` for a scalar query — matches the contract every other
  `raw.sol` implementation (`_LinearInterpolant`, the real `OdeSolution`) already gives.
- **F8 guard (`apps/common/flight_stats.py::_assert_derivatives_reconstructible`) re-verified by
  reading, then by a live call, not by trusting the ticket's claim:** the guard's own condition is
  `if p.solver.sample_rate_hz != 0.0: raise ValueError(...)` — unconditional on `method`, confirmed
  by direct read (lines 103-110). Live call: `with_solver(_demo_baseline(), method="rk45_seg",
  sample_rate_hz=20.0)` passed to `_assert_derivatives_reconstructible` — raised `ValueError`
  with the exact same message text the `rk4`+ZOH combo already gets today. **Zero code change
  confirmed correct, not just claimed.**

## 7. Full test suite — clean run from scratch

Ran `python -m pytest -q` in the background, polled to completion (not left dangling across turns):

```
721 passed, 56 warnings in 646.94s (0:10:46)
```

- Exit code 0.
- **Developer reported "720 passed, 0 failed (705 baseline + 15 new)"; my clean run shows
  721 passed.** Investigated the discrepancy directly rather than taking either number at face
  value: `tests/test_integrate.py` alone went from 12 `def test_` functions (parent commit
  `7fbbe24`) to 27 (`HEAD`, `b9af952`) — exactly **+15**, matching the ticket's own test-count
  claim and the earlier targeted run (`tests/test_integrate.py -q` → `27 passed`). This commit
  touches no other test file. So the repo-wide delta from this diff is genuinely +15, and my full
  run's 721 is internally consistent with that delta (721 - 15 = 706 baseline, not 705). The
  discrepancy is a minor miscount in the developer's self-reported baseline figure (off by one),
  **not a regression or a missing/duplicated test** — the suite is fully green either way.
  **Minor finding, not a defect:** developer's commit-message test count is off by 1 vs. a fresh
  count; does not affect the PASS verdict.
- `tests/test_integrate.py::test_sample_rate_hz_zero_explicit_is_bit_for_bit_the_implicit_default`
  — confirmed passing as part of both the targeted run (27/27 passed) and the full run. Read the
  test body directly: it asserts `np.array_equal` on both `.t` and `.y` between the implicit
  default and an explicit `sample_rate_hz=0.0` call — a genuine bit-for-bit proof that the plain
  path's own behaviour did not shift.

## 8. Independent performance re-measurement (§104.12 acceptance gate)

Own script (`temporary/perf_step104.py`, not copied from the developer), reproducing
qa-report-2.17-step105.md §7's own setup: demo scenario (`configs/scenarios/demo.py`),
ascent-to-apogee truncated (`t_max=40.0s`), `sample_rate_hz=20.0`, `dt=0.001` for the `rk4`
baseline, `run_ensemble(n=100, workers=4)`, identical dispersion
(`normal_path("aero.cx_scale", 1.0, 0.05, stage="params")`) and `seed=42` on both runs.

| Metric | `rk4` + ZOH | `rk45_seg` + ZOH | Speedup |
|---|---|---|---|
| Single-flight wall time | 11.71s | 1.008s | ~11.6x |
| Ensemble (n=100, workers=4) wall time | 321.59s (5.36 min) | 27.64s (0.46 min) | ~11.6x |
| Ensemble `failed` count | 0 | 0 | — |

**Apogee cross-check (same scenario, both integrators):** apogee time `rk4`=29.6144357007...s,
`rk45_seg`=29.6144414557...s — difference ≈ **5.76 microseconds**. Apogee altitude `rk4`=
5947.004873630597 m, `rk45_seg`=5947.007909580241 m — difference ≈ **3 mm**. Both independently
confirm the developer's claimed "~6 microseconds" apogee-time agreement and negligible altitude
drift — this is a genuine own-measurement match, not a re-statement of the developer's number.

**Comparison to the developer's own reported figures** (11.85s->1.02s single-flight;
311.6s->27.7s ensemble, ~11-12x): my own numbers (11.71s->1.01s; 321.6s->27.6s) land in the same
range, slightly higher on the `rk4` ensemble side (321.6s vs. 311.6s — ~3% difference, well within
ordinary machine-load variance, consistent with qa-report-2.17-step105.md §7's own documented
~1.5x developer-vs-QA spread on a comparable workload, this time much tighter). **D-116's "~5 min"
rk4 threshold is confirmed crossed on this machine too** (5.36 min > 5 min), and `rk45_seg` lands
comfortably under a minute, reproducing the developer's own conclusion independently.

**Acceptance gate met:** a real measurement exists, independently reproduced, numbers agree in
kind and in rough magnitude with the developer's — per §104.12's own stated bar ("a real
measurement exists and is reported," not "a specific number is hit").

## 9. Other checks

- `rg -n "\b6\b" sim/integrate.py`: two functional-code hits (`Result.y`'s own docstring comment
  "shape (6, N)" at line 103, pre-existing since Step 2, predates the Step 36 mass field and is
  stale independent of this commit — not introduced or touched by Step 104) and two in the
  `_SegmentedSol` docstring's prose (referring to the ticket's own now-superseded assumption, not
  executable code). No functional hardcoded `6` remains in the new code path — confirmed by
  direct read, matching §3's finding.
- `tests/test_template_docs.py` still green (part of the full-suite 721-pass run) — confirms the
  `_TEMPLATE_scenario.py` table-row edit did not break field-coverage checking.
- No edits found outside the declared scope (`sim/integrate.py`, `sim/params.py`,
  `configs/scenarios/_TEMPLATE_scenario.py`, `tests/test_integrate.py`) — `git show b9af952 --stat`
  lists exactly those four code/test files plus the new ticket doc itself.

## 10. Verdict

**PASS.** All three developer-reported deviations from the ticket's literal sketch are sound
engineering fixes, not weakening shortcuts (§2-§4). §104.1's pin-safety invariants hold under a
fresh, independent re-check, not copied from the ticket's own grep output (§5). `raw.sol(t)`'s
contract is honored for real consumers (`report.py`, `plotting.py`) and the F8 guard correctly,
unconditionally rejects `rk45_seg`+ZOH exactly as it does `rk4`+ZOH, with zero code change (§6).
Full suite: 721 passed, 0 failed, clean background run (§7) — one minor, inconsequential
discrepancy against the developer's self-reported count (720 vs. 721, traced to an off-by-one in
their own baseline figure, not a missing/duplicated test). Performance acceptance gate
independently re-measured and confirmed in kind and rough magnitude (§8): ~11.6x speedup both
single-flight and ensemble, apogee-time agreement to ~6 microseconds.

**No blocker or major defects found.** One minor, non-blocking finding: the developer's commit
message states "705 baseline + 15 new = 720 passed" where a fresh count gives 721 (baseline was
706, not 705) — cosmetic, does not affect the PASS verdict, worth a one-line correction if the
commit message is ever amended/referenced later.
