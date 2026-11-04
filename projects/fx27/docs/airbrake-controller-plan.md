# Airbrake controller — fidelity-ladder plan and controller-type notes

**Status: pre-stage brainstorming notes**, captured by the orchestrator from a
planning conversation with the user (2026-11-03). Not a `dev/docs/architecture-NN`
document, not yet approved by anyone as a committed stage — no tracker entry
exists for this work yet. When the user is ready to turn this into an actual
stage, this file is the starting brief for `product`/`architect`, not a
substitute for their output.

Lives in `projects/fx27/docs/` (user's request) rather than `dev/docs/`,
because this is FX27-vehicle-specific controller work sitting on top of the
core `apps/` sim library, not a change to the library's own architecture.

## 0. What already exists — don't rebuild these

- `apps/optimization/airbrake_sizing/solve_cda.py` (`solve_airbrake`) — static,
  open-loop airbrake area sizing for a fixed target apogee. Wrapped here as
  `projects/fx27/point/airbrake.py::size_airbrake`. This answers "how big
  should the brake be," not "how should it modulate in flight" — the sizing
  result is a natural upper bound / sanity check for the closed-loop
  controller work below (the achievable apogee band at full vs. zero
  extension should bracket the target this solver was given).
- `apps/sim/engine/` already carries a full attitude state (rotational
  dynamics, `_cross_y`/`derivatives`) — per `projects/fx27/README.md`, the
  "point mass" naming in this port is a frozen-attitude special case
  (`aero.model="constant"`, `omega=0`), not a separate solver. **Rung 5 below
  ("port to 2D") is very likely "turn attitude dynamics back on and add an
  airbrake drag/moment term," not a new model from scratch.** Confirm with
  `architect` before writing new 2D equations of motion.
- `apps/analysis/ensemble` — dispersion/Monte Carlo tooling already exists
  for wind/density/thrust variability; reuse for the dispersion checkpoints
  below instead of building a parallel harness.

## 1. Fidelity ladder

Two axes run in parallel and should not be conflated: **plant fidelity**
(what the "truth" sim models) and **estimator/sensor fidelity** (what the
controller actually gets to see). The user's original plan was plant-fidelity
only; estimator fidelity, actuator dynamics, and the controller-tier choice
are added here.

| Rung | Plant | Estimator / sensors | Actuator | Controller tier | Validation checkpoint |
|---|---|---|---|---|---|
| 0 (done for cspace, **pending for euroc**) | n/a — static sizing | n/a | n/a | n/a | `size_airbrake`/`runs/cspace_airbrake.py` covers cspace; no `runs/euroc_airbrake.py` exists yet — euroc campaign has `euroc_comparison.py`/`euroc_sweep.py` but no airbrake-sizing entry point. Needs a small developer task mirroring `cspace_airbrake.py` for euroc before rung 0 is actually closed for both campaigns. |
| 1 | Point-mass, along-trajectory, `Cd_brake` linear in extension | Perfect state (no noise) | Instantaneous extension | **Tier 1** — predictive P/PD on apogee-prediction error | Fixed target+tolerance+nominal-trajectory scenario defined here, reused unchanged through every later rung |
| 2 | Same plant | Perfect state | Rate-limited + position-feedback actuator | Tier 1, retuned for actuator lag | Same scenario, now with actuator saturation near max-q |
| 3 | Same plant | **Noisy sensors + baro-inertial estimator** (complementary/Kalman) — this is the "noise step" the user is deferring; do it here, not later | Same | Promote to **Tier 2** (switching-curve blend) — more robust to noisy/biased state than Tier 1's raw predicted-error P | Same scenario under noise; compare Tier 1 vs Tier 2 degradation |
| 4 | Add `Cd(extension, Mach)` | Same estimator | Same | Tier 2 | Same scenario |
| 5 | Port to 2D — reuse `apps/sim/engine` attitude dynamics (§0), don't hand-build | Estimator now needs attitude (gyro/quaternion) to resolve IMU specific force into vertical | Same | Tier 2 | Same scenario; check whether α-induced coupling breaks the "ignore horizontal velocity" assumption |
| 6 | Add α-dependent aero | Same | Same | Tier 2 | Same scenario |
| 7 | CFD lookup table replaces parametric Cd sum | Same | Same | Consider promoting to **Tier 3 (MPC)** — only pays off once the predictor is this accurate | Same scenario; compare Tier 2 vs Tier 3 |
| 8 | Wind-tunnel dataset swap-in (same table interface) | Same, now also cross-check online Cd estimate against CFD-vs-tunnel gap | Same | Tier 2 or 3, + adaptive/online-Cd correction layer (see §2) | Same scenario |
| checkpoints | — | — | — | — | Monte Carlo dispersion pass (`apps/analysis/ensemble`) at rungs 4, 6, 8 at minimum |

## 1.4 Major correction — Tier 1/partial-Tier-3-estimator already exists, pre-dating this plan (2026-11-04)

**This plan doc was wrong to treat Rung 1-3 as unbuilt.** A parallel session's own
`vehicle-dynamics-roadmap.md` (same folder) correctly flagged that
`apps/control/flight_software/laws.py` already exists; this session had not checked
before drafting §1's ladder. Verified directly against the actual code:

- `apps/control/flight_software/laws.py` — `drag_aware_predicted_apogee(h, v, g, m, k)`:
  a **closed-form** (not numerical forward-sim) drag-only ballistic-coast apogee
  predictor, `k = 0.5*rho_hat*(onboard_CdA0 + onboard_CdA_brake*f_b)` — i.e. drag area
  linear in the brake's extension fraction `f_b`, **exactly Rung 1's plant assumption**.
  Two registered laws consume it: `proportional_drag` (P on predicted-apogee error) and
  `pi_apogee` (PI, with anti-windup) — **this is Tier 1, already implemented and tested**,
  not something to build from scratch.
- `apps/control/flight_software/estimator.py` — two models behind `estimator.step()`:
  `"stub"` (two-point backward difference, exact only for a noiseless measurement) and
  `"alpha_beta"` (Step 108: a real constant-velocity alpha-beta/g-h filter — position+
  velocity recursively estimated from a single noisy/lagged barometric altitude
  measurement). **This is a working, if single-sensor, noisy-estimator — most of Rung
  3**, not absent. Gap: single-sensor (baro only, no accelerometer fusion yet, so not a
  full baro-inertial KF) and its own gain is explicitly flagged
  `estimator_beta: 0.1667 # UNVERIFIED placeholder, see §108.8.3` in `apps/sim/engine/
  params.py` — i.e. **exactly the "tuning without a chirp" problem from §2.5 is already a
  live, named gap in this codebase**, not a future concern.
- `apps/sim/engine/control.py`/`params.py` — actuator rate-limiting already exists
  (confirmed by grep: `rate_limit`/`slew` hits in `control.py`, `params.py`,
  `integrate.py`) — **Rung 2 is also at least partially already built.**
- `onboard_CdA0`/`onboard_CdA_brake` are explicitly the **controller's own internal
  model** of drag, separate from whatever the sim's true `aero.model` actually computes
  — i.e. the scaffolding for a sim-vs-onboard model-mismatch study (the adaptive/Cd-
  correction idea from §2, "robustness layer") already exists structurally, unused so far.
- `tests/test_controllers.py` — 19/19 passing today (2026-11-04), covering both laws and
  both estimator models.
- Source: `dev/docs/architecture-35-paper-alignment.md` SS35.4.4 (laws), Step 107/108
  (estimator) — built under **Phase 2.17** (the project's main ongoing paper-alignment
  stage), unrelated in origin/motivation to this week's planning conversation.

**Implication:** the next concrete coding step is very likely *not* "implement Rung 1" —
it's closing the specific, already-named gaps above (verify/tune `estimator_beta`; decide
whether `alpha_beta` is sufficient or a real multi-sensor KF is needed; confirm the
existing rate-limited actuator is actually wired to these laws in a runnable scenario) and
*then* deciding what Rung 4+ actually requires on top of this. Don't re-scope Rung 1-3
from zero — reconcile against this first. Handed to `architect` to do that reconciliation
properly (2026-11-04); see tracker for outcome.

## 1.5 Revision after research (2026-11-03)

`projects/fx27/docs/airbrake-controller-research.md` (literature grounding, citations
there) confirms §2's reasoning in substance but requires two corrections:

- **Terminology trap.** Nearly every flown competition system that calls itself "MPC"
  (UMD/Karkinos, UGA, Mississippi State, uOttawa, TARS) is, on inspection, a one-step-ahead
  binary/brute-force search over a *held-constant* extension, forward-simulated to apogee —
  i.e. exactly Tier 1 below, just with a discrete search instead of a continuous P/PD gain.
  A genuine receding-horizon multi-step extension-*profile* optimization (strict Tier 3) was
  **not found flown anywhere** in the sources surveyed. Don't reach for "real" MPC machinery
  expecting to match what rocketry papers call MPC — Tier 1, tuned well, already is that.
- **A fourth, model-free option exists and has flight validation**: Woody & Van Bibber (AIAA
  2025-0111) derive a closed-form required-deceleration profile from coast-phase kinematics
  (separation of variables, no drag/Cd model needed) and track it with a plain PI controller
  comparing *measured* axial deceleration (accelerometer) to that *commanded* deceleration.
  Because it never needs an accurate Cd(extension, Mach, α) model, it's attractive precisely
  during the early fidelity rungs (1-6) where that model is admittedly still crude — worth
  prototyping alongside Tier 1, not necessarily instead of it, since the fidelity ladder's
  truth-model rungs are still useful for testing this approach too.
- The adaptive Cd-mismatch layer (§2, "robustness layer") is not merely a later add-on: Virginia
  Tech's ROADKILL flies it as their **primary** controller (PID on measured-vs-modeled Cd, not
  apogee error), confirming it's a legitimate standalone choice, not only a correction bolted
  onto Tier 1/2.
- Sensor side: §0/earlier discussion's baro-referenced-to-pad-pressure + baro-inertial Kalman
  fusion, and pitot-as-secondary-not-primary, are both confirmed across ~8 independent team
  reports and commercial altimeter docs. One nuance: pitot noise/unreliability isn't only a
  near-apogee q→0 effect — the ICAS 2022 paper also reports real sealing/resolution hardware
  failures throughout flight, independent of the q→0 argument.

## 2. Controller type

### Extension actuator — PID, confirmed

Standard cascaded PID (outer position loop → inner rate or current/torque
loop) is the right call. It's unaffected by which trajectory-controller tier
is driving it from above — it just executes whatever net extension command
comes down. Revisit only if real hardware exposes stiction/backlash the sim
doesn't model; a feedforward term for expected aero-load torque on the panel
is the natural first addition if that happens, not a different controller
family.

### Trajectory (apogee targeting) — NOT plain state-feedback PID

Apogee is a **terminal** quantity: there is no instantaneous setpoint for
altitude or velocity at each moment during coast (altitude is still climbing
toward an apogee that hasn't happened yet). A PID on `(h - h_target)` would be
fighting the wrong dynamic. Every sane design here is model-based/predictive
in some form. Three tiers, increasing complexity, matched to the fidelity
ladder above:

**Tier 1 — predictive P/PD on apogee-prediction error.** Each control cycle,
numerically integrate the plant model forward from the current state to
`v=0` holding extension constant, giving a predicted apogee `ĥ`. Feed
`target − ĥ` (and its trend, for PD) through a proportional controller to
adjust extension, saturating to `[0, max]`. Cheap, reuses whatever plant
model the current rung already has, and scales through every fidelity rung
unchanged — including the CFD table, where it just becomes a better (slower)
predictor. **Start here at rung 1.**

**Tier 2 — switching-curve / bounding-trajectory blend.** Each cycle, predict
apogee twice: brakes fully retracted and fully extended from now. If the
target sits between the two, set extension by linear interpolation between
the bounds (proportional guidance against both bounds, not against a single
point prediction); outside the bounds, saturate — shouldn't happen if rung 0's
sizing was done right. This is the standard shape for drag-modulation
terminal guidance (the real-time, softened analogue of the minimum/maximum-
effort bang-bang solution to this problem). It converges faster and degrades
more gracefully near actuator saturation than Tier 1, and partially cancels
shared model bias because both bounding predictions come from the same
(possibly wrong) model. **Promote here once sensor noise enters, rung 3**,
and keep it through most of the ladder.

**Tier 3 — model predictive control (receding horizon).** Generalizes
Tier 1/2 to arbitrary extension-vs-time profiles (not just "hold constant"):
re-solve each cycle for the extension trajectory (even a cheap one-parameter
family like "ramp then hold") that minimizes predicted apogee error subject
to the actuator's rate limit. Only worth it once the forward predictor is
trustworthy — **rung 7+ (CFD table)**. Before that it's just Tier 1/2 with
extra machinery, since "hold extension constant" is a fine approximation when
the plant model itself is still the bigger source of error.

**Adaptive/robustness layer (not a separate rung, a cross-cutting addition):**
feed the online Cd-mismatch estimate (measured drag from `m·a_axial` minus
gravity, vs. modeled `Cd·q·S` — see the sensor/state notes from the prior
conversation) back into whichever tier is active as a multiplicative
correction to the predictor. Earns its keep once sensor noise (rung 3) and
real CFD-vs-wind-tunnel discrepancies (rung 8) are both in the picture — not
worth building before then.

**Recommendation in one line:** Tier 1 at rung 1 → Tier 2 from rung 3 onward
→ Tier 3 considered only at rung 7+ if Tier 2 isn't good enough once CFD-grade
drag data exists; actuator stays a plain cascaded PID throughout.

## 2.5 Methodology notes — estimator wiring and controller tuning (2026-11-03)

Captured from a follow-up conversation; general-engineering-process notes, not yet
project-specific decisions.

**Rung 3 clarifies to:** the Kalman (or complementary) filter is something *you build*,
not something a sensor hands you. Real sensors output raw counts (pressure, raw
acceleration); no commercial rocketry sensor suite outputs a pre-fused state. The rung-3
deliverable is literally an estimator module (would live under `apps/control/`) that
consumes synthesized noisy sensor samples and outputs `(h_est, v_est, ...)`; the
controller is then rewired to consume that estimate instead of the plant's true state.
Starting with a hand-tunable complementary filter before a full Kalman filter is a
reasonable intermediate step, but a real KF generalizes more cleanly once sensor count
grows past one (see below), which is itself an argument for not skipping straight past it.

**How sensor/state/controller choices get made in real projects, in general** (systems-
engineering flow, confirmed by the research doc's own sources — UMD's and EUCASS's papers
are both literally worked examples of this flow):
1. Start from the control objective (here: terminal apogee), not from "what can I measure."
2. From the governing equations, determine the *minimal sufficient* state that affects
   that objective (observability question) — this is where our sensor/state analysis
   (§ earlier conversation, confirmed in the research doc Area 1) comes from.
3. Choose sensors against that required state, filtered by what's actually measurable,
   reliable, and cheap enough (baro+IMU won on all three fronts across every team surveyed;
   pitot lost on reliability specifically).
4. Design the estimator architecture to match the sensor suite's noise/nonlinearity/rate
   characteristics (complementary filter → linear KF → EKF/UKF as nonlinearity grows).
5. Select a controller architecture from a known *taxonomy*, not a fixed checklist — the
   taxonomy exists (classical: P/PI/PID, lead-lag; state-space: LQR/LQG; predictive: MPC;
   nonlinear: sliding-mode, feedback linearization, backstepping; adaptive/robust: gain
   scheduling, adaptive control; and for terminal-targeting problems specifically, the
   aerospace-guidance lineage — predictor-corrector / explicit guidance, e.g. Shuttle/Apollo
   entry guidance, which is exactly what Woody & Van Bibber's analytic law descends from) —
   but *which* entry wins is decided empirically per-problem (next point), not read off a
   table.
6. Down-select by running every serious candidate through the same validated simulation
   under the same uncertainty/dispersion model, scored on the same cost (apogee error bias
   + spread + control effort) — this is exactly what UMD's comparative paper did (MPC vs.
   4 PID variants vs. 2 LQR variants) and what the EUCASS chance-constrained paper did
   (offline optimization against a full uncertainty distribution before ever flying).
   Real-flight telemetry then feeds back into re-tuning the sim/model (iterative test-flight
   calibration loop) — not a one-shot decision.

**Wiring in multiple sensors:** the Kalman filter's predict/update structure generalizes
to N sensors directly — this is one of its main structural advantages over a hand-built
complementary filter. Predict step: propagate state + covariance forward via the process
model (the plant dynamics) every tick. Update step: for *each* sensor, whenever a new
sample from it arrives, compute the innovation (measured − predicted-via-that-sensor's-own
measurement-model), weight it by the Kalman gain (which encodes how much to trust this
sensor vs. the current state uncertainty), and correct the state. Different sensors can
run at different sample rates (baro/pitot slower, accelerometer/gyro faster) — handled by
only running each sensor's update when its own sample is ready, not by forcing a common
rate. Each sensor's noise characteristic goes into the measurement-noise matrix `R`
(diagonal if sensors are independent); the process-noise matrix `Q` encodes how much
unmodeled disturbance (wind gusts, thrust variation) you expect between updates, and is
usually tuned empirically. If any sensor's measurement model is nonlinear in the state
(e.g. pitot's `V = sqrt(2ΔP/ρ)`), that sensor needs an EKF (linearize via Jacobian at each
step) rather than a plain linear KF; a consistency check (normalized innovation squared
against its expected chi-square distribution) is the standard way to tell whether `Q`/`R`
are tuned well, not guesswork.

**Tuning without a chirp/Bode sweep:** split the two loops, because they're not the same
kind of system.
- The **actuator loop** (extension PID) is a repeatable, steady, ground-testable system —
  bench-chirp the real servo+panel (or its simulated model) and classical loop-shaping
  (Bode/phase-margin-based PID tuning) applies exactly as usual. Nothing unusual here.
- The **trajectory/guidance loop** is not repeatable or steady — coast-to-apogee is a
  single-shot, finite-horizon, time-varying nonlinear event; there's no steady-state
  sinusoidal response to chirp in real flight. Two complementary techniques stand in for
  classical loop-shaping, both already evidenced in the research doc:
  1. **Local linearization at representative trim points** (fixed altitude/Mach/mass
     snapshots along a nominal trajectory) gives a family of local transfer functions you
     *can* loop-shape conventionally — this is what gain-scheduled designs (LASC 2025
     paper's gain-scheduling layer) are effectively doing, point by point.
  2. **Monte Carlo sim-sweep optimization**: run the full closed-loop sim (plant +
     estimator + controller) across a grid/optimizer over controller parameters and a
     distribution of initial conditions/disturbances (reuse `apps/analysis/ensemble`),
     score each candidate on a cost (RMS apogee error + control effort), and pick the
     minimizer — seeded by the linearized estimate above, refined numerically. This is
     exactly the methodology both UMD's comparative paper and EUCASS's chance-constrained
     paper used to arrive at their flown gains — not "smart guessing," but numerical
     optimization against an uncertainty model, with real test-flight data closing the loop
     afterward by re-tuning the sim itself.

## 2.6 Idea to evaluate — reaction wheel as a secondary fine-control actuator (2026-11-03)

User suggestion, placement interpreted (confirm/correct if wrong): once the plant/
estimator fidelity reaches CFD/wind-tunnel grade (rungs 7-8), evaluate adding a
**reaction wheel** as a second actuator alongside the airbrake, to fine-tune the
trajectory controller beyond what airbrake-only drag authority can do. Not scoped
further yet — open questions once revisited: what physical effect it would modulate
(small pitch/trim-induced angle-of-attack to add/remove a little extra drag, vs. a
genuinely separate control channel), whether `apps/sim/engine`'s existing rotational
dynamics (already real from rung 5 onward) is enough to model its effect without new
physics, and whether it's worth the mass/complexity budget on the real vehicle at all
or is purely a simulation/academic exercise. Revisit once rungs 7-8 show whether
airbrake-only authority is actually a limiting factor — don't build this before that's
known to be a real gap.

## 3. Open questions, deferred to when this becomes a real stage

- Deployment lockout window (min/max time after burnout, or a dynamic-
  pressure floor/ceiling) — common in real systems, not decided here.
- Control-loop update rate (ties to sensor sample rates once that's modeled).
- Whether Tier 3 (MPC) is ever actually necessary, or Tier 2 is good enough
  through the CFD/wind-tunnel rungs — an empirical question for rung 7/8, not
  a design decision to make now.
- When to formally hand this to `product`/`architect` as a tracked stage
  (currently: not yet — still research/brainstorming per user's explicit
  framing).

## 4. Companion research artifact

`projects/fx27/docs/airbrake-controller-research.md` (literature grounding:
real sensor suites and controller architectures used on actual competition/
amateur-rocketry airbrake systems) — requested separately, see that file for
citations backing or challenging §2's tier recommendation and the prior
sensor/state discussion.
