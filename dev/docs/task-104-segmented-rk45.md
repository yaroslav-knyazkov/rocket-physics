# Step 104 (D-116/D-128) — segmented RK45 + zero-order-hold sampled-data path

## Кратко (RU)

Тикет реализует вариант (b)/(c) из D-116 (`architecture-35-paper-alignment.md` §35.7): новый,
строго опционный путь интегрирования — **сегментированный RK45** вместо фиксированного `rk4`
для sampled-data/ZOH режима. Реальные замеры из `qa-report-2.17-step105.md` §7 подтвердили триггер
D-116 ("делать Step 104, если расчёт превышает ~5 мин"): 100-сэмпловый ансамбль на участке
"разгон-до-апогея" (`t_max=40с`) в RK4-ZOH режиме занял **5.03 мин** — на границе порога; полный
полёт с парашютным спуском — **~2.5 часа**. D-128 (2026-10-23): "строить сейчас, не ждать Step 109".

**Решение по API (сделано архитектором, не вынесено на пользователя — см. финальный ответ):**
новое значение `p.solver.method = "rk45_seg"`. Старый гейт (`sample_rate_hz>0.0` требует
`method=="rk4"`) расширен до `method in ("rk4", "rk45_seg")`; добавлен симметричный новый гейт —
`method=="rk45_seg"` требует `sample_rate_hz>0.0` (иначе это не имеет смысла: просьба использовать
плоский `"RK45"`). Ни один существующий тест/конфиг не использует строку `"rk45_seg"` — свежо
проверено grep (§104.10) — значит путь физически недостижим без явного нового выбора. Внутри каждого
тика — один вызов `scipy.solve_ivp(method="RK45", ...)` с теми же 5 event-функциями, что и обычный
путь (переиспользованы, не переизобретены); terminal `ground` — в каждом сегменте; 4 нетерминальных
события (`apogee`/`burnout`/`rail_exit`/`parachute_deploy`) — "первое срабатывание за весь полёт",
реализовано как сужающийся список событий через чистую тестируемую функцию `_pending_events`.
`Result.raw.sol(t)` — склейка (`_SegmentedSol`) по той же точной схеме вызова, что и
`_LinearInterpolant`/настоящий `OdeSolution` (`scalar -> (6,)`, `array -> (6, N)`), подобрана через
бинарный поиск по стартам сегментов — без сдвига времени (каждый сегмент работает в АБСОЛЮТНОМ
времени, не локальном "от нуля"). Нулевое изменение для `method="rk4"` и для `sample_rate_hz==0.0` —
подтверждено построением гейта и grep'ом существующих тестов. Производительность — не гарантируется
кодом тикета, а ИЗМЕРЯЕТСЯ разработчиком/QA как часть приёмки (§104.12), на той же сцене, что дала
5.03 мин в отчёте Step 105.

---

## Table of contents

- §104.1 Scope and non-goals
- §104.2 Opt-in API surface (decision made, rationale)
- §104.3 Ground truth recap (verified against the code, not assumed)
- §104.4 Design: per-segment integration loop
- §104.5 Event handling — terminal vs first-occurrence-only
- §104.6 Stitching `Result.t`/`.y`/`.raw.sol` across segments
- §104.7 `sim/integrate.py` — exact before/after
- §104.8 `sim/params.py` + template docs — exact before/after
- §104.9 Validation / guards — what's needed, what's not
- §104.10 Pin safety — grep commands + findings
- §104.11 Test plan
- §104.12 Performance verification requirement (acceptance gate)
- §104.13 Test-impact table
- §104.14 Open questions
- §104.15 Definition of done

---

## §104.1 Scope and non-goals

**In scope:**
- `sim/integrate.py`: one new opt-in code path (`_run_segmented_rk45`, `_pending_events`,
  `_SegmentedSol`, `_SegRK45Raw`), wired into `run_sim`'s dispatch + gate logic. Module docstring gets
  one new paragraph (house style — see Steps 42/45/47/48/59's own paragraphs already there).
- `sim/params.py`: `Solver.method`'s inline comment (line 168) — documents the new allowed value.
  No new dataclass field; `method` is already a plain `str`.
- `configs/scenarios/_TEMPLATE_scenario.py`: the `method` doc-table row (line 82) — choices text only.
- `tests/test_integrate.py`: new section, mirroring the existing "sample_rate_hz gate" section's style
  (lines ~239-338, reused wholesale as the model for the new tests' own shape).

**Out of scope / do not touch (D-110's pin policy, strict opt-in):**
- `_run_rk4` (the existing `rk4` + ZOH path) — **zero diff**. Confirmed by this ticket's own design:
  the new path is purely additive, dispatched on a brand-new `method` string value that cannot be
  reached by any existing call.
- The plain-RK45 (`sample_rate_hz==0.0`) path's own call to `solve_ivp` (lines 471-481 today) — **zero
  diff**, beyond whatever the developer judges worth sharing as a helper (see note below).
- `sim/sampling.py` — the channel contract/dispatch registry is reused completely unchanged; no new
  channel, no signature change. This ticket only adds a *second caller* of `sampling.sample(...)`.
- `sim/control.py`, `sim/sensors.py` (if present), any controller/law/estimator — no new controller is
  written here (B11/B12 territory, explicitly out of scope per D-116's own text and this project's
  "capability, not controller" precedent for Step 59).
- `apps/common/flight_stats.py`'s `_assert_derivatives_reconstructible` (the F8 guard) — confirmed
  below (§104.9) it needs **no change**: it already rejects `sample_rate_hz != 0.0` unconditionally,
  regardless of `method`, so it already covers the new path correctly today, with zero edits.
- Any LaTeX file under `dev/docs/latex/` — standing project rule, not reopened here.

**Optional, not required — a judgment call for the developer:** `run_sim`'s plain-RK45 branch and the
new segmented path both build an `args=(p, ...)` tuple and an `events=[...]` list for `solve_ivp`.
If the developer sees a clean, bit-for-bit-provable shared helper (e.g. a tiny function returning the
5-event list, used by both the plain path with `hold=None` and the segmented path with a real `hold`),
it MAY be extracted — but only if the `hold=None` call site's behaviour is proven unchanged
(`test_sample_rate_hz_zero_explicit_is_bit_for_bit_the_implicit_default` and the full suite are the
proof). If in doubt, duplicate the four lines instead — a correctness risk on the untouched default
path is not worth a few lines of DRY-ness (same judgment call Step 118's own ticket made for its
"implementation note", §118.2).

## §104.2 Opt-in API surface (decision made, rationale)

**Chosen:** a new `p.solver.method` value, the literal string `"rk45_seg"`.

Two gate changes in `run_sim`, both additive to the existing single gate:

1. The existing gate (`sample_rate_hz > 0.0` requires `method in {"rk4"}`) widens to
   `method in {"rk4", "rk45_seg"}`. Every method string that was rejected before (the default
   `"RK45"`, `"RK23"`, any other scipy name) is still rejected — only one new value is now accepted.
2. A new, symmetric gate: `method == "rk45_seg"` requires `sample_rate_hz > 0.0`. Segmented RK45
   exists *only* to serve the ZOH/sampled-data mode (D-116's whole premise is "fast sampled-data
   ensembles"); an un-sampled run has no reason to ask for it — `method="RK45"` already is plain,
   un-segmented RK45. Raising here turns a silent, pointless "one segment spanning the whole run"
   degenerate case into an explicit, fail-fast error instead.

**Why a new `method` value, not a new `Solver` field (e.g. `Solver.segmented: bool`) layered on top of
`method="RK45"`:** `method` already IS the project's single dispatch key for "which integrator" (the
existing `"RK45"` vs `"rk4"` choice, `sim/integrate.py`'s own module docstring, Step 8). A third
`method` value keeps that one seam as the single source of dispatch truth, matching the existing
`gravity_model`/`gravity_direction` orthogonality precedent cited by architecture-28-rewrite.md
§28.8.2 for the *sampling* gate itself — reusing the same precedent for the *solver* gate is the
smaller, more consistent change. A separate boolean field would create a FOURTH state
(`method="RK45", segmented=True`) that is meaningless and would need its own guard anyway — no
simpler than the two-gate design above, and it adds a field nobody else needs.

**Why not relax the existing gate to simply accept `sample_rate_hz>0.0` with `method="RK45"` directly
(i.e., reuse the existing default string, no new value at all), dispatching to segmented-vs-plain
purely on `sample_rate_hz`:** rejected — `method="RK45"` with `sample_rate_hz=0.0` (every existing test
and config) and `method="RK45"` with `sample_rate_hz>0.0` (the hypothetical new combo) would then mean
two *structurally different* code paths (plain single `solve_ivp` call vs. a ticking loop of many) under
the exact same `method` string — exactly the kind of implicit, easy-to-miss state-space expansion
D-110's strict-opt-in pin policy is written to prevent. A dedicated string makes the new path visible
at the call site (`with_solver(p, method="rk45_seg", sample_rate_hz=20.0)`), not inferred from a second
field's value.

**This sub-choice is an engineering call, not a `decision_required` for the user** (see final chat
reply): D-116/D-128 already approved "segmented RK45, build it now" as the WHAT; the exact string name
and gate shape are the same kind of naming/wiring decision Steps 116-119's architect made unilaterally
within their own already-approved scope (e.g. Step 118's `r*abs(r)` vs `copysign` choice). Flag to the
orchestrator only if the user specifically wants veto power over the literal string `"rk45_seg"` itself
— functionally interchangeable with any other unused string.

**Inner solver is hardcoded to scipy's `"RK45"`, not read from anywhere configurable.** D-116's own
text says "segmented RK45" specifically, not "segmented, solver-selectable." The segmented path's own
`solve_ivp` call always passes the literal `method="RK45"` — `p.solver.method` itself holds the
sentinel `"rk45_seg"`, which is never a valid scipy method name and must never be forwarded to
`solve_ivp` directly. A future step wanting segmented-DOP853 (or any other adaptive method) is a
separate, out-of-scope extension — do not generalize this ticket's scope to cover it pre-emptively.

## §104.3 Ground truth recap (verified against the code, not assumed)

- `sim/params.py` `Solver` (lines 166-173): `method: str = "RK45"`, `sample_rate_hz: float = 0.0`.
  Plain `str`, no enum/whitelist anywhere in the dataclass itself — `run_sim`'s own `if`/`raise` chain
  is the only place `method` is validated today.
- `sim/integrate.py::run_sim` (lines 420-497): dispatches `method == "rk4"` to `_run_rk4`, everything
  else to a single `scipy.integrate.solve_ivp` call with `events=[_ground_event, _apogee_event,
  _burnout_event, _rail_exit_event, _parachute_deploy_event]`, `dense_output=True`, `args=(p,)` (no
  `hold`, always `None` on this path today). The existing gate (lines 456-462) is exactly: `if
  sample_rate_hz > 0.0 and method != "rk4": raise ValueError(...)`.
- The five event functions (lines 90-210) are scipy-event-compatible `f(t, y, p)` callables, each
  already carrying `.terminal`/`.direction` class attributes scipy itself reads: `_ground_event`
  (`terminal=True, direction=1`) is the only terminal one; `_apogee_event`, `_burnout_event`,
  `_rail_exit_event`, `_parachute_deploy_event` are all `terminal=False`. These are reused verbatim —
  not touched, not reimplemented — by the new path.
- `dynamics.derivatives(t, y, p, hold=None)` already takes a 4th, optional `hold` argument (Step 59);
  the plain-RK45 path's `args=(p,)` never supplies one, so `hold` is always `None` there today. The
  new path will pass `args=(p, hold)` with a real `Hold` object, exactly like `_run_rk4` already does
  for its own RK4 stages.
- `sim/sampling.py::sample(t, y, p, prev) -> Hold` (the whole module, 84 lines) needs **zero** changes
  — its contract is integrator-agnostic by design (its own module docstring explicitly separates "the
  hold itself" from "sim/integrate.py... stays about numerics").
- `Result.raw.sol(t)` contract (confirmed by `rg -n '\.raw\.' ` across `apps/`, `sim/`, `tests/` —
  ~90 call sites): every one of them calls `.sol(t)` with either a scalar or an array `t` and expects
  shape `(6,)` or `(6, N)` back — **except** exactly one test,
  `tests/test_dynamics.py:765` (`r_rk45.raw.t_events[3]`), which accesses `.raw.t_events` directly, but
  only ever on a `Result` produced by the PLAIN RK45 path (the real `scipy.OdeResult`), never on an
  `_run_rk4`-produced `Result` (whose `_RK4Raw` NamedTuple has only a `sol` field and would already
  raise `AttributeError` on `.t_events` today if anyone tried). **This confirms the existing precedent
  this ticket's own `_SegRK45Raw` should follow: a `sol`-only NamedTuple is sufficient — no `.t_events`,
  `.status`, or `.message` compatibility is required of the new path either.**
- `apps/common/flight_stats.py::_assert_derivatives_reconstructible` (lines ~100-110) checks
  `if p.solver.sample_rate_hz != 0.0: raise ValueError(...)` — **unconditional on `method`**. This
  guard, and everything built on it (`apps/motor_selection/compare_motors.py`,
  `apps/airbrake_sizing/solve_cda.py`, `apps/weight_aero_tradeoff/trade_surface.py`'s F8 guard, all
  confirmed by `rg` in §104.10), already rejects the new `method="rk45_seg"` + `sample_rate_hz>0.0`
  combination too, for exactly the same reason it rejects `rk4`+ZOH today (a post-hoc
  `dynamics.derivatives` re-evaluation cannot reconstruct ANY sampled-data run's per-tick hold,
  regardless of which integrator produced it). **No code change needed in any of these files** — flag
  this explicitly in the diff/PR description so nobody "fixes" what isn't broken.

## §104.4 Design: per-segment integration loop

```
tick k (period T_s = 1/sample_rate_hz, absolute time t_k; t_0 = 0)
  hold = sampling.sample(t_k, y_k, p, prev=hold)               # same causal "measure, compute, hold"
                                                                # timing _run_rk4 already uses
  t_end_k = min(t_k + T_s, t_max)                              # clip the LAST tick, never overshoot
  names, fns = _pending_events(found)                          # ground always in; the other 4 only
                                                                # if not already seen (§104.5)
  sol = solve_ivp(derivatives, (t_k, t_end_k), y_k, method="RK45",
                   args=(p, hold), events=fns, dense_output=True,
                   rtol=rtol, atol=atol)
  record sol.sol (this segment's own dense interpolant) + t_k for stitching (§104.6)
  record any of the 4 non-terminal events that fired this segment into `found`
  if sol.status == 1:        # ground fired -- terminal, stop the WHOLE run
      t_ground = sol.t_events[0][0]; break
  else:
      t_{k+1}, y_{k+1} = sol.t[-1], sol.y[:, -1]               # continue to the next tick
loop while t_k < t_max
```

**Each segment's own `t_span=(t_k, t_end_k)` is ABSOLUTE time, never a 0-reset local clock.** This is
a deliberate choice, not an oversight: every `t` scipy hands back for that segment (`sol.t`,
`sol.t_events[...]`, and the dense `sol.sol(t)` interpolant's own domain) is consequently already in
the caller's global time frame. The alternative — integrating each segment over `(0, T_s)` locally and
adding back a running offset everywhere a time value is read — is strictly more code and opens an
entire class of off-by-one-translation bugs for zero benefit (`solve_ivp` has no preference for its
`t_span` starting at zero; it is just two floats). Do not "simplify" to a 0-reset design later without
re-reading this paragraph.

**Event functions are reused verbatim.** No new event-detection logic, manual sign-change code, or
interpolation is written — `_ground_event`/`_apogee_event`/`_burnout_event`/`_rail_exit_event`/
`_parachute_deploy_event` are passed to `solve_ivp`'s own `events=[...]` exactly as the plain-RK45 path
already does, letting scipy's own high-accuracy root-finding locate each crossing (strictly more
accurate than `_run_rk4`'s manual linear interpolation, since RK45's dense output is the actual
polynomial the solver produced, not a post-hoc straight-line approximation between two grid points).

**`method="RK45"` is hardcoded in this inner `solve_ivp` call** (§104.2) — never `p.solver.method`
itself, which holds the sentinel `"rk45_seg"` at this point and is not a valid scipy name.

**Guard against a zero-length final tick:** if floating-point accumulation ever makes `t_end_k <= t_k`
(should not happen under normal `t_max`/`T_s` combinations, but is cheap to guard, mirroring
`_run_rk4`'s own `dt_step = min(dt, t_max - t)` defensiveness), `break` out of the loop instead of
calling `solve_ivp` with a degenerate zero-length span.

## §104.5 Event handling — terminal vs first-occurrence-only

**`_ground_event` — always included, every segment, unconditionally.** It is the one event allowed to
terminate a segment early (`sol.status == 1`), and by construction it is the ONLY terminal event ever
passed to a segment's `solve_ivp` call (confirmed: `_pending_events`, below, never returns anything
terminal except `_ground_event` itself — the other four are always `terminal=False`). When it fires,
the whole outer loop stops; there is no "next segment."

**The other four (`apogee`, `burnout`, `rail_exit`, `parachute_deploy`) are first-occurrence-only
across the WHOLE run**, matching `Result.events`'s own `dict[str, float | None]` contract (never a
list — each key holds at most one time, exactly today's precedent on both existing paths). Implemented
via a small, deliberately pure, independently-testable helper:

```python
_NON_TERMINAL_EVENTS = (
    ("apogee", _apogee_event),
    ("burnout", _burnout_event),
    ("rail_exit", _rail_exit_event),
    ("parachute_deploy", _parachute_deploy_event),
)


def _pending_events(found: "dict[str, Optional[float]]"):
    """Which events still need watching in the NEXT segment. `_ground_event`
    is unconditionally always included (terminal, stops the whole run, not
    first-occurrence-tracked). Each of the other four is dropped the moment
    `found[name]` is no longer `None` -- it has already fired once, and
    `Result.events` can only ever record one time per key (never a list),
    so re-including an already-fired event risks a LATER segment's
    spurious/second crossing (e.g. floating-point noise sitting exactly at
    `thrust == 0` well after burnout) silently overwriting the correct
    first-occurrence time. Pure function of `found` alone -- no `solve_ivp`
    call, no segment state -- independently unit-testable (SS104.11)."""
    pending = [(name, fn) for name, fn in _NON_TERMINAL_EVENTS if found[name] is None]
    names = ["ground"] + [name for name, _ in pending]
    fns = [_ground_event] + [fn for _, fn in pending]
    return names, fns
```

Per segment: call `_pending_events(found)` to get `(names, fns)`, pass `fns` as `events=...`, then for
each non-"ground" `idx, name` in `enumerate(names)`, if `len(sol.t_events[idx])` is nonzero AND
`found[name] is None` (belt-and-braces — `_pending_events` already guarantees this), set
`found[name] = float(sol.t_events[idx][0])`. `ground`'s own time is read separately, only when
`sol.status == 1` (`t_ground = float(sol.t_events[0][0])` — index 0 because `_ground_event` is always
first in `fns`).

**Why this is safe even if two events fire in the same segment, or an event and ground fire at the
same instant:** no new edge case is introduced by segmentation itself — scipy's own single-`solve_ivp`
semantics already handle "multiple events in one accepted step" and "a terminal event stopping before
a later non-terminal crossing in the same step" identically whether the call spans the whole flight (as
today's plain-RK45 path does) or one tick (as this path does); each event's own `t_events` array is
independent of the others' regardless of span length.

## §104.6 Stitching `Result.t`/`.y`/`.raw.sol` across segments

**The single most important design decision in this ticket** (per the brief) — concrete sketch:

```python
class _SegmentedSol:
    """Stitches per-segment scipy dense `OdeSolution` callables
    (`solve_ivp(..., dense_output=True).sol`) into one seamless `raw.sol(t)`
    spanning the WHOLE run -- the exact same call shape `_LinearInterpolant`
    and the real single-call RK45 path's `OdeSolution` already give every
    caller (scalar t -> shape-(6,) array; array t -> shape-(6, N) array), so
    `Result.raw.sol(...)` needs no special-casing per integrator anywhere
    outside this module (task-104-segmented-rk45.md SS104.6). Each
    segment's own `sol` IS scipy's exact dense interpolant for that segment
    -- this class only decides WHICH segment's `sol` to delegate to for a
    given `t`, by binary search over `starts` (each segment's own
    `t_start`, strictly increasing, absolute time -- SS104.4). A `t`
    landing exactly on a shared segment boundary is served by the EARLIER
    segment (`searchsorted(..., side="right")` semantics); `t` outside
    `[starts[0], run end]` is clamped to the nearest edge segment, same
    "caller's responsibility to stay in range" contract every other
    `raw.sol` implementation in this codebase already has.
    """

    def __init__(self, starts: "list[float]", sols: "list"):
        self._starts = np.asarray(starts, dtype=float)
        self._sols = sols

    def __call__(self, t):
        t_arr = np.atleast_1d(np.asarray(t, dtype=float))
        idx = np.searchsorted(self._starts, t_arr, side="right") - 1
        idx = np.clip(idx, 0, len(self._sols) - 1)
        out = np.empty((6, t_arr.size))
        for seg_idx in np.unique(idx):
            mask = idx == seg_idx
            out[:, mask] = self._sols[seg_idx](t_arr[mask])
        return out if np.ndim(t) else out[:, 0]


class _SegRK45Raw(NamedTuple):
    sol: _SegmentedSol
```

Grouping by `np.unique(idx)` before delegating (rather than one Python-level call per scalar `t`) keeps
a large `t_grid` query (`tests/test_thrust_scatter.py`'s own `np.linspace(0.0, r.t[-1], 2001)` is the
existing worst case in the suite) at O(segments) vectorised calls, not O(N) scalar calls — relevant
because a long sampled run at a high rate can have thousands of segments/ticks.

**Building `Result.t`/`Result.y` without duplicating the shared boundary point:** segment `k`'s own
`sol.t[0]`/`sol.y[:, 0]` is, bit-for-bit, the same instant as segment `k-1`'s own `sol.t[-1]`/
`sol.y[:, -1]` — it is literally the `y` value handed in as that segment's initial condition, which
`solve_ivp` always echoes unchanged as its own first output point (no computation performed on it).
So: keep the very first point (`t=0`, `y=y0`) once, then for every segment append only `sol.t[1:]`/
`sol.y[:, 1:]` (dropping each segment's own redundant first column), and `np.concatenate(...)` across
segments at the end:

```python
t_chunks = [np.array([0.0])]
y_chunks = [y0.reshape(6, 1)]
seg_starts, seg_sols = [], []

# ... inside the per-tick loop, after a successful solve_ivp call ...
seg_starts.append(t_k)
seg_sols.append(sol.sol)
t_chunks.append(sol.t[1:])
y_chunks.append(sol.y[:, 1:])

t_arr = np.concatenate(t_chunks)
y_arr = np.concatenate(y_chunks, axis=1)
raw = _SegRK45Raw(sol=_SegmentedSol(seg_starts, seg_sols))
```

`t_arr` is then strictly increasing with no duplicate consecutive values — exactly the same shape
guarantee `sol.t`/`_run_rk4`'s own `t_arr` already give every downstream consumer
(`report.py`/`plotting.py`/every test iterating `result.t`).

## §104.7 `sim/integrate.py` — exact before/after

**Module docstring (after the Step 59 paragraph, lines 50-67).** Add a new paragraph (house style —
matches Steps 42/45/47/48/59's own entries):

```python
Step 104 (Phase 2.17; D-116/D-128; task-104-segmented-rk45.md): a second,
also opt-in sampled-data path -- `p.solver.method == "rk45_seg"` -- for
when the fixed-step `rk4` + ZOH path (Step 59) is too slow for a large
sampled-data ensemble (measured in qa-report-2.17-step105.md SS7: a
100-sample ascent-to-apogee ensemble landed at the D-116 "~5 min"
threshold under rk4; a full-flight ensemble, ~2.5 hours). One
`solve_ivp(method="RK45", ...)` call per sampling tick, instead of one
hand-written RK4 substep per tick -- the adaptive solver's own step
control runs freely inside a tick, and the hold boundary between ticks
is a segment boundary, never a mid-step discontinuity, so it is honoured
exactly, the same ZOH correctness argument Step 59's own docstring makes
for its RK4 stages. Gated the same way Step 59's `rk4` path is
(`sample_rate_hz > 0.0` required), PLUS a new, symmetric gate:
`method == "rk45_seg"` itself requires `sample_rate_hz > 0.0` (this
method exists only to serve the ZOH mode; an un-sampled run has no
reason to ask for it). `_run_rk4` is NOT touched by this step -- zero
diff, confirmed by construction: the new path is dispatched on a
brand-new `method` string no existing call can reach.
```

**New module-level constants/functions, placed after `_run_rk4` (line 417) and before `run_sim`
(line 420).** In order: `_NON_TERMINAL_EVENTS`, `_pending_events` (§104.5), `_SegmentedSol`,
`_SegRK45Raw` (§104.6), `_run_segmented_rk45` (full body below). `bisect`/`numpy` are already imported
at module scope (`np` is; add nothing new except reusing it — `_SegmentedSol` uses
`np.searchsorted`/`np.unique`/`np.clip`, no new import needed since `numpy` is already `import numpy
as np` at line 73).

```python
def _run_segmented_rk45(p, s0: State, t_max: float, sample_rate_hz: float,
                         rtol: float, atol: float) -> Result:
    """Segmented RK45 + zero-order hold (Step 104, D-116/D-128) -- see
    task-104-segmented-rk45.md SS104.4-SS104.6 for the full design
    rationale. One `solve_ivp(method="RK45", ...)` call per sampling tick;
    each segment's own `t_span` is ABSOLUTE time (no 0-reset, no offset
    arithmetic needed when stitching -- SS104.4). Event functions are the
    same five module-level callables the plain-RK45 path uses, reused
    verbatim: `_ground_event` (terminal) every segment; the other four
    first-occurrence-only across the whole run via `_pending_events`.
    """
    from sim import sampling  # local import -- Step 59's own precedent;
                               # never imported on the default RK45 path
                               # or the un-sampled rk4 path.

    y0 = np.array(s0, dtype=float)
    T_s = 1.0 / sample_rate_hz

    t_chunks = [np.array([0.0])]
    y_chunks = [y0.reshape(6, 1)]
    seg_starts: list = []
    seg_sols: list = []

    found = {"apogee": None, "burnout": None, "rail_exit": None, "parachute_deploy": None}
    t_ground = None

    t = 0.0
    y = y0
    hold = None
    while t < t_max:
        hold = sampling.sample(t, y, p, prev=hold)
        t_end = min(t + T_s, t_max)
        if t_end <= t:
            break  # floating-point edge at the very last tick; nothing left to integrate

        names, fns = _pending_events(found)
        sol = solve_ivp(
            derivatives, (t, t_end), y, method="RK45",
            args=(p, hold), events=fns, dense_output=True,
            rtol=rtol, atol=atol,
        )
        if sol.status == -1:
            raise RuntimeError(f"segmented RK45 tick at t={t} failed: {sol.message}")

        for idx, name in enumerate(names):
            if name != "ground" and len(sol.t_events[idx]):
                found[name] = float(sol.t_events[idx][0])

        seg_starts.append(t)
        seg_sols.append(sol.sol)
        t_chunks.append(sol.t[1:])
        y_chunks.append(sol.y[:, 1:])

        t, y = float(sol.t[-1]), sol.y[:, -1]

        if sol.status == 1:
            # The only terminal event ever passed is _ground_event
            # (SS104.5) -- confirmed by construction via _pending_events.
            t_ground = float(sol.t_events[0][0])
            break

    t_arr = np.concatenate(t_chunks)
    y_arr = np.concatenate(y_chunks, axis=1)

    return Result(
        t=t_arr,
        y=y_arr,
        events={
            "apogee": found["apogee"], "ground": t_ground,
            "burnout": found["burnout"], "rail_exit": found["rail_exit"],
            "parachute_deploy": found["parachute_deploy"],
        },
        raw=_SegRK45Raw(sol=_SegmentedSol(seg_starts, seg_sols)),
        params=p,
    )
```

**`run_sim` (lines 420-497) — gate + dispatch.** Replace the existing gate (lines 456-462):

```python
    if sample_rate_hz > 0.0 and method != "rk4":
        raise ValueError(
            f"p.solver.sample_rate_hz={sample_rate_hz} requires "
            f"p.solver.method=='rk4' (got method={method!r}): an adaptive "
            "integrator cannot honour a zero-order-hold boundary "
            "(architecture-28-rewrite.md SS28.8.2)."
        )
```

with:

```python
    if sample_rate_hz > 0.0 and method not in ("rk4", "rk45_seg"):
        raise ValueError(
            f"p.solver.sample_rate_hz={sample_rate_hz} requires "
            f"p.solver.method in {{'rk4', 'rk45_seg'}} (got method={method!r}): "
            "a plain adaptive integrator cannot honour a zero-order-hold "
            "boundary (architecture-28-rewrite.md SS28.8.2; Step 104 adds "
            "'rk45_seg' as the second, segmented-adaptive option, "
            "task-104-segmented-rk45.md)."
        )

    if method == "rk45_seg" and sample_rate_hz <= 0.0:
        raise ValueError(
            f"p.solver.method='rk45_seg' requires sample_rate_hz > 0.0 "
            f"(got sample_rate_hz={sample_rate_hz}): segmented RK45 exists "
            "only to serve the sampled-data/ZOH mode -- for an un-sampled "
            "run use method='RK45' instead (task-104-segmented-rk45.md "
            "SS104.2)."
        )
```

Then, replace the dispatch (lines 464-467):

```python
    if method == "rk4":
        result = _run_rk4(p, s0, t_max, dt, sample_rate_hz)
        _warn_if_mach_blind(result)
        return result
```

with:

```python
    if method == "rk4":
        result = _run_rk4(p, s0, t_max, dt, sample_rate_hz)
        _warn_if_mach_blind(result)
        return result

    if method == "rk45_seg":
        result = _run_segmented_rk45(p, s0, t_max, sample_rate_hz, rtol, atol)
        _warn_if_mach_blind(result)
        return result
```

No other line in `run_sim` changes — the plain-`solve_ivp` branch below (today's lines 469-497) is
untouched, bit-for-bit, for every `method` value that isn't `"rk4"` or `"rk45_seg"`.

Also update `run_sim`'s own docstring (today's lines 420-447) with one sentence after the Step 59
paragraph: `"Step 104 (D-116/D-128): p.solver.method == 'rk45_seg' opts into a second sampled-data
path, segmented RK45, gated the same way plus its own sample_rate_hz>0.0 requirement -- see
task-104-segmented-rk45.md."`

## §104.8 `sim/params.py` + template docs — exact before/after

**`sim/params.py` line 168.** Replace:

```python
    method: str = "RK45"          # RK45 (or any scipy name) | rk4
```

with:

```python
    method: str = "RK45"          # RK45 (or any scipy name) | rk4 | rk45_seg (Step 104, D-116 -- requires sample_rate_hz>0.0)
```

**`configs/scenarios/_TEMPLATE_scenario.py` line 82.** Replace the `method` row's choices cell:

```
| method         | OPT     | RK45 \| rk4 (or any scipy name) | "RK45" | integration method |
```

with:

```
| method         | OPT     | RK45 \| rk4 \| rk45_seg (or any scipy name for RK45's slot) | "RK45" | integration method; rk45_seg needs sample_rate_hz>0.0 (Step 104) |
```

Re-run `tests/test_template_docs.py` after this edit — confirm it only checks field COVERAGE (every
`dataclasses.fields(Solver)` has a row) and row-shape mechanics, not the literal choices text, so this
edit cannot fail that test's own assertions; read the test itself to confirm before assuming.

## §104.9 Validation / guards — what's needed, what's not

**New guard added (both directions, §104.2/§104.7):**
1. `sample_rate_hz > 0.0` now requires `method in ("rk4", "rk45_seg")` (widened from `== "rk4"`).
2. `method == "rk45_seg"` requires `sample_rate_hz > 0.0` (new, symmetric).

**No new guard for "`T_s` absurdly short/long relative to the dynamics" — explicit reasoning, not an
oversight.** Unlike `_run_rk4`'s `T_s/dt` integer-multiple check (which exists because a non-integer
ratio would silently change the EFFECTIVE sample rate — a correctness hazard), there is no analogous
hazard here: `rtol`/`atol` govern step size *within* a segment, and scipy's adaptive stepping handles
any `T_s` magnitude correctly on its own —
- `T_s` very large relative to the natural time constant: each segment just takes many internal RK45
  steps, behaving like one long, correctly-adaptive integration; no accuracy loss, only more work per
  tick (expected, proportional to flight complexity, not a bug).
- `T_s` very small (an absurdly high sample rate): each segment does very little work (often just 1-2
  internal steps), but each segment still pays `solve_ivp`'s own fixed call overhead — at the extreme,
  this path could become SLOWER than fixed-step RK4, not faster. This is a self-correcting
  user/tuning concern (choose a sane sample rate for your controller), not a correctness hazard a hard
  guard should prevent — and it is exactly what the required performance comparison (§104.12) exists
  to surface on a REALISTIC configuration, not to pre-emptively guard against every unrealistic one.

**No new guard for `t_max <= 0.0`, `rtol`/`atol` sanity, etc.** — these have zero precedent as guarded
inputs anywhere else in `sim/integrate.py` today (not on the plain-RK45 path, not on `_run_rk4`);
introducing a guard here that the sibling paths lack would be inconsistent, scope-creeping house style
rather than matching it.

**`_assert_derivatives_reconstructible` (apps/common/flight_stats.py) needs zero changes** — already
covered in §104.3; restated here because it is the one "guard-shaped" piece of this ticket's surface
area that a less careful read might assume needs touching.

## §104.10 Pin safety — grep commands + findings

All run and read directly (not assumed from the pattern alone) during this ticket's drafting:

```bash
# 1. Is the new sentinel string already in use anywhere? (it must not be, for the
#    "physically unreachable without an explicit new choice" claim in SS104.2 to hold)
rg -n "rk45_seg" .
# -> No matches (confirmed 2026-10-24, before this ticket existed).

# 2. Every existing sample_rate_hz>0.0 test/config combo -- confirm each pairs ONLY with
#    method="rk4" today (so the widened gate changes behaviour for NO existing call).
rg -n "sample_rate_hz" tests/ apps/ configs/ sim/
# -> tests/test_actuator.py, tests/test_sampling.py, tests/test_config_pieces.py:
#    all pair sample_rate_hz>0 with method="rk4" explicitly.
# -> tests/test_integrate.py: the two "raises" tests use method="RK23" (default-ish adaptive)
#    and the implicit default "RK45" -- both must CONTINUE to raise under the widened gate
#    (confirmed: neither string is "rk4" or "rk45_seg", so method not in (...) still fires).
# -> tests/test_airbrake_sizing.py, tests/test_motor_selection.py: pair sample_rate_hz>0
#    with method="rk4", feeding the apps/common/flight_stats.py F8 guard (unconditional on
#    method -- SS104.3/SS104.9), not sim/integrate.py's own gate directly.

# 3. Any construction of Solver/with_solver using "rk45_seg" already, anywhere (defensive
#    re-check, same intent as #1 with a narrower pattern):
rg -n 'method\s*=\s*.rk45_seg' .
# -> No matches.

# 4. Does any test rely on run_sim's gate error MESSAGE text (not just ValueError type), which
#    this ticket's rewritten message (SS104.7) must not silently break?
rg -n "match=.*sample_rate_hz" tests/test_integrate.py tests/test_motor_selection.py
# -> tests/test_motor_selection.py uses match="sample_rate_hz" against flight_stats.py's OWN
#    guard message (unchanged by this ticket, SS104.9) -- not sim/integrate.py's message.
#    tests/test_integrate.py's two gate tests use plain `pytest.raises(ValueError)`, no
#    `match=`, so the rewritten message text in SS104.7 is free to change without breaking
#    them (confirmed by direct read, SS104.3 lines quoted above).
```

**Re-run these same four commands as an acceptance gate after implementation** — if any of them
surfaces a NEW match that contradicts the "no existing test/config reaches the new path by accident"
claim, stop and report it rather than silently proceeding.

## §104.11 Test plan

All new tests live in `tests/test_integrate.py`, new section after the existing "sample_rate_hz gate"
block (after line 338, mirroring that block's own house style: plain `assert`/`pytest.raises`, no
fixtures, reusing the file's existing `Params`/`State`/`with_solver` helpers).

**Gate tests (mirror the existing four, same shapes):**
1. `test_rk45_seg_without_sample_rate_raises` — `with_solver(p, method="rk45_seg")` (sample_rate_hz
   left at its 0.0 default) raises `ValueError`.
2. `test_rk45_seg_with_sample_rate_does_not_raise` — `with_solver(p, method="rk45_seg",
   sample_rate_hz=10.0)` runs to completion (`r.t[-1] > 0.0`), mirroring
   `test_integer_sample_ratio_does_not_raise`'s own shape (note: no `T_s/dt` integer-multiple check
   applies here, §104.9 — `dt` is irrelevant to this path and should simply be ignored/unused, confirm
   no `dt`-shaped error is raised).
3. Re-run `test_rk45_with_nonzero_sample_rate_raises_immediately`,
   `test_non_rk4_other_method_with_nonzero_sample_rate_also_raises`, and
   `test_sample_rate_hz_zero_explicit_is_bit_for_bit_the_implicit_default` UNCHANGED — zero diff
   expected, they are the direct proof the widened gate changes nothing for `"RK45"`/`"RK23"`/the
   implicit default.

**`_pending_events` unit tests (no `solve_ivp` call, pure function, SS104.5):**
4. `test_pending_events_includes_ground_and_all_four_when_nothing_found` —
   `_pending_events({"apogee": None, "burnout": None, "rail_exit": None, "parachute_deploy": None})`
   returns `names == ["ground", "apogee", "burnout", "rail_exit", "parachute_deploy"]` and `fns ==
   [_ground_event, _apogee_event, _burnout_event, _rail_exit_event, _parachute_deploy_event]`.
5. `test_pending_events_drops_an_already_found_event` — with `found["burnout"] = 1.23` (others
   `None`), `"burnout"` is absent from `names`/`fns`, the other three plus `"ground"` are present, in
   the same relative order.
6. `test_pending_events_returns_only_ground_when_all_four_found` — all four non-`None` -> `names ==
   ["ground"]`, `fns == [_ground_event]`.

**`_SegmentedSol` stitching unit tests (no `run_sim` call — build directly from two or three small
hand-rolled `solve_ivp(..., dense_output=True)` calls on a trivial ODE, e.g. `dy/dt = 1` so the
expected value at any `t` is analytically known, SS104.6):**
7. `test_segmented_sol_scalar_t_matches_the_right_segment` — construct 3 segments covering
   `[0,1), [1,2), [2,3]`; query `t=0.5` (segment 0), `t=1.5` (segment 1), `t=2.999` (segment 2); assert
   each returned value matches that segment's own analytic/dense value, and the returned shape is
   `(6,)` for a scalar `t` (adapt the trivial ODE to 6 components, or test with a smaller stand-in
   array size and note the real contract is 6 — developer's call on the cleanest way to exercise this
   without a full `State`).
8. `test_segmented_sol_array_t_spanning_multiple_segments` — query an array of `t` values that
   straddles all 3 segments in one call; assert shape `(6, N)` and that each column matches the
   segment its own `t` falls in (cross-check against a per-element scalar call, proving the vectorised
   `np.unique`-grouped path and the scalar path agree).
9. `test_segmented_sol_boundary_t_goes_to_the_earlier_segment` — query `t` exactly equal to a shared
   boundary (e.g. `t=1.0`); assert it matches segment 0's own value at `t=1.0`, not segment 1's
   (both should numerically agree to solver tolerance for a continuous trajectory, but the test should
   pin the *which-segment-is-asked* behaviour, e.g. via a `MagicMock`/call-count spy on each segment's
   `sol`, not just the numeric agreement, so a future refactor that flips the tie-break is caught).

**Integration-level tests (real `run_sim` with `method="rk45_seg"`, a small hand-built `Params`, same
style as `tests/test_sampling.py`'s own `_launch_params`/`_launch_state` helpers — reuse those or
closely mirror them):**
10. `test_rk45_seg_result_t_is_strictly_increasing_no_duplicate_boundaries` — `np.all(np.diff(r.t) >
    0)` over a full flight.
11. `test_rk45_seg_raw_sol_matches_result_y_at_every_stored_t` — for a sample of indices `i`,
    `np.allclose(r.raw.sol(r.t[i]), r.y[:, i])` (self-consistency between the stored grid and the
    dense stitched interpolant — this is the test most likely to catch a stitching/boundary bug).
12. `test_rk45_seg_ground_event_terminates_the_whole_run` — a scenario that reaches the ground before
    `t_max` (e.g. no parachute, short `t_max` not reached) — `r.events["ground"]` is a float,
    `r.t[-1] == r.events["ground"]` (within solver tolerance), and no segment was started after it
    (hard to observe directly without instrumentation; at minimum assert `r.t[-1]` does not exceed
    `t_max` and the ground time is physically sane).
13. `test_rk45_seg_each_of_the_four_events_fires_at_most_once` — for a full-flight scenario (motor
    burn, apogee, rail exit if `L_rail>0`, parachute if configured), assert every one of
    `r.events["apogee"/"burnout"/"rail_exit"/"parachute_deploy"]` is either `None` or a single `float`
    (the type itself already enforces "at most once" — this test exists to catch a REGRESSION to a
    list/multiple-value shape if `_pending_events` is ever bypassed by a future edit, i.e. a
    type/shape assertion, not just a happy-path smoke test).
14. `test_rk45_seg_agrees_with_rk4_sampled_within_tolerance` — same `Params`
    (`sample_rate_hz` identical on both), one run with `method="rk4"` at a small `dt` (converged), one
    with `method="rk45_seg"`; assert apogee altitude and apogee time agree within a loose, named
    tolerance (these are two DIFFERENT integrators, not expected to be bit-identical — this is a
    cross-check in the same spirit as `tests/test_dynamics.py:83-84`'s existing `alt_rk45` vs
    `alt_rk4` comparison for the two existing, un-sampled integrators).
15. `test_rk45_seg_with_default_airbrake_model_is_a_no_controller_passthrough` — `control.airbrake_model
    == "none"` (the default) under `rk45_seg` behaves identically in kind to the same config under
    `rk4`+ZOH (both exercise `sampling.sample`'s existing single `"airbrake"` channel, which this
    ticket does not touch) — a basic "the new path doesn't require a controller to exist" smoke test.

## §104.12 Performance verification requirement (acceptance gate)

**Not a pytest assertion — a measured, reported comparison, run by the developer and independently
reproduced by QA**, because wall-clock timing is machine/load-sensitive (qa-report-2.17-step105.md §7
documents a 1.5x discrepancy between the developer's and QA's own measurements on the SAME code). The
acceptance gate is "a real measurement exists and is reported," not "a specific number is hit."

**Required scenario (reuse qa-report-2.17-step105.md §7's own setup, so the before/after numbers are
directly comparable to the numbers that triggered this ticket):**
- Demo scenario, **ascent-to-apogee truncated** (`t_max=40.0s`, the phase qa-report-2.17-step105.md §7
  judged relevant to a future controller ensemble — recovery descent has no brake-authority question).
- `sample_rate_hz=20.0` (matching the architecture doc's own design-time estimate, §35.4.4/§35.7
  D-116), `dt=0.001` for the `rk4` baseline (the field default, same as qa-report-2.17-step105.md §7
  used — NOT the `dt=0.005` design-doc estimate, to stay apples-to-apples with the number that actually
  triggered D-116's "~5 min" finding).
- `run_ensemble(n=100, workers=4)` (`apps/common/ensemble.py`, Step 105), identical dispersion list on
  both runs, identical seed.

**Report, in the PR/ticket-closing message, both:**
1. Single-flight wall time, `method="rk4"` + ZOH vs. `method="rk45_seg"` + ZOH, same scenario.
2. The 100-sample/4-worker ensemble wall time, both methods, same scenario — this is the number to
   compare against qa-report-2.17-step105.md §7's own **301.83s (5.03 min)** figure for `rk4`.

**No hard numeric pytest assertion on wall-clock time** (flaky, machine-dependent — do not write
`assert elapsed < N` into the test suite). If the developer wants an automated smoke check that the
new path is AT LEAST faster in kind (not a specific factor), a loosely-bounded, explicitly-marked-slow
test comparing single-flight wall time on a tiny scenario (e.g. `assert seg_time < rk4_time`) MAY be
added, clearly marked as a smoke check, not a performance-claim proof — D-116's "10-100x" claim is
validated by the reported numbers above, not by a CI assertion.

## §104.13 Test-impact table

| File | Change | Reason |
|---|---|---|
| `sim/integrate.py` | New: `_NON_TERMINAL_EVENTS`, `_pending_events`, `_SegmentedSol`, `_SegRK45Raw`, `_run_segmented_rk45` | The new opt-in path itself |
| `sim/integrate.py` | `run_sim`: gate widened + new symmetric gate + new dispatch branch | Wiring (§104.7) |
| `sim/integrate.py` | Module + `run_sim` docstrings: one new paragraph/sentence each | House documentation convention |
| `sim/params.py` | `Solver.method`'s inline comment (line 168) | Documents the new value |
| `configs/scenarios/_TEMPLATE_scenario.py` | `method` doc-table row's choices cell (line 82) | Same |
| `tests/test_integrate.py` | ~15 new tests, new section | §104.11 |
| `_run_rk4`, the plain-RK45 branch, `sim/sampling.py`, `apps/common/flight_stats.py` | **No change** | Confirmed additive/already-generic (§104.3/§104.9) |
| All other tests | **No change expected** | `"rk45_seg"` is unreachable without an explicit, new, opt-in choice (§104.10) |

## §104.14 Open questions

1. **Shared-helper extraction between the plain-RK45 and segmented-RK45 branches** (the "args/events
   tuple" building) — left as the developer's judgment call (§104.1's closing note), not mandated,
   not forbidden. If done, it must be proven bit-for-bit for the `hold=None` plain-RK45 case (full
   suite green, specifically `test_sample_rate_hz_zero_explicit_is_bit_for_bit_the_implicit_default`).
2. **Whether `_SegmentedSol` should cache/memoize repeated queries at the same `t`** — not designed
   here; `report.py`/`plotting.py` call `.sol(t_grid)` once with a full array per plot, not repeatedly
   at scattered single points in a hot loop, so this is not expected to matter; flag to the orchestrator
   only if the performance measurement (§104.12) surfaces an unexpected bottleneck specifically inside
   `.sol(...)` itself (as opposed to the integration loop), which would be a different, more surprising
   finding worth a second look.
3. **Should a future step generalize `"rk45_seg"` to other scipy adaptive methods** (e.g.
   "segmented-DOP853")? Explicitly out of scope here (§104.2) — `Aero.C_x180`-style precedent (Step
   118's own §118.5): a schema/field already existing for a future extension does not mean it should
   be threaded through now.
4. **D-116's own open item, restated from qa-report-2.17-step105.md §7:** the REAL controller-ensemble
   shape (Steps 107/108, not yet built) is still the number that should ultimately decide whether this
   path's speedup is "enough" — this ticket builds the capability D-116 approved; it does not itself
   close the open question of exactly how much of a future controller ensemble will use it. Not a
   blocker for this ticket, restated so it isn't lost.

## §104.15 Definition of done

- [ ] `sim/integrate.py`: `_pending_events`, `_SegmentedSol`, `_SegRK45Raw`, `_run_segmented_rk45`
      implemented per §104.5-§104.7; `run_sim`'s gate + dispatch updated per §104.7; module + `run_sim`
      docstrings updated; `_run_rk4` and the plain-RK45 branch have **zero diff**.
- [ ] `sim/params.py` + `configs/scenarios/_TEMPLATE_scenario.py`: doc-comment/table-row updates per
      §104.8; `tests/test_template_docs.py` still green.
- [ ] `tests/test_integrate.py`: ~15 new tests per §104.11, all passing; the four pre-existing gate
      tests re-run unchanged and still passing.
- [ ] §104.10's four grep commands re-run, zero surprising matches.
- [ ] Point-in-time run: `python -m pytest tests/test_integrate.py tests/test_sampling.py -q` green.
- [ ] Full suite green in background per `CLAUDE.md`'s convention. **Expected count: 705 + ~15 new =
      ~720 passed, 0 failed.** Any failure outside `tests/test_integrate.py` is an undiscovered
      regression — report it, do not silently patch around it.
- [ ] §104.12's performance comparison measured and reported (developer, then independently
      re-measured by QA) — both single-flight and 100-sample/4-worker ensemble wall times, `rk4` vs
      `rk45_seg`, same scenario as qa-report-2.17-step105.md §7.
- [ ] `code-review` skill run before handing to QA (project convention, feature branch
      `feature/sim-paper-alignment`).

### [STEP-104] Segmented RK45 + zero-order-hold sampled-data path (D-116/D-128)
- **Module/boundaries:** `sim/integrate.py` (new functions + `run_sim`'s gate/dispatch/docstrings),
  `sim/params.py` (one comment line), `configs/scenarios/_TEMPLATE_scenario.py` (one table row),
  `tests/test_integrate.py` (new section).
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false — `sim/integrate.py` and `sim/params.py` are shared, frequently-touched
  modules on this branch; sequence against any other in-flight ticket editing them, do not run
  alongside one in parallel.

Implement per §104.4-§104.8 above; write §104.11's tests first where practical (TDD skill, pure
`_pending_events`/`_SegmentedSol` tests have no reason to wait on the integration loop); verify
§104.9's "no new guard needed" claims and §104.10's pin-safety greps after implementation; measure and
report §104.12 before handing to QA; tick off §104.15 before handing to QA.
