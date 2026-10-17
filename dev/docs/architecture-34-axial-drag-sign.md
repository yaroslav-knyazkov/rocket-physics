# Architecture 34 — Axial aero force opposes the relative flow (D-91) + demo parachute

## Кратко (RU)

- Баг подтверждён: `sim/forces.py:224` всегда направляет осевую силу к хвосту; `C_x` в моделях constant/linearized не зависит от α, table зажимает α на краю (±10°). При полёте хвостом вперёд «сопротивление» разгоняет ракету (демо: удар 874 м/с). LaTeX (`rocket-2d.tex:65`, `models.tex`) содержит ту же ошибку — follow-up B27, LaTeX не правим.
- Фикс: множитель `f(α)=clip(cos α / cos 85°, −1, 1)` к `C_x` (constant, linearized, table без покрытия обратного потока) и к аэротормозу. 3D наследует через `forces3d`.
- Сдвигается 1 пин (Mach-тест: 2.57 → 1.75, пик на подъёме); остальные 488 тестов бит-в-бит.
- Демо: основной парашют в апогее (Cd 0.8, S 1.23 м²), `t_max` 1200 с → спуск ~6 м/с, удар 5.97 м/с при t ≈ 891 с. Попутно: защита от раскрытия на старте (t < 0.1 с).
- Решения D-92..D-97, шаги 93-95; B17 закрыт, B23 разблокирован.

## Contents

- §34.1 Root cause (measured)
- §34.2 Relation to the LaTeX equations (read-only)
- §34.3 The corrected formula
- §34.4 Affected models and code paths (2D and 3D)
- §34.5 Demo parachute
- §34.6 Measured pin moves (old -> new)
- §34.7 Mach warning, App 2, App 4
- §34.8 Decision log (D-92 …)
- §34.9 Risks
- §34.10 Implementation tickets (Steps 93+)

## 34.1 Root cause (measured)

**Mechanism — confirmed.** `sim/forces.py:220-224`, `aero_force_body`:

```python
c = aero.coefficients(t, s, p, flow, hold)
A_x = flow.q * p.aero.S * c.C_x
...
return np.array([-(A_x + A_brake), -A_z])
```

The axial force is always `-A_x * x_hat_r` (body frame, toward the tail). `flow.q = 0.5*rho*V^2`
(`sim/flow.py:94`) is sign-blind, so the force direction is set entirely by the sign of `C_x`.
Whether `C_x` carries the flow direction depends on the coefficient model (`sim/aero.py`):

| model | `C_x` source | at `alpha = ±180°` (tail-first) | verdict |
|---|---|---|---|
| `constant` | `p.aero.C_x` (`sim/aero.py:235`) | `+C_x` — alpha ignored | **wrong sign** |
| `linearized` | `p.aero.C_A0` (`sim/aero.py:281`) | `+C_A0` — alpha ignored | **wrong sign** |
| `table` | `np.interp(alpha, …)` of `C_A` (`sim/aero.py:318`, `_table_lookup` :197-203) | clamped to the grid edge — `data/aero/example.csv` spans only `alpha ∈ [-10°, +10°]`, so `C_A(±180°) = C_A(±10°) > 0` | **wrong sign** for every table not covering reversed flow (all committed tables) |
| airbrake term | `A_brake = q*Cd_brake*S_max*f` (`sim/forces.py:223`), added into the axial term | always tail-ward | **wrong sign** after apogee (App 4's `descent_demo`, trigger `after_apogee`) |

When the relative wind comes from the tail (`u < 0`, `alpha ≈ ±π`), the body-frame velocity is
along `-x_hat_r`, so `-A_x x_hat_r` is *along* the motion: "drag" does positive work. Pre-fix
`configs.get("demo")`, measured (sample points of the dense output):

| point | t [s] | h [m] | \|v\| [m/s] | e = v²/2 + g h [kJ/kg] | theta |
|---|---|---|---|---|---|
| apogee | 29.38 | 5946.7 | 2.3 | 58.3 | 90.0000° |
| descent | 50.10 | 3542.9 | 283.5 | 74.9 | 90.0000° |
| descent | 56.24 | 995.3 | 634.0 | 210.7 | 90.0000° |
| near ground | 57.50 | 66.4 | 855.1 | 366.2 | 90.0000° |
| impact | 57.58 | 0 | **874.1** | 382 | 90.0000° |

Specific energy rises monotonically on descent — impossible with only gravity and drag.

**Why theta stays exactly 90° (expected for this config).** The demo has `C_z = C_m = 0`,
`c_mq = 0`, on-axis thrust (`misalign_deg = 0`, `u_B = u_C = 0`), no wind and a vertical launch,
so `M_y = M_thrust + M_aero + M_moment` (`sim/dynamics.py:318-321`) is identically zero: `aA` and
`aB` are on-axis and parallel to every force component, and `aero_moment_y` returns 0. `omega`
stays 0 and `theta` stays at its initial 90°. A real fin-stabilised rocket weathercocks nose-down
after apogee; this config cannot, because the `constant` model has no alpha-dependent restoring
moment by construction (a constant `C_m` would be a fixed torque, not a restoring one). So
"falls tail-first" is the correct consequence of the inputs; only the sign of the axial force on
that tail-first leg is a bug. Not changed here (see D-95).

**Scope check of `forces3d.py`.** `aero_force_body_3d` (`sim/forces3d.py:108-123`) builds a 2D
state view and calls `forces2d.aero_force_body` verbatim — the 3D path inherits both the bug
and the fix with no code of its own. `dynamics3d.py` holds attitude fixed, so a 3D vertical
flight is tail-first after apogee exactly like the 2D one.

**Parachute force is correct.** `parachute_drag_inertial` (`sim/forces.py:295-320`) already
uses `-0.5*rho*Cd*S*V*v_rel_i` — it opposes the relative velocity vector. But under canopy the
body's own axial force is still summed into `F_i` (`sim/dynamics.py:218` then `:347-348`), so a
parachute alone does **not** cure the bug: with the canopy deployed and the body frozen
nose-up, the body's `-A_x x_hat_r` still pushes downward. Both fixes are needed.

## 34.2 Relation to the LaTeX equations (read-only)

The code is **faithful to the LaTeX; the LaTeX itself encodes the wrong sign** for reversed flow.
Nothing under `dev/docs/latex/` is edited by this phase (frozen, D-84..D-90 standing); the items
below are a **LaTeX follow-up for the user** (proposed backlog item, D-96).

| where | what it says | problem |
|---|---|---|
| `sections-ai/rocket-2d.tex:65-67` | `A_f = -A_x x_r - A_z z_r`, "`A_x, A_z` the drag and lift magnitudes" | "magnitude" + fixed `-x_r` = always tail-ward. Should read: `A_x` is the *signed* axial force, positive when it points aft, its sign set by the flow direction through `C_x(alpha)`. |
| `sections-ai/models.tex:264` | `A_x = qSC_x` | correct as a definition; fine once `C_x` is signed. |
| `sections-ai/models.tex` §Coefficients, Constant item (~:312) | "`C_x, C_z, C_m` fixed inputs … independent of both alpha and M" | `C_x` must not be alpha-independent across `|alpha| > 90°`; needs the flow-direction factor of §34.3. |
| same, Linearized, `eq:aero_linearized` (~:323) | `C_x = C_A0` | same; becomes `C_x = C_A0 f(alpha)`. |
| same, Table item (~:338) | "bracket and clamp M … interpolate linearly in alpha" | silent about alpha outside the grid; clamping at the alpha edge is the tail-first bug. Needs the §34.3 rule. |
| `sections-ai/models.tex:1059-1069`, `eq:airbrake_force` | brake "routed along `x_r` … axial drag whatever the pitch" | "whatever the pitch" is right for nose-first only; the brake term takes the same `f(alpha)`. |
| `sections-ai/models.tex:1005-1009` (recovery trigger) | "a pre-apogee transient in `z-dot` … would arm deployment early. Not guarded against" | the demo hits this on the pad (§34.5); the `t < 0.1 s` guard of D-94b should be recorded there. |
| `sections-ai/analysis.tex:36-40`, `eq:analytic_force_x` | `m x-ddot = … - A_x` | ascent analysis, nose-first; unaffected (f = 1 there). |

## 34.3 The corrected formula

One flow-direction factor, applied to the axial coefficient only:

```
f(alpha) = clip( cos(alpha) / cos(alpha_0), -1, +1 ),   alpha_0 = 85 deg   (D-92)

constant:    C_x = C_x      * f(alpha)
linearized:  C_x = C_A0     * f(alpha)
table:       C_x = C_A(alpha, M) * f(alpha)   iff the table's alpha grid lies inside (-90°, +90°);
             C_x = C_A(alpha, M)              if the table covers reversed flow (it is authoritative)   (D-93)
airbrake:    A_brake = q * Cd_b * S_b * f_b * f(alpha)                                                  (D-94a)
A_f = -(A_x + A_brake) x_r - A_z z_r          (unchanged expression; A_x is now signed)
```

Properties that make this the recommended shape:

- **Bit-for-bit nose-first.** For `|alpha| <= 85°`, `cos(alpha)/cos(85°) >= 1`, so `f` is exactly
  `1.0` and `C_x * 1.0 == C_x` in IEEE arithmetic. Every ascent, every nose-first flight, every
  test without reversed flow is unchanged to the bit (measured, §34.6).
- **Correct tail-first.** For `|alpha| >= 95°`, `f = -1`: the axial force points toward the nose,
  i.e. against the motion. Same magnitude `|C_x|` — a deliberate simplification (a real body's
  base-first `|C_A|` differs from its nose-first one; a table can carry that). This is what
  "constant coefficients" means once the flow can reverse: a constant `|C_x|` whose sign follows
  the flow; the ramp exists only for continuity, so it is kept as narrow as is comfortable.
- **Continuous.** `f` is linear in `cos(alpha)` across `85°..95°` (slope ≤ 11.5 /rad) and is 0 at
  90° (pure crossflow has ~no axial component on a body of revolution). No jump for the adaptive solver —
  the project already paid for one discontinuity (Step 35, `atan2` branch cut, `sin(alpha)` fix).
  At a vertical apogee alpha jumps 0 -> π while `V -> 0`; the force is `q*S*C_x*f` with
  `q ∝ V^2 -> 0`, so it stays continuous there too.
- **No division by V, no new state.** `flow.alpha` is already computed (`sim/flow.py:86`).

Where it lives: a public helper `axial_flow_factor(alpha) -> float` in `sim/aero.py` (beside the
three `_*_coeffs`, which call it), and one multiplication in `forces.aero_force_body`'s
`A_brake` line. Applying it in the coefficient models (not in `forces.py` on `A_x`) keeps the
Step-55 "one seam" property: `aero.coefficients(...)` returns the coefficient actually in force,
so `control.aero_coeff_delta`, the `C_A(...)` thin wrapper and every test see the signed value.
The `C_A` wrapper (`sim/aero.py:381-384`) inherits it automatically.

Rejected alternatives (measured where it matters, §34.6):

| option | pros | cons |
|---|---|---|
| **clip-ramp `f`, `alpha_0 = 85°` (recommended)** | bit-for-bit for `|alpha| <= 85°`; continuous; zero at 90°; **1 pin test moves** | one constant `alpha_0`; kinks at 85°/95° (C0, harmless for RK45) |
| clip-ramp, `alpha_0 = 80°` | wider, gentler ramp | `test_integrate`'s two tilted pin tests start at `alpha = 80.0°` exactly (`theta0 = 80°`, `v0` horizontal) and reach 80.008°: their 4 pinned runs move by ≤ 3.0e-4 m — **3 pin tests move** (measured) |
| `f = cos(alpha)` | smooth (C∞), no constant | changes `C_x` at every non-zero alpha, table lookups included: **7 tests fail** (measured: 4 in `test_aero.py` table/linearized exact-value pins, both tilted pins, Mach) and under-counts axial drag at moderate alpha (−13 % at 30°) |
| `f = sign(cos alpha)` | bit-for-bit nose-first; simplest | jump of `2qSC_x` at 90° at finite V — exactly the discontinuity class that collapsed RK45 at Step 35 |
| rotate the drag into the wind frame (`-qSC_x u_hat`) | "drag opposes velocity" literally | reverts Step 35 (double-applies alpha with body-axis coefficients); moves every non-zero-alpha pin |

## 34.4 Affected models and code paths (2D and 3D)

| path | file:line | change |
|---|---|---|
| `constant` coefficients | `sim/aero.py:234-240` | `C_x=p.aero.C_x * axial_flow_factor(alpha)` |
| `linearized` coefficients | `sim/aero.py:280-286` | `C_x=p.aero.C_A0 * axial_flow_factor(alpha)` |
| `table` coefficients | `sim/aero.py:317-323` | `C_x=… * _table_axial_factor(table, alpha)` (1.0 if the grid reaches `±90°`) |
| `C_A` thin wrapper | `sim/aero.py:381-384` | none — inherits |
| airbrake term | `sim/forces.py:223` | `* aero.axial_flow_factor(flow.alpha)` |
| 2D axial force | `sim/forces.py:224` | none — `A_x` now signed |
| 2D pitching moment | `sim/dynamics.py:319` `_cross_y(aA, aero_force)` | none — the `-u_B*A_x` term (nonzero only with `u_B != 0`) flips with `A_x`, which is the correct physics |
| 3D | `sim/forces3d.py:120-123` -> `forces2d.aero_force_body` | none — inherits |
| parachute | `sim/forces.py:295-320` | none (already opposes `v_rel`) |
| `parachute_deployed` | `sim/forces.py:280-292` | D-94b: `t < 0.1` guard on the `apogee` trigger (§34.5) |
| C_z / C_m under `constant` | `sim/aero.py:236-237` | **not changed** (D-95): a constant normal force/moment is already non-physical at every alpha; flipping it is not a sign fix |
| Step-92 Mach warning | `sim/mach_warning.py` | no code change; its number changes (§34.7) |

## 34.5 Demo parachute

**Machinery found.** `sim.params.Recovery` (`sim/params.py:146-151`: `model none|deploy`,
`trigger apogee|timer`, `deploy_time`, `Cd`, `S`), carried on `configs.schema.Rocket.recovery`
(`configs/schema.py:278`); force `forces.parachute_drag_inertial` (`sim/forces.py:295`), attitude
freeze `sim/dynamics.py:340-351`, event `integrate._parachute_deploy_event` (`sim/integrate.py:194`).
**One canopy only** — no drogue + main, no altitude trigger. Dual deploy is new `sim/` physics
(D-97, backlog).

**Spec (recommended, D-97 option a): one main canopy at apogee.** Dry (burnt-out) mass measured
from the run: `y[M]` at impact = **2.195 kg** (airframe 1.5 + K570 casing 0.695).

```python
# configs/rockets/demo.py  -- Rocket(...)
    recovery=Recovery(
        model="deploy",     # single main canopy (the only recovery machinery sim/ has)
        trigger="apogee",   # deploys once v_z > 0 (descending), after the t < 0.1 s pad guard (D-94b)
        Cd=0.8,             # round canopy, typical vendor figure
        S=1.23,             # m^2 -- ~1.25 m flat-diameter round canopy (pi*1.25^2/4 = 1.227);
        #                     sized for ~6 m/s at sea level on the 2.195 kg burnt-out vehicle:
        #                     V_term = sqrt(2*m*g/(rho*Cd*S)) = sqrt(2*2.195*9.807/(1.225*0.8*1.23)) = 5.98 m/s
    ),
# configs/scenarios/demo.py  -- Scenario(...)
    solver=Solver(t_max=1200.0),  # canopy descent from ~5.9 km takes ~860 s; default 300 s would stop mid-air
```

Synthetic-but-plausible, commented in the demo's own voice (module docstring gets one bullet:
"main canopy at apogee — a real flight to this altitude would use drogue + main (dual deploy),
which `sim/` cannot model yet; D-97").

**Measured result (scratch copy, sign fix + D-94b guard + this spec):**

| quantity | value |
|---|---|
| apogee / t | 5947.0 m / 29.614 s (event; unchanged from pre-fix) |
| `parachute_deploy` event | 29.614 s (= apogee) |
| descent rate at 3.5 km / 1.0 km / 0.1 km | 7.12 / 6.27 / 6.00 m/s |
| ground impact | **t = 890.87 s, \|v\| = 5.97 m/s** (`V_term` check above: 5.98) |
| specific energy | monotonically decreasing 58.3 -> 0.0 kJ/kg |
| peak Mach | 1.751 at t = 3.2 s (ascent) |
| wall time, one `run_sim` | ~0.4 s (992 output samples, vs ~280 for a ballistic descent) |

For comparison, sign fix **without** parachute: ballistic tail-first descent, impact
**t = 72.68 s, |v| = 183.8 m/s** (terminal `sqrt(2mg/(rho*C_x*S))` = 175 m/s at sea level), peak
descent Mach 0.56, energy monotonically decreasing.

**Latent bug the parachute exposed (D-94b).** With `trigger="apogee"`, `parachute_deployed` is
`y[VZ] > 0` (`sim/forces.py:292`). The demo has no rail and the K570 curve starts at T = 0 at
t = 0, so for the first ~2 ms gravity wins and `vz > 0`: the canopy "deploys" on the pad and
`Result.events["parachute_deploy"]` reads **0.0**, not 29.6 (measured). The integration is
barely affected (chute drag ∝ V ≈ 0 there) but the event is wrong. Fix: the same `t < 0.1`
guard `_apogee_event` already uses (`sim/integrate.py:124-125`): `if t < 0.1: return False`
before the `vz` test. Measured: event becomes 29.614 s.

## 34.6 Measured pin moves (old -> new)

Scratch copies of `sim/ configs/ apps/ tests/ data/ dev/` (baseline copy: **489/489**, 273 s),
patch switchable by env var. Full suite per variant:

| variant | failing tests |
|---|---|
| **recommended: ramp `alpha_0=85°` + D-93 + D-94a/b + demo parachute (D-97)** | **1** — `test_mach_warning.py::test_demo_peak_mach_is_supersonic` (488 pass, 308 s) |
| ramp `alpha_0=85°`, sign fix only | same 1 (tilted pins measured bit-for-bit, max\|Δy\| = 0) |
| ramp `alpha_0=80°` (± parachute) | 3 — the Mach test + `test_integrate.py::test_tilted_run_bit_for_bit_under_parallel_both_integrators` + `::test_tilted_sounding_run_bit_for_bit_under_parallel_both_integrators` (4 pinned runs, max\|Δy\| 1.5e-4 / 3.0e-4 / 5.6e-5 / 2.1e-4) |
| `f = cos(alpha)` | 7 (adds `test_aero.py::test_table_lookup_interpolates_alpha_within_bracketed_M`, `::test_table_lookup_exact_grid_point`, `::test_no_table_reproduces_pre_step25_coefficients_exactly`, `::test_cop_travel_moment_uses_table_l1_not_constant_pl1`) |

**The one re-record (recommended variant):**

| test | old | new |
|---|---|---|
| `tests/test_mach_warning.py::test_demo_peak_mach_is_supersonic` | `2.0 < m < 3.0`; `0 < t <= events["ground"]` (measured 2.569 at t = 57.58 s, the impact) | `1.7 < m < 1.8`; `0 < t <= events["burnout"]` (measured **1.751 at t = 3.2 s**, burnout 3.59 s). Rename to `test_demo_peak_mach_is_the_ascent_peak`; fix the trailing comment. |

**Not pinned, but moves (reported, not asserted).** The demo has no rail and the K570 curve
starts at T(0) = 0, so the vehicle sags tail-first for ~2 ms on the pad (`vz > 0`, `alpha = π`):
the fix flips the (tiny) axial force there, so the demo trajectory differs from the first output
sample at ~1e-14 relative, growing to: apogee event 29.614430 -> 29.614444 s; App 4 brake-closed
apogee 5947.0018 -> 5947.0107 m; App 4 solved `C_dA` 0.00160312 -> 0.00160312 (Δ 2.5e-9 m²),
`timer_3850m` 0.0118366 -> 0.0118368, `when_to_pop` deploy 3.584425 -> 3.584423 s; App 2 rows
agree to ~2e-6 relative. Nothing else in the 488 passing tests moved bitwise where pinned.
Warning count in the suite fell 109 -> 35 (the blow-up overflow warnings are gone).

## 34.7 Mach warning, App 2, App 4

- **Step-92 Mach warning** — still fires (1.75 > 0.8), now with the true ascent peak:
  `peak Mach 1.75 at t=3.2 s` (was `2.57 at t=57.6 s`, the runaway impact). No code change.
- **App 2 (`cfd_conditions`)** — ascent-only by design (`select_conditions.py:127-129`), so its
  table is unchanged to ~2e-6. Its comment "supersonic Mach (~1.05-2.6)" (`:200-201`) was already
  stale: the measured rows span **M 0.51-1.72** before and after. Fix the comment.
- **App 4 (`airbrake_sizing`)** — the three apogee-target specs are ascent physics: `targets.py`
  literals (3850 m, `C_dA` 0.0016, bounds 0-25 s, "~5947 m / ~29.6 s / 3.59 s") stay valid, **no
  re-record**. `descent_demo` (`after_apogee`, 10 m² brake): before the fix the integration
  diverged (`vz = 1.5e12 m/s`, solver died at t = 30.0 s); after it the vehicle descends steadily
  at ~2.1-2.5 m/s and the run ends at `t_max` (impact time `None` for a physical reason now).
  B17 is closed by this fix; **B23** (a descent objective) is unblocked but not built here. The
  refusal text `_AFTER_APOGEE_REFUSAL` (`solve_cda.py:108-117`) and the module note (`:31-35`)
  claiming descent physics is untrustworthy get reworded (the refusal itself stays: apogee is
  still independent of a post-apogee brake by construction).
- **Runtime.** With the parachute every demo flight runs to ~891 s (992 samples vs ~110):
  `test_airbrake_sizing.py::test_end_to_end_against_demo_for_every_named_spec` 9.4 s -> 34.8 s;
  suite ~+30 s. Accepted (D-97); an apogee-terminated run mode for App 4 is the cure (backlog).

## 34.8 Decision log (D-92 … D-97)

| id | question | options | recommendation |
|---|---|---|---|
| D-92 | shape of the flow-direction factor | ramp `alpha_0=85°` / ramp 80° / `cos alpha` / `sign(cos alpha)` / wind-frame drag (§34.3) | **ramp 85°** — 1 pin moves, continuous, bit-for-bit nose-first |
| D-93 | `table` model | (a) factor only if the alpha grid stays inside ±90°, else the table rules / (b) always / (c) never | **(a)** — fixes every committed table (±10°) without double-flipping a future full-range CFD table |
| D-94a | airbrake term | follow `f(alpha)` / stay tail-ward | **follow** — same body-axis physics; unblocks B23 |
| D-94b | `apogee` trigger arms on the pad sag | `t < 0.1 s` guard (same as `_apogee_event`) / "after burnout and vz > 0" / leave | **0.1 s guard** — one line, mirrors the event, measured event 0.0 -> 29.614 s |
| D-95 | `constant` `C_z`/`C_m`, weathercocking | leave / flip with `f` / add restoring moment to demo | **leave** — not a sign bug; frozen theta is the honest consequence of `C_z=C_m=0` |
| D-96 | LaTeX | follow-up items of §34.2 as backlog **B27**; B17 -> closed; B23 -> unblocked; pad-sag "no motion until T > W" as **B28** | **record, do not edit** (LaTeX frozen) |
| D-97 | demo recovery | (a) one main at apogee, Cd 0.8, S 1.23 m², `t_max` 1200 s -> 5.97 m/s / (b) drogue-only S 0.11 m² -> 19.9 m/s, fits 300 s / (c) dual deploy — new `sim/` physics | **(a)** now; (c) as backlog **B29**. Cost: suite ~+30 s |

## 34.9 Risks

- **Pad sag.** Any rest-start without a rail and with T(0) < mg flies its first ms tail-first; the
  fix (correctly) changes it, so such runs drift at round-off and beyond. No pin covers one today
  (measured); a future pin on such a run must be recorded after Step 93. B28 removes the sag.
- **`alpha_0` near a test's alpha.** The tilted pins sit at 80.008°; 85° leaves 5° margin. A
  future scenario living at 85-95° will feel the ramp — by design.
- **Body under canopy keeps `-A_x`** (now signed, correct), evaluated at the frozen attitude.
  For a canopy deployed at a non-vertical attitude `f` may sit inside the ramp — physically fine.
- **Long demo flight** makes `run.py` plots ascent-squeezed (891 s x-axis) and App 4 ~3.7x
  slower. Accepted; B29/apogee-terminated mode mitigate.
- **Numerical pins are environment-sensitive** (D-77): re-record the Mach pin as a band, never a
  bit-exact value.

## 34.10 Implementation tickets (Steps 93-95)

Shape of §33.10. One step = one commit; full suite after each (background, ~5 min; baseline
**489/489**). Gate: suite green at the stated count; only the pins of §34.6 move; `git diff --stat`
inside the boundaries; no `dev/docs/latex/` file. Strictly sequential (shared test files):
`93 -> 94 -> 95`. Assignee: developer; `parallel_safe: false` throughout.

### [Step 93] Axial aero force opposes the relative flow (D-91, D-92, D-93, D-94a)

- **Files:** `sim/aero.py`, `sim/forces.py` (`aero_force_body` only), `tests/test_aero.py`,
  `tests/test_forces.py`, `tests/test_mach_warning.py`, `tests/test_dynamics.py` (append).
- **Spec:** §34.3, §34.4, §34.6.
- **Do:** `_COS_ALPHA0 = cos(radians(85.0))`; public `axial_flow_factor(alpha) = min(1, max(-1,
  cos(alpha)/_COS_ALPHA0))`; multiply it into `C_x` in `_constant_coeffs`/`_linearized_coeffs`;
  `_table_coeffs` multiplies by it only when `table.alpha[0] > -pi/2 and table.alpha[-1] < pi/2`;
  `A_brake *= aero.axial_flow_factor(flow.alpha)`. Update the three docstrings (cite D-91/§34.3).
  Re-record the Mach pin exactly as §34.6. New tests (TDD, red first): factor = 1.0 exactly at
  0/±85°, 0 at ±90°, -1 at ±95°/±180°, continuous across the ramp; `constant`/`linearized` body
  force at `alpha = π` points to the nose (`+x_r`); table at 180° flipped for `example.csv` and
  not flipped for a temp full-range table (write/clean like `test_bad_grid.csv`); airbrake term
  flips tail-first; demo without recovery: specific energy non-increasing after burnout and
  impact `|v| < sqrt(2 g h_apogee)` (measured 183.8 m/s < 341 m/s).
- **Check:** suite 489 + N new, only the Mach pin re-recorded; tilted pins in
  `test_integrate.py` untouched and green.
- **Commit:** `Step 93 (Phase 2.16): axial aero force opposes the relative flow (D-91)`

### [Step 94] Apogee-triggered recovery cannot arm on the pad (D-94b)

- **Files:** `sim/forces.py` (`parachute_deployed` only), `tests/test_dynamics.py` (append).
- **Spec:** §34.5 "Latent bug".
- **Do:** `if t < 0.1: return False` before the `y[VZ] > 0.0` test (apogee branch only; timer
  untouched), comment pointing at `_apogee_event`'s guard. Test: rest start, no rail, motor with
  T(0) = 0, `Recovery(model="deploy", trigger="apogee", S>0)` -> `events["parachute_deploy"]`
  equals `events["apogee"]` within 1e-6 s (was 0.0).
- **Check:** suite +1; no pin moves.
- **Commit:** `Step 94 (Phase 2.16): apogee-triggered recovery ignores the pad sag (D-94b)`

### [Step 95] The demo lands under a parachute (D-97) + stale comments

- **Files:** `configs/rockets/demo.py`, `configs/scenarios/demo.py`,
  `apps/cfd_conditions/select_conditions.py` (comment `:198-201`), `apps/airbrake_sizing/targets.py`
  (docstring note), `apps/airbrake_sizing/solve_cda.py` (`:31-35`, `_AFTER_APOGEE_REFUSAL` wording;
  keep the substring `after_apogee`), `tests/test_config_migration.py` (append).
- **Spec:** §34.5, §34.7.
- **Do:** the `Recovery(...)` and `solver=Solver(t_max=1200.0)` blocks of §34.5 verbatim with
  their comments; demo module docstrings: drop "Mach 2.6", state ascent peak ~Mach 1.75, add the
  dual-deploy caveat (B29). Test: demo lands — `events["ground"]` not None, impact `|v|` in
  [5.5, 6.5] m/s, `parachute_deploy == apogee` within 1e-6 s.
- **Check:** suite +1 (~+30 s runtime); measured impact 5.97 m/s at t ≈ 890.9 s; `python run.py`
  and `python run_airbrake.py` run clean.
- **Commit:** `Step 95 (Phase 2.16): the demo lands under a main canopy (D-97)`

Tracker (orchestrator): D-92..D-97, B27-B29, B17 closed, B23 unblocked.
