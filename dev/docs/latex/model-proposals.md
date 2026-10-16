# Model proposals — what is missing per model

Review of `sections-ai/models.tex` (+ `rocket-2d.tex`, `backlog.tex`, `assumptions.tex`, `sim/`), 2026-10-16.
Scope: hobby/student 2D rocket, subsonic–transonic, apogee 1–10 km, rail launch, single/dual recovery.
Format: name — what · why/effect size · effort S/M/L · in backlog? ★ = top priority within the model.
Effect sizes are order-of-magnitude estimates for a ~75 mm, J–L-class rocket unless stated.
Items that already exist only as a `\todo` in `models.tex` (not in backlog/assumptions) are marked "todo".

## Gravity

- ★ **Constant model at the site value** — default `g = g(φ0, h0)` from Somigliana instead of `g0 = 9.80665` · `g0` corresponds to ~45° latitude; equator/pole differ by −0.27%/+0.26%, i.e. ±0.3% of coast height (~±10 m at 3 km); zero cost, removes a silent latitude bias · S · no.
- ★ **End-to-end vacuum verification** — drag/thrust off, check apogee/time-of-flight against `v²/2g` and the inverse-square energy integral `½v² = μ(1/R − 1/(R+h))` · catches sign/frame errors in the direction models that unit tests of `g(h)` alone do not · S · no.
- **Close the third-order ellipsoid-normal `\todo` as negligible** — the omitted term is `O(ϑ³)`, `ϑ = x/R_χ ≈ 1.6e-3` at 10 km downrange → ~1e-9 rad · state it and drop the todo · S · todo.
- **Honest negligibles (state once, do not implement)** — J2 is already inside normal (Somigliana) gravity; higher harmonics/local anomalies (≤ 50 mGal ≈ 5e-5 relative) and deflection of the vertical (~10″) are below any input uncertainty; the vector-field gravity `\todo` has no use case at these altitudes · S (doc only) · no.

## Thrust

- ★ **Motor-to-motor impulse scatter** — scale factor `T(t) = k_J T0(t)` (or `k_J` on impulse with `k_t` on burn time) as a dispersion input · total impulse of certified hobby motors scatters by a few % (±3–5%); apogee sensitivity ≈ 1–1.5× that, i.e. the single largest apogee uncertainty after `C_x` · S · no.
- ★ **Grain-temperature sensitivity** — impulse-preserving time scaling `T(t) = κ T0(κt)`, `κ = exp(π_K ΔT_grain)`, `π_K ≈ 0.1–0.3 %/K` · ±20 K from test temperature → ±2–6% peak thrust and burn time; small apogee change (~≤1%, impulse conserved) but directly moves rail-exit speed and max-q · S · no.
- **Populate `A_e` from the motor data** — the pressure term `A_e(p0 − p_atm)` exists but defaults to 0 · for a 38–54 mm nozzle and burnout below ~3 km it is ≤1% of thrust; above that it grows to a few %; free accuracy once nozzle exit diameter is entered (and resolves the `T` vs `T0` mass-flow `\todo`) · S · todo (default value only).
- **Impulse-preserving thrust-curve handling** — check `∫lerp(T)dt` equals the file's stated impulse; pass curve breakpoints to the integrator as stop times · sparse `.eng`-style curves under/over-state impulse by ~1% with naive interpolation; RK45 stepping over ignition/burnout kinks costs accuracy and steps · S · no.
- **Honest negligibles** — nozzle flow separation (over-expansion) never occurs at hobby `p_e`; thrust-vector jitter is covered by constant `θ_t` as a dispersion · — · no.

## Mass, centre of gravity and moment of inertia

- ★ **Jet damping, quantified and switched in** — `M_jd = −ṁ (l_t − l_g)² ω_r` · estimate for ṁ ≈ 0.25 kg/s, arm ≈ 0.8 m: ~0.16 N·m·s vs fin damping `½ρvS C_Nα,f l_f² ≈ 1.3 N·m·s` at 100 m/s → ~10% at 100 m/s and comparable at rail-exit speed (20–30 m/s), exactly when wind-induced pitch-up happens; do not add a naive `ω dI/dt` term — in the consistent variable-mass derivation it is largely cancelled by the internal-flow term · S · todo (this gives the estimate the todo asks for).
- ★ **Mass-property input uncertainty** — dry mass ±2–5%, dry CG ±1–2 cm, `I_r,g` ±10–20% as dispersion inputs · CG error moves static margin by ~0.1–0.3 cal, the main stability uncertainty of a home-built airframe · S (given the cross-cutting MC framework) · no.
- **Measured-inertia path** — accept `I_r,g` from a bifilar/trifilar pendulum measurement (period → inertia) as a config option · hand estimates of `I` are routinely off by 20–50%; inertia sets the short-period frequency and weathercock response · S · no (backlog has component build-up, not measurement).
- **Honest negligibles** — propellant slosh: none (solid grain); hybrid/liquid only. Mass shed at separation (nose cone/shoulders) is irrelevant to the trajectory under canopy except through the total drag area · — · no.

## Aerodynamics

- ★ **Store the centre of pressure from the nose, not the arm** — table/config gives `X_cp(M, α)` from point A; the code forms `l_p − l_g(t)` with the live `l_g(t)` · CG travels aft by several cm during a burn, so static margin changes by ~0.3–1 cal over the burn; with a fixed arm (`l1_m`) this is invisible · S–M (table column semantics change) · assumptions: yes ("arm does not respond to CG travel"); new: the concrete fix.
- ★ **Power-on vs power-off base drag** — `C_x,on = C_x,off − C_base(1 − A_e/A_base)` while thrusting · base drag is ~25–40% of subsonic `C_x` of a hobby rocket; burn phase is where `q` is highest; ±1–3% apogee · S (flag + one coefficient) · no.
- **Drag-vs-Mach curve as a 1D tier** — `C_x(M)` table between Constant and the full `(M, α)` table, the format OpenRocket/RASAero export · dominant above M ≈ 0.8: drag roughly doubles through M 0.9–1.1; a constant `C_x` over-predicts transonic apogee by 10%+ · S · todo (no M slope) + backlog Mach correction; new: the cheap tier.
- **Surface-finish / Reynolds correction on friction drag** — `C_f(Re, k_s)` (turbulent flat plate + roughness) scaling the friction part of `C_x` · friction is ~40–60% of subsonic drag; paint quality alone changes total `C_x` by 10–20%; `Re` varies ~10× over the flight · M · todo (Re axis); new: a scaling instead of a third table axis.
- **Nonlinear normal force at large α** — body crossflow term `C_N = C_Nα α + η C_dc (S_plan/S) sin²α` · matters off the rail in strong wind (α 10–20° at low speed) and in any tumble; linear models under-predict restoring force · M · no (backlog Barrowman is linear).
- **Fin-flutter check (post-processing)** — NACA TN-4197 flutter speed vs `v(h)` along the trajectory · transonic hobby rockets lose fins this way; a pure output, no dynamics change · S · no.

## Atmosphere

- ★ **ISA with launch-day offsets** — `T = T_ISA(H) + ΔT`, surface pressure `p_s` anchoring at `h0` · a +15 K hot day is −5% density → +2–4% apogee and lower max-q; currently ISA is the only tier without measured data and has no offset · S · no.
- ★ **Blend a surface observation into the sounding** — replace/merge the lowest levels with a site METAR or handheld (T, p, Td) measurement, relaxing to the sounding over the boundary layer · 00/12 UTC soundings miss afternoon heating of the lowest 1–2 km, where `q` peaks · S–M · no.
- **Atmosphere verification against US Std Atm 1976 tables** — spot values (ρ, a, μ) at 0, 5, 11, 20 km to 1e-5 relative, if not already pinned · guards the layer table and geopotential conversion · S · no.
- **Honest negligibles** — moist `a`/`μ` (doc already argues ~0.2%); virtual-temperature hydrostatics within a layer; diurnal pressure tide (~1 hPa) · — · no.

## Wind

- ★ **Passive cross-plane drift state ("2.5D")** — integrate `y` with `dy/dt = w_y` under canopy (a canopy follows the air horizontally) and a point-mass drag `y`-equation in free flight · the landing point is otherwise wrong whenever wind is not along `χ`; drift under a main from 300 m in 5 m/s wind is ~300 m, from apogee under a single chute km-scale · S–M · backlog has 6DOF out-of-plane; new: kinematic drift without 6DOF.
- ★ **Wind input uncertainty** — speed ±(20–30)% and direction ±(15–30)° of forecast/sounding as dispersion inputs · drives landing-ellipse size and weathercocking more than any other input · S (with the MC framework) · no.
- **Pad anemometer input** — mean + gust at 2–10 m mapped to `W_ref` and Dryden `σ_u` (gust factor) · what a student team actually measures on the day; avoids guessing `σ_high` · S · no.
- **Discrete gust at rail exit** — `1 − cos` gust case · already a todo; the relevant design case is a gust timed to rail exit (lowest airspeed, largest `w/v`) · S · todo.

## Relative wind and angle of attack

- ★ **Rail-exit stability metric** — report `α_exit = atan(w_x/v_exit)` and `v_exit/w`, flag the usual rules (v_exit ≥ 15 m/s, α_exit ≲ 10–15°) · the quantity that decides weathercocking; the doc names it but nothing reports it · S · no.
- **Envelope-exceedance diagnostics** — count time where `|α|` or `M` is outside the table grid (clamped in M) · silent clamping hides extrapolation, e.g. transonic flight on a subsonic-only table · S · no.
- **State that `C_m,α̇` is lumped into `C_m,q`** — downwash lag at the fins adds ~10–30% to measured pitch damping; one sentence prevents double counting when a CFD `C_m,q` (q only) is entered · S (doc) · no.

## Non-inertial frame corrections (Earth's rotation)

- ★ **Analytic Coriolis verification** — vacuum vertical shot at the equator, `χ = 90°`: westward landing offset `Δx = −(4/3) Ω cos φ0 v0³/g²` · one test pins the sign and the factor 2 of the in-plane term · S · no.
- **Say plainly it is negligible for apogee** — ~10 m downrange at most, ≪ wind dispersion (hundreds of m); keep it off by default and out of MC runs · S (doc) · no.
- **Lateral Coriolis as passive drift** — the dropped `ŷ0` term can feed the passive `y` state proposed under Wind at no extra modelling cost · same order as the in-plane term, still ≪ wind drift · S · backlog: yes (6DOF); new: passive route.

## States, initial conditions and integration

- ★ **Default `t_max = 300 s` truncates descents** — 10 km under a drogue at ~25 m/s takes ~400 s, under a main at ~5 m/s ~30 min; derive `t_max` from the scenario or raise it, and report "ended by t_max" as a warning instead of a silent stop · S · no.
- ★ **Segmented integration with latched phases** — stop/restart the solver at rail exit, burnout, deployment and air-brake arming; latch each mode after its event · removes in-step discontinuities, fixes the non-latched apogee predicate (pre-apogee `v_z` transient arming the chute) and the RK45/RK4 event-placement asymmetry · M · no (the caveat is recorded, the fix is not).
- **Convergence study** — already a todo; add the acceptance criterion: apogee and landing point converged to < 0.1 m between `h` and `h/2` / tol and tol/10 · S · todo.
- **Initial CG height above the pad** — start at `z0 = −(L_rocket − l_g)·sinθ_rail` (CG above the rail base), impact at the CG or the lowest point · ~1 m, negligible for apogee; state it · S · no.

## Launch rail

- ★ **Effective rail travel** — the rocket is guided until the *aft* button leaves; usable travel is `L_rail − (offset of aft button from rail start)`, often 10–30% shorter than the rail · rail-exit speed ∝ `√s`, so 5–15% lower `v_exit` and larger `α_exit` · S · no.
- **Pad hold-down (no backward slide)** — already a todo; matters for T/W < ~3 motors with slow ignition ramps · S · todo.
- **Rail angle and azimuth as dispersion inputs** — ±1–2° elevation, ±5° azimuth (alignment of a field rail) · ~1% apogee, tens of m landing point · S (MC) · no.

## Recovery

- ★ **Airframe drag under canopy** — replace the body-axis `C_x, C_z` at the frozen attitude with a tumbling/broadside drag area `C_D,body S_side` along `v̂_rel` (or switch body aero off) · body-axis coefficients at an arbitrary frozen θ are meaningless; the airframe adds ~5–20% of drag area under a small drogue · S · no.
- ★ **Motor-ejection deployment trigger** — `t_dep = t_burnout + t_delay` with delay scatter (±1–2 s) · the most common hobby deployment; a timer from ignition ignores burn-time variation; deployment speed at ejection is the opening-load driver · S · todo (altitude trigger only); new: delay trigger.
- **Recovery outputs** — descent rate per stage, landing kinetic energy per tethered section (common club limit ~100 J), deployment `q` and `v` · direct pass/fail numbers for a recovery design review · S · no.
- **Opening shock / reefing / pendulum** — already in backlog (refined recovery); no new content · — · yes.

## Air brake

- ★ **Drag-aware apogee predictor** — `ĥ_a = h + (m/2k) ln(1 + k v_z²/(m g))`, `k = ½ρ(C_x S + C_D,b S_b f_b)` (vertical ballistic coast closed form) · `h + v_z²/2g` over-predicts by hundreds of metres at burnout of a 3 km flight, so the P law brakes far too early and saturates; still memoryless · S · no.
- **Brake drag coefficient vs Mach and shielding** — `C_D,b(M)` and a body boundary-layer/shielding factor (~0.6–1.0) · flaps opened near M 0.7–0.9 see strong compressibility; sizing studies with constant `C_D,b` mis-size `S_b` · S · no.
- **Asymmetric deployment** — a fraction of `F_b` acting off-axis as a pitch moment dispersion · one jammed flap is the classic failure; size depends on mounting radius · M · assumptions: yes (axial only); new: off-nominal case.
- **Retraction and rate limit** — already in backlog · — · yes.

## Sampled-data evaluation (zero-order hold)

- ★ **Sensor model channels** — barometric altitude with noise, quantisation and lag, IMU acceleration with bias; controller reads sensor channels, not the true state · real air-brake loops are limited by baro noise and transonic static-pressure errors; a controller tuned on truth over-performs · M · backlog: partly (gimbal "waiting on a sensor model"); new: for the air brake, on the existing ZOH seam.
- ★ **Compute/actuation latency** — option to apply `c_k` at `t_{k+1}` (one-tick delay) and a first-order actuator lag · at 10–50 Hz a one-tick delay changes P-loop stability margins noticeably · S · no.
- **Adaptive integration between ticks** — restart RK45 on each `[t_k, t_{k+1})` segment instead of requiring fixed-step RK4 · removes the cost penalty the doc cites; same ZOH semantics · M · no.
- **Honest negligible** — tick jitter of a flight computer (< 1 ms) has no visible trajectory effect · — · no.

## Cross-cutting

- ★ **Monte-Carlo dispersion framework** — sample the inputs flagged above (impulse, grain temperature, `C_x` ±10–15%, mass/CG/I, rail angle/azimuth, wind speed/direction, ΔT, deployment delay) through `sim.params.replace`, fixed seeds, output apogee percentiles and a landing ellipse · every app today is one deterministic trajectory (`compare_motors.py` says so); dispersion, not model fidelity, is what a hobby flight review needs · M · no.
- ★ **Validation against OpenRocket/RASAero and flight logs** — same airframe/motor in OpenRocket (and RASAero for M > 0.8), compare apogee, max v, time to apogee; then altimeter data from a real flight · the only check of the whole chain; typical tool-to-flight scatter is ±5–10% apogee, so agreement within that is the target · M · no.
- **Analytic regression suite** — vacuum parabola, drag-only vertical coast closed form, chute terminal velocity `√(2mg/ρC_DS)`, power/energy budget `ΔE = ∫(T + A_f)·v dt` · each pins one model end-to-end, independent of numerical pins · S · no.
- **One-at-a-time sensitivity table** — `∂(apogee, landing x, v_exit)/∂input` by finite differences around the nominal · ranks inputs before an MC run and before spending on CFD · S · no.
- **Convention/symmetry property tests** — mirroring (`χ → χ+180°`, wind sign, `θ_t → −θ_t`, `r_g → −r_g`) must mirror `x` and `θ_r`; unit checks on every config field · cheap guard for the sign convention the project relies on · S · no.
- **Run diagnostics** — one warnings list per run: `t_max` reached, table envelope exceeded, static margin < 1 cal at any time, `v_exit` low, chute deployed while ascending · turns silent failure modes into visible ones · S · no.

