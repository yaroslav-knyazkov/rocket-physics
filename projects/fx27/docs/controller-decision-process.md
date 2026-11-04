# How sensor/state/controller choices get made in real engineering projects

Standalone reference notes, extracted from an airbrake-controller planning conversation
(2026-11-03) on the `rocket-physics` project. General-purpose systems-engineering process
— not specific to any one project, kept here for personal reference.

Confirmed against two worked real-world examples found via literature research: a
university rocketry team's own published controller comparison (UMD/Karkinos, SAC
competition), and a published chance-constrained-optimal-control rocket airbrake design
(EUCASS 2019) that was actually flown. Both follow this flow end to end.

## The flow

1. **Start from the control objective**, not from "what can I measure." For an airbrake
   apogee controller, the objective is the terminal altitude at the top of the coast —
   not any instantaneous state. Getting this backwards (starting from available sensors)
   tends to produce an estimator/controller pair that's easy to build but doesn't actually
   target the right quantity.

2. **Derive the minimal sufficient state from the governing equations.** Write down (even
   informally) the dynamics that determine the objective, and ask which state variables
   actually appear in them. This is an observability question: a variable that doesn't
   appear in the equations governing the objective isn't worth measuring for this purpose,
   no matter how easy it is to sense.

3. **Choose sensors against that required state** — filtered by what's actually
   measurable, reliable, and affordable, not just by what's theoretically informative.
   A sensor that measures something relevant but has real-world reliability problems
   (sealing, resolution, drift) may lose to a less-direct but more robust alternative.
   Real example: barometric altitude + IMU won out over pitot-tube dynamic pressure for
   rocket airbrake velocity estimation across essentially every team surveyed — not
   because pitot data is theoretically wrong, but because it's least reliable exactly
   where control matters most (low dynamic pressure near the terminal event), and has
   real hardware failure modes (leaky tubing, resolution limits) on top of that.

4. **Design the estimator architecture to match the sensor suite's noise and nonlinearity**
   — not the other way around. A single clean sensor can get away with hand-tuned
   filtering; multiple sensors with different noise characteristics and sample rates
   usually want a proper Kalman filter (or EKF/UKF if any measurement model is nonlinear
   in the state), because that structure generalizes to N sensors without ad-hoc
   reconciliation logic. See the "wiring in multiple sensors" section below.

5. **Shortlist controller candidates from a known taxonomy** — a classification, not a
   lookup table:
   - **Classical**: P/PI/PID, lead-lag.
   - **State-space**: LQR, LQG.
   - **Predictive**: MPC (receding-horizon optimization over a control profile).
   - **Nonlinear**: sliding-mode, feedback linearization, backstepping.
   - **Adaptive/robust**: gain scheduling, adaptive control, H-infinity.
   - **Terminal-targeting / guidance lineage**: predictor-corrector and explicit guidance
     — the family entry/descent guidance algorithms (Apollo, Shuttle) belong to; relevant
     whenever the objective is a terminal condition reached through a drag-dominated,
     time-varying trajectory rather than a continuously tracked setpoint. Apogee targeting
     is structurally this same problem, sign-inverted.

   Which entry is *appropriate* is a judgment call driven by problem structure (regulation
   vs. tracking vs. terminal targeting), how much the plant model can be trusted, actuator
   bandwidth/limits, and computational budget — small embedded flight computers are a real
   constraint, not an afterthought: it's part of why real-world rocketry "MPC" usually
   degenerates to a cheap one-step-ahead search rather than solving a true receding-horizon
   optimization every cycle.

6. **Down-select empirically, not by intuition alone.** Run every serious shortlisted
   candidate through the *same* validated simulation, under the *same* uncertainty/
   dispersion model, scored by the *same* cost function (e.g. RMS terminal error + control
   effort). This is exactly what both real-world examples did:
   - UMD's comparative paper ran MPC vs. four PID variants vs. two LQR variants through one
     validated Simulink model, scored on cumulative weighted apogee error under
     uncertainty, and the winner was decided by that score — not by which controller
     "sounded more sophisticated."
   - EUCASS's chance-constrained design solved a full offline optimization against a
     distribution of flight uncertainty *before* ever flying, and reports a flown result.

   Real flight telemetry afterward feeds back into re-tuning the simulation/model itself —
   this is an iterative loop (test flight → compare telemetry to sim → re-tune model and/or
   controller → next test flight), not a one-shot decision made purely at a desk.

## Wiring in multiple sensors (why Kalman filters generalize better than hand-tuned fusion)

A Kalman filter's predict/update structure extends to any number of sensors without
needing new reconciliation logic each time one is added:

- **Predict**: every tick, propagate state and covariance forward through the process
  model (the system's own dynamics).
- **Update**: for *each* sensor, whenever a new sample from it arrives, compute the
  innovation (`measured value − value predicted by that sensor's own measurement model`),
  weight it by the Kalman gain — which encodes how much to trust this particular sensor
  relative to the filter's current state uncertainty — and apply the correction.
- **Different sample rates are fine.** Sensors don't need a common tick rate; each one's
  update simply runs whenever its own sample is ready.
- **Noise characteristics go into `R`** (the measurement-noise covariance; diagonal if
  sensors are independent of each other). **Unmodeled disturbance goes into `Q`** (process
  noise — wind gusts, thrust variability, anything the process model doesn't capture),
  usually tuned empirically.
- **Nonlinear measurement models need an EKF**, not a plain linear KF — e.g. a pitot
  tube's `V = sqrt(2·ΔP/ρ)` is nonlinear in the state, so that sensor's contribution needs
  linearization (a Jacobian) at each step rather than a fixed linear mapping.
- **How to tell if it's actually tuned well, rather than just guessed:** a
  normalized-innovation-squared (NIS) consistency check against its expected chi-square
  distribution is the standard diagnostic — a real test, not a vibe check.

## Tuning without a chirp/Bode sweep — split the loops, they're different kinds of systems

- A **repeatable, steady, ground-testable sub-system** (e.g. an actuator position/rate
  loop) can be chirped — on a bench, or in simulation — and tuned with classical
  Bode/phase-margin-based methods exactly as usual. Nothing unusual here.
- A **single-shot, time-varying, terminal-event system** (e.g. a coast-to-apogee
  trajectory) has no steady-state sinusoidal response to chirp in real operation — Bode-
  based tuning doesn't apply directly. Two techniques substitute for it, both evidenced in
  real published designs:
  1. **Local linearization at representative trim/operating points** along the nominal
     trajectory gives a family of local transfer functions that *can* be loop-shaped
     conventionally, point by point — this is effectively what gain-scheduled controller
     designs are doing.
  2. **Monte Carlo simulation-sweep optimization**: run the full closed loop (plant +
     estimator + controller) across a grid or numerical optimizer over controller
     parameters, under a distribution of initial conditions and disturbances, score each
     candidate on a cost function, and pick the minimizer — seeded by the linearized guess
     from (1), refined numerically. Both real-world examples above arrived at their flown
     gains this way: numerical optimization against an explicit uncertainty model, not
     manual guessing, with real flight data closing the loop afterward.
