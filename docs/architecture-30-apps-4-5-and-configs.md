# Architecture §30 — Apps 4-5, the shared app layer, and reusable configs (Phase 2.13, Steps 63-69)

## Summary

Design proposal (not approved, no code written) for the five-tool layout the user asked for on
2026-10-13: five run files — (1) simple simulation, (2) motor sweep, (3) airbrake `C_dA`
determination, (4) CFD input-condition selection, (5) CFD optimization, weight vs aerodynamics —
plus "configs I can create and reuse across multiple apps". Two of the five already exist and are
untouched here: the user's "2nd" is **App 3** (`apps/motor_selection/`, Steps 61-62) and the user's
"4th" is **App 2** (`apps/cfd_conditions/`). The user's "1st" is `run.py`, which stays at the repo
root. So the genuinely new work is the user's "3rd" (**App 4**, airbrake `C_dA`) and "5th"
(**App 5**, weight-vs-aero trade), plus the cross-cutting config system and a small shared app
layer. **Internal numbering note, to prevent a future misreading: the existing "App N" labels are
not the user's 1-5 list order.** App 2 = CFD conditions, App 3 = motor selection, **App 4 = airbrake
sizing (new)**, **App 5 = weight-vs-aero trade (new)**; `run.py` has never carried an "App" number
and does not get one.

Everything here is a **consumer of `sim/`**, the App-2/App-3 rule: no physics beyond what already
exists, no new dependency. The airbrake already exists in exactly the additive
`C_dA_total = C_dA_rocket + C_dA_airbrake` form (Step 49, `sim/forces.py`), and a *held-fully-open*
brake over the coast is reachable through `Params` alone (§30.2 F5/F17, measured). **One exception,
added at the D-36 rework and still open:** the user's three requested deployment triggers ("after
burnout, after specified time, after apogee") are **not** all reachable without touching `sim/` —
"after burnout" is free, the other two are structurally impossible under the existing law
(§30.2 F15-F16, confirming the orchestrator's reading). The recommended fix is **+2 defaulted
`Control` fields and ~35 lines in `sim/control.py`**, copying the pattern
`sim/forces.py`'s `parachute_deployed` already uses for the parachute's `timer`/`apogee` triggers —
bit-for-bit safe for every existing config, and its own step with its own gate. D-36-revised
(§30.10) puts the mechanism choice back to the user.

**Status of the decision forks, 2026-10-13:** D-29 (four thin root wrappers), D-30/D-31 (`configs/`
package, `Config` + `Variant`, migrate the existing callers behind a bit-for-bit gate,
`apps/motor_selection/motors.py` stays put) and D-38 (both App 5 modes, surface first) are
**user-approved** and are written up here as settled. D-36 is **reworked and re-opened**. The
remaining forks (D-28, D-32…D-35, D-37, D-39…D-42) stand as recommended.

Seven steps, one commit each. **63** `configs/`; **64** `apps/common/` (promote App 3's
`flight_stats` so Apps 4/5 do not re-derive the numerics this project pins); **65** the airbrake
trigger dispatch in `sim/control.py` — **the one `sim/` step in the phase, D-36-gated**; **66**
App 4; **67** App 5 mode (b), the trade surface; **68** App 5 mode (a), the named-scenario
comparison; **69** migrate the existing callers (`run.py`, App 2, App 3's demo baseline) onto
`configs/` behind a bit-for-bit gate. Steps 66 and 67 are parallel-safe against each other.

Five measured facts that de-risk the design (full numbers in §30.2): apogee is **strictly monotone
decreasing** in `C_dA_airbrake`, so App 4 is a bracketed **root-find** (`brentq`, 17 simulator runs,
1.2 s, residual 1.4e-4 m) and not the squared-residual minimization the MATLAB precedent used; a
post-apogee brake leaves the apogee **flat to 2.4e-3 m of solver noise** across the precedent's whole
`[0, 10]` m² bound range, so App 4 must *refuse* to solve under the "after apogee" trigger rather
than return a number (§30.2 F19 — and the descent it would otherwise be judged on is itself
nonphysical here, backlog B17);
apogee is a function of the **product** `aero.S * aero.C_x` to the last printed digit, so App 5's
drag axis is legitimately one-dimensional in `C_dA`; one `run_sim` costs ~47-91 ms, so a 121-point
2-D trade surface takes 5.75 s; and the local exchange rate at the demo vehicle comes out at
**1 g of added mass ≈ 1.86 mm² of `C_dA` reduction** — which is the actual deliverable of App 5, the
number a CFD-driven component decision gets judged against.

Fifteen decision forks were flagged for the user in §30.10 (**D-28 … D-42**, continuing §29's
D-18 … D-27). Four are now answered (D-29, D-30, D-31, D-38); **D-36 is reworked and is the one
open gate** — it is the only decision in this phase that can put a hand on `sim/`.

---

## Contents

- [§30.1 Scope — the five tools, and what this phase is not](#301-scope--the-five-tools-and-what-this-phase-is-not)
- [§30.2 Findings — read from the code and measured by experiment](#302-findings--read-from-the-code-and-measured-by-experiment)
- [§30.3 The five run files and the entry-point layout](#303-the-five-run-files-and-the-entry-point-layout)
- [§30.4 `configs/` — the shared configuration system](#304-configs--the-shared-configuration-system)
- [§30.5 `apps/common/` — the shared app-support layer](#305-appscommon--the-shared-app-support-layer)
- [§30.6 App 4 — airbrake `C_dA` determination](#306-app-4--airbrake-c_da-determination)
  - [§30.6.1 Deployment triggers — the three laws (D-36 revised)](#3061-deployment-triggers--the-three-laws-d-36-revised)
- [§30.7 App 5 — weight vs aerodynamics](#307-app-5--weight-vs-aerodynamics)
- [§30.8 Test strategy](#308-test-strategy)
- [§30.9 Implementation tickets (Steps 63-69)](#309-implementation-tickets-steps-63-69)
- [§30.10 Decision points for the user (D-28 … D-42)](#3010-decision-points-for-the-user-d-28--d-42)
- [§30.11 Risks](#3011-risks)
- [§30.12 Rejected options, and the backlog items this opens](#3012-rejected-options-and-the-backlog-items-this-opens)

---

## 30.1 Scope — the five tools, and what this phase is not

This is **incremental architecture on the already-approved stack** (Python 3.12 + numpy 2.5 + scipy
1.18 + matplotlib 3.11, flat `sim/` package, dispatch-dict model selection, `apps/` for consumer
tools, Python-literal configuration per D-23) — not a greenfield design and not a stack pivot, so no
grilling interview and **no new dependency**. Everything below was derived by reading the current
code (`sim/params.py`, `sim/control.py`, `sim/forces.py`, `sim/report.py`, `sim/integrate.py`,
`sim/state.py`, `sim/plotting.py`, `run.py`, both existing apps, `tests/test_motor_selection.py`)
and by **running experiments against this tree** — §30.2's F5-F10 are measured numbers, not
predictions, and the measurements are cached there so nobody repeats them.

### What each tool answers

| User's item | Tool | Status | Question it answers |
|---|---|---|---|
| 1st, "simple simulation" | `run.py` (repo root, **not** an `apps/` tool, no "App N" label) | exists | "Fly *this* scenario once; show me the summary, the plots and the two model-comparison sweeps." |
| 2nd, "motor sweep" | `apps/motor_selection/` = **App 3** | exists (Steps 61-62) | "Of these N motors on this airframe, which gives the highest apogee, and what does each cost in peak velocity/acceleration/max-Q?" |
| 3rd, "air brakes parameter determination" | `apps/airbrake_sizing/` = **App 4** | **new, Step 65** | "What airbrake `C_dA` (hence what deployed area, at my chosen brake `Cd`) makes *this* vehicle hit *this* target apogee?" |
| 4th, "cfd input parameter determination" | `apps/cfd_conditions/` = **App 2** | exists | "Which `(V, alpha, M, Re)` conditions are worth spending a CFD run on?" (q-weighted reduction) |
| 5th, "cfd optimization (weight vs aero)" | `apps/weight_aero_tradeoff/` = **App 5** | **new, Steps 67-68** | "Is this much added mass worth that much drag reduction?" — as an iso-apogee exchange rate (mode b) and as a side-by-side comparison of named configurations (mode a). |

`run.py` keeps its place and its role. It is a different kind of thing from the `apps/` tools: it is
*the scenario*, flown once, with the house reporting. The `apps/` tools are *studies* that run the
simulator many times and reduce the results. §30.3 adds a one-line clarification of that to its
docstring and nothing else.

### Scope — what this phase deliberately does NOT do

- **At most one `sim/` change, confined to one step and one gate (Step 65, D-36-revised).** Apps 4
  and 5 themselves need none. The single exception is the airbrake *deployment trigger* dispatch the
  user asked for, which F15-F16 prove is unreachable through `Params` for two of the three requested
  triggers: +2 defaulted `Control` fields and ~35 lines in `sim/control.py`, bit-for-bit safe by
  default, in its own commit. `sim/control.py`'s real-time deployment law (`"proportional"`) is **not**
  touched, re-tuned, re-gated or re-specced even then; no closed-loop controller is designed here.
  Anything else an implementer finds is flagged and escalated, not silently added.
- **No real wind-tunnel or CFD data.** App 5 does not read CFD output and App 4 does not read a
  measured brake `Cd`. Both take the user's numbers as design inputs. Ingesting real aero data is
  `data/aero/` + `aero.model="table"`'s existing job, and a *CFD-output importer* is backlog
  (**B20**), not this phase.
- **No time-varying airbrake deployment profile.** App 4 solves for *one constant* `C_dA_airbrake`,
  fully deployed from its trigger instant onward, which is the user's own framing ("for now only as
  change in `C_dA`"). Three *onset* triggers are in scope (§30.6.1); a deployment schedule, actuator
  rate limits, retraction, a deploy/retract duty cycle, or a `C_dA(M)` dependence are all later work
  (**B19**).
- **No post-apogee / descent-braking study.** The `"after_apogee"` trigger is implemented so the
  capability and the `Params` record exist, but App 4 refuses to *solve* under it and no descent
  objective is designed: F19 measured the apogee objective flat to solver noise and the descent
  itself nonphysical in this project (frozen attitude + body-axis axial drag). That is **B23**,
  blocked on **B17**, and it is a `sim/` physics decision rather than an app feature.
- **No combined-`C_dA` refactor.** The user's stated future direction ("later it's gonna go as one
  combined `C_dA`") routes through `sim/control.py`'s existing Step-57 `aero_coeff_delta` seam. Not
  done here; App 4 is written so that it keeps working when it is (§30.6's `brake_overrides` is the
  one function that would change).
- **No multi-objective optimizer, no gradient-based design loop.** App 5 produces a *surface and an
  exchange rate*; the decision stays with the user. Enumeration and a 1-D root-find are the only
  searches in this phase.
- **No uncertainty / Monte Carlo / dispersion**, and **no 3D anything** — Phase 3 (Step 30, 3D EOM)
  is paused and independent; nothing here touches `sim/dynamics3d.py`, `sim/forces3d.py`,
  `sim/state3d.py`, `sim/quaternion.py` or `sim/rotation.py`.
- **No new dependency and no `docs/latex/` change.** This phase adds no physics, so `main.tex` has
  nothing to record. (Stated explicitly because every Phase ≥2.6 has ended with a LaTeX pass; this
  one correctly does not.)
- **No input validation layer** beyond loud, immediate failure (architecture.md §7). Bad config
  names raise `KeyError` with the available names listed; bad dotted paths raise
  `AttributeError`/`TypeError` from `sim.params.replace`.

---

## 30.2 Findings — read from the code and measured by experiment

**F1 — the airbrake is already exactly what the user described, and it is additive under a shared
`q`.** `sim/forces.py:220-224`:

```python
c = aero.coefficients(t, s, p, flow, hold)
A_x = flow.q * p.aero.S * c.C_x
A_z = flow.q * p.aero.S * c.C_z
A_brake = flow.q * p.control.airbrake_Cd * p.control.airbrake_S_max * control.airbrake_deploy_fraction(t, s, p, hold)
return np.array([-(A_x + A_brake), -A_z])
```

So the axial force is `q * (S*C_x + Cd_brake*S_max*f)`, i.e. literally
`C_dA_total = C_dA_rocket + C_dA_airbrake` with `C_dA_rocket = S*C_x` and
`C_dA_airbrake = Cd_brake * S_max * f`. **The model only ever uses the product
`airbrake_Cd * airbrake_S_max`** — which is why solving for both separately is ill-posed (D-34c) and
why App 4 solves for the product and *reports* the implied `S_max` (§30.6).

**F2 — `Control`'s fields, and the three independent off switches.** `sim/params.py:150-157`:
`airbrake_model` (`"none"` | `"proportional"`), `airbrake_target_apogee_m`, `airbrake_kp`,
`airbrake_Cd` (default **1.0**), `airbrake_S_max` (default 0.0), `aero_coeff_model`. Any one of
`airbrake_model="none"`, `airbrake_kp=0.0`, `airbrake_S_max=0.0` makes `A_brake` exactly `0.0`.
`airbrake_Cd`'s default of `1.0` is what makes "optimize the product, express the bounds in `C_dA`"
degenerate pleasantly: at `Cd = 1.0`, `S_max` *is* `C_dA_airbrake` numerically.

**F3 — the proportional law's gate is the physically right deployment window.**
`sim/control.py:108-112`: `_proportional_airbrake` returns `0.0` unconditionally while
`thrust_curve.thrust(t, y, p) > 0.0` (still under power) or `y[VZ] >= 0.0` (at/past apogee, `z` is
DOWN-positive), otherwise `clip(kp * (predicted_apogee - target), 0, 1)`. So the law's *active
window is exactly the unpowered ascent*, burnout → apogee — which is also when a real airbrake
deploys, and the window the MATLAB precedent's ballistic model implicitly assumed.

**F4 — `run_sim(p, s0)` always starts at `t = 0.0`.** `sim/integrate.py:469-479`: the integration
span is `(0.0, p.solver.t_max)` and `s0` is the initial state, so a nonzero-altitude initial state
is directly supported (nothing in `sim/` needs a "start state injection" API) — **but the thrust
curve is a function of `t`, so a mid-flight start with a non-empty `thrust.motor_curve` re-ignites
the motor at the injected state.** Measured in F8. `State` is a 7-tuple whose `m` field defaults to
`0.0` (`sim/state.py:25`), so a restart also silently drops the mass state when the Step-36
variable-mass model is on (`weight.m_d is not None`).

**F5 — a *held-fully-open* brake over the whole coast needs no `sim/` change. Measured.** Setting

```python
{"control.airbrake_model": "proportional",
 "control.airbrake_target_apogee_m": 0.0,
 "control.airbrake_kp": 1.0e9,
 "control.airbrake_Cd": <the user's brake Cd>,
 "control.airbrake_S_max": <C_dA_airbrake / Cd>}
```

saturates the `clip(..., 0, 1)` in F3 for the entire unpowered ascent. Sampled through one flight of
the §30.4 demo vehicle with the largest synthetic motor (burnout 2.0500 s, apogee 8.1489 s):

| t [s] | 0.0000 | 0.0500 | 1.0250 | 2.0490 | 2.0510 | 5.0994 | 8.1479 | 8.1499 | 9.1489 |
|---|---|---|---|---|---|---|---|---|---|
| deploy fraction | 0.000000 | 0.000000 | 0.000000 | 0.000000 | **1.000000** | **1.000000** | **1.000000** | 0.000000 | 0.000000 |

Exactly `0.0` under power, exactly `1.0` from burnout to apogee, exactly `0.0` after. This is
numerically identical to what a dedicated `"full_coast"` controller variant would compute (D-36), at
zero `sim/` cost. Its one defect is legibility: `kp = 1e9` in a printed `Params` reads as a gain, not
as "held open".

**F6 — apogee is strictly monotone decreasing in `C_dA_airbrake`. Measured**, demo vehicle +
`synthetic_large.csv`, `Cd = 1.0` (so the swept `S_max` *is* `C_dA_airbrake`):

| `C_dA_airbrake` [m²] | 0.0 | 0.001 | 0.005 | 0.010 | 0.020 | 0.050 | 0.100 | 0.500 | 2.000 | 10.000 |
|---|---|---|---|---|---|---|---|---|---|---|
| apogee [m] | 996.750 | 867.631 | 627.400 | 508.699 | 408.942 | 317.983 | 276.196 | 232.212 | 220.953 | 217.219 |
| `t_apogee` [s] | 13.339 | 12.111 | 9.583 | 8.149 | 6.774 | 5.265 | 4.399 | 3.142 | 2.604 | 2.299 |

Strictly decreasing over the precedent's full `[0, 10]` bound range, and strongly saturating past
~0.5 m² (the brake becomes large enough to kill the coast almost immediately). **Consequence:** the
problem is a bracketed root-find, not a minimization — see F7 and D-35. Note also how *flat* the
high end is: a squared-residual minimizer searching `[0, 10]` spends most of its budget in a region
where 9.5 m² of bound maps to 15 m of apogee.

**F7 — `brentq` solves it in 17 simulator runs. Measured.** Target `647.888 m` (65 % of the
brake-closed apogee), bounds `[0, 10]`, `xtol=1e-7`: root `C_dA = 0.00445149 m²`, achieved apogee
`647.8879 m`, residual `+1.41e-4 m`, **17** `run_sim` calls, **1.21 s** wall-clock total.

**F8 — the mid-flight restart: the trap and the (verified) equivalence.** Taking the burnout state
of a full run (`t = 2.0500 s`, altitude 216.034 m, `vz = -179.620 m/s`) and re-running from it as
`s0`:

| restart variant | apogee reached | vs the full launch→apogee run |
|---|---|---|
| `thrust.motor_curve` **kept** | **1954.663 m** | +957.9 m — *the motor re-ignites at `t=0`* (F4) |
| `thrust.motor_curve = ""` | 996.750 m | matches to the printed digits |
| `thrust.motor_curve = ""`, brake held open at `C_dA = 0.01` | 508.699172 m | full run 508.699089 m, **Δ = +8.3e-5 m**, and 26.0 ms vs 62.5 ms |

So a coast-only restart is physically exact (the coast RHS has no explicit `t` dependence once
thrust is zero) and 2.4× faster — but since one full run is only ~60 ms, the saving is ~0.7 s on a
whole App 4 solve. Not worth the state-injection subtleties today (D-37, **B21**).

**F9 — apogee is a function of the product `aero.S * aero.C_x` only. Measured** (demo vehicle,
`C_z = C_m = 0`, target product 0.00221 m²):

| `aero.S` | 0.004420 | 0.002210 | 0.022100 | 0.001105 |
|---|---|---|---|---|
| `aero.C_x` | 0.5 | 1.0 | 0.1 | 2.0 |
| apogee [m] | 996.750441 | 996.750441 | 996.750441 | 996.750441 |

Identical to every printed digit. **Consequence:** App 5's drag axis can legitimately be a single
scalar `C_dA = S*C_x`. **But it must be swept via `aero.C_x` at fixed `aero.S`**, not via `S`:
`S` also multiplies the normal force (`q*S*C_z`) and the pitching moment (`q*S*d_ref*C_m`), so
sweeping `S` would move three things at once in any scenario where `C_z`/`C_m` are not zero.
Sweeping `C_x` moves only the axial term, under every aero model that has a `C_x`.

**F10 — the trade surface is cheap, smooth and monotone. Measured.** An 11×11 grid
(`C_dA ∈ [0.5, 1.5] × 0.00221 m²`, `m ∈ [1.0, 2.5] kg`) = **121 runs in 5.75 s** (47.5 ms each),
apogee spanning 540.2 … 1733.6 m, strictly monotone decreasing along **both** axes everywhere on the
grid. Local sensitivities at the demo baseline (`C_dA = 0.00221 m²`, `m = 1.5 kg`, apogee 996.75 m):

```
d(apogee)/d(C_dA) = -214450 m/m^2  =  -21.44 m per cm^2
d(apogee)/dm      =  -398.18 m/kg  =  -0.398 m per gram
iso-apogee exchange rate:  1 gram of added mass "buys" 1.86 mm^2 (0.0186 cm^2) of C_dA reduction
                           equivalently 0.539 kg per cm^2 of C_dA saved
```

That exchange rate **is** App 5's product. It is the number that answers "if this fairing change
costs me 40 g and saves me 0.5 cm² of `C_dA`, is it worth it?" (here: yes, by a factor of ~13).

**F11 — `flight_stats` already exists, is already tested, and is already app-level.**
`apps/motor_selection/compare_motors.py:197-302` reduces one `Result` to an 11-field bundle over the
**ascent window** (D-19, user-approved), re-evaluating `dynamics.derivatives` for an exact
acceleration (D-20) and refusing `p.solver.sample_rate_hz != 0.0` (§29 F8). Apps 4 and 5 want the
same bundle. `tests/test_motor_selection.py:20-32` imports `flight_stats`, `build_params`,
`compare_motors`, `evaluate_motor`, `MotorEntry`, `_demo_baseline`, `_demo_entries` **from
`compare_motors`** and never names `MotorStats` at all (grep: 0 occurrences) — so promoting the
function and renaming the dataclass is invisible to the existing suite *provided
`compare_motors` re-exports the names* (D-28).

**F12 — packaging reality.** `sim/` has an `__init__.py` (one docstring line); `apps/` and `tests/`
have none and work as implicit namespace packages. The established invocation is
`python -m apps.<pkg>.<module>` **from the repo root** (§29 F12); running an app file by path breaks
`import sim` because the script's own directory, not the repo root, lands on `sys.path`. A root-level
`run_*.py` wrapper does **not** have that problem — its directory *is* the repo root — which is one
of the arguments in D-29.

**F13 — the reporting/plotting seams available for free.**
`sim.plotting.plot_trajectory_overlay(results: dict[str, Result], title)` → a two-panel `Figure`
(`plotting.py:58`), directly reusable by both new apps. `sim.plotting` is strictly
`Result → Figure`; a *surface contour* is not a `Result`, so App 5's contour plot belongs in the
app, not in `sim/plotting.py`. `sim.report.sweep`/`run_sweep` vary exactly **one** dotted path over
a list of values and attach the four-field `flight_summary` (`report.py:67-90`) — the wrong shape for
a 2-D grid and the wrong payload for a stats bundle, so App 5 does not route through it (§30.12).
`output/` is gitignored wholesale and created on demand; both existing apps resolve it as
`Path(__file__).parent.parent.parent / "output"`.

**F14 — environment, re-measured in this tree (cached so nobody re-checks).** Python 3.12.10, numpy
**2.5.3**, scipy **1.18.1**, matplotlib **3.11.2**; `requirements.txt` pins `numpy>=2.5,<3`,
`scipy>=1.18,<2`, `matplotlib>=3.11,<4`, `pytest>=8`. `scipy.optimize.brentq` and
`scipy.optimize.minimize_scalar` both import cleanly. `np.trapezoid` exists, `np.trapz` does not.
PyYAML is still not installed and still not a dependency. **No new dependency is proposed.**
Current test suite: 289 tests, all green (status.json, Step 62).

### Findings added by the D-36 rework (the three deployment triggers)

The user's answer on 2026-10-13 was *"for airbrake there are three laws u should implement for now,
after burnout, after specified time, after apogee. yes no sim file touched"*. F15-F19 are what
reading and measuring say about whether those two sentences can both be true.

**F15 — the existing law's deployment window is hardcoded in its body, not parameterised. Confirmed
by reading, exactly as the orchestrator suspected.** `sim/control.py:108-112` in full:

```python
if thrust_curve.thrust(t, y, p) > 0.0 or y[VZ] >= 0.0:
    return 0.0   # only active during unpowered ascent (post-burnout, pre-apogee)
predicted_apogee = gravity.altitude_agl(y, p) + y[VZ]**2 / (2.0 * gravity.g(t, y, p))
error = predicted_apogee - p.control.airbrake_target_apogee_m
return float(np.clip(p.control.airbrake_kp * error, 0.0, 1.0))
```

So, trigger by trigger:

- **"after burnout" — reachable today, no `sim/` change.** The gate *is* that window (F3), and a
  saturated gain opens the brake the instant thrust ends (F5, F17).
- **"after a specified time" — not reachable.** `t` enters the function in exactly one place,
  `thrust_curve.thrust(t, y, p)`, and `Params.control` has no time field. No choice of
  `airbrake_kp`/`airbrake_target_apogee_m` can make the fraction a function of a user-chosen trigger
  time. (The closest expressible thing is a *predicted-apogee threshold* trigger — `kp*(h + v_z²/2g −
  target) ≥ 1` — which is a legitimate fourth law but is a state trigger, not a time trigger.)
- **"after apogee" — structurally impossible.** `y[VZ] >= 0.0 → return 0.0` is in the function body.
  Past apogee the law returns zero for every parameter value there is.

**The orchestrator's reading is correct on all three counts.**

**F16 — Step 59's `hold`/`sampling` plumbing is not an escape hatch.** `airbrake_deploy_fraction`
does return `hold.values["airbrake"]` when a `Hold` carries that channel (`control.py:136-137`), but
the value in it is produced by `control.sample_airbrake`, which calls
`_AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t, y, p)` — *the same law* (`control.py:157`), just
once per tick instead of once per RHS call. `sampling._CHANNELS` is `{"airbrake":
control.sample_airbrake}` (`sampling.py:64`), module-private. And the whole path requires
`p.solver.sample_rate_hz > 0.0` **and** `method == "rk4"`, which `flight_stats` refuses outright
(§29 F8). There is no app-reachable seam that injects a deployment fraction from outside `sim/`.

**F17 — a bare "fully open while coasting" law reproduces the saturated-gain trick to solver
tolerance. Measured** (demo vehicle + `synthetic_large.csv`):

| `C_dA_airbrake` [m²] | 0.000000 | 0.001000 | 0.004451 | 0.010000 | 0.100000 |
|---|---|---|---|---|---|
| saturated-P apogee [m] | 996.750441 | 867.631268 | 647.887801 | 508.699089 | 276.195608 |
| `after_burnout` law [m] | 996.750441 | 867.631268 | 647.887801 | 508.699089 | 276.195608 |
| difference [m] | 0 | −4.2e-9 | −1.1e-7 | −8.5e-8 | −1.2e-8 |

So D-36(a) and a clean `"after_burnout"` trigger are the *same physics*; the choice between them is
purely about legibility and about whether the other two triggers come with it.

**F18 — "after a specified time" is a materially different and useful design space. Measured**
(`C_dA = 0.01 m²`, brake-closed apogee 996.750 m at `t_apogee = 13.339 s`):

| `t_deploy` [s] | 0.0 | 1.0 | 2.05 (burnout) | 4.0 | 6.0 | 8.0 | 10.0 |
|---|---|---|---|---|---|---|---|
| apogee [m] | 387.79 | 406.58 | 508.70 | 729.22 | 870.65 | 951.61 | 987.90 |
| Δ vs brake closed [m] | −608.96 | −590.17 | −488.05 | −267.53 | −126.10 | −45.14 | −8.85 |

Two things worth noting. (1) The span is wide and smooth, and it is **monotone increasing in
`t_deploy`** — so "my brake is *this* big, when do I pop it?" is a second, equally well-posed 1-D
root-find on the same objective seam. (2) `t_deploy = 0` deploys the brake *during powered flight*
(387.79 m), a region the `after_burnout` law structurally forbids — so this trigger is a strict
superset, not a reparameterisation. At fixed `t_deploy = 4.0 s`, apogee remains strictly monotone
decreasing in `C_dA` (996.75 → 891.02 → 804.46 → 729.22 → 591.35 → 520.35 → 506.86 m over
`C_dA ∈ [0, 10]`), so F6's root-find premise survives.

**F19 — "after apogee" cannot be an apogee-sizing law, and in this project it cannot presently be a
*descent* study either. Measured**, and this is the most consequential finding of the rework:

| `C_dA_airbrake` [m²] | 0.00 | 0.01 | 0.10 | 0.50 | 2.00 | 10.00 |
|---|---|---|---|---|---|---|
| apogee [m] | 996.750441 | 996.748024 | 996.748823 | 996.748439 | 996.750373 | 996.749256 |
| `t_apogee` [s] | 13.339437 | 13.339424 | 13.339428 | 13.339427 | 13.339437 | 13.339431 |
| `t_ground` [s] | 25.694 | 20.666 | **none** | **none** | **none** | **none** |
| impact speed [m/s] | 229.4 | **5285.2** | — | — | — | — |

1. **The apogee objective is flat to solver noise.** Total spread across the precedent's full
   `[0, 10]` m² bound range: **2.4e-3 m** — adaptive-step jitter, against 779 m of signal for the
   same sweep under `after_burnout` (F6). This is not "weakly sensitive", it is *exactly*
   insensitive by construction: the trigger is `y[VZ] > 0.0`, which is true only strictly after the
   apogee instant, so the trajectory up to and including apogee is independent of the brake. A
   root-find on `apogee − target` would be chasing numerical noise, and no target other than
   996.75 m has a root at all.
2. **The descent numbers are nonphysical, and the brake makes them worse.** With a brake, the vehicle
   reaches the ground *sooner* (20.666 s vs 25.694 s) at **5285 m/s**, and for `C_dA ≥ 0.1 m²` the
   integration never reaches the ground at all. The mechanism is already on record: `aero_force_body`
   returns the axial term along the **body** axis (`-(A_x + A_brake)` on `x_hat_r`, i.e. nose→tail),
   and with `C_z = C_m = 0` the attitude stays frozen nose-up through a tail-first fall — so the
   brake's drag points *down*, accelerating the descent instead of opposing it. That is the
   Step-55/F5 finding and backlog **B17**, amplified by adding area to it.

**Consequence for the design:** the `"after_apogee"` *trigger* is 4 lines and bit-for-bit safe, and
there is a good reason to implement it (the capability and the `Params` record exist, and it is the
trigger a descent-braking study will need). But App 4 must **refuse to solve** under it, and any
post-apogee brake study is blocked on a `sim/` **physics** decision — an attitude model with a
restoring moment, or axial drag that opposes the relative wind under reversed flow — which is B17's
territory, not a trigger law and not this phase.

---

## 30.3 The five run files and the entry-point layout

The user asked for "5 run files". Today exactly one of the five (`run.py`) is a file you can point
at; the other two existing tools are reached as `python -m apps.cfd_conditions.select_conditions`
and `python -m apps.motor_selection.compare_motors`. The recommendation (**D-29**) is to make the
user's mental model literal with four thin root-level wrappers:

```
run.py                     # 1. simple simulation      (exists; the scenario itself, unchanged)
run_motor_sweep.py         # 2. motor sweep            -> apps.motor_selection.compare_motors:main
run_airbrake.py            # 3. airbrake C_dA          -> apps.airbrake_sizing.solve_cda:main
run_cfd_conditions.py      # 4. CFD input conditions   -> apps.cfd_conditions.select_conditions:main
run_trade.py               # 5. weight vs aero         -> apps.weight_aero_tradeoff:main (mode flag)
```

Each wrapper is ~6 lines: a docstring naming which of the five it is and which app it calls, the
`--config`/`--mode` argparse call (§30.5), then `main(...)`. The apps keep their `python -m`
invocation and their own `main()` — the wrappers add a front door, they do not become the only one.
`run.py` is not renamed, not moved, and not turned into a dispatcher; it gains one docstring line
saying it is the first of the five and that the other four live in `apps/` (and nothing else).

Resulting top level after Phase 2.13:

```
rocket-trajectory/
  run.py                       # 1  (existing, +1 docstring line)
  run_motor_sweep.py           # 2  NEW, wrapper
  run_airbrake.py              # 3  NEW, wrapper
  run_cfd_conditions.py        # 4  NEW, wrapper
  run_trade.py                 # 5  NEW, wrapper
  configs/                     # NEW (Step 63) -- reusable named scenarios
    __init__.py                #   the registry: CONFIGS, get(), names()
    schema.py                  #   Config, Variant
    toy_05kg.py                #   run.py's / App 2's historical placeholder scenario
    demo_75mm.py               #   App 3's 1.5 kg / 75 mm demo vehicle (D-26)
    demo_75mm_airbrake.py      #   derived: demo_75mm + a target apogee, for App 4's demo
  apps/
    common/                    # NEW (Step 64) -- the shared app layer
      flight_stats.py          #   FlightStats + flight_stats() promoted out of App 3
      artifacts.py             #   OUTPUT_DIR + ensure_dir()
      cli.py                   #   --config / --list-configs parsing
    cfd_conditions/            # App 2, untouched (Step 69 swaps its literal for a Config)
    motor_selection/           # App 3, re-exports from apps.common (Step 64), otherwise untouched
    airbrake_sizing/           # App 4  NEW (Step 66)
      solve_cda.py
      targets.py               #   the study input literal (AirbrakeSpec), D-23 style
    weight_aero_tradeoff/      # App 5  NEW (Steps 67-68)
      trade_surface.py         #   mode (b): the 2-D surface + exchange rate
      compare_configs.py       #   mode (a): named-scenario comparison
      scenarios.py             #   the study input literal (list[Variant]), D-23 style
  sim/                         # read-only EXCEPT Step 65 (D-36-gated): control.py +~35 lines,
                               #   params.py +2 defaulted Control fields. Nothing else, ever, here.
  tests/
    test_configs.py            # NEW (Step 63)
    test_control.py            # APPENDED (Step 65) -- the three trigger predicates
    test_airbrake_sizing.py    # NEW (Step 66)
    test_weight_aero_tradeoff.py  # NEW (Steps 67-68)
  output/                      # generated, gitignored
```

### The convention this phase establishes, stated once

Two kinds of configuration, and the rule for telling them apart:

- **`configs/<name>.py` → a complete, runnable scenario** (`Params` + initial `State` +
  provenance notes). Vehicle-and-environment level. Reusable by *every* tool including `run.py`.
- **`apps/<app>/<study>.py` → the list of deltas this one study sweeps** (`list[Variant]`, or App
  3's existing `list[MotorEntry]`), applied on top of whichever `Config` the app is pointed at.
  Study level, app-specific, not reusable across apps by design.

That is exactly the split App 3 already stumbled into (a shared `_demo_baseline()` plus a per-motor
`motors.py`); Phase 2.13 names it and gives the first half a home. **`apps/motor_selection/motors.py`
does not move** — it is App 3's own study list and belongs where it is (D-32).

---

## 30.4 `configs/` — the shared configuration system

### Why a package of one-module-per-config

The user's two requirements are "reuse across multiple apps" and "many configs to track history".
Git already *is* the history: one module per config means `git log configs/demo_75mm.py` is that
vehicle's design history, with the commit messages explaining every number change. A separate
registry file, database or revision scheme would duplicate what git does and immediately drift from
it, so the design deliberately has none (D-30).

Format is a **Python literal**, which is not a fresh decision — it is D-23, already approved by the
user at Step 62, for reasons that apply verbatim here: `None` is a meaningful value (`weight.m_d =
None` *is* the mass-model off switch), the key set is open and sparse, every number in this repo is
justified in a comment right next to it, and a parsed format would make this project own a validator
it has explicitly decided not to own (architecture.md §7).

### `configs/schema.py` — two objects

```python
@dataclasses.dataclass(frozen=True)
class Config:
    """One complete, runnable scenario: the Params, the initial State, and
    where the numbers came from."""
    name: str                  # registry key, e.g. "demo_75mm"
    params: Params
    s0: State
    notes: str = ""            # provenance: source of the numbers, date, what it is for

    def derive(self, name: str, overrides: dict[str, Any], notes: str = "",
               s0: State | None = None) -> "Config":
        """A new Config, `overrides` applied via sim.params.replace. One call,
        arbitrarily many dotted keys (§29 F1). `s0` defaults to this one's."""

    def with_variant(self, v: "Variant") -> "Config":
        """`v` applied to this config, named f"{self.name}+{v.name}"."""


@dataclasses.dataclass(frozen=True)
class Variant:
    """A *named delta* against some Config -- the generalisation of App 3's
    `MotorEntry.overrides`, for studies that compare N perturbations of one
    baseline (App 5 mode (a), and any future what-if sweep)."""
    name: str
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    def apply(self, cfg: Config) -> Config:   # == cfg.with_variant(self)
```

Both frozen, both trivially constructible, no inheritance, no builders. `derive` is what keeps the
config set DRY *without* making every config indirect: a new vehicle that is "demo_75mm but 2.4 kg
and a 98 mm body" is three lines in its own module and its own git history, while the baseline's
numbers still live in exactly one place.

### `configs/__init__.py` — the registry *is* the package API

```python
from configs import demo_75mm, demo_75mm_airbrake, toy_05kg   # explicit, grep-able
from configs.schema import Config, Variant

_MODULES = (toy_05kg, demo_75mm, demo_75mm_airbrake)
CONFIGS: dict[str, Config] = {m.CONFIG.name: m.CONFIG for m in _MODULES}

def names() -> list[str]: ...
def get(name: str) -> Config:
    """KeyError listing every available name -- the one error message a
    typo'd --config has to produce."""
```

Three implementation notes the developer must not get wrong:

1. **Config modules import `from configs.schema import Config`, never `from configs import
   Config`.** The package `__init__` imports the config modules, so a config module reaching back
   into the partially-initialised package namespace would be a circular import. Importing the
   *submodule* is safe and must be the stated rule in `schema.py`'s docstring.
2. **The registry is an explicit tuple, not directory auto-discovery.** `pkgutil`/`importlib`
   globbing would make a config appear by existing, which is convenient exactly until a half-finished
   draft file breaks every app's import. Explicit is also greppable: "who uses this config" is one
   search.
3. **Registration is the only place a name is bound.** `CONFIGS` is keyed off `m.CONFIG.name`, not
   the module name, so a name/filename mismatch is possible; Step 63's test pins
   `all(k == m.__name__.split(".")[-1] for ...)` so it cannot happen silently.

### The three seed configs

| Module | What it is | Provenance |
|---|---|---|
| `toy_05kg.py` | the 0.5 kg / `S=0.005` / `C_x=0.5` placeholder scenario | **byte-equal** to `run.py`'s current literal and to App 2's `main()` literal — pinned by test, so Step 69's migration is a provable no-op |
| `demo_75mm.py` | the 1.5 kg / 75 mm vehicle, `S=0.00442`, `d_ref=0.075`, `l_ref=0.75`, `C_x=0.5`, `C_z=C_m=0` | **byte-equal** to App 3's `_demo_baseline()` (D-26, user-approved at Step 62); `thrust.motor_curve="synthetic_large.csv"` so it is runnable on its own |
| `demo_75mm_airbrake.py` | `demo_75mm.CONFIG.derive(...)` + a target apogee ~65 % of the brake-closed apogee | App 4's demo; the target is a *study* input, so it is carried in `apps/airbrake_sizing/targets.py` and this config only sets the vehicle side |

Pinning the first two byte-equal to the existing literals is what makes Step 69 a bit-for-bit
migration instead of a rewrite, and it is the only reason those two configs' numbers are not open to
debate in this document.

---

## 30.5 `apps/common/` — the shared app-support layer

Three small modules, no framework. The test is "two or more apps need it and it computes something
this project pins" — printing, argument handling and plot styling that differ per app stay per app.

**`apps/common/flight_stats.py`** — `FlightStats` (the 11-field bundle) and
`flight_stats(result, p) -> FlightStats`, moved verbatim out of
`apps/motor_selection/compare_motors.py` together with `_assert_derivatives_reconstructible`. Zero
behavioural change: same ascent window (D-19), same `derivatives` re-evaluation (D-20), same
`sample_rate_hz` guard (§29 F8), same grid (2000-point ascent ∪ 2000-point burn refinement).
App 3 then does

```python
from apps.common.flight_stats import FlightStats, flight_stats
MotorStats = FlightStats   # the Step-61/62 name, kept so nothing downstream moves
```

and `tests/test_motor_selection.py` keeps importing `flight_stats` from `compare_motors` unchanged
(F11). The gate is bit-for-bit: App 3's printed table and CSV must be byte-identical before and
after, and the 289-test suite must stay green with **no test edits**.

Why promote rather than let Apps 4/5 import App 3 (D-28): three apps computing the same ascent-window
extrema three times is exactly the duplication this project pins numerically to avoid, and
`from apps.motor_selection.compare_motors import flight_stats` inside an airbrake app is a coupling
no reader would predict (plus `MotorStats` is the wrong name for a non-motor study).

**`apps/common/artifacts.py`** — `OUTPUT_DIR` (the `Path(__file__).parents[2] / "output"` both
existing apps hand-roll) and `ensure_dir(path)`. Twelve lines; exists so the output path is defined
once rather than four times.

**`apps/common/cli.py`** — `add_config_arg(parser)` / `resolve_config(args) -> Config`, implementing
`--config NAME` (default per app) and `--list-configs` (prints `configs.names()` with each config's
`notes` first line, then exits). ~30 lines of argparse, no subcommand framework. App-specific flags
(`--target`, `--mode`, `--grid`) are declared by the app itself on the same parser. Apps 2 and 3 do
not get a CLI in this phase (D-33 scopes it to the new tools plus the wrappers).

---

## 30.6 App 4 — airbrake `C_dA` determination

### What it is, versus the MATLAB precedent

The user's `temp/AB_01.m` + `AB_01_sim.m` pair did this: fix `m`, `g`, `rho`; take a mid-flight
state `X0 = [altitude; velocity]` from a separate simulation; hand-roll an explicit-Euler ballistic
integrator with a constant total `C_dA` and no thrust; and call `fminbnd` over the brake's own
`CdAa ∈ [0, 10]` to minimize `(apogee - targetApogee)²`. The user's own verdict on it: *"smn like
this but this time I have proper solver."*

So App 4 keeps the precedent's **interface** — one scalar brake `C_dA`, user-supplied bounds, a
target apogee, a reported convergence flag, a printed altitude/velocity history — and replaces its
**engine** with the project's real simulator: adaptive `solve_ivp`, the real thrust curve, ISA/sounding
atmosphere, `q`-scaled variable aero, the real additive brake term (F1), launched from the pad rather
than from an injected mid-flight state (D-37).

### The variable being solved for (D-34)

One scalar, `C_dA_airbrake` [m²], exactly the precedent's `CdAa`, with the same default bounds
`[0, 10]` carried as a **user input, not a constant**. The mechanism's own drag coefficient
`cd_brake` is a separate *design input* (not solved for — F1: only the product enters the model, so
solving for both is ill-posed), and the deployed area the mechanism must actually provide is
**reported**: `S_max = C_dA_airbrake / cd_brake`. That gives the user the number the precedent gave
them *and* the number a mechanism drawing needs, with one search variable.

### 30.6.1 Deployment triggers — the three laws (D-36 revised)

The user's 2026-10-13 answer: *"for airbrake there are three laws u should implement for now, after
burnout, after specified time, after apogee. yes no sim file touched."* F15-F19 establish that those
two requirements **conflict for two of the three laws**: "after burnout" is free today, "after a
specified time" is unreachable through any parameter choice, and "after apogee" is structurally
impossible because the existing law's body returns `0.0` once `y[VZ] >= 0.0`. No `hold`/sampling
escape hatch exists (F16). So this section designs the three laws as they *should* be shaped, and
D-36-revised asks the user which mechanism they want them built through.

**Deployment is a *trigger* question, not a *law* question — and this repo has already solved the
same problem once.** `sim/forces.py:280-292`, `parachute_deployed`:

```python
if p.recovery.model == "none":    return False
if p.recovery.trigger == "timer": return t >= p.recovery.deploy_time
return y[VZ] > 0.0    # "apogee" (the default)
```

That is two of the user's three triggers, already implemented, already tested, for the parachute —
including the "a state predicate, never a lookup of the apogee *event*, because the RHS runs before
any event is finalised" rule and the `trigger`-string + `deploy_time`-float field pair in
`Params.recovery`. The airbrake's three triggers are **the same pattern moved to the `Control`
group**, which is why the recommended change is small, idiomatic, and has a precedent to copy rather
than a convention to invent.

#### The shape: a trigger dispatch orthogonal to the deployment law

```python
# sim/params.py -- Control gains exactly two fields, both defaulted
class Control:
    airbrake_model: str = "none"               # none | proportional | full        <- "full" is new
    airbrake_trigger: str = "after_burnout"    # after_burnout | after_time | after_apogee   <- NEW
    airbrake_deploy_time: float = 0.0          # s, read only when trigger == "after_time"   <- NEW
    ...  # airbrake_target_apogee_m, airbrake_kp, airbrake_Cd, airbrake_S_max unchanged

# sim/control.py -- one new dispatch dict, one new seam, one new law
def _trigger_after_burnout(t, y, p) -> bool:  return thrust_curve.thrust(t, y, p) <= 0.0
def _trigger_after_time(t, y, p) -> bool:     return t >= p.control.airbrake_deploy_time
def _trigger_after_apogee(t, y, p) -> bool:   return y[VZ] > 0.0

_AIRBRAKE_TRIGGERS = {
    "after_burnout": _trigger_after_burnout,
    "after_time":    _trigger_after_time,
    "after_apogee":  _trigger_after_apogee,
}

def airbrake_triggered(t, y, p) -> bool:
    """Has the brake's deployment condition fired? Dispatches on
    p.control.airbrake_trigger -- the same shape as forces.parachute_deployed,
    and a pure state predicate, never a Result.events lookup."""
    return _AIRBRAKE_TRIGGERS[p.control.airbrake_trigger](t, y, p)

def _full_airbrake(t, y, p) -> float:
    """Variant "full": fully deployed from the trigger instant onward, stowed
    before it. The constant-C_dA model App 4 solves against."""
    return 1.0 if airbrake_triggered(t, y, p) else 0.0

_AIRBRAKE_CONTROLLERS = {"none": ..., "proportional": ..., "full": _full_airbrake}   # +1 entry
```

Why a separate trigger dict rather than three new entries in `_AIRBRAKE_CONTROLLERS`: the trigger is
**orthogonal** to the deployment law. One trigger dict plus one `"full"` law gives three behaviours
today, and it is also the seam through which the existing `"proportional"` law could later be gated
on a chosen trigger instead of its hardcoded window (a separate, deliberate step — **not** now).
This is the `architecture.md` §12 dispatch-dict convention verbatim: a module-private dict keyed on a
`Params` string, one pure function per variant, unknown strings raising `KeyError` at the first call.

**Each trigger is a pure onset condition with no retraction** — a monotone latch in its own variable
(thrust-off, clock, `v_z` sign). Duration, retraction, rate limits and a deployment *schedule* stay
out (**B19**). One consequence to state rather than hide: `"after_burnout"` therefore stays deployed
through the descent, where F5's saturated-P trick closed at apogee. **App 4's answer is identical
either way** — nothing after apogee can change the apogee — and the `"after_burnout"` apogee matches
the saturated-P apogee to ~1e-7 m (F17).

**Cost, if the user takes the `sim/`-edit path:** `sim/params.py` **+2 lines** (two `Control` fields,
both with defaults, and every construction site in this repo is keyword-only — verified: the only
`Control(...)` calls are in `tests/test_control.py` and `tests/test_sampling.py`, all `**kwargs`), and
`sim/control.py` **+~35 lines** with house-style docstrings (3 trigger functions, 1 dict, 1 seam, 1
law, 1 registry entry). **Bit-for-bit safe for every existing config by construction:** the default
`airbrake_model` stays `"none"`; `"proportional"` is not edited; `airbrake_triggered` is unreachable
unless `airbrake_model == "full"` is named explicitly; and the two new fields are read only by the new
code. Plus ~6 tests in `tests/test_control.py`, which already has the fixtures for exactly this.

#### What App 4 can actually *solve* under each trigger

This is the part the user needs to see, because it is not symmetric:

| Trigger | Apogee sensitive to `C_dA`? | App 4 behaviour |
|---|---|---|
| `after_burnout` | **yes**, strongly and monotonically (F6: 996.75 → 217.22 m over `C_dA ∈ [0, 10]`) | full root-find for `C_dA` at a target apogee |
| `after_time` | **yes**, monotone at fixed `t_deploy` (F18: 996.75 → 506.86 m at `t_deploy = 4 s`), with the effect decaying smoothly to zero as `t_deploy → t_apogee` | full root-find for `C_dA`; **and** the mirror solve — root-find for `t_deploy` at fixed `C_dA`, also monotone (F18: 387.79 → 987.90 m), which is the realistic avionics question ("my brake is this big, when do I pop it?"). ~10 extra lines on the same seam |
| `after_apogee` | **no — flat to 2.4e-3 m of solver noise across the whole bound range** (F19), by construction | **refuses to solve**, with the reason named; evaluate-and-report only, and the report carries the B17 warning because the descent itself is nonphysical here (impact at 5285 m/s, or no ground event at all for `C_dA ≥ 0.1 m²`, because body-axis axial drag accelerates a frozen-attitude tail-first fall) |

The refusal is not a limitation of the app — it is the correct answer to an ill-posed question, and
the two-endpoint bracket check (§30.6's step 3) detects it generically: `apogee_open == apogee_closed`
to within solver tolerance means *no setting of this variable moves this objective*. The message
should say which of the two causes applies (a post-apogee trigger, or an `after_time` trigger later
than the brake-closed apogee), because the user can fix the second one by changing `t_deploy`.

A **descent** objective for `after_apogee` (target impact speed, or target descent duration) is the
natural companion solve and is deliberately **not** designed here: F19 shows the descent physics is
not trustworthy under the frozen-attitude/body-axis-drag combination, so a tool that optimizes
against it would be optimizing an artifact. It is listed as **B23**, blocked on B17 — a `sim/`
physics decision, not an app feature.

#### API consequences

`AirbrakeSpec` gains three fields and `AirbrakeSolution` two:

```python
@dataclasses.dataclass(frozen=True)
class AirbrakeSpec:
    target_apogee_m: float
    trigger: str = "after_burnout"      # after_burnout | after_time | after_apogee
    deploy_time_s: float = 0.0          # trigger == "after_time" only
    solve_for: str = "cda"              # "cda" | "deploy_time"  (the latter: trigger=="after_time")
    cd_brake: float = 1.0
    cda_bounds: tuple[float, float] = (0.0, 10.0)
    deploy_time_bounds: tuple[float, float] = (0.0, 60.0)   # s, solve_for == "deploy_time"
    xtol_m2: float = 1.0e-7
    # (kp_saturate is gone under the recommended mechanism -- "full" needs no gain)
```

`brake_overrides(cda, spec)` stays the **single** place the override dict is built — under the
recommended mechanism it becomes `{"control.airbrake_model": "full", "control.airbrake_trigger":
spec.trigger, "control.airbrake_deploy_time": spec.deploy_time_s, "control.airbrake_Cd":
spec.cd_brake, "control.airbrake_S_max": cda / spec.cd_brake}`, which is *simpler* than F5's
saturated-gain dict and carries no `kp = 1e9` to explain (risk 1 in §30.11 disappears with it).
`solve_airbrake_cda` raises `ValueError` naming F19 when `spec.trigger == "after_apogee"` and
`spec.solve_for != "none"`.

**If the user instead insists on the zero-`sim/`-change path**, the design degrades as follows and
needs no redesign: with D-36-revised(c) only `after_burnout` exists and `AirbrakeSpec.trigger` is
fixed to it (F5's saturated-gain dict returns, `kp_saturate` with it); with (b) the three trigger
functions and the `"full"` law live in `apps/airbrake_sizing/solve_cda.py` and are registered into
`sim.control._AIRBRAKE_CONTROLLERS` at app import, the trigger time travelling in a closure — which
means `Result.params` stops being a complete record of what flew (the Step-45 invariant,
`architecture.md` §25.5), so the app must print the trigger and time alongside every result.

### Method (D-35)

```
0. refuse up front if spec.trigger == "after_apogee" (F19: the objective is flat by
   construction -- there is nothing to solve, and the descent is not trustworthy either)
1. p_lo = brake closed (C_dA = bounds[0]);  p_hi = brake at bounds[1]
2. run both -> apogee_closed, apogee_open                      (2 sim runs, free diagnostics)
3. if apogee_open == apogee_closed (to solver tolerance):
       the objective is FLAT -- name the cause (a post-apogee trigger, or an
       "after_time" t_deploy later than the brake-closed apogee); stop
   if not (apogee_open <= target <= apogee_closed):
       reachable = False; clamp to the nearer bound; report loudly; stop
4. brentq(lambda cda: apogee(cda) - target, *bounds, xtol=..., rtol=...)   (~15 sim runs)
5. one final run at the root -> Result + FlightStats + artifacts
```

The same five steps serve the mirror solve (`solve_for = "deploy_time"` under the `"after_time"`
trigger): search `deploy_time_bounds` instead of `cda_bounds`, with the inequality in step 3
reversed because apogee is monotone **increasing** in `t_deploy` (F18). One `_solve_scalar` helper,
two thin callers — not two copies of the method.

Why a root-find rather than the precedent's squared-residual minimization: F6 measured strict
monotonicity, so the root is unique and bracketing is a *proof* of reachability rather than a hope;
`brentq` gets 1.4e-4 m of residual in 17 runs (F7); and the failure mode becomes diagnosable instead
of silent — a `fminbnd` on `(apogee-target)²` with an unreachable target returns a bound with a
small-looking objective and a "converged" flag, where step 3 above says *"your target is above the
brake-closed apogee; no brake setting reaches it — the airframe or the motor has to change."* That
diagnostic is, in practice, the most useful thing this app will ever print.

Objective note for the record: the squared residual is never formed. If the user wants fidelity to
their MATLAB run, `minimize_scalar(method="bounded")` on `(apogee-target)²` is a ~10-line alternative
path behind a `method=` argument (D-35c).

### Public API (`apps/airbrake_sizing/solve_cda.py`)

`AirbrakeSpec` is given in §30.6.1 (it carries the trigger fields, so it belongs with them).

```python
@dataclasses.dataclass(frozen=True)
class AirbrakeSolution:
    cda_airbrake: float          # m^2, the answer (a bound if reachable is False)
    s_max_m2: float              # = cda_airbrake / spec.cd_brake, the mechanism-design output
    cda_rocket: float | None     # p.aero.S * p.aero.C_x, or None if aero.model != "constant"
    cda_total: float | None      # cda_rocket + cda_airbrake, or None
    trigger: str                 # which of the three laws flew (§30.6.1)
    deploy_time_s: float | None  # the trigger instant: spec's own under "after_time", else the
                                 #   burnout/apogee time read back from result.events
    apogee_m: float              # achieved
    target_apogee_m: float
    apogee_error_m: float        # achieved - target
    reachable: bool              # was the target bracketed by the bounds?
    converged: bool              # brentq returned without error and |error| <= tol
    n_sim_runs: int
    apogee_closed_m: float       # brake fully stowed -- the upper envelope
    apogee_open_m: float         # brake at bounds[1] -- the lower envelope
    params: Params               # the solved Params (brake overrides applied)
    result: Result               # the solved trajectory
    stats: FlightStats           # the full ascent-window bundle at the solution
    result_closed: Result        # kept for the overlay plot
    result_open: Result

def brake_overrides(cda: float, spec: AirbrakeSpec) -> dict[str, Any]
def apogee_for_cda(cda: float, cfg: Config, spec: AirbrakeSpec) -> tuple[float | None, Result, Params]
def apogee_for_deploy_time(t_d: float, cda: float, cfg: Config, spec) -> tuple[float | None, Result, Params]
def solve_airbrake(cfg: Config, spec: AirbrakeSpec) -> AirbrakeSolution   # dispatches on spec.solve_for
def evaluate_airbrake(cda: float, cfg: Config, spec) -> AirbrakeSolution  # no search: the
                                 #   "after_apogee" / report-only path (converged = None semantics:
                                 #   reachable=True, n_sim_runs=1, target fields echoed)
def print_solution(sol: AirbrakeSolution) -> None
def save_solution_csv(sol: AirbrakeSolution, path: Path) -> None
def save_overlay(sol: AirbrakeSolution, path: Path) -> None
def main(argv: list[str] | None = None) -> None
```

- `apogee_for_cda` is this app's **objective-function seam**, the role `evaluate_motor` plays in
  App 3: one scalar in, one apogee out, no printing, no I/O, no global state.
  `apogee_for_deploy_time` is the same seam with the other scalar free — and a future genuinely
  2-variable search (area *and* timing together) wraps both.
- A degenerate run (`events["apogee"] is None` — the vehicle never leaves the pad) makes
  `apogee_for_cda` return `None`, and `solve_airbrake_cda` raises `ValueError` naming the config:
  with no apogee at the *closed* bound there is nothing to solve. This is the one place App 4 differs
  from App 3's "`None` apogee is a legitimate study result" rule, and for a good reason — it is the
  *input* that is broken, not a row of the output table.
- `cda_rocket` is `None` unless `aero.model == "constant"`: under `"linearized"`/`"table"` the
  airframe's own `C_dA` is Mach/alpha-dependent and no single number is honest. The brake's
  `C_dA` stays exactly constant in every case (F1), so the app's answer is still well-defined — only
  the *reported total* is withheld. This must be said in the printed output, not just in a docstring.
- Guard, inherited: `flight_stats` refuses `p.solver.sample_rate_hz != 0.0` (§29 F8); App 4 checks it
  once up front, before the first of its ~17 runs.
- The app **owns `control.airbrake_*` entirely**. Whatever the incoming `Config` set there is
  overwritten by `brake_overrides`; if the config has a nonzero `control.airbrake_S_max`, the printed
  output says it was overridden (a warning line, not an error — a config carrying a *previous*
  solution is a perfectly reasonable thing to re-solve).

### Output

Printed block (the precedent's report, plus what the real simulator gives for free):

```
Airbrake C_dA determination -- config "demo_75mm_airbrake", brake Cd = 1.00
  trigger                  after_burnout   (fully deployed from t = 2.050 s onward, no retraction)
  target apogee            650.00 m
  apogee, brake stowed     996.75 m        <- upper envelope (no brake)
  apogee, brake fully open 217.22 m        <- lower envelope (C_dA = 10.00 m^2)
  --> C_dA_airbrake        0.004451 m^2    (= 44.51 cm^2)
      implied S_max        0.004451 m^2    (= 44.51 cm^2 at Cd = 1.00)
      C_dA_rocket          0.002210 m^2    (aero.model = "constant": S*C_x)
      C_dA_total           0.006661 m^2
  achieved apogee          650.00 m        (error +1.4e-04 m)
  converged                yes             (17 simulator runs)
Flight at the solution (ascent-window extrema):
  burnout 2.050 s | apogee 8.46 s | v_max 179.7 m/s | v_avg 101.2 m/s | a_max 11.3 g | max_q 19.4 kPa
```

The two refusal paths print instead of a solution, and each names its cause:

```
REFUSED: trigger "after_apogee" cannot size a brake against an apogee target -- the trigger
  condition (v_z > 0) is true only strictly after apogee, so the apogee is independent of
  C_dA_airbrake by construction (measured flat to 2.4e-3 m across C_dA in [0, 10] m^2, i.e.
  solver noise; architecture-30 F19). Re-run with --mode evaluate for a report-only flight,
  and note that this project's descent physics is not yet trustworthy for a post-apogee brake
  (roadmap B17/B23).

REFUSED: the objective is flat -- apogee with the brake fully open (996.74 m) equals apogee with
  it stowed (996.75 m). Cause: trigger "after_time" with deploy_time = 14.000 s, later than the
  brake-closed apogee at 13.339 s, so the brake never acts before apogee. Lower deploy_time.
```

CSV `output/airbrake_sizing.csv`: one row, every `AirbrakeSolution` scalar field plus the config name
and the `FlightStats` fields — self-describing, same convention as App 3's CSV.
PNG `output/airbrake_sizing_overlay.png`: `plot_trajectory_overlay({"brake stowed": result_closed,
"solved C_dA": result, "brake fully open": result_open})` — the precedent's altitude/velocity plot,
with the two envelopes for context, in one line of app code via F13.

### `apps/airbrake_sizing/targets.py`

The study input literal, D-23 style (every number justified in place): target apogee, brake `Cd`,
bounds, tolerance, and — after the D-36 rework — the trigger, the deploy time and what to solve for.
Separate from `configs/` because a target apogee is a *mission requirement*, not a property of the
vehicle — the same vehicle config gets re-solved against several targets.

Because there are now three triggers and two solve directions, this file holds a **dict of named
specs** rather than one, which is also how the `--spec NAME` flag gets something to select:

```python
SPECS: dict[str, AirbrakeSpec] = {
    # The main case: size the brake for an apogee target, deployed at burnout.
    "burnout_650m": AirbrakeSpec(target_apogee_m=650.0, trigger="after_burnout"),
    # Timer-triggered avionics: same target, brake popped 4 s after launch.
    "timer_650m":   AirbrakeSpec(target_apogee_m=650.0, trigger="after_time", deploy_time_s=4.0),
    # The mirror solve: the brake is already built (44.5 cm^2) -- WHEN do I pop it?
    "when_to_pop":  AirbrakeSpec(target_apogee_m=650.0, trigger="after_time",
                                 solve_for="deploy_time", cda_bounds=(0.00445, 0.00445)),
    # Report-only: a post-apogee brake cannot be sized against an apogee (F19).
    "descent_demo": AirbrakeSpec(target_apogee_m=0.0, trigger="after_apogee", solve_for="none"),
}
```

---

## 30.7 App 5 — weight vs aerodynamics

The user left this one open: "idk if there should be a 2 (or more) input scenarios where one can
compare the performance of configurations or if we should precompute changes in drag vs weight, plot
it and get surface which can be used for every component; decide but there probably can be
implemented both."

**Recommendation: build both, surface first (D-38).** They are not redundant, and the reason is
specific rather than diplomatic:

- The **surface** (mode b) is the general answer. F10 measured it as cheap (121 runs, 5.75 s), smooth
  and monotone, and its derived exchange rate — **1 g ≈ 1.86 mm² of `C_dA` at the demo vehicle** — is
  reusable for *every* component decision without re-running anything, which is exactly the user's
  "surface which can be used for every component".
- The **comparison** (mode a) is *not* just two points read off that surface, in the one case that
  matters: two real candidate configurations can differ in things the surface's two axes do not span
  — a different aero *model* or `data/aero/*.csv` table, a different motor, a different `S`/`d_ref`
  geometry, a different launch site. The moment a configuration difference is not expressible as
  `(Δm, ΔC_dA)`, the surface cannot answer it and the side-by-side run can. Mode (a) is also ~70
  lines, because it is the `Variant` system plus `flight_stats` plus App 3's table shape.

So: mode (b) is the primary deliverable and the more valuable half; mode (a) is a cheap, genuinely
non-redundant companion. Two modules in one app, two steps, two commits.

### 30.7.1 Mode (b) — the trade surface (`trade_surface.py`, Step 66)

**Axes (D-39): 2-D, `C_dA_axial × mass`.** 1-D would delete the entire point of a weight-vs-aero
trade. 3-D (adding a motor or target axis) multiplies the run count by 10 and has no 2-D plot.

**How each axis is swept, and why:** `C_dA` via **`aero.C_x` at fixed `aero.S`** (F9: apogee depends
on the product `S*C_x` to the last digit, and sweeping `C_x` leaves the normal-force and
pitching-moment terms alone, which sweeping `S` would not), reported in `C_dA = S*C_x` units; mass via
**`weight.m`**. A caveat the app must print rather than bury: `weight.I` is held fixed, so added mass
is modelled as adding no pitch inertia — exact for the attitude-frozen vertical demo scenario
(`C_z = C_m = 0`), an approximation otherwise (**B22**).

```python
@dataclasses.dataclass(frozen=True)
class TradeAxes:
    cda_values: tuple[float, ...]    # m^2, axial C_dA = aero.S * aero.C_x
    mass_values: tuple[float, ...]   # kg, weight.m

@dataclasses.dataclass(frozen=True)
class TradeSurface:
    cfg: Config
    axes: TradeAxes
    apogee: np.ndarray               # shape (len(mass_values), len(cda_values)); nan = no apogee event
    def apogee_at(self, cda: float, m: float) -> float            # bilinear inside the box, nan outside
    def gradients(self) -> tuple[np.ndarray, np.ndarray]          # d(apogee)/d(C_dA), d(apogee)/dm, np.gradient
    def exchange_rate(self, cda: float, m: float) -> float        # dm/d(C_dA) [kg/m^2] along the iso-apogee curve

def build_surface(cfg: Config, axes: TradeAxes) -> TradeSurface
def print_surface_table(s: TradeSurface) -> None
def print_exchange_rates(s: TradeSurface) -> None
def save_surface_csv(s: TradeSurface, path: Path) -> None      # long format: m_kg, cda_m2, apogee_m
def save_contour_plot(s: TradeSurface, path: Path) -> None     # iso-apogee contours in the (C_dA, m) plane
def main(argv=None) -> None
```

The exchange rate is the deliverable, and it is the implicit-function-theorem slope of an iso-apogee
contour:

```
along apogee(C_dA, m) = const:   (dA/dC_dA) dC_dA + (dA/dm) dm = 0
    =>  dm/dC_dA = -(dA/dC_dA) / (dA/dm)        [kg per m^2]
```

Both partials come from `np.gradient` on the computed grid — central differences, **no extra
simulator runs** — which is sound precisely because F10 measured the grid as smooth and monotone in
both directions. Printed in design units (`mm² of C_dA per gram`, and its reciprocal `g per cm²`)
with the dimensional form alongside, plus the two raw sensitivities (`m of apogee per gram`,
`m of apogee per cm²`) so the user can sanity-check the ratio. The `nan` policy: a grid point whose
flight produced no apogee event is `nan`, `np.gradient` propagates `nan` locally, and
`print_exchange_rates` says how many points were lost rather than quietly reporting a hole.

Artifacts: `output/trade_surface.csv` (long format, one row per grid point — joinable, plottable in
anything), `output/trade_surface_contour.png` (filled iso-apogee contours, `C_dA` on x, mass on y, the
baseline marked). The contour plot is **new matplotlib code, and it lives in the app**, not in
`sim/plotting.py` — F13: that module's contract is `Result → Figure`, and a surface is not a `Result`.

Grid definition lives in `apps/weight_aero_tradeoff/scenarios.py` as a commented literal (D-23 style):
the default is F10's measured box, `C_dA ∈ [0.5, 1.5] × C_dA_baseline` and `m ∈ [1.0, 2.5] kg`, 11×11,
chosen because it brackets the baseline on both axes and costs 5.75 s.

**Not persisted as committed data (D-40).** The surface is recomputed on demand and written to the
gitignored `output/`; `data/` in this repo means *measured or synthetic physical input*, not computed
results, and at 5.75 s a cache would be a correctness liability (a stale surface silently answering
for a changed vehicle) in exchange for nothing. The "reusable for every component" requirement is met
by `apogee_at`/`exchange_rate` on the in-memory object plus the CSV, not by a committed artifact.

### 30.7.2 Mode (a) — named-scenario comparison (`compare_configs.py`, Step 67)

```python
@dataclasses.dataclass(frozen=True)
class ConfigRun:
    cfg: Config
    result: Result
    stats: FlightStats
    cda_axial: float | None    # S*C_x if aero.model == "constant", else None
    mass_kg: float             # params.weight.m

def evaluate_config(cfg: Config) -> ConfigRun                 # the objective-function seam
def compare_configs(cfgs: list[Config]) -> list[ConfigRun]    # ranked by apogee desc, None last
def print_comparison_table(runs: list[ConfigRun]) -> None
def save_comparison_csv(runs: list[ConfigRun], path: Path) -> None
def save_overlay(runs: list[ConfigRun], path: Path) -> None
def main(argv=None) -> None
```

Same shape as App 3's `compare_motors`, deliberately — ranked by apogee descending, `None` apogee
last, the ascent-window stats bundle per row, plain fixed-width table, CSV, overlay PNG via F13. The
two columns that make it a *weight-vs-aero* table rather than a generic one are `mass_kg` and
`cda_axial`, printed next to the apogee so the trade is visible in the row.

Inputs come from `apps/weight_aero_tradeoff/scenarios.py` as `SCENARIOS: list[Variant]` applied to the
`--config` baseline — e.g. `"heavy_sleek"` (`weight.m += 0.3`, `aero.C_x × 0.85`) vs `"light_draggy"`
(baseline mass, `aero.C_x × 1.0`) vs the baseline itself, each with a `notes` string recording where
the numbers came from (a CFD run, a guess, a measurement). `--config a,b,c` also accepts full
`Config` names straight from the registry, for the case where two candidates differ by more than a
delta (the case that justifies mode (a) existing at all).

---

## 30.8 Test strategy

Continuing D-25's precedent (App 3 ships tests; App 2 historically did not): every step that computes
a number ships pinned tests. The pins below are chosen so they are derivable or structural, not
"whatever the solver printed" — the same discipline §29.5 stated and `tests/test_motor_selection.py`
implements. F6-F10's measured numbers are available as *loose* cross-checks, not as tight pins, since
they are predictions of this tree's solver rather than facts about the world.

**`tests/test_configs.py` (Step 63)**
- `configs.get("toy_05kg").params == <run.py's literal, reconstructed in the test>` — exact dataclass
  equality, and the same for `s0`. This is what makes Step 69 provably a no-op.
- `configs.get("demo_75mm").params == apps.motor_selection.compare_motors._demo_baseline()` — exact.
- registry integrity: every key equals its module's basename; `CONFIGS` has no duplicate `Config`
  objects; `get("nope")` raises `KeyError` whose message contains every available name.
- `derive`: changes exactly the named fields, leaves every other field of every group equal (§29 F1's
  no-silent-reset property); `s0` is inherited unless overridden; the result is a new frozen object
  (the original is unmutated).
- `Variant.apply` == `Config.with_variant`, and the composed name is `f"{cfg}+{variant}"`.
- every registered config actually runs: `run_sim(cfg.params, cfg.s0)` returns an apogee event (a
  config that cannot fly is a broken config).
- no circular import: `import configs.demo_75mm` works as the *first* import in a fresh interpreter,
  and so does `import configs`.

**Step 64 (`apps/common/`)** — the gate is bit-for-bit, not new coverage: the 289-test suite passes
**with zero test-file edits**, and App 3's printed table and CSV are byte-identical before/after
(diff the saved `output/motor_selection.csv` across the two commits). Plus one new test that
`apps.motor_selection.compare_motors.MotorStats is apps.common.flight_stats.FlightStats`, so the alias
cannot drift into a second dataclass.

**`tests/test_control.py` additions (Step 65, the `sim/` step — D-36-gated)**
- **the bit-for-bit gate first:** the full suite green with **no existing test edited**, because the
  new fields are defaulted and the new dispatch entries are unreachable unless named. Assert it
  structurally too: `Control()` with no arguments has `airbrake_trigger == "after_burnout"` and
  `airbrake_deploy_time == 0.0`, and `airbrake_deploy_fraction` under `airbrake_model="none"` and
  under `"proportional"` is unchanged from the values the existing tests already pin.
- one test per trigger, as a *predicate* (`airbrake_triggered`), on hand-built state vectors — no
  integration needed: `after_burnout` false while `thrust > 0` and true after; `after_time` false for
  `t < deploy_time` and true at/after it; `after_apogee` false for `vz < 0`, false at `vz == 0.0`
  exactly (the pad case) and true for `vz > 0`.
- `_full_airbrake` returns exactly `1.0`/`0.0` and nothing between (it is a latch, not a law).
- an unknown `airbrake_trigger` raises `KeyError` at the first call (the house no-validation rule).
- `"full"` + `after_burnout` reproduces the saturated-proportional apogee to ~1e-6 m (F17's measured
  equivalence, asserted loosely — it is a solver-tolerance claim, not an identity).

**`tests/test_airbrake_sizing.py` (Step 66)**
- **monotonicity** (the premise the whole method rests on): `apogee_for_cda` is strictly decreasing
  over a handful of `C_dA` values spanning the bounds (F6's shape, asserted as an ordering, not as
  values), and `apogee_for_deploy_time` is strictly **increasing** in `t_deploy` (F18's shape).
- **round-trip, the load-bearing one**: pick a `C_dA*`, run it, take its apogee as the target, solve —
  the solver must return `C_dA*` to within a stated tolerance. This is a *self-consistency* pin that
  needs no external truth and would catch a wrong override key, a sign error or a units error
  immediately. The same round-trip for `solve_for="deploy_time"`.
- `brake_overrides` + `control.airbrake_deploy_fraction` is exactly `0.0` before the trigger instant
  and exactly `1.0` after it, for each of the three triggers (F5/F17/F18/F19's sampled instants).
- `S_max == cda_airbrake / cd_brake` for a non-unity `cd_brake`, and two different
  `(cd_brake, S_max)` pairs with the same product give the same apogee (F1's product-only property).
- **the `after_apogee` refusal** (F19): `solve_airbrake` raises `ValueError` whose message names the
  flat-objective reason, *without* running a search; and `evaluate_airbrake` under the same trigger
  returns a solution whose apogee equals the brake-stowed apogee to within 1e-2 m for **any**
  `C_dA` — the measured independence, asserted as the property it is.
- **the flat-objective detector**: an `after_time` spec with `deploy_time` past the brake-closed
  apogee is refused with the *other* message (the one the user can act on by lowering the time).
- unreachable target above the brake-closed apogee → `reachable is False`, the clamped bound returned,
  no exception; unreachable below the fully-open apogee → same, other bound.
- a config that never leaves the pad → `ValueError` naming the config.
- `p.solver.sample_rate_hz = 1000.0` → `ValueError` **before** the first `run_sim`.

**`tests/test_weight_aero_tradeoff.py` (Steps 67-68)**
- **the `S*C_x` invariance** (F9), as an exact equality: two configs with the same product give the
  same apogee bit-for-bit. This is the fact the 1-D drag axis stands on.
- surface shape/orientation: `apogee.shape == (len(mass_values), len(cda_values))`, monotone
  decreasing along both axes, and `apogee_at(grid point)` reproduces the stored value exactly
  (bilinear interpolation must be exact *at* nodes — the classic off-by-one-axis bug).
- `exchange_rate` sign and a closed-form sanity check: it is negative, and it equals
  `-(dA/dC_dA)/(dA/dm)` computed independently from two extra direct `run_sim` finite differences, to
  a loose tolerance (~10 %). This is what proves the axis order and the gradient units.
- a `nan` grid point (one deliberately unflyable mass) propagates as `nan` and is *counted*, not
  silently dropped.
- mode (a): ranking is non-increasing with `None` last; `cda_axial` is `None` under
  `aero.model="table"`; a `Variant` changes exactly its named fields.

---

## 30.9 Implementation tickets (Steps 63-69)

Same Files/Spec/Do/Check/Commit shape every roadmap step uses; `docs/roadmap.md`'s new Phase 2.13
section carries the same seven. Step numbers continue the sequence (last used: **Step 62**); Phase 3
keeps its reserved 28-32 block. **Renumbered at the D-36 rework**: the new Step 65 (the airbrake
trigger dispatch, the phase's only `sim/` step) pushed App 4 to 66, the trade surface to 67, the
comparison to 68 and the migration to 69.

### [Step 63] `configs/` — the shared configuration package

- **Module/boundaries:** new `configs/{__init__.py,schema.py,toy_05kg.py,demo_75mm.py,demo_75mm_airbrake.py}`;
  new `tests/test_configs.py`. **No `sim/` file, no `apps/` file, no `run.py`.**
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true (all new files, in a new top-level directory)
- **Spec slice:** §30.4 in full, plus §30.8's `test_configs.py` block. §30.3's directory tree for
  placement. Nothing else.
- **Do:** `Config`/`Variant` per §30.4 (frozen dataclasses, `derive`, `with_variant`, `apply`); the
  registry in `__init__.py` with an explicit module tuple, `CONFIGS`, `names()`, `get()`; the three
  seed configs, with `toy_05kg` and `demo_75mm` copied **number-for-number** from `run.py`'s literal
  and `compare_motors._demo_baseline()` respectively, every number keeping its existing justifying
  comment. `schema.py`'s docstring states the `from configs.schema import Config` rule (§30.4 note 1)
  and the two-kinds-of-configuration convention (§30.3).
- **Check:** §30.8's `test_configs.py` list, with the two exact-equality pins as the primary checks.
  Full suite green, count up by the step's own tests only. `python -c "import configs; print(configs.names())"`
  from the repo root lists three names.
- **Commit:** "Step 63 (Phase 2.13): configs/ -- reusable named scenario configurations"

### [Step 64] `apps/common/` — promote the shared app layer out of App 3

- **Module/boundaries:** new `apps/common/{flight_stats.py,artifacts.py,cli.py}`;
  `apps/motor_selection/compare_motors.py` (imports + the `MotorStats` alias + the `OUTPUT_DIR`
  constant removed in favour of the shared one); `tests/test_motor_selection.py` **must not be
  edited**. **No `sim/` file.**
- **Assignee:** developer
- **depends_on:** [Step 63] (only because `cli.py` resolves names through `configs`; the
  `flight_stats` move itself is independent)
- **parallel_safe:** false (edits App 3)
- **Spec slice:** §30.5 in full; §30.2 F11 (what the existing tests import, and why the re-export is
  what keeps them green); §30.8's Step 64 gate.
- **Do:** move `FlightStats` (renamed from `MotorStats`, fields and docstrings unchanged),
  `flight_stats`, `_assert_derivatives_reconstructible` and the two grid constants into
  `apps/common/flight_stats.py` **verbatim**; re-export from `compare_motors` with
  `MotorStats = FlightStats`; `artifacts.py` with `OUTPUT_DIR`/`ensure_dir`; `cli.py` with
  `add_config_arg`/`resolve_config`/`--list-configs`. Record in `flight_stats.py`'s docstring that
  the ascent-window and `derivatives`-re-evaluation conventions are D-19/D-20/D-21/D-22, decided at
  Phase 2.12, and that this file is their one home now.
- **Check:** **the gate is bit-for-bit** — 289/289 green with **no test file touched**; App 3's
  printed table and `output/motor_selection.csv` byte-identical to the pre-step run (capture both,
  diff them, paste the diff-empty result into the step report). Plus the alias-identity test. No
  app other than App 3 imports `apps.common` yet, by design.
- **Commit:** "Step 64 (Phase 2.13): apps/common/ -- shared flight-stats, artifact and CLI layer"

### [Step 65] Airbrake deployment triggers in `sim/control.py` — **the phase's only `sim/` step, D-36-gated**

- **Module/boundaries:** `sim/params.py` (**+2 defaulted fields** on `Control`, nothing else);
  `sim/control.py` (**+~35 lines**: 3 trigger functions, `_AIRBRAKE_TRIGGERS`, `airbrake_triggered`,
  `_full_airbrake`, one `_AIRBRAKE_CONTROLLERS` entry); `tests/test_control.py` (append).
  **`_proportional_airbrake` is not edited. No other `sim/` file, no `apps/` file, no `run.py`.**
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true (disjoint from Steps 63/64; `sim/` is touched by nothing else in the phase)
- **Spec slice:** §30.6.1 in full (it carries the code shape, the field names, the line-count estimate
  and the bit-for-bit argument); §30.2 **F15-F19** (why this step exists at all, and what each trigger
  is measured to do); §30.8's `test_control.py` block. `sim/forces.py:280-292`
  (`parachute_deployed`) is the pattern to copy.
- **Do:** exactly §30.6.1's listing and nothing more. `Control` gains `airbrake_trigger: str =
  "after_burnout"` and `airbrake_deploy_time: float = 0.0`, both commented in `params.py`'s house
  style. `sim/control.py` gains the three pure trigger predicates, the module-private
  `_AIRBRAKE_TRIGGERS` dispatch dict (architecture.md §12's convention), the `airbrake_triggered`
  seam, and the `"full"` deployment law — registered as a **third** `_AIRBRAKE_CONTROLLERS` entry
  beside the untouched `"none"`/`"proportional"`. The module docstring records: that each trigger is
  a pure *onset* latch with no retraction (duration/retraction is B19); that `after_apogee` uses the
  `y[VZ] > 0.0` state predicate rather than the apogee *event*, with `parachute_deployed`'s own
  reason (the RHS runs before any event is finalised) and its own documented caveat (a pre-apogee
  `v_z` transient would arm it early); and that `airbrake_deploy_time = 0.0` under the `"after_time"`
  trigger means "deployed from `t = 0`", the same semantics `Recovery.deploy_time = 0.0` already has.
- **Check:** **the gate is bit-for-bit** — 289/289 green with **no existing test edited** (if any
  existing test needs a change, the step is wrong: every new field is defaulted and every new
  dispatch entry is unreachable unless named). Then §30.8's `test_control.py` list: one predicate test
  per trigger on hand-built states, `_full_airbrake` returning only `0.0`/`1.0`, an unknown trigger
  raising `KeyError`, and the F17 equivalence (`"full"` + `after_burnout` vs the saturated
  proportional law, to ~1e-6 m). `git diff --stat` must show exactly two `sim/` files and
  `+2` lines in `sim/params.py`.
- **Commit:** "Step 65 (Phase 2.13): airbrake deployment triggers (after_burnout | after_time | after_apogee)"

### [Step 66] App 4 — airbrake `C_dA` determination

- **Module/boundaries:** new `apps/airbrake_sizing/{solve_cda.py,targets.py}`; new
  `run_airbrake.py`; new `tests/test_airbrake_sizing.py`. **No `sim/` file, no other app.**
- **Assignee:** developer
- **depends_on:** [Step 63, Step 64, Step 65]
- **parallel_safe:** true **against Step 67** (disjoint new directories; same dependencies)
- **Spec slice:** §30.6 in full **including §30.6.1**; §30.2 F1-F8 and **F15-F19** (F5/F17's override
  dict, F6/F7's measured monotonicity and cost, F18's second solve direction, F19's refusal); §30.8's
  `test_airbrake_sizing.py` block; §30.3 for the wrapper.
- **Do:** `AirbrakeSpec`/`AirbrakeSolution`; `brake_overrides` (the single place the override dict is
  built — under Step 65 it is the plain `"full"` + trigger + time + `Cd` + `S_max` dict, no gain);
  `apogee_for_cda` and `apogee_for_deploy_time` (the two objective-function seams); one
  `_solve_scalar` helper implementing §30.6's five steps (refusal check, endpoint runs, flat/bracket
  diagnosis, `brentq`, final run) with `solve_airbrake` dispatching on `spec.solve_for`;
  `evaluate_airbrake` for the report-only path; `print_solution`, `save_solution_csv`, `save_overlay`,
  `main`. `targets.py` with the named `SPECS` dict of §30.6. The module docstring in App 2/3's
  register: the question, the explicit non-scope list from §30.1, the MATLAB precedent and what
  replaced it, the three triggers and **which of them can be solved against an apogee target and
  why** (§30.6.1's table), and both invocations (`python run_airbrake.py`,
  `python -m apps.airbrake_sizing.solve_cda`).
- **Check:** §30.8's list, with the **round-trip pin** and the **`after_apogee` refusal** as the two
  primary checks. Then: the app run end to end against `demo_75mm_airbrake` for each of the four
  named specs — the solve, the timer solve, the mirror (`solve_for="deploy_time"`) solve and the
  report-only one — printing the §30.6 blocks and writing both artifacts; the actual numbers go in
  the step report (**this design pins no apogee values**); an unreachable target prints the loud
  diagnostic and exits 0; `git status` shows **zero** `sim/` files touched **by this step** (Step 65
  owns the `sim/` diff).
- **Commit:** "Step 66 (Phase 2.13): App 4 -- airbrake C_dA determination against the real solver"

### [Step 67] App 5 mode (b) — the weight-vs-aero trade surface

- **Module/boundaries:** new `apps/weight_aero_tradeoff/{trade_surface.py,scenarios.py}`; new
  `run_trade.py`; new `tests/test_weight_aero_tradeoff.py`. **No `sim/` file, no other app.**
- **Assignee:** developer
- **depends_on:** [Step 63, Step 64]
- **parallel_safe:** true **against Step 66** (and independent of Step 65 — App 5 never touches the
  airbrake)
- **Spec slice:** §30.7.1 in full; §30.2 F9-F10 and F13; §30.8's surface block; §30.3 for the wrapper.
- **Do:** `TradeAxes`/`TradeSurface` (`apogee_at`, `gradients`, `exchange_rate`), `build_surface`,
  `print_surface_table`, `print_exchange_rates`, `save_surface_csv` (long format),
  `save_contour_plot` (app-local matplotlib, filled iso-apogee contours, baseline marked), `main`.
  The `C_dA` axis is swept via `aero.C_x` at fixed `aero.S` — F9's reason goes in the docstring, not
  just the code. `scenarios.py` carries the default grid literal with its justification.
- **Check:** §30.8's surface block, with the **exact `S*C_x` invariance** and the **node-exact
  interpolation** as the primary checks. `python run_trade.py --mode surface` prints the table and the
  exchange rates, writes CSV + PNG; the printed exchange rate at the baseline and the 121-run
  wall-clock go in the step report (F10 gives ~1.86 mm²/g and ~5.8 s as the expected order of
  magnitude, **not** as a pin).
- **Commit:** "Step 67 (Phase 2.13): App 5 mode (b) -- weight-vs-aero trade surface and exchange rate"

### [Step 68] App 5 mode (a) — named-scenario comparison

- **Module/boundaries:** new `apps/weight_aero_tradeoff/compare_configs.py`;
  `apps/weight_aero_tradeoff/scenarios.py` (append `SCENARIOS`); `run_trade.py` (the `--mode`
  branch); `tests/test_weight_aero_tradeoff.py` (append). **No `sim/` file, no other app.**
- **Assignee:** developer
- **depends_on:** [Step 67] (shares the app directory, `scenarios.py` and the wrapper)
- **parallel_safe:** false
- **Spec slice:** §30.7.2 in full; §30.8's mode-(a) bullets; App 3's `compare_motors`/
  `print_motor_table` as the shape to mirror (`apps/motor_selection/compare_motors.py:320-416`).
- **Do:** `ConfigRun`, `evaluate_config`, `compare_configs`, `print_comparison_table` (with the
  `mass_kg` and `cda_axial` columns that make it a trade table), `save_comparison_csv`,
  `save_overlay`, `main`; `SCENARIOS: list[Variant]` in `scenarios.py` with each entry's `notes`
  recording where its numbers came from; `--config a,b,c` accepting registry names as well as the
  variant list.
- **Check:** §30.8's mode-(a) bullets; `python run_trade.py --mode compare` prints the ranked table and
  writes both artifacts; the table goes in the step report. Cross-check worth one line in the report:
  for two scenarios that differ **only** in `(m, C_dA)` and lie inside Step 67's grid box, mode (a)'s
  apogees agree with `TradeSurface.apogee_at` to interpolation accuracy — the two modes must not
  disagree where they overlap.
- **Commit:** "Step 68 (Phase 2.13): App 5 mode (a) -- named-configuration comparison"

### [Step 69] Migrate the existing callers onto `configs/` (D-32-gated)

- **Module/boundaries:** `run.py`; `apps/cfd_conditions/select_conditions.py`;
  `apps/motor_selection/compare_motors.py` (`_demo_baseline` becomes a one-line re-export of
  `configs.demo_75mm.CONFIG`); new `run_motor_sweep.py`, `run_cfd_conditions.py`;
  `tests/test_configs.py` (append the equality pins if not already there). **No `sim/` file.**
- **Assignee:** developer
- **depends_on:** [Step 63, Step 64]
- **parallel_safe:** false (touches three existing entry points)
- **Spec slice:** §30.4's seed-config table (the byte-equality requirement), §30.3 (the wrappers),
  D-32.
- **Do:** replace the three in-place `Params`/`State` literals with `configs.get(...)` lookups,
  keeping `_demo_entries()` and `MOTORS` exactly where they are; add the two remaining root wrappers;
  add the one-line docstring clarification to `run.py` (§30.3).
- **Check:** **the gate is bit-for-bit** — `run.py`'s printed summary, both of its sweep tables, and
  `output/trajectory.csv` byte-identical to the pre-step run; App 2's printed condition table and
  `output/cfd_conditions.csv` byte-identical; App 3's table and CSV byte-identical. 289+ green with no
  edits to `tests/test_motor_selection.py`. All five entry points run from a clean checkout.
- **Commit:** "Step 69 (Phase 2.13): migrate run.py and Apps 2-3 onto configs/ (bit-for-bit)"

---

## 30.10 Decision points for the user (D-28 … D-42)

Numbering continues `architecture-29-motor-selection.md` §29.10, which used D-18 … D-27.

**Answered by the user on 2026-10-13** (recorded here so the forks below are not re-asked):
**D-29 = (a)**, four thin root wrappers, `run.py` unchanged. **D-30 = (a)** and **D-31 = (a)**, the
`configs/` package of Python literals with `Config` + `Variant`, which also settles **D-32 = (a)**
(migrate `run.py`/App 2/App 3's demo baseline behind the bit-for-bit gate;
`apps/motor_selection/motors.py` stays put). **D-38 = (a)**, both App 5 modes, surface first.
**D-36 is reworked and re-opened below** — it is the only open gate in the phase.

**D-28 — where the stats bundle lives, now that three apps want it.** *Purpose: one implementation of
the ascent-window flight statistics, shared by Apps 3/4/5.*

| Option | Pros | Cons |
|---|---|---|
| **(a) promote to `apps/common/flight_stats.py`, App 3 re-exports (recommended)** | one implementation of the numerics this project pins; `FlightStats` is the honest name; existing tests pass **unedited** because they import `flight_stats` from `compare_motors` (F11); bit-for-bit gate is cheap | edits a shipped, verified app (the only real cost) |
| (b) Apps 4/5 import from `apps.motor_selection.compare_motors` | zero change to App 3 | an airbrake app importing a motor app is a coupling nobody would predict; `MotorStats` is the wrong name; App 3 becomes a de-facto library with no mandate to stay one |
| (c) each app computes its own | total isolation | the same ~40 lines of grid/window/RHS-re-evaluation code three times, each able to drift from the tested one — exactly what §29.4's pinned tests exist to prevent |

**Recommendation: (a).** The migration is mechanical and provable (byte-identical table + CSV, no
test edits). If the user would rather not touch App 3 at all, (b) is survivable and (c) is not.

**D-29 — entry-point layout: how the "5 run files" are actually invoked.** — **ANSWERED 2026-10-13:
(a), four thin root wrappers.** *Purpose: the user asked
for five run files; today four of the five are `python -m` module paths.*

| Option | Pros | Cons |
|---|---|---|
| **(a) four new thin root wrappers + `run.py` (recommended)** | literally what was asked for; discoverable (`ls` shows the five tools); each wrapper is the natural home for `--config`; fixes F12's path-invocation trap, since the repo root *is* the script directory; `python -m` keeps working | four new files (~6 lines each) and a second front door per app |
| (b) keep `python -m apps....` only | zero new files; one invocation convention | only one of the five is a "run file"; the user's mental model and the repo's shape stay mismatched |
| (c) one `run.py <tool> [args]` dispatcher with subcommands | tidiest shell UX; one argparse tree | turns `run.py` — which *is* the user's "1st simple simulation" — into a dispatcher, so the first tool loses its file; a bigger change to the one entry point that already works |

**Recommendation: (a).** Cheap, reversible, and the only option that matches the request as stated.

**D-30 — config system: location and format.** — **ANSWERED 2026-10-13: (a), the `configs/`
package of Python literals.** *Purpose: named reusable scenarios, many of them,
history tracked.*

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(a) `configs/` package, one module per config, registry in `__init__.py` (recommended)** | git log per config file *is* the history; a config is a Python literal with commented numbers (D-23, already approved); `name → Config` lookup enables `--config`; no parser, no dependency | config is code (not editable by a non-programmer) | free |
| (b) one `configs.py` with a dict of everything | fewest files | one file grows without bound; two configs edited in one commit share a diff; no per-config history | free |
| (c) `data/configs/*.json` (or YAML) | editable without Python; language-neutral | re-opens D-23 and loses on every count: no comments, `None` needs a sentinel, heterogeneous values need coercion, and YAML is a new dependency (F14); `data/` means *physical input* in this repo | free (JSON) / new dep (YAML) |
| (d) no shared configs — each app keeps its own literal (status quo) | zero work | the user's actual request unmet; the demo baseline already exists twice |

**Recommendation: (a).** Note the escape hatch, as with D-23: every app takes a `Config` *object*, so
a `load_config_json(path)` loader is a later ~15-line addition that changes nothing else.

**D-31 — what a config *is*: complete scenario, delta, or both.** — **ANSWERED 2026-10-13: (a),
both `Config` and `Variant`.** *Purpose: App 3 wants one baseline
plus a list of motor-keyed deltas; App 5 wants 2+ complete named scenarios.*

| Option | Pros | Cons |
|---|---|---|
| **(a) both objects: `Config` (complete) + `Variant` (named delta), with `Config.derive` (recommended)** | serves both shapes without bending either; `Variant` is the already-proven `MotorEntry.overrides` pattern, generalised; `derive` keeps the config set DRY while each config's numbers stay in exactly one place | two concepts to learn instead of one |
| (b) complete `Config`s only | one concept | App 3's five motors become five near-duplicate configs, destroying the "the equal-impulse pair is identical except the curve" guarantee §29.5 relies on |
| (c) deltas only, against one root config | maximally DRY | no natural root; every config's actual values become indirect, which is the opposite of what a commented literal is for |

**Recommendation: (a).**

**D-32 — do the existing callers migrate onto `configs/` (Step 69)?** — **ANSWERED 2026-10-13: (a),
migrate behind the bit-for-bit gate; `motors.py` stays put.** *Purpose: "reuse across apps"
only materialises if the apps actually share.*
(a) **migrate `run.py`, App 2 and App 3's `_demo_baseline` behind a bit-for-bit gate, leave
`apps/motor_selection/motors.py` exactly where it is (recommended)** — the baseline vehicle stops
existing twice, the gate is provable because the numbers are identical, and App 3's study list stays
App 3's; (b) new apps only, existing untouched — lowest risk, but then `configs/demo_75mm.py` and
`_demo_baseline()` are two copies of one vehicle, which is the defect the config system exists to
remove; (c) migrate everything including `MOTORS` into `configs/` — rejected: a motor list is study
input, not a vehicle config (§30.3's convention), and moving it breaks App 3's tests for no gain.

**D-33 — config selection UX.** (a) **`--config NAME` + `--list-configs` via a shared
`apps/common/cli.py`, on the new apps and the wrappers only (recommended)** — ~30 lines of argparse,
and the one thing that makes "use different configs for different apps" a runtime choice rather than
an edit; (b) a module-level constant per app, edited by hand (zero machinery, status quo, but every
config switch is a source edit); (c) an env var or a pointer file (invisible state, worst of both).

**D-34 — App 4: what scalar is solved for.** *Purpose: the airbrake model takes `Cd` and `S_max`
separately, but only their product has physical effect (F1).*

| Option | Pros | Cons |
|---|---|---|
| **(a) solve for `C_dA_airbrake`, with `cd_brake` a user input and `S_max = C_dA/Cd` reported (recommended)** | same variable and same `[0, 10]` bounds as the user's MATLAB; one search variable; still prints the mechanism-design number (`S_max`, in cm²); survives the future combined-`C_dA` refactor unchanged | the thing searched is not literally a `Params` field (one line of mapping) |
| (b) solve for `airbrake_S_max` with `Cd` fixed | the variable *is* a `Params` field | the bounds then depend on the chosen `Cd`, so the precedent's `[0, 10]` stops being meaningful; the user has to pre-divide to compare with their MATLAB run |
| (c) solve for `Cd` **and** `S_max` | "more general" | **ill-posed**: the model only ever uses the product (F1), so the objective has a continuum of minimisers and any optimizer's answer is arbitrary |

**Recommendation: (a).**

**D-35 — App 4: search method.** *Purpose: find the `C_dA` that hits a target apogee.*

| Option | Pros | Cons |
|---|---|---|
| **(a) `brentq` root-find on `apogee(C_dA) − target`, with an endpoint bracket check (recommended)** | exploits F6's measured strict monotonicity; 17 runs / 1.2 s / 1.4e-4 m residual (F7); bracketing **proves** reachability, so "your target is unreachable with any brake" becomes a clear diagnostic instead of a bound with a plausible-looking objective | not the precedent's method, so a number-for-number comparison with the MATLAB run needs (c) |
| (b) `minimize_scalar(method="bounded")` on `(apogee−target)²` | literal translation of MATLAB `fminbnd`; no bracketing needed | minimises a squared residual whose root structure it then has to rediscover; the objective is very flat over most of `[0, 10]` (F6), so bound-hunting wastes runs; an unreachable target returns a bound and "converged" |
| (c) both, behind a `method=` argument | lets the user reproduce their MATLAB result exactly *and* use the better path | ~10 extra lines and a second code path to keep tested |

**Recommendation: (a)**, with (c) as a cheap concession if the user wants a MATLAB cross-check — in
which case (a) stays the default.

**D-36 REVISED — the three airbrake deployment triggers: through what mechanism?** *(Supersedes the
original D-36, which asked only how a single "held fully open" window should be expressed. The user's
2026-10-13 answer asked for three triggers — "after burnout, after specified time, after apogee" —
and in the same breath for "no sim file touched".)*

**Part 1 — the finding the user needs before choosing.** Those two requirements **cannot both hold
for two of the three triggers.** Confirmed by reading (F15-F16) and by measurement (F17-F19):
"after burnout" is free today; "after a specified time" is unreachable because `t` enters the
existing law only through `thrust_curve.thrust(t, y, p)` and `Params.control` has no time field;
"after apogee" is impossible because `y[VZ] >= 0.0 → return 0.0` sits in the law's body. Step 59's
`hold`/`sampling` path is **not** an escape hatch — it recomputes the same law once per tick, its
channel registry is module-private, and it requires `sample_rate_hz > 0` + `method="rk4"`, which
`flight_stats` refuses outright. **The orchestrator's reading was right on all three counts.**

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(a) edit `sim/control.py` + `sim/params.py`: a trigger dispatch dict + a `"full"` law (recommended)** | all three triggers, honest `Params` repr, `Result.params` stays a complete record of what flew; copies a pattern this repo **already ships** — `forces.parachute_deployed` implements the parachute's `timer`/`apogee` triggers in exactly this shape (`forces.py:280-292`), so there is nothing to invent; bit-for-bit safe for every existing config by construction (new fields defaulted, new dict entries unreachable unless named, `"proportional"` untouched); one isolated step with its own gate; opens the seam that later lets `"proportional"` be gated on a trigger too | breaks the phase's "no `sim/` change" framing — which is exactly what needs the user's yes | `sim/params.py` **+2 lines**; `sim/control.py` **+~35 lines**; ~6 tests; **1 extra step** (65) |
| (b) the app registers its own trigger laws into `sim.control._AIRBRAKE_CONTROLLERS` at import | satisfies "no `sim/` **file** touched" literally; all three triggers; there *is* precedent for registering into these private dicts — but only in tests, with monkeypatch-and-restore (`tests/test_control.py:291-337`, `tests/test_sampling.py:150-160`) | shipping code mutating another package's private module state at import time: invisible, import-order-dependent, and it breaks the Step-45 invariant that `Result.params` records what produced the run (the trigger time has to travel in a closure or be smuggled into a field named for something else), so every printed result must re-state the trigger by hand | ~25 lines in the app, 0 in `sim/`; the invariant is the real cost |
| (c) stay strictly zero-change: ship `"after_burnout"` only | genuinely no `sim/` involvement of any kind; F5/F17 show it is exact; the apogee-sizing use case — the user's actual "3rd run file" — is **fully served** by this one trigger | delivers **1 of the 3 requested laws**; the other two are not approximable (a *predicted-apogee threshold* trigger is also expressible via the existing gain, but that is a fourth, different law, not a timer and not post-apogee) | free |

**Recommendation: (a).** Three reasons, in order of weight. (1) It is **+2 lines of `Params` and
~35 lines of `control.py`**, in a shape this codebase already uses for the parachute — the smallest
honest version of what the user asked for, not a new subsystem. (2) It is **bit-for-bit safe by
construction**, so the risk to the 289 existing tests is structural, not a matter of care. (3) The
alternative that technically honours "no sim file touched", (b), pays for that wording by breaking a
real invariant (`Result.params` as the record of the run) in *shipping* code — a worse outcome than a
small, reviewed, single-commit `sim/` diff. If the user's "no sim file touched" is absolute, (c) is
the honest answer and the app should ship with one trigger rather than three pretend ones.

**Part 2 — what `"after_apogee"` is *for*, given it cannot size a brake.** This needs the user's
answer regardless of Part 1, because it is a scope question, not a mechanism one. F19 measured the
apogee to be **flat to 2.4e-3 m across `C_dA ∈ [0, 10]` m²** under that trigger — not weakly
sensitive, *exactly* insensitive, since the trigger fires only strictly after the apogee instant. So
no apogee-target solve exists under it. Worse, the descent it would otherwise be judged on is
currently nonphysical in this project: with a brake the vehicle hits the ground **sooner** (20.7 s vs
25.7 s) at **5285 m/s**, or never reaches it at all for `C_dA ≥ 0.1 m²`, because the axial aero force
acts along the **body** axis and the attitude stays frozen nose-up through a tail-first fall
(backlog **B17**).

- **(i) implement the trigger, refuse to solve under it, report only (recommended).** The capability
  and the `Params` record exist; App 4 prints a precise refusal naming the flat objective and the
  B17 caveat; a descent objective waits for B17. Cost: ~0 beyond the trigger itself.
- (ii) implement the trigger **and** a descent objective now (target impact speed or descent
  duration). Both are monotone in `C_dA` in principle, so the same `brentq` machinery applies — but
  in this project they would be optimizing a measured artifact (5285 m/s), so the tool would produce
  confident nonsense. ~40 extra lines and a wrong answer.
- (iii) drop `"after_apogee"` from the trigger set until B17 is fixed. Smallest scope, and honest —
  but then the user asked for three laws and gets two, and the `Params` has no way to even express
  the case.

**Recommendation: (i)**, with **B23** recording the descent objective as blocked on **B17**.

**D-37 — App 4: launch-to-apogee, or the precedent's mid-flight start.**

| Option | Pros | Cons |
|---|---|---|
| **(a) full launch → apogee, real motor (recommended)** | one obvious semantics; the solved `C_dA` is valid for the flight you actually fly; no state-injection subtleties; 60 ms/run, so ~1.2 s per solve (F7) | re-integrates a powered phase that is identical for every iterate |
| (b) mid-flight start from an injected burnout state (the precedent's `X0`) | faithful to the MATLAB driver; ~2.4× faster per run (F8) | **requires `thrust.motor_curve = ""` or the motor re-ignites at `t = 0` — measured: 1954.7 m instead of 996.8 m** (F4/F8); silently drops the mass state if the variable-mass model is on; the user must supply a burnout state from somewhere |
| (c) hybrid: run launch→burnout once, then iterate the coast only | measured **exactly** equivalent (Δ = 8.3e-5 m) and 2.4× faster | saves ~0.7 s per solve for a second branch of restart logic and all of (b)'s caveats — a real optimisation with no present need (**B21**) |

**Recommendation: (a).**

**D-38 — App 5: which mode(s), and in what order.** — **ANSWERED 2026-10-13: (a), both modes,
surface first.** *Purpose: the user's own open question.*

| Option | Pros | Cons |
|---|---|---|
| **(a) both, surface (b) first then comparison (a) (recommended)** | the surface is the general, reusable answer and yields the exchange rate (F10: 1 g ≈ 1.86 mm²); the comparison is ~70 lines on top of the config/`Variant` system and covers the cases the surface's two axes cannot span (different aero table, motor, geometry, site); two steps, two commits, either can ship alone | two modules instead of one |
| (b) surface only | one deliverable, maximum generality per line of code | cannot compare two configurations that differ in anything but `(m, C_dA)` — which is most real candidate pairs |
| (c) comparison only | simplest; closest to App 3's proven shape | answers "which of these two" but never "what is the trade rate", so every new component question needs a new pair of runs |

**Recommendation: (a).** If only one can be built, (b) — the exchange rate is the thing that
generalises.

**D-39 — App 5: surface axes and how they are swept.** (a) **2-D, `C_dA` (swept via `aero.C_x` at
fixed `aero.S`) × `weight.m` (recommended)** — F9 measured apogee as a function of the product
`S*C_x` to the last digit, so one drag scalar is legitimate, and sweeping `C_x` rather than `S` leaves
the normal-force and pitching-moment terms untouched; (b) 1-D in `C_dA` only — cheaper, and deletes
the weight half of "weight vs aero"; (c) 3-D (add a motor or target axis) — 10× the runs and no 2-D
contour plot; a different tool (**B18**).

**D-40 — App 5: is the surface persisted as a reusable artifact?** (a) **CSV + contour PNG under the
gitignored `output/`, recomputed on demand, with `apogee_at`/`exchange_rate` as the in-memory query
API (recommended)** — 121 runs is 5.75 s (F10), so a cache would buy seconds and risk a stale surface
silently answering for a changed vehicle; (b) commit it under `data/surfaces/` as a reusable input —
closest to the user's literal "precompute … get surface which can be used for every component", but
`data/` in this repo means measured/synthetic *physical input*, not computed output, and a committed
surface has no link back to the `Params` that produced it; (c) (b) plus a
`RegularGridInterpolator`-backed loader — the full version, worth building only once a surface takes
minutes rather than seconds.

**D-41 — tests for the new apps.** (a) **pinned tests per step, per §30.8 (recommended)** —
continues D-25; the round-trip pin (App 4) and the `S*C_x` invariance (App 5) are both cheap and
would catch the exact errors most likely to occur; (b) structural smoke tests only (fast, misses
units/axis-order errors); (c) none, following App 2's precedent (leaves two optimizers unpinned,
which this project does not do elsewhere).

**D-42 — naming of the two new apps.** (a) **`apps/airbrake_sizing/solve_cda.py` and
`apps/weight_aero_tradeoff/{trade_surface,compare_configs}.py` (recommended)** — directory names the
question, module is verb-noun, mirroring `cfd_conditions/select_conditions.py` (D-24); (b)
`apps/airbrake/` and `apps/cfd_optimization/` — closer to the user's own words, but "cfd
optimization" names something this tool does not do (it runs no CFD; it produces the trade rate CFD
results get judged against), and "airbrake" alone reads like a model, not a study; (c) `apps/app4_*`
/ `apps/app5_*` — matches the chat labels and nothing else.

---

## 30.11 Risks

1. **The airbrake trigger mechanism is the one open gate, and two of its three options carry a
   non-obvious cost.** Under D-36-revised(a) the phase stops being strictly `sim/`-free (mitigated by
   confining the diff to one step, +2 defaulted fields, ~35 lines, a bit-for-bit gate, and a pattern
   copied from `forces.parachute_deployed`). Under (b) nothing in `sim/` is *edited* but shipping app
   code mutates `sim.control`'s private dispatch dict at import time and `Result.params` stops being
   a complete record of the run (mitigated only by the app re-printing the trigger everywhere, which
   is a worse trade). Under (c) the user gets one trigger instead of three. There is no option that
   is free of all three costs — that is the finding, not an oversight.
2. **A post-apogee airbrake invites a confident wrong answer.** The apogee objective is flat to
   solver noise and the descent is nonphysical here (F19). *Mitigation:* App 4 refuses to solve under
   that trigger and prints why, the generic flat-objective detector catches the same shape from any
   other cause, and the descent objective is parked as B23 behind B17 rather than built.
3. **The 1-D drag axis is only 1-D for the axial force.** F9's invariance is exact, but it is exact
   because `C_dA` is swept via `C_x`. Someone later sweeping `aero.S` "because that's the area" would
   silently also move the normal force and the pitching moment. *Mitigation:* stated in
   `trade_surface.py`'s docstring, in §30.7.1 and as a test (the `S*C_x` equality pin).
4. **Added mass with unchanged pitch inertia.** The surface's mass axis moves `weight.m` and leaves
   `weight.I` alone — exact for the attitude-frozen demo scenario, an approximation for anything with
   nonzero `C_z`/`C_m`. *Mitigation:* printed with the surface, recorded as **B22**.
5. **The exchange rate is local.** F10's 1.86 mm²/g holds at that vehicle, that motor and that point
   on the surface; it is not a constant of nature and the surface is visibly nonlinear (F6's
   saturation). *Mitigation:* `exchange_rate(cda, m)` takes the point as an argument rather than
   returning a scalar; the printed table reports it at several grid points, not one.
6. **An unreachable airbrake target is the most likely user error** (a target above the brake-closed
   apogee, or below what even 10 m² can achieve). *Mitigation:* that is precisely what the two
   endpoint runs and the bracket/flat check exist for (§30.6 step 3), and it is a tested path.
7. **Two config homes could drift.** After Step 69, `configs/demo_75mm.py` is the vehicle and
   `apps/motor_selection/motors.py` is App 3's study list. A reader could reasonably look for the
   motor list in `configs/`. *Mitigation:* §30.3's two-kinds convention is stated in `schema.py`'s
   docstring, in `motors.py`'s docstring, and here.
8. **Step 64 edits a verified app, and Step 65 edits verified `sim/` physics plumbing.** Any
   behaviour change in either is a regression in something already signed off. *Mitigation:* both
   gates are byte-identical/unchanged output plus 289 green tests **with no test edits** — if any of
   that fails, the step is wrong, not the gate. Step 65 additionally has `git diff --stat` as a hard
   boundary check (exactly two `sim/` files, `+2` lines in `params.py`).
9. **Five entry points to keep working.** More front doors, more ways for one to rot unnoticed.
   *Mitigation:* Step 69's Check runs all five from a clean checkout; the wrappers are thin enough
   (~6 lines) that there is nothing in them to rot except the import path.
10. **`brentq` assumes continuity.** Apogee vs `C_dA` is smooth here (F6), but a scenario with a
   recovery/airbrake interaction or a rail constraint could in principle introduce a kink.
   *Mitigation:* the monotonicity test; the achieved-vs-target error is always reported, so a bad
   solve is visible rather than silent.
11. **The `"after_time"` trigger has a foot-gun default.** `airbrake_deploy_time = 0.0` means
   "deployed from `t = 0`", i.e. on the pad — measured as a 609 m apogee loss (F18). *Mitigation:*
   it is the exact semantics `Recovery.deploy_time = 0.0` already has under `trigger="timer"`, so the
   behaviour is at least consistent; documented in `params.py`'s field comment and in App 4's report
   line, which always prints the trigger instant it actually flew.

---

## 30.12 Rejected options, and the backlog items this opens

**Rejected: extending `sim.report.sweep` to 2-D for App 5.** `sweep(base, path, values, s0)` varies
one dotted path and attaches the four-field `flight_summary` (F13). A 2-D grid needs a different
return shape *and* a different payload (the ascent-window bundle, D-18/D-19), so bending it would
change a tested `sim/` API and its printed-table companion for one caller. The app's own double loop
is ~12 lines.

**Rejected: putting the contour plot in `sim/plotting.py`.** That module's contract is
`Result → Figure` (F13). A surface is not a `Result`, and the only `sim/` file this phase may touch
is `sim/control.py` (plus two lines of `sim/params.py`), under Step 65's gate.

**Rejected: re-gating the existing `"proportional"` law on the new trigger dispatch.** It would be
three lines and it is the obvious next move once `airbrake_triggered` exists — and under the default
trigger (`"after_burnout"`) it is even bit-for-bit. Rejected *for this phase* anyway: it changes the
behaviour of a law that is not what the user asked about, in a step whose whole value is that its
blast radius is provably zero. The seam is left in place for a later, deliberate step.

**Rejected: a retraction / duty-cycle model for the three triggers.** Each trigger is a pure onset
latch (§30.6.1). Retraction needs a second condition per trigger and a decision about what happens
between them; the apogee answer is unaffected either way (nothing after apogee moves the apogee), so
it buys nothing now. **B19.**

**Rejected: an `apps/common/` table/report framework.** Each app's table answers a different question
and its column set *is* its interface; a shared formatter would be a lowest-common-denominator layer
that every app then works around. Only `flight_stats` (numerics this project pins), the output path
and the `--config` parsing are shared — the test for "does it belong in `apps/common/`" is "two apps
need it **and** it computes something, not formats something".

**Rejected: a config *database*, registry file or revision scheme.** Git already provides config
history, and anything added beside it would duplicate and then contradict it. One module per config,
committed, is the whole mechanism.

**Rejected: auto-discovering config modules.** A half-finished draft in `configs/` would break every
app's import, and "who uses this config" would stop being greppable. The registry is an explicit
tuple.

**Rejected: solving for the airbrake's `Cd` and `S_max` separately** (D-34c) — ill-posed, F1.

**Rejected: a closed-loop airbrake controller in this phase.** The user's framing is "for now only as
change in `C_dA`"; `sim/control.py`'s `"proportional"` law already exists for the real-time problem
and is deliberately untouched.

### Proposed new backlog items

- **B18 — higher-dimensional trade studies (motor × mass × `C_dA`, or target × vehicle).** App 5's
  surface is 2-D because that is what plots and what F10 makes cheap. A third axis is a nested loop
  but a genuinely different output (no contour, a table or a slice viewer) — a separate tool, and
  the same conclusion §29.12's **B16** reached for App 3.
- **B19 — airbrake deployment beyond a pure onset latch.** Step 65 (if approved) gives three *onset*
  triggers and a fully-open/stowed latch. Beyond it: retraction and a second condition per trigger,
  an actuator rate limit, a deployment *schedule* (ramp to a partial fraction), an altitude trigger,
  a `C_dA(M)` dependence, and re-gating the existing `"proportional"` law on the same trigger
  dispatch. App 4's `brake_overrides` plus `sim/control.py`'s `_AIRBRAKE_TRIGGERS` are the only two
  places any of this lands.
- **B20 — CFD-output ingestion.** App 2 produces the condition list and App 5 produces the trade
  rate, but nothing in this repo reads a CFD result back. The target is `data/aero/*.csv` +
  `aero.model = "table"`, which already exists — what is missing is the converter and a convention
  for which CFD output columns map onto `C_A0`/`C_N_alpha`/`C_m_alpha` per Mach. This is the step
  that would close the user's CFD loop.
- **B21 — coast-only restart as an optimizer speed-up.** Measured exactly equivalent (Δ = 8.3e-5 m)
  and 2.4× faster (F8). Worth building only when a single `run_sim` stops being ~60 ms — e.g. under a
  sounding atmosphere, a Mach-indexed aero table, or a Monte Carlo wrapper.
- **B22 — mass changes that also change inertia and geometry.** App 5's mass axis moves `weight.m`
  only; a real mass addition moves `weight.I`, and usually `lengths.l1` (the CoP→CoG arm) too. A
  physically complete mass axis needs a component model (where the mass is added), which is a design
  decision the user has not made yet — and §29.12's **B15** is the same gap seen from App 3's side.
- **B23 — a descent objective for the post-apogee airbrake, blocked on B17.** The `"after_apogee"`
  trigger exists as a capability but nothing can be solved against it: the apogee is independent of
  the brake by construction (F19, flat to 2.4e-3 m), and the obvious alternative objectives — target
  impact speed, target descent duration — are measured nonphysical in this project today (impact at
  5285 m/s with a 0.01 m² brake; no ground event at all for `C_dA ≥ 0.1 m²`), because
  `aero_force_body` applies the axial term along the **body** axis while a `C_z = C_m = 0` vehicle
  keeps a frozen nose-up attitude through a tail-first fall, so the brake's drag accelerates the
  descent. The fix is a `sim/` **physics** decision and belongs to **B17**: either an attitude model
  with a restoring moment, or axial drag that opposes the relative wind under reversed flow. Until
  then a descent-braking study would be optimizing an artifact, and App 4 refuses to run one.
