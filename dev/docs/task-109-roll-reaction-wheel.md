# Step 109 (Phase 2.17) — 2D roll dynamics with a reaction wheel

## Кратко (RU)

- Пользователь прямо попросил ввести в статью и в симулятор **развязанную крутильную степень свободы** (вращение вокруг продольной оси `x̂_r`), управляемую **реактивным маховиком** (внутренний гироскоп: раскручиваем маховик в одну сторону — корпус крутится в другую, внешний момент не нужен).
- Это **не** переход на 3D/6DOF. Проверено: в плоской модели (скорость рыскания `r ≡ 0`) гироскопическая связь крен↔тангаж **тождественно равна нулю** — она даёт момент по рысканию, а не по тангажу. Значит развязка физически честная, а не упрощение. Что она скрывает — момент рыскания `q·h_w` — записано в §109.1.4 и в `assumptions.tex`.
- **Главная находка (§109.2):** нельзя просто дописать компоненты в вектор состояния. RK45 в scipy считает норму ошибки как **RMS** (`norm(x)/sqrt(x.size)`), поэтому расширение вектора с 7 до 10 компонент меняет знаменатель и, следовательно, шаги интегратора — **даже если новые производные тождественно нулевые**. Измерено: 367 шагов против 358, расхождение 4e-9 в финальном значении. Поэтому ширина вектора **переменная**: 7 при `roll.model == "none"` (дефолт, бит-в-бит как сегодня), 10 при включённой модели.
- Состояние расширяется тремя компонентами: `gamma` (угол крена), `omega_x` (угловая скорость корпуса), `omega_w` (**абсолютная** скорость маховика). Интегрируется абсолютная скорость — её ОДУ `I_w·ω̇_w = τ_w` не содержит `ω̇_x`, то есть не требует решения связанной системы.
- Новый модуль `sim/roll.py` (свой dispatch законов управления), новая группа `Params.roll`, два новых коэффициента в `Params.aero`. `sim/control.py` и `sim/sampling.py` **не трогаются** — границы не пересекаются с параллельным Step 108.
- Дефолт — инертный: `roll.model = "none"`. Ни один закреплённый числовой пин не сдвигается. Пересогласование пинов не требуется.
- LaTeX: новая подсекция `\subsection{Roll and the reaction wheel}\label{sec:roll}` в `other-dynamics.tex` + правки в `assumptions.tex`, `appendix.tex` (конвенции), `backlog.tex` (пункт переехал из бэклога в модель), `models.tex` (фраза «момент крена без эффекта в 2D» больше не верна).
- Открытая развилка для пользователя — §109.2.4: вариант «переменная ширина» (рекомендую) против «интегрировать крен вторым проходом после основного прогона». Второй дешевле, но закрывает путь к 3D.

## Table of contents

| Section | Content |
|---|---|
| [§109.1](#1091-physics--the-roll-axis-with-a-reaction-wheel) | Physics: derivation, decoupling proof, what it hides |
| [§109.2](#1092-the-state-vector-fork--why-the-width-must-be-conditional) | **Decision:** state-vector extension, RK45 RMS-norm trap |
| [§109.3](#1093-params--the-roll-group-and-two-aero-coefficients) | `Params.roll`, `Params.aero.C_l`/`C_l_p` |
| [§109.4](#1094-simrollpy--the-new-module) | `sim/roll.py` — new module, full spec |
| [§109.5](#1095-simstatepy--the-width-gate) | `sim/state.py` — index constants, `width`, `to_vector` |
| [§109.6](#1096-simdynamicspy--the-decoupled-ode-block) | `sim/dynamics.py` — exact edits |
| [§109.7](#1097-simintegratepy--y0-width-and-eager-validation) | `sim/integrate.py` — exact edits |
| [§109.8](#1098-latex--what-this-step-already-wrote) | LaTeX: what the architect already wrote (done) |
| [§109.9](#1099-test-impact-table) | Test-impact table |
| [§109.10](#10910-acceptance-checks) | Acceptance checks (physics + bit-identity) |
| [§109.11](#10911-definition-of-done) | Definition of done |
| [§109.12](#10912-decision-log) | Decision log D-131..D-135 |
| [§109.13](#10913-deliberately-out-of-scope) | Deliberately out of scope |

**Spec slice for the implementer:** this file, plus `dev/docs/latex/sections-ai/other-dynamics.tex`
§`sec:roll` (the derivation, ~70 lines, already written by this step). Nothing else. Do **not**
read `architecture.md` or `models.tex` whole.

---

## §109.1 Physics — the roll axis with a reaction wheel

### 109.1.1 Notation

Taken from the paper's own backlog entry (`backlog.tex`, "Roll dynamics with a reaction wheel
(2D)"), which already fixed the symbols before this step; do not invent new ones.

| Symbol | Code | Meaning | Unit |
|---|---|---|---|
| $\gamma_r$ | `y[GAMMA]` | roll angle about $+\hat{x}_r$, right-hand rule | rad |
| $\omega_x$ | `y[OMEGA_X]` | airframe roll rate, $\dot\gamma_r$ | rad/s |
| $\varepsilon_x$ | — | airframe roll acceleration, $\dot\omega_x$ | rad/s² |
| $I_x$ | `p.roll.I_x` | vehicle axial MOI about $\hat{x}_r$, **wheel included and locked** | kg·m² |
| $I_w$ | `p.roll.I_w` | wheel's own axial MOI about the roll axis | kg·m² |
| $I_{x,a}$ | derived | airframe alone, $I_{x,a} = I_x - I_w$ | kg·m² |
| $\omega_w$ | `y[OMEGA_W]` | wheel **absolute** roll rate (inertial) | rad/s |
| $\omega_{w/r}$ | derived | wheel rate **relative** to the airframe, $\omega_w - \omega_x$ (what an encoder reads) | rad/s |
| $h_w$ | derived | relative wheel momentum, $I_w\,\omega_{w/r}$ | kg·m²/s |
| $\tau_w$ | derived | motor torque applied **to the wheel** about $+\hat{x}_r$ | N·m |
| $L_x$ | derived | external axial moment on the vehicle (aerodynamic) | N·m |
| $C_l$ | `p.aero.C_l` | static roll-moment coefficient (fin cant), **code sign** | — |
| $C_{l,p}$ | `p.aero.C_l_p` | roll-damping derivative, **code sign** (positive = damping) | — |
| $\hat\omega_x$ | — | non-dimensional roll rate, $\omega_x c/(2v_{rel})$ | — |

$c$ is the paper's moment reference length (`p.aero.d_ref` in code) and $S$ the reference area —
the same two the pitch moment uses; this step introduces **no** second reference geometry.

### 109.1.2 The two-body derivation

Treat the vehicle as two bodies sharing one axis: the airframe $A$ and the wheel $W$, the wheel
balanced on and spinning about $\hat{x}_r$. Only two torques exist about that axis: the external
aerodynamic moment $L_x$ on the airframe, and the motor torque $\tau_w$, which by Newton's third
law acts $+\tau_w$ on the wheel and $-\tau_w$ on the airframe.

$$\dot\gamma_r = \omega_x \tag{1}$$
$$I_{x,a}\,\varepsilon_x = L_x - \tau_w \tag{2}$$
$$I_w\,\dot\omega_w = \tau_w \tag{3}$$

**This is the form to integrate**, and the reason $\omega_w$ is stored *absolute* rather than
relative: (3) is then a standalone scalar ODE with no $\dot\omega_x$ on its right-hand side. Had
the state carried $\omega_{w/r}$ instead, its derivative would be
$\dot\omega_{w/r} = \tau_w/I_w - \varepsilon_x$ — algebraically fine, but it couples the two rows
of the Jacobian and invites the classic sign error. Integrate (3); report $\omega_{w/r}$ and $h_w$
as derived quantities.

**The momentum-exchange reading.** Total axial angular momentum is
$h_x = I_{x,a}\omega_x + I_w\omega_w$, which rearranges exactly to

$$h_x = I_x\,\omega_x + h_w, \qquad \dot h_x = L_x \tag{4}$$

Adding (2) and (3) reproduces (4) identically, so the implementation of (1)–(3) needs no separate
conservation bookkeeping. With $L_x = 0$ and the vehicle starting at rest, (4) gives the whole
point of a reaction wheel in one line:

$$\omega_x = -\,\frac{h_w}{I_x} \tag{5}$$

Spin the wheel up to momentum $h_w$ and the airframe counter-rotates at $-h_w/I_x$, with **no
external torque used**. This equation is the primary acceptance check (§109.10.1).

### 109.1.3 Saturation — the honest limit of the device

A reaction wheel has finite authority on two axes, and both must be modelled or the device is
fictitious:

- **Torque limit:** $|\tau_w| \le \tau_{max}$ (`p.roll.tau_max`) — the motor's stall torque.
- **Speed limit:** $|\omega_{w/r}| \le \omega_{w,max}$ (`p.roll.omega_w_max`) — the wheel's
  maximum relative speed. On reaching it the wheel **saturates**: from (5), $\omega_x$ can be held
  no further than $\mp I_w\omega_{w,max}/I_x$, and all roll authority in that direction is gone
  until an *external* torque desaturates it. This is the single most important qualitative
  behaviour of the model and must be reachable in a test (§109.10.2).

The speed clamp is **one-sided**: at $\omega_{w/r} = +\omega_{w,max}$ a positive $\tau_w$ is zeroed
but a negative one is still allowed (the wheel can always be braked back). A naive two-sided clamp
would lock the wheel at saturation forever.

### 109.1.4 Why roll is exactly decoupled here — and what that hides

The decoupling is **not** a convenient approximation inside the planar model; it is exact. The
proof, and the one caveat, both matter and are both written into the paper.

**Rigid-body gyroscopic coupling vanishes.** Euler's equations for an axisymmetric body
($I_{yy} = I_{zz} = I_t$) give the pitch channel

$$I_t\,\dot q = M_y - (I_x - I_t)\,r\,p$$

with $p = \omega_x$ the roll rate, $q$ the pitch rate and $r$ the yaw rate. The planar assumption
is $r \equiv 0$, so the coupling term $(I_x - I_t)\,r\,p$ is **identically zero** for any roll
rate whatsoever — not small, zero. Roll cannot drive pitch without yaw rate to pair with.

**The wheel's gyroscopic torque points out of the pitch plane.** A wheel carrying momentum
$h_w\hat{x}_r$ on a body pitching at $q\hat{y}_r$ produces

$$\vec{\tau}_{gyro} = -\,\vec{\omega}\times\vec{h} = -(q\hat{y}_r)\times(h_w\hat{x}_r) = +\,q\,h_w\,\hat{z}_r$$

a torque about $\hat{z}_r$ — pure **yaw**. It has no $\hat{y}_r$ component, so it cannot enter
(`eq:eom_rot`), and no $\hat{x}_r$ component, so it cannot enter (2). In the planar model it is
reacted by the same constraint that holds the motion in the plane, exactly like the out-of-plane
wind component the model already computes and discards.

**Aerodynamics is roll-angle-independent for an axisymmetric body.** $C_x, C_z, C_m, C_{m,q}$ are
functions of $(\alpha, M)$ only; none takes $\gamma_r$. So the existing force and moment chain is
untouched by the new state components, which is what makes the ODE block additive rather than a
rewrite.

**Flagged as neglected** (written into `assumptions.tex`, not hidden):

1. **Roll → yaw.** Both terms above are real yaw torques a 6DOF model would show. A planar model
   cannot represent them. This is the cost of the "2D" in the user's ask, and it is the honest
   reason this step is not a substitute for the 3D work (`research/3d_equations_of_motion.md`,
   still blocked on the $I_a$ fork at Step 30).
2. **Fin-induced roll-orientation dependence.** For a *finned* (not perfectly axisymmetric) body,
   $C_z$ and $C_m$ do depend weakly on $\gamma_r$ — a 4-fin airframe at angle of attack has a
   90°-periodic variation from fin–body interference and the fins' effective dihedral relative to
   the $\alpha$ plane. Modelling it needs $C_z(\alpha, M, \gamma_r)$, a table axis nobody has data
   for. Neglected explicitly.
3. **Roll lock-in / Magnus.** Resonance between roll rate and the pitch natural frequency, and
   Magnus side force at high spin, are both outside the planar model and outside the available
   coefficient set.
4. **Wheel mass properties are static.** The wheel's mass and its contribution to $m$, $I$ and
   $l_g$ are constant and already inside the existing mass model; *spinning* it changes none of
   them. Requires the wheel to be balanced and centred on the axis — stated as an assumption, not
   checked.

### 109.1.5 The aerodynamic roll moment

Written in the paper's own sign convention (positive coefficient opposes motion; positive damping
derivative damps — identical in form to `eq:aero_damped` for the pitch channel):

$$\vec{A}_{m,x} = -\,qSc\left(C_l + C_{l,p}\,\hat\omega_x\right)\hat{x}_r,
\qquad \hat\omega_x = \frac{\omega_x c}{2 v_{rel}},
\qquad q = \tfrac12\rho v_{rel}^2$$

so $L_x = -qSc\left(C_l + C_{l,p}\hat\omega_x\right)$, with $C_{l,p} > 0$ damping.

**Implement it division-free**, exactly as `forces.aero_moment_y` already does for $C_{m,q}$
(`sim/forces.py:~293`): a literal $\omega_x c/(2v_{rel})$ intermediate evaluates to
`0.0 * inf = nan` at $v_{rel} = 0$, which every unperturbed flight hits at apogee. The damping
term expands to

$$q\,c\,\hat\omega_x = \tfrac12\rho v_{rel}^2 \cdot c \cdot \frac{\omega_x c}{2v_{rel}}
  = \tfrac14 \rho\, v_{rel}\, \omega_x\, c^2$$

giving the form the code must use:

```python
L_x = -(flow.q * p.aero.S * p.aero.d_ref * p.aero.C_l
        + 0.25 * flow.air.rho * flow.V * p.aero.S * p.aero.d_ref**2 * y[OMEGA_X] * p.aero.C_l_p)
```

Both coefficients default to `0.0`, so $L_x \equiv 0.0$ bit-for-bit until a user supplies them —
which makes the torque-free reaction-wheel case (5) the model's own default behaviour, and is
exactly right: **nobody has roll coefficients for this airframe.** The paper says so and so does
the backlog.

---

## §109.2 The state-vector fork — why the width must be conditional

### 109.2.1 The trap, measured

The obvious implementation is "append three components with defaults, give them zero derivatives
when the model is off, done" — the Step 36 (`m`) pattern. **It breaks every RK45-pinned number in
the suite, and it does so silently.**

`scipy.integrate._ivp.common.norm` is an **RMS** norm:

```python
def norm(x):
    """Compute RMS norm."""
    return np.linalg.norm(x) / x.size ** 0.5
```

`RungeKutta._estimate_error_norm` divides by it, and `select_initial_step` uses the same norm for
$h_0$. So the state vector's **length appears in the step-size controller's denominator**. Adding
components whose error contribution is exactly zero *reduces* the error norm by
$\sqrt{7/10} \approx 0.837$, the controller accepts larger steps, and the trajectory changes at
the round-off-accumulation level — everywhere, on every scenario, including ones that never touch
roll.

Measured on this machine (numpy 2.5.4 / scipy 1.18.1, the versions D-77 pinned against), a 7-component
system versus the identical system padded to 9 with zero-derivative, zero-initial components, same
`rtol=1e-8`/`atol=1e-10`:

```
nsteps              367   vs   358
accepted t grid     not equal
final y[0]          -0.4294111988034225   vs   -0.42941119502798014
bit-identical       False
```

Reproduce with:

```python
import numpy as np
from scipy.integrate import solve_ivp
def f7(t, y):
    d = np.zeros(7); d[0] = y[1]; d[1] = -np.sin(y[0])*3.0 + 0.1*y[2]; d[2] = -0.2*y[2]
    return d
def f9(t, y):
    d = np.zeros(9); d[:7] = f7(t, y[:7]); return d
y7 = np.array([0.5, 0.0, 1.0, 0, 0, 0, 0.9]); y9 = np.concatenate([y7, [0.0, 0.0]])
a = solve_ivp(f7, (0, 20), y7, method="RK45", rtol=1e-8, atol=1e-10)
b = solve_ivp(f9, (0, 20), y9, method="RK45", rtol=1e-8, atol=1e-10)
print(len(a.t), len(b.t), a.y[0, -1] == b.y[0, -1])
```

`CLAUDE.md` is explicit that re-pinning is a user decision ("Перепин — только с «да» пользователя").
So the unconditional-width design is **not available** to this step without a separate approval
gate, and it would be a bad trade anyway: it spends the project's pin budget on a feature that is
off by default.

> Note for the record: Step 36 *did* widen the vector unconditionally (6 → 7) and therefore did
> move the RK45 pins at the time. That precedent is not a licence — there were far fewer pins then,
> and `tests/test_forces.py:138`'s `np.zeros(7)` comment is the scar tissue from it.

### 109.2.2 The design: conditional width, one gate, two widths

Exactly **two** widths exist, chosen by one gate:

| `p.roll.model` | Width | Components |
|---|---|---|
| `"none"` (default) | **7** | `x, z, vx, vz, theta, omega, m` — bit-for-bit today |
| `"free"`, `"wheel"` | **10** | `… , gamma, omega_x, omega_w` |

`"free"` does **not** get its own 9-wide layout. It is the 10-wide layout with
$\tau_w \equiv 0$ and $\dot\omega_w \equiv 0$ — i.e. aerodynamic roll only, wheel absent. One extra
width for one extra variant would double the plumbing for no physics; two widths is the whole
complexity budget.

### 109.2.3 Where the initial condition comes from

`State` grows three **defaulted** fields (`gamma=0.0, omega_x=0.0, omega_w=0.0`), so it remains the
single home of "the initial state", and a new conversion function gates the width:

```python
state.width(p)        -> 7 or 10
state.to_vector(s, p) -> np.ndarray of width(p)
```

The three `y0 = np.array(s0, dtype=float)` sites in `sim/integrate.py` (lines ~305, ~531, ~723)
become `y0 = state.to_vector(s0, p)`. When the model is off, `to_vector` **trims** to 7 — so a
non-zero `s0.gamma` with `roll.model == "none"` is silently dropped. That is the same contract
`y[M]` already has under `p.weight.m_d is None` ("the integrator never looks at this field"), and
it must be said in the docstring in those words.

Rejected alternative: initial roll conditions as `Roll.gamma0/omega_x0/omega_w0` params fields.
It keeps `State` at exactly 7 fields (zero churn at the ~4 direct `np.array(State(...))` call
sites, §109.9) but puts part of the initial state in `Params`, so `run_sim(p, s0)` would no longer
take its initial condition from `s0` alone. Not worth the lie for four mechanical edits.

### 109.2.4 DECISION REQUIRED — conditional width vs a second integration pass

A genuinely cheaper third option exists and the user should see it before the developer starts.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. Conditional width (recommended)** | One integrator, one RHS; roll is real integrated state; the only path that extends toward 3D or toward roll→pitch coupling later; zero pin risk | `State` is 10 fields but the vector is sometimes 7; `width(p)`/`to_vector(p)` plumbing in 4 files; index constants `GAMMA/OMEGA_X/OMEGA_W` are only valid when the model is on | ~1 step: 1 new module (~180 lines), 5 files edited, ~12 new tests |
| **B. Unconditional width 10** | Simplest code — no gate, no `width()`, `State` is always the state | **Moves every RK45-pinned number** (§109.2.1 measured); needs a user-approved re-pin of `tests/test_integrate.py` and every downstream pin; spends the pin budget on an off-by-default feature | ~1 step + a full re-pin pass + user approval gate |
| **C. Post-pass integration** | Zero touch to the main state vector, integrator or RHS; literally zero pin risk; smallest diff | Needs $q(t), v_{rel}(t), \rho(t)$ by interpolation off the finished solution (adds interpolation error the main path does not have); a second integration path to maintain; a dead end for any future roll→pitch or roll-dependent aero term; cannot run under the sampled/ZOH mode without duplicating it | ~0.6 step, but the work is thrown away if roll ever couples back |

**Recommendation: A.** C is tempting and honestly correct *today* (roll is exactly decoupled,
§109.1.4), but it is correct only as long as that stays true, and it makes the roll DOF
second-class — not visible to events, not visible to the ZOH mode, not visible to a controller
that might later want pitch and roll in one loop. A costs one step now and nothing later.

Questions worth stress-testing with the user before approval:

1. Is the reaction wheel wanted as a **studyable device** (sizing: how much $I_w\omega_{w,max}$ buys
   how much roll authority) or only as a **disturbance-rejection demo**? Sizing wants Option A plus
   an `apps/` utility; a demo is happy with C.
2. Roll is off by default and nobody has $C_l$/$C_{l,p}$ for this airframe. Is a roll model with
   zero aerodynamics useful enough to ship, or should the aero roll coefficients be researched
   first (they are a `\restodo` in the paper today)?
3. Should the rail freeze roll? Two rail buttons on a rail do mechanically prevent roll — but a
   tower or a single-button rail does not. The ticket assumes "frozen" (§109.6.3); it is a
   one-line change either way.
4. Under canopy the existing model freezes pitch attitude by fiat. Freezing roll too is consistent
   but physically wrong (a rocket under a canopy spins freely). Accept the inconsistency, or let
   roll run under canopy?

---

## §109.3 Params — the `Roll` group and two aero coefficients

### 109.3.1 New group, `sim/params.py`

Insert after `Actuator` (keeping the file's "one group per module that owns a dispatch" ordering —
the owning module is the new `sim/roll.py`):

```python
@dataclass(frozen=True)
class Roll:
    """Step 109 (task-109-roll-reaction-wheel.md; other-dynamics.tex SSRoll and
    the reaction wheel): the decoupled roll degree of freedom about x_hat_r and
    the reaction wheel that drives it.

    `model = "none"` (the default) is the off switch, and it is a *structural*
    one: the state vector stays 7 components wide (sim/state.py's `width`), so
    every pinned flight is bit-for-bit unchanged -- see task-109 SS109.2.1 for
    why a zero-derivative 10th component would NOT have been (scipy's RK45
    error norm is an RMS over the vector, so its length is in the step-size
    controller's denominator).

    `"free"`  -- roll angle/rate integrated, aerodynamic roll moment only, no wheel.
    `"wheel"` -- as "free", plus the reaction wheel (eqs. 2-3 of SS109.1.2).
    """
    model: str = "none"                    # none | free | wheel
    I_x: float = 0.0                       # vehicle axial MOI about x_hat_r, wheel INCLUDED
                                           # and locked [kg*m^2]; REQ when model != "none"
    # --- reaction wheel (model == "wheel") ---
    I_w: float = 0.0                       # wheel's own axial MOI [kg*m^2]; 0.0 -> no wheel,
                                           # tau_w forced to 0.0 and domega_w/dt == 0.0
    tau_max: float = float("inf")          # |tau_w| limit [N*m]; inf = unbounded torque
    omega_w_max: float = float("inf")      # |omega_w - omega_x| limit [rad/s]; inf = never saturates
    # --- control law (sim/roll.py's `_ROLL_LAWS` dispatch) ---
    law: str = "none"                      # none | rate_null | angle_hold
    kp: float = 0.0                        # angle_hold: gain on (gamma - gamma_cmd) [N*m/rad]
    kd: float = 0.0                        # rate_null/angle_hold: gain on omega_x [N*m/(rad/s)]
    gamma_cmd: float = 0.0                 # angle_hold: commanded roll angle [rad]
```

`inf` defaults for the two limits follow the `Actuator.rate_open`/`rate_close` precedent
(Step 103) for exactly the same reason: `0.0` would be a *physically meaningful* value (zero torque
authority / a locked wheel), so it cannot double as "no limit".

Register it on `Params`:

```python
    actuator:   Actuator   = field(default_factory=Actuator)
    roll:       Roll       = field(default_factory=Roll)     # Step 109
    solver:     Solver     = field(default_factory=Solver)
```

and update the `Params` docstring's group count (currently "twelve at Step 50, plus `Actuator`").

### 109.3.2 Two new fields on `Aero`

The roll coefficients are aerodynamics, so they live with `c_mq`, not in `Roll` — same reasoning
`c_mq` is in `Aero` rather than in a damping group:

```python
    # Step 109 (task-109 SS109.1.5; other-dynamics.tex eq:roll_aero): roll-moment
    # coefficients. CODE sign, like c_mq: positive C_l_p is DAMPING. Deliberately NOT
    # routed through `cm_convention` -- that flag is about the *pitching* moment
    # (C_m/C_m_alpha/c_mq); a roll convention flag would need its own table column and
    # nobody has roll data to put in one yet. Both 0.0 by default -> L_x == 0.0 exactly.
    C_l: float = 0.0              # static roll-moment coefficient (fin cant) [-]
    C_l_p: float = 0.0            # roll-damping derivative [-], positive = damping
```

**Do not** add them to the aero table schema (`sim/aero.py`'s column list). They are scalars on
`Params.aero` only. A `c_l`/`c_l_p` table column is out of scope (§109.13) and would drag in the
`cm_convention`-style header negotiation Step 119 just finished untangling.

---

## §109.4 `sim/roll.py` — the new module

**Why a new module and not `sim/control.py`.** Three reasons, in order of weight:

1. `sim/control.py` is 589 lines and owns the airbrake end-to-end (laws, triggers, the sampled-law
   registry, the actuator model). Roll is a second, independent dispatch; the project's own rule is
   "one group per module that owns a dispatch" (`params.py` docstring), and `Params.roll`'s owner
   should be `sim/roll.py`.
2. **Boundary isolation.** Step 108 is being implemented in parallel on `sim/sensors.py` and
   `controllers/estimator.py`, and the natural seam it may widen is `sim/control.py`'s measurement
   path. This step must not touch `sim/control.py` or `sim/sampling.py` at all. It does not need to.
3. The roll laws here are **memoryless** — pure functions of $(t, y, p)$, re-evaluated at every RHS
   call, exactly like `_proportional_airbrake`. A roll law *with* memory would register a
   `"reaction_wheel"` channel in `sampling._CHANNELS`; that is deliberately deferred (§109.13), and
   deferring it is what keeps `sim/sampling.py` out of this step's file list.

### 109.4.1 Module contract

```
sim/roll.py
  aero_moment_x(t, y, p, flow)          -> float     # L_x, eq. of SS109.1.5
  wheel_torque(t, y, p, hold=None)      -> float     # tau_w, clamped (SS109.1.3)
  wheel_momentum(y, p)                  -> float     # h_w = I_w*(omega_w - omega_x), derived
  wheel_saturated(y, p)                 -> bool      # |omega_w - omega_x| >= omega_w_max
  airframe_inertia(p)                   -> float     # I_x,a = I_x - I_w
  known_roll_models()                   -> tuple     # ("none", "free", "wheel")
  known_roll_laws()                     -> tuple     # ("none", "rate_null", "angle_hold")
  derivatives_roll(t, y, p, flow, hold) -> tuple[float, float, float]   # (dgamma, domega_x, domega_w)
```

`derivatives_roll` returning the three-tuple is the whole public surface `sim/dynamics.py` needs —
one call, one place to put the block, and the freeze branches (§109.6.3) override its first two
elements rather than re-deriving them.

### 109.4.2 The laws

Module-private dispatch dict, same shape as `control._AIRBRAKE_CONTROLLERS`:

```python
def _no_torque(t, y, p) -> float:
    """`law = "none"` (the default): the wheel is present but never commanded.
    Together with the `C_l = C_l_p = 0.0` aero default this makes the model's
    default behaviour exactly the torque-free momentum exchange of eq. (5)
    driven by the initial condition alone -- which is the right default,
    because it is the only roll behaviour this project has data for."""
    return 0.0


def _rate_null(t, y, p) -> float:
    """`law = "rate_null"`: null the airframe roll rate. tau_w = kd*omega_x.

    SIGN: eq. (2) is I_x_a*eps_x = L_x - tau_w, so a tau_w with the SAME sign
    as omega_x decelerates the airframe. kd > 0 damps; kd < 0 is a sign error
    the model will happily diverge on (no validation, params.py SS7)."""
    return p.roll.kd * y[OMEGA_X]


def _angle_hold(t, y, p) -> float:
    """`law = "angle_hold"`: PD hold on the roll angle.
    tau_w = kp*(gamma - gamma_cmd) + kd*omega_x.

    SIGN: same reasoning as `_rate_null` -- a positive error (gamma above the
    command) needs a positive tau_w to produce a negative eps_x. kp, kd > 0.
    Memoryless by construction: no integral term, because an integral term
    needs the sampled/ZOH mode (sim/sampling.py) and that is out of this
    step's scope (task-109 SS109.13)."""
    return p.roll.kp * (y[GAMMA] - p.roll.gamma_cmd) + p.roll.kd * y[OMEGA_X]


_ROLL_LAWS = {"none": _no_torque, "rate_null": _rate_null, "angle_hold": _angle_hold}
```

### 109.4.3 `wheel_torque` — the clamps

```python
def wheel_torque(t, y, p, hold=None) -> float:
    """tau_w, the motor torque applied TO THE WHEEL about +x_hat_r, after both
    saturation limits (task-109 SS109.1.3).

    `hold` is accepted and ignored -- every law here is memoryless. The
    parameter exists so that adding a sampled roll channel later does not
    change this function's signature at its call site in sim/dynamics.py
    (the same reason `aero_moment_y` took `hold` before any law used it).
    """
    if p.roll.model != "wheel" or p.roll.I_w == 0.0:
        return 0.0                      # no wheel -> no reaction torque, exactly 0.0

    tau = _ROLL_LAWS[p.roll.law](t, y, p)

    # Torque limit, two-sided. `tau_max = inf` (the default) leaves `tau`
    # untouched -- min/max against inf is the identity, no branch needed.
    tau = max(-p.roll.tau_max, min(p.roll.tau_max, tau))

    # Speed limit, ONE-sided (SS109.1.3): at saturation the wheel can still be
    # braked back, only accelerated further is forbidden. A two-sided clamp
    # would lock the wheel at its limit for the rest of the flight.
    # `omega_w_max = inf` (the default) makes both comparisons False.
    omega_rel = y[OMEGA_W] - y[OMEGA_X]
    if omega_rel >= p.roll.omega_w_max and tau > 0.0:
        tau = 0.0
    elif omega_rel <= -p.roll.omega_w_max and tau < 0.0:
        tau = 0.0
    return tau
```

**Known discontinuity.** Both clamps make $\tau_w$ discontinuous in the state, so an adaptive
solver will shorten steps near a clamp boundary and the RHS is no longer $C^1$ there. This is
*exactly* the same property `control._proportional_airbrake`'s `clip` already has, and the project
accepts it on the same terms: no event is registered for the clamp boundary, and
`\simtodo`/docstring says so. Do **not** try to smooth it.

### 109.4.4 `derivatives_roll`

```python
def derivatives_roll(t, y, p, flow, hold=None):
    """(dgamma/dt, domega_x/dt, domega_w/dt) -- eqs. (1)-(3) of task-109 SS109.1.2.

    Called ONLY when `p.roll.model != "none"` (sim/dynamics.py's gate); the
    state vector is 10 wide there, so `y[GAMMA]`/`y[OMEGA_X]`/`y[OMEGA_W]` are
    in range. Never call it on a 7-wide vector.
    """
    L_x = aero_moment_x(t, y, p, flow)
    tau_w = wheel_torque(t, y, p, hold)
    d_omega_x = (L_x - tau_w) / airframe_inertia(p)
    # I_w == 0.0 is "no wheel": tau_w is already exactly 0.0 above, and the
    # wheel's own rate is held constant rather than dividing 0.0/0.0.
    d_omega_w = tau_w / p.roll.I_w if p.roll.I_w > 0.0 else 0.0
    return y[OMEGA_X], d_omega_x, d_omega_w
```

`airframe_inertia(p)` returns `p.roll.I_x - p.roll.I_w`. It is never zero in a valid config because
`run_sim` validates `I_x > I_w` eagerly (§109.7.2) — do **not** add a second defensive guard here;
a silent fallback would hide a config error in the one place it is cheapest to catch.

---

## §109.5 `sim/state.py` — the width gate

Three edits to a 31-line file. Keep the existing seven fields and the existing
`X, Z, VX, VZ, THETA, OMEGA, M = range(7)` line **exactly as they are** — the whole point is that
nothing renumbers.

```python
class State(NamedTuple):
    ...                 # the seven existing fields, untouched
    m: float = 0.0
    # Step 109 (task-109-roll-reaction-wheel.md SS109.2; other-dynamics.tex
    # SSRoll and the reaction wheel): the decoupled roll degree of freedom.
    # Defaulted, like `m`, so every existing `State(...)` call site is
    # unaffected. UNLIKE `m`, these three are NOT always part of the flat
    # vector the integrator sees: `to_vector` below trims them off whenever
    # `p.roll.model == "none"` (the default), because scipy's RK45 error norm
    # is an RMS over the state vector and its *length* therefore changes the
    # accepted step sizes -- a zero-derivative 10th component would move every
    # pinned number in the suite (task-109 SS109.2.1 has the measurement).
    gamma: float = 0.0    # roll angle about x_hat_r [rad], right-hand rule
    omega_x: float = 0.0  # airframe roll rate dgamma/dt [rad/s]
    omega_w: float = 0.0  # wheel ABSOLUTE roll rate [rad/s] (not relative -- SS109.1.2)


X, Z, VX, VZ, THETA, OMEGA, M = range(7)
# Step 109: the roll block. These three indices are valid ONLY while
# `p.roll.model != "none"`; on a 7-wide vector they are out of range, which is
# deliberate -- an accidental read fails loudly instead of returning garbage.
GAMMA, OMEGA_X, OMEGA_W = 7, 8, 9

N_BASE = 7   # width with the roll model off (the default)
N_ROLL = 10  # width with the roll model on


def width(p) -> int:
    """Length of the flat state vector `p` produces. Two values only, and the
    gate is a single string comparison (task-109 SS109.2.2)."""
    return N_ROLL if p.roll.model != "none" else N_BASE


def to_vector(s: State, p) -> np.ndarray:
    """Flatten a `State` into the vector `solve_ivp`/`_run_rk4` integrate.

    With `p.roll.model == "none"` (the default) the three roll fields are
    TRIMMED OFF, so a non-zero `s.gamma`/`s.omega_x`/`s.omega_w` is silently
    ignored -- exactly the contract `s.m` already has when `p.weight.m_d is
    None` ("the integrator never looks at this field"). Bit-for-bit identical
    to the `np.array(s0, dtype=float)` it replaces in that case: `np.asarray`
    of the first seven fields, same dtype, same values.
    """
    return np.asarray(tuple(s)[:width(p)], dtype=float)
```

`state.py` gains `import numpy as np` and stays otherwise dependency-free — `to_vector` reads
`p.roll.model` by attribute, so there is no `sim.params` import and no cycle.

---

## §109.6 `sim/dynamics.py` — the decoupled ODE block

### 109.6.1 Imports

```python
from sim import aero, control, forces, mass, roll, thrust_curve
from sim.state import GAMMA, M, OMEGA, OMEGA_W, OMEGA_X, THETA, VX, VZ, X, Z, width
```

`sim/roll.py` must not import `sim.dynamics` (it does not need to) — the dependency is one-way.

### 109.6.2 Hoist the two branch predicates (prerequisite, behaviour-preserving)

The existing final-assembly block re-evaluates nothing, but the roll block needs the *same* answer
to "is the attitude frozen" that the pitch block uses, and calling `on_rail`/`parachute_deployed` a
second time invites the two to drift apart under a future edit. Hoist them once:

```python
    # Step 109: both predicates are hoisted to locals so the roll block below
    # cannot disagree with the pitch block about whether the attitude is
    # frozen. Both are pure functions of (t, y, p) (`forces.parachute_deployed`
    # says so in its own docstring), so reducing them to one evaluation each is
    # a call-count change only -- the Step 56 precedent for exactly this.
    # `chuted` keeps the original `elif`'s short-circuit: `parachute_deployed`
    # is not consulted while on the rail, same as before.
    on_the_rail = on_rail(y, p)
    chuted = (not on_the_rail) and forces.parachute_deployed(t, y, p)
    attitude_frozen = on_the_rail or chuted

    if on_the_rail:
        ...                  # body unchanged
    elif chuted:
        ...                  # body unchanged
    else:
        ...                  # body unchanged
```

Nothing else in those three branch bodies changes.

### 109.6.3 The roll block

Append after `dydt[M] = dm_dt`, before `return dydt`:

```python
    dydt[M] = dm_dt

    # Step 109 (task-109-roll-reaction-wheel.md SS109.6; other-dynamics.tex
    # SSRoll and the reaction wheel): the decoupled roll degree of freedom.
    #
    # This block is ADDITIVE in the strongest sense available: it writes only
    # indices 7-9 and reads only `y[GAMMA]`/`y[OMEGA_X]`/`y[OMEGA_W]` plus the
    # already-computed `flow`. Not one line above it changes, because for an
    # axisymmetric body the aerodynamic coefficients do not depend on the roll
    # angle and the wheel's reaction torque has no component along y_hat_r --
    # the rigid-body roll/pitch gyroscopic term (I_x - I_t)*r*p is identically
    # zero at the planar model's r == 0, and the wheel's own gyroscopic torque
    # q*h_w points along z_hat_r (yaw), not y_hat_r (task-109 SS109.1.4 proves
    # both). The decoupling is exact within the planar assumption, not an
    # approximation; what it cannot represent is the yaw those terms produce.
    #
    # `width(p)` is 7 whenever `p.roll.model == "none"` (the default), so this
    # branch is unreachable AND `dydt` is 7 long -- bit-for-bit every prior
    # step, including the RK45 step sizes (task-109 SS109.2.1: the state
    # vector's LENGTH is in scipy's RMS error norm, so a 10-wide dydt with
    # three zeros in it would NOT have been bit-for-bit).
    if p.roll.model != "none":
        d_gamma, d_omega_x, d_omega_w = roll.derivatives_roll(t, y, p, flow, hold)
        if attitude_frozen:
            # The same mechanical-constraint mechanism the pitch block uses:
            # two rail buttons running in a rail prevent roll as well as
            # pitch, and the canopy branch inherits sec:recovery's attitude
            # freeze (a modelling choice, flagged in the paper -- a real
            # rocket under a canopy does spin). The WHEEL's own ODE keeps
            # running in both cases: it is internal, and its reaction torque
            # is taken by the rail buttons / the risers instead of by the
            # airframe's roll freedom. A wheel spun up on the rail therefore
            # arrives at rail exit with real stored momentum, which is both
            # physically right and the only way a roll-control law can have
            # authority at the moment it first needs it.
            d_gamma = 0.0
            d_omega_x = 0.0
        dydt[GAMMA] = d_gamma
        dydt[OMEGA_X] = d_omega_x
        dydt[OMEGA_W] = d_omega_w

    return dydt
```

And `dydt = np.zeros(7)` becomes `dydt = np.zeros(width(p))`.

### 109.6.4 Docstring

Extend `derivatives`'s docstring: the state vector is now
`[x, z, vx, vz, theta, omega, m]` **or** `[…, gamma, omega_x, omega_w]`, and add a `Step 109` block
to the module docstring in the same voice as the `Step 36`/`Step 47`/`Step 48` blocks, stating (a)
the `p.roll.model == "none"` structural off switch, (b) that the width, not just the derivative,
is what makes it bit-for-bit, with a pointer to §109.2.1.

---

## §109.7 `sim/integrate.py` — y0 width and eager validation

### 109.7.1 The three `y0` sites

```python
from sim.state import State, VZ, Z, to_vector      # + to_vector
```

| Line (approx) | Function | Before | After |
|---|---|---|---|
| 305 | `_run_rk4` | `y0 = np.array(s0, dtype=float)` | `y0 = to_vector(s0, p)` |
| 531 | `_run_segmented_rk45` | `y0 = np.array(s0, dtype=float)` | `y0 = to_vector(s0, p)` |
| 723 | `run_sim` (RK45 path) | `y0 = np.array(s0, dtype=float)` | `y0 = to_vector(s0, p)` |

All three have `p` in scope already. With the roll model off, `to_vector` returns exactly what
`np.array(s0, dtype=float)` returned — same dtype, same seven values, same shape. Verified
width-agnostic downstream and needing **no** further edits: `_run_rk4`'s `np.array(ys).T`,
`_run_segmented_rk45`'s `y0.reshape(-1, 1)` and `_SegmentedSol`'s `self._y.shape[0]` loops, and
every `result.y[...]` consumer in `sim/plotting.py`, `sim/report.py`, `sim/mach_warning.py` and
`apps/` — all of which index by the named constants, never by row count, and none of which unpacks
`result.y` into fixed-arity tuples (checked exhaustively).

Also fix the stale comment on `Result.y` (line ~103): it says `shape (6, N)`, which has been wrong
since Step 36. Make it `shape (width, N)` with `width` 7 or 10 per `sim/state.py`.

### 109.7.2 Eager validation

Into `run_sim`'s existing validation block (after the `airbrake_model`/`sample_rate_hz` checks),
following the Step 103/107 precedent — "a typo in a model-selection string that only dispatches
deep inside the integration loop must fail before any integration is attempted":

```python
    if p.roll.model not in roll.known_roll_models():
        raise ValueError(
            f"p.roll.model={p.roll.model!r} is not a registered roll model "
            f"(known: {sorted(roll.known_roll_models())}) "
            "(task-109-roll-reaction-wheel.md SS109.3.1)."
        )

    if p.roll.model != "none":
        if p.roll.law not in roll.known_roll_laws():
            raise ValueError(
                f"p.roll.law={p.roll.law!r} is not a registered roll law "
                f"(known: {sorted(roll.known_roll_laws())}) "
                "(task-109 SS109.4.2)."
            )
        if p.roll.I_x <= p.roll.I_w:
            raise ValueError(
                f"p.roll.I_x={p.roll.I_x} must exceed p.roll.I_w={p.roll.I_w}: "
                "I_x is the vehicle's axial inertia with the wheel INCLUDED and "
                "locked, so the airframe-alone inertia I_x - I_w (the denominator "
                "of eq. (2)) must be positive (task-109 SS109.1.1). I_x = 0.0 is "
                "the unset default and is never valid with the roll model on."
            )
```

This is the one place a config error is cheap to catch; `sim/roll.py` deliberately has no
defensive fallback for it (§109.4.4).

Note the ordering constraint: the `roll.model` check must come **before** the `I_x`/`law` checks,
so an unregistered model name reports itself rather than producing a confusing inertia complaint.

---

## §109.7b `configs/` — the config layer is NOT optional here

`tests/test_config_pieces.py::test_assemble_params_call_keyword_set_equals_params_fields_exactly`
parses `configs/schema.py::assemble`'s own source and asserts its `Params(...)` keyword set equals
`{f.name for f in dataclasses.fields(Params)}` **exactly**. Adding a group to `Params` without
wiring it through `schema.py` fails that test immediately. Three edits:

1. **`configs/schema.py`** — import `Roll` from `sim.params`, and give it to the `Rocket` piece
   (the roll DOF and its wheel are vehicle control hardware, the same owning piece as `control`
   and `actuator` — SS31.3.2's one-owner invariant):

   ```python
       actuator: Actuator = dataclasses.field(default_factory=Actuator)
       roll: Roll = dataclasses.field(default_factory=Roll)   # Step 109
   ```

2. **`configs/schema.py::assemble`** — one more keyword in the `Params(...)` call:
   `roll=sc.rocket.roll,`.

3. **`configs/rockets/_TEMPLATE_rocket.py`** — a `roll=Roll(...)` block with every field marked
   `REQ|OPT` plus unit and short description, per the project's template convention (`CLAUDE.md`,
   "Шаблоны конфигов"). All `OPT` except `I_x`, which is `REQ iff model != "none"`.

`_GROUP_DEFAULTS` in `tests/test_config_pieces.py` is **deliberately left alone**: it does not
contain `actuator` either (Step 103 set that precedent), and adding `roll` would force a
non-default roll into `_non_default_scenario()` for no new coverage. Note it and move on.

No demo config turns the roll model on. `configs/` keeps only demo and template configs
(`CLAUDE.md`), and there are no real $I_x$/$I_w$ numbers for this airframe (§109.1.5, and the
paper's own `\restodo`). A roll-enabled scenario is for the user to write when hardware is chosen.

---

## §109.8 LaTeX — what this step already wrote

**Done by the architect in this step** (the user's explicit request; the project's standing
"LaTeX is read-only" rule has an explicit exception for an explicit user request, and this is one).
No further LaTeX work is in the developer's scope — do not edit `dev/docs/latex/`.

| File | Change |
|---|---|
| `sections-ai/other-dynamics.tex` | **New `\subsection{Roll and the reaction wheel}\label{sec:roll}`** at the end of the file, wrapped in `aitext` (AI-written, awaiting the author's review, per `main.tex`'s own convention). Four subsubsections: `sec:roll_decoupling` (the exactness proof + what it hides), `sec:roll_eom` (eqs. `eq:roll_kinematics`, `eq:roll_airframe`, `eq:roll_wheel`, `eq:roll_momentum`, `eq:roll_exchange`), `sec:roll_saturation` (`eq:roll_limits`), `sec:roll_aero` (`eq:roll_aero_moment`), `sec:roll_law`. Plus the section's opening sentence, which claimed every model here "modifies" the EOM — roll *extends* them. |
| `sections-ai/assumptions.tex` | "Planar flight" now states $\omega_z\equiv0$ as what makes roll decouple exactly. New **Roll** assumption item: the dropped yaw torques, roll-angle-independent coefficients, balanced wheel. |
| `sections-ai/appendix.tex` | New **Roll** bullet in `sec:conventions`: $\gamma_r$ sign, $\tau_w$ acting on the *wheel* (airframe gets $-\tau_w$), $\omega_w$ absolute not relative, and that `cm_convention` does **not** touch $C_l$/$C_{l,p}$. |
| `sections-ai/backlog.tex` | The "Roll dynamics with a reaction wheel (2D)" item is no longer a derivation backlog item — reduced to the *data* still missing ($I_x$, wheel specs, $C_l$/$C_{l,p}$, motor roll torque) and the sampled-mode roll channel, pointing at `sec:roll`. |
| `sections-ai/models.tex` | `sec:noise`: the motor roll torque is no longer "out of the pitch plane and so without effect in 2D" — it is a term of $L_x$ when the roll freedom is enabled. |

Equation/label names the implementer should cite in docstrings: `eq:roll_airframe` (the airframe
ODE), `eq:roll_wheel` (the wheel ODE), `eq:roll_exchange` (the $\omega_x=-h_w/I_x$ check),
`eq:roll_limits` (saturation), `eq:roll_aero_moment` (the aero roll moment).

**Not compiled.** There is no LaTeX toolchain in this environment (`CLAUDE.md`), so the new
section is unrendered. Cross-references were checked by hand against the existing labels:
`sec:rocket2d`, `eq:eom_trans`, `eq:eom_rot`, `sec:frames`, `sec:mass`, `sec:assumptions`,
`sec:conventions`, `sec:aero`, `sec:noise`, `sec:sampled`, `sec:rail`, `eq:rail_attitude`,
`sec:recovery`, `sec:airbrake_law`, `eq:airbrake_p`, `eq:pitch_damping_moment` — all exist.

---

## §109.9 Test-impact table

### New file: `tests/test_roll.py`

| # | Test | What it pins |
|---|---|---|
| 1 | `test_width_gate` | `state.width(p)` is 7 for `"none"`, 10 for `"free"` and `"wheel"` |
| 2 | `test_to_vector_trims_roll_when_off` | `to_vector(State(gamma=1.0, omega_x=2.0, omega_w=3.0, …), p_off)` has shape `(7,)` and equals the seven base values; with roll on, shape `(10,)` and carries all three |
| 3 | `test_derivatives_width_follows_params` | `derivatives(...)` returns shape `(7,)` off, `(10,)` on |
| 4 | **`test_momentum_exchange_from_rest`** | eq. `eq:roll_exchange`. `model="wheel"`, `C_l=C_l_p=0`, `law="angle_hold"`, `gamma_cmd != 0`, start at rest. Assert $I_x\omega_x + h_w = 0$ at **every** output point (`atol` ~1e-10 relative to $I_x\omega_{x,max}$), and that $\omega_x$ and $h_w$ have opposite signs |
| 5 | `test_no_law_no_roll` | `law="none"` + zero aero + zero initial roll ⇒ `gamma`, `omega_x`, `omega_w` stay exactly 0.0 for the whole flight |
| 6 | **`test_roll_does_not_perturb_the_other_seven`** | **`method="rk4"`, fixed `dt`.** Run the same scenario roll-off and roll-on (`"wheel"`, nonzero gains, nonzero initial roll rate); assert `np.array_equal(y_off, y_on[:7])`. See the note below — this test is wrong with RK45 |
| 7 | `test_wheel_speed_saturation` | small `omega_w_max`, aggressive `kp`: $|\omega_{w/r}| \le \omega_{w,max}$ throughout, the limit **is reached**, and once reached $|\omega_x|$ stops growing |
| 8 | `test_wheel_speed_clamp_is_one_sided` | at $\omega_{w/r} = +\omega_{w,max}$, `wheel_torque` returns 0.0 for a positive command but passes a negative one through |
| 9 | `test_torque_clamp` | tiny `tau_max`: `|wheel_torque(...)| <= tau_max` over a spread of hand-built states |
| 10 | `test_rate_null_despins` | `law="rate_null"`, nonzero initial `omega_x`: $|\omega_x|$ monotonically decreases, and $h_x$ is conserved |
| 11 | `test_free_model_has_no_wheel` | `model="free"`: `wheel_torque` is exactly 0.0, `omega_w` constant, and with `C_l_p > 0` an initial roll rate decays |
| 12 | `test_roll_damping_finite_at_zero_airspeed` | `aero_moment_x` at $v_{rel}=0$ with `C_l_p != 0` is finite (not `nan`) — the division-free form of §109.1.5 |
| 13 | `test_rail_freezes_roll_but_not_the_wheel` | `L_rail > 0`, commanding law: on the rail `dydt[GAMMA] == dydt[OMEGA_X] == 0.0` while `dydt[OMEGA_W] != 0.0`; off the rail both are nonzero |
| 14 | `test_run_sim_rejects_bad_roll_config` | three `pytest.raises(ValueError)`: unknown `model`, unknown `law`, `I_x <= I_w` |
| 15 | `test_wheel_momentum_and_saturated_helpers` | `wheel_momentum`/`wheel_saturated` agree with the state they are derived from |

> **Test 6 is the subtle one.** "Decoupled" means the first seven components solve the *same* ODE —
> it does **not** mean an adaptive integrator takes the same steps. Under RK45 the 10-wide run has a
> different error-norm denominator (§109.2.1) and so a different step sequence, and the two runs
> agree only to tolerance. Under `method="rk4"` the step sequence is fixed by `dt` alone, every RK4
> stage computes rows 0–6 from rows 0–6 only, and the two runs are **bit-identical**. Write it with
> `rk4` and say why in the test's docstring, or it will be a flaky test somebody later "fixes" by
> loosening the tolerance.

### Existing tests to audit (no pin should move)

| File | Site | Action |
|---|---|---|
| `tests/test_forces.py` | `:138` `dydt = np.zeros(7)` | **No change.** The test's params leave roll off, so `derivatives` still returns 7. Update only the stale comment above it if touched. |
| `tests/test_forces.py` | `:952` `np.array(State(...))` | Audit: `State` is now 10 fields, so this yields a 10-wide array. Harmless if it is only passed to functions that index by name (`flow_state`, `forces.*`); if its length is compared or it is fed to `solve_ivp`, switch to `state.to_vector(s, p)`. |
| `tests/test_qa_phase217_m1.py` | `:54` `np.array(State(...))` | Same audit. |
| `tests/test_control.py` | `:96` `np.array(State(...))` | Same audit. |
| `apps/motor_selection/compare_motors.py` | imports `State` | Audit for the same pattern. |
| `tests/test_config_pieces.py` | `:168` keyword-set pin | Passes once §109.7b is done; fails loudly if it is forgotten. That is the point of it. |
| `tests/test_integrate.py` | RK45 `np.array_equal` pins | **Must not move.** The whole §109.2 design exists to keep them. If any of them moves, stop and escalate — do not re-pin. |

**Full-suite run is the gate** (`python -m pytest -q`, `run_in_background` — ~220 s). Zero changed
numbers anywhere outside `tests/test_roll.py` is the pass condition.

---

## §109.10 Acceptance checks

### 109.10.1 Momentum exchange (the physics check)

`model="wheel"`, `C_l = C_l_p = 0.0`, `law="angle_hold"` with `gamma_cmd = 0.5`, vehicle at rest,
$I_x = 0.02$, $I_w = 2\times10^{-4}$, $k_p = 0.01$, $k_d = 0.002$, no limits. Then at every output
point

$$\left| I_x\,\omega_x + I_w(\omega_w - \omega_x) \right| \le \varepsilon$$

with $\varepsilon$ a few $\times 10^{-12}$ — this is a conserved quantity of the exact ODE, so the
only error is the integrator's. If it drifts linearly in time, the sign of $\tau_w$ in (2) or (3) is
wrong; if it jumps, the clamps are firing when they should not.

### 109.10.2 Saturation is reachable and behaves

Same setup with $\omega_{w,max} = 50$ rad/s. The wheel must hit the limit, $|\omega_x|$ must stop
growing there, and $|\omega_x|$ must plateau near $I_w\omega_{w,max}/I_x$ from
`eq:roll_exchange`. A run where saturation is never reached does not test the feature.

### 109.10.3 Bit-identity of everything else (the regression check)

1. The full suite, unchanged, with **no** number moving outside `tests/test_roll.py`.
2. `state.width(p) == 7` for every config in `configs/` (none enables roll).
3. `python run.py` output (`output/*.csv`) byte-identical to a pre-change run — the strongest
   available end-to-end statement, and cheap. Capture it **before** starting.

### 109.10.4 Decoupling, demonstrated not asserted

Test 6 of §109.9 under `rk4`. `np.array_equal(y_off, y_on[:7])` must hold **exactly**. Anything
less means something in the force/moment chain read a roll component.

---

## §109.11 Definition of done

- [ ] `sim/roll.py` created: the eight public functions of §109.4.1, the three laws, both clamps,
      module docstring in the project's voice citing `other-dynamics.tex` `sec:roll` and this file.
- [ ] `sim/params.py`: `Roll` group added and registered on `Params`; `Aero.C_l`/`Aero.C_l_p`
      added; `Params` docstring's group count updated.
- [ ] `sim/state.py`: three defaulted fields, `GAMMA/OMEGA_X/OMEGA_W`, `N_BASE`/`N_ROLL`,
      `width(p)`, `to_vector(s, p)`; the existing `range(7)` line untouched.
- [ ] `sim/dynamics.py`: predicates hoisted (§109.6.2), `np.zeros(width(p))`, the roll block,
      module + function docstrings extended with a `Step 109` note.
- [ ] `sim/integrate.py`: three `to_vector` sites, the eager validation block, the stale
      `Result.y` shape comment fixed.
- [ ] `configs/schema.py` + `configs/rockets/_TEMPLATE_rocket.py` per §109.7b.
- [ ] `tests/test_roll.py`: all 15 tests, written **test-first** (`tdd` skill is mandatory for this
      role), test 6 using `rk4` with the docstring explaining why.
- [ ] Existing-test audit of §109.9 complete; **no pinned number moved anywhere.**
- [ ] Full suite green (`python -m pytest -q`, background).
- [ ] `code-review` skill run before QA.
- [ ] One commit: `Step 109 (Phase 2.17): 2D roll dynamics with a reaction wheel`.

---

## §109.12 Decision log

| ID | Decision | Rationale |
|---|---|---|
| **D-131** | State-vector width is **conditional** (7 / 10) on `p.roll.model`, not unconditionally widened | scipy's RK45 error norm is an RMS over the state vector, so its *length* sits in the step-size controller's denominator: a zero-derivative 10th component still moves every RK45-pinned number (measured, §109.2.1). `CLAUDE.md` makes re-pinning a user decision. **Open for user approval — alternative C (post-pass integration) is live, §109.2.4.** |
| **D-132** | The wheel's **absolute** rate $\omega_w$ is the state, not the relative $\omega_{w/r}$ | Makes `eq:roll_wheel` a standalone scalar ODE with no $\varepsilon_x$ on its RHS; the relative rate and $h_w$ are cheap derived quantities. |
| **D-133** | `C_l`/`C_l_p` live on `Aero`, are **code sign**, and are **not** routed through `cm_convention` | They are aerodynamics, like `c_mq`. `cm_convention` governs the *pitching* moment; a roll convention flag would need its own table column and there is no roll data to put in one. Written into the paper's conventions section so it cannot be mistaken later. |
| **D-134** | A new module `sim/roll.py`, not an extension of `sim/control.py` | Second independent dispatch ⇒ its own module per the project's own rule; and it keeps this step's file boundaries disjoint from Step 108 (`sim/sensors.py`, `controllers/estimator.py`), which is running in parallel. |
| **D-135** | Roll is frozen on the rail **and** under canopy; the wheel's ODE runs in both | Rail: two buttons in a rail mechanically prevent roll, same as pitch. Canopy: inherited from `sec:recovery`'s attitude freeze, and flagged in the paper as a choice rather than physics. The wheel is internal, so its reaction is taken by the rail/risers — which lets a wheel spin up before rail exit, when a roll law first needs authority. **Both are one-line changes if the user disagrees (§109.2.4 Q3/Q4).** |

---

## §109.13 Deliberately out of scope

| Not done | Why |
|---|---|
| **3D / 6DOF, quaternions, `state3d.py`** | A separate and much larger ask, with a standing user-level blocker (Step 30, the $I_a$ moment-of-inertia fork, `dev/docs/latex/research/3d_equations_of_motion.md`). This step is the *decoupled 2D* add-on the user asked for, and §109.1.4 states precisely what it cannot represent so it is never mistaken for the 3D work. |
| **A sampled/ZOH roll channel** | Needs `sampling._CHANNELS` and therefore `sim/sampling.py` — a file this step keeps out of, both for Step 108 boundary isolation and because no roll law with memory is specified. The paper carries the `\simtodo`. |
| **Roll torque rate limiting / an actuator model for the wheel** | The `Actuator` group's analogue for the wheel motor. Needs the ZOH channel above; and no motor is chosen, so no rate limit is known. |
| **`c_l`/`c_l_p` aero-table columns** | Scalars on `Params.aero` only. A table column drags in the per-table convention-header negotiation Step 119 just finished, for data that does not exist. |
| **A roll-dependent $C_z(\alpha, M, \gamma_r)$ axis** | The honest fin-interference effect of §109.1.4 item 2. No data source identified; `\restodo` in the paper. |
| **Motor roll torque as a driven term** | The paper now points `sec:noise`'s motor roll torque at $L_x$, but no prediction method exists (Knauber: measured peaks, no model). A user who has a number can put it in `C_l`. |
| **An `apps/` roll/wheel sizing utility** | The natural follow-on ("how much $I_w\omega_{w,max}$ buys how much authority"), and §109.2.4 Q1 asks the user whether that is the actual goal. Not this step. |
| **A roll-enabled demo config** | No real $I_x$/$I_w$ numbers for this airframe. `configs/` holds demo and template configs only. |
</content>
</invoke>
