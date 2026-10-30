# Architecture 37 — Step 32 (Phase 3): the 3D integration harness

## Кратко (RU)

- Тикет на **Step 32** в его живой (не roadmap-овской) трактовке: не «3D-графики и регрессия», а
  **интеграционная обвязка 3D** — то, что research-нота `3d-readiness-proposal.md` §3.2/§5 Stage 3
  называла «Step 30b», а `task-30` §30.15 перечислял как перенесённое в Step 30b.
- **Главный вывод этого раунда:** сцепление 2D/3D в `integrate.py` оказалось **существенно тоньше**,
  чем утверждала нота. Все пять событий (земля/апогей/выгорание/сход с рельсы/парашют) читают из
  состояния только `y[X]`, `y[Z]`, `y[VZ]` — и все пять делегируют в функции, которые уже сегодня
  корректно работают на 7-компонентной «проекции» 3D-состояния (`forces3d._s2d`). Из-за этого
  появляется **третий, более дешёвый вариант**, которого нота не видела (см. SS37.2, вариант C).
- **Развилка для пользователя (одна, настоящая):** SS37.2 — абстракция раскладки состояния vs.
  параллельный `run_sim_3d` vs. «шов проекции + тонкие 3D-драйверы». Рекомендация архитектора — C.
- **Вопрос про LaTeX (нота §5.0) закрыт и не живой:** `rocket-3d.tex` (24 КБ, 8 подразделов) уже
  вписан на Step 30 по варианту L-a. Step 32 новой физики не добавляет → **правок LaTeX не нужно**,
  `dev/docs/latex/` для этого тикета read-only.
- **Регрессия 2D/3D частично уже есть** (`tests/test_dynamics3d.py`: два полнотраекторных планарных
  теста), но на уровне *производных*, а не обвязки: они сами зовут `solve_ivp` и берут `t_ground` из
  2D-прогона. Step 32 нужен **свой** тест, где 3D-обвязка сама находит все пять событий (SS37.6).
- **Устарело в ноте:** весь §4 (развилка по `I_a`) и Stage 0/Stage 1 — Step 30 закрыл их шире
  (полный симметричный тензор 6 компонент, общие уравнения Эйлера, `apps/sim/engine/inertia.py`).
  Не переоткрывать.
- **Границы:** аэродинамика 3D (Step 31) заблокирована данными пользователя; обвязка проектируется
  под `M_x = M_z = 0` — ровно то, что уже умеет `forces3d.moment_body_3d`. Новой аэро-физики нет.
- **Найден настоящий баг (SS37.0.4, не было ни в ноте, ни в `task-30`, ни в тестах):**
  `forces3d._s2d` восстанавливает 2D-угол тангажа через `quaternion.to_euler`, у которого диапазон
  `arcsin` — `[-90°, +90°]`; за пределами угол **складывается** (135° → 45°, 170° → 10°, измерено).
  Нарушен явный контракт самого `to_euler` («интегрируемое состояние эту функцию не зовёт»).
  Дефолтный пуск в проекте вертикальный (`rail_angle_deg = 90.0`), а «до земли» — это баллистический
  спуск, где угол гарантированно выходит из диапазона → **без фикса главный deliverable шага
  недостижим**. Починка — 3 строки через `atan2`, и она **бесплатна только если идёт первой**
  (на 3D-пути сегодня нет ни одного `array_equal`-пина). Вынесено в подшаг **32.0** / D-32.9.

---

## Table of contents

| Anchor | Section |
|---|---|
| SS37.0 | Input status — what is confirmed, what is stale |
| SS37.1 | Refreshed coupling table (replaces the note's §3.2) |
| SS37.2 | **Decision D-32.1 — the one real fork** (user gate) |
| SS37.3 | Scope decisions needing the user (D-32.2, D-32.3) |
| SS37.0.4 | **NEW FINDING** — `_s2d` folds pitch past ±90° (blocks "end-to-end" on its own) |
| SS37.4 | Architect-made decisions (D-32.4 .. D-32.9) |
| SS37.5 | LaTeX — no edit needed (closes the note's §5.0) |
| SS37.6 | 2D/3D regression — what exists, what Step 32 must add |
| SS37.7 | Staged sub-step breakdown (files / gates / pin risk) |
| SS37.8 | Deliberately out of scope |
| SS37.9 | Definition of done, risks |
| SS37.10 | Tickets (parallel-launch format) |

**Numbering note.** `D-32.x` are ticket-local decision ids, the same convention `task-30` used
(`D-30.5` etc.). Global `D-NN` ids are assigned by the orchestrator when a decision is answered;
the last live global id observed while writing this was `D-162`.

---

## SS37.0 Input status — what is confirmed, what is stale

Re-measured against the working tree on 2026-10-30 (post Phase 2.19/2.20 restructure, so every path
in the two source documents is stale by one rename: `sim/` → `apps/sim/engine/`, `configs/` →
`apps/sim/schema.py`).

### SS37.0.1 Stale — do not re-open

| Source claim | Status |
|---|---|
| Note §4 (the whole `I_a` fork), §4.4's comparison table, §4.5's `I_a(t)` sub-fork | **Superseded by Step 30.** The user chose the full 6-value symmetric tensor, body axes not assumed principal, `I_yy == I_zz` not assumed (`params.Inertia`, `apps/sim/engine/inertia.py`, 189 lines). A scalar `I_a` fork no longer exists to resolve. |
| Note §5 Stage 0 / Stage 1 | **Done** (Step 30, commits `eef31df`/`2c11275`). |
| Note §5.0 (LaTeX authorisation, options L-a/L-b/L-c) | **Resolved and closed** — L-a was taken: `dev/docs/latex/sections-ai/rocket-3d.tex` exists, 24.1 KB, 8 subsections through `sec:3d_state`. See SS37.5. |
| Note §3.2's `I_a`-driven framing of `forces3d` | Partly stale: `moment_body_3d` now exists and is wired, but still through `_s2d`. See SS37.0.2. |
| Note §3.1's "`sim/integrate.py` — 759 lines" | Now **796** (`apps/sim/engine/integrate.py`). |

### SS37.0.2 Confirmed — still true, still the blocker

1. **`forces3d._s2d` is still the only bridge, and still documented as disposable.**
   `apps/sim/engine/forces3d.py:83-91` builds `[r[0], r[2], v[0], v[2], theta, omega[1], 0.0]` fresh
   per call; the module docstring (lines 50-56) still says it "claims validity" only for planar
   attitude and that Step 31 "replaces the whole adapter". Confirmed: **a non-planar 3D run is not
   physically meaningful today**, independently of the harness.
2. **`dynamics3d.derivatives_3d` is reachable only from its own unit test.** Nothing in
   `apps/sim/engine/integrate.py` imports `state3d`, `dynamics3d` or `forces3d`
   (verified: `integrate.py:95-98` imports only `aero, control, dynamics, forces, roll`,
   `dynamics.derivatives`, `state.{State, VZ, Z, to_vector}`, `gravity`, `thrust_curve`).
3. **No 3D scenario can be flown to the ground.** There is no `run_sim_3d`; `run_sim(p, s0: State)`
   takes the 2D `State` NamedTuple and calls `to_vector(s0, p)`.
4. **Numeric pins:** `tests/test_integrate.py` — 27 tests, **7** `np.array_equal` assertions (D-77).
   The in-house `rk4` is version-stable, the scipy `RK45` path is not (`CLAUDE.md`).
5. **Step 31 is blocked** on real airframe geometry (user data). Out of scope here.
6. **`forces3d` hardcodes `hold = None`** (`flow_fb_coeffs_3d:123`, `moment_body_3d:185`): the
   sampled-data / zero-order-hold machinery has no 3D path at all. Relevant to D-32.2.
7. **Line counts** (`wc -l`, 2026-10-30): `integrate.py` 796, `control.py` 579, `report.py` 407,
   `plotting.py` 146, `dynamics3d.py` 110, `forces3d.py` 187, `state3d.py` 71, `inertia.py` 189,
   `dynamics.py` 475, `_shared/flight_stats.py` (20.7 KB).

### SS37.0.3 New facts the note did not have

- **The 2D state is already variable-width.** Step 109 gave `apps/sim/engine/state.py` a `width(p)`
  of 7 or 10 (`N_BASE`/`N_ROLL`) and `to_vector(s, p)` trims the roll block. `integrate.py` and
  `dynamics.py` already carry width-agnostic comments (`Result.y` is documented as
  "shape (width, N); width is 7 or 10"). So **`integrate.py` already tolerates more than one state
  layout** — precedent exists, and the note's "written entirely against the 7-component vector" is
  no longer accurate.
- **`assemble()` already validates inertia** (`apps/sim/schema.py:407`:
  `inertia_mod.validate(p.inertia, roll=p.roll)`), so `task-30` §30.15's "call `inertia.validate`
  from a 3D run entry point" is covered for every config-built `Params`, and only hand-built
  `Params` (i.e. every test) are unguarded. See D-32.6.
- **The rail is specified by elevation only** (`params.Site.rail_angle_deg`; `azimuth_deg` is the
  direction of `+x`, not a rail-vs-`x` offset). So the 3D rail unit vector is an **exact** embedding
  `(cos ε, 0, −sin ε)` of `dynamics._e_rail` — no new physics, no new parameter. See D-32.5.

### SS37.0.4 NEW FINDING — `_s2d` folds pitch past ±90°, and this blocks "end-to-end" by itself

Found while re-confirming the note's claims; **not in the note, not in `task-30`, and not covered by
any existing test.** `forces3d._s2d` recovers the 2D pitch angle as

```python
_yaw, theta, _roll = quaternion.to_euler(q)   # forces3d.py:90
```

and `quaternion.to_euler`'s own docstring (`quaternion.py:169-175`) says:

> *"Singular at `pitch = +-90 deg` (module docstring) — **not handled specially here, since the
> integrated state never calls this function at that attitude** (it uses the quaternion directly);
> `plotting.py`-style human-readable output is **this function's only intended caller**."*

That precondition is **violated**: `_s2d` calls `to_euler` on the integrated state on *every* RHS
evaluation. `pitch = arcsin(clip(-R[2,0]))` has range `[-90°, +90°]`, so pitch **folds**. Measured
directly (`from_euler(0, θ, 0)` → `to_euler`, this working tree, 2026-10-30):

| `θ` in | `to_euler` pitch | `atan2(-R[2,0], R[0,0])` |
|---|---|---|
| 45° | 45.0000° | 45.0000° |
| 89.9° | 89.9000° | 89.9000° |
| 90.0° | 90.0000° | 90.0000° |
| **95°** | **85.0000°** ✗ | 95.0000° ✓ |
| **135°** | **45.0000°** ✗ | 135.0000° ✓ |
| **170°** | **10.0000°** ✗ | 170.0000° ✓ |
| **−135°** | **−45.0000°** ✗ | −135.0000° ✓ |

Why this matters more than a precision nit: the recovered `theta` always has `cos θ ≥ 0`, i.e. **the
adapter reports the nose pointing downrange no matter where it actually points.** A rocket at 135°
(nose up and back over the pad) is handed to `flow.flow_state`/`forces.aero_force_body` as 45°, so
`alpha` and the whole aerodynamic force are computed for the wrong attitude — silently, with no
warning.

And it is **not an edge case for this step**:

- `Site.rail_angle_deg` defaults to **90.0** — the project's default launch is exactly vertical,
  i.e. exactly on the singularity (the round trip happens to be exact *at* 90°, but any tip past
  vertical folds immediately);
- "fly a 3D scenario end-to-end **to the ground**" necessarily includes ballistic descent, where 2D
  `theta` leaves `(−90°, 90°]` routinely. 2D `theta` is integrated and **unwrapped**; the
  quaternion recovery is not.

So the harness cannot deliver its own headline capability on top of the current `_s2d`. Existing
tests do not catch it: both full-trajectory tests use `θ₀ = 45°` with either `C_m = 0` (θ exactly
constant) or a deliberately short 2 s span chosen, per its own docstring, to stay "comfortably
inside that range".

**→ D-32.9, and sub-step 32.0 (first, before anything else).**

---

## SS37.1 Refreshed coupling table (replaces the note's §3.2)

The note counted *modules that import the 2D state layout* (11 of 26 then; **13** now — `aero`,
`control`, `dynamics`, `flow`, `forces`, `gravity`, `integrate`, `plotting`, `report`, `roll`,
`rotation`, `soundings`, plus `apps/_shared/flight_stats.py`). That count answers the question
"what would a *unification* on one state vector cost" — which is still a phase, not a step, and is
still not what Step 32 does.

The question Step 32 actually has to answer is narrower: **what does the harness itself read out of
the state vector.** Measured directly:

| Harness element | `integrate.py` lines | Reads from the state | Works on `_s2d(y3d)` verbatim? |
|---|---|---|---|
| `_ground_event` | 109-122 | `gravity.ground_depth(t, y, p)` → `y[Z]`, `y[X]` | **Yes** |
| `_apogee_event` | 125-150 | `y[VZ]` | **Yes** |
| `_burnout_event` | 156-189 | `thrust_curve.thrust(t, y, p)` → `y[Z]`, `y[X]` | **Yes** |
| `_rail_exit_event` | 192-210 | `dynamics.rail_distance(y, p)` → `y[X]`, `y[Z]` | **Yes** |
| `_parachute_deploy_event` | 213-229 | `forces.parachute_deployed(t, y, p)` → `y[VZ]`, `t` | **Yes** |
| `run_sim` RK45 branch | 760-788 | `to_vector(s0, p)`, `derivatives`, the 5 events | needs `y0` + RHS swapped only |
| `_run_rk4` loop | 338-426 | same 5 predicates + `derivatives(t, y, p, hold)` | same |
| `_run_rk4` crossing block | 364-418 (~55 lines) | `y[VZ]` directly (line 367-368) + the 4 delegates | one direct index to project |
| `_run_segmented_rk45` | 516-619 | + `sampling.sample(t, y, p, prev=hold)` → control laws | **No** — see D-32.2 |
| `_warn_if_mach_blind` | 791-796 | `mach_warning.peak_mach(result)` → `flow_state` per column | needs a projected `Result` |
| `_LinearInterpolant`, `_SegmentedSol`, `_pending_events`, `Result` | 232-256, 439-513 | nothing layout-specific | **Yes, already layout-agnostic** |

**Downstream (the roadmap's original "Step 32 output" scope):**

| Module | Lines | 2D indices used | What a 3D run needs |
|---|---|---|---|
| `apps/sim/engine/plotting.py` | 146 | `X, VX, VZ, THETA, OMEGA` (lines 43, 82, 115-117) | new 3D-only functions: ground track (x-y), 3D trajectory, Euler-angle histories |
| `apps/sim/engine/report.py` | 407 | `X, Z, VX, VZ, THETA, OMEGA` (line 28) | `flight_summary` is the only piece worth a 3D twin; `static_margin_cal` / `cm_slope_series` / `stability_check` / `sweep` are deeply 2D-aero and belong with Step 31 |
| `apps/_shared/flight_stats.py` | 20.7 KB | `M, THETA, VX, VZ, X` (line 62) | **out of scope** — it is the apps-layer statistics surface, consumed by `apps/analysis`/`apps/optimization`, all of which are 2D by the user's own Phase-3 scope ruling |
| `apps/sim/engine/control.py` | 579 | `VZ` only (line 109) | **nothing.** The note's "pitch-only feedback/actuator needs a 2-axis law" is a *control-law* claim, not a harness claim — and it is a product decision (`task-30` §30.15). The harness runs with the control path inert. |

**Net correction to the note.** The harness coupling is ~6 touch points, not 796 lines, and five of
the six are already satisfied by an adapter that exists and is tested. The note's "strictly larger
than Steps 30, 31 and 32 combined" was written before `_s2d` had been proven against a full
trajectory (`tests/test_dynamics3d.py::test_planar_3d_matches_phase1_2d_trajectory`) and before
Step 109 had already made `integrate.py` width-tolerant. **Revised estimate: comparable to Step 30,
not larger than 30+31+32.** The expensive version is still available (SS37.2 option B) — but it is
now a choice, not a necessity.

---

## SS37.2 Decision D-32.1 — the one real fork (USER GATE)

**Purpose of the component:** let a 13-component 3D state be flown end-to-end by
`apps/sim/engine/integrate.py` — ground impact, apogee, burnout, rail exit, parachute deploy — with
the 2D path's seven `np.array_equal` pins (D-77) intact.

This is the fork the research note explicitly refused to make in passing (§5 Stage 3, lines 325-330).
Option C did not exist when the note was written; it is the product of SS37.1's measurement.

| Option | What it is | Pros | Cons | Cost | Pin risk |
|---|---|---|---|---|---|
| **A — parallel `run_sim_3d`, full duplication** (the note's own lean) | A new `run_sim_3d(p, s0_3d)` plus its own copies of the five event functions and its own rk4 loop, in `integrate.py` or a new `integrate3d.py`. Nothing in the 2D code path is edited. | Zero-pin-risk by construction: the 2D bytes are untouched, so the pins cannot move even in principle. Reviewable in isolation. Fastest to a working 3D flight. | Duplicates ~250 lines of event/crossing logic that is *already* known to work on a projected state. Permanent drift surface: any future 2D event fix (the kind Step 42/47/48/104 each made) must be made twice, and the second copy will be forgotten. Contradicts the project's own "the EXACT same extracted formula, not a hand-copied duplicate" discipline (`forces3d.moment_body_3d` D-30.7). | ~250-300 new lines, ~10-14 new tests | **None** |
| **B — shared state-layout abstraction** | A `StateLayout` seam (`n`, `to_vector`, `rhs`, index/projection accessors) injected into **one** generalised loop; `run_sim` and `run_sim_3d` are both thin callers of it. The deep-module answer. | One implementation of the event/crossing/segmentation machinery forever. Makes a future 3D `rk45_seg`, a 3D mass model, or a 4th layout nearly free. Deepest module, best long-run navigability (`codebase-design` vocabulary: a single narrow interface over the widest implementation). | Requires rewriting the interior of a 796-line file where every pinned number in the project is produced. Bit-for-bit identity of the 2D path becomes a *claim to be proven by the pins* rather than a property of the diff. Largest upfront cost, and the cost lands on the riskiest file. Also the highest chance of a multi-round QA cycle. | ~150 changed + ~120 new lines in `integrate.py`, ~12-16 new tests, plus a full-suite gate per sub-step | **High** — the real one |
| **C — projection seam + thin 3D drivers** *(recommended)* | Keep the five event functions **exactly as they are** and reuse them verbatim for 3D by handing them `forces3d._s2d(y)` through a one-line projection wrapper built by a small factory (`_events_for(project)`); add a thin `run_sim_3d` that reuses `Result`, `_LinearInterpolant` and `_pending_events` unchanged, with its own ~55-line copy of only the rk4 crossing block. The 2D path's projection is the identity and is never constructed. | Reuses the five predicates *literally* — the one thing option A duplicates and the one thing option B risks. Duplication shrinks from ~250 lines to ~55 (the rk4 crossing arithmetic only). No line inside `run_sim`/`_run_rk4`/`_run_segmented_rk45` changes, so the pins are as safe as under A. Leaves option B reachable later as a pure refactor, with a working 3D flight already pinned to compare against. | Two drivers still exist, so it is not the final architecture — the rk4 crossing block is duplicated and must carry an explicit "mirror of `_run_rk4:364-418`" marker. Introduces one new indirection (`_events_for`) into a file that currently has none. | ~110-140 new lines, ~10-14 new tests | **Near-none** (new code only; one new module-level factory added above the pinned functions) |

**Architect's recommendation: C.** The deciding fact is empirical, not stylistic: all five event
predicates were measured to read only `y[X]`, `y[Z]`, `y[VZ]`, and `forces3d._s2d` already supplies
exactly those three from a 3D state and is already validated against a full 2D trajectory. Option C
is therefore the only option that gets A's pin safety *and* B's non-duplication of the part that
matters. B remains the right end state; it should be a later, standalone refactor whose acceptance
criterion is "the 3D pins from Step 32 and the 2D pins from D-77 both hold unchanged" — which Step 32
under option C is precisely what creates.

**Question to put to the user:** A, B or C?

---

## SS37.3 Scope decisions needing the user

### D-32.2 — which solver paths get a 3D driver?

**Purpose:** `run_sim` has three paths (`RK45` adaptive, in-house fixed-step `rk4`,
`rk45_seg` segmented + zero-order hold). Which must `run_sim_3d` support in Step 32?

| Option | Content | Pros | Cons | Cost |
|---|---|---|---|---|
| **S1 — `rk4` only** | Fixed-step only. The committed 3D reference trajectory is an `rk4` pin (version-stable per `CLAUDE.md`), which is exactly what the note's Stage 2 asked for. | Smallest. Gives a pinnable 3D reference immediately. No adaptive-event-location subtleties. | No adaptive 3D run, so a 3D flight is `dt`-resolution-limited on events (~one `dt`), and no dense output of solver quality. Users comparing 2D-RK45 to 3D-rk4 compare two different integrators. | ~70 lines |
| **S2 — `rk4` + `RK45`** *(recommended)* | Both un-sampled paths. `RK45` gives solver-tolerance event location (so the 2D/3D equivalence test compares like with like against `run_sim`'s default); `rk4` carries the committed numeric pin. | Covers every scenario a 3D run can express today. Event-location equivalence against the 2D default path becomes testable. `RK45` trajectories are **not** pinned (version-unstable — `CLAUDE.md`, D-77), only asserted against 2D to tolerance. | Two drivers instead of one (though they share the events under D-32.1/C). | ~130 lines |
| **S3 — all three** | Adds `rk45_seg` + the zero-order-hold/sampled-data path. | Complete parity with `run_sim`. | **Requires a 3D control law**, which `task-30` §30.15 routes to *product*, not architecture; `forces3d` currently hardcodes `hold = None` in two places, so the whole hold contract would have to be designed for 3D first. Pulls a product decision into an integration step. | ~230 lines + a blocked product decision |

**Recommendation: S2.** `rk45_seg` is gated behind a product decision the project has deliberately
not taken; including it would make Step 32 blocked for the same reason Step 31 is. `run_sim_3d`
raises `ValueError` eagerly on `sample_rate_hz > 0.0` or `method == "rk45_seg"` (same eager-validation
convention as `run_sim`'s actuator/roll guards, `integrate.py:683-748`).

### D-32.3 — how much 3D output is in Step 32?

**Purpose:** the roadmap's original Step 32 title is "3D output and regression"; `task-30` §30.15
routes "3D output: ground track, Euler-angle histories, 3D flight summaries" to Step 32. The harness
itself produces no human-visible artefact.

| Option | Content | Pros | Cons | Cost |
|---|---|---|---|---|
| **O1 — harness only, output deferred** | `run_sim_3d` + tests. No plotting, no report. | Smallest step, single concern, fastest to merge. | Step 32 then has no deliverable a user can look at, and the roadmap's Step 32 title is left unmet — the work would have to be re-scheduled as yet another step. | 0 extra |
| **O2 — harness + minimal 3D output** *(recommended)* | Additive, 3D-only: `plotting.plot_ground_track_3d` (x-y), `plotting.plot_trajectory_3d`, `plotting.plot_attitude_history_3d` (yaw/pitch/roll from `quaternion.to_euler`), and `report.flight_summary_3d` (apogee alt/time, impact time, max-Q via the projection). Existing 2D functions untouched. | Meets the roadmap's Step 32 in one step. Every new function is additive and 2D-pin-free. Gives the harness a visible acceptance artefact (a ground track that is a straight line for a planar run is itself a check). | +~120 lines across two files, +4-6 tests (matplotlib `Agg`, per `tests/test_plotting.py`'s own convention). | ~120 lines |
| **O3 — O2 + full `report.py` 3D parity** | Also 3D `static_margin_cal`, `cm_slope_series`, `stability_check`, `sweep`. | Complete reporting parity. | All four are **aero-stability** functions resting on `C_z`/`C_m` slopes and `alpha` — i.e. exactly Step 31's blocked content. A 3D static margin computed through `_s2d` would be a planar number wearing a 3D label: actively misleading. | ~300 lines, and partly wrong until Step 31 |

**Recommendation: O2.** O3 is rejected on correctness grounds, not cost (see SS37.8).

---

## SS37.4 Architect-made decisions (no user gate needed)

These are implementation choices with no cost, no physics content and no alternative worth a user's
attention. Recorded so the developer does not re-open them.

- **D-32.4 — quaternion renormalisation.** Carried from `task-30` §30.6 ("pick between
  per-accepted-step projection and a solver event, and only then"). **Decision:** on the `rk4` path,
  project with `quaternion.normalise` once per accepted step, **after** the crossing-detection block
  and before `ys.append` — a step boundary is the only place a projection is consistent with the
  method. On the `RK45` path, **do not** project: `solve_ivp` builds its error estimate and dense
  output from RHS evaluations, so there is no accessible accepted-step hook, and a solver *event*
  cannot mutate state in scipy. Instead keep `task-30` §30.9 test 18's drift assertion as the gate:
  `abs(norm(q) - 1) < 1e-9` over a full flight. `derivatives_3d` keeps **not** renormalising
  (task-30 §30.6 reason 1 stands). Rationale for the asymmetry: `rk4` is where the committed pin
  lives and where projection is free and exact; `RK45` is where projection is unavailable and where
  the drift is already measured and bounded.
- **D-32.5 — the 3D rail and parachute attitude freeze.** `task-30` §30.15 flags this as a
  must-not-forget: `dynamics.derivatives` freezes `dtheta/dt` and `domega/dt` while
  `on_rail(y, p)` or `forces.parachute_deployed(t, y, p)` (`dynamics.py:394-432`), and the 3D path
  has no such branch. **Decision:** the freeze goes in `dynamics3d.derivatives_3d`, not in the
  harness — it is a property of the equations of motion, exactly as it is in 2D, and putting it in
  the integrator would split one physical constraint across two modules. Mechanics:
  - predicates reused verbatim on the projection: `on_the_rail = dynamics.on_rail(_s2d(y), p)`,
    `chuted = (not on_the_rail) and forces.parachute_deployed(t, _s2d(y), p)`; one `_s2d` call shared
    (the `flow_fb_coeffs_3d` sharing precedent);
  - when frozen: `dydt[Q] = 0.0` **and** `dydt[OMEGA] = 0.0` (the 3D twin of `dtheta/dt = omega = 0`
    plus `domega/dt = 0` — note that in 3D the *attitude* derivative is `q_dot`, so both must be
    zeroed, where 2D needed `dydt[THETA] = 0` explicitly);
  - on the rail, translational acceleration is projected onto the **exact** 3D rail embedding
    `e_rail_3d = (cos ε, 0, −sin ε)` built from `dynamics._e_rail(p)` by inserting a zero
    y-component — the same exact-embedding argument `forces3d`'s module docstring makes for gravity
    and thrust (`Site` carries no rail azimuth relative to `+x`, so an out-of-plane rail is not
    expressible and is not new scope);
  - under the canopy, `forces.parachute_drag_inertial(t, _s2d(y), p, None)` returns a 2D inertial
    vector, embedded `(Fx, 0, Fz)` — again exact, since a round canopy is axisymmetric
    (`dynamics.py:411-425`'s own reasoning, and `roadmap.md` B2).
  - **Bit-for-bit guarantee:** `p.site.L_rail <= 0.0` (default) and `p.recovery` off (default) make
    both predicates false from the first call, so this block is unreachable for every existing 3D
    test. `tests/test_dynamics3d.py`'s 8 tests must not move.
- **D-32.6 — eager validation in `run_sim_3d`.** Mirroring `run_sim:683-748`, and closing
  `task-30` §30.15's "`inertia.validate` from a 3D run entry point". `run_sim_3d` raises
  `ValueError` immediately, before any integration, on:
  1. `inertia.validate(p.inertia, roll=p.roll)` failing (covers hand-built `Params`, which
     `assemble()`'s own call at `apps/sim/schema.py:407` does not reach);
  2. `p.roll.model != "none"` — the 2D decoupled roll DOF (Step 109) and the 3D `omega[0]` are the
     *same* physical degree of freedom (the research note §5.1 proves the roll equation is identical
     in both), so running both at once double-counts roll. Message must say so explicitly and point
     at `Inertia.I_xx` as the 3D home;
  3. `p.weight.m_d is not None` — there is no 3D variable-mass model; the 13-component layout has no
     mass slot and `_s2d` passes `0.0` for `M` (`forces3d.py:44-48`). A set `m_d` would silently
     make `weight_inertial` read that `0.0` as the vehicle's mass. This is a latent trap *today*;
     the guard closes it;
  4. D-32.2's solver-path guards (`sample_rate_hz > 0.0`, `method == "rk45_seg"`);
  5. `p.actuator.model` unregistered — reused from `run_sim` verbatim.
- **D-32.7 — the Mach diagnostic.** `_warn_if_mach_blind` → `mach_warning.peak_mach(result)` walks
  `result.y` columns through `flow_state`, which is 2D. **Decision:** `run_sim_3d` calls it on a
  *projected* `Result` built by a 3-line local helper (`y` columns mapped through `_s2d`), leaving
  `apps/sim/engine/mach_warning.py` untouched. Peak Mach of a planar 3D flight is then identical to
  the 2D answer by construction, and the module keeps one state contract.
- **D-32.8 — where the code lives.** `run_sim_3d`, `_events_for` and the 3D drivers go in
  **`apps/sim/engine/integrate.py`**, not a new `integrate3d.py`. Reason: under option C they share
  `Result`, `_LinearInterpolant`, `_pending_events` and the five event functions, all of which are
  module-private; a second module would either import privates across a boundary or force them
  public. `integrate.py` grows to ~930 lines, which is within what the project already tolerates
  (`aero.py` is 908). Revisit only if D-32.1 resolves to **A** — full duplication *does* justify a
  separate file, since then nothing is shared but `Result`. *(If the user picks A, the developer
  should raise this back as a 1-line follow-up rather than deciding silently.)*
- **D-32.9 — fix `_s2d`'s pitch recovery with `atan2`, as sub-step 32.0, before anything else.**
  The finding is SS37.0.4. **Decision:** replace
  `_yaw, theta, _roll = quaternion.to_euler(q)` in `forces3d._s2d` with a direct DCM extraction
  ```python
  R = quaternion.to_dcm(q)
  theta = math.atan2(-R[2, 0], R[0, 0])    # full (-pi, pi], no arcsin singularity
  ```
  which is **exact** for any pitch-only `q` (verified across −135°…+170°, SS37.0.4's table) and is
  the standard 3-2-1 pitch whenever roll and yaw are zero — which is precisely `_s2d`'s documented
  contract. No new parameter, no new physics, ~3 lines.
  - **Why it must be first, not folded into 32.2:** it changes `derivatives_3d`'s numerical output
    (at rounding level for `|θ| < 90°`, qualitatively beyond it), so doing it *after* sub-step 32.3
    would move the brand-new 3D `rk4` pin. Doing it first makes it free: **the 3D path has no
    `np.array_equal` pins at all today** (status.json, Step 30: the 3D path "had no pin tests
    whatsoever" before Step 30, and Step 30 added none of the `array_equal` kind).
  - **Scope discipline:** this fixes the *planar* adapter's pitch recovery only. It does **not**
    make `_s2d` valid for non-planar attitude — that remains Step 31's replacement of the whole
    adapter (SS37.8). Update `forces3d`'s module docstring accordingly, and `quaternion.to_euler`'s
    docstring claim "this function's only intended caller is plotting-style output" becomes true
    again.
  - **Residual, documented not fixed:** `atan2` is still wrapped at ±π, so it cannot represent a
    multi-revolution tumble the way 2D's integrated `theta` can. Every downstream consumer reaches
    `theta` through `sin`/`cos` (`flow.flow_state`, `forces.*`, `rotation`), for which wrapping is
    immaterial; the one place it is visible is a *reported* theta history, where 2D and 3D may
    differ by `2πk`. Any 2D/3D theta-history comparison test must compare `sin`/`cos` or wrap both
    sides — state this in the test.
  - **Tests:** the SS37.0.4 table itself becomes a test (`tests/test_forces3d.py` or
    `tests/test_dynamics3d.py`): round-trip `θ ∈ {45, 85, 89.9, 90, 95, 135, 170, −135}°` through
    `from_euler` → `_s2d` and assert the recovered `theta` matches to `1e-12`. Plus: all 8
    `tests/test_dynamics3d.py` tests must still pass (they use `θ₀ = 45°`, where the change is at
    rounding level and their tolerances are `1e-6`).

---

## SS37.5 LaTeX — no edit needed (closes the note's §5.0)

**Plainly: Step 32 requires no change under `dev/docs/latex/`, and the directory is read-only for
this ticket.** Three independent reasons:

1. **The note's §5.0 question is no longer live.** It asked whether the user's "+ in latex" authorised
   editing `main.tex` under the 2026-10-15 freeze. That was answered in Step 30 by taking option
   **L-a**: `dev/docs/latex/sections-ai/rocket-3d.tex` exists (24.1 KB; `sec:rocket3d`,
   `sec:3d_scope`, `sec:3d_attitude`, `sec:3d_inertia`, `sec:3d_admissibility`, `sec:3d_eom_rot`,
   `sec:3d_moment`, `sec:3d_state`). `task-30` §30.15 records "**Any further LaTeX work — None,
   already done** (§30.14.1, D-30.15)". There is nothing to re-ask.
2. **Step 32 introduces no new physics content.** Everything in it is numerics or presentation:
   event location, step loops, a projection adapter, plots. The one item with any claim to paper
   content is the rail/parachute attitude freeze (D-32.5) — and that is a *re-statement one dimension
   up* of a constraint already documented (`models.tex`/`roadmap.md` B1/B2, and `rocket-2d.tex`'s own
   conventions), with an exactness argument that belongs in the code docstring, not a new equation.
3. **The only plausible LaTeX home is already a deferred decision.** Quaternion renormalisation and
   event-location tolerance are numerical-integration topics, and the project already has a recorded
   deferred decision to write a separate LaTeX "Numerical integration" section (status.json,
   2026-10-13). Step 32 should add a **backlog line** to that item, not a section.

**Do not manufacture a decision here.** If the user later wants the harness documented in the paper,
it is the deferred "Numerical integration" section, scheduled on its own.

**Noted, not acted on:** `rocket-3d.tex` and `task-30` still cite pre-restructure paths (`sim/...`,
`configs/schema.py`). The user consciously accepted LaTeX path drift (decision 2026-10-27) and a
separate pass fixed `appendix.tex` (2026-10-29). Not Step 32's job; listed in SS37.8.

---

## SS37.6 2D/3D regression — what exists, what Step 32 must add

**Direct answer to "is the planar-case-matches-Phase-1 test already done by Step 30?" —
partially, at the wrong level.**

What **already exists** in `tests/test_dynamics3d.py` (8 tests):

| Test | Line | What it proves | Level |
|---|---|---|---|
| `test_planar_3d_matches_phase1_2d_trajectory` | 45 | A **full-trajectory** planar 3D run matches the Phase-1 2D `run_sim` trajectory to `rtol=1e-7, atol=1e-4` in x/z, with `r[1]`, `v[1]` **exactly** `0.0` at every sample | derivatives + raw `solve_ivp` |
| `test_derivatives_3d_cross_checks_derivatives_2d_pointwise` | 110 | RHS-level agreement at matching states, to machine precision | derivatives |
| `test_planar_3d_reproduces_the_phase1_2d_pitch_history` | 198 | `theta`/`omega` histories agree over a 2 s span with a real non-zero `C_m`; `omega[0]`, `omega[2]`, `q[1]`, `q[3]` exactly `0.0` | derivatives + raw `solve_ivp` |
| `test_off_diagonal_inertia_breaks_planarity` | 294 | the planarity assertions are not vacuous | derivatives |
| `test_torque_free_tumble_conserves_inertial_angular_momentum` | 377 | the gyroscopic term's sign | derivatives |
| `test_quaternion_norm_drift_is_bounded` | 397 | `abs(norm(q) − 1)` bound | derivatives |

**So the trajectory-level equivalence is covered.** What is **not** covered, and is Step 32's
headline acceptance test, is the *harness* level. Both existing full-trajectory tests:

- call `solve_ivp(derivatives_3d, ...)` **directly in the test body** (lines 69-78, 228-231) — the
  thing Step 32 exists to remove;
- take `t_ground` **from the 2D run** (`result_2d.events["ground"]`, line 58) and integrate to it,
  i.e. the 3D side never **finds** the ground;
- pass **no `events=`** at all: nothing exercises apogee, burnout, rail exit or parachute on the 3D
  side, and nothing exercises termination.

### SS37.6.1 Required new tests (the regression Step 32 owes)

New file **`tests/test_integrate3d.py`** (not an extension of `test_dynamics3d.py` — different
subject, and `test_integrate.py` must stay a pure 2D-pin file):

1. **Harness-level planar equivalence, RK45.** `run_sim_3d(p, s0_3d)` vs `run_sim(p, s0_2d)` on the
   `_P` scenario from `test_dynamics3d.py`: all five `events[...]` entries agree
   (`ground`/`apogee` to `rel_tol=1e-6`; `burnout`/`rail_exit`/`parachute_deploy` to the same, or
   both `None`), and the x/z trajectory agrees to the existing `rtol=1e-7, atol=1e-4`.
   **This is the test that would have caught every bug the harness can have.**
2. **Exact out-of-plane zero through the harness.** `r[1] == 0.0`, `v[1] == 0.0`, `omega[0] == 0.0`,
   `omega[2] == 0.0`, `q[1] == 0.0`, `q[3] == 0.0` at every recorded sample of the 3D `Result` —
   bit-exact, not `allclose`. Proves the events/crossing code introduces no out-of-plane leakage.
3. **Termination.** `run_sim_3d` terminates on ground impact, not at `t_max`: the last sample's
   `ground_depth` crosses zero and `events["ground"] is not None` with `t_ground < t_max`.
4. **Committed 3D reference pin (`rk4`).** The note's Stage 2 deliverable, now reachable through the
   harness: `run_sim_3d` with `params.with_solver(p, method="rk4", dt=...)`, asserted with
   `np.array_equal` against a committed fixture. **Only the `rk4` path is pinned** — the `RK45`
   path is version-unstable (`CLAUDE.md`, D-77) and is asserted against the 2D run to tolerance
   instead, never pinned.
5. **Rail freeze (D-32.5).** `p.site.L_rail > 0` planar run: while `rail_distance < L_rail`,
   `q` is exactly constant and `omega` exactly constant; after rail exit they move; the 2D
   `rail_exit` time matches.
6. **Parachute freeze (D-32.5).** `p.recovery` on, apogee trigger: `q`/`omega` exactly constant
   after `parachute_deploy`; descent rate matches the 2D terminal velocity.
7. **Quaternion norm through a full flight (D-32.4).** `rk4` path: `norm(q) == 1.0` to `1e-15` at
   every sample (projection active). `RK45` path: `abs(norm(q) − 1) < 1e-9`.
8. **Eager-validation guards (D-32.6).** Five `pytest.raises(ValueError)` cases, one per guard,
   each asserting a substring of the message so the diagnostic itself is pinned.
9. **2D pins untouched.** Not a new test — the gate is that `tests/test_integrate.py`'s 27 tests
   and 7 `np.array_equal` assertions pass unchanged, and that `git diff` shows **no change** inside
   `run_sim`, `_run_rk4`, `_run_segmented_rk45` or the five event function bodies (under option C).

### SS37.6.2 What "bit-identical 2D/3D" must **not** mean

Restating the note's §5 Stage-1 warning, because it now applies to the harness too: exact bit
identity of the *trajectory* is not achievable (a 3×3 DCM multiply and a `to_euler` recovery are a
different floating-point op sequence from a 2×2 rotation) and its absence is not a bug. The
achievable and genuinely strong statements are the ones in tests 1-2: **out-of-plane components
exactly `0.0`** (bit-exact, load-bearing), in-plane agreement **to solver tolerance**. Do not write
"bit-identical" into any acceptance criterion for in-plane quantities.

---

## SS37.7 Staged sub-step breakdown

Ordered by information-per-unit-risk, same principle as the note's §5. Each sub-step is one commit
(`Step 32.N (Phase 3): ...`), one full-suite gate. **Sequential — not parallelisable** (SS37.10).

> **Numbering note for the orchestrator:** Phase 3 uses its own step ids (28-32) while the
> Phase-2.x line is at Step 142. `32.1`-`32.5` are sub-step labels inside the existing Step 32
> entry in `dev/status.json`, not new global step numbers. If the orchestrator prefers global ids,
> allocate 143-148 and note the mapping — the architect does not renumber the tracker.

### Sub-step 32.0 — fix `_s2d`'s pitch recovery (BLOCKING PREREQUISITE)

- **Files:** `apps/sim/engine/forces3d.py` (`_s2d`, ~3 lines + module-docstring paragraph),
  `tests/test_dynamics3d.py` **or** a new `tests/test_forces3d.py` (the SS37.0.4 round-trip table).
- **Does:** D-32.9. Without it, "fly a 3D scenario end-to-end to the ground" is not deliverable —
  descent leaves `arcsin`'s range and the aerodynamic attitude silently folds.
- **Gate:** the new round-trip test; `tests/test_dynamics3d.py` 8/8; full suite.
- **Pin risk:** **none.** No `np.array_equal` pin exists on the 3D path, and no 2D module imports
  `forces3d` (verified: `forces3d` is imported only by `dynamics3d`, which `integrate.py` does not
  yet import). This sub-step is free **only if it goes first** — after 32.3 it would move the new
  3D pin.
- **Why not deferred to Step 31:** Step 31 replaces `_s2d` entirely, so this work is thrown away
  then — but Step 31 is blocked on user data with no date, and Step 32's own deliverable depends on
  it. Three lines now, deleted later, is the right trade. Say so in the code comment.

### Sub-step 32.1 — the projection seam and the event factory

- **Files:** `apps/sim/engine/integrate.py` (additive only: `_project_identity`, `_events_for`,
  and a 2D self-test that `_events_for(identity)` returns the same five callables with the same
  `terminal`/`direction` attributes), `tests/test_integrate3d.py` (new).
- **Does:** introduces the seam, wires nothing to 3D yet.
- **Gate:** `python -m pytest tests/test_integrate.py tests/test_integrate3d.py -q`, then full suite
  (background, ~220 s). The five event functions' bodies must be byte-identical in `git diff`.
- **Pin risk:** **none** (new module-level names above the pinned functions; no pinned function is
  edited). If `git diff` touches a pinned function body, the sub-step is wrong.

### Sub-step 32.2 — `run_sim_3d`, RK45 path, with eager validation

- **Files:** `apps/sim/engine/integrate.py` (`run_sim_3d` + the projected-`Result` Mach helper,
  D-32.7), `tests/test_integrate3d.py` (tests 1, 2, 3, 8).
- **Does:** the first end-to-end 3D flight to the ground. Reuses `Result` and the five events via
  `_events_for(forces3d._s2d)`. Guards per D-32.6.
- **Reads from spec:** SS37.2 (chosen option), SS37.3/D-32.2, SS37.4/D-32.6, SS37.4/D-32.7,
  SS37.6.1 tests 1-3 and 8.
- **Gate:** the three equivalence tests green; full suite; `tests/test_dynamics3d.py` 8/8 unchanged.
- **Pin risk:** **none** on the 2D side. New import of `forces3d`/`state3d` into `integrate.py` —
  check for an import cycle (`forces3d` imports `aero, control, dynamics, forces, quaternion, flow,
  state3d`; `integrate` already imports `aero, control, dynamics, forces` — so the new edge is
  `integrate → forces3d`, and `forces3d` does **not** import `integrate`: acyclic, verified).

### Sub-step 32.3 — `run_sim_3d`, `rk4` path + the committed 3D reference pin

- **Files:** `apps/sim/engine/integrate.py` (the 3D rk4 driver — the ~55-line mirror of
  `_run_rk4:364-418`, carrying an explicit "mirror of `_run_rk4`" marker comment per D-32.1/C),
  `tests/test_integrate3d.py` (tests 4, 7).
- **Does:** fixed-step 3D with crossing detection + quaternion projection at accepted steps (D-32.4);
  commits the first numeric pin the 3D path has ever had at trajectory level.
- **Gate:** `np.array_equal` pin green twice in a row (determinism), full suite.
- **Pin risk:** **none existing**; creates a **new** pin. The new pin is `rk4`-based and therefore
  version-stable — do **not** pin an `RK45` 3D trajectory (CLAUDE.md, D-77).

### Sub-step 32.4 — rail and parachute attitude freeze in 3D

- **Files:** `apps/sim/engine/dynamics3d.py` (the freeze branch, D-32.5),
  `tests/test_integrate3d.py` (tests 5, 6), `tests/test_dynamics3d.py` (one added test only if the
  freeze needs an RHS-level assertion; existing 8 must not change).
- **Does:** closes `task-30` §30.15's second carried item.
- **Gate:** the two freeze tests; `tests/test_dynamics3d.py` 8/8 unchanged (the branch is
  unreachable with `L_rail = 0.0` and recovery off — the defaults every existing 3D test uses);
  full suite.
- **Pin risk:** **low, and on the 3D side only.** The 3D pin created in 32.3 uses `L_rail = 0.0` /
  recovery off, so it must not move either — **if it moves, the freeze branch is leaking into the
  unconstrained path** and that is the bug this gate catches. 2D: none.

### Sub-step 32.5 — minimal 3D output (D-32.3 / O2)

- **Files:** `apps/sim/engine/plotting.py` (`plot_ground_track_3d`, `plot_trajectory_3d`,
  `plot_attitude_history_3d` — additive, existing functions untouched),
  `apps/sim/engine/report.py` (`flight_summary_3d` — additive), `tests/test_plotting.py` or a new
  `tests/test_plotting3d.py` (matplotlib `Agg`, per `tests/test_plotting.py`'s existing convention),
  `tests/test_report.py` (1-2 additions).
- **Does:** the roadmap's original Step 32 title.
- **Acceptance detail worth stating:** for a planar run the ground track must be a **straight line
  along x with y exactly 0.0** — the plot is itself a check, and the test should assert the data
  series, not the figure.
- **Gate:** full suite; `output/` artefacts written and visually sane (the one place a human look is
  worth it).
- **Pin risk:** **none** (additive functions; `report.py`'s existing `flight_summary` and the
  sweep/stability functions are not edited).

### Estimate

| Sub-step | New/changed lines | New tests | Risk |
|---|---|---|---|
| 32.0 | ~3 changed + ~15 doc | 1 | none (if first) |
| 32.1 | ~35 new | 1-2 | none |
| 32.2 | ~70 new | 5-7 | none (2D), low (3D) |
| 32.3 | ~65 new | 2-3 | creates a new pin |
| 32.4 | ~35 new (`dynamics3d.py`) | 2-3 | low, 3D only |
| 32.5 | ~120 new | 4-6 | none |
| **Total** | **~343 new, 3 changed in `forces3d`, 0 changed in pinned bodies** | **15-22** | **low** — a material revision of the note's "medium-high / larger than 30+31+32 combined" |

---

## SS37.8 Deliberately out of scope

Each with where it goes instead, so nothing here is a silent omission.

| Item | Goes to |
|---|---|
| 3D aerodynamics: sideslip `beta`, total `alpha`, roll moment from fin cant (`M_x`), yaw moment (`M_z`), roll/pitch damping; replacing `forces3d._s2d` with a true 3D relative-wind model | **Step 31** — blocked on real airframe geometry from the user. The harness is designed for `M_x = M_z = 0`, exactly what `forces3d.moment_body_3d` produces today. **No new aero content is invented here.** |
| Non-planar 3D flights as a *validated* capability | **Step 31.** The harness will happily integrate one, but `_s2d` makes the forces an approximation for non-planar attitude (its own docstring). Step 32's tests therefore assert planar equivalence; a non-planar run is runnable, not yet trustworthy. State this in `run_sim_3d`'s docstring. |
| `rk45_seg` / sampled-data (zero-order-hold) 3D path; a 3D control law (2-axis gimbal, reaction wheel in 3D) | **A product decision first** (`task-30` §30.15), then its own step. `forces3d` hardcodes `hold = None` in two places; that contract has to be designed before it can be integrated. See D-32.2/S3. |
| 3D `static_margin_cal`, `cm_slope_series`, `combined_stability_slope_series`, `stability_check`, `sweep` | **Step 31+.** These rest on `C_z`/`C_m` slopes and `alpha`; through `_s2d` they would return a planar number labelled 3D. Rejected on correctness, not cost (D-32.3/O3). |
| `apps/_shared/flight_stats.py` 3D support, and 3D in `apps/analysis`, `apps/optimization`, `apps/control` | **Out of Phase 3 by the user's own scope ruling** (status.json stage 3 `scope`: "3D — only simulation/optimisation/guidance; CFD and airbrake Step 49 stay 2D"). A 3D flight-stats surface has no consumer today. |
| 3D variable-mass model (`m` in the state vector), time-varying `I_body(t)` and its `I_dot · omega` term, unifying `Inertia.I_yy/I_zz` with `Weight.I(t)` and `Inertia.I_xx` with `Roll.I_x` | **Existing backlog items from `task-30` §30.15.** D-32.6 guard 3 makes the absence fail loudly instead of silently. |
| Unifying 2D and 3D on one state vector / layout abstraction (option B as the end state) | **A later standalone refactor.** Its acceptance criterion is "D-77's 7 pins and Step 32's new 3D pin both hold unchanged" — which Step 32 is what creates. Add as a backlog item. |
| Any LaTeX edit | **None needed** (SS37.5). `dev/docs/latex/` is read-only for this ticket. |
| Fixing pre-restructure paths cited in `rocket-3d.tex` / `task-30` / the research note (`sim/...`, `configs/schema.py`) | **Not Step 32.** Drift consciously accepted by the user (2026-10-27); a separate pass fixed `appendix.tex` (2026-10-29). Add a backlog line if it still bothers anyone. |
| Renumbering / re-wording the research note's §3.2, §3.3, §4, §5 to match reality | **Not done, deliberately.** The note is the user's sign-off artefact; this document supersedes it in writing (SS37.0.1, SS37.1) rather than editing it — the same discipline `task-30` D-30.17 applied to `3d_equations_of_motion.md` §3. |

---

## SS37.9 Definition of done, risks

### Done when

0. `forces3d._s2d` recovers pitch with `atan2`, the SS37.0.4 round-trip table is a passing test, and
   `quaternion.to_euler`'s "only intended caller is plotting-style output" docstring claim is true
   again (D-32.9).
1. `run_sim_3d(p, s0_3d)` exists in `apps/sim/engine/integrate.py`, flies a planar 3D scenario to
   ground impact, and reports all five events — including a **vertical** launch
   (`rail_angle_deg = 90.0`, the project default) and a descent that crosses vertical.
2. `tests/test_integrate3d.py` exists with SS37.6.1's tests 1-8 (14-21 assertions-worth).
3. `tests/test_integrate.py` — 27 tests, 7 `np.array_equal` pins — **passes unchanged**, and
   `git diff` shows no edit inside `run_sim`, `_run_rk4`, `_run_segmented_rk45` or the five event
   function bodies (under option C; under A, no edit anywhere in `integrate.py`).
4. `tests/test_dynamics3d.py` — 8 tests — passes unchanged.
5. `apps/sim/engine/dynamics3d.py` has the rail/parachute freeze (D-32.5) and its module docstring
   no longer says the 3D path "has no rail and no parachute".
6. A committed `rk4` 3D reference pin exists (the note's Stage 2 deliverable, finally reachable).
7. D-32.3's chosen output slice exists and its data series are asserted (not the figures).
8. `run_sim_3d`'s docstring states, in as many words, that non-planar attitude is **runnable but not
   validated** until Step 31, and names `forces3d._s2d` as the reason.
9. Full suite green (background run; ~220 s nominal, up to ~800 s observed — `CLAUDE.md`).
   Numeric pins unmoved.
10. `dev/docs/index.md` / `log.md` / `tag.md` updated by `documentation` for this file.

### Risks

| Risk | Mitigation |
|---|---|
| **Option B is chosen and the pins move.** | Per-sub-step full-suite gate; a pin movement is a hard stop, not a re-pin (re-pinning needs the user's "yes", `CLAUDE.md`). Budget 2-3 QA rounds instead of 1. |
| **`_s2d`'s `theta` recovery folds past ±90°** — confirmed, measured, SS37.0.4. The project's default launch (`rail_angle_deg = 90.0`) and every ballistic descent sit in the broken range. | **Promoted out of the risk list into sub-step 32.0 / D-32.9** — a ~3-line `atan2` fix, free if taken first. The residual (wrapping at ±π, so no multi-revolution tumble) is documented, not fixed, and is immaterial to every `sin`/`cos` consumer. |
| **Verticality probe still needed after the fix.** `arcsin` is gone but `atan2(-R[2,0], R[0,0])` near `θ = ±90°` is well-conditioned, so the expected answer is "no degradation" — which has to be measured, not assumed. | Sub-step 32.2 includes the equivalence test at `θ₀ ∈ {85°, 89°, 90°}` and a run that crosses vertical during descent. If any of those diverge from the 2D run, that is a scope finding — escalate, do not paper over. |
| **Duplicated rk4 crossing block drifts** (option C). | Explicit marker comment naming `_run_rk4:364-418`; SS37.6.1 test 1 compares both paths' event times, so a drift in either shows up as a test failure, not as silent divergence. |
| **The freeze branch leaks into unconstrained flights** (D-32.5). | The 32.3 pin is taken *before* 32.4 lands, with rail/recovery off; it must not move. That ordering is the whole reason 32.3 precedes 32.4. |
| **Import cycle `integrate → forces3d`.** | Verified acyclic (SS37.7/32.2). Re-verify after the edit: `python -c "import apps.sim.engine.integrate"`. |
| **Scipy `RK45` native access-violation flake on Windows** (`CLAUDE.md`, QA 2026-10-24). | Known flaky, unrelated to the diff: re-run the full suite, do not treat as a step failure. |
| **Full suite is long.** | `run_in_background` only; the orchestrator must chunk into 3-6 files per call (~200 s ceiling, `CLAUDE.md`); sub-agents do not need to chunk. |

---

## SS37.10 Tickets (parallel-launch format)

**All five are `parallel_safe: false`.** They form a strict chain through the same file
(`apps/sim/engine/integrate.py`) and, more importantly, through the same *pin surface*: two agents
editing a pinned integrator concurrently cannot be gated independently. 32.5 touches different files
and has no code dependency on 32.4, but it needs 32.2's `run_sim_3d` to exist in order to be
testable, so it still waits.

### [S32-0] Fix `_s2d`'s pitch recovery (blocking prerequisite)
- **Module/boundaries:** `apps/sim/engine/forces3d.py`, `tests/test_forces3d.py` (new) or
  `tests/test_dynamics3d.py`
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (it must land before S32-3 or the new 3D pin moves; file boundaries do
  not overlap S32-1, so it *may* run concurrently with S32-1 if the orchestrator wants one
  parallel pair — this is the only safe pairing in the whole chain)
- **Spec slice:** SS37.0.4 (the finding + the measured table), SS37.4/D-32.9, SS37.7/32.0
- **Not blocked on the D-32.1 user gate** — independent of which harness option is chosen, so it
  can start while the gate is open.
- Three-line `atan2` replacement + docstring update + the round-trip table as a test. Do **not**
  extend the fix to non-planar attitude (Step 31 owns that).

### [S32-1] Projection seam and event factory in `integrate.py`
- **Module/boundaries:** `apps/sim/engine/integrate.py` (additive only, above the existing event
  functions), `tests/test_integrate3d.py` (new file)
- **Assignee:** developer
- **depends_on:** [] — but **blocked on D-32.1** (user gate, SS37.2)
- **parallel_safe:** false
- **Spec slice:** this file, SS37.1 (the harness column), SS37.2 (the chosen option), SS37.7/32.1
- Introduce the state-projection seam per the option the user picked. Do not wire 3D yet. Prove the
  2D path is byte-identical: `git diff` must not touch any pinned function body.

### [S32-2] `run_sim_3d` — RK45 path + eager validation
- **Module/boundaries:** `apps/sim/engine/integrate.py`, `tests/test_integrate3d.py`
- **Assignee:** developer
- **depends_on:** [S32-0, S32-1]
- **parallel_safe:** false
- **Spec slice:** SS37.3/D-32.2, SS37.4/D-32.6, SS37.4/D-32.7, SS37.6.1 tests 1-3 + 8, SS37.7/32.2,
  SS37.9 risk 2 (**the `θ₀ ∈ {85°, 89°, 90°}` + cross-vertical-in-descent probe is part of this
  ticket, not optional**)
- First end-to-end 3D flight to the ground. Five eager `ValueError` guards with pinned message
  substrings.

### [S32-3] `run_sim_3d` — `rk4` path + committed 3D reference pin
- **Module/boundaries:** `apps/sim/engine/integrate.py`, `tests/test_integrate3d.py`
- **Assignee:** developer
- **depends_on:** [S32-2]
- **parallel_safe:** false
- **Spec slice:** SS37.4/D-32.4, SS37.6.1 tests 4 + 7, SS37.6.2, SS37.7/32.3
- Quaternion projection at accepted steps. Pin with `np.array_equal` on the `rk4` path **only**;
  never pin an `RK45` 3D trajectory.

### [S32-4] 3D rail and parachute attitude freeze
- **Module/boundaries:** `apps/sim/engine/dynamics3d.py`, `tests/test_integrate3d.py`,
  `tests/test_dynamics3d.py` (additions only)
- **Assignee:** developer
- **depends_on:** [S32-3]
- **parallel_safe:** false
- **Spec slice:** SS37.4/D-32.5 (all five bullets), SS37.6.1 tests 5-6, SS37.7/32.4
- The freeze lives in `derivatives_3d`, not the harness. Zero **both** `dydt[Q]` and `dydt[OMEGA]`.
  32.3's pin must not move — that is the acceptance check for "no leak into unconstrained flight".

### [S32-5] Minimal 3D output
- **Module/boundaries:** `apps/sim/engine/plotting.py`, `apps/sim/engine/report.py`,
  `tests/test_plotting3d.py` (new) or `tests/test_plotting.py`, `tests/test_report.py`
- **Assignee:** developer
- **depends_on:** [S32-2]
- **parallel_safe:** false (needs `run_sim_3d` to exist; file boundaries do not overlap S32-3/S32-4,
  so the orchestrator *may* run it concurrently with S32-3 if it accepts two full-suite gates
  landing out of order — recommended only if schedule pressure justifies it)
- **Spec slice:** SS37.3/D-32.3 (the chosen option), SS37.7/32.5
- Additive functions only. Assert the data series (planar ground track: `y` exactly `0.0`), not the
  figures.

### Review and QA

- `code-review` skill before QA (project rule), on the sub-step diff against the ticket.
- QA gate per sub-step: point tests, then full suite in background, then "pins unmoved" confirmed
  explicitly in the QA report.
- Rounds 2+ via `SendMessage` to the same developer, not a new spawn; escalate after 3.
