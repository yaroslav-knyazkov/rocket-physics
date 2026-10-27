# Step 112 notes (Jorgensen large-alpha extension, D-120)

## Measured (DEMO + LARGE + example_v2.csv, RK45, S_p = 0.08, l_pc = 0.7, table_oob="jorgensen")
- ballistic (no chute), t_max 200: ground at 33.03 s, 854 RHS evals, 0.08 s wall.
- with chute, t_max 400 (canopy descent from ~1.25 km needs ~250 s, not 200): ground at 248.5 s, 2726 evals, 0.32 s wall.
- clamp (unchanged) stalls (diagnosis: >150k evals).

## Parameters (research: dev/docs/latex/research/jorgensen-params-findings.md)
- eta(L/d): TR R-474 Fig. 4 digitized (+-0.005), L/d 2..40 -> 0.577..0.815, linear, clamped. Rise with crossflow Mach (-> ~1 supersonic) NOT modelled. L/d is taken as S_p/d_ref^2.
- C_dn = 1.2 constant: UNVERIFIED default; Mach/Re dependence (transonic peak, supercritical drop) out of scope (backlog B42).
- C_x180: UNVERIFIED placeholder; 0.0 -> C_x(0) of the table. Jorgensen uses a separate C_A(180); the user should set it.

## Model choices (not paper-verified)
- Blend: smoothstep over `oob_blend_deg` (10 deg) beyond the table edge.
- Sign of the potential term above 90 deg: follows the printed sin(2a)cos(a/2) (negative there, tiny). Sign convention for a > 90 deg not confirmed by sources.
- Crossflow term made odd as sin(a)|sin(a)|.

## Deviations from the ticket
- Test 2 ("ascent equals clamp, bitwise") is not valid: on the pad the air-relative speed is ~1e-7 m/s, alpha = atan2(w, u) is noise (frequently +-180 deg), so the clamp run leaves the table in its first steps and the step sequences differ. Replaced by `test_ascent_matches_clamp` (altitude and vz at t = 15 s within rel 1e-5).
- Continuity constant L = 50 is too small: C_m slope at the end of the blend band is ~210/rad for S_p/S = 35 (crossflow arm term). Used 400.
- Chute full-flight test uses t_max = 400 (see above).
- `tests/test_scenario_sweep.py` L123 comment already pointed to Step 112; left as is.

## Pins
No existing expectation moved (see suite result in the report).
