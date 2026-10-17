# Code vs paper sweep

Sweep date 2026-10-17. Code: `D:/YandexDisk/Projects/Rocket-physics` @ `feature/motor-config-separation` (305bb66).
Paper: `.worktrees/latex-notes/dev/docs/latex/sections-ai/*.tex` (models.tex ~1150 lines; the file was being edited during
the sweep, so paper line numbers are approximate +-40; code line numbers are exact for 305bb66).

Branch note: `develop..feature/motor-config-separation` holds the whole of Phase 2.16 (Steps 76-96, D-56..D-103), including
Step 93 (axial drag sign fix, `aero.axial_flow_factor`, D-91..D-94a), Step 94 (chute pad guard, D-94b), Step 92 (Mach > 0.8
warning), the motor/config separation (Steps 71-91) and the one-demo configs. `develop` has none of these. The paper
describes the feature-branch code; against `develop` the paper's `\todo` on the axial term would still be open.

Abbreviations: C = `sim/`, P = paper section label.

## In code, not in paper

- **Axial flow-direction factor** `f = clip(cos(alpha)/cos(85 deg), -1, 1)` multiplies `C_x` (exactly 1 for |alpha| <= 85 deg) ·
  `aero.axial_flow_factor`, `_constant_coeffs`, `_linearized_coeffs`, `_table_coeffs` · P `sec:aero` "Axial force and the flow
  direction" · the paper only has a \todo asking for it (D-91/D-92).
- **Table exemption from the factor** (D-93): `C_A` is multiplied only if the table's alpha grid lies strictly inside (-90, 90) deg;
  a table covering reversed flow is used as is · `aero._table_axial_factor` · P `sec:aero_coeffs` Table · not written.
- **Same factor on the air-brake force** (D-94a): `A_brake *= axial_flow_factor(alpha)` · `forces.aero_force_body` L226 ·
  P `sec:airbrake` ("acts along x_r whatever the pitch") · the brake changes sign tail-first.
- **0.1 s pad guard on the chute apogee trigger** (D-94b; a rest start with T(0) < mg sags tail-first, v_z > 0) ·
  `forces.parachute_deployed` L297 · P `sec:recovery` Deployment ("apogee, taken as v_z > 0") · paper silent on the guard.
  The air-brake `after_apogee` trigger has no such guard (`control._trigger_after_apogee` L161) - code asymmetry.
- **Mach warning**: one `MachRangeWarning` if peak M > 0.8 under `aero.model` in {constant, linearized}; table exempt; diagnostic
  only · `mach_warning.warn_if_mach_blind`, called from `integrate.run_sim` / `_warn_if_mach_blind` · P `sec:aero_coeffs`
  (Constant/Linearized) or `sec:states` · not mentioned anywhere.
- **Lateral Coriolis diagnostic** `-2(Omega_z v_x - Omega_x v_z)`, never fed to the state · `rotation.coriolis_lateral_diagnostic` ·
  P `sec:noninertial` · paper says the term is "discarded"; the code exposes it for due-N/S launches.
- **ISA altitude clamp** h_msl in [-5000, 86000] m before the lapse formula (B13; keeps `solve_ivp` trial states from NaN) ·
  `atmosphere._isa_air_state` L105 · P `sec:atmos_tiers` ISA · last layer otherwise unbounded above 71 km; not stated.
- **Humid air: Td clamped to <= T** (anti-supersaturation) · `atmosphere.virtual_temperature` · P `sec:density` · not stated.
- **Sounding tier uses only the first file of a case** (extra stations silently ignored) · `atmosphere._sounding_air_state`,
  `wind._sounding_wind` (`load_case(...)[0]`) · P `sec:atmos_tiers` tier 2 · one line.
- **Field tier pre-resamples every station onto a common MSL grid** 0..`grid_top_m` (30 km) step `grid_step_m` (100 m) before
  weighting; the combined profile is then linearly interpolated, ISA-anchored above 30 km · `soundings._resample_case`,
  `Soundings.grid_top_m/grid_step_m` · P "Field" paragraph · paper presents it as exact IDW of the station profiles.
- **Sounding file format** (`data/soundings/<case>/<station>_<YYYYMMDDHHMM>.csv`, `#key: value` metadata, `h_msl_m` strictly
  increasing, blank = NaN, optional `Td_K`, wind (wdir, wspd) -> (u, v) at load) · `soundings._load_sounding_file` ·
  P `sec:atmosphere` · paper documents the aero-table format but not this one.
- **Motor file formats**: `.csv`, RASP `.eng/.rasp`, `"<file>#<designation>"` picker, header metadata (m_prop, m_total,
  diameter, length), and an explicit `(0,0)` point prepended to a RASP record whose first row has t > 0 (D-64) ·
  `motor_file.load`, `thrust_curve._load_motor_curve` · P `sec:thrust` Magnitude ("from a motor file") · not described.
- **Mass assembly defaults** (D-67/SS32.3): casing/propellant centroid default to length/2, inertias default to a uniform
  cylinder `m(3r^2+L^2)/12`, motor placed by `l_motor_fwd` or `l_motor_aft - length`, endpoint inversion of (l_0,l_f,I_0,I_f)
  into the lump · `configs/schema._weight_from_pieces`, `mass.uniform_cylinder_I`, `mass.combine` · P `sec:mass_inertia` "In the
  code" · only the result (two-lump) is described, not the defaults or the inversion formula.
- **`Weight.I_p_spec`** (propellant specific MOI; `None` falls back to the borrowed `I_d/m_d`) · `mass.moment_of_inertia` ·
  P `sec:mass_inertia` · paper says only "I_prop proportional to remaining propellant mass".
- **Propellant mass clamped at 0 for CoG/inertia only**; `y[M]` itself is never clamped at `m_d`, and `dm/dt` is the unclamped
  `-T/(I_sp g0)` · `mass.propellant_mass` L60, `dynamics.derivatives` L239 · P `sec:mass_mass` ("m_m >= m_f").
- **Initial mass seeding** (D-76): with the mass model on and `s0.m == 0`, `assemble` sets `s0.m = weight.m` · `schema.assemble`
  L366 · P `sec:states` Initial conditions (states `m(0)=m_launch`, not the rule).
- **Separate Reynolds length** `Aero.l_ref` (not `d_ref`) · `flow.flow_state` L96 · P `sec:reynolds_mach` (uses c).
- **Event guards**: the 0.1 s guard also applies to the rail-exit event; RK4 applies `t_next >= 0.1` to apogee, ground and
  rail exit · `integrate._rail_exit_event` L185, `_run_rk4` L348/361/384 · P `sec:states` Events (mentions the guard for
  ground impact and apogee only).
- **RK4 `raw.sol`** is a piecewise-linear interpolant (`_LinearInterpolant`), so RK4 results sampled between steps are only
  O(dt) · `integrate._LinearInterpolant` · P `sec:states` Integrators · reporting accuracy, not stated.
- **Dryden details**: 64 sinusoids per component, geomspace grid 600 s..0.2 s, draw order phases_u then phases_v from
  `default_rng(seed)`, cached per seed; weights recomputed per call (altitude dependent) · `wind._turbulence_realization`,
  `_dryden_turbulence` · P `sec:atmos_noise` Turbulence · only the period range is stated.
- **Proportional air-brake predictor** uses the curved-ground altitude `gravity.altitude_agl` and the local `g(t,y,p)`, not
  `h` and `g_0` · `control._proportional_airbrake` L126 · P `eq:airbrake_p` · negligible, but differs for curved gravity.
- **WGS84 `g` uses MSL altitude (includes `h0_m`), radial `g` uses AGL** · `gravity._g_wgs84` L119 vs `_g_radial` L79 ·
  P `sec:gravity` · the paper's new todo already covers the radial half.
- **3D scaffold**: 13-state `[r, v, q, omega]`, quaternion algebra, translation-only EOM with attitude held constant, force
  wrappers reusing the 2D forces · `dynamics3d.derivatives_3d`, `state3d`, `quaternion`, `forces3d` · P `sec:introduction`,
  `sec:backlog` (out-of-plane item) · paper treats 3D as future; a one-paragraph status note would fit the backlog.
- **Aero control seam** `control.aero_coeff_delta` (identity) - already described in the \todo at the end of `sec:aero_coeffs`.
- **Flight summary / sweeps** (`report.flight_summary`: max-Q on a 2000-point grid, apogee altitude on curved ground) are
  outputs, not physics; the apps (`apps/*`) are listed in the introduction only.

## Paper \todo audit

33 `\todo` calls (28 models.tex, 1 analysis.tex, 4 template.tex; the two hits in main.tex are the macro definition and a comment).
`\simtodo`/`\restodo` macros exist in main.tex/introduction.tex but no todo has been converted yet. Lines = models.tex unless
stated, as of the sweep (file is moving). Classes: SIM = paper describes, code lacks; RESEARCH = needs research/decision;
DOC = code has it, paper incomplete; RESOLVED = stale.

| line | gist | class | evidence / note |
|---|---|---|---|
| 41 | radial g uses R_e + h_AGL, not R_0 + height | SIM | `gravity._g_radial` L79-80 (`p.gravity.R_e + altitude_agl`); no h_0/h_g0 |
| 79 | ellipsoid normal differs at 3rd order in theta | DOC | `gravity._R_chi`, `_dir_curved` freeze R_chi; accuracy note only |
| 91 | no vector-field gravity model | SIM | `gravity._GRAVITY_MODELS` = constant/radial/wgs84 only |
| 145 | names of p_0, A_e in sim/ | RESOLVED | now in appendix.tex notation (`p.thrust.p_ref`, `A_e`) |
| 211 | mass flow uses pressure-corrected T, not T_0 | RESEARCH | `dynamics.derivatives` L239 `thrust_curve.thrust`; decision |
| 220 | linear mass model not implemented | SIM | `Motor.mass_model` in {none, isp, endpoints}; no Delta-t model |
| 267 | radial offsets r_g(t) constant, no radial term | SIM | `mass.cog_position` axial; `dynamics` L302-303 use constant `u_B`, `u_C` |
| 277 | dI/dt and jet-damping terms neglected | RESEARCH | `dynamics` L356 `M_y / I`; needs magnitude estimate |
| 287 | linear l_g,m / I_m,g differ from two-lump | SIM | `mass.moment_of_inertia`, `schema._weight_from_pieces` (endpoint inversion) |
| 305 | mass/inertia change by mechanisms | RESEARCH | nothing in sim/ |
| 307 | dry-rocket inputs from components | RESEARCH | `Airframe.m/l/I` typed by hand (`schema.Airframe`) |
| 329 | single aero component only | SIM | `aero.coefficients` returns one bundle; one `Aero.S/d_ref` |
| 340 | axial term assumes nose-first flight | RESOLVED | `aero.axial_flow_factor` L98; `forces.aero_force_body` L226 (Step 93); paper must state factor |
| 364 | only alpha slope; table is (M, alpha); no Re | SIM | `aero._linearized_coeffs`, `_load_table`; `flow.Re` computed, unused |
| 411 | table has no Re axis | SIM | `aero._load_table` needs `alpha_deg, M, ...` only |
| 428 | CFD pipeline; control-surface entry point | RESEARCH | seam exists: `control.aero_coeff_delta` (identity) - paper already says so |
| 460 | adopt drag polar? | RESEARCH | no polar in `aero.py` |
| 478 | no interpolation in time between soundings | SIM | `soundings.interp_field_at(case, E, N, h, p)` has no t |
| 486 | no discrete-gust model | SIM | `wind._TURBULENCE_MODELS` = none, dryden |
| 631 | wind: no time interpolation between soundings | SIM | same as 478 |
| 688 | thrust noise not implemented | RESEARCH | nothing in sim/; needs test-stand data |
| 939 | mass flow uses T not T_0 (duplicate of 211) | RESEARCH | `dynamics.derivatives` L239 |
| 977 | integrator cost/accuracy study | RESEARCH | both integrators exist (`integrate.run_sim`, `_run_rk4`); study not done |
| 999 | apogee = v_z crossing, not max h_true | RESEARCH | `integrate._apogee_event` docstring L106-121 confirms |
| 1036 | no pad contact; rocket can slide down the rail | RESEARCH | `dynamics.derivatives` L334-339 no clamp; changes low-T/W results |
| 1055 | omega keeps its value under canopy | RESEARCH | `dynamics` L350-351 zeroes only d(theta), d(omega) |
| 1067 | no altitude/q chute trigger, no drogue+main | SIM | `Recovery.trigger` in {apogee, timer} |
| 1096 | canopy transient, shock, reefing, pendulum, added mass | RESEARCH | not modelled |
| analysis:178 | needs a value/model for C_m,q | RESEARCH | `aero.AeroCoeffs.C_mq` is wired; only the number is missing |
| template:167 | mass change due to mechanisms | RESEARCH | duplicate of models:305 |
| template:187 | geometry / control-surface dependence | RESEARCH | duplicate of models:428 |
| template:188 | pitch rate in coefficients | RESOLVED | `C_mq` in all three models: `forces.aero_moment_y` L269; paper pitch-damping paragraph |
| template:196 | what about c_d (drag polar) | RESEARCH | duplicate of models:460 |

Counts: SIM 12, RESEARCH 17, DOC 1, RESOLVED 3 (total 33). template.tex is not `\input` by main.tex (legacy skeleton).

## Discrepancies

1. **Tail-first axial force (paper describes the pre-Step-93 behaviour as current).** Paper `sec:aero` "Axial force and the flow
   direction" (~L336-342): C_x > 0 always points aft, "flying tail-first ... it would accelerate the rocket"; also
   `eq:aero_magnitudes`, `eq:analytic_force_x`, `eq:aero_linearized` use `-qS C_x x_r` unconditionally. Code: `C_x` is multiplied by
   `axial_flow_factor(alpha)` in all three models (`aero.py` L98-105, L263, L313, L355) and in the brake (`forces.py` L226);
   it equals the paper only for |alpha| <= 85 deg. Present on `feature/...`, absent on `develop`.
2. **Coriolis dropped under canopy.** Code `dynamics.py` L348 `a_chute = (F_i + F_chute)/m` discards the Coriolis term that L250-251
   added to `a_i`, although the comment L341-346 says it is "included exactly once". Paper: `eq:chute_eom` has no Coriolis, but
   `sec:noninertial` says the term enters the translational equation, and the rail equation (`eq:rail_constraint`) does include it.
   Code bug against its own docstring (only with `gravity.earth_rotation=True` and a deployed chute); the paper matches the bug.
3. **Field tier is not exactly the sounding tier.** Paper "Field" (~L554): a single station "reproduces the sounding tier
   exactly". Code resamples each station onto a 0..30 km, 100 m MSL grid first (`soundings._resample_case` L406-444,
   `interp_field_at` L547-554) and linearly interpolates that grid, so agreement is to grid-linearisation error only
   (kinks between nodes; levels above 30 km re-extrapolated from the grid edge).
4. **Reynolds reference length.** Paper `sec:reynolds_mach` (~L616) `Re = rho v_rel c / mu`, c = body diameter = `d_ref`. Code
   `flow.py` L96 uses `p.aero.l_ref`, a separate field (default 0.0). Re is unused by every model, so no numeric effect.
5. **Mass floor.** Paper `eq:mass_motor` (~L189) `m_m >= m_f`, "integrated until m_m reaches m_f". Code integrates
   `dm/dt = -T/(I_sp g0)` (`dynamics.py` L239) with no clamp on `y[M]`; only the propellant part is clamped for CoG/inertia
   (`mass.propellant_mass` L60). Exact with `mass_model="endpoints"`; a hand-typed inconsistent `I_sp` can burn below `m_d`.
6. **Example aero table sign.** Paper Conventions: stable needs `C_m,alpha > 0` (positive C_m pitches nose down, `A_m = -qSc C_m`).
   `data/aero/example.csv` has `C_m = -0.0873` at alpha = +10 deg (header comment: "restoring (negative-slope)") - the textbook
   sign, destabilising in this code (backlog B31 already open for it).
7. **Thrust-angle sign.** Paper: `x_t = cos(theta_t) x_r - sin(theta_t) z_r`, `theta_t = -radians(misalign_deg)` (appendix.tex
   notation table L36). Code `forces.thrust_body` L156-158 returns `(T cos d, T sin d)` (+z_r) and the docstrings (`forces.py` L136,
   `dynamics.py` L313) describe `+delta`. Consistent through the appendix mapping, but a positive `misalign_deg` gives a nose-UP
   moment while positive paper theta_t gives nose-down; in-code comments contradict the paper's sign.
8. **Event guards.** Paper `sec:states` Events: "ignored for the first 0.1 s" for ground and apogee only; code also guards rail exit
   (`integrate.py` L185) and, since D-94b, the chute apogee predicate (`forces.py` L297). Paper `sec:recovery`: apogee deployment
   "is not guarded against" - true after 0.1 s, not before.
9. **One g_0 for three jobs.** Paper separates ISP's `g_0` ("unrelated to the local g(h)") from constant gravity; code uses the
   single `Params.g0` for ISP (`dynamics.py` L239), constant gravity (`gravity._g_constant`) and the radial reference
   (`_g_radial`). Identical at 9.80665; differs only if a scenario overrides `g0`.
10. **Radial gravity radius** (paper `sec:gravity`: r = R_0 + height gained, R_0 = R_e + h_0 + h_g0) vs code `R_e + h_AGL`
    (`gravity.py` L79-80); already a \todo (models:41), listed for completeness. Naming: paper "Ellipsoidal" = code
    `gravity.direction="elliptical"` / `gravity.model="wgs84"`.

## Round 7 additions (2026-10-17)

Paper: Dryden/vertical wind in `sec:atmos_noise`, `sec:vertical_wind`; air brake in `sec:airbrake` (now in `other-dynamics.tex`).

- **Dryden `w` missing.** Code `wind._dryden_turbulence` (L180) returns `(u, v)` only; the spec's vertical component `w`
  (in-plane in 2D; MIL-F-8785C low altitude `L_w = h`, `sigma_w = 0.1 W20`, PSD of the form of `Phi_v`) is absent.
  Paper: `\simtodo` in `sec:atmos_noise`.
- **Dryden `v` has no 2D effect.** `w_y` is discarded by the 2D closure, so the code's `v` never reaches the trajectory;
  only `u` (projected) acts. Paper states it.
- **Air-brake representation.** Code `forces.aero_force_body` L223-227: additive axial term
  `A_brake = q Cd_b S_max f_b`, times `axial_flow_factor(alpha)`; no `C_z`/`C_m` contribution, no own component, no
  `f_b` table axis. Paper `sec:airbrake`: two variants (own component in the multi-component build-up; whole-rocket tables
  with `f_b` axis), neither implemented; the additive term is the paper's simplest case, `Delta C_x = C_{D,b} S_b f_b / S`.
- **Omega frame.** Code resolves Omega once at the launch site in F0 (`rotation.py`) while gravity may follow the rotated
  `z_g`; effect ~3e-6 of Coriolis at 10 km. Paper: `\simtodo` in `sec:noninertial`.
- **Vertical wind.** All tiers return `w_z = 0`. Paper: `\simtodo` + three `\restodo` in `sec:vertical_wind`.
- **Thrust side-force noise** `T_s = kappa T xi z_t` and **motor roll torque**: not in code (already a `\restodo`).
- **Recovery force symbol.** Paper renamed `F_ch` to `R_ch` (code `forces.parachute_drag_inertial`, unchanged).
