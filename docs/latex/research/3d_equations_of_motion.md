# Research/proposal: 3D rigid-body equations of motion (Phase 3, Step 30)

Date: 2026-10-04. Requested by the user: "then u can start with 3D section" (after Phase 2.10 —
launch rail, parachute, control scaffold). `roadmap.md`'s Step 30 is explicitly blocked on exactly
this: `main.tex` has no 3D content anywhere (confirmed by reading it in full — zero mentions of
`3D`, `quaternion`, `inertia tensor`, `Euler's equations`, `yaw`, or `roll`). This note is a
**proposal**, not yet a `main.tex` edit — standard rigid-body mechanics, not something needing
external primary-source verification the way the Dryden spectrum's numeric constants did, but still
presented for the user's sign-off before Step 30 implements against it, per this project's working
rule that `main.tex` is the user's own document and the physics source of truth.

## 1. What 2D already fixes, and what 3D must not silently change

`rocket-2d.tex` §Frames already defines a right-handed body frame $\mathcal{F}_r$ with
$\hat{x}_r,\hat{y}_r,\hat{z}_r$ — the 2D model only ever *uses* $\hat{y}_r$ as a rotation axis, it
was never a 2-axis frame. 3D needs no new frame definition, only permitting rotation about all
three body axes instead of holding $\hat y_r$'s companions fixed. Likewise $A,B,C,D$ and
$l_B,l_C,l_D,u_B,u_C$ (§Geometry) are unchanged — they are points and body-frame distances, not
planar constructions. The translational equation \eqref{eq:eom_trans} and every force
($\vec W,\vec T,\vec A_f$) generalise to 3D vectors with no change in form, only in how many
components they carry; this is Step 29's scope (3D state + translation, attitude held fixed),
**not** this note's. This note is Step 30's scope only: the **rotational** equation
\eqref{eq:eom_rot}, which the 2D scalar form `I*theta_ddot = M_y` cannot generalise merely by adding
components, because a rotating rigid body's angular momentum is **not** `I*omega_vec` for a general
inertia tensor and a rotating frame introduces the `omega x (I*omega)` gyroscopic term that has no
2D analogue (a single rotation axis has nothing to precess around).

## 2. Attitude representation: quaternion (already decided, `architecture.md` §Phase 3)

`architecture.md`'s existing Phase-3 section already made this call, with a concrete reason: the
standard 3-2-1 Euler sequence is singular at pitch $\pm90°$, exactly where a vertically-launched
rocket sits for the whole boost phase. This note adopts it as given, not re-litigated. Let
$q=(q_0,q_1,q_2,q_3)$, scalar-first, represent the rotation from $\mathcal{F}_0$ to $\mathcal{F}_r$.
Kinematics (standard result, e.g. Wertz, *Spacecraft Attitude Determination and Control*, or any
flight-dynamics text):
```
q_dot = (1/2) * q (x) omega_body         (quaternion product, omega_body = (omega_x,omega_y,omega_z)
                                           as a pure quaternion (0,omega_x,omega_y,omega_z))
```
with the explicit component form (Hamilton product, scalar-first):
```
q0_dot = -0.5*(q1*wx + q2*wy + q3*wz)
q1_dot =  0.5*(q0*wx + q2*wz - q3*wy)
q2_dot =  0.5*(q0*wy + q3*wx - q1*wz)
q3_dot =  0.5*(q0*wz + q1*wy - q2*wx)
```
`|q|=1` is preserved by this ODE only in exact arithmetic; numerically it must be renormalised
(every step, or as a solver event) — Step 28's own scope (`roadmap.md`), not repeated here.

The 2D pitch-only case must fall out exactly: $q=(\cos(\theta/2),0,\sin(\theta/2),0)$ (a pure
rotation about $\hat y_r$) reduces the four equations above to $\dot q_0=-0.5 q_1\cdot 0$ etc. with
$\omega_x=\omega_z=0$, leaving only $q_2$ evolving at $\dot q_2 = 0.5 q_0\omega_y$ — the
half-angle form of $\dot\theta=\omega$. This is exactly Step 28's own "Check" (`roadmap.md`:
"a pitch-only quaternion reproduces the 2D `R_body_to_inertial` from Step 5 exactly").

## 3. Inertia tensor: axisymmetric, not general — and why that is not a simplification invented here

A general rigid body needs a full symmetric $3\times3$ inertia tensor (6 independent components,
generally off-diagonal/time-varying as the body reorients relative to its own principal axes — a
real headache). This project's rocket is **already**, by construction, a body of revolution about
$\hat x_r$ at every stage of 2D modelling: the mass model (`main.tex` §Mass and moment of inertia)
only ever derives a single transverse moment of inertia $I(t)$ about $\hat y_r$ through the CoG,
exactly because a slender body of revolution has **no preferred transverse direction** — $I_{yy}=
I_{zz}$ by the same symmetry, and all products of inertia vanish in body axes
($I_{xy}=I_{xz}=I_{yz}=0$) for the same reason. This is not a new assumption this note introduces;
it is the assumption the entire 2D mass/geometry treatment already made implicitly by never needing
a second transverse axis. So the inertia tensor in body axes is, and stays, diagonal:
```
I_body = diag(I_a, I_t, I_t)      # I_a = axial (roll, about x_hat_r), I_t = transverse (today's I(t))
```
**One genuinely new physical input**: $I_a$, the axial (roll) moment of inertia. Unlike $I_t$, this
is *not* already implied by anything in the 2D document. Unlike $I_t$, it is also **not** shifted by
the parallel-axis theorem when the CoG travels along $\hat x_r$ — a body of revolution's axial
inertia is computed from perpendicular distance to the axis, which an axial shift of the reference
point does not change — so $I_a$ is a single constant for the vehicle, not a function of $l_B(t)$.
**Waiting on:** an actual radius-of-gyration or body-diameter profile (the same airframe-geometry
gap `main.tex` §Backlog already names for Barrowman/$c_{m,q}$) to derive a real value; until then, a
required scenario input with no default (like $m,I,l_1,l_2$ already are), not an optional
zero-defaults-to-off field like every Phase-2 model gate — $I_a=0$ is not physical and would make
Euler's first equation below divide by zero.

## 4. Rotational equations of motion: Euler's equations, axisymmetric case

General form (body-frame angular momentum $\vec H=I\vec\omega$, Euler's equation
$\dot{\vec H}+\vec\omega\times\vec H=\vec M$, rearranged):
```
I_body * omega_dot + omega x (I_body * omega) = M
```
With $I_{body}=\mathrm{diag}(I_a,I_t,I_t)$, the cross term collapses to the classical symmetric-top
result (standard derivation, e.g. any rigid-body-dynamics text's "axisymmetric Euler's equations";
not re-derived from scratch here, just specialised):
```
I_a * omega_x_dot                 = M_x
I_t * omega_y_dot - (I_t - I_a)*omega_z*omega_x = M_y
I_t * omega_z_dot + (I_t - I_a)*omega_x*omega_y = M_z
```
Two properties worth stating explicitly because they are exactly what makes this tractable without
more airframe data than §3 already asks for: (a) the roll equation has **no** gyroscopic term at
all — $I_t-I_t=0$ on that axis — so roll responds to roll moment alone, uncoupled from pitch/yaw
except through $\omega_x$ appearing in the other two; (b) with $\omega_x=0$ (no roll rate — true for
a nominal, non-finned-cant flight) the pitch/yaw equations reduce to two **independent** copies of
today's scalar 2D equation, $I_t\dot\omega_y=M_y$, $I_t\dot\omega_z=M_z$ — the check this note
proposes for Step 30 (`roadmap.md` already states it this way: "a body-symmetric rocket with planar
initial conditions reproduces the Phase 1 pitch history").

## 5. Moment vector $\vec M$ — deliberately left general here

$\vec M = \vec{BC}\times\vec T + \vec{BD}\times\vec A_f + \vec A_m$ (eq:eom_rot's own structure,
now three components instead of one). This note does **not** derive $A_m$'s 3D form (yaw moment
from sideslip, roll moment from fin cant) — that is explicitly Step 31's scope
(`roadmap.md`: "3D aerodynamics... roll moment from fin cant, roll and pitch damping"), which in
turn is waiting on the same airframe-geometry gap §3 already named. Step 30 can and should be
implemented and checked (§4's reduction to the 2D case) with $M_x=0$ (no roll moment modelled yet)
and $M_y,M_z$ taken from whatever 2D-style aero model is configured, applied identically about both
transverse axes by the same axisymmetry argument — not a new assumption, the same one §3 already
rests on.

## 6. Required new `Params`/`main.tex` additions (summary)

| Symbol | Meaning | Status |
|---|---|---|
| $I_a$ | axial (roll) moment of inertia | **new, required, no default** — §3 |
| — | everything else ($m,I_t,l_1,l_2,l_B,l_C,l_D,u_B,u_C,\delta$) | unchanged, already defined in `rocket-2d.tex` |

## 7. Open design forks for the user, before Step 30 implements against this

1. **$I_a$'s source for now.** No airframe geometry exists in this document yet (§3's own
   "waiting on"). Options: (a) a placeholder constant per scenario, swept by hand like $c_{m,q}$'s
   Step-44 fixture; (b) a simple geometric estimate from a body radius/diameter the user supplies
   now (e.g. $I_a\approx\tfrac12 m r^2$ for a uniform cylinder, a textbook placeholder in the same
   spirit as $c_{m,q}$'s strip estimate); (c) block Step 30 entirely until real geometry exists.
2. **Renormalisation of $q$.** Every RHS call (cheap, matches this project's existing per-call-cost
   style) vs. a solver event (matches `architecture.md`'s own suggestion, "or as a solver event") —
   a pure implementation-cost choice with no physics content, could be left to the developer, but
   flagged here since Step 28/30 both touch it.

## 8. What this note deliberately does not do

- Does not derive or propose the 3D aerodynamic moment ($M_x$ fin-roll, $M_z$ yaw/sideslip) — Step
  31, waiting on the same airframe data.
- Does not touch translation (Step 29) — already generalises with no new physics, per §1.
- Does not propose a value for $I_a$ — §7.1 lists the options, deliberately not choosing one here.
