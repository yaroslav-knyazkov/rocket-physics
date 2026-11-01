# Architecture 38 — porting `fx27/simulation` onto rocket-physics `apps/`

## Кратко (RU)

- **Что это.** Скоупинг-тикет на перенос всего, что делает соседний проект `fx27/simulation`
  (построен на сторонней библиотеке `rocketpy`, точечно-массовая модель 3DOF), на собственную
  библиотеку `apps/` этого проекта — с теми же реальными данными ракет/моторов/стартовых площадок.
  Код не писался; это только проектирование, как architecture-37 для Step 32.
- **Главная развилка (SS38.3).** Как реализовать «точечную массу»: **A** — жёстко замороженная
  ориентация на существующем rigid-body решателе (`C_z=0, C_m=0, c_mq=0`), ноль нового кода;
  **B** — настоящий отдельный точечно-массовый решатель в движке; **C** — A плюс уже готовая
  диагностика Step 137 как измерительный инструмент погрешности. **Рекомендация — C.**
- **Важная поправка к постановке.** Gated Step 143 (`Option A` из task-136-137) — это НЕ то, что
  нужно для паритета с fx27: там замышлялся грубый аналитический gravity-turn (замкнутая форма, без
  кривой тяги, атмосферы и рельса). Настоящий паритет требует нового RHS в движке — задача
  крупнее Step 143 и сравнимая со Step 32. Выбор B не «разблокирует Step 143», а открывает новую,
  более дорогую работу.
- **Нужен ли Step/Phase.** При выборе A или C — **нет**: это чистый скриптинг в `projects/fx27/`,
  ни одна строка `apps/` не меняется. При выборе B — да, полноценный Step с тикетом и тест-гейтом.
- **Готовые куски apps/, которые закрывают fx27 почти целиком:** `apps/sim/schema.assemble`,
  `apps/sim/engine/integrate.run_sim`, `apps/_shared/flight_stats.flight_stats` (покрывает ВСЕ 8
  метрик fx27), `apps/optimization/airbrake_sizing/solve_cda.solve_airbrake` (аэротормоз — прямой
  вызов), `apps/optimization/motor_selection/scenario_sweep.sweep_scenario` (опционально для euroc).
  **Не подходят:** `compare_motors` и `trade_surface` — оба явно отказываются работать при
  включённой модели массы, а она для паритета с fx27 обязательна (SS38.4.2).
- **Бесплатный оракул валидации.** В `fx27/.../rockets_ideal.py` захардкожены уже решённые ответы
  (масса 4.2864 / 8.0654 кг, Cd 0.2351 / 0.8304 на цель 3000 м). Наши решатели должны воспроизвести
  их — это и есть критерий приёмки Option A/C, не «на глаз».
- **Данные.** 3 CSV помечены `-todo` (содержат `null`) — соответствующие 3 из 26 euroc-сборок
  выносятся в явный `DEFERRED` список, не выбрасываются молча. Отдельно: `projects/data/README.md`
  похоже случайно **перемещён** в `projects/fx27/data/README.md` (git: ` D projects/data/README.md`)
  — его надо вернуть, иначе исчезает единственное не-gitignored содержимое `projects/data/`.

---

## Table of contents

- [SS38.1 Scope and what "done" means](#ss381-scope-and-what-done-means)
- [SS38.2 Verification of the orchestrator's rocket-physics-side claims](#ss382-verification-of-the-orchestrators-rocket-physics-side-claims)
- [SS38.3 DECISION — how to realise "point mass" (`decision_required`)](#ss383-decision--how-to-realise-point-mass-decision_required)
- [SS38.4 Physics / configuration mapping fx27 -> rocket-physics](#ss384-physics--configuration-mapping-fx27---rocket-physics)
- [SS38.5 Deliverable-by-deliverable mapping (exhaustive)](#ss385-deliverable-by-deliverable-mapping-exhaustive)
- [SS38.6 Proposed layout under `projects/fx27/`](#ss386-proposed-layout-under-projectsfx27)
- [SS38.7 Data readiness, the three `-todo` motors, and a repo hygiene flag](#ss387-data-readiness-the-three--todo-motors-and-a-repo-hygiene-flag)
- [SS38.8 Does this need a Step / Phase number?](#ss388-does-this-need-a-step--phase-number)
- [SS38.9 Acceptance criteria](#ss389-acceptance-criteria)
- [SS38.10 Risk register](#ss3810-risk-register)
- [SS38.11 Tickets](#ss3811-tickets)
- [SS38.12 Open decisions for the user gate](#ss3812-open-decisions-for-the-user-gate)
- [SS38.13 Rejected options](#ss3813-rejected-options)

---

## SS38.1 Scope and what "done" means

Reimplement, inside this repository, every behaviour of `D:\Projects - Ongoing\fx27\simulation`,
using this project's own `apps/` library instead of `rocketpy`, against the same real
rocket / motor / launch-site data. The source project's inventory was supplied by the orchestrator
and is treated as ground truth here (it was read in full there); this document verifies only the
**rocket-physics side** against the actual code.

In scope:

1. Two real launch configurations, `cspace` and `euroc`, as rocket-physics `Scenario` literals.
2. A generic, launch-config-agnostic layer equivalent to fx27's `point/` package.
3. Six runnable entry points equivalent to fx27's `runs/` scripts.

Out of scope (explicitly):

- Any change to `apps/` **unless** the user picks Option B in [SS38.3](#ss383-decision--how-to-realise-point-mass-decision_required).
- Any change to `dev/docs/latex/` (project rule: edit on explicit request only). If Option B is
  picked, a LaTeX section for the new model becomes required and is a separate ticket.
- Re-pinning any existing numeric test.
- The 3 `-todo` motors (see [SS38.7](#ss387-data-readiness-the-three--todo-motors-and-a-repo-hygiene-flag)).

---

## SS38.2 Verification of the orchestrator's rocket-physics-side claims

Every claim below was checked against the code at `develop` (da388d6). Verdicts: **CONFIRMED**,
**CONFIRMED WITH ADDITION**, **CORRECTED**.

### SS38.2.1 `aero.py` `"constant"` model freezes attitude — CONFIRMED, and stronger than stated

`apps/sim/engine/aero.py:589` `_constant_coeffs` returns
`C_x = p.aero.C_x * axial_flow_factor(alpha)`, `C_z = p.aero.C_z`,
`C_m_code = _cm_to_code(p.aero.C_m, p)`, `C_mq_code = _cm_to_code(p.aero.c_mq, p)` —
alpha/Mach-independent except for the axial flow factor. Confirmed.

The attitude-freeze claim is not just "the aero moment is zero", it is **the total pitching moment is
identically zero**. `apps/sim/engine/dynamics.py:213-235` assembles
`M_y = cross_y(aB, thrust_body) + cross_y(aA, aero_force_body) + aero_moment_y`, with
`aA = [-l1_aero, p.lengths.u_B]` and `aB = [-(l1+l2), u_B - u_C]`. Given
`_cross_y(a, b) = -(a_x*b_z - a_z*b_x)`:

| term | value under the fx27 configuration | why zero |
|---|---|---|
| `cross_y(aB, thrust)` | `(u_B - u_C) * T` | `u_B = u_C = 0` (library defaults) and `misalign_deg = 0`, so `thrust_body = [T, 0]` |
| `cross_y(aA, aero_force)` | `-(l1_aero * A_z + u_B * (A_x + A_brake))` | `A_z = q*S*C_z = 0` because `C_z = 0`; `u_B = 0` |
| `aero_moment_y` | `-(q*S*d_ref*C_m_code + 0.25*rho*V*S*d_ref^2*omega*C_mq_code)` | `C_m = 0` and `c_mq = 0` make both terms exactly `0.0` (`forces.py:291-292`) |

So `omega_dot == 0.0` exactly for every state, and with `s0.omega = 0` (which `schema._pad_state`
sets) `theta` stays bit-exactly at `radians(site.rail_angle_deg)` for the whole flight —
ascent, apogee and descent. Three consequences worth knowing:

- `Lengths.l1` / `l2` are **dynamically inert** here (they only ever multiply `A_z == 0`). The demo
  file's "`0.0` is not usable" comment is about alpha-dependent models; for this port `l1`/`l2` can
  be any positive placeholder and they will not move a single digit of the trajectory.
- `Weight.I` (or the composed MOI with the mass model on) must still be **non-zero**, otherwise
  `omega_dot = M_y / I` is `0.0/0.0 = nan`.
- The quoted static margin is therefore meaningless for this port — see SS38.2.5.

### SS38.2.2 Frozen-axis force direction vs. true point mass — CONFIRMED, and it applies to thrust too

`apps/sim/engine/forces.py:169-244` `aero_force_body` returns `[-(A_x + A_brake), -A_z]` in **body
axes**, and its docstring is explicit that the force is deliberately *not* rotated through
`flow.u_hat`/`n_hat` (the relative-wind frame) — the alpha dependence lives in the coefficients, not
in the force direction. So under Option A the aerodynamic force points exactly along `-x̂_r`, i.e.
along the frozen body axis, with magnitude `q*S*C_x*axial_flow_factor(alpha)`. A true point-mass
model puts it along `-v̂`. Confirmed.

**Addition the orchestrator's note did not make:** the same is true of **thrust**. `thrust_body` is
along `+x̂_r` (modulated only by `misalign_deg`, zero here), whereas rocketpy's point-mass 3DOF
applies thrust along the velocity vector. So Option A differs from fx27 in *both* force directions,
not only drag. During boost this is the smaller of the two effects (see SS38.3.1) and is arguably
the physically *more* correct of the two conventions.

`axial_flow_factor` (`aero.py:162-184`) is exactly `1.0` for `|alpha| <= 85 deg`, `cos^2`-shaped
outside, `0` at `90 deg`, `-1` for `|alpha| >= 95 deg`. So the *magnitude* of the axial force is
bit-identical to a point-mass drag magnitude throughout the whole alpha range the ascent visits;
only the direction differs. This matters for the error estimate in SS38.3.1.

### SS38.2.3 `flight_stats.point_mass_flightpath` is a diagnostic, not a solver — CONFIRMED

`apps/_shared/flight_stats.py:294-420` reads everything off `result.raw.sol(t_grid)` of an
**already-completed** rigid-body run and re-evaluates `dynamics.derivatives`. Its own module header
(lines 235-247) states it is "NOT a new `State` component, NOT a new `p.solver.method`, NOT a change
to `apps/sim/engine/dynamics.py`". It cannot be repurposed as an alternative integrator: it has no
RHS, no state propagation, and its `theta_v_dot_pointmass` is a *prediction evaluated at the
rigid-body solution's own state*, not an integrated quantity.

It **can** be used as an error-measurement instrument, which is what Option C in SS38.3 proposes:

- `flight_path_angle(vx, vz)` (line 270) is public and vectorised — reusable directly for fx27's
  `theta(t)` plot panel, no new code.
- `still_air_residual = theta - alpha - theta_v` is an **exact identity** (0, not ≈0) with wind off,
  so `alpha(t) = theta_frozen - theta_v(t)` can be read off any run without recomputing it.
- `lambda_ratio` is `NaN` everywhere under `aero.model == "constant"` (documented at lines 334-348,
  and already observed by `tests/test_point_mass_flightpath.py`). **Do not expect `Lambda` to be a
  usable number for this port** — it needs an alpha-dependent aero model.

### SS38.2.4 `solve_cda.solve_airbrake` matches fx27's air-brake estimator — CONFIRMED, better behaviour

`apps/optimization/airbrake_sizing/solve_cda.py:425` `solve_airbrake(cfg: Config, spec:
AirbrakeSpec) -> AirbrakeSolution`. Mapping to fx27's `estimate_air_brake`:

| fx27 | rocket-physics | notes |
|---|---|---|
| `target_apogee_agl=2500` | `AirbrakeSpec.target_apogee_m=2500.0` | `apogee_for_cda` uses `gravity.altitude_agl`, already AGL — no manual elevation subtraction |
| `c_da_bracket=(0, 0.05)` | `AirbrakeSpec.cda_bounds=(0.0, 0.05)` | same meaning, user-supplied bound |
| `brake_c_d=1.0` | `AirbrakeSpec.cd_brake=1.0` | also the library default |
| `power_off_drag += C_DA/area` | `trigger="after_burnout"` + `control.airbrake_Cd`/`airbrake_S_max` | **semantically equivalent**: rocketpy uses `power_off_drag` only while the motor is *not* burning, i.e. from burnout onward; this project's `after_burnout` trigger is a pure onset latch from the burnout event onward |
| min brake area = `C_DA / brake_c_d` | `AirbrakeSolution.s_max_m2` (= `cda_airbrake / spec.cd_brake`, line 489) | identical formula |
| design area = `min * margin` | **not in `apps/`** | pure arithmetic, belongs in the `projects/` wrapper |
| per-panel = `design / brake_count` | **not in `apps/`** | ditto |
| raises if baseline apogee < target | `reachable=False` + clamp to the nearer bound + a loud named diagnostic (`print_solution`, lines 586-593) | **better**: reports the reachable range instead of throwing |
| `print_brake_report` | `print_solution` + the two extra lines above | fx27's exact text is not reproduced; the information is a superset |

`solve_airbrake` has **no `weight.m_d` guard** — it works with the mass model on, unlike
`compare_motors`/`build_surface`. `brake_overrides` only touches `control.airbrake_*`, so `weight`
and `s0` are untouched by the search. Verified by reading `apogee_for_cda` (line 191) and
`_solve_scalar` (line 250).

One **correction** to the orchestrator's "whether `cfg`/`spec` can be populated from a from-scratch
`Params`/`Config`": yes, trivially — `solve_airbrake` takes a `Config`, and `Config` is what
`apps.sim.schema.assemble(Scenario)` returns. Nothing in `solve_cda.py` references
`DEMO_SCENARIO` except its own `main()` CLI (line 674), which is not on the call path.

### SS38.2.5 `_margins` / static margin is a fabricated number for this port — NEW FINDING

`scenario_sweep._margins` (line 241) calls `report.static_margin_cal` (line 136), which for a
`"constant"`-model config with no `aero.l_p` returns `margin(t) = l1(t) / d_ref` — i.e. **the
placeholder `Lengths.l1` divided by the body diameter**. fx27 carries no fin/CP geometry at all, so
there is no honest `l1` to supply. Consequences for the port:

- `SweepRow.margin_rail_exit` / `margin_burnout` / `margin_min` must be read as "not available", and
- `Constraints.min_margin_cal` (default `1.0`) would mark rows `INFEASIBLE: static_margin` on a
  fabricated figure. If `sweep_scenario` is used (SS38.5.3 variant B) it **must** be called with
  `Constraints(min_tw=0.0, min_margin_cal=-math.inf)` and that fact printed above the table.

### SS38.2.6 `compare_motors.MotorEntry.overrides` can vary dry mass — CONFIRMED, but the app is still unusable here

The orchestrator's doubt is resolved in the *affirmative*: `MotorEntry.overrides` (line 122) is an
open dict of dotted `Params` paths and `build_params` merges it into one `params_replace` call, so
`{"weight.m": 5.636}` is legal. euroc's "both motor and dry mass vary" shape fits
`MotorEntry` on paper.

**But `compare_motors` is nevertheless the wrong tool**, for a reason that outranks it:
`compare_motors` (line 190) raises `ValueError` if `baseline.weight.m_d is not None`, i.e. it
**refuses any baseline with the mass model on** — and the mass model must be on for fx27 parity
(fx27's `PointMassMotor` carries `propellant_initial_mass` and depletes it; propellant is 1-5 kg of
a 6-10 kg vehicle, see SS38.4.2). The same guard exists in
`apps/analysis/weight_aero_tradeoff/trade_surface.build_surface` (line 224). Both are
constant-mass studies by design (D-82). Neither can be used for this port.

The usable per-scenario path is `apps/optimization/motor_selection/scenario_sweep.py`, which
re-`assemble()`s per motor (`evaluate_motor`, line 265: `dataclasses.replace(scenario, motor=motor)`
-> `assemble(sc)` -> `run_sim(p, cfg.s0)`) and therefore gets a correct `s0.m` and a correct derived
`weight` group for every row. It has no `m_d` guard.

**Correction to the orchestrator's framing** of `scenario_sweep` as "a general root-finding-against-
target-apogee pattern items 3/4 could reuse": it is **not** a root finder. `target` is only a
**ranking key** (`_rank_key`, line 326: feasible first, then `|h_apogee - target|`). It enumerates a
caller-supplied motor list. There is no scalar search in it at all.

### SS38.2.7 There is no reusable apogee-target root finder in `apps/` — NEW FINDING

The only root-find-to-a-target-apogee machinery in the repo is `solve_cda._solve_scalar`
(line 250) — private, and coupled to the airbrake objective's return shape
`(apogee|None, Result, Params)` plus an `AirbrakeSpec` it reads only for a diagnostic message. So
fx27's `mass_estimation.estimate_mass` and `drag_estimation.estimate_drag` have **no existing
counterpart**: `trade_surface` is a 2-D *grid sweep* with bilinear interpolation and exchange rates,
not a 1-D solve, and it refuses the mass model on.

Those two therefore need a ~40-line `scipy.optimize.brentq` objective in `projects/fx27/` — which is
exactly what fx27 itself does (it calls `brentq` directly). See SS38.5.4 and B-NN-1 in SS38.11.

### SS38.2.8 `Motor` fields needed for a header-less `.csv` — CONFIRMED, with a concrete recipe

`apps/sim/engine/motor_file.py:95-132` `_read_csv` skips blank rows and rows whose first cell starts
with `#`, then parses `float(row[0])`, `float(row[1])`; every metadata field of the returned
`MotorRecord` is `None`. The fx27 CSVs are bare `time, thrust` with no comment line at all — they
parse. (Confirmed on `projects/fx27/data/motors/cspace/pro54-2060K570.csv`.)

With `mass_model != "none"`, `schema._weight_from_pieces` (line 452) resolves every `None` `Motor`
field from the record's header — which does not exist for a `.csv`. The orchestrator asked whether
`m_total`/`m_prop` must be supplied explicitly: **yes, and so must more.** Reading the function
line-by-line, the minimal non-crashing set for a header-less CSV with `mass_model="endpoints"` is:

```
Motor(
    name=...,
    thrust=Thrust(motor_curve=<abs path to .csv>),
    mass_model="endpoints",       # derives I_sp = J/(m_prop*g0) from the curve itself
    m_total=<dry_mass + propellant_initial_mass>,   # REQ: no header to read it from
    m_prop=<propellant_initial_mass>,               # REQ: ditto
    l_case=0.0, l_prop=0.0, I_case=0.0, I_prop0=0.0,   # REQ: see below
)
```

`length` and `diameter` stay `None` and are **never dereferenced** provided (a)
`Sections.l_motor_fwd` is given rather than `l_motor_aft` (line 567 computes
`l_motor_aft - length` otherwise), and (b) all four of `l_case`/`l_prop`/`I_case`/`I_prop0` are
given explicitly, so the `length/2.0` and `mass.uniform_cylinder_I(m, length, diameter)` defaults
(lines 545-556) are not taken. Supplying them all as `0.0`, together with `Airframe.l = 0.0` and
`Sections.l_motor_fwd = 0.0`, collapses every longitudinal station to the origin.

**This "zero-geometry" trick is sound here for exactly one reason**, and it must be written into the
config's own docstring: the total pitching moment is identically zero (SS38.2.1), so no station and
no MOI split can influence the trajectory. `Airframe.I` must still be `> 0` (SS38.2.1). The trick
would be **wrong under any alpha-dependent aero model** — if someone later switches these scenarios
to `"linearized"`/`"table"`, the collapsed stations become a silent physics bug. Flag in the file.

The alternative is to invent plausible geometry (nose-to-CoG ~0.6 L, motor aft-flush). It is
inert either way; "zero and documented as inert" is the more honest of the two, and it cannot be
mistaken for measured data.

### SS38.2.9 Metric coverage — `FlightStats` covers all eight fx27 metrics

`apps/_shared/flight_stats.py:71-92`:

| fx27 `flight_metrics` key | rocket-physics | source |
|---|---|---|
| `apogee_agl` | `FlightStats.apogee_altitude` | already AGL (`gravity.altitude_agl`, accounts for `site.h0_m`) — fx27's manual `- elevation` is not needed |
| `apogee_time` | `FlightStats.apogee_time` | event time |
| `max_speed` | `FlightStats.max_velocity` | ascent-window `|v|` (D-19) |
| `max_acceleration` | `FlightStats.max_accel` (+ `max_accel_g`) | exact, from re-evaluated `dynamics.derivatives` (D-20), gravity included (D-21) |
| `max_mach` | `FlightStats.max_mach` | ascent-window flow Mach |
| `out_of_rail_velocity` | `FlightStats.rail_exit_speed` | `None` when `site.L_rail == 0` |
| `mass` (dry) | `Rocket.airframe.m` / `Params.weight.m_d` | config value, not a flight reduction |
| `total_mass` (wet) | `Params.weight.m` | ditto |

`FlightStats` additionally gives `avg_velocity`, `max_q`, `total_impulse`, `burnout_time`,
`impact_time`, `downrange_impact` — a strict superset. The launch rail is really modelled
(`dynamics.on_rail`/`_e_rail`, lines 249-269; `integrate._rail_exit_event`), so `rail_exit_speed` is
a physical rail-exit speed, not a proxy.

Note on windows: fx27 runs with `terminate_on_apogee=True`, so **every fx27 number is an
ascent-window number**. `flight_stats`' own D-19 ascent-only window is the same choice, arrived at
independently. This is load-bearing for the error estimate in SS38.3.1.

---

## SS38.3 DECISION — how to realise "point mass" (`decision_required`)

**Purpose of the component:** a trajectory model that reproduces what fx27's
`rocketpy.Flight(simulation_mode="3 DOF")` produced for the same vehicle/motor/site data, so the
ported comparison tables, estimators and plots are about the same physics the user has been looking
at in the sibling project.

**The constraint that makes this a real fork:** this project has no point-mass solver. Its 2D/3D
engine always carries an attitude state. The nearest thing on the roadmap, **Step 143, is GATED and
not started** (`dev/status.json`, stage 2.17 `next`: "GATED Step 143 (standalone estimator, Option A
— перенумерован с 138, см. D-169; не начат, требует отдельного запроса пользователя").

### SS38.3.0 First, a correction that changes the shape of the fork

The orchestrator framed Option B as "implement Step 143 for real". **Step 143 would not give fx27
parity.** Reading its own scope
(`dev/docs/task-136-137-point-mass-flight-path-angle.md:472-484`, ticket `[TBD-2]` at line 564):

> Option A — new standalone analytic module `apps/analysis/point_mass/`. A small, self-contained
> closed-form propagator: integrate `eq:flightpath_rate` + `eq:speed_rate` (or evaluate the closed
> form `eq:gravity_turn_closed`) for fast trade-study estimates […] **Cost:** ~1 module + 1 test
> file; no engine change.

That is a **crude analytic gravity-turn estimator** — no thrust curve, no ISA/sounding atmosphere,
no launch rail, no propellant depletion, no airbrake, no recovery. fx27's rocketpy 3DOF is the
opposite: a *full* simulator (real thrust curve, real atmosphere, real rail, real mass depletion)
that merely has no attitude DOF. So:

- Step 143 is **cheap but insufficient** for this port.
- Real parity needs a **new RHS inside the engine** where the aerodynamic force and the thrust act
  along `∓v̂` instead of `∓x̂_r`. That is a different, larger piece of work than Step 143, and
  choosing it does not "unblock" the gated step — it opens a new one.

The options below are therefore restated on that basis.

### SS38.3.1 Quantifying Option A's error, since the recommendation hinges on it

Option A's only difference from a true point mass is **force direction**, not magnitude
(SS38.2.2: `axial_flow_factor == 1.0` exactly for `|alpha| <= 85 deg`). In still air the frozen
attitude gives the alpha history exactly:

```
alpha(t) = theta_rail - theta_v(t),    theta_v(t) = atan2(-vz, vx)
```

For an 85 deg (cspace) / 84 deg (euroc) rail, `theta_v` starts at the rail angle and decays to
**exactly 0 at apogee** (apogee is where `vz = 0`), so `alpha` sweeps 0 -> ~85 deg over the ascent.
That looks alarming until the dynamic pressure is put next to it. Order-of-magnitude, for a
representative 3 km-class flight (`V_burnout ~ 300 m/s`, `theta_rail = 85 deg`, drag-free coast for
the estimate, `v_horizontal ~ 300*cos(85°) ~ 26 m/s` roughly preserved):

| phase | `alpha` | `V` | `q/q_burnout` | along-path drag deficit `1-cos(alpha)` | product |
|---|---|---|---|---|---|
| rail exit -> burnout | 0-3 deg | 30 -> 300 m/s | 0.01 -> 1.0 | <0.002 | ~0.002 |
| early coast (`theta_v` 85->75 deg) | 3-10 deg | 300 -> 101 m/s | 1.0 -> 0.11 | <0.015 | ~0.002 |
| mid coast (75->60 deg) | 10-25 deg | 101 -> 52 m/s | 0.11 -> 0.03 | 0.015-0.09 | ~0.003 |
| late coast (60->0 deg) | 25-85 deg | 52 -> 26 m/s | 0.03 -> 0.008 | 0.09-0.91 | ~0.005 |

The large-`alpha` region is exactly the low-`q` region: at apogee `q` is ~0.5-1 % of its
burnout value, so the drag force there is negligible regardless of which direction it points. The
spurious *normal* component (`sin(alpha) * A_x`, which in Option A points below the flight path and
so slightly *increases* the gravity turn) peaks at ~1-2 N against a ~55 N weight, for ~4 s.

**Estimate: apogee agreement with a true point mass within ~0.5 %** (order 5-15 m on 3000 m) for
these near-vertical, no-wind, terminate-at-apogee configurations. `max_speed`, `max_accel`,
`max_mach` and `rail_exit_speed` all occur at or before burnout where `alpha <= 3 deg`, so those are
expected to agree to **better than 0.2 %**.

This is an estimate, not a measurement, and it is **explicitly listed as a numeric check in the
implementation ticket** (SS38.9 AC-3). Crucially, the check does not need a reference implementation
to be built: **fx27 has already hardcoded the answers.** `cspace/rockets_ideal.py` carries the
*solved outputs* of its own mass/drag estimators as rocket literals:

| fx27 solved value | meaning | our solver must reproduce |
|---|---|---|
| `pro54_transition_ideal_mass` mass = **4.2864 kg** | dry mass for 3000 m AGL | `estimate_airframe_mass(pro54_transition, 3000)` |
| `pro54_transition_ideal_drag` drag = **0.2351** | constant `C_D` for 3000 m AGL | `estimate_cx(pro54_transition, 3000)` |
| `pro75_ideal_mass` mass = **8.0654 kg** | dry mass for 3000 m AGL | `estimate_airframe_mass(pro75, 3000)` |
| `pro75_ideal_drag` drag = **0.8304** | constant `C_D` for 3000 m AGL | `estimate_cx(pro75, 3000)` |

Four independent cross-validation points against the rocketpy point-mass model, for free, with no
rocketpy dependency and no new code. That is the acceptance oracle for Option A/C. Note the
*sensitivity* amplification: a 0.5 % apogee error near the root maps to roughly a 1-3 % error in the
solved mass or `C_D` (the apogee is far more sensitive to those than linearly), so the acceptance
band should be stated as **within 5 % of the fx27 figure**, not 0.5 %.

### SS38.3.2 The options

| # | Option | Pros | Cons | Cost |
|---|---|---|---|---|
| **A** | **Frozen-attitude rigid body.** `aero.model="constant"`, `C_z=0`, `C_m=0`, `c_mq=0`, `u_B=u_C=0`, `misalign_deg=0`, `s0.omega=0`. Attitude provably frozen at the rail angle (SS38.2.1). | Zero new `apps/` code, zero engine risk, zero pin risk, no Step/Phase needed. Reuses the real thrust curve, real ISA with site elevation, real rail, real mass depletion, real airbrake term — i.e. everything that made fx27's model a *full* simulator. Error confined to force direction, concentrated where `q` is negligible (SS38.3.1). | Not literally point-mass physics; drag and thrust act along a frozen axis, not along `∓v̂`. Divergence grows with the launch-angle-to-flight-path-angle gap, so it would be a poor choice for a low-inclination or windy case. The error is *estimated*, not measured, until AC-3 runs. | **0 lines in `apps/`.** Part of the `projects/fx27/` work that has to happen under any option. |
| **B** | **New true point-mass solver path in the engine.** A new RHS (e.g. `Aero.force_frame = "velocity"` + a matching thrust frame, or a separate 4-state point-mass integrator) where both aero force and thrust act along `∓v̂` and `theta` is either absent or diagnostic-only. | Genuine physics parity with fx27/rocketpy; permanently useful as a cheap fast mode and as a validation oracle for the rigid-body model; closes a real capability gap (the repo currently cannot answer "what does a point mass do?" except diagnostically). | **Does not reuse Step 143** (SS38.3.0) — Step 143 is a different, cruder thing; picking B opens new work rather than unblocking gated work. Touches `forces.py`/`dynamics.py`/`integrate.py` — the files carrying this project's bit-for-bit numeric pins (`tests/test_integrate.py`, `np.array_equal`). Needs its own ticket, test gate, `code-review`, QA, and a LaTeX model section (`dev/docs/latex/` is edit-on-request, so that is a second explicit permission). Adds "a second trajectory model in the tree" — exactly the "which one is right?" confusion the Step 143 ticket itself warned about (`task-136-137…md:481-483`). Blocks the fx27 port behind a multi-day engine change. | **~400-700 insertions** in 3-4 engine files + 1-2 new test files + pin-protection work. For calibration: **Step 32 was 1706 insertions / 5 engine files / 4 test files / a 58 KB architecture doc**. So: clearly bigger than Step 143 (~1 module + 1 test), roughly **half to two-thirds of Step 32**. Plus the LaTeX ticket. |
| **C** | **A + the existing Step-137 diagnostic as the measuring instrument** (RECOMMENDED). Run Option A, then on every flight call `flight_stats.point_mass_flightpath(result, p)` and report, per scenario: `max|alpha|` restricted to samples where `q > 0.01*q_max`, the `alpha` at burnout, and the `still_air_residual ≡ 0` identity check. Publish these alongside every table. Gate acceptance on the four fx27 ideal-mass/ideal-drag numbers (SS38.3.1). | Everything A has, plus the approximation stops being an unquantified assumption: each run carries a printed, per-scenario measurement of *how far from point-mass this flight actually is*, in the one window where it can matter. Uses only already-shipped, already-tested public functions (`point_mass_flightpath`, `flight_path_angle`) — still **zero `apps/` change**. Gives the user the evidence to decide whether B is ever worth buying. | Still not true point-mass physics. The diagnostic costs one extra dense-grid pass per flight (~2000 `dynamics.derivatives` re-evaluations) — noticeable on a 26-scenario sweep, so it should be opt-in per run script. `lambda_ratio` will be `NaN` throughout (SS38.2.3) and must be suppressed from the report rather than printed as a blank column. | **0 lines in `apps/`.** ~40 extra lines in `projects/fx27/point/`. |
| D | *(considered and rejected)* Tiny time steps / "let the frozen axis catch up". | — | **Not real.** The frozen-axis divergence is a **model** difference (the force points along the wrong unit vector), not a discretisation error, so it does not shrink as `dt -> 0`. Refuting this explicitly because it is an attractive-looking non-solution. | n/a |

**Recommendation: Option C.**

Reasoning, in order of weight:

1. **The error estimate and the validation oracle both point the same way.** fx27's own hardcoded
   solved figures (SS38.3.1) let us *prove* Option A is good enough for these specific
   configurations before committing to anything. If the four numbers come out within 5 %, Option B
   buys nothing the user can see.
2. **The divergence region is out of scope by construction.** fx27 runs
   `terminate_on_apogee=True`, and `flight_stats` is ascent-window by D-19. The place where the
   frozen axis is badly wrong — descent — is not in any fx27 metric or plot.
3. **Option B's gate was opened for a different reason.** Step 143 was gated pending "a separate
   user request" about a *paper/trade-study estimator*. Reopening it for a port of a sibling
   project's scripts conflates two unrelated decisions, and (SS38.3.0) would not even satisfy this
   one.
4. **C is honest where A alone is not.** A frozen-attitude run that *silently* claims to be a point
   mass is the kind of thing this project's own conventions audit exists to prevent. C makes the
   approximation a printed number on every table.

If the user wants true point-mass physics as a capability in its own right (not just for this port),
that is a legitimate separate request: scope it as its own Phase ticket after the port lands, with
Option C's measured `max|alpha| @ q>1%` figures as the evidence for whether it is worth the engine
risk.

---

## SS38.4 Physics / configuration mapping fx27 -> rocket-physics

Everything in this section assumes Option A or C from SS38.3. Under Option B the force-frame fields
change but the rest of the mapping stands.

### SS38.4.1 Per-group mapping

| fx27 (rocketpy) | rocket-physics | value notes |
|---|---|---|
| `Environment(latitude, longitude, elevation)` | `LaunchSite(site=Site(lat0_deg, lon0_deg, h0_m))` | cspace `(43.218, -0.047, 428.96)`; euroc `(39.3897, -8.2890, 160.0)` |
| `rail_length` | `Site.L_rail` | cspace `5.0`; euroc `12.0` |
| `inclination` | `Site.rail_angle_deg` | cspace `85.0`; euroc `84.0`. Both are "elevation from horizontal", same sense |
| `heading` | `Site.azimuth_deg` | cspace `0.0`, euroc `133.0`. **Must be set explicitly** — the library default is `90.0`, not `0.0`. Purely cosmetic in a 2D no-wind run |
| default ISA environment | `Weather(atmosphere=Atmosphere(model="isa", humid_air=False, dT_K=0.0), wind=Wind(model="none"), soundings=Soundings())` | ISA with site elevation handled by `atmosphere` via `h0_m` (`atmosphere.py:13`) |
| `PointMassRocket(radius=0.040)` | `Aero.S = pi*0.040**2 = 0.005026548`, `Aero.d_ref = 0.080` | rocketpy's `radius` is the body radius; reference area is `pi*r^2` |
| `power_off_drag` / `power_on_drag` (both constant, equal) | `Aero.model="constant"`, `Aero.C_x = 0.5` | this project has **one** axial coefficient, not a burn/coast pair. fx27 sets both to the same constant everywhere, so nothing is lost. If a future fx27 config splits them, this project cannot express it without a new field — flag, do not silently average |
| `PointMassRocket(mass=<dry>)` | `Airframe.m` | airframe mass, motor excluded — the same meaning rocketpy's `mass` has |
| (no MOI in a point-mass rocket) | `Airframe.I` | must be `> 0` (SS38.2.1). Use a plausible placeholder (e.g. `0.5` kg·m²) and comment it as **dynamically inert** |
| `PointMassMotor(thrust_source=<csv>)` | `Motor(thrust=Thrust(motor_curve=<path>))` | CSVs parse verbatim (SS38.2.8) |
| `PointMassMotor(dry_mass, propellant_initial_mass)` | `Motor(mass_model="endpoints", m_total=dry+prop, m_prop=prop, l_case=0.0, l_prop=0.0, I_case=0.0, I_prop0=0.0)` + `Sections(l_motor_fwd=0.0)` + `Airframe(l=0.0)` | the zero-geometry recipe, SS38.2.8. `"endpoints"` derives `I_sp` from the curve's own total impulse — no hand-entered `I_sp` to get wrong |
| `Flight(terminate_on_apogee=True)` | nothing — apogee is a non-terminal event; set `Recovery(model="none")` and `Solver(t_max=...)` | every fx27 metric is ascent-window (D-19) so the descent is simply ignored. `t_max` must be large enough for the apogee event to be *reached*; `flight_stats` tolerates `events["ground"] is None` (line 148) |
| `Flight(max_time=100)` | `Solver(t_max=...)` | fx27's 100 s is enough only because it terminates at apogee. Use `Solver(t_max=300.0)` (library default) and verify the apogee event fires for every scenario; raise it for the big pro98 rows if needed |
| (rocketpy picks its own integrator) | `Solver(method="RK45", rtol=1e-8, atol=1e-10)` | library defaults; do **not** set `sample_rate_hz` (it would trip `_assert_derivatives_reconstructible` in `flight_stats`, `solve_airbrake`, and `point_mass_flightpath`) |
| `Lengths` | `Lengths(l1=<placeholder>, l2=<placeholder>)` | dynamically inert (SS38.2.1). Comment as such. Feeds only the meaningless static margin (SS38.2.5) |

### SS38.4.2 The mass model must be ON — and that is what rules out two apps

fx27's `PointMassMotor` carries `propellant_initial_mass` and rocketpy depletes it over the burn.
For these vehicles the propellant is a large fraction of the total (e.g. cspace `pro54_transition`
dry 5.835 kg against a 2060 N·s K-class motor; euroc airframes 5.6-7.5 kg against motors up to
19 kN·s N-class). Running constant-mass would be a gross divergence, not a refinement — so
`Motor.mass_model` must be `"endpoints"` (or `"isp"`), i.e. `Params.weight.m_d is not None`.

Direct consequences, all verified in SS38.2.6:

- `apps/optimization/motor_selection/compare_motors.compare_motors` — **refuses** (`ValueError`,
  D-82). Not usable.
- `apps/analysis/weight_aero_tradeoff/trade_surface.build_surface` — **refuses** (same guard). Not
  usable.
- Any `params_replace`-based mass or `C_x` override on an already-assembled `Config` is **unsafe for
  mass**: `assemble` derives `weight` from the pieces and seeds `s0.m` from `weight.m` (lines
  378, 433-434). Changing `weight.m` after the fact leaves `s0.m` stale. **Therefore every
  mass-varying objective must go back through `Scenario` -> `assemble`,** not through
  `params_replace`. (`C_x` is safe to override either way — it is not derived and does not feed
  `s0`; `Scenario.overrides` is the tidier route and is what the estimators below use.)
- `apps/optimization/motor_selection/scenario_sweep.{evaluate_motor,sweep_scenario}` — **fine**,
  they re-`assemble()` per motor.
- `apps/optimization/airbrake_sizing/solve_cda.solve_airbrake` — **fine**, no guard, and its
  overrides touch only `control.airbrake_*`.

### SS38.4.3 Motor-file path resolution

`apps/sim/engine/datafiles.resolve` (3 rules): absolute -> as-is; contains a separator -> resolved
against **`os.getcwd()` at call time**; bare name -> `projects/examples/data/<kind>/`.

`projects/fx27/data/README.md` documents the cwd-relative form
(`"projects/data/motors/<campaign>/<file>"`). That works only when cwd is the repo root. For a
config literal that is a silent foot-gun. **Use rule 1 instead**: compute the absolute path at
import time from the module's own location, in one place:

```python
# projects/fx27/_paths.py
from pathlib import Path
_HERE = Path(__file__).resolve().parent
MOTORS_CSPACE = _HERE / "data" / "motors" / "cspace"
MOTORS_EUROC  = _HERE / "data" / "motors" / "euroc-sweep"
```

and then `Thrust(motor_curve=str(MOTORS_CSPACE / "pro54-2060K570.csv"))`. One module owns the
anchor; no config literal depends on cwd. This is a deliberate, documented deviation from the
README's convention and the reason goes in `_paths.py`'s docstring.

### SS38.4.4 Expected `MachRangeWarning` noise — not a bug

`apps/sim/engine/mach_warning.py` fires one `MachRangeWarning` per `run_sim` whose peak Mach exceeds
0.8 under `aero.model in ("constant", "linearized")`. Several euroc rows (pro98 M/N-class on a 6-7 kg
airframe) will comfortably exceed Mach 1. fx27 had the identical modelling defect — a constant
`C_D = 0.5` through the transonic region — it just had nothing to warn about it. So:

- The warnings are **correct and should not be suppressed globally**.
- The comparison run scripts should collect them and print a single summary line
  ("N of M scenarios exceeded Mach 0.8 under a Mach-independent drag model; those apogees are
  not credible") rather than emitting 26 separate warnings into the table.
- Record as a known limitation inherited from fx27, with `aero.model="table"` as the upgrade path if
  the user ever supplies Mach-dependent `C_A` data. This is a **real** accuracy caveat, larger in
  magnitude than Option A's frozen-attitude error (SS38.3.1) — worth saying out loud, since it means
  the point-mass-vs-frozen-attitude question is *not* the dominant error term in this port.

---

## SS38.5 Deliverable-by-deliverable mapping (exhaustive)

Legend for the **Verdict** column:

- **(a)** direct call into an existing `apps/` function — named.
- **(b)** thin new wrapper/script under `projects/fx27/` composing existing functions — **no `apps/` change**.
- **(c)** needs new reusable code in `apps/` — named, with size.

### SS38.5.0 Summary table

| # | fx27 deliverable | Verdict | Where |
|---|---|---|---|
| 1 | `point/core.build_flight` | **(a)** | `schema.assemble` + `integrate.run_sim` |
| 2 | `point/core.flight_metrics` | **(a)** | `flight_stats.flight_stats` + 2 config reads |
| 3 | `point/flight.run` | **(b)** | `projects/fx27/point/flight.py`, ~15 lines |
| 4 | `point/mass_estimation.estimate_mass` | **(b)** | `projects/fx27/point/estimate.py`, ~45 lines (`brentq`) |
| 5 | `point/drag_estimation.estimate_drag` | **(b)** | same file, ~25 lines (shares the solver) |
| 6 | `point/air_brake_size_estimation` | **(a)** + **(b)** | `solve_cda.solve_airbrake` + ~30 lines of margin/panel arithmetic |
| 7 | `point/point_comparison.evaluate_rockets` + `print_table` | **(b)** | `projects/fx27/point/comparison.py`, ~70 lines |
| 8 | `point/point_comparison.plot_displacement_comparison` (2x2) | **(b)** | `projects/fx27/point/plots.py`, ~90 lines |
| 9 | `point/point_comparison.plot_kinematics_comparison` (2x3) | **(b)** | same file, ~110 lines |
| 10 | `_variant_style` / `_family_colors` | **(b)** | same file, ~30 lines, copied verbatim in spirit |
| 11 | `runs/cspace/point.py` (single flight + info + 3D plot) | **(a)** + **(b)** | `report.print_run_summary` + `plotting.plot_trajectory`/`plot_time_histories` |
| 12 | `runs/cspace/point_comparison.py` (7 rockets, table + 2 plots) | **(b)** | composes #7-#10 |
| 13 | `runs/cspace/ideal_mass_estimation.py` (2 rockets) | **(b)** | composes #4 |
| 14 | `runs/cspace/ideal_drag_estimation.py` (2 rockets) | **(b)** | composes #5 |
| 15 | `runs/cspace/air_brake_estimation.py` (4 ideal rockets) | **(b)** | composes #6 |
| 16 | `runs/euroc/point_comparison.py` (27 -> 24 combos; corrected from an earlier 26/23 miscount, see implementation notes) | **(b)** | composes #7; `sweep_scenario` as an optional richer variant |
| 17 | cspace / euroc `launch_data.py`, `motors.py`, `rockets.py`, `rockets_ideal.py` | **(b)** | `Scenario`/`Rocket`/`Motor`/`LaunchSite`/`Weather` literals |
| 18 | `point/` package as a whole | **(b)** | **nothing in it needs to live in `apps/`** — see SS38.5.8 |

**Total `apps/` changes required: zero** (under Option A/C).

### SS38.5.1 Single flight + metrics (#1, #2, #3, #11)

**(a)** `apps.sim.schema.assemble(scenario) -> Config`, then
`apps.sim.engine.integrate.run_sim(cfg.params, cfg.s0) -> Result`. That is fx27's `build_flight`
in two calls; `rail_length`/`inclination`/`heading` are not arguments here because they live on the
`LaunchSite` piece (SS38.4.1), which is the better factoring.

**(a)** `apps._shared.flight_stats.flight_stats(result, p) -> FlightStats` is fx27's
`flight_metrics` with all 8 keys covered (SS38.2.9). The two non-flight keys (`mass`, `total_mass`)
read straight off `cfg.params.weight.m_d` / `cfg.params.weight.m`.

**(b)** `projects/fx27/point/flight.py::run(scenario) -> (Config, Result, FlightStats)` — a ~15-line
convenience that does the three calls and nothing else, so every run script and every estimator
objective shares one entry.

For #11's `flight.info()` equivalent: **(a)** `apps.sim.engine.report.print_run_summary(result, p,
s0)`. For `flight.plots.trajectory_3d()`: this project's 2D model has no 3D trajectory —
`plotting.plot_trajectory_3d` requires a 13-state `run_sim_3d` result. **Substitute**
**(a)** `plotting.plot_trajectory(result)` (downrange vs altitude) + `plotting.plot_time_histories(
result)` (altitude/speed/pitch/pitch-rate 2x2). Note in the run script that the 3D figure is not
reproduced because the model is planar and, with no wind, the fx27 flight was planar too — the 3D
plot there showed a straight line in a vertical plane and carried no extra information.

### SS38.5.2 cspace 7-rocket comparison table (#7, #12)

**(b)** `projects/fx27/point/comparison.py::evaluate_scenarios(scenarios: dict[str, Scenario]) ->
list[Row]` — a loop over `point.flight.run`, one `Row` per scenario holding the fx27 column set
(`name, mass, total_mass, apogee_agl, apogee_time, max_speed, max_acceleration, max_mach,
out_of_rail_velocity`), plus `print_table` in the house fixed-width style
(`compare_motors.print_motor_table` / `scenario_sweep.print_table` are the models to imitate —
copy the formatting idiom, not the code, since the column sets differ).

Explicitly **not** `compare_motors.compare_motors` — it refuses a mass-model-on baseline
(SS38.2.6/SS38.4.2). This is the single most important "don't reuse that" in the ticket.

The 7 rows are the 3 base rockets + the 4 `rockets_ideal` variants. The 4 ideal variants are
`Scenario` literals derived from their base by overriding one field:

- `*_ideal_mass` -> `dataclasses.replace(rocket, airframe=replace(airframe, m=<solved>))`
- `*_ideal_drag` -> `Scenario(..., overrides={"aero.C_x": <solved>})`

and their names must keep fx27's `"<family> (ideal mass)"` / `"<family> (ideal drag)"` suffix
convention, because that string **is** the plot-styling protocol (#10).

### SS38.5.3 euroc 27-combo comparison table (#16)

24 runnable combos, 3 deferred (SS38.7). **Correction, implementation phase:** this section
originally said 26 total / 23 runnable, an orchestrator miscount against the real fx27 source
(`data/euroc/rockets.py`'s `ROCKET_CONFIGS`, which lists 27 (config, motor) pairs). The developer
built against the real on-disk data (27 CSVs under `projects/fx27/data/motors/euroc-sweep/`) and
flagged the mismatch rather than silently following the wrong prose figure -- `DEFERRED_MOTORS` is
the same 3 named `-todo` motors either way, so this was a prose-accuracy issue only, not a spec
conflict.

**Variant A (recommended, primary):** **(b)** the *same* `evaluate_scenarios` loop as cspace, fed a
dict built by `projects/fx27/euroc/scenarios.py::generate_scenarios()` which produces one `Scenario`
per `(airframe_config, candidate_motor)` pair, named `"<config>/<motor>"`. One code path for both
campaigns, matching fx27's own single `evaluate_rockets`, and the column set stays fx27's.

**Variant B (optional extra run script, maximum apps reuse):** **(a)**
`apps.optimization.motor_selection.scenario_sweep.sweep_scenario(scenario, motors)` once per
airframe config (12 calls), concatenating `SweepResult.rows` and handing the flat list to
`scenario_sweep.print_table`. This reuses the existing ranking, CSV writer and overlay plot and
gives a *richer* table (`J_total`, `t_burn`, `T/W`, `q_max`, `m_burnout`). Two conditions:

1. Call it with `Constraints(min_tw=0.0, min_margin_cal=-math.inf)` — the default
   `min_margin_cal=1.0` would stamp `INFEASIBLE: static_margin` on a fabricated figure
   (SS38.2.5). Print why, above the table.
2. Motor `name`s must be globally unique if rows from several calls are merged (`sweep_scenario`
   raises on duplicates *within* a call; across calls the collision is silent in
   `SweepResult.results`). Name the `Motor` pieces `"<config>/<motor>"`.

Recommend shipping Variant A as `runs/euroc_comparison.py` and Variant B as
`runs/euroc_sweep.py`, clearly labelled as the richer-but-different-columns view.

### SS38.5.4 Mass estimation (#4, #13) and drag estimation (#5, #14)

**(b)**, ~70 lines total in `projects/fx27/point/estimate.py`. No existing `apps/` function does a
1-D solve to a target apogee (SS38.2.7).

```
estimate_airframe_mass(scenario, target_apogee_agl=3000.0, mass_bracket=(4.0, 10.0))
    objective(m) = apogee_of(scenario with airframe.m = m) - target
      -> dataclasses.replace down to Airframe(m=m)  [NOT params_replace -- SS38.4.2]
      -> assemble -> run_sim -> flight_stats.apogee_altitude
    scipy.optimize.brentq(objective, *mass_bracket)
    returns (baseline_mass, required_mass, delta)      # fx27's own return shape

estimate_cx(scenario, target_apogee_agl=3000.0, cx_bracket=(0.0, 1.0))
    objective(cx) = apogee_of(Scenario(..., overrides={"aero.C_x": cx})) - target
    same brentq, same return shape
```

Two robustness notes the developer must honour, lifted from `solve_cda._solve_scalar`'s hard-won
behaviour (`solve_cda.py:250-372`) rather than reinvented:

1. **Evaluate both bracket ends first and check the sign change.** An unbracketed target must report
   the reachable apogee range and clamp, not let `brentq` raise a bare `ValueError`. fx27 does not
   do this; it is a free improvement and matches the house style.
2. **`apogee_altitude is None` is a legitimate outcome** (too heavy / too draggy to leave the pad).
   Guard it explicitly; do not let `None - target` raise `TypeError`.

`brentq`'s `xtol` should be set on the *search variable* (kg, or dimensionless `C_x`), with a final
confirmation run and a reported apogee residual — the `_solve_scalar` pattern. The adaptive-xtol
refinement in `_solve_scalar` (lines 335-355) is **not** needed here: `apogee(mass)` and
`apogee(C_x)` are far less convex than `apogee(C_dA)` over these brackets.

Acceptance for both: the four fx27 figures in SS38.3.1 within 5 %.

> **Alternative considered and deferred (B-NN-1):** promote a general
> `solve_for_target_apogee(cfg_factory, bounds, target, *, increasing)` into
> `apps/optimization/` by generalising `_solve_scalar`. That would be **(c)** — a real `apps/`
> change, a real Step, and three callers (`solve_cda`, mass, drag) is thin justification. Log it as
> a backlog item; do not do it as part of this port.

### SS38.5.5 Air-brake sizing (#6, #15)

**(a)** `apps.optimization.airbrake_sizing.solve_cda.solve_airbrake(cfg, spec)` with

```python
AirbrakeSpec(
    target_apogee_m=2500.0,
    trigger="after_burnout",     # == fx27's power_off_drag semantics (SS38.2.4)
    solve_for="cda",
    cd_brake=1.0,                # fx27's brake_c_d
    cda_bounds=(0.0, 0.05),      # fx27's c_da_bracket
)
```

**(b)** ~30 lines in `projects/fx27/point/airbrake.py` for the three things `apps/` does not do:

- `area_min = sol.s_max_m2` (identical formula; just a rename for the fx27 report),
- `area_design = area_min * margin` (`margin=2`),
- `area_per_panel = area_design / brake_count` (`brake_count=3`),

plus a `print_brake_report` that prints those three alongside `solve_cda.print_solution`'s own
block. Do **not** re-implement the "baseline already below target" check: `solve_airbrake` already
returns `reachable=False` with the reachable range and `print_solution` says so loudly — strictly
better than fx27's bare `raise`.

#15 runs this for the 4 ideal variants only (fx27 deliberately excludes the 3 un-ideal-ised base
rockets). Keep that choice and keep fx27's comment explaining it.

### SS38.5.6 The two comparison figures (#8, #9, #10)

**(b)**, `projects/fx27/point/plots.py`. `apps/sim/engine/plotting.py` has
`plot_trajectory_overlay` (2 panels: `z(x)` and `z(t)`), which covers 2 of fx27's 4 displacement
panels but with the wrong panel set and no variant styling. Nothing covers the kinematics figure.
So this is new plotting code — but it is **assembled entirely from public `apps/` helpers**:

| fx27 panel | data source — all existing public functions |
|---|---|
| `z(x)` flight path | `y = result.raw.sol(t)`; `y[X]`, `gravity.altitude_agl(y, p)` |
| `theta(t)` flight-path angle | **`apps._shared.flight_stats.flight_path_angle(y[VX], y[VZ])`** — public, vectorised, reuse directly |
| `z(t)` altitude AGL | `gravity.altitude_agl` |
| `x(t)` downrange | `y[X]` directly. **fx27's `hypot(x, y)` collapse is unnecessary here** — this model is planar, so `x` *is* the downrange |
| `|v|(t)` | `np.hypot(y[VX], y[VZ])` |
| body-frame `v_x(t)`, `v_z(t)` | **`apps.sim.engine.frames.to_body(np.array([vx, vz]), theta)`** — public. Note: in this project the body frame is **real** (it is the `theta` state), not fx27's hand-rolled frozen axis. Under Option A `theta` happens to be constant, so the two agree by construction; under Option B they would not, and the panel label should say "body axis (frozen at the rail angle)" either way |
| `|a|(t)` | `apps.sim.engine.dynamics.derivatives(t, y, p)` re-evaluation — the `flight_stats` D-20 idiom; take components `VX`/`VZ`. Requires `p.solver.sample_rate_hz == 0.0` (SS38.4.1) |
| body-frame `a_x(t)`, `a_z(t)` | `frames.to_body` on the above |
| `_variant_style` / `_family_colors` | pure matplotlib + string parsing on the `"<family> (ideal mass)"` convention. Copy the behaviour: same colour per family, solid / dashed / dotted per variant |

Sample on `result.raw.sol(t)` over a uniform grid — mirror
`plotting._dense_time_grid`'s reasoning (dense interpolant, not the sparse adaptive step points).
Since the fx27 figures are ascent-only (`terminate_on_apogee`), clip the grid at
`result.events["apogee"]` rather than at `events["ground"]`.

Return `fig` and do not call `plt.show()` — the house convention in `plotting.py`.

> **B-NN-2 (backlog, not this port):** `plot_displacement_comparison` and
> `plot_kinematics_comparison` are genuinely reusable and would be a sensible addition to
> `apps/sim/engine/plotting.py` alongside `plot_trajectory_overlay`. That would be **(c)**. Keep
> them in `projects/fx27/` for now; promote only once a second consumer exists.

### SS38.5.7 Option C's diagnostic hook

**(a)** `apps._shared.flight_stats.point_mass_flightpath(result, p) -> PointMassFlightPath`, plus
**(b)** ~40 lines in `projects/fx27/point/validity.py` that reduce it to three printable numbers per
scenario:

- `alpha_burnout_deg` — `|theta_rail - theta_v(t_burnout)|`,
- `alpha_max_deg @ q>1%` — `max|alpha|` over samples where `q > 0.01 * q_max` (the only window where
  the frozen-axis error can move a number),
- `still_air_residual_max` — must be ~0 to machine precision; a non-zero value means wind got turned
  on by accident, i.e. it is a **config self-check**, not a physics result.

Suppress `lambda_ratio` from the report entirely: it is `NaN` throughout under `aero.model ==
"constant"` (SS38.2.3). Printing a `NaN` column would read as a defect.

Make this opt-in per run script (`--validity`): it costs an extra 2000-point `dynamics.derivatives`
pass per flight, which on the 23-row euroc sweep is 23 extra dense passes.

### SS38.5.8 Why none of the `point/` layer belongs in `apps/`

Each module is either (i) a 3-call composition of existing `apps/` entry points
(`flight.py`, `airbrake.py`), (ii) a table formatter for a column set that is fx27's contract and
nobody else's (`comparison.py`), (iii) matplotlib layout (`plots.py`), or (iv) a `brentq` objective
that re-`assemble`s a `Scenario` (`estimate.py`). None adds physics; none is used by a second
consumer today. This project's own convention is explicit that `apps/` is the pre-built library and
`projects/` is where runnable, rocket-specific code lives. Two promotion candidates are logged as
backlog items (B-NN-1, B-NN-2) rather than being smuggled in as part of a port.

---

## SS38.6 Proposed layout under `projects/fx27/`

Mirrors fx27's own three-layer shape (`data/<config>/` literals — generic `point/` — `runs/` entry
points), re-expressed in this project's `Scenario`/`assemble` idiom and in
`apps/input/demo_scenario.py`'s inline `REQ|OPT` crib-sheet convention.

```
projects/fx27/
  README.md                  # what this is, provenance (fx27/simulation), how to run, the
                             #   Option-A/C caveat, the Mach>0.8 caveat, the 3 deferred motors
  __init__.py
  _paths.py                  # SS38.4.3: absolute anchors for the two motor-CSV directories
  data/
    README.md                # RETITLE: currently a verbatim copy of projects/data/README.md and
                             #   describes the wrong directory (SS38.7.2)
    motors/cspace/*.csv            # already present (2 files)
    motors/euroc-sweep/*.csv       # already present (26 files, 3 of them -todo stubs)

  point/                     # the launch-config-agnostic layer == fx27's point/
    __init__.py
    flight.py                # run(scenario) -> (Config, Result, FlightStats)          SS38.5.1
    metrics.py               # Row dataclass: fx27's 9-key metric set over FlightStats  SS38.5.1
    comparison.py            # evaluate_scenarios(...) -> [Row]; print_table; save_csv  SS38.5.2
    estimate.py              # estimate_airframe_mass / estimate_cx (brentq)            SS38.5.4
    airbrake.py              # solve_airbrake wrapper + margin/panel arithmetic         SS38.5.5
    plots.py                 # plot_displacement_comparison / plot_kinematics_comparison
                             #   + _variant_style / _family_colors                      SS38.5.6
    validity.py              # Option C: point_mass_flightpath -> 3 printable numbers   SS38.5.7

  cspace/
    __init__.py
    site.py                  # LaunchSite: 43.218, -0.047, 428.96 m, rail 5 m @ 85 deg, az 0
    weather.py               # Weather: ISA dry, no wind, no sounding
    motors.py                # Motor x2: pro54_2060K570, pro75_3419L645
    rockets.py               # Rocket x3: pro54_transition, pro54_equal, pro75
    rockets_ideal.py         # Rocket/override x4: the solved ideal-mass / ideal-drag variants
    scenarios.py             # SCENARIOS: dict[str, Scenario] -- the 7 compared rows

  euroc/
    __init__.py
    site.py                  # LaunchSite: 39.3897, -8.2890, 160 m, rail 12 m @ 84 deg, az 133
    weather.py
    motors.py                # Motor x26, with DEFERRED_MOTORS = frozenset({...3 names...})
    rockets.py               # Rocket x12: pro54_2G ... pro98_6GXL (dry mass 5.636-7.523 kg)
    scenarios.py             # CANDIDATES: dict[airframe -> tuple[motor, ...]]
                             # generate_scenarios() -> dict[str, Scenario] (24 runnable)
                             # DEFERRED: tuple[str, ...]  (the combos blocked on -todo data)

  runs/                      # entry points; `python -m projects.fx27.runs.<name>` from repo root
    __init__.py
    cspace_point.py          # one flight (pro75): summary + trajectory + time histories   #11
    cspace_comparison.py     # 7 rockets: table + both comparison figures                  #12
    cspace_ideal_mass.py     # mass solve for pro54_transition + pro75, target 3000 m       #13
    cspace_ideal_drag.py     # C_x solve, same two rockets, target 3000 m                   #14
    cspace_airbrake.py       # brake sizing for the 4 ideal variants, target 2500 m         #15
    euroc_comparison.py      # 23 combos: table (+ deferred list printed explicitly)        #16
    euroc_sweep.py           # optional: the scenario_sweep variant, richer columns     SS38.5.3B
```

Conventions every file in this tree must follow (these are the house rules, not new ones):

1. **Every field in a config literal carries an inline `# REQ|OPT, <unit> -- <one line>` comment**,
   the `apps/input/demo_scenario.py` crib-sheet convention. A reader must not have to open
   `params.py` to know whether a number matters.
2. **Every number carries its provenance** in the module docstring or the `notes=` field: which
   fx27 file it came from, and whether it is measured, vendor-published, or a placeholder.
3. **Every dynamically inert placeholder is labelled as such** — `Lengths.l1`/`l2`, `Airframe.I`,
   the zero-geometry motor stations (SS38.2.8). Each one needs a one-line "inert because the total
   pitching moment is identically zero under `C_z = C_m = c_mq = 0`; **becomes a silent bug if this
   scenario is ever switched to an alpha-dependent aero model**".
4. **Artifacts go to `output/`** via `apps._shared.artifacts.output_dir()` — gitignored, the house
   convention. No run script writes into `projects/`.
5. **No run script writes to `dev/`** and none touches the trackers.

### SS38.6.1 Tests

`tests/` is this repo's single test root (`tests/__init__.py` is mandatory — the `eventkit`
site-packages collision, see `CLAUDE.md`). Add **one** file, `tests/test_fx27_port.py`, covering:

- every `cspace`/`euroc` scenario `assemble()`s without raising (cheap, no integration) — this is
  the real guard against the zero-geometry recipe (SS38.2.8) being typed in wrong;
- `DEFERRED` is exactly the 3 `-todo` names and `generate_scenarios()` excludes them;
- `estimate_airframe_mass` / `estimate_cx` reproduce fx27's four hardcoded figures within 5 %
  (SS38.3.1) — the acceptance oracle, and the slowest test in the file;
- the brake solve for one ideal variant converges and `reachable is True`;
- plots produce a figure with the expected number of axes and the expected number of lines
  (assert the data series, not the pixels — `tests/test_plotting3d.py` is the precedent).

**No numeric pin may be added or changed outside this new file.** The existing
`tests/test_integrate.py` `np.array_equal` pins must be untouched; a `projects/`-only change cannot
move them, and if a full run shows otherwise, stop and escalate.

---

## SS38.7 Data readiness, the three `-todo` motors, and a repo hygiene flag

### SS38.7.1 The three deferred motors — DEFERRED, not dropped, not blocking

`projects/fx27/data/motors/euroc-sweep/` holds 26 CSVs. Three are 4-byte stubs containing the
literal text `null`:

```
pro75-2412K1085-todo.csv
pro98-14200N3180-todo.csv
pro98-9876M1890-todo.csv
```

`motor_file._read_csv` would raise `ValueError: could not convert string to float: 'null'` on any of
them — loud, not silent, which is the right failure mode. Required handling:

- `euroc/motors.py` defines `DEFERRED_MOTORS = frozenset({...})` holding exactly these three names,
  with a comment stating the data is not ready and who is expected to supply it.
- `generate_scenarios()` **excludes** any `(config, motor)` pair whose motor is in that set and
  returns the excluded pairs as a separate `DEFERRED` tuple.
- `runs/euroc_comparison.py` **prints the deferred list under the table** —
  "N combinations deferred, motor data not ready: ..." — so a reader of the output cannot mistake 23
  rows for the full candidate set.
- A test pins that the deferred set is exactly these three and that no generated scenario references
  them.

Nothing else is blocked on them: the remaining 24 combinations run. When the real curves arrive,
removing three names from one frozenset is the entire change.

### SS38.7.2 `projects/data/README.md` appears to have been moved by accident — FLAG

`git status` at the start of this pass shows:

```
 D projects/data/README.md
?? projects/fx27/
```

and `projects/fx27/data/README.md` is byte-identical in content to what `projects/data/README.md`
was (it is titled `# projects/data/ — личные данные пользователя` and documents *that* directory,
not `projects/fx27/data/`). `.gitignore` lines 25-26 are:

```
/projects/data/*
!/projects/data/README.md
```

So that README is the **only** tracked content in `projects/data/`; deleting it makes the directory
vanish from a fresh clone, and its documented convention (how to reference personal data files)
disappears with it.

Recommended: restore `projects/data/README.md` (`git checkout -- projects/data/README.md`, **after
asking the user**, per the project's git-safety rule) and give `projects/fx27/data/README.md` its
own text describing the fx27 motor corpus specifically. Not a blocker for the port, but it should
not be committed as-is.

### SS38.7.3 `projects/fx27/` is untracked and NOT gitignored

The 28 CSVs total well under 10 KB and will be committed along with the new Python. That is the
right outcome (they are the inputs that make the port reproducible), but it is worth the user
confirming it, since they are vendor thrust curves copied from a sibling repository.

---

## SS38.8 Does this need a Step / Phase number?

**Under Option A or C: no.** Stating this explicitly, since the brief asked.

- Not one line under `apps/` changes. The project's step discipline ("one step — one commit
  `Step NN (Phase X.Y): …`; after each step a full test run and a check that the numeric pins have
  not moved") exists to protect the library and its pins. A `projects/`-only addition cannot move a
  pin: nothing under `tests/` imports `projects/fx27/` except the one new test file, and nothing
  under `apps/` imports it at all.
- There is no architectural decision being *made in the code* — the one real decision (SS38.3) is
  resolved at the user gate before any code is written, and the result is a configuration choice in
  a literal, not a code path.
- The project already has precedent: `projects/` is explicitly "where the user writes their own
  input scripts" (`CLAUDE.md`, Профиль проекта, after Phase 2.20 Step 141 retired the pre-built
  entry scripts). Adding a user workspace there is ordinary use of the library, not development of
  it.

Recommended tracking instead: **one `feature/fx27-port` branch, one or two commits**
(`projects/fx27: port fx27/simulation onto apps/ (cspace + euroc)`), a `dev/journal.md` entry, and
a `D-NN` decision-log line recording the SS38.3 answer. A full test run before merge as usual —
not because the port can break anything, but because the house rule is a full run before any merge.

**Under Option B: yes, unambiguously.** A new solver path in `forces.py`/`dynamics.py`/
`integrate.py` is a Step with its own architecture ticket, `tdd` discipline, pin-protection
analysis, `code-review`, QA, and a LaTeX model section (which needs its own explicit user
permission, `dev/docs/latex/` being edit-on-request). The fx27 port would then be a second,
dependent Step on top. Numbering continues from the last used value in `dev/status.json`.

---

## SS38.9 Acceptance criteria

| # | Criterion | How checked |
|---|---|---|
| AC-1 | All 7 cspace scenarios and all 24 runnable euroc scenarios `assemble()` without raising | `tests/test_fx27_port.py`, no integration needed |
| AC-2 | Every run script completes and writes its artifacts to `output/` | manual run of all 7 entry points |
| **AC-3** | **`estimate_airframe_mass` / `estimate_cx` reproduce fx27's four hardcoded solved figures (4.2864 kg, 0.2351, 8.0654 kg, 0.8304 at 3000 m AGL) within 5 %** | `tests/test_fx27_port.py` — **this is the Option A/C validation, the whole physics argument rests on it** |
| AC-4 | If AC-3 fails by more than 5 %, the work **stops** and returns to the user gate with the measured numbers, rather than being "tuned" to fit | process rule, stated in the ticket |
| AC-5 | Air-brake solve converges (`converged is True`, `reachable is True`) for all 4 ideal variants at 2500 m, and `s_max_m2` is in the same order of magnitude as fx27's reported min area | `tests/test_fx27_port.py` + run output |
| AC-6 | The 3 `-todo` motors appear in a printed DEFERRED list, never silently absent | test + run output |
| AC-7 | `MachRangeWarning` count is reported as a summary line, not suppressed and not spammed | run output review |
| AC-8 | Option C only: `alpha_max_deg @ q>1%` and `still_air_residual_max` are printed per scenario; residual is ~0 (machine precision) | run output; a non-zero residual is a config bug, fail the run |
| AC-9 | Full suite green, **existing numeric pins bit-identical** | `python -m pytest -q` (background, chunked per `CLAUDE.md`) |
| AC-10 | `rg "^from apps|^import apps" projects/fx27` shows imports only of public names; no `_`-prefixed `apps` internals are imported | grep. Specifically: **do not import `solve_cda._solve_scalar` or `schema._weight_from_pieces`** |

---

## SS38.10 Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Option A's frozen-attitude error is larger than the SS38.3.1 estimate | low-medium | high — invalidates the approach | AC-3/AC-4: measured against fx27's own solved numbers before anything is built on top. The estimate is explicitly labelled an estimate |
| R2 | The zero-geometry motor recipe (SS38.2.8) is typed in wrong and `_weight_from_pieces` dereferences a `None` `length` | medium | low — fails loudly at import | AC-1 asserts every scenario assembles; the failure is a `TypeError`/`ValueError` at assembly, never a wrong number |
| R3 | Someone later switches these scenarios to `"linearized"`/`"table"` aero, silently un-zeroing the moment and making the collapsed stations a physics bug | low | high — silent wrong numbers | Mandatory one-line warning comment on every inert placeholder (SS38.6 rule 3) and in the campaign module docstrings |
| R4 | Constant `C_D = 0.5` through the transonic region makes several euroc apogees non-credible | **certain** | medium — inherited from fx27, not introduced here | AC-7 surfaces it per run; README states it; upgrade path is `aero.model="table"` with real Mach-dependent data |
| R5 | `Solver.t_max` too small for the largest pro98 rows -> no apogee event -> `FlightStats` all-`None` row | medium | low — visible as a blank row | `flight_stats` handles it (line 157); the comparison table must render `None` as `-`, and the run script should warn when any row has `apogee_altitude is None` |
| R6 | `scenario_sweep` (Variant B) marks every row INFEASIBLE on a fabricated static margin | high if used naively | medium — misleading output | SS38.5.3 condition 1: `Constraints(min_tw=0.0, min_margin_cal=-inf)`, with a printed explanation |
| R7 | cwd-relative motor paths break when a script is run from anywhere but the repo root | medium | low — loud `FileNotFoundError` | `_paths.py` absolute anchors (SS38.4.3) |
| R8 | The port drifts from fx27 silently as the sibling project evolves | medium | low | Each campaign module names the exact fx27 source file it mirrors; the README records the date of the port |
| R9 | A reviewer assumes "point mass" in the file names means true point-mass physics | medium | medium | The `point/` package docstring must open with the Option A/C caveat verbatim, not bury it |

---

## SS38.11 Tickets

All tickets below assume the SS38.3 gate resolved to **Option A or C**. If the user picks Option B,
none of these start until the new solver Step lands; a separate architecture ticket is required for
it and this document does not scope it beyond the cost estimate in SS38.3.2.

### [FX27-1] Campaign configs: cspace

- **Module/boundaries:** `projects/fx27/__init__.py`, `projects/fx27/_paths.py`,
  `projects/fx27/cspace/**` (new). No other path.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true
- **Spec slice:** this file, SS38.2.8, SS38.4.1, SS38.4.3, SS38.6 (conventions 1-3), SS38.5.2
  (the 7-row set and the `"<family> (ideal …)"` naming protocol).

Write `site.py`, `weather.py`, `motors.py`, `rockets.py`, `rockets_ideal.py`, `scenarios.py` as
`Scenario`/`Rocket`/`Motor`/`LaunchSite`/`Weather` literals with inline `REQ|OPT` comments. Values
come from the orchestrator's inventory of fx27's `data/cspace/*`. The zero-geometry motor recipe is
SS38.2.8 verbatim — do not invent motor geometry.

### [FX27-2] Campaign configs: euroc

- **Module/boundaries:** `projects/fx27/euroc/**` (new). No other path.
- **Assignee:** developer
- **depends_on:** [FX27-1] — only for `_paths.py`; otherwise disjoint
- **parallel_safe:** false (shares `_paths.py` creation with FX27-1; becomes true once FX27-1 lands)
- **Spec slice:** this file, SS38.2.8, SS38.4.1, SS38.6, SS38.7.1.

12 airframe `Rocket` literals, 26 `Motor` literals, `DEFERRED_MOTORS`, `CANDIDATES` mapping, and
`generate_scenarios() -> (dict[str, Scenario], DEFERRED)`. Motor names are `"<config>/<motor>"`
(SS38.5.3 condition 2).

### [FX27-3] The generic `point/` layer

- **Module/boundaries:** `projects/fx27/point/**` (new). No other path.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true — disjoint from FX27-1/2
- **Spec slice:** this file, SS38.5.1 and SS38.5.4-SS38.5.7 (the per-module specs), SS38.2.4
  (the `AirbrakeSpec` mapping table), SS38.2.9 (the metric mapping table).

Seven modules per SS38.6. Follow `tdd`. Hard constraints: no `apps/` edit; no import of any
`_`-prefixed `apps` name (AC-10); `estimate.py` goes through `Scenario` -> `assemble`, **never**
`params_replace`, for anything that changes mass (SS38.4.2).

### [FX27-4] Run scripts

- **Module/boundaries:** `projects/fx27/runs/**`, `projects/fx27/README.md` (new).
- **Assignee:** developer
- **depends_on:** [FX27-1, FX27-2, FX27-3]
- **parallel_safe:** false
- **Spec slice:** this file, SS38.5 (the #11-#16 rows), SS38.4.4, SS38.7.1.

Seven entry points per SS38.6. Each writes to `output/` via
`apps._shared.artifacts.output_dir()`. `euroc_comparison.py` prints the DEFERRED list;
every comparison script prints the Mach-blind summary line (SS38.4.4).

### [FX27-5] Tests and the AC-3 validation gate

- **Module/boundaries:** `tests/test_fx27_port.py` (new). **No other test file may be touched.**
- **Assignee:** developer
- **depends_on:** [FX27-1, FX27-2, FX27-3]
- **parallel_safe:** false
- **Spec slice:** this file, SS38.6.1, SS38.3.1 (the four oracle figures), SS38.9.

Per SS38.6.1. **AC-3 is the gate**: if the four fx27 figures are not reproduced within 5 %, stop and
report the measured numbers to the orchestrator (`needs_input`) — do not adjust brackets, tolerances
or configuration to make them fit.

### [FX27-6] Repo hygiene (separate, needs a user "yes" first)

- **Module/boundaries:** `projects/data/README.md` (restore), `projects/fx27/data/README.md`
  (rewrite).
- **Assignee:** orchestrator (git restore requires an explicit user confirmation per the project's
  git-safety rule)
- **depends_on:** []
- **parallel_safe:** true
- **Spec slice:** SS38.7.2.

---

## SS38.12 Open decisions for the user gate

| id | Question | Options | Recommendation |
|---|---|---|---|
| **D-A** | **How to realise "point mass"** | A (frozen attitude) / B (new engine solver) / C (A + the Step-137 diagnostic as the measured error instrument) | **C** — SS38.3.2. Note that B would *not* reuse the gated Step 143 (SS38.3.0) and costs roughly half to two-thirds of Step 32 plus a LaTeX ticket |
| D-B | euroc table: fx27's column set, the richer `scenario_sweep` columns, or both | fx27 columns only / `sweep_scenario` only / both as two scripts | **both** — SS38.5.3; fx27 columns as the primary, `scenario_sweep` as an extra view (maximum apps reuse, costs ~20 lines) |
| D-C | Step/Phase number for this work | none (projects-only) / a full Step | **none** under Option A/C — SS38.8 |
| D-D | Commit the 28 vendor motor CSVs into this repo | yes / gitignore them like `projects/data/` | **yes** — tiny, and the port is not reproducible without them; needs a user "ok" since they are copied from a sibling repo (SS38.7.3) |
| D-E | Restore `projects/data/README.md` | restore / leave deleted | **restore** — it is the only tracked content in a gitignored directory (SS38.7.2). Requires a user "yes" before any `git checkout --` |
| D-F | Promote the two comparison figures and a general apogee-target solver into `apps/` | now / backlog / never | **backlog** (B-NN-1, B-NN-2) — one consumer is not enough to justify an `apps/` change (SS38.5.4, SS38.5.6) |

### Questions to stress-test with the user (`grilling` input)

1. Do you want fx27 *parity* (same numbers), or fx27 *capability* (same questions answered, on this
   project's better model)? C gives capability plus a measured bound on the difference; only B gives
   parity, and parity with rocketpy is not obviously a goal worth an engine change.
2. The dominant error in this port is **constant `C_D = 0.5` through the transonic region**
   (SS38.4.4, R4), inherited from fx27 — not the point-mass question. Would you rather spend the
   effort on Mach-dependent `C_A` data than on a point-mass solver?
3. The 12 euroc airframes carry `C_D = 0.5` as an explicit placeholder in fx27. Is that still the
   intent here, or is real drag data coming?
4. fx27's static-margin-equivalent data does not exist (no fin/CP geometry). Are you content for
   every stability column to read "n/a", or is there geometry to supply?
5. Is `projects/fx27/` the right home, or should this become a sibling repo that depends on
   rocket-physics as a package (the `fx27/simulation` consumer precedent in the last commit)?

---

## SS38.13 Rejected options

| Rejected | Why |
|---|---|
| `compare_motors.compare_motors` for either campaign | Refuses a mass-model-on baseline (`ValueError`, D-82, `compare_motors.py:190`), and the mass model is mandatory for fx27 parity (SS38.4.2) |
| `trade_surface.build_surface` for the mass/drag estimates | Same `m_d` guard; and it is a 2-D grid sweep with interpolation, not a 1-D root find — a different question with a different answer shape (SS38.2.7) |
| Reusing `solve_cda._solve_scalar` for the mass/drag solves | Private, and coupled to `AirbrakeSpec`. Importing a `_`-prefixed name across package boundaries is exactly the coupling this repo's module docstrings argue against. Generalising it properly is an `apps/` change -> backlog B-NN-1 |
| Implementing gated Step 143 to get point-mass physics | Step 143 is a closed-form analytic gravity-turn estimator with no thrust curve, atmosphere or rail (`task-136-137…md:472-484`). It would not reproduce a single fx27 number (SS38.3.0) |
| "Tiny time steps so the frozen axis catches up" | The frozen-axis divergence is a model difference (the force points along the wrong unit vector), not a discretisation error. It does not shrink as `dt -> 0`. Listed as option D in SS38.3.2 only to refute it |
| `params_replace` to vary mass for the estimator objective | `assemble` derives `weight` from the pieces and seeds `s0.m` from `weight.m`; a post-hoc `weight.m` override leaves `s0.m` stale and the mass model would fly the old launch mass (SS38.4.2) |
| Putting the `point/` layer in `apps/` | No new physics, no second consumer, and `apps/` is the pre-built library while `projects/` is where runnable rocket-specific code lives (SS38.5.8) |
| Reproducing fx27's `flight.plots.trajectory_3d()` | The 2D engine has no 3D state; `plot_trajectory_3d` needs a 13-component `run_sim_3d` result. With no wind the fx27 flight was planar anyway, so the figure carried no information the 2D flight-path plot does not (SS38.5.1) |
| Collapsing lateral axes with `hypot`, as fx27 does | fx27 needed it because rocketpy carries two lateral axes; this model is planar, so `y[X]` *is* the downrange and `theta` *is* the body axis. Copying the `hypot` would be cargo-culting (SS38.5.6) |
| Suppressing `MachRangeWarning` | It is a correct warning about a real modelling defect inherited from fx27. Summarise, do not silence (SS38.4.4) |

