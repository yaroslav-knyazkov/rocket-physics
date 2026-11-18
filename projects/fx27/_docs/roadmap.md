# fx27 Roadmap

## General

**Version-id protocol:** `<solver-stage>.<sequence>`.

- **Stage 0 — dependencies.** Not part of the flow itself — infrastructure/data the flow below depends on, out of the chronological sequence (its own internal "when was it built" doesn't determine where it sits; its role does).
- **Stage 1 — point mass.** Everything below right now. Attitude frozen (`C_z=C_m=c_mq=0`), one reference radius per rocket, no fin/CP geometry.
- **Stage 2 — 2D rigid body.** Reserved for when attitude dynamics turn back on (vehicle-dynamics roadmap item F7 — "very likely turn `omega`/`C_z`/`C_m` back on"). First item there is `2.1`, not a continuation of stage 1's numbering.
- **Stage 3 — 3D / full 6DOF.** Reserved the same way; first item `3.1`.

Sequence within a stage is plain chronological order of when the work actually happened — not grouped/lettered by analysis type (cspace vs euroc, dc vs dm are called out in the `name` column instead). Stage 0 is the exception: it's not chronological, it's whatever the flow currently depends on.

| id | name | current file | description |
|----|------|---|---|
| 0.1 | Theory-based Mach-dependent drag (in progress) | `data/utils/aero/drag_theory.py`, `data/cspace/aero/generate_theory_drag_tables.py` | Niskanen/OpenRocket-method C_D0(M) from component geometry — a **dependency** feeding the dm rows (1.5-1.8), not a step in the flow itself. Currently `PRO54_TRANSITION_DM` only, side-by-side comparison variant. `drag_theory.py` itself lives under `data/utils/aero/` (Step 157) since it's campaign-agnostic; the generator and its cspace-specific output CSV stay under `data/cspace/aero/`. |
| 1.1 | Cspace comparison (constant drag) | `runs/point/01_cspace_comparison_dc.py` | Baseline 3-rocket cspace flight comparison, constant-C_x (dc) rockets only. |
| 1.2 | Cspace ideal mass (constant drag) | `runs/point/02_cspace_ideal_mass_dc.py` | Solves the minimum airframe mass that hits the 2500 m target apogee, per dc rocket. |
| 1.3 | Cspace ideal drag (constant drag) | `runs/point/03_cspace_ideal_drag_dc.py` | Solves the C_x scale factor that hits the target apogee, per dc rocket. |
| 1.4 | Cspace ideal airbrake sizing (constant drag) | `runs/point/04_cspace_ideal_airbrake_dc.py` | Open-loop Cd×Area brake sizing against the target apogee, 4 ideal dc variants. |
| 1.5 | Cspace comparison (Mach-dependent drag) | `runs/point/05_cspace_comparison_dc_dm.py` | Same comparison, dc+dm rockets merged into one 7-row table. |
| 1.6 | Cspace ideal mass (Mach-dependent drag) | `runs/point/06_cspace_ideal_mass_dm.py` | Same as 1.2, for the 3 dm rockets. |
| 1.7 | Cspace ideal drag (Mach-dependent drag) | `runs/point/07_cspace_ideal_drag_dm.py` | Same as 1.3, for dm. |
| 1.8 | Cspace ideal airbrake sizing (Mach-dependent drag) | `runs/point/08_cspace_ideal_airbrake_dm.py` | Same as 1.4, for the 4 ideal dm variants. |
| 1.9 | Euroc motor sweep, fx27-parity columns | `runs/point/09_euroc_comparison_fx27_columns.py` | 24 (config, motor) combos, fx27's own simpler flight-column set. |
| 1.10 | Euroc motor sweep, feasibility view | `runs/point/10_euroc_sweep_feasibility.py` | Same 24 combos, richer columns (`J_total`, `t_burn`, `T/W`, `q_max`, `m_burnout`) for picking a motor per airframe. |
| 1.11 | Euroc motor sweep (Mach-dependent drag) | — not built | Deferred — the sibling repo has no euroc "dm" source to port from (see Notes). |
| 1.12 | Final cross-campaign comparison | `runs/point/12_final_cross_campaign_comparison.py` | Wrap-up comparison once configurations were chosen across cspace + euroc, dc + dm. |

### Notes

- **1.11 was never built.** Not a gap in this doc — a real gap in the project. The sibling repo this project ports from has no euroc Mach-dependent-drag data to port.
- **"Airbrake sizing" is not a separate id.** It's the same artifact as 1.4/1.8 (`04_cspace_ideal_airbrake_dc.py`/`08_cspace_ideal_airbrake_dm.py`, split out of the former `ideal_open_airbrake.py` per architecture-46) — cspace-only, dc+dm, never touched euroc. No distinct later version of it exists.
- **1.10 (`sweep.py`) is the "choosing a configuration" step**, not 1.9 — it's the richer, feasibility-metric view (`apps/optimization/motor_selection`) that's actually useful for picking a motor; 1.9 just replicates fx27's own simpler column set for a side-by-side check.

## Controller

| id | name | current file | description |
|----|------|---|---|
| 1.1 | P, analytical burnout predictor, linear drag `C(f)` | `solvers/controller_pd/controller.py`, `runs/controller_pd/01_p_analytical_burnout_linear_drag.py` (Step 152, moved to its own `controller_pd/` package Step 156) | Baseline. Closed-form burnout predictor, `proportional_drag` law, ρ fixed at sea-level (1.225), drag linear in brake fraction `f` only, no Mach term, ideal actuator, noiseless `stub` estimator. |
| 1.2 | PD, same predictor | `apps/control/flight_software/laws.py` (`pd_apogee`, Step 153) — law built, not yet wired to an fx27 `runs/controller_pd/` script | Same predictor/plant/estimator as 1.1, swap `proportional_drag` for `pd_apogee`. |
| 1.3 | ρ at altitude + decomposed Mach drag | — not built; needs the `h → ρ` helper (task-107 §107.3.3/3.4) and `Cd,r(M)`/`Cd,a(M,f)` data | ρ evaluated at the current estimated altitude (not sea-level) and `Cd = Cd,r(M) + Cd,a(M,f)` (rocket's own Mach-dependent drag plus the airbrake's own Mach-and-`f`-dependent increment, additive) — both frozen at the current tick, still closed-form. |
| 1.4 | ρ at altitude + combined `Cd(M,f)` table | — not built | Same frozen-at-current-tick pattern as 1.3, but `Cd(M,f)` is one combined lookup table instead of an additive split — can capture body/brake interaction 1.3 can't. Reuses General 0.1's drag-theory tables. |
| 1.5 | Point-mass **numeric** predictor | — not built | Predictor stops being a single algebraic evaluation and numerically integrates the 1D coast ODE — live, non-frozen `ρ(h)`/`Cd(f,M)` at every step, the same functions the truth sim uses. No more freezing. |
| 1.6 | Full (rate-limited) actuator | `apps/sim/engine` actuator model (Step 103, built); not wired into any fx27 closed-loop script yet | Replaces the ideal/instantaneous actuator — both the plant's own brake-extension dynamics and the signal the controller commands through. |
| 1.7 | Noisy sensors + real Kalman filter | `apps/control/flight_software/estimator.py` — only `stub`/`alpha_beta` exist | Replaces the noiseless/single-sensor estimator with a genuine multi-sensor KF feeding noisy sensor data. Open prerequisite: a real KF doesn't exist in this codebase yet; pending Step 147's tuning output. |
| 1.8 | 2D as plant (predictor still point-mass) | — not built | Truth plant upgraded to the engine's existing 2D rigid-body model (`apps/sim/engine/dynamics.py`, `C_z`/`C_m`/`c_mq` turned back on, Step 6). Predictor keeps consuming only `h`/`v` extracted from the richer state — isolates predictor robustness to plant-model mismatch. |
| 1.9 | 2D as predictor too | — not built; depends on 1.8 | Predictor also rolls forward the 2D attitude-aware dynamics, closing the mismatch 1.8 opened on purpose. |
| 2.1 | Tier 2 (switching-curve / bounding-trajectory blend) | — not built, not yet scoped | Standalone control-law architecture, not a fidelity increment — predicts apogee at both brake extremes and interpolates. Inherits whichever predictor/actuator/estimator stage 1 settled on; does not redo the fidelity ladder. |
| 3.1 | Tier 3 (MPC) | — not built, speculative | Receding-horizon optimization each tick — architecturally distinct controller type, not an increment on 1.x/2.1. Also inherits stage 1's matured predictor/plant/estimator. |
| 4.1 | Fixed bench: disturbances + Monte Carlo dispersion | `apps/analysis/ensemble` (MC machinery exists); wind/turbulence disturbance model on the plant not built | Final validation campaign: every built version (1.x/2.1/3.1) evaluated under disturbances across repeated draws, not a single nominal run. |

**5.1 (flagged, not committed):** 3D re-tune pass once a design is chosen from the 4.1 comparison —
expected to be a re-tune of gains, not a redesign. Scope TBD when reached.

### Notes

- **Stage 1 is one continuous P/PD track** — each row adds exactly one new piece of realism (law, drag
  model, ρ, numeric integration, actuator, estimator, plant dimensionality), deliberately sequential.
- **2.1/3.1 inherit stage 1's matured predictor/actuator/estimator** — only the control-law architecture
  changes; they are not required to re-derive predictor fidelity themselves.
- **1.8/1.9 split 2D on purpose** (plant-only, then predictor-too) to get plant-model-mismatch robustness
  as its own data point, not just a fidelity-matched jump.
- **"2D" is the engine's own pre-existing 2D rigid-body model** (`dynamics.py`, Step 6) — independent of
  (not derived from) the separately-built 3D model (`dynamics3d.py`, Step 29/30). The two are kept
  consistent via a regression check (planar 3D initial conditions reproduce the 2D trajectory bit-for-bit),
  not by projecting one onto the other at runtime.
- Static open-loop airbrake sizing (General 1.4/1.8, `ideal_open_airbrake.py`) is **not** part of this
  table — a design-time sizing tool, not a closed-loop controller version.
