# Airbrake controller — plan and decisions

**Status: pre-stage working notes**, not a `dev/docs/architecture-NN` document, no
tracker stage opened yet. When the user is ready to turn this into a tracked stage,
this file is the starting brief for `product`/`architect`.

Lives in `projects/fx27/docs/` (user's request) because this is FX27-vehicle-specific
controller work on top of the core `apps/` sim library, not a library architecture change.

**This file holds decisions only** — the plan, the sensor choice, the controller-tier
choice, and what's still open. Supporting literature/citations live in
`airbrake-controller-research.md`; general "how these choices get made" methodology
lives in `controller-decision-process.md`; the formal plan-vs-code reconciliation lives
in `architecture-controller-reconciliation.md`. Don't restate their content here —
link to it.

## 1. What already exists — don't rebuild

- `apps/optimization/airbrake_sizing/solve_cda.py` (`solve_airbrake`) — static,
  open-loop airbrake area sizing for a fixed target apogee (Rung 0). Answers "how big
  should the brake be," not "how should it modulate in flight."
- `apps/sim/engine/` already carries a full attitude state (rotational dynamics,
  `_cross_y`/`derivatives`); the "point mass" framing used at low rungs is a
  frozen-attitude special case (`aero.model="constant"`, `omega=0`), not a separate
  solver. Rung 5 ("port to 2D") turns this back on — confirm with `architect` before
  writing new 2D equations of motion.
- `apps/analysis/ensemble` — Monte Carlo/dispersion tooling already exists; reuse it for
  every dispersion checkpoint below instead of building a parallel harness.
- `apps/control/flight_software/laws.py` + `estimator.py` — Tier 1 controller (P and PI
  laws on a closed-form predicted-apogee error) and a single-sensor alpha-beta estimator
  already exist, pre-dating this plan (Phase 2.17, Steps 107/108). See §3/§4 below for
  exactly what this covers and what it doesn't.
- `apps/control/flight_software/harness.py` (Step 146, 2026-11-04) — closed-loop
  integration harness: runs one flight through `run_sim`, replays the actuator
  trajectory, returns flat metrics (`apogee_m`, `apogee_error_m`,
  `actuator_saturation_fraction`, `actuator_travel`). QA PASS, `tests/test_harness.py`
  (7 tests). This is the harness §3's tuning work and §5's empirical KF-vs-alpha-beta
  question both depend on — it exists now, it did not before Step 146.

## 2. Fidelity ladder (the plan)

Two axes run in parallel, don't conflate them: **plant fidelity** (what the "truth" sim
models) and **estimator/sensor fidelity** (what the controller actually gets to see).

| Rung | Plant | Estimator / sensors | Actuator | Controller tier | Status |
|---|---|---|---|---|---|
| 0 | n/a — static sizing | n/a | n/a | n/a | done (cspace); **pending (euroc)** — blocked on an external colleague's Barrowman-based Mach-curve generator, not a coding gap, see §6 |
| 1 | Point-mass, `Cd_brake` linear in extension | Perfect state | Instantaneous | Tier 1 — predictive P/PD on apogee-prediction error | **DONE** — `laws.py`, 19/19 `test_controllers.py` |
| 2 | Same | Perfect state | Rate-limited + position-feedback | Tier 1, retuned for lag | **DONE as of Step 146** — actuator model existed since Step 103, Step 146 is the first place it actually runs together with the Tier-1 laws |
| 3 | Same | Noisy sensors + baro-inertial estimator (complementary/Kalman) | Same | Promote to Tier 2 (switching-curve blend) | **PARTIALLY DONE** — single-sensor alpha-beta filter exists and now runs end-to-end (Step 146); `estimator_beta` gain still unverified; still single-sensor, not a true baro+IMU KF (see §5) |
| 4 | Add `Cd(extension, Mach)` | Same estimator | Same | Tier 2 | **NOT STARTED** — bounded change to `laws.py`/`estimator.py` only, no new sim machinery needed |
| 5 | Port to 2D — reuse `apps/sim/engine` attitude dynamics | Needs attitude (gyro/quaternion) to resolve IMU specific force into vertical | Same | Tier 2 | not started |
| 6 | Add α-dependent aero | Same | Same | Tier 2 | not started |
| 7 | CFD lookup table replaces parametric Cd sum | Same | Same | Consider Tier 3 (MPC) — only pays off once the predictor is this accurate | not started |
| 8 | Wind-tunnel dataset swap-in | Same, cross-check online Cd estimate against CFD-vs-tunnel gap | Same | Tier 2 or 3 + adaptive/online-Cd correction layer | not started |
| checkpoints | — | — | — | — | Monte Carlo dispersion pass (`apps/analysis/ensemble`) at rungs 4, 6, 8 minimum |

Status column is per `architecture-controller-reconciliation.md` S2 (direct code read,
2026-11-04) plus Step 146's closure of most of Rung 2/3's wiring gap — treat that doc as
the source of truth over this table if they ever disagree; update this table, not it.

## 3. Sensor choice (decision)

**Target architecture** (confirmed by literature research across ~8 independent teams +
commercial altimeter vendors, see `airbrake-controller-research.md` §1/§1.4):

| Quantity | Sensor | Role | Needed from |
|---|---|---|---|
| Altitude `h` | Barometer, referenced to pad pressure | Primary — direct controller input | Rung 1 |
| Vertical velocity `v` | Derived: baro-inertial fusion of barometer + **accelerometer** | Primary — direct controller input (the other arg of `drag_aware_predicted_apogee`) | Rung 1 — this is not an attitude/2D-only concern, it's needed for the vertical-velocity estimate even in the 1D treatment every surveyed team uses |
| Attitude (tilt off vertical) | **Gyro**, dead-reckoning (Woody & Van Bibber) or assumed-zero (UMD/Karkinos) | Projects the accelerometer's specific-force reading onto the true vertical axis — without this, a tilted vehicle's accelerometer reading is misread as vertical deceleration | Rung 1 in principle (even "assume zero tilt" is a choice about this), becomes load-bearing at Rung 5 (2D) once tilt is no longer negligible |
| Angular velocity (body rates) | Gyro (same sensor as attitude — attitude is gyro integrated, not a separate measurement) | Only matters once rotational dynamics are on (Rung 5+); not an input to the apogee predictor itself, only to the attitude estimate that feeds it | Rung 5 |
| Angular acceleration | **Not directly sensed** by any source found — derived from gyro rate-of-change or from the plant's own moment equations, never its own sensor channel | Not a controller input in any literature source found; not planned as a controller input here either | n/a |
| Axial acceleration (raw, pre-fusion) | Accelerometer | Doubles as the input to the adaptive Cd-mismatch layer (§4): `m·a_axial − gravity` vs. the onboard drag model | From whenever that layer is adopted |
| Angle of attack / horizontal velocity | **No direct sensor found in any source** — no vane, multi-port probe, or flush air-data sensing on any competition/amateur airbrake system surveyed | Teams either assume zero tilt (1D treatment, UMD) or track attitude via gyro to project the accelerometer without needing true AoA (Woody & Van Bibber) — **neither measures AoA/horizontal velocity directly**, and neither does this plan | not planned |
| Drag coefficient `Cd` | Not sensed — backed out from density + accelerometer (+ pitot if wired in) | Secondary/derived, feeds the adaptive/online-Cd-correction layer, not the primary control law | from whenever that layer is adopted |

**Primary sensors, bottom line**: barometer + accelerometer (+ gyro once attitude
matters, Rung 5+), fused via a baro-inertial Kalman or complementary filter.
**Secondary**: pitot/dynamic-pressure tube — independent Cd-verification channel only,
never the primary velocity source, because it's noisiest exactly near apogee (q→0) and
has real recurring hardware reliability problems (sealing, resolution) on top of that.
**Alternative to baro**: GNSS/GPS-inertial fusion, seen in a few baro-free designs — not
pursued here, noted for completeness.

**Current implementation** (Rung 3, partial): `estimator.py` is single-sensor —
barometric altitude only, via `"stub"` (backward difference) or `"alpha_beta"` (Kalata
g-h filter). **No accelerometer fusion yet** (so the vertical-velocity estimate is
derived from baro alone, not baro+accelerometer as the target architecture calls for),
no gyro/attitude tracking (fine for now, Rung 5 hasn't landed), no pitot integration
anywhere in code. This is a known, named gap (`estimator_beta` flagged `UNVERIFIED` in
`apps/sim/engine/params.py`), not an oversight — closing it is scoped as a future step,
not decided yet (see §5, §6).

## 4. Controller choice (decision)

**Extension actuator — PID, confirmed.** Standard cascaded PID (outer position loop →
inner rate/torque loop). Unaffected by which trajectory tier drives it. Revisit only if
real hardware exposes stiction/backlash the sim doesn't model.

**Trajectory (apogee targeting) — NOT plain state-feedback PID.** Apogee is a terminal
quantity (there's no instantaneous setpoint for altitude/velocity during coast); every
sane design here is model-based/predictive. Three tiers, matched to the fidelity ladder:

- **Tier 1 — predictive P/PD on apogee-prediction error.** Forward-integrate (or, as
  built, closed-form) the plant from current state to `v=0` holding extension constant;
  feed `target − predicted` through a P/PD gain. Cheap, scales through every rung
  unchanged. **Already implemented** (`laws.py::proportional_drag`/`pi_apogee`) —
  this is Rung 1, done.
- **Tier 2 — switching-curve / bounding-trajectory blend.** Predict apogee at both brake
  extremes (full retract / full extend); interpolate linearly between them toward the
  target; saturate outside the bounds. Standard shape for drag-modulation terminal
  guidance — the softened real-time analogue of bang-bang. **Promote here at Rung 3**
  (sensor noise entering) and keep through most of the ladder.
- **Tier 3 — model predictive control (receding horizon).** Re-solve each cycle for an
  extension-vs-time profile (not just "hold constant"), subject to the actuator's rate
  limit. Only worth it once the forward predictor is CFD-grade — **Rung 7+**. Note:
  nearly every flown competition system calling itself "MPC" (UMD/Karkinos, UGA,
  Mississippi State, uOttawa, TARS) is actually a one-step-ahead brute-force search over
  a held-constant extension — i.e. Tier 1 with a discrete search instead of a continuous
  gain, not true receding-horizon Tier 3. A genuine Tier 3 was not found flown anywhere
  in the literature survey. Don't over-build expecting to match what rocketry papers
  call "MPC" — a well-tuned Tier 1/2 already is that.
- **Adaptive/robustness layer** (cross-cutting, not a separate rung): feed an online
  Cd-mismatch estimate (measured drag from `m·a_axial` minus gravity, vs. the onboard
  model) back into whichever tier is active as a correction. Earns its keep once sensor
  noise (Rung 3) and CFD-vs-wind-tunnel discrepancies (Rung 8) are both in play. Worth
  noting it's a legitimate *standalone* primary controller too, not only an add-on —
  Virginia Tech's ROADKILL flies exactly this (PID on measured-vs-modeled Cd) as their
  primary controller, not apogee error.
- **Fourth option, model-free, with flight validation** (Woody & Van Bibber, AIAA
  2025-0111): a closed-form required-deceleration profile derived from coast-phase
  kinematics (no drag/Cd model needed at all), tracked by a plain PI comparing measured
  axial deceleration to that commanded value. Attractive specifically during the early,
  still-crude-Cd-model rungs (1–6) — worth prototyping alongside Tier 1, not necessarily
  instead of it.

**Recommendation, one line:** Tier 1 at Rung 1 (done) → Tier 2 from Rung 3 onward →
Tier 3 considered only at Rung 7+ if Tier 2 isn't good enough once CFD-grade drag data
exists. Actuator stays a plain cascaded PID throughout.

## 5. Open — next steps not yet started/approved

- **`estimator_beta` tuning.** Now possible (Step 146's harness is the prerequisite),
  not yet done. Method per `controller-decision-process.md` §"Tuning without a chirp" —
  local linearization + Monte Carlo sweep via `apps/analysis/ensemble`, not guessing.
  Not started — needs user go-ahead as its own step.
- **Multi-sensor KF vs. single-sensor alpha-beta.** Deliberately deferred per architect's
  S5 — no empirical basis existed before Step 146; the harness now produces that
  evidence as a side effect of the tuning run above. Don't decide this speculatively
  before that data exists.
- **Rung 4 (`Cd(extension, Mach)`).** Small, bounded change to `laws.py`/`estimator.py`
  alone, no new sim machinery — reasonably deferred until the tuning/KF questions above
  are answered, since there's no harness benefit yet to observing Rung 4's effect in.
- **Reaction wheel as a secondary fine-control actuator** (user idea, interpretation
  unconfirmed): deferred until Rungs 7–8 (CFD/wind-tunnel fidelity) show whether
  airbrake-only drag authority is actually a limiting factor. Don't build before that's
  known to be a real gap.
- **Deployment lockout window** (min/max time after burnout, or a dynamic-pressure
  floor/ceiling) — common in real systems, not decided here yet.
- **Control-loop update rate** — ties to sensor sample rates once that's modeled.
- **When to formally hand this to `product`/`architect` as a tracked stage** — not yet;
  still research/brainstorming per the user's own framing.

## 6. Euroc Rung 0 gap

Blocked externally, not a coding gap: per a parallel session's own
`vehicle-dynamics-roadmap.md` (F4), euroc Mach-dependent drag work is waiting on a
colleague's Barrowman-based Mach-curve generator script. No `runs/euroc_airbrake.py`
exists yet (cspace has one, `cspace_airbrake.py`). Nothing to do here until that
external input arrives.

## 7. Pointers

- `airbrake-controller-research.md` — literature findings backing §3/§4 (sensor suites
  and controller architectures actually used on flown/competition rocketry, with
  citations).
- `controller-decision-process.md` — general "how sensor/state/controller choices get
  made in real projects" methodology (not project-specific), kept standalone per the
  user's own request.
- `architecture-controller-reconciliation.md` — the formal architect reconciliation of
  this plan against actual code (2026-11-04); authoritative on per-rung status (§2's
  source).
- `dev/docs/qa-report-step146-controller-harness.md` — QA verification of the Step 146
  harness referenced in §1/§2.
