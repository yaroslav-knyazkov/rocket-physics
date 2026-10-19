# Architecture 35 — Phase 2.17: bring the simulator in line with the approved report, driven by the user's goals

## Кратко (RU)

- Документ планирует фазу 2.17: подтянуть код (`sim/`, `configs/`, `apps/`, `data/`) к утверждённому отчёту, но в порядке целей пользователя: (1) подбор мотора для второй конфигурации ракеты, (2) максимальная спецификация аэротормоза для двух конфигураций, (3) старт проектирования регулятора (дискретный, ZOH).
- Минимальный набор: баги B32 (Кориолис под куполом, ограничение m_f, защита 0.1 с, длина для Re), расход массы от T_0 и масштабы импульса/времени тяги, таблица аэро с l_p от носа (B33) и выбор знака C_m (B31), перестройка App 3 под реестр `Motor`, вторая конфигурация как конфиг, аэротормоз как ось f_b в таблице аэро (опционально, старый аддитивный путь остаётся), привод (ограничение скорости/диапазона/задержка), ансамбль Монте-Карло, затем регулятор: предиктор с учётом сопротивления, датчик высоты (барометр) + оценщик, каркас замкнутого контура.
- Всё новое включается явно (opt-in): значения по умолчанию воспроизводят текущие числовые пины бит-в-бит. Единственные места с риском сдвига пинов отмечены в таблице (m_f-зажим — возможен сдвиг в последнем бите; знак C_m и перепин — только с «да»).
- Отложено: 3D, мультикомпонентная аэродинамика, Dryden w / вертикальный ветер, jet damping, C_m,q (нет значения), двухступенчатый парашют, всё research-blocked.
- Параллельный трек отчёта: приложение, генерирующее 13 `\comptodo` и 4 симуляторных `\figtodo`; ревью оставшихся разделов; обозначения и библиография.
- Нужны от пользователя: данные ракеты (обе конфигурации), кандидаты-моторы (.eng), аэро-таблица(ы) (с осью f_b для тормоза), параметры привода/датчиков/цель по апогею и определение «максимальной спецификации» — см. §35.7 и §35.8 (решения D-109…D-118).

## Contents

- §35.1 Context: what the three goals need (and what they do not)
- §35.2 Gap table (paper simtodo / code-vs-paper / proposals -> goals, effort, pin risk)
- §35.3 Phase 2.17 scope (in / out, justification)
- §35.4 Design: components, new fields, interfaces, directory changes
- §35.5 Non-functional decisions
- §35.6 Tickets (Steps 97-112; Step 112 = large-alpha Jorgensen extension, "Inserted steps")
- §35.7 Open decisions for the user (`decision_required`)
- §35.8 Data the user must supply
- §35.9 Timeline and milestones M1 / M2 / M3, paper track
- §35.10 Risks
- §35.11 Rejected options
- §35.12 Decision log (proposed D-109 ...)

## 35.1 Context: what the three goals need (and what they do not)

State of the code at `develop` (Phase 2.16 + LaTeX merge), measured while writing this document:

- 501 tests collected. Full run ~220-390 s. Many tests pin results bit-for-bit (`np.array_equal`).
- `sim/` has 3 aero models (`constant`, `linearized`, `table`), a thrust curve with `A_e (p_ref - p_amb)` correction (default
  `A_e = 0`), a mass model (`none | isp | endpoints`) driven by the integrated state `y[M]`, `dm/dt = -T/(I_sp g0)` with `T` the
  pressure-corrected thrust (`sim/dynamics.py:239`), a sampled-data/ZOH mode (`sim/sampling.py`, one channel `"airbrake"`,
  RK4 only, `sample_rate_hz > 0`), air brake as an **additive axial force** `q Cd S_max f_b` (`sim/forces.py:223-227`), laws
  `none | proportional | full`, triggers `after_burnout | after_time | after_apogee`.
- Apps: App 3 `apps/motor_selection` (sweep, constant-mass, CSV thrust curves, per-motor `overrides` dict, NOT built on the new
  `Motor`/`Scenario` pieces), App 4 `apps/airbrake_sizing` (scalar `C_dA` solver for the `full` law), App 2 CFD conditions,
  App 5 weight/aero trade.
- Only one rocket (`configs/rockets/demo.py`, synthetic, `aero.model = "constant"`, supersonic -> `MachRangeWarning`; numbers
  are wiring numbers, not credible drag), one real motor (CTI K570 `.eng`), one table (`data/aero/example.csv`, synthetic,
  alpha in [-10, 10] deg, M in {0.5, 1, 2}).
- Cost of a sampled run (measured on this machine, demo, 40 s flight): RK45 0.06 s; RK4 dt = 5 ms 1.3 s; RK4 dt = 1 ms 6.7 s.
  A 200-sample sampled-data ensemble at dt = 1 ms is ~22 min single-core. This drives tickets 104-105.

### Goal -> capability map

| Goal | What must be true | Present? | Missing (-> gap IDs) |
|---|---|---|---|
| 1. Motor sweep for config 2 | config 2 as data; candidate motors as `Motor` configs (real `.eng`, mass history); sweep built on `Motor`/`Scenario` with feasibility filters (T/W, rail-exit speed, max Mach vs table range, **static margin vs burn**, max accel); credible aero (table with CP from nose); mass flow consistent | App 3 exists but on old CSV/`overrides` path, constant mass; static margin is blind to CG travel (arm fixed) | G5, G6, G13, C3, P2, P8, Step 100-101, user data |
| 2. Max air-brake spec, 2 configs | brake in aero (at least `Delta C_x`, ideally `C_x, C_z, C_m, l_p` vs `f_b`); dispersions (impulse, C_x, mass, wind, dT) to size margin; authority bounds `h_closed`, `h_open` per config x motor; brake load numbers | App 4 solves one scalar `C_dA` on the nominal flight only; additive axial brake only, no CP shift | G22, P1, P2, P3, Step 102, 105, 106 |
| 3. Controller design start | sampled-data loop with command, actuator (rate/range/delay), sensor (baro noise/lag) and estimator; law with memory; predictor that includes drag; harness with metrics; fast ensembles | ZOH seam exists, channel contract recursive (`prev`), one memoryless law, no actuator, no sensors | P4, P5, P6, P11, Step 103, 104, 107-109 |

What the goals do **not** need (and so are not in the scope): 3D, vertical wind / Dryden `w`, jet damping, `C_m,q` value, multi-component
aerodynamics, drogue+main, grain models. Justification in §35.3. Reason for jet damping / `C_m,q` exclusion: the air brake is an
axial-drag actuator acting on the vertical channel; for a near-vertical flight in modest wind the pitch dynamics only enter through
`alpha` -> `C_x(alpha)` (second order). Revisit when a wind-weathercock / rail-exit study is requested.

## 35.2 Gap table

Legend. **Goal**: 1 motor sweep, 2 brake spec, 3 controller, `-` none. **Effort**: S (<= 1 step, < 1 session), M (1-2 steps), L (> 2 steps
or open research). **Pin risk**: `none` = new path is opt-in, default reproduces current numbers bit-for-bit; `last-bit?` = may
move `np.array_equal` pins at 1e-13 level, to be verified by the full suite; `MOVES` = changes existing results, needs the
user's "yes" (re-pin). **Plan**: Step number in 2.17, or `defer`. Paper line numbers are of the merged `models.tex` /
`other-dynamics.tex` (grep the `\simtodo` text to find them; they drift).

### A. Paper `\simtodo` (paper describes, code lacks) — 24 in `sections-ai` (G1-G21), plus code-backlog items G22-G24

| ID | Item (source) | Goal | Effort | Pin risk | Plan |
|---|---|---|---|---|---|
| G1 | Radial `g` uses `R_e + h_AGL`, not `R_0 + height` (models:42) | - | S | MOVES radial-gravity pins | defer |
| G2 | Arc angle `phi = x/R_e` for the direction model (models:62) | - | S | MOVES elliptical-direction pins | defer |
| G3 | Unified gravity model (magnitude + direction) does not exist (models:96) | - | M | none | defer |
| G4 | One `g0` serves ISP, constant gravity, radial reference (models:190) | - | S | none (equal at default) | defer |
| G5 | `y[M]` has no floor at `m_f`; mass can burn below `m_d` (models:204; **B32.2**) | 1,2 | S | last-bit? | Step 97 |
| G6 | Mass flow from pressure-corrected `T`, not bare `T_0` (models:222; **B27.3**) | 1 | S | none at `A_e = 0`; MOVES if `A_e` populated for K570 | Step 98 |
| G7 | `r_g(t)` radial CG offset, time-dependent (models:273) | - | M | none | defer |
| G8 | Jet damping `-mdot (l_t - l_g)^2 omega` (models:288) | 3 (marginal) | S | none if switch default off | defer (2.18) |
| G9 | Linear `l_g,m`, `I_m,g` models vs two-lump (models:291; **B27.1-2**) | 1 (marginal) | M | MOVES if default | defer (opt-in later) |
| G10 | Multi-component aerodynamics `S_k, c_k` (models:366; **B30.3**) | 2 (alt. to G22) | L | none | defer |
| G11 | Linearized model: only `alpha` slope (models:455) | - | M | none | defer |
| G12 | Table stores arm `l1_m`, paper wants `l_p` from nose, arm from live `l_g(t)` (models:458; **B33**) | 1,2 | M | none (opt-in column + `Aero.l_p`) | Step 99 |
| G13 | Time interpolation between soundings (models:497, 618; **B30.5**) | - | M | none | defer |
| G14 | Field tier resamples stations onto a grid (models:552) | - | doc | - | paper track |
| G15 | Vertical wind `w_z = 0` in all tiers (models:667) | 3 (marginal) | M | none | defer |
| G16 | Discrete gust model (models:704; **B30.5**) | 2 (rail exit) | S | none | defer |
| G17 | Dryden `w` component (models:711; Round 7) | 3 (marginal) | M | none | defer |
| G18 | `Omega` resolved once in `F0` (models:882) | - | S | none (3e-6) | defer |
| G19 | Coriolis dropped under canopy (other-dynamics:66; **B32.1**) | - (correctness) | S | none unless `earth_rotation` + chute tests (`test_dynamics`, `test_control`, `test_config_pieces` use both flags — verify) | Step 97 |
| G20 | No altitude/`q` chute trigger (other-dynamics:80; **B30.2**) | - | S | none | defer |
| G21 | Air brake: own-component form and `f_b` table axis not implemented (other-dynamics:162) | 2,3 | M | none (opt-in) | Step 102 |
| G22 | `omega_r` under canopy not zeroed (**B30.1**; paper `\restodo` decision) | - | S | MOVES descent pins | defer (decision pending) |
| G23 | Drag polar `C_x = C_x0 + k C_z^2` (**B30.4**; paper `\restodo`) | - | M | none | defer (research) |
| G24 | Vector gravity field (**B30.6**) | - | L | none | defer (negligible, see model-proposals) |

### B. Code-vs-paper (`code-vs-paper.md`) not already above

| ID | Item | Goal | Effort | Pin risk | Plan |
|---|---|---|---|---|---|
| C1 | Air-brake `after_apogee` trigger has no 0.1 s pad guard (**B32.3**) | 3 | S | none (rest start has `v_z = 0`) | Step 97 |
| C2 | Re uses `Aero.l_ref` (default 0), paper uses `c = d_ref` (**B32.4**) | - | S | `tests/test_flow.py:143` expectation (not a numeric pin of a flight) | Step 97 + D-118 |
| C3 | `C_m` sign: example table vs code convention (**B31**) | 1,2 | S-M | MOVES if the code convention is changed | Step 99 + D-111 |
| C4 | Thrust-angle sign in code comments vs paper `theta_t` | - | S (comments) | none | Step 97 (comment-only) |
| C5 | Event-guard text, table exemption (D-93), brake factor (D-94a), mass defaults, file formats, Mach warning, ISA clamp... (27 features) | - | doc | - | paper track |
| C6 | Paper still describes pre-Step-93 axial force (discrepancy 1; **resolved in code**) | - | doc | - | paper track |

### C. Paper `\restodo` (17 + 1 in `analysis`, 1 in `introduction`) — research-blocked, all deferred

Mass-flow `T` vs `T_0` decision (-> G6, adopt the approved paper text, D-112), `dI/dt` + jet damping magnitude (G8), mechanisms mass change,
dry-rocket from components, table/large-angle blending, CFD pipeline definition, drag polar (G23), brake `C_N` data, weather items (DEM,
insolation, balloon), roll torque / thrust noise, integrator study (-> Step 110 `comptodo`), apogee definition, pad contact (B28), `omega` under
canopy (G22), canopy transients, `C_m,q` value (`analysis:188`). None blocks goals 1-3. Two **filters** are needed instead of models:
motor sweep rejects low T/W motors (pad slide, B28) and flags `M > 0.8` on non-table aero (existing `MachRangeWarning`).

### D. Proposals from `model-proposals.md` that serve the goals

| ID | Item | Goal | Effort | Pin risk | Plan |
|---|---|---|---|---|---|
| P1 | Monte-Carlo dispersion framework (seeded, parallel, percentiles) | 2,3 | M | none (apps layer) | Step 105 |
| P2 | Motor impulse/time scatter `k_J`, `k_t` | 2 | S | none (defaults 1.0 skip path) | Step 98 |
| P3 | ISA launch-day offset `dT` | 2 | S | none | Step 105 (hook) |
| P4 | Drag-aware apogee predictor (closed-form ballistic coast) | 3 | S | none (new law) | Step 107 |
| P5 | Actuator rate/range limit + command delay | 3 | M | none (default `ideal`) | Step 103 |
| P6 | Sensor model (baro noise, lag, quantisation) + estimator | 3 | M | none | Step 108 |
| P7 | Analytic regression suite (vacuum, drag-only coast, terminal velocity, energy) | all | S | none (new tests) | Step 97 |
| P8 | Static-margin-vs-time, rail-exit speed, envelope-exceedance diagnostics | 1 | S | none (outputs) | Step 100 |
| P9 | Segmented integration (RK45 restarted per ZOH tick) | 3 (runtime) | M-L | none (new path) | Step 104 (gated by D-116) |
| P10 | `C_x` scale dispersion hook (`Aero.cx_scale`) | 2 | S | none | Step 105 |
| P11 | Power-on/off base drag, surface-finish correction | 1 | S-M | - | defer (user table covers) |
| P12 | Brake asymmetric deployment, brake shielding | 2 | M | - | defer |
| P13 | Convergence study, one-at-a-time sensitivity | paper/2 | S | none | Step 110 (paper track) |
| B26 | Config = data (thin slice: provenance + derived mass history export) | 1 | S-M | none | Step 100 + D-113 |
| B28 | Pad slide at low T/W | 1 | M | MOVES low-T/W results | defer; filter in sweep |
| B29 | Drogue + main | - | M | none | defer |

### E. Paper deliverables (parallel track)

13 `\comptodo` (gravity, thrust T vs T0, mass models, aero models, atmosphere tiers, wind, Dryden ensemble, Coriolis, integrators,
sampled vs continuous brake — `models.tex`; rail, recovery triggers, brake laws — `other-dynamics.tex`) and 4 simulator-output `\figtodo`
(aero example table plot models:460, wind profile models:640, demo trajectory models:967, recovery/brake time series
other-dynamics:109) -> Step 110. 3 `\figtodo` are TikZ diagrams (models:115, other-dynamics:35, rocket-2d:78): not simulator work.

## 35.3 Phase 2.17 scope

### In (the minimum that unblocks goals 1-3)

| Block | Items | Why in |
|---|---|---|
| Safety net + bugs | P7 analytic suite, G5, G19, C1, C2, C4 (Step 97) | Cheap, make later numbers trustworthy; G5 matters when sweeping motors with hand-typed `I_sp`; analytic closed-form coast is the oracle for the brake and the predictor |
| Thrust/mass truth | G6, P2 (Step 98) | Sweep and dispersions need `T_0`-driven mass flow and `k_J`/`k_t`; `A_e` populated for new motors (<= 1% thrust below 3 km) |
| Aero data semantics | G12 + C3 (Step 99) | A motor changes the CG (heavier aft motor -> smaller margin). With the arm fixed (`l1_m`) the sweep cannot see instability; CFD/RASAero tables come as `l_p` from the nose and in the standard `C_m` sign — silent wrong stability otherwise |
| Motor sweep (M1) | B26 thin slice, P8, App 3 rebuilt on `Motor`/`Scenario` (Step 100); config 2 (Step 101) | Goal 1 itself |
| Brake in aero | G21 table `f_b` axis (Step 102) | Goal 2: brake changes CP/`C_z`; CFD is already the user's route (App 2) |
| Actuator | P5 (Step 103) | Max spec depends on how fast the brake opens (authority vs time); controller needs it |
| Runtime | P9 (Step 104, gated) | Ensembles of sampled runs are 100x slower than RK45 |
| Dispersions + spec (M2) | P1, P3, P10, App 4 extension (Steps 105-106), App 2 `f_b` conditions (Step 111) | Goal 2 itself |
| Controller (M3) | P4, P6 + estimator, harness (Steps 107-109) | Goal 3 |
| Paper track | Step 110 (+ non-code review work, §35.9) | Replace todos by simulator output; independent of the above except ordering after Step 98 |

### Out, with reason

| Item | Reason |
|---|---|
| 3D, `dynamics3d`, quaternions | The user's goals are on the vertical/2D channel; scaffold stays untouched |
| G15/G17 vertical wind, Dryden `w` | `sigma_w ~ 0.1 W20 ~ 0.5-1 m/s` vs `v ~ 100-300 m/s`: < 1% in `q`, below other dispersions; add when a high-fidelity disturbance study is requested |
| G8 jet damping, `C_m,q`, G7 | Pitch channel; `C_m,q` has no value (`\restodo`); estimate G8 magnitude first (model-proposals: ~10% of fin damping) |
| G10 multi-component aero | L effort; the table with `f_b` axis serves the brake without a component build-up |
| G9 linear mass models, full B26 | Endpoints inversion already matches burnout/launch exactly; see D-113 |
| G1-G4, G13, G18, G20, G22-G24, B28, B29 | Not on the critical path to any goal; each listed with its pin impact above |
| Everything `\restodo` | Research-blocked (orchestrator calls the research agent when the user picks one) |

## 35.4 Design

No stack change: Python 3.12, numpy, scipy, matplotlib, pytest (`requirements.txt`); stdlib `concurrent.futures` for ensembles. No new
dependency. No Context7 lookups were needed (no new library); scipy/numpy facts relied on are already pinned in CLAUDE.md traps.

Layering rule (unchanged, extended): `sim/` = deterministic physics + plant-side hooks, single run, offline. `configs/` = data.
`apps/` = consumers (sweeps, ensembles, sizing). **New** `controllers/` = flight software under design (estimator + law); it
imports `sim/` and registers into `sim.control` at import; `sim/` never imports `controllers/`. Rationale: controller experiments
churn constantly and must not touch the physics package or its pins.

### 35.4.1 New / changed `Params` fields (every default reproduces today's numbers bit-for-bit)

| Group.field | Default | Meaning | Ticket |
|---|---|---|---|
| `thrust.k_J` | 1.0 | amplitude scale of the thrust curve (impulse scatter) | 98 |
| `thrust.k_t` | 1.0 | time scale of the curve (burn-time scatter, grain temperature) | 98 |
| `aero.l_p` | 0.0 | CP station from nose [m]; `> 0` switches the arm to `l_p - l_g(t)` for all three models | 99 |
| `lengths.l_g` | 0.0 | constant CG station from nose [m]; read only when `aero.l_p > 0` (or an `l_p_m` table) and the mass model is off | 99 |
| `aero.cm_convention` | `"code"` | `code` (positive `C_m` nose-down, stable <=> `C_m,alpha > 0`) or `standard`; applied at table/coefficients load (sign flip of `C_m`, `C_m,alpha`, `C_m,q`) | 99 |
| `aero.cx_scale` | 1.0 | multiplier on `C_x` (dispersion hook; skipped when `== 1.0`) | 105 |
| `atmosphere.dT_K` | 0.0 | ISA launch-day temperature offset (skipped when `== 0.0`) | 105 |
| `control.airbrake_aero` | `"additive"` | `additive` (today) or `table` (brake from the `f_b` axis; `airbrake_Cd/S_max` ignored) | 102 |
| `actuator.model` | `"ideal"` | `ideal` or `rate_limited` | 103 |
| `actuator.rate_open`, `rate_close` [1/s], `f_min`, `f_max`, `delay_ticks` | inf, inf, 0, 1, 0 | rate limits (fraction per second), range, command delay in ZOH ticks | 103 |
| `sensors.*` (`baro_sigma_m`, `baro_tau_s`, `baro_quant_m`, `baro_bias_m`, `seed`) | 0, 0, 0, 0, 0 | barometric-altitude channel; all zero = truth passthrough | 108 |
| `control.*` (law gains/onboard model: `kp`, `ki`, `kd`, `onboard_mass`, `onboard_CdA0`, `onboard_CdA_brake`, ...) | 0 | read only by registered sampled laws | 107 |

`Actuator` and `Sensors` are new groups of `Params` (the dotted-path `replace` already supports arbitrary groups). `Aero.l_ref`
handling: D-118.

### 35.4.2 Thrust and mass (Step 98)

```
T_curve(t)            = interp of the motor file (unchanged)
thrust_stand(t, p)    = (k_J / k_t) * T_curve(t / k_t)                       # "T_0": stand thrust, what the motor file says
thrust(t, s, p)       = thrust_stand + A_e (p_ref - p_amb)  (while thrust_stand > 0)   # unchanged semantics
mass_flow(t, p)       = -T_curve(t / k_t) / (k_t * I_sp * g0)        # amplitude NOT scaled: same propellant, any k_J
dydt[M]               = mass_flow     # replaces -thrust(t,y,p)/(I_sp g0); clamped: 0 when y[M] <= m_d
```
Invariants (tests): burned mass `= m_prop` for any `k_J, k_t > 0`; impulse of `thrust_stand = k_J * J`; with `k_J = k_t = 1`,
`A_e = 0` every pinned flight is bit-identical (the scaling branch is skipped by `if p.thrust.k_J == 1.0 and p.thrust.k_t == 1.0`).
`A_e` for new motors comes from the nozzle exit diameter the user supplies; K570 stays `A_e = 0` unless D-112 says otherwise.

### 35.4.3 Aero table v2 (Step 99, extended Step 102)

CSV header comments (`# key: value`) carry metadata; columns:
`alpha_deg, M, [f_b,] C_A, C_N, C_m, (l1_m | l_p_m)`. Rules:
- exactly one of `l1_m` (legacy arm CoP->CoG [m], today) or `l_p_m` (CP station from the nose [m]) — never both.
  Arm used by dynamics = `l1_m` (legacy) or `l_p_m - l_g(t)` with `l_g(t) = mass.cog_position` (mass model on) or the constant
  constant `lengths.l_g` (mass model off; fail-fast if `l_g == 0` while `l_p` is used).
- `# cm_convention: code | standard` (default `code`); `standard` flips `C_m` on load.
- optional `f_b` column: rectangular grid in `(f_b, M)` x `alpha`; interpolation: `alpha` via `np.interp`, `M` and `f_b` bracketed and
  linearly blended, both clamped at the edges (no extrapolation, same as M today). A table with an `f_b` column used with
  `control.airbrake_aero = "additive"` is read at `f_b = 0` only; `airbrake_aero = "table"` on a table without `f_b` is a
  fail-fast error at `assemble`.
- `aero.coefficients(t, y, p, flow, hold=None, fb=0.0)`: `fb` is computed once per RHS call in `dynamics.derivatives` (from
  `control.airbrake_deploy_fraction`) and passed down; today it is evaluated inside `aero_force_body` only.
- Axial-flow factor (D-93/D-94a) still multiplies `C_A` of the tail-first-incapable tables exactly as now; the brake's contribution
  is inside the table, so no separate factor is applied in `table` mode.
- Static margin `(l_p - l_g(t))/d_ref` is exposed by `sim/report.py` as a time series for every run with `aero.l_p > 0` or an
  `l_p_m` table (used by the sweep as a filter and by plots).

The legacy additive brake (`A_brake = q Cd S_max f_b axial_flow_factor`) is left untouched and remains the default; it equals the
paper's simplest case `Delta C_x = C_{D,b} S_b f_b / S`.

### 35.4.4 Sampled-data chain (Steps 103, 107, 108)

```
tick k (period T_s, fixed, RK4 or segmented RK45)
  channel "airbrake"(t_k, y_k, p, prev) ->
     meas_k , sens_state_k  = sensors.measure(t_k, y_k, p, prev.sens_state)      # baro: lag, noise N(seed, k), quantisation
     cmd_k  , ctrl_state_k  = law(t_k, meas_k, p, prev.ctrl_state)              # estimator + law, registered by name
     cmd_eff_k              = delay buffer (delay_ticks) of cmd
     f_k                    = actuator value at t_k = value of prev's ramp at t_k  (continuous, f_0 = 0)
     returns AirbrakeHold(cmd_eff_k, f_k, t_k, ctrl_state_k, sens_state_k)       # NamedTuple, the channel's `prev`
airbrake_deploy_fraction(t, y, p, hold) =                                       # called every RHS stage
     hold value is float            -> that float                                   # legacy, ideal actuator, unchanged
     hold value is AirbrakeHold     -> clip(f_k + clip(cmd_eff - f_k, -r_close dt, +r_open dt), f_min, f_max),  dt = t - t_k
```
Closed form: with the command constant over a tick, the rate-limited actuator is a ramp toward the command; no extra state
in `y` (the 7-element state vector and all pins are unchanged). Noise is stateless: `np.random.default_rng([seed, k])`
(counter-based) so a tick re-evaluation is bit-identical. A first-order actuator lag is not included (D-114).

Law registry in `sim/control.py`: `register_sampled_law(name, fn)`; `fn(t_k, meas, p, state) -> (cmd, state)`;
`control.airbrake_model` accepts `none | proportional | full` (memoryless, unchanged) or any registered name (requires
`solver.sample_rate_hz > 0`; fail-fast at `run_sim` otherwise). `meas` is a small NamedTuple `Measurement(h_baro, a_imu=None)`; the
controller never sees `y`. The truth `y_k` is passed only to `sensors.measure`.

`controllers/` (flight software): `estimator.py` (alpha-beta filter on baro altitude -> `h_hat`, `v_hat`), `laws.py`
(`proportional_drag`, `pi_apogee` with anti-windup), registered at import of `controllers`. Onboard model uses the **nominal**
mass and `C_dA` (`control.onboard_*`), not the truth, so dispersions create real model mismatch.

Drag-aware predictor (closed form for vertical ballistic coast, from model-proposals): with `k = 1/2 rho_hat (C_x S + C_D,b S_b f_b)`,
`h_a = h + (m/(2k)) ln(1 + k v_z^2/(m g))`; `rho_hat` from the ISA at `h_hat` (onboard), or a nominal constant. Oracle test: equals the
simulated apogee of a drag-only vertical coast to < 0.1%.

### 35.4.5 Ensemble runner and sweep outputs (Steps 100, 105, 106)

`apps/common/ensemble.py` (apps layer, `sim/` stays single-run):
```
Dispersion(name, apply, draw)    # apply(obj, value) -> obj ; draw(rng) -> value; stage "scenario" | "params"
run_ensemble(base, dispersions, n, seed, evaluate, workers=None) -> EnsembleResult   # structured numpy table + percentiles
```
- Per-sample RNG from `np.random.SeedSequence(seed).spawn(n)`; sample `i` is reproducible independent of `workers` (test:
  `workers=1` equals `workers=4`).
- `evaluate(config) -> dict[str, float]` top-level picklable function (Windows `spawn`); executor `ProcessPoolExecutor`.
- "scenario"-stage dispersions (airframe mass/CG/I, motor, rail) re-run `configs.schema.assemble` per sample because `Weight` is
  derived there; "params"-stage ones (`thrust.k_J`, `aero.cx_scale`, `atmosphere.dT_K`, `wind.*`, `site.rail_angle_deg`) use `params.replace`.
- Provided constructors: `normal_path`, `uniform_path`, `lognormal_path`, `airframe_mass`, `airframe_cg`, `wind_speed_dir`.

Motor sweep (App 3 v2, `apps/motor_selection/scenario_sweep.py`): input = `Scenario` (rocket config, site, weather) + list of `Motor`
registry names + constraints; per motor `assemble(replace(scenario, motor=m))` then `run_sim`. Output row: `J_total`, `t_burn`, T/W at
liftoff, rail-exit speed, `h_apogee` (brake closed), `h_apogee` (brake open, if a brake spec is given), `v_max`, `M_max` (vs table
range), `q_max`, `a_max`, static margin at rail exit and at burnout and minimum over the burn, `m_burnout`, feasibility flags,
distance to the target apogee. Ranking: feasible first, then `|h_apogee - target|`; infeasible rows keep the failed constraint
name. The old `MotorEntry`/`overrides` path and its tests are untouched.

Max-spec app (`apps/airbrake_sizing/max_spec.py`): for each `(rocket config, motor)`: (i) `h_closed`, `h_open` (brake open from the
chosen trigger) nominal; (ii) ensemble (Step 105) of the required `C_dA` for the target apogee via App 4's scalar solver per
sample (bounded, with a "infeasible: even full brake overshoots" flag); (iii) spec = percentile (default P95/P99, D-117) of required
`C_dA` divided by the allowed `f_max` (headroom for the controller), with implied `S_b = C_dA/C_D,b`; (iv) load numbers: peak
`q`, `M`, brake force `F_b = q C_D,b S_b` at the worst deploy instant, time window of deployment, deployment speed.
Reports both configs side by side; CSV + PNG into `output/`.

### 35.4.6 Directory changes

```
sim/
  thrust_curve.py   + thrust_stand, mass_flow            (98)
  aero.py           + l_p arm, cm_convention, f_b axis   (99, 102)
  control.py        + register_sampled_law, AirbrakeHold, actuator ramp   (103, 107)
  sensors.py        NEW baro channel (physics of the sensor, seeded)       (108)
  sampling.py       channel value may be AirbrakeHold (contract extended, float still valid)   (103)
  integrate.py      + segmented RK45 sampled path (gated, D-116)           (104)
  report.py         + static-margin series                               (99)
  params.py         + fields of 35.4.1, groups Actuator, Sensors          (98..108)
controllers/        NEW  __init__.py estimator.py laws.py                  (107, 108)
configs/
  motors/           + real motors (from user's .eng files)                (100)
  rockets/          + second configuration                                (101)
  scenarios/        + scenario(s) for configuration 2 (and 1 if real)     (101)
data/
  motors/           + user .eng files   aero/ + config tables (v2 format)   (100, 101)
apps/
  common/ensemble.py                        NEW (105)
  motor_selection/scenario_sweep.py         NEW (100)
  airbrake_sizing/max_spec.py               NEW (106)
  airbrake_control/{harness.py,metrics.py}  NEW (109)
  paper_figures/                            NEW (110)
  cfd_conditions/                           + f_b condition sets (111)
tests/              one test file per new module + test_analytic.py (97)
```

## 35.5 Non-functional decisions

- **Determinism.** `sim/` stays deterministic and offline. All randomness is seeded and stateless per tick/sample (counter-based
  `default_rng`); ensembles are reproducible regardless of worker count.
- **Pin policy (D-110).** Every change is opt-in; defaults reproduce current numbers. Full-suite run as the gate of every step;
  any moved pin is reported, not silently re-pinned. RK45 pins stay on numpy 2.5.4 / scipy 1.18.1 (D-77).
- **Performance.** Ensembles in parallel across processes (Windows: top-level functions, `if __name__ == "__main__":`). Sampled-data
  runs: RK4 dt = 5 ms with `f_s = 20-50 Hz` as the working point (1.3 s/flight) until segmented RK45 (Step 104) lands; the dt
  choice must be validated by the integrator study (Step 110: |apogee difference| < 0.1 m vs dt = 1 ms).
- **Aero validity.** `constant`/`linearized` models are blind above M ~ 0.8: sweeps and sizing on those emit `MachRangeWarning` and the
  report marks the numbers "wiring only". Credible goal-1/2 numbers require the table model with the user's CFD/RASAero data.
- **Provenance (B26 thin).** Derived data carries a `provenance` string/dict (model name + inputs + source file hash). Solver reads
  inputs, not provenance. GUI/recalc is later.
- **Units/frames.** SI; `l_p` and stations measured from the nose tip (+ aft); `f_b` in [0, 1]; angles internally in rad (unchanged).
- **LaTeX.** Not edited anywhere in this phase. Step 110 produces tables/plots in `output/paper/`; pasting is a separate, user-approved action.
- **Windows/Yandex.Disk.** No new long blocking calls; the full suite and ensembles run in the background (<= 240 s per foreground call).

## 35.6 Tickets (Steps 97-112)

Format per ticket: boundaries, assignee, `depends_on`, `parallel_safe`, spec slice (file + section), tests first (TDD), pin
impact, acceptance. All tickets: developer reads only the cited slice (`Grep -n` the anchor in this file, then `Read` with
offset/limit); full suite in the background as the step gate; one step = one commit `Step NN (Phase 2.17): ...`. Nothing is
`parallel_safe` because every ticket either edits shared `sim/params.py` / `sim/dynamics.py` or depends on another; notes on safe
concurrency are given where files are really disjoint.

### Milestone M1 — motor sweep usable for configuration 2

#### [Step 97] Safety net + B32 bug fixes
- **Goal:** 1, 2, 3 (trust). **Boundaries:** `sim/dynamics.py`, `sim/control.py`, `sim/flow.py`, `sim/params.py` (comment only), `sim/forces.py` (comments only), `tests/test_analytic.py` (new), `tests/test_dynamics.py`, `tests/test_control.py`, `tests/test_flow.py`.
- **Assignee:** developer. **depends_on:** []. **parallel_safe:** false (touches `dynamics.py`).
- **Spec slice:** §35.2 rows G5, G19, C1, C2, C4; §35.4.1 (`Aero.l_ref` note) and D-118.
- **Tests first:** (1) `test_analytic.py`: vacuum vertical shot apogee `= v0^2/(2 g)` (thrust and drag off, constant gravity); drag-only coast with constant `C_x` and constant mass matches the closed form `h + (m/2k) ln(1 + k v^2/(m g))` within a tolerance justified by the density change over the rise (ticket states the tolerance; suggest 1%); canopy terminal speed `sqrt(2 m g / (rho C_D S))` within 1%. (2) `y[M]` never below `m_d` for an `isp` motor whose `I_sp` is too low (burns more than `m_prop`), no NaN downstream. (3) Under canopy with `gravity.earth_rotation=True` the acceleration includes the Coriolis term exactly once (compare with the explicit expected vector); with the flag off, bit-identical to before. (4) air-brake `after_apogee` is not triggered for `t < 0.1 s` even if `v_z > 0`, triggered after. (5) `Re` uses `d_ref` when `l_ref == 0.0`, `l_ref` otherwise (D-118 option c).
- **Fix:** `dynamics.py` L348 `a_chute = (F_i + F_chute)/m` — build from `a_i` (which already contains Coriolis): `a_chute = a_i + F_chute/m`, keeping `F_i`-based result identical when Coriolis is off (verify bitwise: `(F_i + F_chute)/m` vs `F_i/m + F_chute/m` differ in rounding — the developer must keep the exact legacy expression when `earth_rotation` is False, add Coriolis only as an extra term otherwise). Mass floor: `dm_dt = 0.0` when `y[M] <= m_d` (only branch change; before burnout identical). `_trigger_after_apogee`: `t >= 0.1 and y[VZ] > 0.0`. `flow.py` Re length fallback. C4: fix the comments only.
- **Pin impact:** none expected; **last-bit?** for mass-model flights (floor sliver at burnout) and for any test that asserts the dropped-Coriolis chute value. The developer classifies every moved test; moved pins are reported to the orchestrator, never re-pinned silently (D-110).
- **Acceptance:** new tests green; full suite green with zero changed expectations, or a list of moved pins with old/new values for the user's decision.

#### [Step 98] Stand thrust `T_0`, mass flow, impulse/time scatter
- **Goal:** 1, 2. **Boundaries:** `sim/thrust_curve.py`, `sim/dynamics.py` (one line), `sim/params.py` (`Thrust.k_J`, `Thrust.k_t`), `tests/test_thrust_curve.py`, `tests/test_mass.py`, `tests/test_dynamics.py`.
- **Assignee:** developer. **depends_on:** [97]. **parallel_safe:** false.
- **Spec slice:** §35.4.2, §35.4.1 (thrust rows), D-112.
- **Tests first:** burned mass `= m_prop` for `k_J, k_t` in {0.9, 1.0, 1.1}; impulse of `thrust_stand = k_J J`; burnout time `= k_t t_b`; `A_e > 0` case: `mass_flow` independent of altitude and of `A_e`, while `thrust` changes; `k_J = k_t = 1`, `A_e = 0` bit-identical to the current `thrust()` on the K570 and synthetic curves; mass-model apogee for demo unchanged (pin).
- **Pin impact:** none at defaults. If D-112 selects "populate `A_e` for K570" the demo pins MOVE (re-pin step, separate, only with "yes").
- **Acceptance:** the new `Motor`-level field for the nozzle exit diameter (`Motor.d_exit`, OPT, m) maps to `Thrust.A_e` in `assemble`; template doc updated (`tests/test_template_docs.py` green).

#### [Step 99] Aero table v2: CP from the nose, `C_m` convention
- **Goal:** 1, 2. **Boundaries:** `sim/aero.py`, `sim/dynamics.py` (arm line only), `sim/params.py` (`Aero.l_p`, `Aero.cm_convention`, `Lengths.l_g`), `sim/report.py` (static-margin series), `data/aero/example.csv` (add a v2 sibling `example_v2.csv`; do not edit the old one), `configs/rockets/_TEMPLATE_rocket.py` (fields), `tests/test_aero.py`, `tests/test_report.py` (new).
- **Assignee:** developer. **depends_on:** [98]. **parallel_safe:** false.
- **Spec slice:** §35.4.3, D-111.
- **Tests first:** loader accepts `l1_m` xor `l_p_m` (both -> error); with `l_p_m` and mass model on, the arm equals `l_p_m - cog_position(m_p)` at 3 times along the burn (CG travels aft -> margin shrinks); `# cm_convention: standard` flips `C_m` exactly; `static_margin_cal(t)` series; legacy `example.csv` flights are bit-identical (pin); unknown/missing `l_g` with `l_p` and mass model off -> fail-fast.
- **Thrust arm:** `aB` keeps today's expression for legacy configs; for `l_p` configs the developer derives the thrust point station from `Sections.L_total` or documents that `misalign_deg` must be 0 (on-axis thrust has zero moment). Choose the smaller change; record in the step notes.
- **Pin impact:** none (all opt-in). Changing the code's `C_m` convention is NOT part of this step (D-111 option c).
- **Acceptance:** a v2 table with `standard` convention and a stable airframe flies stable; flipping the declared convention makes the static-margin diagnostic report instability (negative margin warning).

#### [Step 100] Motor sweep v2 on `Motor`/`Scenario` + B26 thin slice
- **Goal:** 1. **Boundaries:** `apps/motor_selection/scenario_sweep.py` (new), `apps/common/flight_stats.py` (additive fields), `configs/motors/*` (new real motors), `data/motors/*` (user `.eng`), `sim/motor_file.py` (`derive_history`, read-only), `run_motor_sweep.py` (new flag `--scenario`), `tests/test_scenario_sweep.py` (new).
- **Assignee:** developer. **depends_on:** [98, 99]. **parallel_safe:** false.
- **Spec slice:** §35.4.5 (motor sweep paragraph), D-113, §35.8 (motor data).
- **Tests first:** sweep over 2 synthetic `.eng`/CSV motors on the demo scenario: row fields present and ordered; infeasible motor (T/W < threshold, `M_max` beyond table range, margin < 1 cal) flagged with the constraint name and ranked last; `derive_history(motor)` returns `t, m(t), l_cg(t), I(t)` consistent with the `endpoints` model at launch/burnout to 1e-12 and with `y[M]` of a simulated burn to 1e-9; provenance dict carries model name, inputs and source-file hash; old `compare_motors` tests untouched and green.
- **Pin impact:** none.
- **Acceptance:** `python run_motor_sweep.py --scenario <name> --motors a,b,c --target <m>` prints/saves the table and overlay; works with `aero.model="table"` v2.

#### [Step 101] Second rocket configuration as data
- **Goal:** 1 (and 2). **Boundaries:** `configs/rockets/<name2>.py`, `configs/scenarios/<name2>.py`, `data/aero/<name2>.csv`, registries, `tests/test_config2.py`, `tests/config_variants.py` (additive).
- **Assignee:** developer. **depends_on:** [99]. **parallel_safe:** false (may run concurrently with Step 100 once 99 has landed: disjoint files, the orchestrator decides).
- **Spec slice:** §35.8 (what the user supplies); template docs `configs/rockets/_TEMPLATE_rocket.py`.
- **Tests first:** config loads; assembled `Weight` consistent (launch mass = airframe + motor, CG inside the vehicle, `I > 0`); table covers the Mach range of a smoke flight (no clamp warnings); static margin >= 1 cal at rail exit and burnout for the baseline motor; flight smoke (`apogee > 0`, lands under canopy).
- **Pin impact:** none (new files). Provenance (`notes`) of every number is filled in (source: CAD/CFD/measurement).
- **Acceptance:** the sweep from Step 100 runs on this scenario with the user's candidate motors. **M1 reached.**

### Milestone M2 — maximum air-brake specification for both configurations

#### [Step 102] Air brake as a table axis (`f_b`)
- **Goal:** 2, 3. **Boundaries:** `sim/aero.py`, `sim/forces.py`, `sim/dynamics.py`, `sim/params.py` (`Control.airbrake_aero`), `tests/test_aero.py`, `tests/test_forces.py`, `tests/test_control.py`.
- **Assignee:** developer. **depends_on:** [99]. **parallel_safe:** false.
- **Spec slice:** §35.4.3 (`f_b` rules), D-109.
- **Tests first:** table with `f_b` in {0, 1}: coefficients at `f_b = 0.5` are the linear blend; `f_b = 0` plane equals the brake-closed table exactly; `airbrake_aero="table"` with a table lacking `f_b` -> error at `assemble`; additive path bit-identical to today (pin); equivalence test: a table whose `f_b = 1` plane has `C_A = C_A,0 + C_D,b S_b/S` reproduces the additive brake apogee to < 0.01% (constant `C_D,b`); `l_p` shifts with `f_b` change the static margin (the Farha effect) and the diagnostic shows it.
- **Pin impact:** none. **Acceptance:** `f_b` computed once per RHS call (profile: no extra aero/atmosphere evaluations vs today).

#### [Step 103] Actuator model (rate/range/delay) in the sampled chain
- **Goal:** 2, 3. **Boundaries:** `sim/control.py`, `sim/sampling.py`, `sim/params.py` (`Actuator` group), `sim/integrate.py` (guard messages only), `tests/test_control.py`, `tests/test_sampling.py`, `tests/test_actuator.py` (new).
- **Assignee:** developer. **depends_on:** [97]. **parallel_safe:** false.
- **Spec slice:** §35.4.4 (actuator ramp, `AirbrakeHold`), D-114.
- **Tests first:** command step 0->1 with `rate_open = 2/s` gives `f_b(t) = 2 (t - t_0)` until 1, analytically, evaluated at RK4 stage times; `f_min/f_max` clip; `delay_ticks = 2` delays the command by `2 T_s`; `actuator.model="ideal"` returns the float and keeps `hold.values["airbrake"]` a float (legacy tests unchanged); unknown law name raises at `run_sim` entry; state vector length 7 unchanged.
- **Pin impact:** none. **Acceptance:** a `full`-law flight with `rate_open = inf` equals the legacy sampled flight bit-for-bit.

#### [Step 104] (gated by D-116) Segmented RK45 for sampled-data mode
- **Goal:** 3 (runtime), 2. **Boundaries:** `sim/integrate.py` (new `_run_sampled_adaptive`), `tests/test_integrate.py`.
- **Assignee:** developer. **depends_on:** [103]. **parallel_safe:** false.
- **Spec slice:** §35.5 (Performance); D-116. Do only if the measured cost of the Step 105 ensemble at RK4 dt = 5 ms exceeds the D-116 threshold.
- **Tests first:** on a smooth scenario, apogee/impact time agree with fixed-step RK4 (dt = 1 ms) to < 0.1 m / 1 ms; ZOH semantics: the hold is constant across each segment and events (rail exit, burnout, apogee, ground) are detected inside a segment with the 0.1 s guard; wall time for the demo sampled run at 20 Hz is >= 5x faster than RK4 dt = 1 ms.
- **Pin impact:** none (new path; default RK45 and RK4 paths untouched). **Acceptance:** `solver.method="RK45"` with `sample_rate_hz > 0` accepted; old guard message updated.

#### [Step 105] Dispersion hooks + ensemble runner
- **Goal:** 2, 3. **Boundaries:** `sim/params.py` (`Aero.cx_scale`, `Atmosphere.dT_K`), `sim/aero.py` (one multiply behind `!= 1.0`), `sim/atmosphere.py` (ISA offset behind `!= 0.0`), `apps/common/ensemble.py` (new), `tests/test_ensemble.py` (new), `tests/test_atmosphere.py`.
- **Assignee:** developer. **depends_on:** [98]. **parallel_safe:** false.
- **Spec slice:** §35.4.5 (ensemble), §35.4.1.
- **Tests first:** `cx_scale = 1.1` scales apogee loss monotonically and `=1.0` is bit-identical; `dT_K = +15` lowers density by the ISA ratio (analytic) and `=0` is bit-identical; ensemble: same seed -> same table; `workers=1` equals `workers=4`; sample statistics of a drawn parameter match the requested mean/sigma (`n = 2000`, 3 sigma tolerance); `evaluate` failure of one sample is recorded (NaN + reason), not fatal; spawn-safe on Windows (test uses a top-level function).
- **Pin impact:** none. **Acceptance:** 100-sample RK45 ensemble on the demo completes in well under a minute on 4 workers; the RK4-sampled timing is recorded for D-116.

#### [Step 106] Maximum air-brake specification app
- **Goal:** 2. **Boundaries:** `apps/airbrake_sizing/max_spec.py` (new), `apps/airbrake_sizing/targets.py` (additive specs), `run_airbrake.py` (new flag), `tests/test_max_spec.py` (new).
- **Assignee:** developer. **depends_on:** [101, 102, 103, 105]. **parallel_safe:** false.
- **Spec slice:** §35.4.5 (max-spec paragraph), D-117, §35.8 (brake and mission data).
- **Tests first:** synthetic case with known answer: constant mass, constant `C_x`, no wind: `h_closed`, `h_open` and required `C_dA` agree with the closed-form coast to < 0.5%; infeasible case (target above `h_closed`) returns "no brake needed"; target below `h_open` returns "infeasible: even full brake overshoots by X m"; percentile spec is monotone in dispersion width; output files exist.
- **Pin impact:** none (App 4 untouched; new module imports `solve_cda`). **Acceptance:** for each of the two configurations and each candidate motor: table `h_closed / h_open / C_dA_req (nominal, P95, P99) / S_b implied / F_b,max / q, M at deploy`. **M2 reached.**

### Milestone M3 — controller design starts

#### [Step 107] Sampled laws registry + drag-aware predictor law
- **Goal:** 3. **Boundaries:** `sim/control.py` (`register_sampled_law`), `controllers/` (new `laws.py`, `estimator.py` stub), `sim/params.py` (`Control` gains), `tests/test_control.py`, `tests/test_controllers.py` (new).
- **Assignee:** developer. **depends_on:** [103]. **parallel_safe:** false.
- **Spec slice:** §35.4.4 (law registry, predictor).
- **Tests first:** predictor equals the simulated drag-only coast apogee within 0.1%; with an ideal sensor and ideal actuator `proportional_drag` brings the demo apogee to the target within the controller's own steady error (open-loop sanity); registered law is called once per tick with the `prev` state; a law with an integrator keeps state across ticks and resets between runs; `proportional` (legacy, `h + v^2/2g`) numbers unchanged.
- **Pin impact:** none. **Acceptance:** comparison table `none / full / proportional / proportional_drag` on the nominal flight.

#### [Step 108] Baro sensor channel + estimator
- **Goal:** 3. **Boundaries:** `sim/sensors.py` (new), `sim/params.py` (`Sensors` group), `sim/control.py` (channel composes sensor -> law), `controllers/estimator.py`, `tests/test_sensors.py` (new).
- **Assignee:** developer. **depends_on:** [103, 107]. **parallel_safe:** false.
- **Spec slice:** §35.4.4 (chain), D-115.
- **Tests first:** all-zero `Sensors` returns the truth altitude (pressure altitude from ISA vs true: documented exact-inverse); noise: reproducible per `(seed, k)`, sigma matches the setting over 5000 ticks; lag: first-order response with `tau`; quantisation; alpha-beta filter converges on a noiseless ramp and attenuates noise by the expected ratio; `v_hat` error on a coast within bound.
- **Pin impact:** none. **Acceptance:** closed loop with `baro_sigma_m = 1`, `tau = 0.1 s` runs deterministically.

#### [Step 109] Closed-loop harness and metrics
- **Goal:** 3. **Boundaries:** `apps/airbrake_control/{harness.py,metrics.py}` (new), `run_airbrake_control.py` (new), `tests/test_airbrake_control.py` (new).
- **Assignee:** developer. **depends_on:** [105, 107, 108]. **parallel_safe:** false.
- **Spec slice:** §35.4.4, §35.4.5.
- **Tests first:** metrics on a scripted run (apogee error, saturation fraction, time at `f_max`, actuator travel, brake duty); gain sweep returns one row per gain; the harness reproduces the nominal numbers of Step 107 for the same settings.
- **Pin impact:** none. **Acceptance:** ensemble over the Step 106 dispersions gives the apogee-error distribution and the saturation probability for each config; this is the baseline that controller design iterates on. **M3 reached (design loop exists).**

### Parallel / paper track

#### [Step 110] Paper figures and tables app
- **Goal:** paper (none of 1-3). **Boundaries:** `apps/paper_figures/` (new: one function per `\comptodo`/`\figtodo`), `run_paper_figures.py`, `output/paper/` (git-ignored), `tests/test_paper_figures.py` (smoke: each generator returns a non-empty table within a time budget on a cut-down grid).
- **Assignee:** developer. **depends_on:** [98] (T vs `T_0` figure needs the split; sampled-vs-continuous needs Step 103 for the final form but the current RK4 hold suffices). Disjoint files from everything else: may run concurrently with any ticket after 98 (orchestrator decision). **parallel_safe:** false (rule: depends_on not empty).
- **Spec slice:** §35.2 section E; each todo's text gives the table columns; do **not** edit LaTeX.
- **Tests first:** one smoke test per generator; reproducibility (same inputs -> byte-identical CSV).
- **Pin impact:** none. **Acceptance:** 13 `\comptodo` tables/plots + 4 `\figtodo` plots written to `output/paper/` with a manifest (todo id -> file). Delivered in three slices (gravity/thrust/mass/aero; atmosphere/wind/Dryden/Coriolis; integrators/sampled/rail/recovery/brake) so review can start early.

#### [Step 111] CFD conditions with the `f_b` dimension
- **Goal:** 2. **Boundaries:** `apps/cfd_conditions/select_conditions.py`, `tests/test_cfd_conditions.py` (new; check `tests/test_apps_common.py` for existing coverage first).
- **Assignee:** developer. **depends_on:** [102]. **parallel_safe:** false.
- **Spec slice:** §35.4.3; App 2 docstring.
- **Tests first:** requested `f_b` levels produce one condition set per level using the flight of the brake-open case; default (no levels) bit-identical to today.
- **Pin impact:** none. **Acceptance:** the user gets the (M, alpha, Re, f_b) list to feed CFD for the whole-rocket table.

### Inserted steps

#### [Step 112] Large-α extension of table aero (Jorgensen, opt-in)
- **Goal:** 1, 2, 3 (any table-aero flight under RK45 must get through tail-first descent). **Boundaries:** `sim/aero.py` (`_table_coeffs` branch, new helpers, `validate`, `reset_oob_warning`), `sim/params.py` (`Aero` fields below), `sim/integrate.py` (ONE line: `aero.reset_oob_warning()` at `run_sim` entry), `configs/rockets/_TEMPLATE_rocket.py` (fields, `REQ|OPT`), `tests/test_aero_oob.py` (new), `tests/test_scenario_sweep.py` (comment at L123 only).
- **Assignee:** developer. **depends_on:** [99] (landed). **parallel_safe:** false (`params.py`, `aero.py` shared).
- **Spec slice:** this ticket + D-120 (§35.12); root cause: `dev/docs/diagnosis-rk45-v2-table.md` (Verdict, Evidence, Recommendation); paper `dev/docs/latex/sections-ai/models.tex` L375-409 (`eq:axial_factor`, `eq:cx_full`, `eq:cz_crossflow`, the `\restodo`); code anchors: `aero.py` `_table_lookup`, `_table_coeffs`, `_cm_to_code`, `_resolve_arm`, `validate`; moment sign: `forces.py` `aero_force_body` (`F = [-qS C_x, -qS C_z]`) and `aero_moment_y` (`-qS d C_m`), `dynamics.py` `_cross_y`.
- **Why (one line):** `np.interp` clamps `C_N, C_m` at the table edge, so at `alpha ~ +-180 deg` they flip sign with the sign of a ~1e-9 transverse velocity: a sliding mode that collapses RK45's step (not stiffness, not `C_m,q`). The extension makes every coefficient continuous through `+-180 deg`.

**112.1 New `Aero` fields (all inert at defaults; D-110 strict opt-in)**

| Field | Default | REQ/OPT | Meaning / source |
|---|---|---|---|
| `table_oob` | `"clamp"` | OPT | `clamp` = today, bit-identical (+ once-per-run warning, 112.5). `jorgensen` = the extension below |
| `oob_blend_deg` | `10.0` | OPT | width `Delta` of the blend band beyond the table edge [deg] (our choice, 112.3) |
| `S_p` | `0.0` | REQ iff `jorgensen` | planform area [m^2]. NO overall-length field exists in `params.py` (grep `L_total` finds nothing in `sim/`), so it is user-supplied. Recipe in the template: body `d_ref * L` (+ fin planform if wanted) |
| `l_pc` | `0.0` | REQ iff `jorgensen` | planform-centroid station from the nose [m]; recipe: `~0.5 L` for a plain cylinder-plus-nose-cone body, shifted aft by fins |
| `C_dn` | `1.2` | OPT | crossflow drag coefficient of a cylinder, constant (paper L401: 1.2 at low crossflow Mach). Mach dependence `C_dn(M sin a)` is NOT modelled (backlog B42) |
| `eta` | `0.0` | OPT | finite-length factor; `0.0` -> derived from fineness `lam = S_p/d_ref^2` (~ L/d) by `np.interp` over `(lam, eta)` = (1, .63), (2, .68), (5, .74), (10, .82), (20, .87), (40, .90), (1000, 1.0) clamped (Hoerner finite-cylinder values as remembered, **UNVERIFIED**: developer checks against the paper's `\cite{jorgensen}` entry / Hoerner, or marks them UNVERIFIED in the step notes; the user may override with an explicit `eta`) |
| `C_x180` | `0.0` | OPT | axial coefficient for tail-first flow; `0.0` -> `C_x(0)` of the table at the current Mach (no invented number; a blunt-base-first body is really higher, ~1.0-1.2 for a flat-ended cylinder, UNVERIFIED) |
| `S_base` | `0.0` | OPT | base area for the potential term [m^2]; `0.0` -> `S` (ratio 1) |

Derivable from existing fields: only `S_base` (`= S`) and `eta` (from `S_p`, `d_ref`). `S_p`, `l_pc` cannot be derived (no length field), hence REQ.

**112.2 Formulas.** `alpha` in `(-180, 180]` deg as given by the flow (`atan2`). Table edges `a_hi = table.alpha[-1]`, `a_lo = table.alpha[0]`. **If `a_lo <= alpha <= a_hi` call the existing code path untouched** (bit-identical, no extra work). Otherwise let `a_e = a_hi` (`alpha > 0`) or `a_lo` (`alpha < 0`), `d = |alpha| - |a_e|`, `tau = min(d/Delta, 1)`, `w = tau^2 (3 - 2 tau)` (smoothstep), `Delta = oob_blend_deg` in rad.

- `C^clamp` = exactly what `_table_coeffs` returns today (including `_table_axial_factor`), for `C_x, C_z, C_m`.
- Helper `Z(a) = sin(2a) cos(a/2)` (odd in `a`; zero at `0, +-90, +-180`).
- Axial: `x0 = lookup(C_A, alpha=0, M)`, `x180 = C_x180 or x0`. `C_x^J = x0 cos^2(a)` for `|a| <= 90`, `C_x^J = -x180 cos^2(a)` for `|a| > 90` (the minus sign is the flow-direction sign the paper obtains through `f(alpha)`; here it is built in, so `f` is NOT applied to `C_x^J`). Even in `a`; `= 0` at `+-90` with zero slope on both sides (C1); `-x180` at `+-180`.
- Normal force (code convention: `A_z = q S C_z`, `F = -A_z z_hat`, `C_z > 0` for `alpha > 0` restoring): `C_z,pot = (S_base/S) Z(a)`, `C_z,cf = eta C_dn (S_p/S) sin(a)|sin(a)|` (the paper's `sin^2` with the sign that makes `C_z` odd: the force opposes the transverse velocity; this resolves the sign half of the `\restodo` for `a > 90`), `C_z^J = C_z,pot + C_z,cf`.
- Moment, each force at its own station, relative to the live CG. The seam applies one arm `l1 = l_p - l_g(t)` (the table's `l_p`, edge-clamped as today, NOT blended) to the whole `C_z`: `M_y = -qS (l1 C_z + d_ref C_m)`. Crossflow at `l_pc` instead of `l_p` adds `(l_pc - l_p) C_z,cf` to the bracket, hence `C_m^J = C_m(a_e) Z(a)/Z(a_e) + (l_pc - l_p(a_e)) C_z,cf / d_ref`, with `C_m(a_e)` and `l_p(a_e)` looked up at `(a_e, M)` (`C_m` already in code convention after load; positive = nose-down). The first term continues the table's residual moment with the potential shape (vanishes at `0, +-180`, odd); the second is the arm correction (negative when `l_pc < l_p`: crossflow acts forward of the CP; if `l_pc < l_g` the crossflow moment destabilises, as physically expected).
- Result: `C = (1 - w) C^clamp + w C^J` for `C_x, C_z, C_m`; `l1` and `C_mq` stay the clamped lookups (continuous, no jump).
- **Smoothness.** At `+-180`: `C_x -> -x180` (continuous, even); `C_z ~ K e|e|`, `C_m ~ K' e|e|` for `e = 180 - |a|` signed through the crossing -> continuous, odd, zero slope at the crossing (the force becomes quadratic transverse drag; no sign jump, so no sliding mode). At `+-90`: `C_x` C1 as above, `C_z` is smooth (`sin^2` branch smooth; `Z(90) = 0`). Table edge: C0 (`w = 0`, `C^clamp(a_e) = table(a_e)`; the slope drops from the table slope to the blend start, same kink as today's clamp). End of band: C1 (`w' = 0`).
- Symmetry (needs an odd-symmetric table: `C_A` even, `C_N, C_m` odd): `C_x(-a) = C_x(a)`, `C_z(-a) = -C_z(a)`, `C_m(-a) = -C_m(a)`.

**112.3 Blend choice and justification.** Smoothstep weight over `Delta = 10 deg` (field), clamp-hold below the weight, Jorgensen above. Alternatives rejected: (i) hard switch at the edge (C0 jump: crossflow term at 10 deg for a slender body is already larger than the table `C_N`, a step would re-create a mini-discontinuity); (ii) pure taper to zero (the diagnosis's minimal fix: zero normal force at 90 deg is unphysical for crossflow, and loses the large-`a` moment the user asked for); (iii) 5 deg band: legal, but slope up to `~4.5/rad` vs the table's ~3/rad; the wider band is kinder to RK45 and costs nothing. The paper's `\restodo` on blending **remains**: the blend shape is our engineering choice, not validated, and `C_z,pot` for `a > 90` follows the printed sign (`Z < 0` there, tiny because of `cos(a/2)`); both are to be reported to the user as "model choice, not paper-verified".

**112.4 Validation (`aero.validate`, fail-fast at `assemble`).** `table_oob` in `{"clamp","jorgensen"}`; `jorgensen` requires `model == "table"`, `uses_l_p(p)` (v2 table: legacy `l1_m` tables carry an arm, not a station, so the `l_pc` correction is undefined), a two-sided table (`alpha[0] < 0 < alpha[-1]`; one-sided tables need an odd-mirror feature, backlog B43), both edges `< 80 deg` (else `Z(a_e)` is ill-conditioned and the table already covers large `a`), `S > 0`, `d_ref > 0`, `S_p > 0`, `l_pc > 0`, `oob_blend_deg > 0`, `C_dn >= 0`, `0 <= eta <= 1`, `C_x180 >= 0`, `S_base >= 0`.

**112.5 Clamp-mode warning.** In `_table_coeffs`, `table_oob == "clamp"` and `alpha` outside `[a_lo, a_hi]`: `warnings.warn` once per run (module-level set keyed by table name, cleared by `aero.reset_oob_warning()` called at `run_sim` entry) with an `AeroRangeWarning(UserWarning)`: names the table, its range, and the hint "set Aero.table_oob='jorgensen'; RK45 can stall in tail-first descent (diagnosis-rk45-v2-table.md)". Numerics unchanged. The developer greps existing tests for `recwarn`/`pytest.warns`/`-W error` assumptions and reports any that break.

**Tests first (`tests/test_aero_oob.py`, TDD).**
1. Full demo flight (DEMO rocket + LARGE motor + `example_v2.csv`, params with `S_p`, `l_pc` set, e.g. `S_p = 0.08`, `l_pc = 0.7`; `t_max` 200 s), RK45, `table_oob="jorgensen"`: (a) ballistic (no chute) reaches the ground; (b) with chute reaches the ground; both with the RHS counter wrapper that raises after 50 000 calls (fail instead of hang) and assert `nfev` below an explicit bound (the monkeypatched taper needed 2480; constant aero 1052; use 20 000 as ceiling and record the measured value in the step notes).
2. Ascent equals clamp: same flight with `t_max` just before apogee (~15 s) under `clamp` and `jorgensen` -> `np.array_equal` of the whole solution (all `|alpha|` inside the table).
3. Continuity (numeric): for `M` in a few values, `|C(a + 1e-7 rad) - C(a)| <= L * 1e-7` with a generous common `L` (e.g. 50) at `a` in `{+-180, +-90, +-a_e, +-(a_e + Delta)}` for `C_x, C_z, C_m`, plus a dense scan (0.01 deg steps over `(-180, 180]`) with a bounded finite-difference slope; and `C_z(180 - e) ~ -C_z(-180 + e)` sign-correct with both `-> 0` as `e -> 0`.
4. Inside the table range (`|alpha| <= a_hi` on a grid) `jorgensen` output `==` `clamp` output bitwise for `C_x, C_z, C_m, C_mq, l1`.
5. Symmetry in the extended region (odd-symmetric table): `C_x(-a) = C_x(a)`, `C_z(-a) = -C_z(a)`, `C_m(-a) = -C_m(a)` to 1e-12.
6. Analytic spot checks: far from the band (`a = 90`) `C_x = 0`, `C_z = eta C_dn S_p/S + 0`; `a = 180` `C_x = -x180` (explicit and the `0.0 -> C_x(0)` default); moment arm: `C_m^J - C_m_tab-part = (l_pc - l_p) C_z,cf / d_ref` at one `a`.
7. Default `clamp`: `_table_coeffs` for `alpha` in and out of range equals the legacy expression (`_table_lookup` + `_table_axial_factor`) bit-for-bit; the existing flights/pins are the second line.
8. Warning: `clamp` + out-of-range alpha, three calls inside one `run_sim`-like scope -> exactly one `AeroRangeWarning` (use `catch_warnings(record=True)` + `simplefilter("always")`; call `reset_oob_warning()` first); none in range; none under `jorgensen`; a second `run_sim` warns again.
9. `validate` failures (one assert per rule in 112.4); template doc test green.

- **Pin impact:** none at default (`clamp` untouched; new fields inert). No re-pin. The new RK45-completes tests are additions. After landing, whether `test_scenario_sweep.py` should leave RK4 for RK45 is a separate decision (not part of this step).
- **Comment fix (same step):** `tests/test_scenario_sweep.py` L123 "RK45 crawls on this airframe with a restoring-moment table (no damping)" is a misattribution; the cause is the clamped lookup at `alpha ~ 180` (sliding mode), see `diagnosis-rk45-v2-table.md`. Replace the comment (no behaviour change; the sweep stays RK4 unless decided otherwise).
- **Acceptance:** tests 1-9 green; full suite green with zero changed expectations; measured `nfev` recorded; step notes list the UNVERIFIED defaults (`eta` table, `C_x180` remark) and the open model choices (blend shape, sign of `C_z,pot` for `a > 90`). Not covered / deferred: Mach-dependent `C_dn` (B42), one-sided tables (B43), multi-component crossflow (fins) beyond the user-supplied `S_p`/`l_pc`.

## 35.7 Open decisions for the user (`decision_required`)

**STATUS 2026-10-18 (user): all decisions D-109..D-119 TAKEN, every recommendation accepted** — brake representation (b) `f_b` table axis with additive kept as default; pin policy (a) strict opt-in; `C_m` (c) per-table convention flag; mass flow from `T_0`, `A_e` only for new motors (a); B26 thin (a); actuator (b) rate+range+delay; sensors (b) baro + alpha-beta; runtime (c) measure, Step 104 only if > ~5 min; spec definition (c) authority + structural, envelope; `Re` (c) `l_ref == 0` -> `d_ref`; deferral list confirmed. (Ids were shifted by one: D-108 is taken in the tracker by another decision.) The table below keeps the options for the record.

| ID | Question | Options (pros / cons / cost) | Recommendation |
|---|---|---|---|
| D-109 | Air-brake representation in the aero | **(a) keep additive axial term only** — zero work, exact paper simplest case; no CP/`C_z` shift, cannot use CFD of the deployed brake. **(b) whole-rocket table with `f_b` axis, additive kept as default** (Step 102) — uses the user's CFD route, captures CP shift and Mach-dependent `C_D,b`; needs CFD at >= 2 `f_b` levels; M effort. **(c) own component in a multi-component build-up** — most physical, brake arm moment; L effort, needs component aero (none exists), no brake `C_N` data in the literature. Cost: none external | (b). Revisit (c) in a later phase |
| D-110 | Pin policy for 2.17 | **(a) strict opt-in:** defaults unchanged, no pin moves, new behaviour behind fields; one optional "adopt new defaults" step at the end with its own approval. **(b) fix-in-place:** change defaults and re-pin as steps go (cleaner code, many pin moves, each needs "yes"). Cost: (b) re-pin time + risk of masking regressions | (a) |
| D-111 | `C_m` sign (B31) | **(a) fix `example.csv` + header only** — no code change; user-supplied CFD tables (standard sign) are still easy to misuse. **(b) switch code to standard convention** — least surprising for CFD/RASAero data, moves every moment pin, touches LaTeX conventions (paper is approved with the current convention). **(c) keep code convention, tables declare `# cm_convention: standard|code`, converted at load, default `code`** — safe, zero pin moves, explicit | (c) now; (b) only with the 3D phase |
| D-112 | Mass flow from `T_0` (adopt approved paper) and `A_e` | Mass flow: **adopt** (paper approved, no change at `A_e = 0`) vs keep pressure-corrected `T` (inconsistent with paper). `A_e`: **(a) populate only new motors** (K570 pins stay) vs **(b) populate K570 too** (apogee shifts < ~1%: moves demo pins, needs re-pin). Cost: none | Adopt; `A_e` per (a) |
| D-113 | Depth of B26 (config = data) in 2.17 | **(a) thin:** provenance + derived `m(t), l_cg(t), I(t)` export for motors; solver unchanged (Step 100). **(b) table-driven mass in the solver** (`m(t), l_g(t), I(t)` from stored tables, `y[M]` kept as passenger): mass becomes a pure function of time given `T_0`; M effort; small pin risk. **(c) full:** drop `y[M]` (state 7 -> 6) — breaks shape of every state-based test and pin; L effort. None is needed for goals 1-3 | (a); (b) in 2.18 |
| D-114 | Actuator fidelity | **(a) ideal** (today) — no rate limit, overstates authority. **(b) rate + range + command delay, closed form** (Step 103) — no new state, exact in RK4; no lag. **(c) second-order servo with lag + backlash** — needs a state or sub-stepping, no parameters known yet. Cost: none | (b); (c) when servo data exist |
| D-115 | Sensors/estimator scope | **(a) none, controller reads truth with delay** — fastest, over-optimistic. **(b) baro altitude (noise, lag, quantisation, bias) + alpha-beta estimator** (Step 108) — realistic main limit of air-brake loops. **(c) baro + IMU + Kalman filter** — best fidelity, M-L, no IMU parameters known | (b) |
| D-116 | Runtime of sampled-data ensembles | **(a) RK4 dt = 5 ms only** (1.3 s/flight; 200 samples ~ 4 min on 1 core, ~1 min on 4) — no work, accuracy to validate. **(b) segmented RK45** (Step 104) — 10-100x faster, M-L effort, events per segment. **(c) both, decide by measurement** | (c): do Step 104 only if the Step 105 timing of the controller ensemble exceeds ~5 min |
| D-117 | Definition of the "maximum air-brake specification" | **(a) authority spec:** smallest `C_dA` (hence `S_b` for a given `C_D,b`) that trims the P95/P99 overshoot to the target while keeping `f_b <= f_max` (default 0.8) for controller headroom. **(b) structural spec:** peak brake force/`q`/`M` at the worst deployment instant. **(c) both, reported together; the spec is the envelope** (and per motor candidate). Needs the user's target apogee(s), dispersion list/widths and allowed `f_max` | (c) |
| D-118 | Reynolds length (B32.4) | **(a) follow the paper:** `Re` uses `d_ref`, delete `l_ref`. **(b) keep `l_ref` as is** and amend the paper. **(c) fallback:** `l_ref == 0` -> `d_ref`, nonzero `l_ref` honoured — no config/test breaks, paper gets one sentence. `Re` feeds no model, so no flight result changes | (c) |
| D-119 | Deferral list | Confirm the "Out" table of §35.3 (3D, vertical wind/Dryden `w`, jet damping, `C_m,q`, multi-component aero, drogue+main, pad slide, research-blocked items). Alternatively move any of them in (the main candidates: jet damping if wind-weathercock matters for config 2; Dryden `w`; pad slide B28 if low-T/W motors are in the candidate list) | Confirm |

Questions worth putting to the user together with the table (cheap to ask, expensive to guess): is configuration 1 the existing
demo or a real vehicle; what is the target apogee and is it the same for both configurations; is the brake mounted as flaps,
petals or a sleeve (sets `C_D,b` range and whether it shields the fins); is the competition scored on apogee error only.

## 35.8 Data the user must supply

Everything marked **REQ** blocks the named step. Anything missing is replaced by a flagged placeholder and the report says "wiring only".

**Configuration 1 is a REAL rocket (user, 2026-10-18), not the demo.** The user supplies data for both configurations; `configs/rockets/demo.py` stays as the test/demo config (pins untouched). Step 101 therefore adds two real rocket configs (config 1 and config 2) plus scenarios.

**Both rocket configurations (REQ for Step 101, 106)**
1. Airframe without motor: dry mass `m` [kg]; CG station from nose tip `l` [m]; pitch MOI about its own CG `I` [kg m^2]
   (CAD or pendulum; estimate allowed, say which). REQ.
2. Geometry: overall length `L_total`, nose length, fin root leading/trailing stations, body diameter (-> `S`, `d_ref`),
   motor-mount station (`l_motor_aft` or `l_motor_fwd`), largest motor diameter/length that fits. REQ.
3. Aerodynamics for the **whole rocket**, M from 0 to the highest expected Mach (+margin), alpha 0..~10 deg (more for wind):
   `C_A, C_N, C_m` and CP station from the nose `l_p` (CFD / RASAero / OpenRocket), the `C_m` sign convention used, and the reference
   `S`, `d_ref`. REQ for credible results. Minimum acceptable: `C_A(M)` at alpha = 0, `C_N,alpha(M)`, `l_p(M)`.
4. Pitch-damping `C_m,q` (or "0"); not needed for the brake study.
5. Recovery: canopy area/`C_D`, deployment rule (apogee/time/altitude), for landing checks only (OPT for goals 1-3).

**Motors (REQ for Step 100)**
6. The candidate list: RASP `.eng` files (e.g. from ThrustCurve.org, header has `m_prop`, `m_total`, diameter, length), nozzle exit
   diameter if known (-> `A_e`), propellant/casing centroid if known (else length/2), `I_sp` only if not derivable. State total
   impulse class limits (rail-exit speed, max acceleration, max Mach) as constraints.

**Air brake (REQ for Steps 102, 103, 106)**
7. Concept (flaps/petals/sleeve), maximum deployable area `S_b,max` and stowed envelope, first guess of `C_D,b` (or CFD at
   `f_b` = 0, 0.5, 1 per Step 111's condition list, and the matching tables with the `f_b` column).
8. Actuator: stroke time 0 -> 1 and 1 -> 0 (or rates), position limits, command-to-motion latency, update rate of the flight computer [Hz].
9. Allowed `f_max` headroom (D-117), mounting/structural limits (max brake force or `q` at deployment) if known.

**Sensors (REQ for Step 108; defaults used otherwise)**
10. Barometer: noise sigma, resolution, lag/filtering, expected transonic pressure error; IMU only if D-115 (c).

**Mission and environment (REQ for Steps 100, 106, 109)**
11. Target apogee (m AGL) and acceptable error band, per configuration; launch site elevation, rail length/elevation/azimuth;
    weather case (sounding file in `data/soundings/` or ISA + `dT`), wind speed/direction ranges.
12. Dispersion widths to use (defaults proposed: impulse +-3-5%, burn time +-3%, `C_x` +-10-15%, dry mass +-2-5%, CG +-1-2 cm,
    wind speed +-25% and direction +-20 deg, `dT` +-10 K, rail angle +-1 deg) — accept or override.

## 35.9 Timeline and milestones

Relative order and rough session counts (a session = one orchestrated working session: ticket -> developer -> QA -> full suite
-> commit; Phase 2.16 took about 20 steps over several sessions). Not calendar dates; user-data latency is excluded.

```
Main track                                             Paper track (parallel, no sim dependency unless noted)
-----------------------------------------------        --------------------------------------------------------
S97  safety net + bugs               (1 session)       P-A  review: introduction, analysis            (1-2 rounds)
S98  T0 / mass flow / k_J,k_t        (1)               P-B  review: assumptions, backlog              (1 round)
S99  aero table v2, C_m convention   (1-2)             P-C  appendix (notation, bibliography completeness)
S100 motor sweep v2 + B26 thin       (2)                    + Implementation appendix from code-vs-paper
S101 config 2 as data                (1; needs user data)       (27 undocumented features)               (1-2)
==== M1: motor sweep usable for config 2 ==== ~6-7 sessions after the user's data arrive
S110 paper figures (3 slices)        (3, any time after S98, between main-track steps)
S102 brake as f_b table axis         (1-2)             P-D  replace the 13 comptodo / 4 figtodo with the
S103 actuator model                  (1)                    generated tables and plots (after S110 slices;
S105 dispersion hooks + ensemble     (1-2)                  LaTeX edits only on the user's explicit request)
S111 CFD conditions with f_b         (1)               P-E  update the paper: discrepancies 1, 3, 8 and the
S106 max air-brake spec app          (2)                    new Phase 2.17 behaviour (brake table form,
==== M2: max brake spec for both configs ==== ~6-8 further sessions                actuator, T0 mass flow)
S107 sampled laws + drag predictor   (1)
S108 baro sensor + estimator         (1-2)
S104 segmented RK45                  (2; only if D-116 says so)
S109 closed-loop harness + metrics   (1-2)
==== M3: controller design loop exists ==== ~4-6 further sessions
```
Totals: M1 ~6-7, M2 ~12-15 cumulative, M3 ~16-21 cumulative sessions; Step 110 (3 sessions) and the review rounds are interleaved
and do not block the milestones. Order of review/fill work in the paper track: sections not yet reviewed (introduction, analysis,
assumptions, backlog, appendix), then notation + bibliography completeness check, then the todo replacement once Steps 98 and 110
exist, finally the update of the paper text where the simulator changed (Step 99 table format and `C_m` convention, Step 102 brake
form, Step 103 actuator; plus C5/C6 documentation gaps).

User-gated items on the critical path: the data of §35.8 (M1 needs items 1-3, 6, 11; M2 adds 7-9, 12 and the CFD tables with `f_b`);
decisions D-109..D-118 (D-109, D-110, D-111 before Step 99; D-112 before Step 98; D-117 before Step 106; D-114/D-115 before 103/108).

## 35.10 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Pins move unexpectedly (m_f floor sliver, Coriolis chute test) | extra re-pin round | Full suite per step; opt-in policy D-110; Step 97 classifies moved tests before fixing |
| Config 2 aero from CFD is missing/late | M1 runs on `constant` model: sweep is "wiring only" | Placeholder table from `C_A(M)`+`l_p(M)` minimum; `MachRangeWarning` surfaced in the report |
| CG-vs-CP convention mix-up (arm vs `l_p`, `C_m` sign) | silently unstable or over-stable results | Step 99 declared-convention loader + static-margin diagnostic as a hard check in the sweep (>= 1 cal) |
| Sampled-data ensemble too slow | M3 harness unusable | Parallel workers; RK4 dt = 5 ms; Step 104 gated by measurement |
| Thrust arm (`aB`) with moving CG | wrong moment only when `misalign_deg != 0` | Step 99 records the choice; on-axis thrust has zero moment |
| "Maximum spec" ambiguity | wrong deliverable | D-117 asked before Step 106 |
| Brake `C_N`/`C_m` data absent in literature | CP-shift effect rests on the user's CFD | `f_b` axis lets the user supply it; additive path remains |
| Yandex.Disk sync / long background runs | stale files, lost runs | Incremental writes, `run_in_background` with polling <= 240 s |
| LaTeX untouched rule vs paper alignment | paper stays behind the code | Paper-update item is a list handed to the user; edits only on explicit request |

## 35.11 Rejected options

- **Table-driven mass in the solver now (B26 b/c).** Not needed by goals 1-3; drops/changes `y[M]`; pin risk. Deferred (D-113).
- **Own-component brake with multi-component aero now (D-109 c).** L effort and no data; the table axis serves the same goal.
- **Changing the `C_m` convention in code now (D-111 b).** Moves all moment pins and diverges from the approved paper.
- **A new state for the actuator (f_b as an 8th ODE state).** Changes the state shape for all tests and pins; the per-tick ramp is exact
  for a held command and needs no state.
- **Controller code inside `sim/`.** Design churn would touch the physics package and its pins; `controllers/` registers into the hook.
- **Stateful RNG in the sensor channel.** Not reproducible under re-evaluation; counter-based `default_rng([seed, k])` instead.
- **Monte Carlo inside `sim/`.** `sim/` is single-run deterministic; ensembles are a consumer concern (`apps/common`).
- **Closing every paper todo in the code.** 17 `\restodo` need research or decisions; none blocks a goal.
- **Using `scipy`'s `RK45` with ZOH inside one `solve_ivp` call.** Discontinuities inside an adaptive step break step control; hence per-tick segments (Step 104) or fixed-step RK4.

## 35.12 Decision log (all taken by the user, 2026-10-18, recommendations accepted; status column reads "proposed" historically = now "taken")

| ID | Decision | Status |
|---|---|---|
| D-109 | Air-brake representation: `f_b` table axis, additive path kept | proposed (a/b/c) |
| D-110 | Pin policy: strict opt-in | proposed |
| D-111 | `C_m` convention: declared per table, converted at load | proposed |
| D-112 | Mass flow from `T_0`; `A_e` only for new motors | proposed |
| D-113 | B26 thin slice only | proposed |
| D-114 | Actuator: rate + range + delay, closed form | proposed |
| D-115 | Sensors: baro + alpha-beta | proposed |
| D-116 | Segmented RK45 gated by measurement | proposed |
| D-117 | Max-spec = authority envelope + structural loads | proposed |
| D-118 | `Re` length fallback to `d_ref` | proposed |
| D-119 | Deferral list confirmed | proposed |
| D-120 | Out-of-range alpha in the table model: opt-in Jorgensen extension (`Aero.table_oob = "jorgensen"`), default `"clamp"` stays bit-identical (D-110); blend = smoothstep over 10 deg beyond the table edge; REQ `S_p`, `l_pc`; defaults `C_dn = 1.2`, `eta` from fineness, `C_x180 = C_x(0)`. Taken by the user 2026-10-19; designed as Step 112 | taken |

New backlog items to register after approval (continue from B34): B34 table-driven mass (D-113 b), B35 first-order actuator/servo
model, B36 IMU + Kalman, B37 Dryden `w` + vertical wind with the 2D closure, B38 jet damping once `ṁ` and arm are known,
B39 `C_m` standard convention in code (with the 3D phase), B40 asymmetric brake deployment and shielding, B41 paper update list
after Phase 2.17 (brake form, actuator, `T_0` mass flow, table format).
