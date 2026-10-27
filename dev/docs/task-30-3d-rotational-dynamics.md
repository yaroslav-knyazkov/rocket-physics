# Task 30 — 3D rotational dynamics with a full symmetric inertia tensor

Phase 3, Step 30. Branch: `feature/sim-paper-alignment`. Author: architect, 2026-10-25.
Design only — no `sim/` code was written for this ticket.

## Кратко (RU)

- Закрывает дыру в `sim/dynamics3d.py`, где `dydt[Q]` и `dydt[OMEGA]` жёстко прибиты к нулю
  («Step 30's job»). Включает настоящую вращательную динамику 3D.
- **Решение пользователя:** полный симметричный тензор инерции из 6 чисел
  (`I_xx, I_yy, I_zz, I_xy, I_xz, I_yz`), а не осесимметричная пара `I`/`I_a`. Уравнения берутся
  в **общей** форме Эйлера `I·ω̇ + ω×(I·ω) = M` — без допущения `I_yy = I_zz`.
- **Где живёт тензор:** новая группа `Params.inertia` (`sim/params.py`), владелец — `Rocket`
  (как `roll`/`actuator`/`sensors` из шагов 103/108/109). `Weight` **не трогаем вообще** — там
  `I(t)` переменной массы, он должен остаться бит-в-бит для 2D (§30.2).
- **Знаки произведений инерции выведены с нуля** (§30.1.2), не процитированы: `I_xy ≡ ∫xy dm`,
  а в матрице стоит `−I_xy`. Общая форма при `I_yy = I_zz` **в точности** воспроизводит §4
  старой заметки `3d_equations_of_motion.md` и §109.1.4 тикета про крен — перекрёстная проверка
  знаков прошла.
- **Новый жёсткий контроль конфига** (§30.8): тензор обязан быть физически допустимым —
  положительно определённым и удовлетворять неравенствам треугольника. Следствие, которое
  пользователь должен знать: для тонкой ракеты `|I_yy − I_zz| ≤ I_xx`, т.е. поперечные моменты
  могут различаться не более чем на ~0.4 % (§30.1.5).
- **Честная переоценка:** не «~30 строк в одном файле», а ~250 строк кода + ~400 строк тестов в
  9 файлах (§30.12). Само уравнение — одна строка; дорого стоят валидатор, слой конфига и
  потерянная инвариантность плоского движения.
- **Очерёдность:** Step 109 должен быть влит и закоммичен **до** начала работы по этому тикету —
  оба правят `sim/params.py` и `configs/schema.py`, и §30.8 читает `Roll.I_x` (§30.0.3).
- **LaTeX: развилка закрыта** — пользователь выбрал L-a (2026-10-25), секция уже написана
  архитектором: новый файл `dev/docs/latex/sections-ai/rocket-3d.tex` + `\input` и три `\bibitem`
  в `main.tex` + по одному пункту в `appendix.tex`/`assumptions.tex` + сверка пункта про 3D в
  `backlog.tex`. Уже утверждённые секции (`rocket-2d.tex` и др.) не тронуты.
  **У разработчика LaTeX в скоупе нет** — только цитировать метки уравнений (§30.14.3).
- Открытых решений для пользователя больше нет.

## Table of contents

- [§30.0 Scope, dependencies, sequencing](#300-scope-dependencies-sequencing)
- [§30.1 Physics — general Euler's equations with a full inertia tensor](#301-physics--general-eulers-equations-with-a-full-inertia-tensor)
- [§30.2 Where the tensor lives — the `Inertia` group, and why not `Weight`](#302-where-the-tensor-lives--the-inertia-group-and-why-not-weight)
- [§30.3 `sim/inertia.py` — the new module](#303-siminertiapy--the-new-module)
- [§30.4 `sim/forces3d.py` — the moment vector](#304-simforces3dpy--the-moment-vector)
- [§30.5 `sim/dynamics3d.py` — the rotational block](#305-simdynamics3dpy--the-rotational-block)
- [§30.6 Quaternion norm drift](#306-quaternion-norm-drift)
- [§30.7 `configs/` — schema and template wiring](#307-configs--schema-and-template-wiring)
- [§30.8 Validation — where it runs, what it rejects](#308-validation--where-it-runs-what-it-rejects)
- [§30.9 Test-impact table](#309-test-impact-table)
- [§30.10 Acceptance checks](#3010-acceptance-checks)
- [§30.11 Pin safety](#3011-pin-safety)
- [§30.12 Cost re-estimate against the proposal's "~30 lines"](#3012-cost-re-estimate-against-the-proposals-30-lines)
- [§30.13 Decision log](#3013-decision-log)
- [§30.14 LaTeX — RESOLVED, and already written](#3014-latex--resolved-and-already-written)
- [§30.15 Deliberately out of scope](#3015-deliberately-out-of-scope)
- [§30.16 Definition of done](#3016-definition-of-done)
- [§30.17 Ticket block](#3017-ticket-block)

---

## §30.0 Scope, dependencies, sequencing

### 30.0.1 The gap being closed

`sim/dynamics3d.py:52-53`, verbatim today:

```python
    dydt[Q] = 0.0
    dydt[OMEGA] = 0.0
```

with `dq/dt = 0   (constant -- Step 29 holds attitude fixed)` and
`domega/dt = 0   (constant -- no moments computed yet; Step 30's job)` in the module docstring.
Everything else Step 30 needs on the kinematic side already exists and is tested:
`sim/quaternion.py:183 q_dot(q, omega_body)` (Step 28, `tests/test_quaternion.py`), and the
13-component layout `[r(3), v(3), q(4), omega(3)]` with its slice constants (`sim/state3d.py`,
Step 29).

What is missing is exactly three things: an inertia representation, a moment vector, and the
rotational ODE that joins them.

### 30.0.2 The 3D path is an island — which is what makes this step safe

`rg` over the whole repository for `state3d|dynamics3d|forces3d|quaternion` finds **six** code
files: `sim/quaternion.py`, `sim/state3d.py`, `sim/dynamics3d.py`, `sim/forces3d.py`,
`tests/test_quaternion.py`, `tests/test_dynamics3d.py`. Nothing in `sim/integrate.py`,
`sim/dynamics.py`, `sim/report.py`, `sim/plotting.py`, `run.py` or `apps/` touches the 3D layout.
`derivatives_3d` is reachable only from its own test file.

Consequence, stated up front because it governs the whole risk profile of this ticket: **no pinned
number in the suite can move, structurally, not merely by intent.** See §30.11.

### 30.0.3 Dependency on Step 109 — sequential, not parallel

A sibling developer is implementing Step 109 (2D roll + reaction wheel,
`dev/docs/task-109-roll-reaction-wheel.md`) on `sim/roll.py`, `sim/dynamics.py`, `sim/params.py`,
`sim/state.py`, `sim/integrate.py`, `configs/schema.py`. Two of those — `sim/params.py` and
`configs/schema.py` — are files this ticket also edits, **in the same regions** (the group list in
`params.py`, the `Params(...)` field list, `Rocket`'s field list, `assemble`'s keyword list,
`_TEMPLATE_rocket.py`'s group blocks).

There is also a **hard content dependency**, not only a merge-conflict one: §30.8's config
cross-check reads `Roll.I_x`, and `Roll` does not exist without Step 109.

> **Sequencing rule: Step 109 must be landed and committed on `feature/sim-paper-alignment`
> before a developer starts this ticket.** `depends_on: [STEP-109]`, `parallel_safe: false`.
> Do not run the two in parallel worktrees.

Note for the implementer: at the time this ticket was written the `Roll` group and its `schema.py`
wiring were **already present in the working tree** (`sim/params.py:281-309`,
`configs/schema.py:76/301/385`) as Step 109's work in progress. This ticket is written against
Step 109 *as landed*. If any of those line references have shifted, locate by symbol name, not by
line number.

### 30.0.4 What Step 30 does NOT deliver

Step 30 gives the 3D core real rotational dynamics. It does **not** make a 3D scenario flyable
end-to-end — `sim/integrate.py`'s 759 lines of event/hold machinery (ground, apogee, burnout, rail
exit, parachute deploy) are written entirely against the 7-component 2D vector. That gap is
**Step 30b, "3D integration harness"**, identified in
`dev/docs/latex/research/3d-readiness-proposal.md` §3.2 as missing from the roadmap and strictly
larger than Steps 30, 31 and 32 combined. Restated here so nobody reads a green Step 30 as "3D
works now".

---

## §30.1 Physics — general Euler's equations with a full inertia tensor

Everything in this section is derived, not quoted, so a reader can check the signs without leaving
the document. Where the result coincides with an existing project artefact, that is noted as a
cross-check.

### 30.1.1 Notation and frame

Frame convention is unchanged (`sim/state3d.py`, `sim/params.py`, `architecture.md` §2): a single
NED-like inertial frame `F_0` with `z` DOWN, and a right-handed body frame
`F_r = (x_hat_r, y_hat_r, z_hat_r)` fixed to the vehicle, `x_hat_r` along the axis toward the nose.
`q` is the attitude quaternion body→inertial, scalar-first (`sim/quaternion.py`'s convention).
`omega = (omega_x, omega_y, omega_z)` is the **body-frame** angular velocity; `omega_y` is the 2D
pitch rate, `omega_x` the roll rate, `omega_z` the yaw rate.

Moments are taken about the instantaneous centre of gravity, the same reference point the 2D model
uses (`sim/dynamics.py`'s `aA`/`aB` arms are both measured from it).

> **Point naming — the paper and the code disagree, and this ticket uses the paper's.**
> `rocket-2d.tex` §Geometry names the four points `A` (nose tip), `g` (centre of gravity),
> `t` (thrust application point), `p` (aerodynamic moment reference), with arms `\vec{gt}`,
> `\vec{gp}` (`eq:arms`). `sim/` comments and `CLAUDE.md` still carry the older `A`/`B`/`C`/`D`
> naming (CoG = `B`), and renaming the code is a separately deferred decision — do **not** rename
> anything in this step. Where this ticket says "the CoG" it means the paper's `g` and the code's
> `B`; they are the same point.
>
> **Naming warning.** Classical rigid-body texts abbreviate the six inertia components as
> `A, B, C, D, E, F`. **Do not use that shorthand anywhere in this project** — `A` is the nose tip
> in both namings, and `B`, `C`, `D` are points in the code's. Always spell `I_xx … I_yz`.

### 30.1.2 The inertia matrix and the product-of-inertia sign convention

This is the one place a silent sign error would be both catastrophic and nearly invisible (the
off-diagonals are ~0 for any normally built rocket, so a wrong sign produces a small wrong answer,
not an obvious one). So it is derived rather than cited.

Angular momentum about B of a rigid body:

```
H = ∫ r × (omega × r) dm
```

Using the vector identity `r × (omega × r) = omega (r·r) − r (r·omega)`:

```
H_x = ∫ [ omega_x (x²+y²+z²) − x (x·omega_x + y·omega_y + z·omega_z) ] dm
    = omega_x ∫(y²+z²) dm  −  omega_y ∫xy dm  −  omega_z ∫xz dm
```

Adopt the **standard textbook definitions** (Hibbeler, *Engineering Mechanics: Dynamics*,
§21.1-21.2; Stevens & Lewis, *Aircraft Control and Simulation*, ch. 1; the same convention Etkin
and every CAD mass-properties report use):

```
moments of inertia    I_xx = ∫(y²+z²) dm     I_yy = ∫(x²+z²) dm     I_zz = ∫(x²+y²) dm
products of inertia   I_xy = ∫xy dm          I_xz = ∫xz dm          I_yz = ∫yz dm
```

Then, by the line above and its two cyclic partners:

```
H_x =  I_xx·omega_x − I_xy·omega_y − I_xz·omega_z
H_y = −I_xy·omega_x + I_yy·omega_y − I_yz·omega_z
H_z = −I_xz·omega_x − I_yz·omega_y + I_zz·omega_z
```

so the **inertia matrix that the code must assemble** is

```
          [  I_xx   -I_xy   -I_xz ]
I_body =  [ -I_xy    I_yy   -I_yz ]        (symmetric, by construction)
          [ -I_xz   -I_yz    I_zz ]
```

**The minus signs are not optional and not a style choice.** They are the consequence of defining
`I_xy` as the *integral* `∫xy dm` rather than as the matrix entry. The literature carries both
conventions — physics texts (Goldstein) define `I_ij = ∫(r²δ_ij − x_i x_j) dm`, which has the minus
already folded in, so their matrix has **no** extra sign. This project takes the aerospace/CAD
convention above, because that is what a user transcribing a number off a mass-properties report or
a textbook will have in hand.

**Implementation rule:** the minus signs appear in **exactly one place** in the codebase —
`sim/inertia.py::tensor` (§30.3) — and are pinned by a point-mass test that compares
`tensor(p) @ omega` against `Σ m·(r × (omega × r))` computed directly (§30.9 test 2). That test
cannot pass if any sign anywhere is wrong.

### 30.1.3 Euler's rotational equations of motion — general form

Newton's second law for rotation, in the inertial frame: `dH/dt|_inertial = M`. `H` is expressed in
body components, and the body frame rotates at `omega`, so by the transport theorem

```
dH/dt|_inertial = dH/dt|_body + omega × H
```

`I_body` is constant in the body frame for a rigid body of fixed mass distribution, so
`dH/dt|_body = I_body · omega_dot`, giving **Euler's rotational equation in its general form**:

```
I_body · omega_dot + omega × (I_body · omega) = M                              (eq. 30.1)
```

and the explicit ODE the code integrates:

```
omega_dot = I_body⁻¹ ( M − omega × (I_body · omega) )                          (eq. 30.2)
```

Expanded, with `H` from §30.1.2:

```
(omega × H)_x = omega_y·H_z − omega_z·H_y
(omega × H)_y = omega_z·H_x − omega_x·H_z
(omega × H)_z = omega_x·H_y − omega_y·H_x
```

and then eq. 30.1 is the 3×3 linear system `I_body · omega_dot = M − (omega × H)`.

**Two preconditions of eq. 30.1, both satisfied here, both worth stating because violating either
silently invalidates the equation:**

1. **`I_body` is constant in time.** True on the 3D path: `derivatives_3d` runs at a fixed mass
   (`p.weight.m`; the 13-component layout has no mass component, and `forces3d._s2d` passes mass
   `0.0` through). There is no 3D variable-mass model, so there is no `I_body(t)`. When a 3D mass
   model arrives, eq. 30.1 gains an `I_dot · omega` term and this ticket's module must be revisited
   — recorded as a backlog item in §30.15.
2. **Moments are taken about the CoG** (or a body-fixed point). True: §30.1.1.

### 30.1.4 Cross-check — reduction to the diagonal and axisymmetric cases

Set the three products of inertia to zero. Then `H = (I_xx·omega_x, I_yy·omega_y, I_zz·omega_z)` and

```
(omega × H)_x = (I_zz − I_yy)·omega_y·omega_z
(omega × H)_y = (I_xx − I_zz)·omega_z·omega_x
(omega × H)_z = (I_yy − I_xx)·omega_x·omega_y
```

giving the classical Euler equations

```
I_xx·omega_x_dot + (I_zz − I_yy)·omega_y·omega_z = M_x
I_yy·omega_y_dot + (I_xx − I_zz)·omega_z·omega_x = M_y
I_zz·omega_z_dot + (I_yy − I_xx)·omega_x·omega_y = M_z
```

Now specialise to the axisymmetric case `I_yy = I_zz = I_t`, `I_xx = I_a`:

```
I_a·omega_x_dot                                   = M_x
I_t·omega_y_dot − (I_t − I_a)·omega_z·omega_x     = M_y
I_t·omega_z_dot + (I_t − I_a)·omega_x·omega_y     = M_z
```

**This is character-for-character the block in `dev/docs/latex/research/3d_equations_of_motion.md`
§4** (the user's own sign-off artefact), and the pitch line is character-for-character
`dev/docs/task-109-roll-reaction-wheel.md` §109.1.4's `I_t·q_dot = M_y − (I_x − I_t)·r·p` with
`p = omega_x`, `q = omega_y`, `r = omega_z`. Two independent artefacts, derived at different times
by different agents, agree with the from-scratch derivation above. **The signs are confirmed.**

Further specialisation, the one that ties this step to the trusted 2D path: with
`omega_x = omega_z = 0` the pitch line collapses to `I_t·omega_y_dot = M_y`, which is exactly
`sim/dynamics.py:407`'s `dydt[OMEGA] = M_y / I`.

### 30.1.5 Admissibility of a symmetric inertia tensor — and a constraint the user should know about

Two conditions, each derived from one integral.

**(a) Positive definiteness.** For any `omega`,

```
omega · (I_body · omega) = ∫ |omega × r|² dm  ≥ 0
```

(the rotational kinetic energy, doubled). So `I_body` is always positive *semi*-definite, and it is
positive *definite* unless every mass element lies on a single line through B. A rocket is not a
line, so a physically real tensor has **all three eigenvalues strictly positive**.

**(b) Triangle inequalities.** In *any* orthonormal body frame,

```
I_xx + I_yy − I_zz = ∫[ (y²+z²) + (x²+z²) − (x²+y²) ] dm = 2∫z² dm  ≥ 0
```

and cyclically. On the principal axes (where the matrix is diagonal with eigenvalues
`λ_1 ≤ λ_2 ≤ λ_3`) this reads `λ_1 + λ_2 ≥ λ_3`, the binding one of the three.

**These two conditions are not just necessary — together they are sufficient.** Given
`λ_i > 0` with strict triangle inequalities, a uniform solid ellipsoid of mass `m` and semi-axes

```
a² = (5/2m)(λ_2 + λ_3 − λ_1),   b² = (5/2m)(λ_1 + λ_3 − λ_2),   c² = (5/2m)(λ_1 + λ_2 − λ_3)
```

realises them exactly. So the validator in §30.8 is testing precisely "could this tensor have come
from a real mass distribution", with no slack and no conservatism.

**The consequence that matters for the user's choice of a full 6-value tensor.** Combining the two
triangle inequalities that contain `I_xx`:

```
I_xx + I_yy − I_zz ≥ 0  and  I_xx + I_zz − I_yy ≥ 0   ⟺   |I_yy − I_zz| ≤ I_xx
```

For the demo airframe (`m = 1.5 kg`, transverse `I ≈ 0.15 kg·m²`, `d_ref = 0.054 m`, so axial
`I_xx ≈ 5.5e-4 … 1.1e-3 kg·m²` for solid-cylinder vs thin-shell) this is a **hard ceiling of about
0.4–0.7 % on the difference between the two transverse moments**. Physically obvious in hindsight —
for an axisymmetric body `I_yy = I_zz` exactly, and `I_xx = 2∫z² dm` is itself the whole slack —
but it is worth stating plainly: the extra generality the full tensor buys on the *diagonal* is
confined to a sub-percent band by physics, not by this implementation. The genuinely new freedom
the full tensor buys is the **off-diagonal** one (body axes that are not principal axes), which has
no such narrow bound.

This is a disclosure, not an argument: the full tensor is the chosen model and is implemented in
full. But a user who types `I_yy = 0.150, I_zz = 0.151, I_xx = 5.5e-4` will get a `ValueError`, and
they must be able to find out why from the error message (§30.8 specifies the wording).

### 30.1.6 What the general tensor breaks: exact planarity

`tests/test_dynamics3d.py`'s load-bearing invariant today is that the out-of-plane components stay
**exactly** `0.0` — not approximately — which proves the 3D embedding has no spurious out-of-plane
coupling.

That invariant survives Step 30 **only for a diagonal tensor**:

- With `I_xy = I_xz = I_yz = 0` and planar state (`omega = (0, omega_y, 0)`, `M = (0, M_y, 0)`):
  `H = (0, I_yy·omega_y, 0)`, so `omega × H = 0` exactly, the RHS is `(0, M_y, 0)` exactly, and LU
  on a diagonal matrix has zero multipliers, so `omega_dot = (0, M_y/I_yy, 0)` with exact zeros in
  x and z. `q_dot` with `omega_x = omega_z = 0` leaves `q_1 = q_3 = 0` exactly. Planarity holds
  bit-exactly. ✔
- With any non-zero off-diagonal, `I_body⁻¹` couples the axes and a pitch moment **legitimately**
  produces roll and yaw acceleration. The rocket leaves its launch plane. **That is correct
  physics**, and it is the entire point of modelling mass asymmetry.

So §30.9 needs **both**: the exact-planarity test (diagonal tensor, strengthened — it now proves
the rotational block too, not just the translational one) **and** a new positive test that a
non-zero `I_xy` demonstrably breaks planarity. The second test is what stops a future refactor from
"fixing" the first one by hard-zeroing out-of-plane terms.

---

## §30.2 Where the tensor lives — the `Inertia` group, and why not `Weight`

### 30.2.1 What `Weight` is today

`sim/params.py:46-59`:

```python
@dataclass(frozen=True)
class Weight:
    m: float                      # initial (wet) mass [kg]
    I: float                      # pitch MOI about the CoG [kg*m^2]
    m_d: Optional[float] = None   # dry mass [kg]; None = mass model off (Step 36 gate)
    l_d: float = 0.0
    l_p: float = 0.0
    I_d: float = 0.0
    I_sp: float = 0.0
    I_p_spec: Optional[float] = None
```

Three properties of this group decide the question:

1. **`Weight.I` is not the inertia of a rigid body — it is the `t = 0` value of a time-varying
   quantity.** With the mass model on (`m_d` set), `sim/dynamics.py` calls
   `sim.mass.moment_of_inertia(m_p, l_B, p)`, which rebuilds `I(t)` every RHS evaluation from the
   two-lump model with a parallel-axis shift as the CoG travels. `Weight.I` is only the initial
   (wet) value.
2. **`Weight` is DERIVED, not user-supplied.** `configs/schema.py:378` builds it with
   `_weight_from_pieces(sc.rocket.airframe, sc.rocket.sections, sc.motor, sc.g0)` — a composition
   of the airframe lump and the motor's own mass/CoG/MOI history (§32.3, D-56/D-57), with a
   bit-for-bit pass-through branch for `mass_model == "none"`.
3. **Every pinned 2D number in the suite flows through it.**

### 30.2.2 The decision

> **New `Params` group `Inertia`, owned by the `Rocket` piece. `Weight` is not touched at all.**

Rationale, in descending order of weight:

| # | Reason |
|---|---|
| 1 | **Different physical object.** `Weight.I` is `I_yy(t)` of a variable-mass vehicle. `Inertia.I_yy` is a component of a **constant** rigid-body tensor (§30.1.3 precondition 1 — the 3D path has no mass model). Deriving one from the other would either silently freeze a time-varying quantity or pretend a constant one varies. Both are the kind of wrong this project's history keeps catching. |
| 2 | **Different provenance / one-owner invariant (§31.3.2).** `Weight` is derived from three pieces by a function; the tensor is six numbers a user measures or computes. Putting user input into a derived group means threading six fields through `_weight_from_pieces`' two `Weight(...)` construction sites and through `Airframe` + `Motor` composition — and *composing* off-diagonal products of inertia across two lumps needs lateral offsets nobody has. That is a whole feature, not a field. |
| 3 | **Structural pin safety.** Nothing in the 2D chain imports `Inertia`; `Weight`'s field set, `_weight_from_pieces`, and every `Weight(...)` call site are byte-identical. §30.11. |
| 4 | **Precedent.** `actuator` (Step 103), `sensors` (Step 108) and `roll` (Step 109) are all exactly this: a new group on `Params`, owned by `Rocket`, gated by a `model` string, defaulting to off. Following it costs nothing and reviewers already know the shape. |

### 30.2.3 The group

Add to `sim/params.py`, immediately after `Roll` (so the two rotational groups sit together), and
add `inertia: Inertia = field(default_factory=Inertia)` to `Params` immediately after `roll`:

```python
@dataclass(frozen=True)
class Inertia:
    """Step 30 (task-30-3d-rotational-dynamics.md): the vehicle's full
    symmetric moment-of-inertia tensor in body axes, for the 3D rotational
    equations of motion (sim/inertia.py, sim/dynamics3d.py).

    Six independent components, NOT the axisymmetric `diag(I_a, I_t, I_t)`
    special case: body axes are not assumed to be principal axes, and
    `I_yy == I_zz` is not assumed (user decision, 2026-10-24).

    SIGN CONVENTION (task-30 SS30.1.2, derived there, not merely cited).
    The three products of inertia are the *integrals*

        I_xy = INT x*y dm    I_xz = INT x*z dm    I_yz = INT y*z dm

    (Hibbeler SS21.1; Stevens & Lewis ch.1; what a CAD mass-properties
    report calls "products of inertia"), so the MATRIX carries minus signs
    off the diagonal:

        [  I_xx  -I_xy  -I_xz ]
        [ -I_xy   I_yy  -I_yz ]
        [ -I_xz  -I_yz   I_zz ]

    That assembly lives in exactly one place, `sim/inertia.py::tensor`, and
    is pinned by a point-mass test. Do not re-derive it anywhere else.

    Moments are about the instantaneous CoG (point B), the same reference
    point the 2D moment arms use (sim/dynamics.py's `aA`/`aB`).

    RELATION TO `Weight.I` -- deliberately none (SS30.2). `Weight.I` is the
    t=0 value of a *time-varying* transverse MOI rebuilt every RHS call by
    `sim.mass.moment_of_inertia` as the propellant burns and the CoG
    travels; `I_yy`/`I_zz` here are components of a *constant* rigid-body
    tensor, because the 3D path has no variable-mass model (SS30.1.3). They
    are the same physical quantity only when the mass model is off. Nothing
    derives one from the other and nothing silently cross-checks them --
    see SS30.8.3 for the one cross-check that IS made (against `Roll.I_x`),
    and SS30.15 for the backlog item that unifies them when a 3D mass model
    arrives.

    `model = "none"` (the default) is the off switch and leaves the 3D
    rotational *dynamics* off: `domega/dt == 0.0` exactly, i.e. a prescribed
    constant body rate. The attitude *kinematics* (`dq/dt`) are live either
    way -- they need no inertia (SS30.5.2).
    """
    model: str = "none"           # none | tensor
    # --- moments of inertia about the CoG, body axes [kg*m^2]; REQ when model == "tensor"
    I_xx: float = 0.0             # axial (roll), INT(y^2+z^2) dm
    I_yy: float = 0.0             # transverse (pitch), INT(x^2+z^2) dm
    I_zz: float = 0.0             # transverse (yaw), INT(x^2+y^2) dm
    # --- products of inertia [kg*m^2]; 0.0 = body axes ARE principal axes (the normal case)
    I_xy: float = 0.0             # INT x*y dm   (matrix entry is -I_xy)
    I_xz: float = 0.0             # INT x*z dm   (matrix entry is -I_xz)
    I_yz: float = 0.0             # INT y*z dm   (matrix entry is -I_yz)
```

**Why a `model` gate at all**, given a zero tensor could serve as the off switch: a zero tensor is
*singular*, so "unset" and "nonsense" would be indistinguishable, and `np.linalg.solve` would raise
`LinAlgError` from inside the RHS instead of a readable `ValueError` at config time. The explicit
gate lets §30.8 reject a half-filled tensor loudly while leaving every existing config inert. It is
also the extension point for a future `model = "axisymmetric"` (derive `diag(Roll.I_x, Weight.I,
Weight.I)` and spare the user six numbers) — **named here, deliberately not implemented**, because
the chosen model is the full tensor and adding a convenience mode in the same step would blur what
was approved.

---

## §30.3 `sim/inertia.py` — the new module

A new, small, deep module (`codebase-design` vocabulary: narrow interface, all the sign and
admissibility knowledge behind it). Three public functions, no state, no I/O.

```python
def tensor(ine) -> np.ndarray:
    """The 3x3 symmetric inertia matrix in body axes from an `Inertia` group
    (SS30.1.2). The ONLY place the product-of-inertia minus signs appear."""

def validate(ine) -> None:
    """Fail-fast admissibility check (SS30.1.5, SS30.8). Raises ValueError
    with a message naming the offending condition and value. No-op when
    `ine.model == "none"`."""

def omega_dot(I: np.ndarray, omega: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Euler's rotational EOM, general form (eq. 30.2):
    omega_dot = I^-1 (M - omega x (I omega))."""
```

### 30.3.1 `tensor`

```python
    return np.array([
        [ ine.I_xx, -ine.I_xy, -ine.I_xz],
        [-ine.I_xy,  ine.I_yy, -ine.I_yz],
        [-ine.I_xz, -ine.I_yz,  ine.I_zz],
    ])
```

Symmetry is structural (the same six names are written twice), so no symmetrisation step and no
symmetry check are needed at runtime — `tests/test_inertia.py` asserts
`np.array_equal(I, I.T)` once to pin that the literal above stays symmetric under edits.

Built fresh per RHS call. **Do not** cache it in `Params` (that group holds inputs, not derived
arrays). If profiling ever shows the ~2 µs matters, `functools.lru_cache(maxsize=None)` on
`tensor` is safe and is a one-line change — `Inertia` is a frozen dataclass of floats and therefore
hashable — but do not add it speculatively.

### 30.3.2 `omega_dot`

Write the cross product out component-wise rather than calling `np.cross`, matching
`sim/quaternion.py::q_dot`'s own explicit style (and avoiding `np.cross`'s per-call overhead on a
3-vector):

```python
    wx, wy, wz = omega
    Hx, Hy, Hz = I @ omega
    rhs = np.array([
        M[0] - (wy * Hz - wz * Hy),
        M[1] - (wz * Hx - wx * Hz),
        M[2] - (wx * Hy - wy * Hx),
    ])
    return np.linalg.solve(I, rhs)
```

**`np.linalg.solve`, not a precomputed inverse** — correctness first, consistent with this
project's standing preference, and the near-singular corner of §30.1.5 (a slender airframe has a
condition number of order `I_t/I_a ≈ 275`, fine for LU, worse for an explicit inverse). A closed-form
3×3 cofactor inverse would be faster but is hand-written arithmetic in the one place this ticket
most wants to avoid hand-written arithmetic.

`validate` (which `assemble` has already run, §30.8) guarantees `I` is non-singular, so `solve`
cannot raise in a validated run. `omega_dot` itself does **not** validate — per-RHS-call validation
is exactly the cost this project's eager-validation convention exists to avoid (cf. §109.7.2).

---

## §30.4 `sim/forces3d.py` — the moment vector

### 30.4.1 The scope fork, and the call

`forces3d.py` has **no moment function at all** today — it carries only `weight_inertial_3d`,
`thrust_body_3d`, `aero_force_body_3d`. So Step 30 has to choose what `M` is:

| Option | What it gives | Cost | Verdict |
|---|---|---|---|
| **M-a. `M = 0` identically** | Torque-free rotation only. The strongest *internal* check (angular-momentum conservation under the gyroscopic term) is available, and nothing new is needed in `forces3d.py` | 0 lines | **Rejected.** With `M ≡ 0` the step cannot demonstrate the roadmap's own stated check for Step 30 ("a body-symmetric rocket with planar initial conditions reproduces the Phase 1 pitch history"), which is the only check that ties the new rotational path to the *trusted* 2D one. A step that validates only against itself is not worth shipping. |
| **M-b. Embed the 2D pitching moment: `M = (0, M_y, 0)`** | Planar equivalence against the 2D pitch history becomes testable. `M_x = M_z = 0` is documented as Step 31's scope (the research note's §5 says exactly this) | ~25 lines, reusing the existing `_s2d` adapter verbatim | **Chosen.** |
| **M-c. Full 3D moment `M = BC×T + BD×A_f + A_m` with 3-vector arms** | The real thing | Needs 3-vector moment arms, which re-opens the unresolved Step 36 fork (should `l_1`/`l_2` follow `l_B(t)`), plus a 3D `A_m` (yaw from sideslip, roll from fin cant) that is blocked on airframe geometry | **Rejected — Step 31.** Explicitly out of scope, see §30.15. |

### 30.4.2 `moment_body_3d`

Add one function, mirroring the three existing embeddings' structure and docstring style:

```python
def moment_body_3d(t: float, s: np.ndarray, p) -> np.ndarray:
    """M about the CoG, body frame, 3-vector -- the 2D pitching moment
    `M_y` embedded with zero roll and yaw components (module docstring,
    task-30 SS30.4).

    `M_y` is assembled exactly as `sim/dynamics.py` assembles it:
    `_cross_y(aB, thrust) + _cross_y(aA, aero_force) + aero_moment_y(...)`.
    `M_x = M_z = 0.0`: no roll moment (fin cant) and no yaw moment
    (sideslip) are modelled yet -- Step 31's scope, and the research note
    `3d_equations_of_motion.md` SS5 states the same staging.
    """
```

Three implementation notes, all load-bearing:

1. **The sign needs no conversion.** `sim/dynamics.py:141-148`'s
   `_cross_y(a, b) = -(a_x*b_z - a_z*b_x) = a_z*b_x - a_x*b_z` is *exactly* the y-component of the
   standard right-handed 3D cross product `a × b` for in-plane `a = (a_x, 0, a_z)`,
   `b = (b_x, 0, b_z)`. So `M_y` from the 2D chain drops straight into the 3D moment vector's
   middle slot with no sign flip. Verified by hand; pinned by §30.9 test 17.
2. **Do not duplicate the arm arithmetic.** `aA`/`aB` and the three moment terms live inside
   `sim/dynamics.py::derivatives` (lines ~336-356), not in a reusable function. Two sub-options:
   (i) extract a small `dynamics.pitch_moment(t, y, p, flow, hold, fb, coeffs) -> float` and have
   both callers use it; (ii) reproduce the five lines in `forces3d.py`.
   **Choose (i)** — a pure extraction with the identical expression, no behaviour change, is the
   only version that cannot drift out of sync, and this project has already paid for a drifted
   duplicate once (`c_mq`/`C_m` convention audit, Step 115). The extraction must be
   **expression-identical**: same operand order, same intermediate names, so the 2D result is
   bit-for-bit. Full-suite run is the proof (§30.11).
   *If, on reading `derivatives`, the extraction turns out to need more than the local `flow`,
   `hold`, `fb`, `coeffs` already in scope there — stop and return `needs_input`; do not refactor
   `derivatives`' control flow in this step.*
3. **The planar adapter's limits carry over unchanged.** `_s2d` is documented as valid only for a
   pitch-only quaternion (`forces3d.py:50-56`). `moment_body_3d` inherits that: it is correct for
   planar attitude and an approximation otherwise, exactly like the three force wrappers beside it.
   Say so in the docstring; Step 31 replaces the whole adapter.

---

## §30.5 `sim/dynamics3d.py` — the rotational block

### 30.5.1 The code

Replace lines 52-53. The whole change:

```python
    omega = y[OMEGA]
    ...
    dydt[Q] = quaternion.q_dot(q, omega)
    if p.inertia.model == "none":
        dydt[OMEGA] = 0.0
    else:
        I_b = inertia.tensor(p.inertia)
        M_b = moment_body_3d(t, y, p)
        dydt[OMEGA] = inertia.omega_dot(I_b, omega, M_b)
```

with `from sim import inertia` and `moment_body_3d` added to the `sim.forces3d` import.

Dispatch style note: `Roll` (Step 109) and `Aero` use a dict-dispatch (`_ROLL_LAWS`) when there are
three or more branches. Two branches is an `if`. Do not build a registry for one real model.

### 30.5.2 Why `dq/dt` is NOT gated

`q_dot` is pure kinematics — it reads `q` and `omega` and no inertia at all. Gating it on an
*inertia* parameter would be a non-sequitur, and worse: with `model = "none"` and `omega ≠ 0` it
would hold the attitude fixed while the body is stated to be rotating, which is not an off switch
but a wrong model. So:

- `model = "none"` → **prescribed-rate kinematics**: `omega` is exactly constant, `q` integrates
  under it. Well-defined, documented, and useful (it is how a commanded tumble or a frozen-dynamics
  sanity run is expressed).
- `model = "tensor"` → full rotational dynamics.

**Retirement of a documented behaviour, stated explicitly so it is not a silent stale docstring:**
Step 29's "`dq/dt = 0` identically" is **retired** at Step 30. Both places that assert it in prose
must be corrected:

- `sim/dynamics3d.py`'s module docstring (lines 16-17 and the Step-29 "Check" paragraph).
- `sim/state3d.py`'s module docstring, lines 9-12 ("Step 29 scope: `q` and `omega` are both held
  exactly constant for the whole integration -- `dq/dt = 0`, `domega/dt = 0` identically").
- `tests/test_dynamics3d.py:92` ("Attitude/angular velocity are genuinely held constant (Step 29
  scope)") — the *assertions* there still pass unchanged (§30.11.2); only the reason changes, from
  "the code forces it" to "`omega = 0` and `M = 0` make it so". That is a strictly stronger
  statement and the comment must say which.

### 30.5.3 Rail and parachute

`sim/dynamics.py` freezes `dtheta/dt`/`domega/dt` while on the rail or under the parachute
(`attitude_frozen`). The 3D path has **no rail and no parachute** — those live in
`sim/integrate.py`'s event machinery, which the 3D layout cannot reach (§30.0.2). Out of scope for
Step 30; it is Step 30b's problem, and Step 30b must not forget that the 3D rotational block needs
the same two freezes. Recorded in §30.15.

---

## §30.6 Quaternion norm drift

`|q| = 1` is preserved by `q_dot` only in exact arithmetic. The research note's §7.2 left the
renormalisation strategy open ("every RHS call vs. a solver event", explicitly flagged as "a pure
implementation-cost choice with no physics content, could be left to the developer").

> **Decision (architect): the RHS does not renormalise.** `derivatives_3d` returns `q_dot(q, omega)`
> and nothing else.

Reasons:

1. Renormalising inside the RHS **changes the vector field** the solver is integrating. `solve_ivp`
   builds its error estimate and dense-output polynomial from RHS evaluations at trial points; a
   projection applied there is inconsistent with the ODE it thinks it is solving, which degrades
   the step-size controller rather than helping it.
2. Renormalisation belongs at step/output boundaries — which is `run_sim`'s job, and there is no
   3D `run_sim` yet. Step 30 has nowhere correct to put it.
3. Drift over a flight-length span is tiny and, crucially, **measurable**: §30.9 test 18 asserts
   `abs(norm(q) - 1) < 1e-9` over the test span, so the quantity is pinned rather than hidden.

Carried to Step 30b: pick between per-accepted-step projection and a solver event, and only then.
`sim/quaternion.py::normalise` already exists for it.

---

## §30.7 `configs/` — schema and template wiring

**This is not optional**, and it is the step most easily forgotten. Step 109's ticket §109.7b
documented the trap; it applies verbatim:

`tests/test_config_pieces.py::test_assemble_params_call_keyword_set_equals_params_fields_exactly`
parses `configs/schema.py::assemble`'s own source for the `Params(...)` call site and asserts its
keyword set equals `{f.name for f in dataclasses.fields(Params)}` **exactly**. Adding a group to
`Params` without wiring it through `schema.py` fails that test immediately. Do not re-derive the
pattern — copy it.

Four edits:

1. **`configs/schema.py`** — add `Inertia` to the `sim.params` imports (the file imports one group
   per line, e.g. `from sim.params import Roll` at line 76; follow that).
2. **`configs/schema.py::Rocket`** — one field, immediately after `roll`, with the same
   owner-rationale comment shape:

   ```python
       # Step 30 (task-30-3d-rotational-dynamics.md SS30.2): the full 3D
       # moment-of-inertia tensor -- a property of the airframe-plus-motor
       # assembly, so the same owning piece as `roll` above, not a
       # run-level/weather/site concern (SS31.3.2's one-owner invariant).
       inertia: Inertia = dataclasses.field(default_factory=Inertia)   # Step 30
   ```
3. **`configs/schema.py::assemble`** — one more keyword in the `Params(...)` call:
   `inertia=sc.rocket.inertia,` (place it after `roll=sc.rocket.roll,`), **plus** the validation
   call described in §30.8.2.
4. **`configs/rockets/_TEMPLATE_rocket.py`** — a commented-out `inertia=Inertia(...)` block plus a
   row in the group table at the top and a field table section, following the `Roll` block's exact
   shape (`_TEMPLATE_rocket.py:49`, `:160-171`, `:305-321`). Every field marked `REQ|OPT` with unit
   and a one-line description, per `CLAUDE.md` § "Шаблоны конфигов". All `OPT` except the three
   diagonal moments, which are `REQ iff model == "tensor"`. Add `Inertia` to the template's
   `from sim.params import ...` line.

**Leave `_GROUP_DEFAULTS` in `tests/test_config_pieces.py` alone.** It does not contain `actuator`,
`sensors` or `roll` either (Step 103 set that precedent, Step 109 followed it); adding `inertia`
would force a non-default tensor into `_non_default_scenario()` for no new coverage. Note it and
move on.

**No demo config turns the model on.** `configs/` holds only demo and template configs
(`CLAUDE.md`), and there are no measured inertia numbers for this airframe — the same data gap that
blocks `Roll.I_x`, `c_mq` and Barrowman. A tensor-enabled scenario is for the user to write when
real mass properties exist. Every tensor value in this step lives in test files.

---

## §30.8 Validation — where it runs, what it rejects

### 30.8.1 Add it, do not defer it

Recommendation: **add the fail-fast check now**, in this step. Three reasons:

1. The failure mode without it is bad and remote from its cause: a non-positive-definite tensor
   gives a *silently wrong* `omega_dot` (energy growing without bound, a tumble that accelerates),
   or — for a singular one — a `numpy.linalg.LinAlgError` raised from the middle of
   `solve_ivp`'s step loop with a stack trace pointing at `np.linalg.solve`, not at the config.
2. §30.1.5 makes the check **provably exact**, not conservative: the conditions it tests are
   necessary *and* sufficient for the tensor to come from a real mass distribution. There is no
   false-positive risk to trade against.
3. The §30.1.5 ceiling `|I_yy − I_zz| ≤ I_xx` is tight (sub-percent for a slender airframe) and
   deeply unobvious. Without a check with a good message, the first user to try a mildly asymmetric
   tensor gets a wrong flight instead of an explanation. This check is the main *user-facing* value
   of the whole admissibility analysis.

Cost: ~25 lines plus five tests.

### 30.8.2 Where it runs

`sim/inertia.py::validate(ine)` holds the predicate — pure, no config dependency, directly
testable. It is **called** from `configs/schema.py::assemble`, inside the existing fail-fast block
added at step (2b) (the Step-99 aero-v2 guards, `schema.py:398`), i.e. after `overrides` have been
applied so that an override cannot smuggle in an inadmissible tensor:

```python
    inertia_mod.validate(p.inertia)
```

This is the §109.7.2 eager-validation convention: once, at assembly time, not per RHS call.
`validate` is a no-op when `model == "none"`, so every existing config and every 2D scenario is
untouched.

`derivatives_3d` does **not** validate (§30.3.2). When Step 30b gives the 3D path a `run_sim`
entry point, that entry point calls `validate` too — same as `run_sim` validates `Roll` today.
Recorded in §30.15.

### 30.8.3 What it rejects

| # | Condition | Check | Message must name |
|---|---|---|---|
| 1 | unknown model | `ine.model not in {"none", "tensor"}` | the value and the two legal ones |
| 2 | not positive definite | `min(eigvalsh(I)) <= 0` | the smallest eigenvalue, and that a real body's principal moments are all > 0 |
| 3 | triangle inequality violated | for ascending eigenvalues `l1 <= l2 <= l3`: `l1 + l2 - l3 < -tol` | the three principal moments and the violated sum; and, when the violation is the `I_xx` one, the derived ceiling `\|I_yy - I_zz\| <= I_xx` with the actual numbers (this is the message a user will actually hit — §30.1.5) |
| 4 | inconsistent with the 2D roll DOF | `roll.model != "none"` **and** `inertia.model == "tensor"` **and** `abs(roll.I_x - inertia.I_xx) > 1e-9 * max(abs(roll.I_x), abs(inertia.I_xx))` | both field paths and both values, and that they are the same physical quantity (axial MOI about `x_hat_r`, reaction wheel included and locked, per `Roll.I_x`'s own docstring) |

Notes:

- Use `np.linalg.eigvalsh` (symmetric solver, real ascending eigenvalues), not `eigvals`.
- `tol` absorbs eigensolver round-off only, **not** leniency: `tol = 1e-12 * trace(I)`. Scale-free,
  and far below any physically meaningful margin. (Sanity anchor: for the demo airframe the true
  slack in the binding inequality is `I_xx ≈ 5e-4`, nine orders of magnitude above `tol`.)
- Check 3 is a hard `ValueError`, not a warning. Project convention is fail-fast on nonsense input,
  and a warning for a condition that makes the answer wrong is worse than useless — but the message
  carries the whole explanation, so it is self-documenting rather than merely blunt.
- Check 4 is inert for every config that sets only one of the two (which is every config that
  exists). It exists because `Roll.I_x` and `Inertia.I_xx` are **the same number reached by two
  paths**, and a config that disagrees with itself about the vehicle's axial inertia is a bug
  nobody would find by reading two different files. Both are "wheel included and locked", so they
  must be equal, not merely close.
- Check 4 lives in `assemble`, not in `sim/inertia.py::validate` (which takes only the `Inertia`
  group). Give it its own small helper beside the Step-99 guards, or extend `validate`'s signature
  to `validate(ine, roll=None)` — implementer's choice, state it in the docstring either way.

---

## §30.9 Test-impact table

### New file: `tests/test_inertia.py`

| # | Test | What it pins |
|---|---|---|
| 1 | `test_tensor_is_symmetric_and_carries_the_minus_signs` | Hand-set all six fields to distinct values; assert the nine entries literally, and `np.array_equal(I, I.T)` |
| 2 | **`test_tensor_matches_the_mass_integral_for_three_point_masses`** | **The convention pin, and the single most important test in this ticket.** Place three point masses at hand-chosen asymmetric `(x,y,z)`; compute all six components from the integral definitions of §30.1.2 by explicit summation in the test; build `Inertia(...)` from them; then for several `omega` assert `tensor(ine) @ omega == Σ m (r × (omega × r))` (computed directly with `np.cross`) to `~1e-15`. **This test fails if any sign anywhere in §30.1.2 is wrong**, and it does not depend on the ticket's own algebra being right |
| 3 | `test_validate_accepts_a_slender_axisymmetric_airframe` | `I_xx=5.47e-4, I_yy=I_zz=0.15`, zero products (the demo-airframe order of magnitude) — accepted |
| 4 | `test_validate_accepts_an_off_principal_axis_tensor` | Small non-zero `I_xy`/`I_xz`/`I_yz` on top of #3 — accepted (the user's chosen generality actually works) |
| 5 | `test_validate_rejects_a_singular_tensor` | all-zero with `model="tensor"`, and `diag(0.0, 1.0, 1.0)` — both `ValueError` |
| 6 | `test_validate_rejects_a_negative_eigenvalue` | an off-diagonal large enough to push an eigenvalue negative (e.g. `I_xx=I_yy=1, I_xy=2`) — `ValueError` |
| 7 | `test_validate_rejects_a_triangle_inequality_violation` | `diag(1, 1, 10)` — positive definite but not realisable — `ValueError` |
| 8 | **`test_validate_bounds_the_transverse_split_by_the_axial_moment`** | §30.1.5's ceiling. `I_xx=5.0e-4`: `I_yy=0.150, I_zz=0.1504` → `ValueError`; `I_yy=0.150, I_zz=0.1503` → accepted. Assert the message mentions `I_xx` |
| 9 | `test_validate_is_a_noop_when_model_is_none` | a deliberately absurd tensor with `model="none"` — no raise |
| 10 | `test_validate_rejects_an_unknown_model` | `model="diagonal"` — `ValueError` naming the legal values |
| 11 | `test_omega_dot_reduces_to_the_axisymmetric_component_form` | For a diagonal `I_yy=I_zz` tensor and several random `(omega, M)`, compare against the three scalar equations of §30.1.4 **written out independently in the test** (not calling `omega_dot`). Pins the gyroscopic signs against the research note's own §4 |
| 12 | `test_omega_dot_reduces_to_the_2d_scalar_equation` | diagonal, `omega=(0,w,0)`, `M=(0,M_y,0)` → `omega_dot == (0.0, M_y/I_yy, 0.0)` with x and z **exactly** `0.0` (§30.1.6) |
| 13 | **`test_torque_free_motion_conserves_angular_momentum_and_energy`** | **The gyroscopic-term sign check.** A fully asymmetric tensor (three distinct diagonal values *and* non-zero products, chosen admissible), nonzero 3-axis `omega0`, `M = 0`; integrate `omega_dot` with the project's own fixed-step `rk4` (version-stable, `CLAUDE.md`) over ~10 s; assert `‖I·omega‖` and `½ omega·I·omega` are both constant to ~1e-10 relative. A sign error in any cross term breaks at least one of the two |
| 14 | `test_validate_rejects_a_tensor_that_disagrees_with_roll_I_x` | §30.8.3 check 4, via `assemble` (see the next table) |

### Existing file: `tests/test_dynamics3d.py` — new tests

| # | Test | What it pins |
|---|---|---|
| 15 | `test_prescribed_rate_kinematics_with_no_inertia_model` | `model="none"`, `omega=(0, 0.1, 0)`, `q` pitch-only: `omega` exactly constant throughout, and `theta(t)` from `quaternion.to_euler(q)[1]` matches `theta0 + 0.1·t` to solver tolerance. Pins §30.5.2 |
| 16 | **`test_planar_3d_reproduces_the_phase1_2d_pitch_history`** | **The roadmap's own stated Step-30 check.** Non-zero `C_m` so `M_y ≠ 0`; **mass model OFF** (`m_d=None`) so the 2D `I` is the constant `Weight.I`; diagonal tensor with `I_yy = I_zz = Weight.I` and a slender `I_xx`. Run the 2D path and the 3D path over the same span; assert `theta(t)` and `omega_y(t)` match the 2D `theta`/`omega` to solver tolerance, **and** that `r[1]`, `v[1]`, `omega_x`, `omega_z`, `q_1`, `q_3` are **exactly** `0.0` at every sample (§30.1.6) |
| 17 | `test_moment_body_3d_embeds_the_2d_pitching_moment` | At several mid-flight states, `moment_body_3d(t, y3d, p)[1]` equals the 2D moment (`dynamics.derivatives(...)[OMEGA] * I`) to `rel_tol=1e-13`, and components 0 and 2 are exactly `0.0`. Pins §30.4.2 note 1 (no sign conversion) and guards the §30.4.2 extraction |
| 18 | `test_off_diagonal_inertia_breaks_planarity` | Same setup as #16 but with a non-zero admissible `I_xy`: assert `omega_x` and `omega_z` become non-zero and `r[1]` leaves the plane. **The positive test for the chosen model** — and the guard that stops a later refactor from restoring #16's exact zeros by hard-zeroing out-of-plane terms |
| 19 | **`test_torque_free_tumble_conserves_inertial_angular_momentum`** | The strongest end-to-end check: zero moments (`C_m=C_z=0`, `misalign_deg=0`), asymmetric tensor, 3-axis `omega0`; integrate the full 13-state and assert `to_dcm(q) @ (I·omega)` is constant **in the inertial frame** to ~1e-9 relative. This ties `q_dot`, `to_dcm` and `omega_dot` together — it fails on a frame mismatch or a quaternion-convention error that test 13 cannot see |
| 20 | `test_quaternion_norm_drift_is_bounded` | Over test 19's span, `abs(norm(q) - 1) < 1e-9` at every sample. Pins §30.6 |

### Existing tests to audit — no pin may move

| File | Site | Action |
|---|---|---|
| `tests/test_dynamics3d.py:40-97` `test_planar_3d_matches_phase1_2d_trajectory` | `omega0 = 0`, `C_m = 0` → `M = 0`, so `q_dot(q, 0) == 0` exactly and `omega_dot` is never evaluated (`model="none"` by default). | **Assertions unchanged, and they must stay unchanged.** Only the comment at `:92` is rewritten (§30.5.2). If any assertion needs touching, stop — something is wrong. |
| `tests/test_dynamics3d.py:100-130` `test_derivatives_3d_cross_checks_derivatives_2d_pointwise` | `:130` `assert np.all(dydt_3d[6:13] == 0.0)` | **Passes unchanged.** `q_dot` with `omega = 0` returns `[-0.5*0.0, 0.0, 0.0, 0.0]`; `-0.0 == 0.0` is `True` in IEEE-754, so `np.all(... == 0.0)` holds. Update the trailing comment to say *why* it is zero. |
| `tests/test_quaternion.py` | all | Untouched — `q_dot` is not modified. |
| `tests/test_config_pieces.py:152` keyword-set pin | — | Passes once §30.7 is done; fails loudly if it is forgotten. That is its purpose. |
| `tests/test_config_pieces.py:117` `_GROUP_DEFAULTS` | — | **Deliberately left alone** (§30.7). |
| `tests/test_integrate.py` RK45 `np.array_equal` pins | — | **Must not move.** Structurally cannot (§30.11). If one moves, stop and escalate — do not re-pin (D-77). |
| Everything under `tests/` that constructs `Params(...)` | — | Unaffected: `inertia` has a default factory, so no `Params(...)` call site changes. |

**Full-suite run is the gate** (`python -m pytest -q`, `run_in_background`, ~220 s). Pass condition:
**zero changed numbers anywhere outside `tests/test_inertia.py` and `tests/test_dynamics3d.py`.**

---

## §30.10 Acceptance checks

Ordered by how much each would actually catch — deliberately **not** in roadmap order. The research
note's own §4 check (planar equivalence) is third, not first, because it is the weakest: with
`omega_x = omega_z = 0` the gyroscopic term is identically zero, so planar equivalence cannot see a
sign error in `omega × (I·omega)` at all.

### 30.10.1 The convention check (test 2)

Three point masses at `(0.3, 0.02, -0.01)`, `(-0.2, -0.05, 0.03)`, `(0.05, 0.01, 0.08)` with
distinct masses. Compute the six components by explicit summation of the §30.1.2 integrals in the
test. Then for `omega` in a handful of directions including off-axis ones:

```
tensor(ine) @ omega  ==  Σ_i m_i · (r_i × (omega × r_i))     to ~1e-15 relative
```

This is the only check in the suite that validates the sign convention *independently of this
ticket's algebra*. If it passes, the matrix is right. If it fails, nothing downstream is
trustworthy.

### 30.10.2 Torque-free conservation (tests 13 and 19)

Asymmetric tensor, three-axis initial rate, zero moment.

- **Body frame (test 13):** `‖I·omega‖` and `½ omega·I·omega` both constant to ~1e-10 relative over
  ~10 s of `rk4`. Catches a sign error in any cross-coupling term.
- **Inertial frame (test 19):** `to_dcm(q) @ (I·omega)` constant to ~1e-9 relative over the same
  span, integrating the full 13-component state. Strictly stronger: it also catches a `q`/`omega`
  frame mismatch, a transposed DCM, or a quaternion-order error — none of which test 13 can see,
  because test 13 never touches `q`.

Use `method="rk4"` (fixed step) for both, per `CLAUDE.md`: the in-house `rk4` is version-stable
across numpy/scipy, while the scipy `RK45` path shifts at rounding level between versions (D-77).
A conservation tolerance pinned under `RK45` would be a version-fragile test.

### 30.10.3 Planar equivalence against the trusted 2D path (test 16)

Preconditions that must be written into the test's docstring, because the check is meaningless
without them:

- **mass model OFF** (`Weight.m_d is None`) — otherwise the 2D `I` varies with `t` while the 3D
  tensor is constant (§30.1.3 precondition 1), and the two paths are solving different problems;
- **diagonal tensor** with `I_yy = I_zz = p.weight.I`;
- no rail, no parachute (the 3D path has neither, §30.5.3);
- non-zero `C_m` so that `M_y ≠ 0` and the rotational channel is actually exercised.

Then `theta(t)` (from `quaternion.to_euler(q)[1]`) and `omega_y(t)` match the 2D `theta`/`omega` to
solver tolerance, and the six out-of-plane quantities are **exactly** `0.0`.

> **On "bit-identical":** do not ask for bit-identical trajectories between the 2D and 3D paths.
> `derivatives_3d` reaches the same physics through a different sequence of floating-point
> operations (a 3×3 DCM multiply instead of a 2×2 rotation, `to_euler` to recover `theta`, an LU
> solve instead of a scalar division), so exact trajectory identity is not achievable and its
> absence is not a bug. The achievable and genuinely load-bearing version is the one above:
> **out-of-plane components exactly `0.0`**, in-plane to tolerance. (Same caveat the 3D-readiness
> proposal §5 raised; restated here so it is not lost.)

### 30.10.4 The asymmetry actually works (test 18)

Same setup, non-zero admissible `I_xy`. `omega_x` and `omega_z` become non-zero and `r[1]` leaves
the launch plane. Without this, the whole 6-value model could be inert and every other test would
still pass.

### 30.10.5 Config rejection (tests 5-8, 10, 14)

Every row of §30.8.3's table has a test, including the `|I_yy − I_zz| ≤ I_xx` boundary from both
sides and an assertion that the error message mentions `I_xx`.

---

## §30.11 Pin safety

### 30.11.1 The 2D path

| Claim | Why it is structural, not aspirational |
|---|---|
| `sim/state.py` unchanged | Not in this ticket's file list at all |
| `sim/integrate.py` unchanged | Not in this ticket's file list at all |
| `Weight`'s field set unchanged | §30.2.2 — the tensor is a new group, not a new `Weight` field |
| `_weight_from_pieces` unchanged | Follows from the line above |
| No `Params(...)` call site changes | `inertia` has a `default_factory`, like every group but `weight` |
| `derivatives`' numeric result unchanged | The only edit to `sim/dynamics.py` is the §30.4.2 extraction of three already-existing lines into a module-level function, called from the same place with the same arguments and the identical expression |

**The §30.4.2 extraction is the single highest-risk edit in this ticket** — it is the only one that
touches a file every pinned 2D number flows through. Guard rails:

- it must be a **pure move**: same operand order, same operator order, same intermediate names, no
  reassociation (floating-point addition is not associative, and `M_thrust + M_aero + M_moment`
  must stay exactly that order);
- the full-suite run (`python -m pytest -q`, background) is the proof, not the reading;
- if the extraction turns out to need anything beyond the `flow`, `hold`, `fb`, `coeffs` locals
  already in scope at `sim/dynamics.py:353-356`, **stop and return `needs_input`** rather than
  reshaping `derivatives`' control flow in this step.

### 30.11.2 The 3D path — what gets a test for the first time

Stated explicitly, because this is new capability rather than modified pinned behaviour.

**Frozen (behaviour and assertions unchanged):**

- `tests/test_dynamics3d.py`'s two existing tests. Both use `omega0 = 0` and a zero-moment
  scenario, so `q_dot(q, 0) == 0` exactly and the `model="none"` default leaves `omega_dot` at
  `0.0`. Every assertion, including the `== 0.0` exact ones, holds unchanged. Only comments change.
- `tests/test_quaternion.py` — `q_dot` is not modified.

**Tested for the first time, ever:**

| Capability | First test |
|---|---|
| Quaternion *integration* under a real body rate (as opposed to `q_dot` evaluated pointwise) | 15, 19, 20 |
| The inertia matrix and its sign convention | 1, 2 |
| `omega_dot` — Euler's equations in any form | 11, 12, 13 |
| The gyroscopic term `omega × (I·omega)` | 13, 19 |
| A 3D moment vector of any kind | 17 |
| Non-planar rotational motion | 18, 19 |
| Rotational angular-momentum / energy conservation | 13, 19 |
| Inertia-tensor admissibility validation | 5-8, 10 |
| Quaternion norm drift as a measured quantity | 20 |

**No numeric pin is created in this step.** No `np.array_equal` fixture, no committed reference
trajectory. Every new assertion is a physical invariant (conservation, exact zero, closed-form
agreement) or an exception. A committed 3D reference trajectory is Stage 2 of the 3D-readiness
proposal's rollout (an `rk4` shadow run) and is a separate step — deliberately not bundled here, so
that this step cannot be the thing that freezes a number before the physics has been reviewed.

---

## §30.12 Cost re-estimate against the proposal's "~30 lines"

`dev/docs/latex/research/3d-readiness-proposal.md` §1.1 and §3.1 estimated Step 30 at
"**roughly a 30-line, one-file, one-new-param change**", "2-3 files, 4-6 tests, low risk". **That
estimate assumed the simplest inertia model** — one scalar `I_a` beside the existing axisymmetric
`Weight.I`, with the tensor written inline as `diag(I_a, I_t, I_t)`.

Honest re-estimate for the chosen full 6-value tensor:

| Item | Files | Source lines (incl. docstrings) | Test lines |
|---|---|---|---|
| `sim/inertia.py` (new) | 1 new | ~120 (~40 code, ~80 docs) | — |
| `sim/params.py` — the `Inertia` group + one `Params` field | 1 | ~45 | — |
| `sim/forces3d.py` — `moment_body_3d` | 1 | ~30 | — |
| `sim/dynamics3d.py` — the rotational block + docstring rewrite | 1 | ~35 (8 of them code) | — |
| `sim/dynamics.py` — the `pitch_moment` extraction | 1 | ~+12 / −5 | — |
| `sim/state3d.py` — docstring correction | 1 | ~4 | — |
| `configs/schema.py` — import, `Rocket` field, `assemble` keyword, validate call | 1 | ~12 | — |
| `configs/rockets/_TEMPLATE_rocket.py` — the group block + two table sections | 1 | ~25 | — |
| `tests/test_inertia.py` (new, 14 tests) | 1 new | — | ~260 |
| `tests/test_dynamics3d.py` (6 new tests, 3 comment edits) | 1 | — | ~230 |
| **Total** | **2 new + 7 edited** | **≈270** | **≈490** |

So: **~9× the line estimate, ~3× the file count, ~3× the test count.** Low risk is still the right
risk rating (§30.11), but "one file, 30 lines" is not.

**What drove the growth — and the part that did *not* grow.** The answer to the ticket brief's own
question ("check whether the general Euler form actually adds much code over the axisymmetric
case") is: **the equation itself adds essentially nothing.**

```
# axisymmetric, as the research note wrote it — 3 lines
wx_dot = M[0] / I_a
wy_dot = (M[1] + (I_t - I_a) * wz * wx) / I_t
wz_dot = (M[2] - (I_t - I_a) * wx * wy) / I_t

# fully general — 2 lines
rhs = M - cross(omega, I @ omega)
return np.linalg.solve(I, rhs)
```

The general form is **shorter**. Everything else is what grew:

1. **The validator (~25 source + ~110 test lines) is entirely new work the axisymmetric case did
   not need.** For `diag(I_a, I_t, I_t)` the whole admissibility check is `I_a > 0 and I_t > 0`
   (the triangle inequalities are then automatic, since `I_t + I_t ≥ I_a` always holds for a
   slender body and `I_a + I_t ≥ I_t` is `I_a ≥ 0`). The general case needs an eigensolve, three
   triangle inequalities, and a tolerance argument. **This is the single largest cost of the user's
   choice, and it buys the most: the `|I_yy − I_zz| ≤ I_xx` ceiling (§30.1.5) is a real constraint
   that nobody would otherwise discover until their flight was wrong.**
2. **Six config fields instead of one means a new `Params` group**, which means the whole config
   layer: `schema.py`, the `Rocket` piece, `assemble`'s keyword list, the AST keyword-set pin, the
   template's three blocks (~37 lines + the pin). The one-scalar version would have been a single
   `Weight` field — though note that would not have been free either, since `Weight` is derived by
   `_weight_from_pieces` (§30.2.1).
3. **The moment vector was simply missing from the estimate.** `forces3d.py` has no moment
   function; the proposal's §3.1 assumed `M_y` was available. ~30 source + ~30 test lines, and it
   is what makes planar equivalence testable at all (§30.4.1).
4. **Exact planarity is no longer unconditional** (§30.1.6), so the planar test needs a stated
   precondition and acquires a mirror-image partner (test 18) that did not exist in the
   axisymmetric plan.

Items 2-4 would have been incurred by *any* Step 30. Item 1 is the honest incremental cost of the
full tensor, and it is ~135 lines.

---

## §30.13 Decision log

Resolved by the architect, with the alternative recorded so each is reversible.

| # | Decision | Alternative rejected | Why |
|---|---|---|---|
| D-30.1 | Tensor lives in a **new `Params` group `Inertia`**, owned by `Rocket`; `Weight` untouched | add six fields to `Weight` | `Weight.I` is time-varying and derived; the tensor is constant and user-supplied. Threading six fields through `_weight_from_pieces` would require composing products of inertia across lumps, which needs lateral offsets nobody has (§30.2.2) |
| D-30.2 | Product-of-inertia convention: `I_xy ≡ ∫xy dm`, **matrix carries `−I_xy`** | the physics/Goldstein convention (`I_ij` already negated, no minus in the matrix) | What a CAD mass-properties report and every aerospace text call "products of inertia". Derived from scratch in §30.1.2 and pinned by test 2, so the choice costs nothing in risk |
| D-30.3 | **One** convention, documented | an `Inertia.product_convention: "integral" \| "tensor"` selector, in the style of `Aero.cm_convention` | `cm_convention` exists because real coefficient *tables* arrive in both conventions. Nobody ships an inertia tensor as a file here; one documented convention plus test 2 is enough. Offer the selector only if a real user hits it |
| D-30.4 | Explicit `model: "none" \| "tensor"` gate | a zero tensor as the off switch | A zero tensor is singular, so "unset" and "nonsense" would be indistinguishable, and the failure would surface as `LinAlgError` from inside the solver instead of `ValueError` at config time (§30.2.3) |
| D-30.5 | `model = "axisymmetric"` (derive `diag(Roll.I_x, Weight.I, Weight.I)`) is **named but not implemented** | implement it now as a convenience | The approved model is the full tensor; shipping a simpler mode in the same step would blur what was approved. One line in the docstring reserves the name |
| D-30.6 | **Moment scope M-b**: `M = (0, M_y, 0)` from the existing 2D chain | M-a (`M = 0`, torque-free only); M-c (full 3D moment) | M-a cannot test against the trusted 2D path at all; M-c re-opens the unresolved Step 36 `l_1`/`l_2` fork and needs airframe geometry. §30.4.1 |
| D-30.7 | `moment_body_3d` calls an **extracted** `dynamics.pitch_moment`, not a hand-copied formula | reproduce the five lines in `forces3d.py` | `forces3d.py`'s own module docstring states the file's philosophy: reuse the 2D functions verbatim rather than "duplicating their formulas by hand". A drifted duplicate of a moment formula is exactly the class of bug the Step 115 convention audit cleaned up. Mitigated by §30.11.1's guard rails |
| D-30.8 | Admissibility validation **now**, hard `ValueError`, in `assemble` | defer it; or warn instead of raise | The conditions are necessary *and* sufficient (§30.1.5), so there is no false-positive risk to trade; and the `\|I_yy − I_zz\| ≤ I_xx` ceiling is unobvious enough that a user needs the message, not a silently wrong flight (§30.8.1) |
| D-30.9 | `np.linalg.solve` per RHS call | precompute `I⁻¹` at assembly; hand-written 3×3 cofactor inverse | Correctness first; a slender airframe's tensor has condition number ~`I_t/I_a ≈ 275`, which LU handles and an explicit inverse handles worse. `Params` holds inputs, not derived arrays. `lru_cache` on `tensor` is the cheap optimisation if ever needed (§30.3.1) |
| D-30.10 | `dq/dt` is **never** gated; only `domega/dt` is | gate the whole rotational block on `inertia.model` | `q_dot` needs no inertia. Gating it would freeze the attitude of a body stated to be rotating — a wrong model, not an off switch (§30.5.2) |
| D-30.11 | The RHS does **not** renormalise `q`; drift is measured by test 20 | renormalise every RHS call; a solver event | Projection inside the RHS changes the vector field the error controller sees. The correct home is step/output boundaries, i.e. a `run_sim` that does not exist yet (§30.6). The research note itself left this to the implementer |
| D-30.12 | A `Roll.I_x` ↔ `Inertia.I_xx` consistency check in `assemble` | leave the two independent | They are the same physical number (axial MOI about `x_hat_r`, wheel included and locked) reached by two code paths. A config disagreeing with itself about it is a bug nobody finds by reading two files. Inert for every config that sets only one (§30.8.3 check 4) |
| D-30.13 | No numeric pin, no committed reference trajectory in this step | commit an `rk4` 3D reference run | That is the proposal's Stage 2 and deserves its own step. Freezing a number before the physics has been reviewed is the wrong order (§30.11.2) |
| D-30.14 | Never use the classical `A…F` inertia shorthand | — | `A` is the nose tip in the paper's naming and `A`/`B`/`C`/`D` are points in the code's (§30.1.1) |
| D-30.15 | **LaTeX: L-a, approved by the user 2026-10-25 and written in this pass** — new `sections-ai/rocket-3d.tex`, `\input` + 3 `\bibitem`s in `main.tex`, one bullet each in `appendix.tex`/`assumptions.tex`, the `backlog.tex` 3D item reconciled | L-b (amend `rocket-2d.tex` too); L-c (no LaTeX) | L-a closes the roadmap's declared Step-30 blocker without touching an author-approved section. **Developer scope: none** — `dev/docs/latex/` is read-only for the implementation (§30.14) |
| D-30.16 | Place `rocket-3d` after `other-dynamics`, before `analysis` | right after `rocket-2d` | 3D reads as the generalisation that follows the planar models (its moment vector reuses the `sec:aero` chain, and it reconciles `sec:roll`), and this leaves `rocket-2d.tex`'s position in the document untouched |
| D-30.17 | Annotate, do not edit, `research/3d_equations_of_motion.md` (whose §3 says the tensor "stays diagonal") | correct the note in place | It is the user's own sign-off artefact. `sec:3d_inertia` now states the general case and says explicitly that it is a deliberate widening of the symmetry argument, which supersedes the note without rewriting it |

### Cross-checks performed while writing this ticket

- The general Euler form derived in §30.1.3 specialises **exactly** to
  `dev/docs/latex/research/3d_equations_of_motion.md` §4's axisymmetric block and to
  `dev/docs/task-109-roll-reaction-wheel.md` §109.1.4's pitch equation. Three independent
  derivations agree; the signs are confirmed (§30.1.4).
- `sim/dynamics.py:141-148`'s `_cross_y` is **exactly** the standard right-handed `(a × b)·y_hat`
  for in-plane vectors, so the 2D moment needs no sign conversion to enter the 3D moment vector
  (§30.4.2 note 1).
- `dev/docs/latex/research/3d_equations_of_motion.md` §3's claim that the inertia tensor "is, and
  stays, diagonal" is **superseded by the user's decision**, not corrected — the symmetry argument
  it makes is sound for a perfectly built body of revolution; the full tensor exists to model the
  departure from that. The note should be annotated rather than edited (it is the user's sign-off
  artefact); §30.14 covers whether this step may touch `dev/docs/latex/` at all.
- No Context7 lookup was possible from this agent (no MCP tools in scope). Nothing here is
  version-specific library API; the physics is derived from first principles in §30.1 and
  self-verified by test 2 rather than resting on a citation. Textbook attributions are given for
  the *convention* (Hibbeler §21.1-21.2; Stevens & Lewis ch. 1) and, for the quaternion
  kinematics already in the codebase, Wertz — the same informal prose-citation style
  `dev/docs/latex/` already uses (there is no `.bib` in this project).

---

## §30.14 LaTeX — RESOLVED, and already written

> **Status: closed. The user approved option L-a on 2026-10-25.** The LaTeX was written by the
> architect in the same pass, per the project's standing rule that the freeze on
> `dev/docs/latex/` has an explicit carve-out for an explicit user request — and this was one.
> **No further LaTeX work is in the developer's scope: do not edit `dev/docs/latex/`.**
> The record of the fork as it was put to the user is kept below for provenance.

### 30.14.1 What was written

| File | Change |
|---|---|
| **`dev/docs/latex/sections-ai/rocket-3d.tex`** | **New file.** `\section{Rocket 3D}\label{sec:rocket3d}` with seven subsections: `sec:3d_scope` (what 3D changes and what it does not), `sec:3d_attitude` (the quaternion, `eq:quat_kinematics`, `eq:quat_kinematics_components`, `eq:quat_pitch_only`, norm drift), `sec:3d_inertia` (`eq:inertia_integrals`, `eq:inertia_matrix`, the sign convention, the relation to the planar `I(t)` and `I_x`), `sec:3d_admissibility` (`eq:inertia_pd`, `eq:inertia_triangle`, `eq:inertia_ellipsoid`, `eq:inertia_transverse_bound`), `sec:3d_eom_rot` (`eq:eom_rot_3d`, `eq:eom_momentum_3d`, `eq:eom_rot_3d_expanded`, `eq:eom_rot_3d_diag`, `eq:eom_rot_3d_axisym`), `sec:3d_moment` (`eq:moment_3d`), `sec:3d_state` (`eq:state_vector_3d`) |
| `dev/docs/latex/main.tex` | Two additive changes only: `\input{sections-ai/rocket-3d}` wrapped in `aitext` (placed after `other-dynamics`, before `analysis` — 3D reads as the generalisation that follows the planar models, and this keeps `rocket-2d.tex`'s position untouched); and three new `\bibitem`s — `wertz`, `hibbeler`, `stevenslewis` |
| `sections-ai/appendix.tex` | One new **Inertia tensor** bullet in `sec:conventions`: the integral definitions, the off-diagonal minus signs, the warning that the physics-literature convention is the negative, that the body axes are not assumed principal, and the `I_yy ↔ I`, `I_xx ↔ I_x` identification |
| `sections-ai/assumptions.tex` | One new **Three-dimensional motion** item: constant tensor (no `İ·ω`), `M_y`-only moment vector, wheel taken as locked, and no 3D flight-phase machinery. The existing "Planar flight" and "Roll" items were **not** touched |
| `sections-ai/backlog.tex` | The "Model extensions for 3D" item reconciled: its lead-in now points at `sec:rocket3d` for the parts that are derived; the `mass` bullet reduced to what actually remains (time dependence, off-axis CoG, measured values); two bullets added — 3D moment arms, and the integration-harness gap named as the largest item of the group |

**`rocket-2d.tex`, `models.tex` and `other-dynamics.tex` were not touched** — L-a's own scope.
`rocket-2d.tex` in particular is author-approved (it is the one section `main.tex` does **not**
wrap in `aitext`), and `eq:eom_rot`/`eq:eom_trans`/`eq:arms` are referenced from the new section
rather than amended.

### 30.14.2 Verification performed (no toolchain available)

There is no LaTeX toolchain in this environment (`CLAUDE.md`), so the section is unrendered and the
user compiles. Checked mechanically instead:

- **24 new labels, zero collisions** against the 159 labels already in `sections-ai/*.tex`
  (368 lines added).
- **Every `\autoref` in all four touched files resolves** to a label that exists (checked by set
  difference, not by eye).
- **Every `\cite` key resolves** to a `\bibitem` in `main.tex`.
- Environments balanced, braces balanced, `$` count even, in all four files.
- `aitext` wrapping applied in `main.tex` (not inside the file), matching the convention used for
  `introduction`/`analysis`/`assumptions`/`backlog`/`appendix`.

### 30.14.3 Equation labels the implementer should cite in docstrings

Same convention as Step 109 (`task-109` §109.8). Cite the label, not the page:

| Code | Cite |
|---|---|
| `sim/inertia.py::tensor` | `eq:inertia_integrals`, `eq:inertia_matrix`; `sec:conventions` for the sign warning |
| `sim/inertia.py::validate` | `eq:inertia_pd`, `eq:inertia_triangle`, `eq:inertia_ellipsoid`, `eq:inertia_transverse_bound` |
| `sim/inertia.py::omega_dot` | `eq:eom_rot_3d`, `eq:eom_rot_3d_expanded` (and `eq:eom_rot_3d_axisym` for the reduction test) |
| `sim/params.py::Inertia` | `eq:inertia_matrix`, `sec:3d_inertia` |
| `sim/forces3d.py::moment_body_3d` | `eq:moment_3d` (and `eq:eom_rot` for the planar projection it embeds) |
| `sim/dynamics3d.py` | `eq:state_vector_3d`, `eq:quat_kinematics_components`, `eq:eom_rot_3d_expanded` |
| `tests/test_inertia.py` reduction tests | `eq:eom_rot_3d_diag`, `eq:eom_rot_3d_axisym` |

### 30.14.4 The fork as it was put to the user (historical record)

#### `decision_required` — does Step 30 write LaTeX? *(answered: L-a)*

**Purpose.** `dev/docs/roadmap.md:2246` declares Step 30 *"blocked on a `main.tex` extension of
§Equations of motion to 3D (inertia tensor, the `omega × I·omega` gyroscopic term)"*, while
`CLAUDE.md` records a standing freeze (*"LaTeX не редактировать … Правки — только по явной
просьбе"*, 2026-10-15) and `dev/status.json` carries *"Step 84: синхронизация LaTeX — отложено"*.
The user's own request was *"do the 3D implementation in sim **+ in latex**"*. Raised by the
3D-readiness proposal §5.0 and still unresolved.

**Relevant precedent, on this very branch:** Step 109's architect **did** write LaTeX
(`sections-ai/other-dynamics.tex` §Roll and four other files, `task-109` §109.8), treating the
user's explicit request as the freeze's own carve-out. So the answer is plausibly already "yes" —
but that step's request named the roll section specifically, and amending *already-approved*
sections is a different act from adding a new one.

| Option | Meaning | Blast radius |
|---|---|---|
| **L-a (recommended)** | New `dev/docs/latex/sections-ai/rocket-3d.tex`, `\input` from `main.tex`, wrapped in `aitext` per the project's AI-written convention. Sections: frames (unchanged from 2D, §30.1.1), the inertia tensor and its sign convention (§30.1.2), Euler's equations general + specialised (§30.1.3-30.1.4), admissibility and the `\|I_yy − I_zz\| ≤ I_xx` ceiling (§30.1.5), the moment vector's current `M = (0, M_y, 0)` staging (§30.4). Plus a note in `assumptions.tex` and an `appendix.tex` §conventions bullet for the product-of-inertia sign | Additive, reviewable in isolation, touches no approved section, and it satisfies Step 30's own declared blocker |
| **L-b** | L-a, **plus** amending `rocket-2d.tex` §Frames/§Mass to present 2D as the planar specialisation of 3D | Cleaner document, but edits already-approved sections — precisely what the freeze protects |
| **L-c** | No LaTeX. `sim/` implements against this ticket and the 2026-10-04 research note; LaTeX catches up with Step 84 | Zero LaTeX risk; Step 30's roadmap entry stays formally blocked, and the paper diverges further from the code |

**Note either way:** there is no LaTeX toolchain in this environment (`CLAUDE.md`), so nothing
written can be compile-verified by an agent; under L-a/L-b the user compiles.

**Recommendation: L-a.** Smallest blast radius, consistent with the Step-109 precedent, and the
only option that actually closes the roadmap's stated blocker.

**→ User chose L-a, 2026-10-25. Executed; see §30.14.1.** `dev/docs/roadmap.md`'s Step-30 blocker
(*"blocked on a `main.tex` extension of §Equations of motion to 3D (inertia tensor, the
`omega × I·omega` gyroscopic term)"*) is now satisfied: the inertia tensor is
`eq:inertia_matrix` and the gyroscopic term is `eq:eom_rot_3d`. The orchestrator should clear that
blocker line and the matching `dev/status.json` `deferred_decisions` entry.

### Two architect calls worth confirming, but not blocking

| Call | Where | If the user disagrees |
|---|---|---|
| **D-30.6** — Step 30 ships a moment vector (`M = (0, M_y, 0)`) rather than torque-free-only | §30.4.1 | Drop `moment_body_3d` and tests 16-18; the step shrinks by ~60 source + ~130 test lines but can then only be validated against itself |
| **D-30.8** — admissibility violations are a hard `ValueError`, including the sub-percent `\|I_yy − I_zz\| ≤ I_xx` ceiling | §30.8 | A warn-once variant is ~5 lines different. But a config that cannot come from a real body gives a wrong flight, and this project fails fast on nonsense input everywhere else |

---

## §30.15 Deliberately out of scope

Each with where it goes instead, so nothing here is a silent omission.

| Item | Goes to |
|---|---|
| Flying a 3D scenario end-to-end — events (ground, apogee, burnout, rail exit, parachute deploy), hold machinery, `run_sim` | **Step 30b**, the 3D integration harness. Larger than Steps 30+31+32 combined; its own approval gate (3D-readiness proposal §3.2, §5 Stage 3) |
| Freezing `dq/dt`/`domega/dt` on the rail and under the parachute (the 3D twin of `dynamics.py`'s `attitude_frozen`) | **Step 30b** — the predicates live in `integrate.py`'s event machinery, unreachable from the 3D layout today (§30.5.3) |
| Calling `inertia.validate` from a 3D run entry point | **Step 30b** — there is no 3D `run_sim` to call it from; `assemble` covers every config path that exists (§30.8.2) |
| Quaternion renormalisation strategy (per-accepted-step projection vs. solver event) | **Step 30b** (§30.6) |
| Roll moment from fin cant (`M_x`), yaw moment from sideslip (`M_z`), total `alpha` / sideslip `beta`, roll and pitch damping in 3D | **Step 31** — and independently blocked on the airframe-geometry gap that also blocks Barrowman and `c_mq` |
| Full 3D moment arms `BC`/`BD` as 3-vectors | **Step 31**, and it first needs the unresolved **Step 36** ruling on whether `l_1`/`l_2` follow `l_B(t)`. A 3D implementation has to pick a side; a fixed-arm approximation that is one error term in pitch becomes the same error term in yaw too |
| A time-varying tensor `I_body(t)` as the propellant burns, and the extra `I_dot · omega` term eq. 30.1 then acquires | **Backlog item (new).** Blocked on a 3D variable-mass model, which does not exist (the 13-component layout has no mass component). Until then §30.1.3's precondition 1 holds by construction and the tensor is honestly constant |
| Unifying `Inertia.I_yy`/`I_zz` with `Weight.I(t)`, and `Inertia.I_xx` with `Roll.I_x` | **Backlog item (new).** Today they are the same quantities in different homes, with a fail-fast cross-check for the one pair that can disagree (§30.8.3 check 4). Real unification needs the 3D mass model above |
| Deriving the tensor from geometry (`k_a · m · (d_ref/2)²`, the proposal §4.4's option B+) | **Not needed.** Superseded by the user's decision: the tensor is a direct input. The option survives as the unimplemented `model = "axisymmetric"` name (D-30.5) |
| 3D output: ground track, Euler-angle histories, 3D flight summaries | **Step 32** |
| A 3D control law (2-axis gimbal, or the reaction wheel in 3D) | A **product** decision, not architecture — route to `product`/the user |
| Committed 3D reference trajectory / numeric pins | Proposal **Stage 2** (an `rk4` shadow run), its own step (D-30.13) |
| Editing `dev/docs/latex/research/3d_equations_of_motion.md` §3 (whose "the tensor stays diagonal" is superseded) | **Resolved (D-30.17): not edited.** `sec:3d_inertia` of the new LaTeX section states the general case and says in as many words that it is a deliberate widening of that note's symmetry argument, which supersedes it without rewriting the user's sign-off artefact |
| **Any further LaTeX work** | **None — already done** (§30.14.1, D-30.15). `dev/docs/latex/` is read-only for the developer on this ticket |

---

## §30.16 Definition of done

1. `sim/inertia.py` exists with `tensor`, `validate`, `omega_dot`, each docstring'd in this
   project's style and citing `task-30-3d-rotational-dynamics.md` §§30.1-30.3 by anchor.
2. `sim/params.py` has the `Inertia` group (§30.2.3 verbatim, including the sign-convention and
   `Weight.I` paragraphs) and `Params.inertia`.
3. `sim/forces3d.py` has `moment_body_3d`; `sim/dynamics.py` has the extracted `pitch_moment` and
   calls it from the one place that used to inline it.
4. `sim/dynamics3d.py`'s `dydt[Q]`/`dydt[OMEGA]` are real (§30.5.1), and its module docstring no
   longer claims attitude is held fixed.
5. `sim/state3d.py`'s module docstring no longer claims `dq/dt = 0`, `domega/dt = 0` identically.
6. `configs/schema.py` and `configs/rockets/_TEMPLATE_rocket.py` are wired per §30.7, and
   `tests/test_config_pieces.py::test_assemble_params_call_keyword_set_equals_params_fields_exactly`
   passes.
7. `tests/test_inertia.py` exists with tests 1-14; `tests/test_dynamics3d.py` has tests 15-20 and
   its three stale comments corrected.
8. Test 2 (the point-mass convention check) and test 19 (inertial angular-momentum conservation)
   both pass — if either is skipped or weakened, the ticket is not done.
9. **Full suite green** (`python -m pytest -q`, `run_in_background`, ~220 s) with **zero changed
   numbers outside `tests/test_inertia.py` and `tests/test_dynamics3d.py`**. If any
   `tests/test_integrate.py` RK45 pin moves, **stop and escalate — do not re-pin** (D-77).
10. `code-review` skill run before QA (`CLAUDE.md` skills table), with the §30.1.2 sign convention
    and the §30.11.1 extraction guard rails as named review targets.
11. **No `dev/docs/latex/` file touched by the developer.** The LaTeX is already written (§30.14.1,
    D-30.15) — `rocket-3d.tex` plus four small additive edits. The developer's obligation here is
    only to **cite** it: every new docstring names the equation labels of §30.14.3, so the code and
    the paper stay cross-referenced. A docstring that re-derives the physics in prose instead of
    citing a label is a review finding.
12. Two new backlog items recorded (time-varying 3D tensor; `Inertia`/`Weight`/`Roll` unification) —
    `dev/docs/backlog.md`, by the orchestrator, not the developer.

---

## §30.17 Ticket block

### [STEP-30] 3D rotational dynamics with a full symmetric inertia tensor

- **Module/boundaries:** `sim/inertia.py` (new), `sim/params.py` (the new `Inertia` group +
  `Params.inertia` only), `sim/forces3d.py`, `sim/dynamics3d.py`, `sim/state3d.py` (docstring only),
  `sim/dynamics.py` (**the `pitch_moment` extraction only** — no other line), `configs/schema.py`
  (import + `Rocket.inertia` + `assemble` keyword + validate call only),
  `configs/rockets/_TEMPLATE_rocket.py`, `tests/test_inertia.py` (new),
  `tests/test_dynamics3d.py`. **Do not touch** `sim/state.py`, `sim/integrate.py`, `sim/roll.py`,
  `sim/mass.py`, `dev/docs/latex/**` (already written, §30.14.1 — read it, cite it, do not edit
  it), or any tracker file.
- **Assignee:** developer
- **depends_on:** `[STEP-109]` — Step 109 must be landed and committed first (§30.0.3): same
  regions of `sim/params.py`, `configs/schema.py`, `configs/rockets/_TEMPLATE_rocket.py` and
  `sim/dynamics.py`, **and** §30.8.3 check 4 reads `Roll.I_x`, which does not exist without it.
- **parallel_safe:** false
- **Spec slice needed:** this file. Read §30.0-30.1 in full first (the physics and the sign
  convention — do not start coding from §30.3 alone), then §30.2-30.8 as the file-by-file plan,
  §30.9-30.11 for tests and pin safety. §30.12-30.15 are context, not instructions. Do **not** read
  `dev/docs/architecture*.md` or `dev/docs/roadmap.md` for this ticket — everything needed is here.
  Supporting reads, in this order and only these: `sim/dynamics3d.py` (54 lines, whole),
  `sim/forces3d.py` (124 lines, whole), `sim/state3d.py` (61 lines, whole),
  `sim/quaternion.py:183-197` (`q_dot`), `sim/dynamics.py:320-360` (the moment assembly to be
  extracted), `sim/params.py:281-345` (the `Roll` group as the template to copy, and `Params`),
  `configs/schema.py:273-310` and `:357-400` (`Rocket` and `assemble`),
  `tests/test_dynamics3d.py` (131 lines, whole), and
  `dev/docs/latex/sections-ai/rocket-3d.tex` (368 lines, whole — the same physics as §30.1 in the
  paper's own notation; read it for the equation labels you must cite, per §30.14.3, and **do not
  edit it**).
- **Skills:** `tdd` (mandatory — tests before code; write test 2 first, it is the one that proves
  the convention), `code-review` before QA. `diagnosing-bugs` if a conservation test fails — do
  **not** loosen a conservation tolerance to make it pass, a failing conservation check means a
  sign is wrong.

Implement §30.2-30.8 exactly as specified. The three places where "stop and escalate" applies
rather than deciding yourself: (a) any `tests/test_integrate.py` pin moves; (b) the
`dynamics.pitch_moment` extraction needs anything beyond the locals already in scope at
`sim/dynamics.py:353-356`; (c) a conservation test (13 or 19) cannot be made to pass without
loosening its tolerance.




