# Model development candidates — proposals for review

**Status: proposals only.** Nothing here is a ticket, nothing is scheduled, and nothing should be
implemented off this document. It answers the second half of the user's 2026-10-24 request
("improve other models by making them more developed") with a survey of where the paper and the
simulator are thinnest, so the user can pick. Written by `architect` along
`dev/docs/task-109-roll-reaction-wheel.md`.

## Кратко (RU)

- Это **список предложений на выбор пользователя**, не тикеты. Четыре кандидата, где модель
  сегодня тоньше всего, с оценкой «что даёт / что мешает / во что обойдётся».
- **A. Цепочка спуска (парашют).** Самый дешёвый и самый практичный: сегодня купол раскрывается
  мгновенно и полностью, нет связки «дрог + основной», нет триггера по высоте, и есть
  зафиксированный в статье дефект — `ω_r` под куполом сохраняет бессмысленное ненулевое значение.
- **B. Аэродинамика по Барроумену (построение из геометрии).** Самый высокий рычаг: сегодня **все**
  коэффициенты «подаются снаружи», и из-за этого заблокированы статический запас, $C_{m,q}$,
  и только что добавленные крутильные $C_l$/$C_{l,p}$. Это корень почти каждого `\restodo` в статье.
- **C. Внутренняя баллистика / геометрия заряда.** Вывод в статье **уже есть целиком**
  (`sec:mass_grain`), в симуляторе нет ничего — $m_m(t)$ просто следует кривой тяги. Редкий случай,
  когда статья опережает код.
- **D. Рельс: фиксация «съезда назад» + tip-off.** Самый маленький объём: в статье висит прямое
  решение к принятию — зажим, который чинит сползание ракеты вниз по рельсу при малой тяговооружённости.
- Рекомендуемый порядок: **A → D → B → C** (по отношению «польза / цена»). B — единственный, который
  требует реальных данных по планеру.

---

## How the candidates were chosen

Three signals, all already in the repository, were used rather than judgement alone:

1. **`\simtodo` markers** — the paper derives something the simulator does not implement. These are
   the cheapest wins: the physics is already written and reviewed.
2. **`\restodo` markers** — something is blocked on data or on a decision. These are where the
   project is actually stuck, and a few are stuck on the *same* root cause.
3. **Model asymmetry** — a channel the simulator treats with three tiers of fidelity (atmosphere:
   ISA / sounding / field; wind: none / analytic / sounding / field; gravity: constant / radial /
   WGS84) next to a channel with exactly one, crude tier. Recovery is the clearest such asymmetry.

Deliberately excluded: atmosphere (already three tiers plus humid air), gravity (three magnitude
models and three direction models), thrust-curve handling (file-based with impulse/time scatter and
a nozzle-pressure correction). Those are developed.

---

## A. The descent chain — recovery, honestly modelled

**Where it is thin.** `other-dynamics.tex` `sec:recovery` is the one dynamic model in the paper with
no tiers at all. Deployment is "instantaneous and total", the canopy is drag-only, attitude is
frozen by fiat, and the model knows exactly two triggers (timer, apogee). The section itself lists
what is missing with Knacke chapter numbers: the inflation transient (5.4.3–5.4.4), opening shock on
airframe and shock cord (5.4.6), reefing (5.6), a drogue-plus-main sequence (ch. 7), and the pendulum
motion under the risers (5.3).

**What it blocks.** Descent time, drift distance and landing point — the three numbers a recovery
system is actually sized against — all come out of this model, and all three are currently computed
from a canopy that opens in zero time at whatever altitude apogee happens to be. There is no way to
model the standard high-power configuration (drogue at apogee, main at ~150 m), which is the single
most common real-world recovery architecture.

**Also a live defect, already documented.** `sec:recovery` carries a `\restodo` stating that under
canopy only $\dot\theta_r$ and $\dot\omega_r$ are zeroed in the code, so the stored $\omega_r$ keeps
its pre-deployment value and the reported pitch rate under canopy is meaningless. And a `\simtodo`
notes the Coriolis term is dropped under canopy but kept on the rail and in free flight — an
inconsistency, now partly fixed in code at Step 97 but still stated as open in the paper.

**Proposed scope, smallest useful version.** (i) An altitude trigger, so a two-event sequence is
expressible; (ii) a two-stage drogue-plus-main device list rather than one canopy; (iii) a finite
inflation time with the drag area ramping $0 \to C_{D,ch}S_{ch}$, which is what turns "instantaneous"
into something a shock load can be read off; (iv) reset $\omega_r$ to zero at deployment, closing the
`\restodo`. Opening-shock loads, reefing, added mass and the riser pendulum stay out — the pendulum
needs a second body, which is a much larger item the backlog already names separately.

**Cost / risk.** Moderate, and well bounded. Deliberately changes results for any scenario with a
parachute, so it needs a pin decision up front — but no current demo scenario deploys one at a
pinned altitude, so the blast radius is small. **Best value-to-cost ratio of the four.**

---

## B. Aerodynamic build-up from geometry (Barrowman + Mach correction)

**Where it is thin.** All three aero models — `constant`, `linearized`, `table` — are *suppliers*,
not *models*: `sec:aero_coeffs` opens by saying the coefficients "are not derived from the
airframe's shape; they are supplied." There is no path from a nose cone, body tube and fin planform
to $C_z$, $C_m$ and $l_p$.

**What it blocks — and this is the point.** It is the common root of nearly every open `\restodo` in
the paper:

- static margin and the centre-of-pressure travel (`sec:analysis_stability`);
- $C_{m,q}$, whose framework exists and whose *value* does not (backlog: "Dynamic stability,
  quantitatively");
- the Jorgensen large-$\alpha$ extension's $S_p$, $l_{pc}$, $\eta$ (Step 112's parameters, currently
  hand-entered);
- $C_l$ and $C_{l,p}$ — the two coefficients the roll model added at Step 109 needs and cannot get
  (`sec:roll_aero`'s `\restodo`), since roll damping and fin-cant roll torque are *fin* properties
  above all;
- the air brake's normal-force and CP-shift effects (`sec:airbrake`'s `\restodo`: "no $C_N$ data for
  deployed brakes found in the literature").

Every one of those is "waiting on an actual airframe". A Barrowman-style build-up converts that from
a data problem into a geometry problem, and the project *can* supply geometry.

**Proposed scope.** The classic component build-up the backlog already sketches: per-component
normal-force slope $C_{z,\alpha,i}$ at station $X_i$, CP as the slope-weighted mean
$X_{cp} = \sum C_{z,\alpha,i}X_i / \sum C_{z,\alpha,i}$, plus a body-tube skin-friction and base-drag
axial build-up, plus a subsonic Prandtl–Glauert Mach correction with an explicit validity ceiling.
Roll derivatives from fin geometry and cant are a natural second phase.

**Cost / risk.** The largest of the four, and it needs a decision the project has deferred twice: a
concrete airframe. It also introduces a *fourth* aero model, which means a fourth branch in a
dispatch that Steps 55/112/114/119 have each had to untangle. High value, real cost.

---

## C. Internal ballistics and grain geometry

**Where it is thin.** The inverse of B: here the **paper is ahead of the code**.
`models.tex` `sec:mass_grain` derives the whole thing — $r = a_b p_c^n$, $K_n = A_b/A_t$, the
chamber-pressure closure $p_c = (a_b\rho_{pr}c^*K_n)^{1/(1-n)}$, the BATES burning-area law, web
regression, segment inertias — and then ends with `\simtodo{the simulator has no grain model;
$m_m(t)$ follows the thrust curve}`. The mass model currently interpolates $I_{m,g}$ linearly in
propellant mass between two endpoint values, and `Weight.I_p_spec` falls back to a placeholder
$I_d/m_d$ when unset.

**What it would give.** A thrust curve the simulator *generates* instead of reads, so a motor can be
designed rather than selected; a physically-grounded $l_{g,m}(t)$ and $I_{m,g}(t)$ instead of the
two-point interpolation; and altitude-dependent chamber behaviour. It would also make
`apps/motor_selection` able to explore motors that do not exist as files yet.

**Cost / risk.** Moderate derivation work (none — it is written), moderate implementation, but it
needs propellant data the project does not have: $a_b$, $n$, $\rho_{pr}$, $c^*$, segment geometry,
throat and exit areas. And the paper flags that star and finocyl grains have **no** closed form
(openMotor regresses them numerically by level-set). So the honest scope is BATES only.

**Candid assessment:** the most *satisfying* item — a complete derivation sitting unimplemented —
and the least *necessary*, because a measured thrust curve is more trustworthy than a predicted one
for trajectory work. Worth doing for the motor-design use case, not for trajectory fidelity.

---

## D. Launch rail: the reverse-slide clamp, and tip-off

**Where it is thin.** `sec:rail` documents an actual wrong behaviour, with its fix already named:
when thrust along the rail is below the weight component, the constrained acceleration goes negative
and the rocket **slides backwards down the rail** ($s_{rail} < 0$) until thrust catches up. A real
pad reacts weight until lift-off. The paper carries the decision explicitly:

> `\restodo{decision: adopt the clamp; it would change existing results for low thrust-to-weight starts}`

and names the clamp: hold $\vec{a}_r\cdot\hat{e}_{rail} \ge 0$ while $s_{rail}\le 0$ and
$\vec{v}_r\cdot\hat{e}_{rail}\le 0$. RASAero II corrected exactly this case.

Beyond it, the rail has no friction, no flex and no tip-off: transverse and rotational freedoms are
restored *instantly* at $s_{rail} = L_{rail}$. Rail-exit tip-off is a real and well-known source of
initial pitch rate, and rail-exit speed versus wind is precisely what the section says the model
exists to answer.

**Proposed scope, two independent pieces.** (i) The clamp — a handful of lines, a decision already
written down, closes a documented `\restodo`. (ii) Tip-off — the backlog's "Rail–rocket dynamics, in
detail" item, which needs button positions, clearances and a friction coefficient, i.e. it is
blocked on hardware the way B is.

**Cost / risk.** Piece (i) is the smallest item in this document and the only one that fixes a
behaviour the paper already calls wrong. It *does* change results for low thrust-to-weight starts,
so it is a pin decision — which is exactly why it is still open. Piece (ii) is a separate, larger
item.

---

## Suggested order, and the one thing to decide first

| | Candidate | Value | Cost | Blocked on |
|---|---|---|---|---|
| 1 | **A. Descent chain** | High — sizes the recovery system; closes 1 defect + 2 markers | Moderate | Nothing |
| 2 | **D(i). Rail reverse-slide clamp** | Moderate — fixes a documented wrong behaviour | Very small | A pin decision |
| 3 | **B. Aerodynamic build-up** | Highest — unblocks ~6 open markers at once | Large | **A chosen airframe** |
| 4 | **C. Internal ballistics** | Moderate — motor *design*, not trajectory fidelity | Moderate | Propellant data |

**The one decision that unlocks the most:** whether the project commits to a **concrete airframe
geometry** (nose shape, body diameter and length, fin planform and cant). Candidate B depends on it
entirely, and through B so do the static margin, $C_{m,q}$, the Jorgensen parameters, the air brake's
normal force, and the roll coefficients Step 109 just introduced. Without it the project keeps
accumulating models whose coefficients are placeholders; with it, roughly six open `\restodo` markers
become computable rather than researchable.

**Deliberately not proposed:** anything requiring the 3D/6DOF rewrite (standing blocker at Step 30 —
`research/3d_equations_of_motion.md`); state-coupled Dryden turbulence (backlog B11, and its open
question about whether per-tick noise makes results depend on sample rate is a genuine research item,
not a modelling one); and vertical wind (the backlog says "no data source", and that is still true).
A discrete 1-cosine gust model is a cheap partial alternative to B11 worth a mention, but it was left
off the list above because without a gust *specification* to size it against, the gust amplitude
would be as arbitrary as the turbulence intensity already is.
</content>
