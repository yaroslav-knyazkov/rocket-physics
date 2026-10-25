# 3D readiness proposal — decision package for Step 30 and beyond

Date: 2026-10-24. Author: architect (prep only). Branch: `feature/sim-paper-alignment`.

## Кратко (RU)

- Это **не** реализация 3D и **не** разрешение на неё. Это упаковка уже существующей, но так и не
  закрытой заметки `dev/docs/latex/research/3d_equations_of_motion.md` в пакет, по которому
  пользователь может принять решение за минуты, не перечитывая физику с нуля.
- Полный 3D (6DOF) — это перезапись вектора состояния, всех сил/моментов и физической постановки
  почти всех тестов. Оценка масштаба — см. §3: порядок десятка модулей `sim/` и десятков тестов.
- Блокирующая развилка одна и конкретная: **откуда брать осевой момент инерции $I_a$** (роллинг).
  Варианты и таблица сравнения — §4. Рекомендация архитектора: вариант **B+** (геометрическая
  оценка из радиуса корпуса, обязательное поле сценария, без дефолта), с явным флагом «оценка».
- Предлагаемый поэтапный план (§5): сначала решение по $I_a$ (0 строк кода), потом 3D-скелет,
  который бит-в-бит воспроизводит 2D при плоском движении, потом реальная 3D-аэродинамика.
- Прочие отложенные решения, которые 3D вытащит наружу (§6), и чего этот документ **не** делает (§7).

## Table of contents

- [1. What this document is](#1-what-this-document-is)
- [2. What 3D buys over today's 2D model](#2-what-3d-buys-over-todays-2d-model)
- [3. What 3D costs — honest blast radius](#3-what-3d-costs--honest-blast-radius)
- [4. The blocking fork: source of the axial inertia `I_a`](#4-the-blocking-fork-source-of-the-axial-inertia-i_a)
- [5. Recommended staged rollout](#5-recommended-staged-rollout)
- [6. Other deferred decisions a 3D rewrite forces open](#6-other-deferred-decisions-a-3d-rewrite-forces-open)
- [7. What this document is NOT](#7-what-this-document-is-not)

---

## 1. What this document is

Prep, nothing else. The user asked, right before sleeping: *"then do the 3D implementation in sim +
in latex."* The orchestrator declined to execute that unsupervised, correctly, because
`dev/status.json`'s `deferred_decisions` has carried a user-level blocker on exactly this since
2026-10-04:

> *Step 30: ревью предложения 3D-уравнений движения
> (`dev/docs/latex/research/3d_equations_of_motion.md`), развилка — осевой момент инерции `I_a` —
> ждёт пользователя.*

This document turns that never-resolved note into a package the user can decide on in minutes.

### 1.1 Correction to the working premise — 3D is *mostly already built*

The spawn brief assumed full 3D is "a genuine architecture rewrite of the state vector, every
force/moment computation, and every existing test's physical setup". **That was true when the
research note was written (2026-10-04); it is not true today.** Ground truth from the repository on
this branch:

| Roadmap step | Status in code today | Evidence |
|---|---|---|
| Step 28 — quaternion algebra | **landed** | `sim/quaternion.py` (197 lines): `multiply`, `conjugate`, `normalise`, `rotate_vector`, `to_dcm`, `from_euler`, `to_euler`, **and `q_dot(q, omega_body)`** — i.e. the whole rotational *kinematics* half of Step 30 already exists and is tested (`tests/test_quaternion.py`, 188 lines) |
| Step 29 — 3D state + translation | **landed** | `sim/state3d.py` (13-component `[r(3), v(3), q(4), omega(3)]`), `sim/dynamics3d.py` (`derivatives_3d`), `sim/forces3d.py` (3D force wrappers), `tests/test_dynamics3d.py` with a planar-vs-Phase-1 equivalence test |
| Step 30 — rotational dynamics | **blocked, not started** | `sim/dynamics3d.py:52-53` literally hardcodes `dydt[Q] = 0.0; dydt[OMEGA] = 0.0` with the comment "Step 30's job" |
| Step 31 — 3D aero | not started | `forces3d.aero_force_body_3d` embeds the 2D force with a zero y-component |
| Step 32 — 3D output/regression | not started | `sim/plotting.py`, `sim/report.py`, `run.py` contain **zero** references to `state3d`/`dynamics3d` |

So the thing the user asked for is **not** a rewrite. It is: fill in two lines of `dynamics3d.py`
with `q_dot` (already written) and Euler's equations (fully derived in the research note), plus one
new scenario parameter. That is roughly a **30-line, one-file, one-new-param change** — and it is
blocked on a decision, not on engineering.

The expensive part is somewhere else entirely, and the roadmap under-scopes it badly (see §3.2).

---

## 2. What 3D buys over today's 2D model

Plain language, in descending order of actual value to this project:

1. **Roll.** The 2D model has no roll degree of freedom at all. Everything roll-related the project
   already wants is blocked by this: fin cant producing a steady roll rate, roll damping, and the
   reaction-wheel roll control item already written into `dev/docs/latex/sections-ai/backlog.tex`
   (lines 43-48). This is the single biggest functional gain.
2. **Out-of-plane wind response.** Today, a crosswind is representable only by rotating the whole
   2D plane to the wind azimuth; the rocket cannot weathercock *out* of its launch plane. With 3D,
   a wind whose direction changes with altitude (which `sim/soundings.py` already provides, with
   real radiosonde data) produces a genuinely curved **ground track** rather than a straight
   downrange line. For landing-zone/recovery prediction this is the difference between a 1D
   dispersion estimate and a real 2D footprint.
3. **Sideslip `β` and total angle of attack.** `sim/aero.py` already carries table/Jorgensen-style
   body-of-revolution machinery whose natural input is total `α`, not planar `α`. 3D lets the aero
   model be used the way its source material intends.
4. **Gyroscopic coupling.** Pitch/yaw cross-coupling through `ω_x` — the `(I_t − I_a) ω_z ω_x` terms.
   Physically real for a rolling rocket, and the classical source of roll-pitch resonance. Of real
   interest only once roll is actually driven (fin cant or the reaction wheel), i.e. after item 1.
5. **Honest 3-axis dispersion / Monte-Carlo.** `sim/sampling.py` + `tests/test_ensemble.py` already
   do ensembles; in 2D they can only disperse in-plane.

What it does **not** buy: for a nominal, symmetric, near-vertical flight with uniform wind, the 3D
answer is the 2D answer. Apogee, max-Q, burnout velocity, static margin — all essentially unchanged.
3D is about *asymmetric* flight, not about better numbers for the symmetric case. Worth saying
plainly so the user is not expecting the headline figures to move.

---

## 3. What 3D costs — honest blast radius

### 3.1 Step 30 proper (rotational dynamics): small

- **Files touched:** `sim/dynamics3d.py` (one function body), `sim/params.py` (one new field),
  `tests/test_dynamics3d.py` (new tests), one scenario/template config.
- **Pin risk to the existing suite: essentially zero.** This is the important point. The 3D path is
  *additive and parallel*, not a replacement: `sim/state.py` (7-component) and `sim/dynamics.py`
  stay byte-identical, and nothing in the 2D chain imports `state3d`. The numeric pins that this
  project guards (`tests/test_integrate.py` RK45 pins, `np.array_equal` fixtures, D-77) all live on
  the 2D path and cannot move.
- **New physics content:** exactly one number — `I_a`. Everything else (§4 of the research note) is
  textbook symmetric-top Euler, and the note already states the specialised component form.

### 3.2 The real cost, which the roadmap does not account for: the 3D path is an island

`sim/dynamics3d.py` is currently reachable only from its own unit test. `sim/integrate.py`'s
`run_sim` — 759 lines of event/hold machinery — is written entirely against the 7-component 2D
vector, and so is everything downstream:

| Module | Lines | Coupled to the 2D layout via | What breaks for a 3D run |
|---|---|---|---|
| `sim/integrate.py` | 759 | `state.X/Z/VX/VZ/THETA/OMEGA/M` indices in ground/apogee/burnout/rail-exit/parachute-deploy events, hold logic, `_rhs` | **No 3D scenario can be flown end-to-end at all.** No ground impact, no apogee detection, no rail constraint, no parachute |
| `sim/control.py` | 589 | pitch-only feedback/actuator on `THETA`/`OMEGA` | nozzle-cant control has no 3D analogue; needs a 2-axis (or 3-axis) law |
| `sim/report.py` | 377 | `flight_summary`, `static_margin_cal`, stability series read 2D indices | no summaries/sweeps for 3D runs |
| `sim/plotting.py` | 146 | 2D trajectory/time-history plots | roadmap Step 32's scope |
| `sim/forces.py`, `flow.py`, `aero.py`, `gravity.py`, `rotation.py`, `soundings.py` | ~2900 | 2D state indices | reached today only through `forces3d._s2d()`, a *disposable planar adapter* that is explicitly documented as invalid for non-planar attitude (`sim/forces3d.py:50-56`) |

Totals: **11 of 26 `sim/` modules** import the 2D state layout; **~30 of ~44 test files** construct
`State(...)` or import `sim.state`. Those are the numbers if one ever tried to *unify* on a single
3D state vector — that would be the rewrite the brief feared, and it is a Phase-sized project, not
a step.

**Architectural call-out for the user/orchestrator:** the roadmap's Step 32 ("3D output and
regression": `plotting.py`, `run.py`, `tests/`) silently omits `integrate.py`'s event machinery,
`control.py` and `report.py`. As written, Steps 29→32 deliver a 3D dynamics core that still cannot
fly a complete scenario. That gap needs a step of its own (call it **Step 30b, "3D integration
harness"**) and it is strictly larger than Step 30, Step 31 and Step 32 combined. See §5.

### 3.3 Order-of-magnitude estimate

| Work item | Files | New/changed tests | Risk |
|---|---|---|---|
| Step 30 — Euler's equations + `q_dot` wiring + `I_a` param | 2-3 | 4-6 | low |
| Step 30b — 3D integration harness (events, `run_sim` generalisation) | 3-5 | 10-15 | **medium-high**, touches `integrate.py` where the pins live |
| Step 31 — 3D aero (`β`, total `α`, roll moment, damping) | 2-3 | 8-12 | medium; blocked on airframe geometry (same gap as `I_a`, see §6) |
| Step 32 — 3D output/regression | 3-4 | 5-8 | low |
| 3D control law | 1-2 | 6-10 | medium; needs a product decision, not just architecture |

---

## 4. The blocking fork: source of the axial inertia `I_a`

### 4.1 What the fork actually is

The inertia tensor in body axes is diagonal — `I_body = diag(I_a, I_t, I_t)` — and this is **not a
new simplification**: the rocket is a body of revolution about `x̂_r` by construction, so
`I_yy = I_zz` and all products of inertia vanish. `I_t` is today's `I(t)`, already modelled
(`sim/mass.py:moment_of_inertia`, with the parallel-axis shift as the CoG travels).

`I_a` — the **axial / roll** moment of inertia — is the one genuinely new physical input. The 2D
document never needed it, because 2D has no roll axis. And it cannot be defaulted to zero: it is the
sole denominator of Euler's roll equation `I_a ω̇_x = M_x`, so `I_a = 0` is a division by zero, not a
disabled model.

The note left the fork open because, on 2026-10-04, no airframe geometry existed anywhere in the
project to derive `I_a` from.

### 4.2 What changed since the note was written — the fork is now cheaper

**`sim/params.py:Aero` already carries the geometry needed**, added later by the Phase-2 aero work:

- `d_ref` — reference diameter [m] (`configs/rockets/demo.py`: `0.054`)
- `S` — reference area [m²] (`demo.py`: `0.00229`; and `π·0.054²/4 = 0.002290` — the two are
  mutually consistent, so either can derive the other and they cross-check)

So option B below no longer requires the user to supply new data. It requires a decision about
provenance and about where the field lives.

### 4.3 Sensitivity — why this decision is less load-bearing than it looks

With `demo.py`'s numbers (`m = 1.5 kg`, `I_t = 0.15 kg·m²`, `r = d_ref/2 = 0.027 m`):

| Model | `I_a` [kg·m²] | `I_a / I_t` |
|---|---|---|
| solid cylinder, `½ m r²` | 5.47e-4 | 0.0036 |
| thin-walled shell, `m r²` | 1.09e-3 | 0.0073 |

Two consequences, and they point in opposite directions:

- **Pitch/yaw is insensitive.** The gyroscopic coefficient is `(I_t − I_a)`, and `I_a` is 2-3 orders
  of magnitude below `I_t` for any slender airframe. A factor-2 error in `I_a` perturbs the
  pitch/yaw equations by **< 0.4 %**. A placeholder is harmless there.
- **Roll is fully, inversely sensitive.** `ω̇_x = M_x / I_a` — a factor-2 error in `I_a` is a
  factor-2 error in roll rate. Nothing about roll can be trusted on a placeholder.

**Therefore:** a placeholder value is adequate for **Step 30**, where `M_x = 0` by the note's own
§5 (no roll moment is modelled yet) and the validation check is planar equivalence. `I_a` only
becomes load-bearing at **Step 31** (fin cant) and at the reaction-wheel backlog item. This means the
fork **should not be allowed to keep blocking Step 30** — which it has done for 20 days.

### 4.4 Comparison table — paste-ready for `AskUserQuestion`

**Question:** Where does the axial (roll) moment of inertia `I_a` come from?
**Purpose:** `I_a` is the only new physical input 3D rotational dynamics needs; it is the denominator
of the roll equation and cannot default to zero.

| Option | Pros | Cons | Cost / risk | |
|---|---|---|---|---|
| **A. Per-scenario placeholder constant** — a required `Weight.I_a` field, no default, user types a number per rocket config; swept by hand like `c_mq` was in its Step-44 fixture | Zero derivation, zero coupling to other params. Matches how `m`, `I`, `l_1`, `l_2` are already supplied. Honest: the number is visibly an input, not a fake derivation | Every new config must supply a number the user may not have. No guidance on what a *plausible* number is — invites a wrong order of magnitude silently | Lowest code cost (~1 field). Risk: silent bad roll results later, because nothing cross-checks the value |
| **B. Geometric estimate from existing `d_ref`** — `I_a = k · m · (d_ref/2)²`, with `k` a shape factor the user picks once (`k = 0.5` solid, `k = 1.0` thin shell) | Needs **no new user data** — `d_ref`/`S` already exist in every aero config. Self-consistent with the aero reference geometry. A textbook placeholder in exactly the same spirit as `c_mq`'s strip estimate, which this project already accepted | Couples a *mass*-model quantity to an *aero*-model field: a scenario with the aero model off has `d_ref = 0` → `I_a = 0` → the division-by-zero the note warned about. Needs an explicit fail-fast guard. Also hides the factor-2 solid-vs-shell ambiguity behind a default | Low (~1 field + a guard + a config-validation test). Risk: the `d_ref = 0` trap must be caught at config-validation time, not at integration time |
| **B+. Dimensionless radius of gyration (recommended)** — a required `Weight.k_a` (shape factor, dimensionless, no default) plus `I_a(t) = k_a · m(t) · (d_ref/2)²`, derived in `sim/mass.py` beside `moment_of_inertia`, with `d_ref` promoted out of `Aero` into shared geometry (or mirrored into `Weight`) | All of B's "no new data", but the user's input is a **shape judgement** (`0.5` solid / `1.0` shell / anything between), which is far easier to get right than an absolute `kg·m²`. Lives in `sim/mass.py` next to `I_t`, so both inertias are derived in one place with one convention. **Tracks the burning propellant** — see §4.5, which plain A and B both get wrong | Slightly more code than A/B: one derivation function, and a decision about where `d_ref` lives. Moving/mirroring `d_ref` touches config schema + migration (`tests/test_config_migration.py` exists for exactly this) | Low-medium (~2 files + schema/migration test). Risk: the `d_ref` relocation is the only real surface; can be deferred by reading `p.aero.d_ref` initially with a TODO |
| **C. Block Step 30 until real airframe geometry exists** — no `I_a` until a measured radius-of-gyration or a CAD/mass-breakdown profile is available | Nothing speculative ever enters the model | **This is the status quo, and it has blocked Step 30 for 20 days** while §4.3 shows the value barely matters for Step 30 at all. Also blocks the reaction-wheel backlog item indefinitely | Zero code. Risk: continued indefinite stall on a decision whose numerical impact on the deliverable (planar equivalence) is literally zero |

**Architect's recommendation: B+**, with `k_a` as a required, no-default scenario input and a
fail-fast config check that rejects `d_ref <= 0` whenever `k_a` is set. Rationale: it is the only
option that (i) needs no data the user does not already have, (ii) asks the user for a judgement they
can actually make (shape, not an absolute inertia), (iii) puts both inertias in one module with one
convention, and (iv) does not silently freeze `I_a` while the propellant burns.

If the user wants the absolute minimum decision surface tonight: **A** is acceptable and can be
upgraded to B+ later without breaking anything, since `I_a` would be read through one accessor
either way. **C should be rejected** — §4.3 shows it blocks a step it cannot meaningfully protect.

### 4.5 Secondary fork (small, but the note gets it half-wrong)

The research note, §3, states: *"`I_a` is a single constant for the vehicle, not a function of
`l_B(t)`."* The first half of the reasoning is correct — a body of revolution's axial inertia is
**not** shifted by the parallel-axis theorem when the CoG travels along `x̂_r`, because axial inertia
is computed from perpendicular distance to the axis. But the conclusion "a single constant" does not
follow: as propellant burns, `m(t)` falls (the project already models this via `p.weight.m_d`), and
axial inertia falls with it. `I_a` is independent of `l_B(t)`, **not** independent of `m(t)`.

| Option | Pros | Cons | Cost / risk |
|---|---|---|---|
| **F2-a. `I_a` frozen constant** | Simplest. Matches the note's literal wording. Difference is invisible while `M_x = 0` (Step 30) | Physically wrong once the mass model is on: a burnt-out rocket is credited with its wet axial inertia. Understates roll acceleration by the propellant mass fraction (can be 30-50 %) | Zero extra cost, but a known-wrong value that will have to be revisited at Step 31 |
| **F2-b. `I_a(t) = k_a · m(t) · r²` (recommended)** | Correct, free (it is the same formula with `m(t)` instead of `m`), consistent with how `I_t(t)` is already handled in `sim/mass.py` | Assumes the shape factor `k_a` is mass-invariant, which is an approximation when the propellant is a central grain rather than distributed | Negligible — one symbol |

Recommendation: **F2-b**, and amend the research note's §3 wording (one sentence) when Step 30 is
approved. Flagging rather than silently fixing, because the note is the user's own sign-off artefact.

---

## 5. Recommended staged rollout

Ordered by **information-per-unit-risk**, not by roadmap number. The deliberate inversion is that
the cheap-but-high-information validation (Stage 2) is pulled *in front of* the expensive
integrator work (Stage 3), even though the roadmap's numbering implies the opposite.

### Stage 0 — pure decisions, zero code

| # | Decision | Owner | Blocks |
|---|---|---|---|
| 0.1 | The `I_a` fork (§4.4) and the `I_a(t)` sub-fork (§4.5) | user | everything rotational |
| 0.2 | **Does "+ in latex" authorise editing `main.tex`?** | user | Step 30's own roadmap-declared blocker — see §5.0 |
| 0.3 | `q` renormalisation: per-RHS-call vs. solver event (note §7.2 — no physics content) | may be left to the developer | nothing |

#### §5.0 — the LaTeX authorisation collision (needs the user's word, not an architect's guess)

There is a direct conflict on record that the orchestrator must put to the user explicitly:

- `dev/docs/roadmap.md:2246` — Step 30 is *"**Blocked on:** a `main.tex` extension of §Equations of
  motion to 3D (inertia tensor, the `ω × Iω` gyroscopic term)"*.
- `CLAUDE.md` — *"**LaTeX не редактировать** (`dev/docs/latex/`, решение пользователя 2026-10-15):
  только чтение и перенос. Правки — только по явной просьбе."*
- `dev/status.json` `deferred_decisions` — *"Step 84: синхронизация LaTeX с Phase 2.16 — отложено,
  LaTeX не трогать."*
- The user's verbatim request — *"then do the 3D implementation in sim **+ in latex**."*

The last line is plausibly the "явная просьба" the freeze carves out, but it is not an architect's
call to decide that a freeze the user imposed has been lifted by an offhand clause. Three options for
the orchestrator to put to the user:

| Option | Meaning |
|---|---|
| **L-a** | Yes — write a new `dev/docs/latex/sections-ai/rocket-3d.tex` and `\input` it, touching no existing approved section. *(Architect's recommendation: smallest blast radius, additive, reviewable in isolation, and it satisfies Step 30's declared blocker.)* |
| **L-b** | Yes, and also amend existing `rocket-2d.tex` §Frames/§Mass to present 2D as the planar specialisation of 3D. Cleaner document, but edits already-approved sections — exactly what the freeze protects |
| **L-c** | No — keep the freeze; `sim/` implements against this proposal + the 2026-10-04 note, and LaTeX catches up later with Step 84 |

Note also that `pdflatex`/`latexmk` **are not installed in this environment** (`CLAUDE.md`), so any
LaTeX written cannot be compile-verified by an agent. Under L-a/L-b the user compiles.

### Stage 1 — Step 30 core: Euler's equations (low risk, high value)

- **Files:** `sim/dynamics3d.py` (replace the two hardcoded `dydt[Q] = 0.0; dydt[OMEGA] = 0.0`
  lines), `sim/mass.py` (the `I_a` derivation, if B+), `sim/params.py` (`Weight.k_a` or
  `Weight.I_a`), `tests/test_dynamics3d.py`.
- **Physics:** verbatim from the research note §2 and §4 — `q_dot` already exists in
  `sim/quaternion.py:183`; the symmetric-top component form is the note's §4 block. `M_x = 0`,
  `M_y` from the existing `forces.aero_moment_y`, `M_z` the same by axisymmetry (note §5).
- **Checks, in order of how much they would actually catch:**
  1. **Torque-free angular-momentum conservation** — `‖I·ω‖` constant under `M = 0` with `ω_x ≠ 0`.
     This is the only check that exercises the gyroscopic term at all, and the only one that would
     catch a sign error in `ω × Iω`. The roadmap lists it last; it should be first.
  2. **`‖q‖ = 1` throughout** (with the Stage-0.3 renormalisation choice).
  3. **Planar equivalence vs. 2D** — extends the existing
     `tests/test_dynamics3d.py:test_derivatives_3d_cross_checks_derivatives_2d_pointwise`.

  ⚠️ **On "bit-identical":** the brief asks for a 3D path that "round-trips to bit-identical 2D
  results". That target should be relaxed before it is written into a ticket. `derivatives_3d`
  reaches the same physics through a different sequence of floating-point operations (a 3×3 DCM
  multiply instead of a 2×2 rotation, `quaternion.to_euler` to recover `θ`), so exact bit identity
  of the *trajectory* is not achievable and its absence would not indicate a bug. The achievable and
  genuinely strong version, which the existing test already uses, is: **out-of-plane components stay
  exactly `0.0`** (bit-exact, and this one really is load-bearing — it proves no spurious
  out-of-plane coupling), while in-plane components match to solver tolerance.

### Stage 2 — 3D shadow run, without touching `integrate.py` (cheap, high information)

The point of pulling this ahead of Stage 3: get a *full-trajectory* 3D validation while the
integrator is still untouched, so that if Stage 3 later perturbs anything, there is already a
trusted 3D reference.

- Drive `derivatives_3d` with the project's **own fixed-step `rk4`** (not `RK45`) — `CLAUDE.md`
  records that the in-house `rk4` is version-stable across numpy/scipy while the scipy `RK45` path
  shifts at rounding level between versions, so an `rk4`-based 3D reference pin is safe to commit.
- No events, no parachute, no rail: integrate a fixed time span, planar initial conditions.
- Deliverable: a committed reference trajectory + the same run through the 2D path, diffed.
- **Zero risk to existing pins** — nothing in `sim/integrate.py` is modified.

### Stage 3 — Step 30b, the 3D integration harness (the real cost; separate approval gate)

This is the step §3.2 showed is missing from the roadmap, and it is larger than Steps 30, 31 and 32
combined. It should **not** be bundled into an approval for Stage 1.

- Generalise `sim/integrate.py`'s events (ground, apogee, burnout, rail exit, parachute deploy) and
  hold machinery to work off either state layout.
- Design question to settle *before* coding (and the one real architecture decision left after
  `I_a`): **a state-layout abstraction vs. a parallel `run_sim_3d`.** A shared abstraction is the
  deep-module answer and avoids duplicating 759 lines; a parallel function is the zero-pin-risk
  answer because the 2D code path stays byte-identical. Given how hard this project pins numbers,
  the parallel function is probably right first, with unification as a later refactor — but that
  deserves its own `decision_required` round rather than a decision made here in passing.
- **This is where every numeric pin in `tests/test_integrate.py` is at risk.** Full-suite run
  (background, ~220 s) is mandatory per step.

### Stage 4 — Step 31, 3D aerodynamics (blocked on airframe geometry, same gap as `I_a`)

Sideslip `β`, total `α`, roll moment from fin cant, roll and pitch damping. Independently blocked on
the airframe-geometry gap listed in `main.tex` §Backlog (the same gap that made `I_a` a fork in the
first place, and the same one `c_mq` and Barrowman are waiting on). Do not start until Stage 3 exists
— otherwise there is no way to fly a scenario that would show whether the roll model is right.

### Stage 5 — Step 32 output/regression, and the 3D control law

`plotting.py` ground-track and Euler-angle histories; `report.py` 3D summaries. The **3D control
law** (a 2-axis nozzle gimbal, or the reaction wheel) is a *product* decision, not architecture, and
should be routed to `product`/the user rather than assumed.

### 5.1 The roll / reaction-wheel item — flagged, not resolved

`dev/docs/task-109-roll-reaction-wheel.md` **does not exist** as of this writing, so there is no
sibling ticket to reconcile against. The underlying item is, however, already on record in
`dev/docs/latex/sections-ai/backlog.tex:43-48`: *"Roll dynamics with a reaction wheel (2D) — a
decoupled roll degree of freedom about `x̂_r`: roll angle `γ_r`, roll rate `ω_x` and axial moment of
inertia `I_x` … **Waiting on:** `I_x` of the airframe, the wheel inertia and motor torque limits."*

Two observations, both for the user to rule on rather than for an architect to settle:

1. **It is blocked on the same number.** That backlog item's `I_x` *is* this proposal's `I_a`. One
   decision in §4.4 unblocks both. Worth saying to the user, because it raises the value of making
   that decision.
2. **It is forward-compatible, not throwaway — probably.** The research note's §4(a) establishes that
   the roll axis carries **no gyroscopic term at all** (`I_t − I_t = 0`), so the decoupled 2D roll
   equation `I_a ω̇_x = M_x` is *literally identical* to the roll component of the full 3D Euler
   equations. A decoupled roll DOF would therefore map directly onto the 3D model's own roll axis
   rather than being made redundant by it — the equation, the parameter and the reaction-wheel
   momentum-exchange term all carry over verbatim. The part that would *not* carry over is the state
   plumbing: a 2D roll addition means bolting `γ_r`, `ω_x` and a wheel-speed component onto the
   7-component 2D vector, and that plumbing is thrown away when the 13-component 3D vector arrives.
   **So: the physics is reusable, the plumbing is not.** Whether that makes a 2D roll addition worth
   doing first depends entirely on when 3D actually lands — which is the user's call, not mine. If
   a sibling agent has in the meantime landed such a ticket, this paragraph is the reconciliation
   note for it; it does not need to be undone, but its state plumbing should be marked as
   provisional.

---

## 6. Other deferred decisions a 3D rewrite forces open

Grepped from `dev/status.json`'s `deferred_decisions` (via `status_query.py key deferred_decisions`)
for anything touching 3D, rotation, inertia, frames or geometry. There are **more than just the
`I_a` item** — six of the nine recorded entries are implicated.

| Recorded deferred decision | Date / status | How 3D forces it open |
|---|---|---|
| **Step 30: `I_a` fork** (this document's §4) | 2026-10-04, *waiting on user* | The headline blocker. Resolved by §4.4 |
| **Step 84: LaTeX sync with Phase 2.16 — "LaTeX не трогать"** | 2026-10-15, *deferred by user* | **Direct collision** with the user's own "+ in latex". Step 30's roadmap entry declares itself blocked on a `main.tex` extension. See §5.0 — this is the second genuine decision needed |
| **Step 36: should `l_1`/`l_2` follow `l_B(t)` as the CoG moves (currently fixed)** | 2026-09-27, *open, needs user/architect review* | 3D makes this strictly worse, not merely unresolved: the moment arms `BC`/`BD` become 3-vectors, and a fixed-arm approximation that was one error term in pitch becomes the *same* error term in yaw as well. Any 3D moment implementation has to pick a side. Recommend resolving it as part of Stage 1 or explicitly carrying it forward in writing |
| **Step 36: `I_p(t) = (I_d/m_d)·m_p(t)` placeholder until real grain geometry** | 2026-09-27, *acceptable as placeholder* | This is the *transverse* twin of the exact question §4 asks about the axial inertia. If `I_a` gets a shape-factor treatment (option B+), consistency argues for revisiting `I_p` with the same machinery — or at minimum documenting why the two inertias use different conventions |
| **Renaming A/B/C/D ↔ `l_1`/`l_2` in code** | 2026-09-27, *deferred ("only if we feel like it")* | 3D is the natural fork-or-never moment: new 3D moment-arm code must pick *some* naming, and whatever it picks will diverge from the 2D code unless this is settled first. Cheap now, annoying later |
| **2026-09-28 user-deferred bundle: nozzle-gimbal control law, Barrowman aerodynamics, grain geometry, vertical wind, CFD → `aero_table` pipeline** | 2026-09-28, *deferred, not scheduled* | Three of the five are implicated. **Barrowman + grain geometry** are the airframe-geometry gap that made `I_a` a fork and that independently blocks Stage 4. **The nozzle-gimbal control law** becomes a different problem in 3D — a 2-axis gimbal, not a scalar `δ` — so the deferred 2D decision cannot simply be un-deferred later; 3D changes the question |
| D-54: ad-hoc CLI `--rocket/--site/--weather` | 2026-10-14, *deferred* | Marginal. 3D adds a run mode, which resurfaces the question of how runs are selected, but nothing forces it |
| Step 24: sounding time interpolation | 2026-09-21, *deferred* | Not forced by 3D |
| Separate LaTeX "Numerical integration" section | 2026-10-13, *deferred* | Not forced by 3D, though Stage 2's `rk4` reference run would give it content |

**Net:** resolving `I_a` alone is not sufficient to unblock a clean 3D run. The minimum decision set
to reach a *trustworthy* Stage 1 is: **`I_a` (§4.4) + `I_a(t)` (§4.5) + the LaTeX authorisation
(§5.0) + a ruling on Step 36's `l_1`/`l_2`** — four decisions, all of them zero-code, all of them
answerable in one sitting.

---

## 7. What this document is NOT

This is **not** a go-ahead, and nothing in it has been implemented. No `sim/` code was written or
modified, no LaTeX was touched, no git operation was performed, no test was run, no tracker file was
edited. The only new file is this one. Every physics statement here is either quoted from the
existing 2026-10-04 research note (`dev/docs/latex/research/3d_equations_of_motion.md`, which remains
the sign-off artefact for the equations themselves) or is an observation about what the repository
contains today. It is also **not** a replacement for that note and does not re-derive its equations;
where this document disagrees with it, it says so explicitly and in exactly one place (§4.5, on
whether `I_a` is constant in mass). Its entire purpose is that the user's first waking decision is a
fast one: read §4.4's table, pick a letter, read §5.0's table, pick a letter — and the 20-day-old
blocker on Step 30 is gone, with the implementation itself a ~30-line change in one file.

