# TASK-TBD — Point-mass flight-path-angle rate (gravity turn): paper note + simplified model

Step/stage number to be assigned by the orchestrator (`task-NNN-point-mass-flight-path-angle.md`).
Phase 2.17 (paper-alignment) candidate.

## Кратко (RU)

- Пользователь попросил добавить «упрощённую вращательную динамику `dtheta/dt = -g*cos(gamma)/V`» —
  и в LaTeX, и в код. Это **не** вращательная динамика: это уравнение скорости изменения угла
  наклона траектории (gravity turn) для точечной массы без подъёмной силы и без инерции вращения.
- Главная находка: `theta` в проекте — тангаж корпуса, `gamma` — угол крена (Step 109, `\gamma_r` в
  статье), а `\chi` — азимут полёта. Все три символа заняты. Угла наклона траектории в проекте
  **нет вообще** — ни в коде, ни в таблице обозначений статьи, хотя `analysis.tex:178` уже ссылается
  на него словами.
- Рекомендуемое обозначение — **`\theta_v`** (угол вектора скорости от `\hat{x}_0`), а не `\gamma_v`:
  `\gamma_r` (крен) и `\gamma_v` отличались бы одной буквой индекса при совершенно разном смысле.
  Решение за пользователем (D-1).
- Знак выходит **без переворота**: в конвенции статьи (`\hat{z}_0` вниз) при `\theta_v>0` на подъёме
  получается ровно `\dot\theta_v = -(g/V)\cos\theta_v`.
- Проверено аналитически: `\alpha = \theta_r - \theta_v` точно совпадает с тем, что считает
  `flow.py` (`atan2(w,u)`) в безветрие. Это даёт строгую замену голословному «flight-path angle
  changes slowly»: точное уравнение имеет невязку `-(\ddot\theta_v + M_q\dot\theta_v)`, критерий
  малости — `\Lambda = g/(V\omega_n) \ll 1`.
- Код: три варианта (новый модуль `apps/analysis/point_mass/`, диагностика поверх существующей
  траектории, или оба). Рекомендация — вариант C, начиная с диагностики. Нужно решение (D-2).
- Риск для числовых пинов — нулевой при любом варианте: `apps/sim/engine/` не трогается.

## Contents

- [1. What the user asked for, and what it actually is](#1-what-the-user-asked-for-and-what-it-actually-is)
- [2. Notation audit — what is already taken](#2-notation-audit--what-is-already-taken)
- [3. D-1 — symbol for the flight-path angle (DECISION REQUIRED)](#3-d-1--symbol-for-the-flight-path-angle-decision-required)
- [4. Derivation, in this paper's conventions](#4-derivation-in-this-papers-conventions)
- [5. Making "changes slowly" rigorous](#5-making-changes-slowly-rigorous)
- [6. Draft LaTeX text (do not apply yet)](#6-draft-latex-text-do-not-apply-yet)
- [7. D-2 — code scope (DECISION REQUIRED)](#7-d-2--code-scope-decision-required)
- [8. Ticket draft](#8-ticket-draft)
- [9. Decisions needed before implementation](#9-decisions-needed-before-implementation)
- [10. Side findings](#10-side-findings)

---

## 1. What the user asked for, and what it actually is

The request, verbatim: add "the simplified rotational dynamics of `dtheta/dt = -g*cos(gamma)/V`".

**This is not rotational dynamics.** It is the flight-path-angle rate equation of a *point-mass*
gravity turn: zero lift, thrust aligned with the velocity vector, flat non-rotating Earth. It
describes how the **velocity vector** rotates under gravity. It contains no moment, no moment of
inertia, no angle of attack and no pitch rate.

Three distinct physical quantities are in play, and the user's one-line equation mixes the names of
all three:

| Quantity | What it is | In this project |
|---|---|---|
| Pitch attitude | angle of the **nose axis** `x̂_r` above horizontal | `State.theta`, paper `\theta_r`; driven by the full moment equation `eq:eom_rot` |
| Roll angle | rotation about the nose axis `x̂_r` | `State.gamma` (Step 109), paper `\gamma_r` |
| **Flight-path angle** | angle of the **velocity vector** above horizontal | **does not exist** — not a state, not computed, not in the notation table |

So the equation is **not** a refinement, correction or drop-in replacement for the existing
rotational EOM. It is a *different and cruder model* of the whole vehicle (point mass, no rotational
degree of freedom at all), useful for fast closed-form estimates and for justifying an
approximation the paper already leans on. The existing rigid-body path must not change.

### The existing hook in the paper

`analysis.tex:177-179` (short-period / dynamic stability) currently asserts, in prose and without
justification:

> "In the short-period approximation the flight-path angle changes slowly over one oscillation, so
> $\mathrm{d}\alpha/\mathrm{d}t\approx\omega_r$"

That sentence (a) names the flight-path angle without ever defining a symbol for it, and (b) asserts
"changes slowly" with nothing behind it. The user's equation is **exactly the missing quantitative
justification** for that claim — see [section 5](#5-making-changes-slowly-rigorous). This is the
strongest argument for adding the note: it closes an existing gap rather than bolting on a new topic.

---

## 2. Notation audit — what is already taken

Grepped across `dev/docs/latex/sections-ai/*.tex` and cross-checked against the authoritative
notation table (`appendix.tex:2-126`, `\label{sec:notation}`).

| Symbol | Already means | Where |
|---|---|---|
| `\theta_r` | pitch angle of the body, from `\hat{x}_0`, positive nose-up | `rocket-2d.tex:18`, `appendix.tex:91` |
| `\theta_t` | thrust-line angle from `\hat{x}_r` (misalignment) | `rocket-2d.tex:41`, `appendix.tex:36` |
| `\gamma_r` | **roll angle** about `+\hat{x}_r` | `other-dynamics.tex:214-215`, `eq:roll_kinematics` |
| `\gamma_0`, `\gamma_e` | Somigliana **normal gravity** (WGS84) | `models.tex:24`, `appendix.tex:204` |
| `\chi` | **flight azimuth** (Euler's radius-of-curvature formula) | `models.tex:73-79`, `assumptions.tex:6` |
| `\varphi` | downrange **arc angle** `x/R_e` | `models.tex:103`, `analysis.tex:8` |
| `\phi` / `\psi` | geodetic / geocentric **latitude** | `models.tex:65-66` |
| `\vartheta` | geodetic-latitude **change along track** | `models.tex:68` |
| `\alpha` | angle of attack | `appendix.tex:84` |
| `\zeta`, `\omega_n` | short-period damping ratio, natural frequency | `analysis.tex:185` |
| `\varepsilon_r`, `\omega_r` | pitch acceleration, pitch rate | `rocket-2d.tex:19` |

Conclusions:

1. **The flight-path angle has no symbol at all** in this paper. Nothing to reuse; a new one must be
   introduced, and it must go into the `sec:notation` table.
2. **Bare `\gamma` is free**, but `\gamma` is already carrying two unrelated meanings via subscripts
   (roll `\gamma_r`, normal gravity `\gamma_0/\gamma_e`).
3. **`\chi` is taken** (flight azimuth) — the second collision the task warned about is real; do not
   propose it.
4. The paper's own subscript discipline is consistent: `\theta` + a subscript naming *what the angle
   belongs to* (`_r` rocket body, `_t` thrust line).

---

## 3. D-1 — symbol for the flight-path angle (DECISION REQUIRED)

Paper-facing notation in a physics document — not mine to pick silently.

### Option A — `\theta_v` (RECOMMENDED)

"Angle of the **v**elocity vector", measured from `\hat{x}_0`, positive climbing.

- **Pros:** fits the paper's existing discipline exactly (`\theta_r` body, `\theta_t` thrust line,
  `\theta_v` velocity vector). Measured from the **same reference axis** as `\theta_r`, so the
  central relation `\alpha = \theta_r - \theta_v` is immediate and self-evidently dimensionally and
  geometrically right. The velocity unit vector is then *literally* `eq:body_axes_in_ground` with
  `\theta_r \to \theta_v`, so the whole derivation reuses machinery already on the page. Does not add
  a third meaning to `\gamma`.
- **Cons:** `\gamma` is the universal textbook symbol for flight-path angle (Vinh, Zipfel, Anderson);
  an external reader expects `\gamma` and may briefly stumble. Mitigated by one parenthetical in the
  text and a row in `sec:notation`.

### Option B — `\gamma_v`

- **Pros:** keeps the textbook letter `\gamma`; `_v` disambiguates from roll.
- **Cons:** **`\gamma_r` (roll) and `\gamma_v` (flight-path) would differ by a single subscript letter
  while being completely unrelated quantities** — the most confusable possible pairing, and far worse
  than the `\theta_r`/`\theta_v` pairing, where the two *are* the same kind of angle from the same
  axis and their difference is exactly `\alpha` (a benign, even instructive, proximity). Also makes
  `\gamma` carry three meanings (roll, normal gravity, flight-path).

### Option C — bare `\gamma`

- **Pros:** maximal textbook familiarity, shortest.
- **Cons:** sits one subscript away from `\gamma_r` (roll) and `\gamma_0` (normal gravity) **in the
  same document**; the code's `State.gamma` already means roll, so paper and code would use the same
  letter for two different things — the precise failure this task was raised to avoid.

**Recommendation: Option A, `\theta_v`**, with an explicit note on first use ("the flight-path angle,
conventionally $\gamma$; written $\theta_v$ here because $\gamma_r$ is the roll angle of
\autoref{sec:roll}") plus a `sec:notation` row. Rationale in one line: it is the only option that
adds no visually-confusable near-twin to an existing symbol, and it makes
`\alpha = \theta_r - \theta_v` a one-glance identity.

---

## 4. Derivation, in this paper's conventions

Frame recap (`rocket-2d.tex:9-12`): `\mathcal{F}_0` has `\hat{x}_0` horizontal downrange and
**`\hat{z}_0` DOWN**; altitude is `-z`. A climbing rocket therefore has `v_z < 0`.

### 4.1 Definition (sign convention resolved)

Define `\theta_v` positive-climbing, mirroring `eq:body_axes_in_ground`:

```
x̂_v = cos θ_v x̂_0 − sin θ_v ẑ_0        (unit vector along the velocity)
ẑ_v = sin θ_v x̂_0 + cos θ_v ẑ_0        (normal to it, completing the pair)
v   = V x̂_v ,   i.e.  v_x = V cos θ_v ,  v_z = −V sin θ_v
θ_v = atan2(−v_z, v_x)
```

Check: climbing (`v_z<0`) gives `θ_v>0`. Correct, and `x̂_v`/`ẑ_v` are exactly `x̂_r`/`ẑ_r` with
`θ_r → θ_v`, so the pair is orthonormal by the same algebra already in the paper.

### 4.2 Kinematics

Differentiating `v = V x̂_v`, and using `d/dt(x̂_v) = −\dot θ_v ẑ_v`:

```
a = V̇ x̂_v − V θ̇_v ẑ_v
```

### 4.3 Point-mass assumptions

Taken explicitly (these are the whole content of the "simplified" model):

- **A1** no lift / no aerodynamic normal force: the only aero force is drag `D`, antiparallel to `v`;
- **A2** thrust aligned with the velocity vector, `T x̂_v` (so `θ_t = 0` *and* `α = 0`);
- **A3** flat, non-rotating Earth: `ẑ_g = ẑ_0` (i.e. `φ = 0`), `g` constant, no Coriolis;
- **A4** no rotational degree of freedom at all — `I`, `C_m`, `ω_r` do not appear;
- **A5** still air, so the path speed equals the airspeed: `V = v_rel` (the paper's symbol for
  airspeed is `v_{rel}`, `sec:relwind`; `V` is introduced here for the point-mass path speed and the
  two coincide only under A5).

Then `m a = mg ẑ_0 + (T − D) x̂_v`.

### 4.4 Projection

`ẑ_0 · ẑ_v = cos θ_v` and `x̂_v · ẑ_v = 0`. Projecting onto `ẑ_v`:

```
m(−V θ̇_v) = mg cos θ_v
```

**⟹ `θ̇_v = −(g/V) cos θ_v`**

**The sign comes out correct with no flip**, in the paper's `ẑ_0`-down convention, given the
positive-climbing definition of 4.1. No convention adjustment is needed — this answers the sign
question in the task directly.

Projecting onto `x̂_v` gives the companion equation (worth stating, it completes the model):

```
m V̇ = T − D − mg sin θ_v
```

### 4.5 Sanity checks

| Case | Result | Correct? |
|---|---|---|
| Level flight, `θ_v = 0` | `θ̇_v = −g/V < 0` → immediately starts descending | yes |
| Straight up, `θ_v = 90°` | `cos θ_v = 0` → `θ̇_v = 0`; gravity purely decelerates, does not turn | yes — this *is* the gravity-turn property |
| Vertical dive, `θ_v = −90°` | `θ̇_v = 0` → stays vertical (attracting state) | yes |
| High speed | `|θ̇_v| ∝ 1/V` → fast vehicles turn less per second | yes |

### 4.6 Closed form (constant `V`)

With `V` held constant, `dθ_v/cos θ_v = −(g/V)dt` integrates via `∫ sec θ dθ = ln|tan(π/4 + θ/2)|`:

```
tan(π/4 + θ_v/2) = tan(π/4 + θ_v0/2) · exp(−g t / V)
```

So `θ_v → −90°` asymptotically: the classic gravity turn, with time constant `V/g`. This closed form
is the natural test oracle for the code side (cf. existing `tests/test_analytic.py`).

### 4.7 Relation to the existing model — verified against the code

In still air, with `α` as the code defines it (`flow.py:86`, `alpha = atan2(w, u)` on the body-frame
relative-velocity components):

```
u = v·x̂_r = V cos(θ_r − θ_v)
w = v·ẑ_r = V sin(θ_r − θ_v)
⟹ α = atan2(w, u) = θ_r − θ_v
```

**`α = θ_r − θ_v` exactly**, matching the code's own `atan2` convention. This is the bridge between
the cruder model and the existing rigid-body one, and it is what makes section 5 possible.

Caveat to state in the paper: `θ_v` as defined is the **inertial (ground-referenced)** flight-path
angle, while `α` is referenced to the **relative wind**. The identity `α = θ_r − θ_v` therefore holds
in still air; with wind, `θ_v` must be the air-relative flight-path angle. In code, the two routes
(`atan2(-vz, vx)` vs `theta - alpha`) differ by exactly the wind contribution — a free consistency
check.

---

## 5. Making "changes slowly" rigorous

This is the part that upgrades `analysis.tex:177-179` from assertion to result.

From `α = θ_r − θ_v`: `\dot α = ω_r − \dot θ_v` and `\ddot α = ε_r − \ddot θ_v`.

The paper's linearised moment (`analysis.tex:168-176`) is `ε_r = M_α α − M_q ω_r`. Substituting
`ω_r = \dot α + \dot θ_v` and `ε_r = \ddot α + \ddot θ_v`:

```
\ddot α + M_q \dot α − M_α α = −( \ddot θ_v + M_q \dot θ_v )        (EXACT)
```

The paper's eq. (181) is this equation **with the right-hand side dropped**. So the approximation is
not "dα/dt ≈ ω_r" hand-waved — it is a named forcing term with a computable magnitude:

- `|\dot θ_v| = (g/V)|cos θ_v| ≤ g/V`
- `\ddot θ_v = (g/V) sin θ_v \dot θ_v + (g \dot V / V²) cos θ_v`, i.e. `O((g/V)² + g|\dot V|/V²)`

The dominant neglected term is `M_q \dot θ_v`. Comparing it with the retained stiffness term
`M_α α ~ ω_n² \hat α` (oscillation amplitude `\hat α`), and using `M_q = 2ζω_n`:

Define the **flight-path-to-short-period rate ratio**

```
Λ ≡ (g/V) / ω_n = g / (V √(−M_α))
```

Then the short-period approximation is valid when

```
2 ζ Λ ≪ \hat α        (dominant, from the M_q \dot θ_v term)
Λ² ≪ \hat α           (subdominant, from \ddot θ_v)
```

i.e. **`Λ ≪ 1`** as the headline criterion. Equivalently, in the form that matches the paper's own
words ("changes slowly over one oscillation"): over one short period `T_n = 2π/ω_n` the flight-path
angle drifts by at most

```
Δθ_v ≤ (g/V) · T_n = (g/V)(2π/ω_n) = 2π Λ
```

which must be small against the oscillation amplitude `\hat α`.

**Illustrative numbers** (plausible values, NOT this project's airframe — see acceptance criteria):
`V = 150 m/s`, `ω_n = 10 rad/s`, `ζ = 0.1`, `\hat α = 5° = 0.087 rad`
→ `Λ = 9.81/(150·10) = 6.5×10⁻³`; `2ζΛ = 1.3×10⁻³` vs `0.087` → the neglected forcing is ~1.5 % of
the retained term. Approximation good.

Low speed just off the rail, `V = 30 m/s`, `ω_n = 5 rad/s`
→ `Λ = 6.5×10⁻²`, `2ζΛ = 1.3×10⁻²` vs `0.087` → ~15 %. **Marginal** — the short-period approximation
is weakest exactly where the rail and early boost live.

Two honest caveats to carry into the text:

- The criterion **degrades as `V → 0`** (`Λ ∝ 1/V`): low speed off the rail, and near apogee of a
  lofted trajectory.
- Near-vertical flight partially rescues it, because `cos θ_v → 0` makes `\dot θ_v` small
  independently of `V`; at the apogee of a near-vertical shot both `V → small` and `cos θ_v → 0`, so
  the product is indeterminate and no general claim should be made there.

This is a genuine strengthening of the paper: it gives the reader a number to check rather than an
adjective.

---

## 6. Draft LaTeX text (do not apply yet)

**Do not write this into `analysis.tex` yet** — a concurrent developer task is editing that file near
line 159 (the `C_m`/`C_m_code` notation fix), and `rocket-2d.tex` is also freshly touched. Apply only
after that lands, and after D-1 is settled (every `\theta_v` below changes if D-1 picks another
symbol).

Placement: a new `\subsection` in `analysis.tex` **immediately before** `sec:analysis_dynamic`
(so the short-period discussion can `\autoref` it), plus a 2-3 line edit inside
`sec:analysis_dynamic` replacing the bare assertion at lines 177-179.

### 6.1 New subsection (insert before `\subsubsection{Dynamic stability}`)

```latex
\subsection{Flight-path angle and the point-mass gravity turn}\label{sec:analysis_flightpath}
Everything above tracks the \emph{nose} direction $\theta_r$. The trajectory itself is set by the
\emph{velocity} direction, and the two differ by the angle of attack. Define the flight-path angle
$\theta_v$, the angle of $\vec{v}_r$ above the horizon (conventionally written $\gamma$; here
$\theta_v$, since $\gamma_r$ is the roll angle of \autoref{sec:roll}), by the same construction as
\autoref{eq:body_axes_in_ground}:
\begin{equation}\label{eq:vel_axes_in_ground}
    \hat{x}_v = \cos\theta_v\,\hat{x}_0 - \sin\theta_v\,\hat{z}_0, \qquad
    \hat{z}_v = \sin\theta_v\,\hat{x}_0 + \cos\theta_v\,\hat{z}_0, \qquad
    \vec{v}_r = V\hat{x}_v,
\end{equation}
so that $v_x=V\cos\theta_v$, $v_z=-V\sin\theta_v$ and $\theta_v=\operatorname{atan2}(-v_z,v_x)$:
positive climbing, since $\hat{z}_0$ points down. In the pitch plane and in still air the three
angles close exactly,
\begin{equation}\label{eq:alpha_closure}
    \alpha = \theta_r - \theta_v,
\end{equation}
which is the simulator's $\alpha=\operatorname{atan2}(v_{rel,z},v_{rel,x})$ of
\autoref{sec:relwind} written in ground-frame terms. With wind, $\theta_v$ in
\autoref{eq:alpha_closure} is the air-relative flight-path angle.

\paragraph{The point-mass limit.} Strip the airframe of its rotational degree of freedom: no
aerodynamic normal force, thrust along the velocity vector ($\theta_t=0$ and $\alpha=0$, so
$\hat{x}_v=\hat{x}_r$), a flat non-rotating Earth ($\hat{z}_g=\hat{z}_0$, $\varphi=0$), still air
(so the path speed is the airspeed, $V=v_{rel}$) and drag $D$
antiparallel to $\vec{v}_r$. Then \autoref{eq:eom_trans} reduces to
$m\vec{a}_r = mg\hat{z}_0 + (T-D)\hat{x}_v$, while differentiating
\autoref{eq:vel_axes_in_ground} gives
\begin{equation}\label{eq:accel_in_vel_axes}
    \vec{a}_r = \dot{V}\hat{x}_v - V\dot\theta_v\,\hat{z}_v .
\end{equation}
Projecting on $\hat{z}_v$, where $\hat{z}_0\cdot\hat{z}_v=\cos\theta_v$ and weight is the only
contributor, and on $\hat{x}_v$:
\begin{gather}
    \dot\theta_v = -\frac{g}{V}\cos\theta_v, \label{eq:flightpath_rate}\\
    m\dot{V} = T - D - mg\sin\theta_v. \label{eq:speed_rate}
\end{gather}
\autoref{eq:flightpath_rate} is the \emph{gravity turn}: gravity alone bends the velocity vector, at
a rate $g/V$ modulated by $\cos\theta_v$. It vanishes when the flight is vertical
($\theta_v=\pm90^\circ$), where gravity is purely decelerating and turns nothing, and is largest
when level, $\dot\theta_v=-g/V$. A faster rocket turns less per unit time --- the reason a high
thrust-to-weight launch holds its initial attitude. Holding $V$ fixed, \autoref{eq:flightpath_rate}
integrates to
\begin{equation}\label{eq:gravity_turn_closed}
    \tan\!\left(\frac{\pi}{4}+\frac{\theta_v}{2}\right)
        = \tan\!\left(\frac{\pi}{4}+\frac{\theta_{v,0}}{2}\right) e^{-gt/V},
\end{equation}
so $\theta_v\to-90^\circ$ with time constant $V/g$.

This is a \emph{cruder} model than \autoref{eq:eom_trans}--\autoref{eq:eom_rot}, not a refinement of
them: it carries no moment, no inertia and no angle of attack, and the simulator never integrates it.
Its uses are the two below --- a closed-form estimate to check the integrator against, and the
justification of the short-period approximation that follows.
```

### 6.2 Replacement for the assertion at `analysis.tex:177-179`

Current text: *"In the short-period approximation the flight-path angle changes slowly over one
oscillation, so $\mathrm{d}\alpha/\mathrm{d}t\approx\omega_r$ and"*. Proposed replacement:

```latex
$M_\alpha$ is negative for a statically stable airframe and $M_q$ is positive for $C_{m,q}>0$.
Eliminating $\theta_r$ in favour of $\alpha$ through \autoref{eq:alpha_closure}
($\omega_r=\dot\alpha+\dot\theta_v$, $\varepsilon_r=\ddot\alpha+\ddot\theta_v$) turns
$\varepsilon_r=M_\alpha\alpha-M_q\omega_r$ into an exact statement,
\begin{equation}\label{eq:short_period_exact}
    \ddot\alpha + M_q\dot\alpha - M_\alpha\alpha
        = -\left(\ddot\theta_v + M_q\dot\theta_v\right),
\end{equation}
whose right-hand side is the entire content of the short-period approximation: dropping it gives
\begin{equation}
    \frac{\mathrm{d}^2\alpha}{\mathrm{d}t^2} + M_q\frac{\mathrm{d}\alpha}{\mathrm{d}t} - M_\alpha\alpha = 0,
\end{equation}
with natural frequency and damping ratio
\begin{equation}
    \omega_n = \sqrt{-M_\alpha}, \qquad \zeta = \frac{M_q}{2\omega_n} = \frac{M_q}{2\sqrt{-M_\alpha}},
\end{equation}
valid only for $M_\alpha<0$; otherwise the disturbance grows rather than oscillates.

\autoref{eq:flightpath_rate} makes the dropped term quantitative instead of merely ``slow''. With
$|\dot\theta_v|\le g/V$ and $\ddot\theta_v=O\!\left((g/V)^2+g\dot V/V^2\right)$, the dominant
neglected term is $M_q\dot\theta_v=2\zeta\omega_n\dot\theta_v$. Measuring it against the retained
stiffness $M_\alpha\alpha\sim\omega_n^2\hat\alpha$ for an oscillation of amplitude $\hat\alpha$, and
writing
\begin{equation}\label{eq:flightpath_ratio}
    \Lambda \equiv \frac{g/V}{\omega_n} = \frac{g}{V\sqrt{-M_\alpha}},
\end{equation}
the approximation holds when $2\zeta\Lambda\ll\hat\alpha$ and $\Lambda^2\ll\hat\alpha$ --- in short,
$\Lambda\ll1$: the flight-path angle must drift through much less than the oscillation amplitude in
one short period, $\Delta\theta_v\approx2\pi\Lambda\ll\hat\alpha$. Since $\Lambda\propto1/V$, the
approximation is at its weakest at low airspeed --- on and just off the rail, and near the apogee of
a lofted flight --- and strongest through the high-$q$ part of the boost. Near-vertical flight
relaxes it independently of speed, because $\cos\theta_v\to0$ suppresses $\dot\theta_v$ directly.
```

### 6.3 Notation-table rows (`appendix.tex`, `sec:notation`)

Add to the **States and integration** block (or a new row near `$\alpha$` in *Atmosphere and wind*):

```latex
$\theta_v$ & not implemented (derivable: \texttt{atan2(-vz, vx)}, or \texttt{theta - alpha} in still air) & flight-path angle, velocity vector above the horizon & rad \\
$\hat{x}_v$, $\hat{z}_v$ & --- & velocity-axis unit vectors (\autoref{eq:vel_axes_in_ground}) & --- \\
$V$ & \texttt{flow.V} (air-relative $v_{rel}$); $|\vec{v}_r|$ inertially & point-mass path speed; $V=v_{rel}$ in still air & m/s \\
```

And to the **Analysis** block:

```latex
$\Lambda=(g/V)/\omega_n$ & --- & flight-path drift rate against the short-period frequency & --- \\
```

Also extend the closing "some letters carry two meanings" note (`appendix.tex:121-125`) to record
that `\theta` now carries three subscripted meanings (`_r` body pitch, `_t` thrust line, `_v`
velocity direction), and that the conventional `\gamma` for flight-path angle is deliberately *not*
used because `\gamma_r` is roll.

### 6.4 Assumptions section

`assumptions.tex` should gain a line noting that the point-mass gravity turn of
`eq:flightpath_rate` is an **analysis-only** model under A1-A4 above, never integrated by the
simulator — so the reader cannot mistake it for part of the simulated physics.

---

## 7. D-2 — code scope (DECISION REQUIRED)

The user said "both" (docs + code), but "code" has three defensible shapes, and one of them is
probably not what they pictured. Not mine to decide silently — this is product scope.

Common ground in all three options: **nothing under `apps/sim/engine/` is touched**, so the numeric
pins carry **zero** risk. A new `State` component or a new `p.solver.method` variant is explicitly
**rejected** — see [8.4](#84-explicitly-out-of-scope).

### Option A — new standalone analytic module `apps/analysis/point_mass/`

A small, self-contained closed-form propagator: integrate `eq:flightpath_rate` + `eq:speed_rate`
(or evaluate the closed form `eq:gravity_turn_closed`) for fast trade-study estimates, following the
existing `apps/analysis/cfd_conditions/` and `apps/analysis/ensemble/` precedent.

- **Pros:** matches the user's literal words ("a new code path/mode"); genuinely useful for
  order-of-magnitude work (burnout flight-path angle, gravity-turn losses) in microseconds instead of
  a full integration; a clean test oracle via `eq:gravity_turn_closed`.
- **Cons:** a second, cruder trajectory model in the tree invites "which one is right?" confusion;
  needs its own docstring discipline about being analysis-only; of the three, the least connected to
  the paper gap that motivated the request.
- **Cost:** ~1 module + 1 test file; no engine change.

### Option B — diagnostic over the existing trajectory (RECOMMENDED as the first slice)

Compute, from an already-simulated run, the **actual** `θ_v(t) = atan2(-vz, vx)`, the actual
`\dot θ_v`, the point-mass prediction `-(g/V)cos θ_v`, and the validity ratio `Λ(t)`; expose them via
`apps/_shared/flight_stats.py` and optionally a plot panel.

- **Pros:** directly closes the paper gap — turns `analysis.tex`'s asserted "changes slowly" into a
  **measured, plotted result for the user's own airframe**, which is exactly what the paper's
  `\restodo` culture wants. Also answers a question the full model cannot answer about itself: *where
  in this flight does the point-mass approximation hold?* Smallest surface, read-only over existing
  outputs, no new model in the tree. Supplies the real numbers that section 5's illustrative figures
  currently stand in for.
- **Cons:** not a "new simulation mode" — if the user specifically wanted a runnable simplified
  propagator, this alone does not deliver it.
- **Cost:** ~1 function + stats/plot wiring + 1 test file.

### Option C — both A and B (RECOMMENDED overall, B first)

B lands the paper value and the validation; A then adds the standalone estimator on top, reusing B's
verified `θ_v` helper.

- **Pros:** fully satisfies "both"; natural ordering, since B's helper is A's building block.
- **Cons:** roughly double the work of either; A's value should be confirmed against a real use case
  before building it.
- **Cost:** two steps rather than one.

**Recommendation: Option C, sequenced B → A, with A gated on the user confirming they want a
runnable simplified propagator** (and on *what question* it should answer — see D-4).

---

## 8. Ticket draft

Numbering `TBD-1`/`TBD-2` until the orchestrator assigns step numbers.

### [TBD-0] Paper: flight-path angle and the point-mass gravity turn

- **Module/boundaries:** `dev/docs/latex/sections-ai/analysis.tex` (new subsection before
  `sec:analysis_dynamic`; replacement of lines 177-179), `dev/docs/latex/sections-ai/appendix.tex`
  (`sec:notation` rows + the two-meanings note), `dev/docs/latex/sections-ai/assumptions.tex`
  (one line). **No code.**
- **Assignee:** developer (LaTeX-only; note the project rule that `dev/docs/latex/` is
  edit-on-explicit-request — this ticket *is* that explicit request, scoped to these insertions)
- **depends_on:** [D-1 resolved, concurrent `C_m` fix in `analysis.tex` merged]
- **parallel_safe:** false — overlaps the concurrent `analysis.tex` edit
- **Spec slice:** this file, sections [4](#4-derivation-in-this-papers-conventions),
  [5](#5-making-changes-slowly-rigorous), [6](#6-draft-latex-text-do-not-apply-yet). Section 6 is
  paste-ready once D-1 is confirmed.

Apply section 6 verbatim, substituting the D-1 symbol throughout if it is not `\theta_v`. Do not
recompute the derivation; do verify every `\autoref` target exists before committing:
`eq:body_axes_in_ground` (`rocket-2d.tex:20`), `eq:eom_trans` (`rocket-2d.tex:88`), `eq:eom_rot`
(`rocket-2d.tex:95`), `sec:roll` (`other-dynamics.tex:210`), `sec:relwind` (`models.tex:333`) —
all five **verified present** during this scoping pass.

### [TBD-1] Diagnostic: flight-path angle + point-mass validity over a simulated run (Option B)

- **Module/boundaries:** `apps/_shared/flight_stats.py` (additive), optionally
  `apps/sim/engine/plotting.py` (one new panel — *the only engine-directory file touched, and
  plotting only, no physics*), `tests/test_point_mass_flightpath.py` (new)
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true — additive to `flight_stats.py`; no overlap with the LaTeX tickets. Becomes
  `false` if any other live ticket edits `flight_stats.py` or `plotting.py`.
- **Spec slice:** sections [4.1](#41-definition-sign-convention-resolved),
  [4.7](#47-relation-to-the-existing-model--verified-against-the-code),
  [5](#5-making-changes-slowly-rigorous) of this file.

Provide, over an existing simulation result:

1. `theta_v(t) = atan2(-vz, vx)` — inertial flight-path angle, rad, positive climbing;
2. `theta_v_dot_actual(t)` — numerically differentiated, or exactly from the known `a_i`;
3. `theta_v_dot_pointmass(t) = -(g / V) * cos(theta_v)` — the prediction of `eq:flightpath_rate`;
4. `lambda_ratio(t) = (g / V) / omega_n` where `omega_n = sqrt(-M_alpha)` is available, else `None`;
5. the still-air consistency residual `theta - alpha - theta_v`, which must be ~0 with wind off.

Follow `tdd`: tests before implementation.

### [TBD-2] Standalone point-mass gravity-turn estimator (Option A) — GATED

- **Module/boundaries:** `apps/analysis/point_mass/` (new package: `__init__.py`,
  `gravity_turn.py`), `tests/test_point_mass.py` (new); optionally a `run_point_mass.py` entry point
  **only if** D-4 says yes
- **Assignee:** developer
- **depends_on:** [TBD-1, D-2 → Option A or C approved, D-4]
- **parallel_safe:** true once TBD-1 has landed (disjoint new files)
- **Spec slice:** sections [4.3](#43-point-mass-assumptions)-[4.6](#46-closed-form-constant-v) of
  this file.

### 8.1 Acceptance criteria

**TBD-0 (paper)**
- [ ] New subsection renders conceptually self-consistently; every `\autoref` target exists (grep
      each label).
- [ ] `sec:notation` has rows for the D-1 symbol, `\hat{x}_v`/`\hat{z}_v`, `V`, `\Lambda`.
- [ ] The chosen symbol collides with nothing in section [2](#2-notation-audit--what-is-already-taken);
      re-grep after writing.
- [ ] The text states explicitly that the model is analysis-only and never integrated.
- [ ] No LaTeX compilation is attempted (no toolchain in this environment, per `CLAUDE.md`).

**TBD-1 (diagnostic)**
- [ ] `theta_v` of a purely vertical ascent is `+90°` (within tolerance); of a vertical descent,
      `-90°`.
- [ ] Still-air residual `theta - alpha - theta_v` is `< 1e-9` rad across a full demo run (this is
      the real test of [4.7](#47-relation-to-the-existing-model--verified-against-the-code)).
- [ ] On a drag-free, aero-free, thrust-free coast (ballistic), `theta_v_dot_actual` matches
      `theta_v_dot_pointmass` to `< 1 %` — the point-mass model is *exact* in that case, making this
      a true oracle, not a tolerance-fudge.
- [ ] On the standard demo scenario, the report records where `Λ` exceeds ~0.1, and that region is
      the low-speed one predicted in section 5.
- [ ] **Full suite unchanged: 761/761, no numeric pin moves.** Explicitly re-verify
      `tests/test_integrate.py` and `tests/test_analytic.py`.
- [ ] `tests/test_layering.py` G1-G3 still pass (G1: nothing in the engine imports `apps.*` outside
      `apps.sim.engine`).

**TBD-2 (estimator)**
- [ ] Reproduces `eq:gravity_turn_closed` to `< 1e-6` relative for constant `V`.
- [ ] Agrees with a full `run_sim` to within a stated tolerance on a deliberately
      point-mass-like scenario (no lift, aligned thrust, flat Earth) — and the doc states the
      observed number rather than promising one.
- [ ] Module docstring states A1-A4 and "cruder model, not a refinement; the engine never calls
      this".
- [ ] Full suite unchanged; no engine import added.

### 8.2 Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Numeric pins move | **none** by construction | no `apps/sim/engine/` physics change; state vector width untouched (the Step 109 `to_vector` lesson: vector *length* changes RK45 step acceptance — so adding no state component is essential) |
| Symbol collision in the paper | medium | section [2](#2-notation-audit--what-is-already-taken) audit + re-grep in acceptance criteria |
| Reader mistakes the crude model for simulated physics | medium | explicit "analysis-only" wording in `assumptions.tex`, the subsection text, and the module docstring |
| Race with the concurrent `analysis.tex` edit | high if ignored | TBD-0 is `parallel_safe: false` and depends on that merge |
| `plotting.py` edit touches the engine directory | low | plotting only, no physics; `tests/test_plotting.py` covers it (note the known flaky `access violation` there — rerun, do not treat as failure) |

### 8.3 Why this is not a pin risk, stated precisely

The existing engine integrates a 7- or 10-component state (`state.py:45-52`). This work adds **no
state component**, changes **no derivative**, and adds **no `p.solver` option**. TBD-1 is pure
post-processing over `run_sim` output; TBD-2 is a disjoint new package the engine never imports.
Step 109's recorded finding — that changing the state-vector *width* alone moves every pinned number,
because scipy's RK45 error norm is an RMS over the vector — is the reason the "new `State` field"
design is rejected outright rather than merely disfavoured.

### 8.4 Explicitly out of scope

- **No new `State` component** for `θ_v` (it is a function of `vx, vz` — storing it would be
  redundant *and* would move every pin; see 8.3).
- **No new `p.solver.method` variant.** The simplified equation is not an alternative *integration
  method* for the same model; it is a different model. Putting it behind `solver.method` would
  imply the engine can run the crude model, which it cannot and should not.
- **No change to `derivatives()`**, `pitch_moment()`, or anything in `apps/sim/engine/dynamics.py`.
- **No 3D/rotational extension** (`dynamics3d.py`, `state3d.py`, `quaternion.py` untouched).
- **No LaTeX compilation** (no toolchain available).

---

## 9. Decisions needed before implementation

| # | Decision | Options | Recommendation |
|---|---|---|---|
| **D-1** | Symbol for the flight-path angle in the paper | A `\theta_v` / B `\gamma_v` / C bare `\gamma` — section [3](#3-d-1--symbol-for-the-flight-path-angle-decision-required) | **A `\theta_v`** — only option with no visually-confusable near-twin |
| **D-2** | Code scope | A new estimator module / B diagnostic over existing runs / C both — section [7](#7-d-2--code-scope-decision-required) | **C, sequenced B → A** |
| **D-3** | Does the user want the paper note to *replace* the assertion at `analysis.tex:177-179`, or sit alongside it? | replace (recommended, section 6.2) / add-only | **Replace** — the assertion is what the derivation fixes |
| **D-4** | If Option A is built, should it be CLI-exposed (`run_point_mass.py`) or library-only? | CLI entry point / library + tests only | **No recommendation — product scope.** Library-only is the cheaper default; a CLI implies a user-facing tool with its own output contract |
| **D-5** | Should TBD-1 add a plot panel to `plotting.py`, or stats only? | plot + stats / stats only | **Stats only first** — keeps the engine directory untouched; add the panel once the user has seen the numbers |

D-1 and D-3 are paper-facing (physics notation and a published claim) and D-4 is product scope: all
three need the user, not the architect. D-2 and D-5 are cost/sequencing calls the orchestrator can
take with the user in one pass.

---

## 10. Side findings

Not part of this ticket; logged because they were found while grounding it.

1. **The notation table has stale code paths** (Phase 2.19 drift). `appendix.tex` still references
   `sim/dynamics.py` (lines 27, 35, 44, 93, 98) and `configs/schema.py` (line 41); both moved to
   `apps/sim/engine/dynamics.py` and `apps/sim/schema.py`. Worth a separate sweep ticket over
   `dev/docs/latex/` for post-restructure path references — the `code-vs-paper.md` file in that
   directory is probably also affected.
2. **There is no `sec:flow` label** (a plausible-looking guess that turned out wrong, caught and
   corrected during this pass). The angle of attack is defined in
   `\subsubsection{Relative velocity and angle of attack}\label{sec:relwind}` (`models.tex:333`),
   inside `sec:aero`. Section 6.1 now uses `sec:relwind`. Noting it because the same wrong guess is
   easy to repeat.
3. **`analysis.tex` is 12 KB, not 300 KB+** as the task assumed — small enough to read whole. The
   same is true of `rocket-2d.tex` (6 KB). `models.tex` (63 KB) is the large one in that directory.
4. **`tests/test_analytic.py` is the natural precedent** for TBD-2's closed-form oracle: it already
   holds vacuum-shot, drag-only-coast and canopy-terminal-speed oracles with the same `z`-down sign
   note in its docstring.
