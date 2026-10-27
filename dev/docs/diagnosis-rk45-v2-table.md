## Кратко (RU)

- RK45 "зависает" не из-за жёсткости или нестабильности тангажа, а из-за разрыва в табличной аэродинамике при хвостовом спуске: alpha = atan2(w, u) около ±180 градусов, а `np.interp` клампит C_N и C_m на краю таблицы (±10 градусов) с противоположными знаками. Это скользящий режим (Filippov) на w = 0: шаг RK45 схлопывается до ~1e-14.
- Не зависит от C_m (v2 и legacy example.csv ведут себя одинаково), от c_mq (демпфирование не лечит), от парашюта. Constant-аэро не затронуто.
- RK4 dt=0.005 "работает" потому, что фиксированный шаг не замечает разрыва (дребезг вокруг w = 0 с амплитудой порядка шага).
- Рекомендация: opt-in политика экстраполяции таблицы за пределы alpha (C_N, C_m плавно к 0 к ±90 градусам / нечётное продолжение). C_m,q и jet damping эту проблему не решают. Влияние на пины: ноль при дефолте (clamp).

# Diagnosis: RK45 stalls on the demo airframe with `data/aero/example_v2.csv`

Date: 2026-10-18. Branch `feature/sim-paper-alignment` (worktree `merge-develop`). Diagnosis only; no source edits.

## Verdict

Root cause is **(b): a discontinuity in the table lookup**, not (a) stiffness, (c) instability or (d) event chatter.

During tail-first descent (after apogee) the body is still nose-up (theta = pi/2, omega ~ 1e-9) while the air-relative velocity points along -x_body. Then `alpha = atan2(w, u)` is ~ +/-180 deg and flips sign with the sign of the tiny transverse velocity `w` (~1e-9..1e-7 m/s). `aero._table_lookup` uses `np.interp(alpha, table.alpha, ...)`, which clamps outside the table grid (alpha_deg in {-10, 0, 10}). So C_N and C_m jump between +0.5236 (alpha = +180) and -0.5236 (alpha = -180) as `w` crosses 0. The jump sign is such that the induced acceleration pushes `w` back toward 0 on both sides: a sliding mode on the surface w = 0. The adaptive stepper cannot resolve it: step size collapses (min step 7e-15, ~400k RHS evaluations in 40 s wall, never gets past t ~ 16.8 s). RK4 with fixed dt cannot "see" the discontinuity and just chatters at O(dt).

The stall is **not** caused by the C_m convention, pitch damping, the airframe's flight stability, the parachute, or the events.

## Evidence

All scripts in the scratchpad (`exp1..exp5.py`), wall-clock capped.

Scenario: `DEMO` rocket + `LARGE` motor (test `test_works_with_v2_table_and_margin_series`), `t_max` 20-200 s.

| Case | Result |
|---|---|
| constant aero (demo default), parachute on | OK: 1052 RHS evals, 130 steps, apogee 14.9 s |
| constant aero, no parachute | OK: 626 evals, ground 30.96 s |
| table `example_v2.csv`, parachute on | STALL at t ~ 16.6-16.8 s (>150k evals) |
| table `example_v2.csv`, no parachute | STALL at t ~ 16.45 s (>187k evals) |
| table `example.csv` (legacy), c_mq = 0 | STALL at t ~ 16.7 s |
| table `example_v2.csv`, c_mq = 0.5 | STALL at t ~ 16.7 s |
| RK4 dt=0.005, v2, c_mq = 0 | OK: 16000 evals, 1.3 s, apogee 16.23 s |

Stall state: z = -1255.5 (altitude 1255 m, just after apogee at 16.23 s), vz ~ +1.9..4.3 m/s (descending), vx ~ 1e-8, theta = 1.5708, omega ~ 1e-9, accepted times separated by 4e-7 s, then 0.07..0.2 s jumps (error estimate randomly lucky).

RHS probe at the stalled state (t = 16.4, y = [0, -1256.7, vx, 1.9, pi/2, 0, 1.7], vx varied):

```
vx=-2e-08  alpha=-180.000  dvx=+1.3799e-03  domega=+7.7244e-03
vx=-1e-12  alpha=-180.000  dvx=+1.3799e-03  domega=+7.7244e-03
vx= 0      alpha=+180.000  dvx=-1.3799e-03  domega=-7.7244e-03
vx=+2e-08  alpha=+180.000  dvx=-1.3799e-03  domega=-7.7244e-03
```

A sign jump in the RHS across an infinitesimally thin surface, with the vector field pointing at the surface from both sides: textbook sliding mode.

Confirmation by monkeypatch (not committed): fade C_N and C_m linearly to 0 between the table edge (10 deg) and 90 deg (odd, continuous through 180 deg). Same scenario, same RK45, `t_max = 200 s`: finishes in **2480 RHS evaluations, 0.24 s wall**, apogee 16.23 s, max|omega| = 4e-9 (`exp5.py fix`). Unpatched: timeout (`exp5.py nofix`).

### (a) Stiffness: ruled out

Flown test case (3 s, from `tests/test_aero_v2.py::_v2_example_params`, c_mq = 0, RK45): median accepted step 3.2 ms, max 23 ms, 692 steps, 4484 RHS evals, 0.4 s wall. Estimate at max-q (v = 150 m/s, q ~ 13.5 kPa, S = 0.02, d = 0.08, C_m,alpha ~ 0.5/rad, I = 0.05): omega_n ~ sqrt(q S d C_m,alpha / I) ~ 15 rad/s (period ~ 0.4 s) -> ~130 RHS steps per period. Not stiff. Note that for this airframe the static stability is dominated by the normal force acting through the arm (C_N,alpha ~ 3/rad times arm l_p - l_g = 0.28 m), not by the C_m term: d*C_m,alpha / (C_N,alpha * arm) ~ 0.05. So the C_m sign convention barely affects the dynamics here, and "restoring C_m slope, no damping" is not the cause.

### (c) Instability: ruled out

Flight is statically stable in both tables (CP behind CG by the normal-force arm). 3 s test flight, omega envelope per quarter: RK45 v2 = 4.94 -> 1.09 -> 0.236 -> 0.046; RK4 v2 = 4.91 -> 0.25 -> 0.046 -> 0.023; RK45 legacy `example.csv` = 4.69 -> 1.08 -> 0.257 -> 0.053. No growth. The decay with c_mq = 0 comes from the falling dynamic pressure (adiabatic frequency drop) plus the rotation of the velocity vector by the normal force; there is no explicit pitch damping term. In the ascent of the demo launch (vertical, no disturbance) omega stays at ~5e-9 (rounding noise), alpha ~ 0.

### (d) Events: ruled out

The stall persists with the parachute removed. `_apogee_event` fires at 16.23 s and `_parachute_deploy_event` at the same time, well before the stall; the step collapse happens ~0.2-0.6 s later at varying times with no event nearby.

### Q2: legacy `example.csv`

Flies in the 3 s test with RK45 (0.34 s, stable, decaying, as above). In the full demo-airframe launch it stalls at the same place, same mechanism (row "legacy" above). Statically stable as noted (the C_m term is ~5% of the normal-force moment; B31 sign question is nearly irrelevant for these numbers).

### Q3: RK4 with v2

Physically plausible and stable for the ascent (3 s test: omega peak 4.9 rad/s from the 0.1 rad initial offset, decays to 0.02 rad/s). Caveat: the descent is not meaningful after apogee for the same reason: RK4 is chattering around w = 0, silently. The test `test_works_with_v2_table_and_margin_series` only reads the ascent (`rail_exit`, `burnout`), which is why RK4 is "fine" there. Its comment "RK45 crawls on this airframe with a restoring-moment table (no damping)" is a misattribution and should be corrected when the fix lands.

## Recommendation

C_m,q (paper `eq:pitch_damping_moment`) and jet damping do **not** help: the discontinuity is in the force and moment lookup at alpha ~ 180 deg, not in pitch dynamics. `max_step` also does not help (a sliding mode defeats any step size). Real-rocket tables (typically alpha range 0..15 or +/-15 deg) will hit the same wall on the first tail-first descent under RK45 (either with or without a chute).

Proposed fix (needs an architect decision since it adds model behaviour and an `Aero` field):

1. In `sim/aero.py` `_table_lookup` (and the corresponding C_N, C_m reads in the table path of the seam), add an out-of-range alpha policy, selectable by a new `Aero` field, e.g. `table_oob: str = "clamp"`:
   - `"clamp"` (default): today's behaviour, **bit-identical**.
   - `"taper"`: for |alpha| beyond the table edge, C_N and C_m fade linearly to 0 at |alpha| = 90 deg and stay 0 beyond (odd and continuous through +/-180 deg). C_A is left clamped (reverse axial flow is a separate question; its value is continuous, no sliding mode).
   Alternative with more physics: odd, 2*pi-periodic reflection (C_N(pi - alpha) = C_N(alpha)-style) -- but this invents data for a flow regime the table does not cover; taper-to-zero is the minimal honest choice (small `q` anyway in tail-first descent).
2. Table loader/validator: emit a warning (like the Mach-range flag in `test_mach_beyond_table_range_is_flagged`) when a flight leaves the table's alpha range, so the user knows the outcome there is extrapolated.
3. Correct the comment in `tests/test_scenario_sweep.py` (line ~123); add a regression test: demo + `example_v2.csv` + `table_oob="taper"` + RK45, `t_max = 200`, assert `nfev` / wall below a bound and apogee equals the RK4 apogee within tolerance. (Seam is right: it flies the real call path.)

## Pin impact

- Defaults unchanged (`table_oob="clamp"`): no numeric change anywhere; strict opt-in policy preserved. All existing pins (RK4 and RK45) stay bit-identical.
- Tests that run table models only fly inside the table's alpha range (ascent / short flights), plus `test_works_with_v2_table_and_margin_series` on RK4; none need re-pinning. Making `"taper"` the default would be a decision for the user and would change any table-model flight that leaves the alpha range (none among current pins as far as I could see, not exhaustively checked).
- Interim workaround for users: keep RK4 for table models, or cut `t_max` at apogee/`terminal` apogee (RK45 is fine up to apogee).

## Scratch files

`C:/Users/kaman/AppData/Local/Temp/claude/d--YandexDisk-Projects-Rocket-physics/c4709641-981a-4999-9116-5277ff307891/scratchpad/exp1.py` .. `exp5.py` (instrumented runs, RHS probe `exp4.py`, monkeypatched fix `exp5.py`). No debug instrumentation in the repo.
