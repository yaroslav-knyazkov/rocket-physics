## Кратко (RU)

- Зачем держать 3 реализации предиктора (analytical/point-mass numeric/2D numeric) одновременно, а не
  заменять одну другой: они решают одну и ту же задачу (предсказать апогей из текущего состояния) на
  разных уровнях точности/стоимости, и каждый служит регрессионным оракулом для следующего по лестнице.
- `_docs/roadmap.md`'s Controller-таблица — это порядок РЕАЛИЗАЦИИ (P/PD как одна версия, Tier 2 — новая
  версия, Tier 3 — отдельная категория, не инкремент). Этот файл — отдельно: матрица конфигураций и
  методология СРАВНЕНИЯ, которое прогоняет собранные версии против единого жёсткого стенда (полная
  актуаторная модель, зашумлённые Kalman-фильтрованные данные, 2D-with-disturbances truth plant) — не
  stage-matched сравнение, как было в более раннем черновике этого файла.
- ρ (плотность воздуха) трактуется по-разному в зависимости от типа предиктора: у аналитического —
  только константа (требование замкнутой формы), улучшаемая до "константа на текущей высоте"; у численных
  (point-mass/2D) — можно сразу использовать РЕАЛЬНУЮ функцию ρ(h) из самой симуляции, без заморозки.
- Не предписывает реализацию (пути файлов, кто пишет код) — это за architect/developer, когда до версии
  дойдёт очередь. Обоснование и методология сравнения, зафиксированные из разговора с пользователем
  2026-11-18 (включая правки того же дня).

---

# Controller solver versions — why three predictors, default configuration, what each is tested against

Companion to `_docs/roadmap.md`'s Controller section (the version table). That table says *what* each
version is; this file says *why* three solver implementations of the same sub-problem are being kept
side by side on purpose, what's currently wired as the default vs. an opt-in alternate, and what each
one's accuracy claim actually gets checked against.

## 1. Why three predictor "solvers," not one

All three solve the same sub-problem — *given the current state, predict the apogee if the brake stayed
where it is* — at increasing fidelity and increasing compute cost:

1. **Analytical (closed-form).** One algebraic evaluation: `h_a = h + (m/2k)·ln(1 + k·v²/(m·g))`. Only
   valid when the drag-area coefficient `k` is constant for the whole remaining coast (linear drag, no
   Mach dependence). Cheapest by a wide margin — a handful of flops, trivially real-time on anything.
2. **Point-mass numerical integration.** Forward-integrates the same 1D vertical coast ODE
   (`m·dv/dt = -m·g - k(v,h)·v²`), but `k` is now allowed to vary (Mach-dependent `Cd`, altitude-dependent
   `ρ` changing *during* the predicted coast, not just at the current tick). No closed form exists once
   `k` depends on the state being integrated — needed the moment drag stops being linear.
3. **2D numerical integration.** Same idea, but rolls forward the full attitude-aware dynamics (reusing
   `apps/sim/engine`'s existing rotational state — `_docs/old/airbrake-controller-plan.md` §1 already notes
   the point-mass model is a frozen-attitude special case of the same engine, not a separate solver to
   hand-build). Needed once AoA-induced drag/velocity-direction effects matter.

**ρ handling differs by predictor type, not independently of it** (correction, 2026-11-18): the analytical
predictor can only ever use a per-tick CONSTANT ρ — the closed form's derivation requires constant `k` for
the whole predicted coast, full stop. The best it can do is evaluate that constant at the current estimated
altitude instead of a flat sea-level default — still frozen, just a better freeze-point. The numeric
predictors (point-mass or 2D) have no such restriction once they're integrating step-by-step anyway: they
can call the SAME `ρ(h)` function the truth simulation itself uses, evaluated fresh at every integration
step, no freezing needed at all. So ρ(altitude) is not an independent axis crossed with every predictor —
it's the analytical predictor's own best option, while the numeric predictors get full-fidelity ρ "for
free" as part of going numeric in the first place.

They are deliberately **not** a strict replace-the-old-one-with-the-new-one progression:

- The analytical formula stays useful even after the numeric ones exist — as the cheap default/fallback
  (if its linear-drag assumption is good enough for the current flight regime, there's no reason to pay
  for a numeric rollout), and as a **correctness oracle** for the numeric predictors: in the exact
  degenerate case where `k` is held constant, the point-mass numeric integrator MUST reproduce the
  analytical formula's own output within integration tolerance. If it doesn't, the numeric integrator has
  a bug — this is the cheapest, most direct way to validate a new numeric predictor before trusting it on
  a case the analytical formula can't handle at all.
- Same relationship between point-mass numeric and 2D numeric: at zero AoA / frozen attitude, the 2D
  rollout must reduce to the point-mass numeric rollout's own answer.

So "3 solvers" isn't redundancy — each is both a candidate for the final flown controller AND a
regression oracle for the next one up the fidelity ladder.

## 2. Configuration matrix — current default vs. alternate

"Default" means what's actually wired up and running today (`runs/point/controller.py`, Step 152), not a
recommendation for what should eventually fly. **Controller law is its own axis** — P and PD are treated
as one roadmap version (`_docs/roadmap.md` 1.1, interchangeable gain-laws on the same predictor/plant
pairing), but still two distinct settings of this axis for comparison purposes. Tier 3 is flagged
separately (see §3) since the user considers it architecturally distinct, not an increment.

| Axis | Default (built, running today) | Alternate(s) | Status of alternate |
|---|---|---|---|
| Controller law | P (`proportional_drag`) | PD (`pd_apogee`) | Law built in `apps/control/flight_software/laws.py` (Step 153), not yet wired into an fx27 runs script |
| | | Tier 2 (switching-curve/bounding blend) | Not implemented anywhere yet |
| | | Tier 3 (MPC) — different controller architecture, not an increment of P/PD/Tier 2 | Not implemented, speculative per the plan doc's own §4 |
| Predictor model | Analytical closed-form | Point-mass numerical integration | Not built |
| | | 2D numerical integration | Not built |
| Onboard ρ (analytical predictor only — numeric predictors use the real ρ(h), see §1) | Constant nominal (1.225 kg/m³, sea level) | Constant-at-current-altitude (still frozen per tick, just a better lookup) | Not built — needs a pure `h → ρ` helper factored out of `apps/sim/engine/atmosphere.py` |
| Actuator model | Ideal (instantaneous, `Actuator(model="ideal")`) | Full (rate-limited, real `rate_open`/`rate_close`) | Model exists in `apps/` (Step 103), not wired into any fx27 controller demo yet |
| Estimator model | `stub` (noiseless two-point backward difference) | `alpha_beta` (noisy single-sensor filter); a real multi-sensor Kalman filter | `alpha_beta` built (Step 108) but `estimator_beta` unverified (Step 147 open); **a true Kalman filter does not exist in this codebase yet** — needed for the fixed comparison bench (§3) |

**User's stated intent on actuator dynamics** (2026-11-18): once wired, "full" (rate-limited) should
become the default going forward, not stay an opt-in alternate — real actuators always have finite rate,
and it doesn't touch the predictor math at all, so there's little reason for later comparisons to run
without it past the first "does this work at all" sanity check. This is now also formalized as part of the
fixed comparison bench in §3, not left as a per-version choice.

## 3. What each predictor variant is tested against

**Superseded (2026-11-18): this section originally proposed a stage-matched/rung-matched comparison
(compare 1.1-1.3 against a point-mass truth plant, 2.1 against a 2D truth plant). The user corrected this
— the comparison study uses a single, fixed, demanding bench for every built version, not a bench matched
to that version's own fidelity.** Rationale: judging a simpler controller against an easier bench than
real flight would flatter it and hide exactly the robustness gap the comparison exists to surface.

Two-layer validation:

1. **Internal consistency check (cheap, first, per predictor only — not part of the fixed bench below).**
   Does the new predictor agree with the *simpler* one in the degenerate case where both should give the
   same answer? (Numeric point-mass vs. analytical at constant `k`; 2D vs. point-mass numeric at zero AoA.)
   Catches implementation bugs before any simulation-level accuracy question is asked.
2. **Fixed comparison bench.** Every built version (every controller law × predictor model combination) is
   evaluated against the SAME external conditions: full actuator model (rate-limited), noisy sensor data
   run through a Kalman-filtered estimator (not `stub`, not even `alpha_beta` — see §2's open prerequisite,
   a real KF doesn't exist yet), and the 2D-with-disturbances truth plant (not a plant matched to the
   version's own predictor fidelity). This is what makes "compare every possible combination" (the user's
   own framing) a fair bake-off — every candidate is judged under the same realistic stress, regardless of
   how simple or sophisticated its own internal model is.
3. **Dispersion check.** A single nominal flight under the fixed bench only tells you about one noise/wind
   draw. A Monte Carlo pass via `apps/analysis/ensemble` is needed for the robustness comparisons (e.g.
   Tier 2's claimed noise-robustness edge over Tier 1) to mean anything.

**On 3D (open question, answered in `_docs/roadmap.md`'s "On 3D" section):** the fixed bench above uses
2D-with-disturbances, not 3D/6DOF, even though real flight is 3D. Recommendation there: compare first at
2D-with-disturbances, treat 3D as a final validation/re-tuning pass on the already-chosen design rather
than a prerequisite to starting the comparison — the controller only ever sees a reduced vertical-channel
abstraction of the true state regardless of plant dimensionality, so the *relative ranking* of candidates
is expected to transfer; gains may still need re-tuning once real 3D effects are included.

## 4. Compute-cost metric (practical starting point)

Not yet measured, but the cheapest useful first step: wall-clock time per predictor call
(`time.perf_counter()` around the predictor), on whatever host machine is running the comparison. This is
not an absolute flight-computer budget (that depends on actual target hardware, unknown for now), but the
*relative ordering* across variants — closed-form ≪ point-mass-numeric ≪ 2D-numeric ≪ MPC-horizon-search —
will almost certainly hold regardless of host. The real budget each predictor must fit inside is one
sample tick (`1/sample_rate_hz`); closed-form is trivially fine on anything, the numeric predictors are
where that budget check first becomes worth doing for real.

## 5. Out of scope for this note

File placement (which new predictor/controller code lives in `apps/` vs. `projects/fx27/`, mirroring the
Step 152 vs. Step 153 precedent — reusable-across-projects logic goes in `apps/`, fx27-specific wiring
stays in `projects/fx27/`) and exact module/test design are architect/developer decisions to make when
each version in `_docs/roadmap.md`'s Controller table is actually scoped, not predetermined here.
