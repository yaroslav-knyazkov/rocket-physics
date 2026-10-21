# Industry-standard conventions audit of `sim/` (read-only)

## Кратко (RU)

- Повод: пользователь (2026-10-22) потребовал, чтобы в проекте не было самодельных конвенций — только отраслевые стандарты; поводом стал знак `C_m` (B31/D-111).
- Проверено 12 заявленных пунктов + 9 дополнительных находок по всем модулям `sim/` (включая 3D-каркас и исследовательские записки).
- **Подтверждено стандартным** (менять нечего): ISA-1976 (слои, lapse rates, Сазерленд, геопотенциал), WGS84/Сомильяна + поправка по высоте, Драйден MIL-F-8785C (шкалы и интенсивности), формат RASP `.eng` (порядок полей, единицы, `;`-комментарии, prepend (0,0)), статзапас в калибрах по Барроумену, станция ЦД от носа, кватернионы (scalar-first, Гамильтон, 3-2-1), уравнения Эйлера для симметричного тела, `I_sp` через `g0 = 9.80665`, метеорологическая конвенция ветра, тяга с поправкой `A_e(p_ref − p_amb)`.
- **Самодельные конвенции (расходятся со стандартом)**: 6 штук. Главная после `C_m` — **переопределённость аэро-момента**: таблица одновременно задаёт станцию ЦД `l_p_m` и ненулевой `C_m`, и код складывает оба вклада; в стандартной практике (CFD/RASAero/OpenRocket/Барроумен) ЦД — *производная* величина `x_cp = x_ref − C_m·d/C_N`, а не независимый вход рядом с `C_m`. Риск двойного учёта статического момента в данных пользователя.
- Остальные: множитель осевого потока `clip(cos α/cos 85°)` вместо стандартного `cos²α` (D-92, стандарт даже не рассматривался); продолжение `C_m` в расширении Йоргенсена через `cm_e·Z(α)/Z(α_e)` вместо опубликованного геометрического члена; `c_mq` не переворачивается при `cm_convention="standard"` (ловушка для пользователя); `Re` на `l_ref` вместо `d_ref` (D-118, безвредно — `Re` ни во что не входит); `η`/`C_dn`/`C_x180` не пришпилены к первоисточнику (QA-9).
- **Числовые пины**: исправление `C_m` (D-111 вариант b) и множителя осевого потока сдвигают пины; остальное — нет либо почти нет. LaTeX (`dev/docs/latex/`) затрагивает только пункт `C_m` и переопределённость момента.
- Нужны решения пользователя: см. §13 «Open questions» и таблицы развилок в §1.1, §2, §9, §12.1.

---

## Table of contents

- §0 Method, scope, how to read this
- §0.1 Findings index (one row per item, with pin/LaTeX impact)
- §1 Moment and force sign conventions
  - §1.1 `C_m` — the calibration case (confirmed invented)
  - §1.2 `C_mq` pitch damping — consequential flip, not a second invention
  - §1.3 GAP: `c_mq` is not flipped by `cm_convention="standard"`
  - §1.4 `C_N` / `C_A` body-axis force signs — confirmed standard
  - §1.5 Pitch angle, pitch rate, `_cross_y` — confirmed standard
- §2 Axial force sign and tail-first handling
- §3 Reynolds reference length (D-118)
- §4 Static margin / stability margin definition
- §5 CP station convention (`l_p` from the nose)
- §6 RASP `.eng` / motor-file parsing
- §7 Atmosphere model (ISA 1976)
- §8 Gravity models (constant / radial / WGS84)
- §9 Jorgensen / Hoerner large-alpha extension
- §10 Quaternion convention for the blocked 3D phase
- §11 Units and `g0` / `I_sp`
- §12 Additional findings not in the brief
  - §12.1 GAP (highest impact after `C_m`): the aero moment is over-determined — `l_p` and `C_m` both supplied
  - §12.2 `AeroCoeffs.C_x`/`C_z` naming vs `C_A`/`C_N` semantics
  - §12.3 `linearized` model uses `sin α`, not Barrowman's linear `α`
  - §12.4 Dryden realization: sum-of-sinusoids instead of the MIL transfer function
  - §12.5 `_g_radial` uses AGL where `_g_wgs84` uses MSL
  - §12.6 Dangling backlog reference `B42` in `sim/aero.py`
  - §12.7 Propellant MOI placeholder `I_p ∝ m_p`
  - §12.8 Apogee predictor uses `v_z` only
  - §12.9 Wind direction / shear — confirmed standard
- §13 Open questions for the user (morning list)
- §14 Recommended order of work

---

## §0 Method, scope, how to read this

Branch `feature/sim-paper-alignment` at `f17a88a`, working tree clean apart from an untracked
`docs/`. Nothing was written outside this file; no test run; no git operation beyond the checkout.

Modules read in full: `sim/forces.py`, `sim/aero.py`, `sim/dynamics.py`, `sim/frames.py`,
`sim/state.py`, `sim/flow.py`, `sim/atmosphere.py`, `sim/gravity.py`, `sim/mass.py`,
`sim/thrust_curve.py`, `sim/motor_file.py`, `sim/params.py`, `sim/quaternion.py`, `sim/state3d.py`,
`sim/dynamics3d.py`. Read in part: `sim/control.py`, `sim/wind.py`, `sim/integrate.py`,
`sim/report.py`, `sim/forces3d.py`, `sim/mach_warning.py`. Supporting documents:
`dev/docs/architecture-34-axial-drag-sign.md`, `dev/docs/architecture-35-paper-alignment.md` §35.7,
`dev/docs/step-99-notes.md`, `dev/docs/step-112-notes.md`, `dev/docs/qa-report-2.17-m1.md` (QA-9/13),
`dev/docs/latex/sections-ai/rocket-2d.tex` §§forces/geometry/eom,
`dev/docs/latex/research/jorgensen-params-findings.md`,
`dev/docs/latex/research/3d_equations_of_motion.md`, `data/aero/example_v2.csv`, tracker
`backlog_ideas`.

**Verdict vocabulary.** `CONFIRMED STANDARD` — the code matches a named external standard, nothing
to do. `INVENTED (documented)` — the code deviates and the deviation has a D-number / backlog entry.
`INVENTED (undocumented)` — the code deviates and I found no decision record. `UNPINNED` — the code
claims a literature source but no test compares it against published values.

**Sources named in this document** (no "the standard says" without one):

| Short name | Full reference |
|---|---|
| Barrowman | J. S. Barrowman, "The Practical Calculation of the Aerodynamic Characteristics of Slender Finned Vehicles", NARAM-8 / NASA TMX-, 1966-67 — the amateur-rocketry CP/stability method |
| OpenRocket techdoc | S. Niskanen, "OpenRocket Technical Documentation" (openrocket.sourceforge.net/techdoc.pdf) |
| Mandell et al. | G. Mandell, G. Caporaso, W. Bengen, "Topics in Advanced Model Rocketry", MIT Press 1973 |
| Jorgensen TR R-474 | L. H. Jorgensen, "Prediction of Static Aerodynamic Characteristics for Slender Bodies Alone and with Lifting Surfaces to Very High Angles of Attack", NASA TR R-474, 1977 |
| Jorgensen TN D-7228 | L. H. Jorgensen, NASA TN D-7228, 1973 (the 0–90 deg form) |
| Hoerner | S. F. Hoerner, "Fluid-Dynamic Drag", 1965 |
| US Std Atm 1976 | "U.S. Standard Atmosphere, 1976", NOAA/NASA/USAF; ISO 2533 for the ISA subset |
| WGS84 / TR8350.2 | NIMA TR8350.2, "DoD World Geodetic System 1984", 3rd ed. |
| MIL-F-8785C / MIL-HDBK-1797 | US military flying-qualities specs — the Dryden turbulence model |
| RASP `.eng` | The RASP/ThrustCurve.org engine-file format (`;` comments, one header line per motor, `t F` rows) |
| Etkin / Stevens-Lewis | B. Etkin "Dynamics of Atmospheric Flight"; Stevens & Lewis "Aircraft Control and Simulation" — pitch-moment and stability-derivative sign conventions |
| Wertz | J. R. Wertz (ed.), "Spacecraft Attitude Determination and Control" — quaternion/DCM conventions |

---

## §0.1 Findings index

**Score: 21 items audited (12 from the brief + 9 found while reading). 6 genuine invented-vs-standard
gaps, 11 confirmed already standard, 4 "matches the standard but is not pinned / not fully
implemented".**

| § | Item | Verdict | Pins move to fix? | LaTeX? |
|---|---|---|---|---|
| 1.1 | `C_m` sign (positive = nose-down; stability needs `C_m_alpha > 0`) | **INVENTED** (documented, D-111) | yes | yes |
| 1.2 | `C_mq` pitch damping sign and non-dimensionalisation | consistent with 1.1, **no second invention** | (rides on 1.1) | — |
| 1.3 | `c_mq` not flipped by `cm_convention="standard"` (scalar path only) | **INVENTED** (documented, no decision record) | no | no |
| 1.4 | `C_N` / `C_A` body-axis force signs | CONFIRMED STANDARD | — | — |
| 1.5 | Pitch angle / pitch rate / `_cross_y` / NED frame | CONFIRMED STANDARD | — | — |
| 2 | Axial flow factor `clip(cos a / cos 85°)` vs Jorgensen `cos²a` | **INVENTED** (documented, D-92; standard never considered) | yes | yes |
| 3 | Reynolds reference length `l_ref` → `d_ref` | **INVENTED** (documented, D-118); zero consequence — `Re` feeds nothing | no | no |
| 4 | Static margin `(CP - CG)/d` in calibers | CONFIRMED STANDARD (Barrowman/OpenRocket) | — | — |
| 5 | CP station from the nose, positive aft | CONFIRMED STANDARD | — | — |
| 6 | RASP `.eng` grammar, field order, units, `(0,0)` prepend | CONFIRMED STANDARD; 3 robustness deviations | no | no |
| 7 | ISA / US Standard Atmosphere 1976 (layers, lapse, Sutherland, geopotential, Magnus) | CONFIRMED STANDARD, exactly | — | — |
| 8.1 | WGS84 Somigliana normal gravity + 2nd-order height term | CONFIRMED STANDARD (TR8350.2 constants exact) | — | — |
| 8.2 | `elliptical` direction = Euler/Meusnier `R_chi` | CONFIRMED STANDARD | — | — |
| 8.3 | `_g_radial` uses AGL where `_g_wgs84` uses MSL | internal inconsistency, informational | yes (if changed) | no |
| 9 | Jorgensen `C_N`, `C_A`, crossflow `C_m` structure | CONFIRMED STANDARD (verified term by term) | — | — |
| 9 | Jorgensen potential-`C_m` term (`cm_e·Z(a)/Z(a_e)`) and the blend | **INVENTED** (labelled "not paper-verified") | yes | maybe |
| 9.1 | `eta`, `C_dn`, `C_x180` values, `alpha > 90°` sign | UNPINNED / UNVERIFIED (QA-9, QA-13) | no (for pinning) | no |
| 10 | Quaternion: scalar-first, Hamilton, body→inertial, 3-2-1, `q̇`, Euler's equations | CONFIRMED STANDARD; one direction-convention note for the pending 3D review | — | — |
| 11 | `I_sp` / `g0` / pressure-thrust / angles / cylinder MOI | CONFIRMED STANDARD | — | — |
| **12.1** | **Aero moment over-determined: `l_p` *and* `C_m` both supplied, both summed** | **INVENTED** (inherited from the approved paper; no decision record) | **no** (option A) | yes |
| 12.2 | `AeroCoeffs.C_x`/`C_z` hold `C_A`/`C_N` (opposite-sign standard symbols) | naming gap only | no | yes |
| 12.3 | `linearized` uses `sin(alpha)` not Barrowman's `alpha` | INVENTED but well justified — keep, document | no | no |
| 12.4 | Dryden: MIL scales/intensities standard, sum-of-sinusoids realization substituted | standard spectrum, invented realization (documented) | — | — |
| 12.6 | `sim/aero.py` cites backlog `B42`, which does not exist | traceability gap | no | no |
| 12.7 | Propellant MOI `I_p ∝ m_p` | acknowledged placeholder (B24), not a misrepresented standard | — | — |
| 12.8 | Apogee predictor `h + v_z²/(2g)` | CONFIRMED STANDARD estimator | — | — |
| 12.9 | Meteorological wind direction, 1/7 power-law shear at 10 m | CONFIRMED STANDARD | — | — |

---

## §1 Moment and force sign conventions

### §1.1 `C_m` — the calibration case (confirmed invented, decision already taken)

**Verdict: INVENTED (documented). Confirmed exactly as the brief states; not re-derived.**

**What the code does.** `sim/forces.py::aero_moment_y` builds `A_m = q·S·d_ref·C_m` and returns
`-A_m`; `sim/dynamics.py` then uses that return value directly as a `+ŷ_r` moment contribution
(`M_y = M_thrust + M_aero + M_moment`, `domega/dt = M_y / I`). I verified the frame chain that makes
this a genuine sign flip rather than a bookkeeping artefact:

- `sim/frames.py::R_body_to_inertial(theta) = [[c, s], [-s, c]]` acting on `(x, z)` is exactly the
  active rotation `R_y(theta)` about `+ŷ`. So `theta` is a right-handed rotation about `+ŷ_r`, and in
  this NED-like frame (`x` forward, `z` down, `y` right) a positive rotation about `+y` lifts the
  nose. That is the standard aerospace pitch convention (Etkin; Stevens & Lewis).
- `omega = dtheta/dt` is therefore the standard pitch rate about `+ŷ_r`, and
  `I·theta_ddot = M_y` with `M_y` about `+ŷ_r` is dimensionally and sign-wise the standard
  `I_yy·q̇ = M`.
- Hence `M_y_from_Cm = -q·S·d_ref·C_m`: **positive `C_m` produces a nose-down moment**, and static
  stability needs `dC_m/dalpha > 0`.
- `flow.alpha = atan2(w, u)` is positive when the nose is pitched up relative to the relative wind
  (verified by rotating `v_i = (V, 0)` into the body frame at `theta > 0`) — the standard `alpha`
  sign. So the `alpha` side of the derivative is standard; only `C_m`'s sign is flipped.

**What the actual standard is.** Positive `C_m` = nose-up (restoring sense for a stable vehicle is
negative), static stability ⇔ `C_m_alpha < 0`. Source: Etkin and Stevens & Lewis (flight-dynamics
convention), Barrowman and OpenRocket techdoc §3 (amateur-rocketry convention), and every
CFD/RASAero/wind-tunnel export the project intends to consume.

**Why the project deviated.** B31 (found 2026-10-17), D-111 (decided 2026-10-18): option (c) —
keep the code convention, let each table declare `# cm_convention: code|standard`, flip at load. The
recorded reasons were (i) zero numeric-pin movement, (ii) the approved LaTeX paper uses the same
convention throughout (`dev/docs/latex/sections-ai/rocket-2d.tex` eq. `eq:aero_magnitudes` writes
`A_m = -qSc·C_m·ŷ_r`), (iii) option (b) — switch the codebase and the paper to the real standard —
was deferred "only with the 3D phase" and never scheduled.

**Cost to fix (option b, the real standard).**

| Axis | Estimate |
|---|---|
| Files referencing `C_m` | 34 files (`sim/` 5, `configs/` 3, `apps/` 3, `tests/` 21, `data/aero/` 2); 264 matching lines |
| Files referencing `c_mq`/`C_mq` | 12 files, 135 lines |
| `cm_convention` plumbing to delete | 10 files, 50 lines |
| Numeric pins | **Yes** — every moment/attitude pin moves unless the flip is paired with sign-flipped data; `tests/test_forces.py`, `test_dynamics.py`, `test_aero*.py`, `test_integrate.py`, `test_control.py` |
| Approved LaTeX | **Yes** — 13 files under `dev/docs/latex/` mention `C_m`; `rocket-2d.tex` eq. `eq:aero_magnitudes` and `eq:eom_rot_expanded`, `analysis.tex` (static-margin / `C_m,alpha` discussion), `models.tex`, `other-dynamics.tex`, `appendix.tex` |

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(a) status quo (D-111 c)** — code convention + per-table `cm_convention` flag | already shipped and tested; zero pin movement; externally-sourced tables are explicitly declarable | every human reading `sim/`, the paper, or a `Params.C_m_alpha` value has to hold an inverted convention in their head; `c_mq` is a documented exception to the flag (§1.3); "`C_m_alpha > 0` is stable" will keep tripping reviewers and any future contributor | 0 |
| **(b) switch code + paper to the standard** (D-111 b, deferred) | one convention everywhere; published `C_m`, `C_m_alpha`, `C_m_q` usable with no sign bookkeeping; removes `cm_convention`, `_cm_to_code` and the `c_mq` exception entirely | moves every moment pin; edits the approved paper (user has forbidden LaTeX edits without an explicit ask); one focused step + a re-pin approval | M (1 step for `sim/`+`configs/`+`data/`, 1 for tests/re-pin, 1 for the paper when the user allows) |
| **(c) keep the internal sign but rename the symbol** — call the code's quantity `C_m_code` (or `C_n` for "nose-down moment coefficient") everywhere, reserve `C_m` for the standard-sign quantity at the I/O boundary | no pin movement; removes the main harm (a standard symbol with a non-standard meaning); honest in the paper too | still two conventions in the system; rename touches the same 34 files; paper edit still needed | S-M |

**Recommendation.** (b) is the only answer consistent with the user's new rule, but it is a pin-moving,
paper-touching change — schedule it as a dedicated step with its own approval, not inside another
phase. If the user wants zero pin movement now, (c) is a real improvement over (a) at low risk and
can be done immediately; (b) then becomes a pure data/sign step later.

### §1.2 `C_mq` pitch damping — consequential flip, not a second invention

**Verdict: CONFIRMED consistent (no independent second flip), but inherits §1.1.**

**What the code does.** `sim/forces.py::aero_moment_y` adds
`A_m += 0.25·rho·V·S·d_ref²·omega·C_mq` and returns `-A_m`. That is the division-free form of
`q·S·d_ref·q̂·C_mq` with `q̂ = omega·d_ref/(2V)`. The resulting moment contribution is
`M_y = -(q·S·d_ref²/(2V))·omega·C_mq`, i.e. a damping (opposing) moment requires `C_mq > 0`.
`sim/aero.py::_table_coeffs` states this explicitly: "positive c_mq is DAMPING in this document's
convention … the opposite of the textbook `C_mq < 0`, the same flip `C_m_alpha` already carries".

**What the actual standard is.** `C_mq = ∂C_m/∂q̂` with `q̂ = q·l_ref/(2V)` and `C_mq < 0` for a
damped vehicle (Etkin; Stevens & Lewis; the project's own research note
`dev/docs/latex/research/c_mq_pitch_damping.md`). The non-dimensionalisation used here
(`q̂ = omega·d_ref/(2V)`, reference length = body diameter) is the standard **missile/body-of-
revolution** convention; aircraft use `c̄`. `d_ref` is correct for a rocket.

**Why the deviation.** None independent: `C_mq` is a derivative of `C_m`, so flipping `C_m` flips
`C_mq` by exactly the same single sign. The non-dimensional group, the `2V` factor and the use of
`omega` (the true pitch rate about `+ŷ`) are all standard. Step 114 correctly flips a table's `c_mq`
column together with its `C_m` column under `cm_convention: standard` (`sim/aero.py` lines ~279-282).

**Cost to fix.** Nothing to fix in isolation; it rides on §1.1 option (b). Phase 2.6/2.7 history
(B9, "real value/model for `c_mq`") concerns the *magnitude* (still a Step-44 fixture, tracker status
"open — decided to keep the Step 44 fixture"), not the sign — a separate, data-fidelity concern.

### §1.3 GAP: `c_mq` is NOT flipped by `cm_convention="standard"` for the constant/linearized models

**Verdict: INVENTED (documented, but a user-facing trap).**

**What the code does.** `sim/aero.py::_constant_coeffs` and `_linearized_coeffs` both do
`C_m=_cm_to_code(…)` but `C_mq=p.aero.c_mq` — **raw, unflipped**. `sim/params.py` documents it:
"pitch-damping derivative [-]. CODE sign (positive = damping) regardless of `cm_convention`: the
scalar is NOT flipped under 'standard' (a table's c_mq column IS flipped there)."

**Why this is a problem.** A user who sets `Aero.cm_convention = "standard"` — the whole point of
which is "I am giving you textbook-sign numbers" — and then types a textbook `c_mq = -5.0` gets an
*anti-damping* term, silently, with no validation error. The same user with the same two numbers in a
table file gets the correct behaviour. The two paths disagree about what `cm_convention` means.

**What the actual standard is.** `C_m` and `C_mq` are the same quantity's value and slope; a sign
convention that applies to one applies to the other. There is no literature convention in which they
differ.

**Why the project deviated.** No decision record found. `cm_convention` was introduced at Step 99
(D-111) for the static `C_m` only; Step 114 extended the flip to the table `c_mq` column but not to
the scalar. The asymmetry appears to be an implementation oversight later written up as documentation
rather than a deliberate choice.

**Cost to fix.** Tiny and pin-safe: one line in each of `_constant_coeffs`/`_linearized_coeffs`
(`C_mq=_cm_to_code(p.aero.c_mq, p)`), one comment in `sim/params.py`, one test. Bit-for-bit for every
existing config, because **no config in the repo combines `cm_convention="standard"` with a nonzero
scalar `c_mq`** (`cm_convention` appears in 10 files; the only `standard` declaration is the header of
`data/aero/example_v2.csv`, which is a table, and `Aero.c_mq` defaults to `0.0`). No LaTeX impact.

**Recommendation.** Fix now, as part of whatever the first `sim/aero.py` step is. Alternative (if
§1.1 option (b) is approved): the whole `cm_convention` mechanism disappears and this gap with it —
do not spend a step on it in that case.

### §1.4 `C_N` / `C_A` body-axis force signs — CONFIRMED STANDARD

`sim/forces.py::aero_force_body` returns `[-(A_x + A_brake), -A_z]` with `A_x = q·S·C_x`,
`A_z = q·S·C_z`. So positive `C_x` gives a force along `-x̂_r` (aft = drag for nose-first flight) and
positive `C_z` gives a force along `-ẑ_r` ("up" relative to the body) — and with
`C_z = C_N_alpha·sin(alpha)`, `C_N_alpha > 0`, a positive `alpha` gives a force toward `-ẑ_r`, which
is physically correct and matches the NASA missile convention for `C_N` (normal force positive out
the top of the body; Jorgensen TR R-474 §2.3, Nielsen "Missile Aerodynamics"). `C_A` positive aft is
likewise the standard axial-force convention (Jorgensen eqs. 2.18/2.19; `C_A = -C_X`). **No gap.**
See §12.2 for the naming (not the sign) problem.

### §1.5 Pitch angle, pitch rate, `_cross_y` — CONFIRMED STANDARD

- Inertial frame: `x` downrange, `z` down, `y` completing a right-handed triad — NED-like, the
  standard flight-dynamics choice (Stevens & Lewis §1).
- `theta` positive nose-up from the horizontal, `R_body_to_inertial = R_y(theta)` — standard.
- `_cross_y(a, b) = -(a_x·b_z - a_z·b_x)` is the `ŷ` component of `a × b` given
  `x̂_r × ẑ_r = -ŷ_r` — the correct 2-D reduction of an ordinary right-handed 3-D cross product in a
  z-down frame, not an invented sign. Verified consistent with `aA = -l1·x̂_r` producing a restoring
  (negative `M_y`) moment for positive `alpha` with the CP aft of the CG.
- `sim/quaternion.py::to_dcm` reduces, for a pitch-only quaternion, to exactly
  `frames.R_body_to_inertial(theta)` in its `(x, z)` sub-block — the 2-D and 3-D attitude conventions
  agree (checked algebraically, see §10).

**No gap.**

---

## §2 Axial force sign and the tail-first handling (B27/B17, D-91/D-92, Steps 93-96)

**Verdict: the sign fix is correct; the *shape* of the correction is INVENTED (documented), and the
standard form was never among the options considered.**

**What the code does.** `sim/aero.py::axial_flow_factor(alpha) = clip(cos(alpha)/cos(85°), -1, +1)`,
multiplied into `C_x` for the `constant` and `linearized` models, into a `table` model's `C_A` iff the
table's own alpha grid stays strictly inside `(-90°, +90°)` (`_table_axial_factor`, D-93), and into the
additive airbrake term (`sim/forces.py` line ~243, D-94a). Result: exactly `1.0` for
`|alpha| <= 85°` (bit-for-bit legacy), linear in `cos alpha` through zero at `±90°`, exactly `-1` for
`|alpha| >= 95°`.

**What the actual standard is.** For a body of revolution over the full `0..180°` range the
literature form is **`C_A(alpha) = C_A(alpha=0)·cos²(alpha)` for `0 <= alpha <= 90°` and
`C_A(alpha) = C_A(alpha=180°)·cos²(alpha)` for `90° <= alpha <= 180°`** — Jorgensen TR R-474
eqs. (2.18)/(2.19), restated in the project's own research note
`dev/docs/latex/research/jorgensen-params-findings.md` §3/§4, with the sign carried by
`C_A(180°)` being a separate measured input (it is *not* equal to `-C_A(0)`; a flat base facing the
flow is a bluff body, so `|C_A(180°)| > |C_A(0)|` for a pointed-nose rocket — the research note calls
`C_A(180) = C_A(0)` "not a conservative default").

**So: the *fixed* version is correct in sign but not in shape.** The ramp is right about the thing the
bug was (the axial force must oppose the flow when flying tail-first) and wrong about how the axial
force actually decays with incidence. For small-angle flight `cos²alpha` ≈ 1 to within 1.5% out to
10°, so the plateau is nearly harmless there; the two forms differ materially from ~20° upward, which
is exactly the regime the factor exists for.

**Why the project deviated.** `dev/docs/architecture-34-axial-drag-sign.md` §34.3 / D-92. The options
compared were: ramp `alpha_0 = 85°`, ramp `80°`, bare `cos alpha`, `sign(cos alpha)`, and
wind-frame drag. **`cos²alpha` — the published form — is not in that list.** The chosen criterion was
explicitly "bit-for-bit for `|alpha| <= 85°`" plus "1 pin test moves" (§34.3 line ~141, §34.8 D-92).
This is the clearest instance in the audit of a convention selected to protect numeric pins rather
than to follow a source.

**Interaction with §9 (a real internal inconsistency).** Under `table_oob="jorgensen"` the clamped
in-range `C_x` carries the 85° ramp, and the out-of-range branch computes
`Cx_J = x0·cos²(alpha)` (or `-x180·cos²(alpha)`) — *the standard form* — then blends the two over
`oob_blend_deg`. The same physical quantity therefore has two different alpha-dependences on either
side of the table edge, joined by a smoothstep. Inside `±10°` this is invisible; between 10° and
90° it is not.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(a) keep the 85° ramp** | shipped, tested, documented, 1 pin already moved for it; nose-first flight bit-for-bit | not the literature form; inconsistent with the Jorgensen branch it blends into; no source | 0 |
| **(b) adopt `C_A = C_A0·cos²alpha` / `-C_A180·cos²alpha` everywhere** (`Aero.C_x180` already exists for the second constant) | one form, Jorgensen-sourced, consistent with `_jorgensen_extend`; lets the user supply a real `C_A(180°)`; removes `_COS_ALPHA0` and the 85°/95° kinks | **moves pins**: `cos²` ≠ 1 for every `alpha ≠ 0`, so *every* flight with nonzero alpha changes, not just tail-first ones — this is the expensive one; `tests/test_aero.py`, `test_forces.py`, `test_dynamics.py`, `test_integrate.py`, `test_mach_warning.py`, plus the app-level sweeps | M-L |
| **(c) hybrid: keep a plateau but make it `cos²`-shaped and signed outside it** | bit-for-bit nose-first (no pin movement below `a0`); standard shape where it matters; consistent with the Jorgensen branch | still a plateau nobody publishes; one more tunable (`a0`); the kink at `a0` remains | S |
| **(d) (b) restricted to the `table` model only**, leaving `constant`/`linearized` on the ramp | pins for the demo/table scenarios are what matter; low blast radius | makes the three models disagree about the same physics — the exact class of bug Step 55/F2 closed | S |

**Cost data.** `axial_flow_factor` is referenced in 4 files / 19 lines (`sim/aero.py`,
`sim/forces.py`, `tests/test_aero.py`, `tests/test_forces.py`); the *behavioural* blast radius is much
larger than that, because the factor multiplies `C_x` on every RHS call. No LaTeX impact for (c)/(d);
option (b) needs one sentence in `models.tex` describing the new `C_A(alpha)` form (and `Aero.C_x180`
promoted from "jorgensen-only" to always-used).

**Recommendation.** (c) now if the user wants the standard shape without a re-pin campaign; (b) if the
user's rule ("use industry standards, change what is invented") is applied literally — but (b)
must be scheduled as its own step with an explicit re-pin approval, and should be bundled with
§9's `C_x180` fidelity question so that the `C_A(180°)` input is populated at the same time.

---

## §3 Reference length for the Reynolds number (D-118, B32.4)

**Verdict: INVENTED (documented); harmless today because `Re` feeds nothing.**

**What the code does.** `sim/flow.py` lines ~118-121:
`l_re = p.aero.l_ref if p.aero.l_ref != 0.0 else p.aero.d_ref`, then
`Re = rho·V·l_re/mu`. `Aero.l_ref` defaults to `0.0`, so out of the box `Re` uses `d_ref`.
`sim/aero.py::validate` rejects `l_ref < 0`.

**What the actual standard is.** For a rocket there are two *legitimate* reference lengths, used for
different purposes, and both are standard:

- **`Re_d` on the diameter** — the standard choice for crossflow and base/body pressure correlations
  (Jorgensen TR R-474 uses a crossflow Reynolds number `Re_n` based on the diameter; Hoerner's
  cylinder data is diameter-based).
- **`Re_L` on body length** — the standard choice for skin-friction drag, which is the thing that
  actually needs a Reynolds number in a rocket drag build-up. OpenRocket techdoc §3.4.1 computes skin
  friction from `Re` based on **body length**; Barrowman and Mandell et al. likewise use body length
  for the friction term.

So neither `d_ref` nor `l_ref` is "wrong". What is non-standard is having a *single* unlabelled `Re`
whose reference length is a free parameter, because the correct length depends on which correlation
consumes it. There is no literature convention for "the Reynolds number of a rocket" in the abstract.

**Why the project deviated.** D-118 (architecture-35 §35.7), option (c), accepted by the user
2026-10-18: "`l_ref == 0` → `d_ref`, nonzero `l_ref` honoured — no config/test breaks, paper gets one
sentence. `Re` feeds no model, so no flight result changes". The driver was alignment with the paper
(which writes `c = d_ref`) at zero cost. Code reference: `architecture-35` row C2 / B32.4.

**Cost to fix / cost of doing nothing.** `l_ref` appears in 26 lines. `Re` is computed in `Flow` and
**consumed by no model** (it reaches only `tests/test_flow.py` expectations; it is not read in
`aero.py`/`forces.py`/`dynamics.py`). No pins move either way. No LaTeX change beyond the sentence
D-118 already allows.

**Recommendation.** Keep the mechanism, but **document the semantics instead of the length**: say in
the field comment *which* correlation it is for, and when a `Re`-dependent model eventually lands
(backlog B30 item 3, "no `Re` axis in the aero table") give it its own length-based `Re_L` instead of
reusing this one. Low priority — nothing is wrong today, only under-specified.

---

## §4 Static margin / stability margin definition

**Verdict: CONFIRMED STANDARD.**

**What the code does.** `sim/report.py::static_margin_cal`:
`margin(t) = aero.coefficients(...).l1 / p.aero.d_ref`, where `l1` is the CP-to-CG arm
(`l_p - l_g(t)` for a station config, the legacy constant arm otherwise), evaluated on the flight's
own `(alpha, M)`. Positive ⇒ CP aft of CG ⇒ statically stable. `d_ref` is documented in
`dev/docs/architecture.md` line ~1015 as "body diameter [m] — moment reference length".
`sim/report.py::stability_check` additionally warns on a negative margin or a negative
`dC_m/dalpha` *in the code convention*.

**What the actual standard is.** Static margin in calibers `= (X_cp - X_cg)/d`, with `d` the maximum
body diameter, positive = stable. Source: Barrowman; OpenRocket techdoc §3.6 and its UI
("stability, calibers"); Mandell et al. on static stability. The familiar 1-2 caliber design rule
uses exactly this definition.

**Confirmed details.** Sign ✓ (positive = CP aft of CG = stable). Scaling ✓ (divided by `d_ref`, not
by body length and not by `2d`). Origin ✓ (both stations from the nose tip, so the difference is
origin-independent). Time dependence ✓ (uses the *live* `l_g(t)` from `sim/mass.py` — more faithful
than OpenRocket's launch-mass-only display, and what B33 asked for).

**One caveat, not a gap.** `Aero.d_ref` serves double duty as the aerodynamic moment reference length
*and* the caliber. For a rocket these coincide by the standard missile convention (both are the body
diameter), so the conflation is correct — but a user who sets `d_ref` to anything other than the
maximum body diameter (a fin chord, or a reference length inherited from a CFD run that used a
different `c`) will get a silently wrong "calibers" number.
`architecture-28-rewrite.md` line ~312 already notes that these two roles are not independent.
Suggest a one-line warning in the rocket template rather than code.

---

## §5 CP station convention (`l_p` from the nose)

**Verdict: CONFIRMED STANDARD.**

**What the code does.** Lengths are "all nose-tip-referenced, metres" (`sim/params.py::Lengths`).
`Aero.l_p` / the table column `l_p_m` is "CP station from the nose [m]" (`sim/aero.py` module
docstring, Step 99/D-110); `Lengths.l_g` / `mass.cog_position` is the CG station from the nose; the
arm is `l_p - l_g(t)` (`aero._resolve_arm`). Positive aft. The paper agrees:
`rocket-2d.tex` §geometry — "`l` is the axial distance of a point from `A` [the nose tip], positive
towards the tail", `Ap = [-l_p, 0, 0]ᵀ_r`.

**What the actual standard is.** Barrowman's method and every tool implementing it (OpenRocket
techdoc §3.6; RASAero; RockSim) report CP and CG as stations measured aft from the nose tip, positive
aft; wind-tunnel and CFD exports do the same (`x/L` or `x [m]` from the nose or from a declared
reference station). **Match.**

**Confirmed details.** Origin = nose tip ✓. Sign = positive aft ✓. The internal model coordinate is
negative along `x̂_r` (`AB = -l_B·x̂_r`) because `x̂_r` points toward the nose — that is the
documented project-wide sign convention (`CLAUDE.md` § "Соглашение о знаках") and a *representation*
detail, not a convention deviation: the user-facing input is positive-aft-from-nose, exactly as the
standard requires. Step 99's fail-fast (`misalign_deg == 0` required for a station config, because
the thrust arm still uses the legacy `-(l1 + l2)` expression) is an acknowledged incompleteness
rather than a convention problem — a backlog line, not a sign fix.

---

## §6 RASP / `.eng` motor-file parsing

**Verdict: CONFIRMED STANDARD on field order, units, comment convention and the leading-zero point;
three robustness deviations, one of which silently loses data.**

**What the code does.** `sim/motor_file.py::_read_rasp`. Grammar: `;`-prefixed lines are comments and
discarded; a non-comment line whose first whitespace token does not parse as a float is a header line
and starts a new record; every other non-blank, non-comment line is a `time thrust` data row; a record
ends at the next header or EOF. Header fields are read positionally as
`designation diameter_mm length_mm delays m_prop_kg m_total_kg manufacturer`, with
`diameter`/`length` divided by 1000 to metres and `delays` kept as free text, never parsed. If a
record's first data row has `t > 0`, an explicit `(0.0, 0.0)` point is prepended (D-64).

**What the actual standard is.** The RASP `.eng` format as published by ThrustCurve.org / NAR and
implemented by every consumer: one header line per motor with the fields
`designation diameter(mm) length(mm) delays prop-weight(kg) total-weight(kg) manufacturer`, `;` for
comments, then `time thrust` pairs, records concatenated. **Field order ✓, units ✓ (mm for the two
geometry fields, kg for the two masses), comment character ✓, multi-record files ✓, blank lines
non-significant ✓, extra data columns tolerated ✓.**

**The `(0, 0)` prepend is also the reference behaviour**, not a project invention: OpenRocket's RASP
loader inserts a zero-thrust point at `t = 0` when the file's first point is later, for exactly the
reason given in D-64 (the first row is the first measured point after ignition, so holding it back to
`t = 0` manufactures impulse the motor never produced). Confirmed as matching the reference
implementation, not just as "plausible".

**Deviations found (robustness, not convention):**

1. **`manufacturer = tokens[6]` takes one token only.** Real `.eng` headers often carry a multi-word
   manufacturer (`Cesaroni Technology`, `AeroTech RMS`, `Loki Research`); reference parsers join
   everything from field 7 to end of line. Here the remainder is silently discarded, so a library's
   provenance metadata is truncated without warning. One-line fix:
   `manufacturer = " ".join(tokens[6:])`.
2. **A header with fewer than 7 tokens raises `IndexError`**, not a `ValueError` naming the file and
   the offending line. Some real `.eng` files omit the manufacturer field.
3. **A data row with a single token raises `IndexError` at `tokens[1]`**, same problem.

None of these is a convention invention; none moves a pin. `sim/motor_file.py` is consumed by
`sim/thrust_curve.py`, `configs/schema.py`, `apps/motor_selection/*`, `tests/test_motor_file.py`,
`tests/test_motor_pieces.py`.

**Recommendation.** Fix (1) now (silent data loss, zero risk); (2)+(3) as a small fail-fast
improvement whenever `sim/motor_file.py` is next touched. No user decision needed — this is "match the
spec more completely", not a fork.

---

## §7 Atmosphere model — ISA / US Standard Atmosphere 1976

**Verdict: CONFIRMED STANDARD, exactly. The cleanest module in the audit.**

**What the code does.** `sim/atmosphere.py::_isa_air_state` with the module-level `_LAYERS` table.
Geopotential conversion `H = r·h_msl/(r + h_msl)`, piecewise-linear temperature lapse, hydrostatic
pressure (`p_b·(T/T_b)^(-g/(L·R))` where `L ≠ 0`, `p_b·exp(-g(H-H_b)/(R·T_b))` where `L = 0`),
ideal-gas density, `a = sqrt(gamma·R·T)`, Sutherland viscosity.

**Checked term by term against US Std Atm 1976 / ISO 2533:**

| Quantity | Code | US Std Atm 1976 | ✓ |
|---|---|---|---|
| Layer bases `H_b` [m] | 0, 11000, 20000, 32000, 47000, 51000, 71000 | identical | ✓ |
| Lapse rates `L` [K/m] | -0.0065, 0, +0.0010, +0.0028, 0, -0.0028, -0.0020 | identical | ✓ |
| Base temperatures `T_b` [K] | 288.15, 216.65, 216.65, 228.65, 270.65, 270.65, 214.65 | identical | ✓ |
| Base pressures `p_b` [Pa] | 101325, 22632.06, 5474.889, 868.0187, 110.9063, 66.93887, 3.956420 | 101325, 22632.1, 5474.89, 868.019, 110.906, 66.9389, 3.95642 | ✓ |
| `R_d` [J/(kg·K)] | 287.0528 | `R*/M = 8.31432/0.0289644 = 287.0528` | ✓ |
| `gamma` | 1.4 | 1.40 | ✓ |
| `g_0` baked in | 9.80665 | 9.80665 (the standard's own fixed `g`) | ✓ |
| Effective radius `r` [m] | 6356766.0 | 6356766 (`r_0`, the 1976 standard's own value) | ✓ |
| Sutherland `mu_0`, `T_0`, `S` | 1.716e-5, 273.15, 110.4 | equivalent to the standard's `beta = 1.458e-6`, `S = 110.4` (`1.458e-6·273.15^1.5/383.55 = 1.716e-5`) | ✓ |
| Upper clamp | 86000 m MSL | the standard's own validity limit (86 km geometric ⇒ `H = 84852 m`, exactly the top of the last layer) | ✓ |

**Notable correctness detail worth preserving.** `_isa_air_state` deliberately uses the ISA's own
fixed `g = 9.80665` rather than `gravity.g()` ("the pressure column is defined for a fixed `g`") —
that is the correct reading of the standard and a frequent error elsewhere. The B13 extrapolation
clamp (`[-5000, 86000]` m MSL) is a numerical guard outside any physical flight and coincides with
the standard's own upper limit.

**Humid-air extension, also standard.** `sat_vapor_pressure` is the Alduchov-Eskridge (1996) Magnus
form (`6.1094 hPa`, `17.625`, `243.04 °C`) with the `hPa → Pa` factor written out; `virtual_temperature`
is `T_v = T/(1 - (e/p)(1 - eps))` with `eps = R_d/R_v` *computed*, not hard-coded as 0.622;
`moist_density = p/(R_d·T_v)`. All standard meteorological forms.

**Nothing to fix.** The "sounding"/"field" tiers are data interpolation, not a standard to match.

---

## §8 Gravity models

**Verdict: CONFIRMED STANDARD for `wgs84` and for the `elliptical` direction. One minor internal
inconsistency in `radial`.**

### §8.1 `wgs84` magnitude — CONFIRMED STANDARD

`sim/gravity.py::_g_wgs84` implements Somigliana normal gravity plus the second-order free-air
height correction:

```
gamma0(phi) = ge·(1 + k·sin²phi) / sqrt(1 - e²·sin²phi)
g(phi, h)   = gamma0·[1 - (2/a)(1 + f + m - 2f·sin²phi)·h + (3/a²)·h²]
```

Both expressions are verbatim the published WGS84 forms (NIMA TR8350.2 §4, "theoretical normal
gravity" and the second-order height reduction). Every constant matches the published value exactly:

| Constant | Code | TR8350.2 |
|---|---|---|
| `gamma_e` | 9.7803253359 | 9.7803253359 m/s² |
| `k` (Somigliana) | 0.00193185265241 | 0.00193185265241 |
| `e²` | 0.00669437999013 | 0.00669437999013 |
| `a` | 6378137.0 | 6378137.0 m |
| `f` | 1/298.257223563 | 1/298.257223563 |
| `m = omega²a²b/GM` | 0.00344978650684 | 0.00344978650684 |

This is a real reference formula, not a simplified stand-in mislabelled as standard. Two documented
simplifications: `phi` is frozen at the launch latitude (flat-range assumption), and `h` is MSL
rather than height above the ellipsoid (geoid-ellipsoid separation ignored, "far below the model's own
error"). Both are stated in the docstring and in `architecture.md` §13 — acceptable and labelled.

### §8.2 `elliptical` direction — CONFIRMED STANDARD

`_R_chi` is Euler's formula for the normal-section radius of curvature in azimuth `chi`:
`1/R_chi = cos²chi/M + sin²chi/N` with `M = a(1-e²)/(1-e²sin²phi)^1.5` (meridional) and
`N = a/sqrt(1-e²sin²phi)` (prime vertical) — textbook geodesy (Euler/Meusnier), with the WGS84
constants reused rather than duplicated. ✓

### §8.3 Minor inconsistency: `_g_radial` uses AGL, `_g_wgs84` uses MSL

`_g_radial` computes `g0·(R_e/(R_e + h))²` with `h = altitude_agl(y, p)`, i.e. the launch site is
treated as being at radius `R_e` regardless of `Site.h0_m`; `_g_wgs84` uses `altitude_msl`. For a site
at 1000 m elevation the two models therefore disagree about the reference radius by 1000 m
(≈ 3·10⁻⁴ g). The docstring justifies the operand choice (`p.R_e` is "the geocentric falloff radius")
but not why the altitude differs from the sibling model's.

**Standard?** There is no single "standard" for an inverse-square flat-range model — `radial` is
itself an idealisation. The point is internal consistency, not a literature mismatch.

**Cost to fix.** One line (`altitude_msl` instead of `altitude_agl`) — but it **moves pins** for any
scenario with `gravity.model = "radial"` and `Site.h0_m != 0`. Given that `wgs84` exists and is the
one with a real reference, the better answer is probably documentation, not a code change.

**Recommendation.** Document, do not change. Flag to the user as an informational item.

---

## §9 Jorgensen / Hoerner large-alpha extension (Step 112, D-120)

**Verdict: mixed. The normal-force and axial-force structures CONFIRMED STANDARD; the moment
structure is INVENTED (documented as "not paper-verified"); the `eta` / `C_dn` / `C_x180` values are
UNPINNED against the source (QA-9).**

**What the published method is** (Jorgensen TR R-474 eqs. 2.11/2.12/2.18/2.19; TN D-7228 eq. 1;
transcribed in the project's own `dev/docs/latex/research/jorgensen-params-findings.md` §3):

```
C_N = (A_b/A_r)·sin(2a)·cos(a/2)  +  eta·C_dn·(A_p/A_r)·sin²a
C_A = C_A(a=0)·cos²a              (0..90 deg)
    = C_A(a=180)·cos²a            (90..180 deg)
C_m = [(V - A_b(l - x_m))/(A_r·d)]·sin(2a)·cos(a/2)
      + eta·C_dn·(A_p/A_r)·[(x_m - x_c)/d]·sin²a
```

with `A_b` base area, `A_p` planform area, `A_r` reference area, `V` body volume, `l` body length,
`x_m` the moment reference station, `x_c` the planform-area centroid station, `d` reference diameter,
`eta` the finite-length crossflow drag factor (Fig. 4), `C_dn` the cylinder crossflow drag
coefficient (Fig. 1).

**Item-by-item comparison with `sim/aero.py::_jorgensen_extend`:**

| Term | Code | Published | Verdict |
|---|---|---|---|
| `C_z` potential | `(S_base/S)·sin(2a)·cos(a/2)` with `S_base → S` by default | `(A_b/A_r)·sin(2a)·cos(a/2)` | ✓ **matches** (`S_base` is `A_b`; the default `S_base = S` is correct for a non-boat-tailed body whose reference area is the max cross-section) |
| `C_z` crossflow | `eta·C_dn·(S_p/S)·sin(a)·|sin(a)|` | `eta·C_dn·(A_p/A_r)·sin²a` | ✓ **matches**, with `sin²` replaced by the odd extension `sin·|sin|` so the term is antisymmetric in `alpha` — a necessary and correct generalisation (the published form is stated for `alpha >= 0` only) |
| `C_x` | `x0·cos²a` for `|a| <= 90°`, `-x180·cos²a` beyond, with `C_x180` a magnitude | `C_A(0)cos²a` / `C_A(180)cos²a` with the sign carried by the datum | ✓ **matches** (code makes the sign explicit instead of implicit) |
| `C_m` potential | `cm_e·Z(a)/Z(a_e)` — the table's own `C_m` at the alpha edge, rescaled by the potential shape ratio | `[(V - A_b(l - x_m))/(A_r·d)]·sin(2a)cos(a/2)` — a **geometric** coefficient from body volume, base area and the moment reference station | ✗ **INVENTED** |
| `C_m` crossflow | `(l_pc - lp_e)·Cz_cf/d_ref` | `eta·C_dn·(A_p/A_r)·[(x_m - x_c)/d]·sin²a` | ✓ **matches**, including the sign: the code's convention is sign-flipped relative to standard (§1.1), so `(x_m - x_c)` correctly becomes `(x_c - x_m) = (l_pc - lp_e)`. Checked algebraically |
| Blend into the clamped values | smoothstep over `oob_blend_deg` | no blend in the source (the method is used over the whole range) | ✗ invented, but a pure numerical-continuity device; step notes label it "not paper-verified" |
| `alpha > 90°` sign of the potential term | follows the printed `sin(2a)cos(a/2)` (negative there) | the research note explicitly says "I could not retrieve the exact sign/absolute-value convention for alpha > 90 deg … Verify in TN D-6996 / R-474 sec. 2.1 before implementing" | ✗ **unverified assumption**, already flagged (QA-13: near ±180° the extension "stabilises" tail-first flight, which a fin-stabilised body is not) |

**So the formula structure is genuinely Jorgensen's for `C_N` and `C_A`, and genuinely Jorgensen's for
the crossflow half of `C_m`, but the potential half of `C_m` is a project-invented continuation.**
That is the substantive finding of this section — and it is avoidable: `(V - A_b(l - x_m))/(A_r·d)` is
built from quantities the user already has to supply for a real vehicle (body volume, base area,
overall length) and one the code already carries (the moment reference station = the CP station
`l_p`). The invented form makes the extension inherit whatever the table's edge `C_m` happens to be —
and since the table's `C_m` already mixes potential and viscous effects, it is then rescaled by a
pure-potential shape and a crossflow term is added *on top*, double-counting the crossflow content of
the edge value.

**Why the project deviated.** `dev/docs/step-112-notes.md` § "Model choices (not paper-verified)" and
D-120 / architecture-35 §35.6. The reason is scope: the geometric coefficient needs body volume and
base area, which `Params` does not carry (`Aero.S_p`, `Aero.l_pc`, `Aero.S_base` were added, but not
`V` or `L_total`), and the step was explicitly a numerical-robustness fix for the RK45 stall in
tail-first descent (`dev/docs/diagnosis-rk45-v2-table.md`), not an aerodynamics-fidelity step.

### §9.1 UNPINNED: `eta`, `C_dn`, `C_x180` against the published source (QA-9)

- `_ETA_LAM`/`_ETA_VAL` (`sim/aero.py` lines 136-137) are a **third-party hand digitisation** of
  TR R-474 Fig. 4, not Jorgensen's own numbers — the research note states this explicitly and names
  the secondary source (an `hpr_aero` Rust crate). The project's own tests
  (`test_analytic_at_90_deg`, `test_moment_arm_correction`) rebuild `eta` *from* `_ETA_LAM`/`_ETA_VAL`,
  so "any table edit passes" (QA-9). The two cross-checks that exist are reassuring (Jorgensen's own
  Fig. 6 start values 0.68/0.70 for `L/d` 10/12 match the digitised 0.685/0.701) but are not in a
  test.
- `C_dn = 1.2` is labelled `UNVERIFIED` in the code; the Mach/Re dependence (transonic peak 1.6-2.0,
  supercritical drop to 0.15-0.30) is out of scope. The code cites "backlog B42" — **which does not
  exist in the tracker** (see §12.6).
- `C_x180 = 0.0 → C_x(0)` is labelled `UNVERIFIED` and the research note calls this default
  "not conservative".
- `eta` is taken as `S_p/d_ref²` in place of `L/d`. For a cylinder of length `L` and diameter `d`,
  `S_p = L·d`, so `S_p/d² = L/d` exactly — correct for a pure cylinder, an over-estimate of `L/d` for
  a body with a tapering nose (the planform area is less than `L·d`, so `S_p/d²  < L/d`, giving a
  slightly conservative, lower `eta`). Worth one sentence of documentation; not a gap.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(a) status quo** | works, stalls fixed, everything labelled `UNVERIFIED`/"not paper-verified" in code and notes | the `C_m` extension is not the literature method; no test ties `eta`/`C_dn` to any source; the `alpha > 90°` sign is an open assumption | 0 |
| **(b) pin the digitised tables + document provenance** — add a test asserting `_ETA_VAL` against the values transcribed in `jorgensen-params-findings.md`, plus the Fig. 6 cross-check (0.685/0.701 at `L/d` 10/12) | closes QA-9 at near-zero cost; makes an accidental table edit fail; no pin movement | still a secondary source — it pins *provenance*, not Jorgensen's own numbers | **S (do this regardless)** |
| **(c) replace the invented `C_m` potential term with the published geometric coefficient** — add `Aero.V_body` and `Aero.S_base`/`L_total`, compute `(V - A_b(l - x_m))/(A_r·d)` | the real Jorgensen moment equation; removes the crossflow double-count at the edge; makes the extension independent of whatever the table's edge `C_m` is | 2 new required fields for `jorgensen` mode; **moves the out-of-range pins** in `tests/test_aero_oob.py`; needs the `alpha > 90°` sign question answered first | M |
| **(d) primary-source verification pass** — read TR R-474 printed p. 77 (Fig. 4) and TN D-6996 for `C_A(180°)` and the `alpha > 90°` convention, from page images | removes the last three `UNVERIFIED` labels; answers (c)'s blocker | needs a `research` agent with working Firecrawl credits (the 2026-10-19 session hit both Exa and Firecrawl limits — see §5 of the research note for the exact URLs and page numbers) | M, external |

**Recommendation.** (b) immediately (it is cheap and closes a live QA finding). (d) next, as a
`research` task with the URLs the note already lists — it is the prerequisite for (c). (c) only after
(d), bundled with §2 option (b) so that `C_A(180°)` and the axial form land together.

---

## §10 Quaternion convention for the blocked 3D phase (Step 28, `26cbf1b`)

**Verdict: CONFIRMED STANDARD and internally consistent. One convention-*direction* choice worth
folding into the pending user review, plus the already-known `I_a` question.**

**What the code does** (`sim/quaternion.py`, verified algebraically rather than taken from the
docstring):

| Aspect | Code | Standard | ✓ |
|---|---|---|---|
| Component order | **scalar-first** `(q0, q1, q2, q3)` | scalar-first is the aerospace/Wertz convention (JPL/`scipy.spatial.transform` use scalar-last) | ✓ standard, and the docstring says so |
| Product | **Hamilton**: `w = w1w2 - x1x2 - y1y2 - z1z2`, `x = w1x2 + x1w2 + y1z2 - z1y2`, … | the Hamilton product exactly (the JPL convention reverses the vector-part cross term) | ✓ verified term by term |
| Rotation direction | `rotate_vector(q, v_body) = v_inertial`, `to_dcm(q) = R_body→inertial` | both directions are used in the literature; **most missile/flight-dynamics texts define `q` as inertial→body (`q_{B/I}`)** | ⚠ see below |
| DCM formula | `(q0² - |qv|²)I + 2·qv·qvᵀ + 2q0·[qv]×` | the standard closed form for an *active* (vector) rotation; matches `rotate_vector`'s `q⊗(0,v)⊗q*` | ✓ verified element (0,1) `= 2(q1q2 - q0q3)` matches both routes |
| Kinematics | `q̇ = 0.5·q ⊗ (0, omega_body)` | correct **for a body→inertial quaternion** (`Ṙ_{b→i} = R_{b→i}[omega_b]×` ⇒ right-multiplication by the incremental quaternion). The inertial→body convention would require `q̇ = 0.5·(0, omega_b) ⊗ q` | ✓ verified all four components against the Hamilton product |
| Euler sequence | 3-2-1 (yaw-pitch-roll) intrinsic z-y'-x'', `q = q_z(psi) ⊗ q_y(theta) ⊗ q_x(phi)`, `R_{b→i} = Rz·Ry·Rx` | the standard aerospace sequence | ✓ |
| `to_euler` extraction | `theta = asin(-R[2,0])`, `phi = atan2(R[2,1], R[2,2])`, `psi = atan2(R[1,0], R[0,0])` | the standard 3-2-1 extraction from `R_{b→n}` | ✓ verified against `Rz·Ry·Rx` symbolically |
| 2D reduction | pitch-only `q = (cos(theta/2), 0, sin(theta/2), 0)` ⇒ `to_dcm`'s `(x,z)` block `= [[c, s], [-s, c]]` | exactly `frames.R_body_to_inertial(theta)` | ✓ the 2D and 3D attitude conventions agree bit-for-bit in form |
| Euler's equations (research note §4) | `I_a·ω̇x = Mx`; `I_t·ω̇y - (I_t - I_a)ωzωx = My`; `I_t·ω̇z + (I_t - I_a)ωxωy = Mz` | `I_i·ω̇_i + (I_k - I_j)ω_jω_k = M_i` for `I = diag(I_a, I_t, I_t)` | ✓ verified all three |

**The one convention risk worth folding into the pending review.** The project's `q` is
**body→inertial**. That is a legitimate, internally consistent, documented choice (and it had to be,
to match the existing 2D `R_body_to_inertial`). But the majority convention in missile/launch-vehicle
literature and in most reference implementations is the **opposite** direction (`q_{B/I}`,
inertial→body — e.g. Zipfel "Modeling and Simulation of Aerospace Vehicle Dynamics", and the
quaternion blocks of most GNC codebases). The practical consequence is narrow but real: **any
quaternion, DCM, kinematic equation or test vector copied from an external source must be
conjugated** before it can be compared against this module, and `q̇ = 0.5·q ⊗ (0, ω)` becomes
`q̇ = 0.5·(0, ω) ⊗ q` under the other convention — a silent, plausible-looking sign error that
produces a slowly diverging attitude rather than an obvious failure.

Nothing in the code is wrong. The ask is a **documentation/guard** item, not a fix:

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(a) keep body→inertial, add a loud "conversion required" note** at the module docstring and in whatever 3D ticket imports external attitude data; add one test that asserts `to_dcm(q).T == R_inertial→body` so the relationship is explicit | zero change to shipped code; 2D/3D stay aligned; the trap is documented where it bites | relies on a reader noticing | **XS** |
| **(b) switch to inertial→body** (`q_{B/I}`) | matches the majority of missile literature and copied-in reference material | would invert the 2D `frames.py` relationship or create a 2D/3D mismatch — strictly worse; 34 lines / `tests/test_quaternion.py` + `test_dynamics3d.py` churn for no physics gain | S, not worth it |

**Recommendation.** (a), folded into the **already-pending** user review of
`dev/docs/latex/research/3d_equations_of_motion.md` (currently blocked on the `I_a` question). Both
items are "confirm a convention before Phase 3 code is written", and they should be asked together:

1. `I_a` — the axial (roll) MOI: a new required input with no default; the note's §7.1 lists the
   options and deliberately does not choose (the suggested textbook placeholder is
   `I_a ≈ ½·m·r²` for a uniform cylinder, which *is* the standard solid-cylinder result).
2. The quaternion direction convention (this section) — confirm body→inertial so that any
   externally-sourced attitude data is conjugated on the way in.

**No invented-convention gap found in the 3D scaffold.** `sim/state3d.py` (13-component
`[r, v, q, omega]`, `omega` in body axes) and `sim/dynamics3d.py` (`m·v̇ = W + R(q)(T + A)`, `q̇ = 0`,
`ω̇ = 0` at Step 29) are consistent with the 2D code and with the research note.

---

## §11 Units and `g0` / `I_sp`

**Verdict: CONFIRMED STANDARD.**

- **`I_sp` in seconds with standard gravity.** `Params.g0 = 9.80665` (the CGPM-defined standard
  gravity); `sim/thrust_curve.py::mass_flow` returns `-T/(I_sp·g0)`; `sim/mass.py::isp_from_impulse`
  computes `I_sp_eff = J/(m_prop·g0)`. That is exactly the standard definition `I_sp = F/(ṁ·g0)`
  [s] used by NAR/TRA, ThrustCurve.org and every propulsion text. ✓
- **`g0` is one shared constant**, not duplicated: `params.Params.g0` for propulsion and the gravity
  reference, `atmosphere._G_ISA = 9.80665` separately and deliberately for the ISA pressure column
  (the standard's own fixed `g`, correctly *not* routed through `gravity.g()`). Two occurrences of the
  same number for two different standards' definitions — correct, and documented as such. ✓
- **Nozzle pressure-thrust correction.** `T = T_ref + A_e·(p_ref - p_amb)` (`sim/thrust_curve.py`),
  applied only while `T_ref > 0`. This is the standard rocket thrust equation's pressure term
  (`F = ṁ·v_e + A_e(p_e - p_amb)`) in the form appropriate for correcting a stand-measured curve to
  altitude. Units SI throughout; `p_ref` defaults to 101325 Pa. ✓
- **Mass flow from the *stand* curve, not the pressure-corrected thrust** (Step 98, D-112): correct —
  the pressure term changes thrust, not propellant flow. ✓ This was B27 item 3 and is now right.
- **Angles: "degrees in `Params`, radians at first use".** `misalign_deg`, `lat0_deg`, `lon0_deg`,
  `azimuth_deg`, `rail_angle_deg`, `dir_deg`, `alpha_deg` (table column), `oob_blend_deg` — all
  converted at the point of use via `np.radians`. Consistent and conventional. ✓
- **`uniform_cylinder_I = m(3r² + L²)/12`** — the standard transverse MOI of a solid cylinder about
  its centroid. ✓
- **`combine()`** — mass-weighted centroid plus parallel-axis theorem, using `math.fsum`. Standard,
  and the deliberate non-bit-equality with `moment_of_inertia` is documented (F3/F4). ✓

**One unit-convention item the user should know about, not a bug.** The RASP header gives
`prop-weight` and `total-weight` in **kg** (mass, despite the name), and the code reads them as kg
(`m_prop`, `m_total`) — correct. Some older `.eng` files in circulation use grams; there is no
in-band way to tell. A sanity check (`0 < m_prop < m_total`, and `m_total` plausible for the stated
diameter/length) at load time would catch a gram-unit file before it silently produces a
1000×-too-light rocket. Cheap, no pin impact, worth a backlog line.

---

## §12 Additional findings not in the brief

### §12.1 GAP — the aero pitching moment is over-determined: `l_p` **and** `C_m` are both inputs

**This is the highest-impact finding in the audit other than `C_m`'s sign. Verdict: INVENTED
(inherited from the approved paper); no decision record found; it can silently double-count the
static moment in user-supplied CFD data.**

**What the code does.** `sim/dynamics.py` sums two *independent* aerodynamic moment contributions:

```
aA   = (-l1, u_B)                     # l1 = l_p - l_g(t): the CP/"reference point" arm
M_aero   = _cross_y(aA, aero_force)   # = -q·S·( l1·C_z + u_B·C_x )
M_moment = aero_moment_y(...)         # = -q·S·d_ref·C_m
M_y      = M_thrust + M_aero + M_moment
```

so the total aero moment about the CG is `q·S·[ (l_g - l_p)·C_z - u_B·C_x - d_ref·C_m ]`. This is a
character-for-character match to the approved paper
(`dev/docs/latex/sections-ai/rocket-2d.tex` eq. `eq:eom_rot_expanded`:
`qS[-r_g C_x + (l_g - l_p)C_z - c·C_m]`, with `u_B ≡ r_g`) — verified, so this is **not** a
code↔paper discrepancy. The problem is the *definition* the paper gives: §geometry says

> `p` — aerodynamic reference point (centre of pressure), where `A_f` acts **and about which `A_m` is
> taken**.

**Why that is self-contradictory against the standard.** The centre of pressure is *by definition* the
station at which the aerodynamic pitching moment vanishes. If `p` is the CP, then `C_m ≡ 0` and the
entire `A_m` term is dead weight. If `C_m` is non-zero, then `p` is **not** the CP — it is a moment
reference station, and the quantity `(l_p - l_g)/d_ref` that `sim/report.py::static_margin_cal`
reports as "static margin in calibers" is not the static margin.

**What the actual standard is.** Every source the project would want to match supplies **one** of the
two representations, never both as independent inputs:

- **CFD / wind tunnel / RASAero**: give `C_N`, `C_A`, `C_m` about a **declared moment reference
  station `x_ref`**. The CP is then a *derived* quantity, `x_cp = x_ref - C_m·d/C_N` (standard sign).
- **Barrowman / OpenRocket techdoc §3.6**: give `C_N_alpha` and `X_cp` per component, sum to a
  whole-vehicle `X_cp`, and compute the moment as normal force × `(X_cp - X_cg)`. No separate `C_m`
  exists in the Barrowman formulation at all.

The physically correct decomposition, if you want both a station and a moment coefficient, is:

```
M(about CG) = [moment about x_ref]  +  [normal force at x_ref] × (arm from CG to x_ref)
```

i.e. the arm must run from the CG to **`x_ref`, the moment reference station** — not to the CP. The
code's structure is exactly this and is therefore **correct if and only if `l_p` is read as
`x_ref`**. The column is named `l_p_m` = "CP station from the nose", so it is not read that way.

**The two plausible user readings and what each breaks:**

| User reading of `l_p_m` | Dynamics | `static_margin_cal` | `stability_check` / `cm_slope_series` |
|---|---|---|---|
| "the CP station, as the column name says" + a non-zero `C_m` from a CFD run whose moment reference was something else (nose tip, or the CAD origin) | **wrong** — the static moment is counted twice, once through the `l_p` arm and once through `C_m` | right | right by accident |
| "the moment reference station of my `C_m` column" (e.g. `l_p_m = 0.0`, the nose tip, which is the most common CFD choice) | **right** | **wrong** — reports `(0 - l_g)/d_ref`, a large *negative* "margin", i.e. a false "unstable" verdict | **wrong** — `dC_m/dalpha` about the nose is large and of the opposite sign to the true stability criterion |

Note that `Aero.l_p = 0.0` is also the *off switch* for station mode, so the second reading is not
even expressible: a user cannot say "my moment reference is the nose tip".

**Evidence this is live, not theoretical.** `data/aero/example_v2.csv` — the repo's own reference v2
table — supplies `l_p_m = 1.18` (a plausible CP station) **and** a non-zero `C_m` slope
(`∓0.0873` at `∓10°`, i.e. a synthetic `C_m_alpha = 0.5 /rad`). Both contributions are restoring and
both are summed. Backlog **B31** already observed the two terms competing in `example.csv` ("the table
stays stable only thanks to the `l1` arm, the CP being aft of the CG") but framed it purely as a sign
problem. It is also an over-determination problem.

Also note `stability_check`'s criterion itself: it warns on a negative margin **or** a negative
`dC_m/dalpha` in the code convention, treating them as two independent stability tests. In the
standard formulation there is exactly one criterion, and for this model it is
`d/dalpha[ (l_g - l_p)C_z - d_ref·C_m ] < 0` (nose-down restoring) — the *combined* slope. Testing the
two halves separately can report "stable" when the sum is not, or vice versa.

**Cost to fix.** `l_p` appears in 186 lines; `C_m` in 264 lines / 34 files. But the fix is mostly
semantic, not arithmetic:

| Axis | Estimate |
|---|---|
| Code changed | `sim/aero.py` (column semantics + validation), `sim/report.py` (`static_margin_cal`, `stability_check`, `cm_slope_series`), `configs/rockets/_TEMPLATE_rocket.py` docs, `data/aero/*.csv` headers |
| Numeric pins | **Option (A) below: none** (pure documentation + a derived-CP diagnostic). Option (B): moves the `l_p`/`C_m` pins in `tests/test_aero_v2.py`, `test_aero_fb.py`, `test_report.py`, `test_scenario_sweep.py`, plus any flight pin on a v2 table |
| Approved LaTeX | **Yes for both options** — `rocket-2d.tex` §geometry's definition of `p` needs one sentence changed ("aerodynamic *moment reference* point, where `A_f` is taken to act and about which `A_m` is taken; the centre of pressure is the derived station `l_p - C_m·c/C_z`"). `analysis.tex`'s static-margin discussion follows |

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(A) relabel: `l_p` is the moment reference station `x_ref`; CP becomes derived** — keep the arithmetic exactly as is, rename the column/field semantics in docs, allow `x_ref = 0` (nose), and change `static_margin_cal` to compute `x_cp = x_ref - C_m·d/C_z` first and report `(x_cp - l_g)/d_ref`; single combined stability criterion | **zero change to the dynamics ⇒ zero pin movement**; matches how CFD/RASAero actually export data; removes the double-count by construction (you can no longer supply "the CP" and a moment about something else); fixes the diagnostics; the off-switch problem disappears | the field name `l_p` becomes a misnomer unless renamed (`l_mref`); the paper sentence must change; `static_margin_cal` divides by `C_z`, undefined at `alpha = 0` — needs the slope form `x_cp = x_ref - (dC_m/dalpha)·d/(dC_z/dalpha)` | **S-M; recommended** |
| **(B) enforce the CP reading: require `C_m == 0` whenever `l_p`/`l_p_m` is given** (and conversely require `l_p == 0` when `C_m ≠ 0`, with the arm then coming from the derived CP) | the column name stays true; no ambiguity possible; the simplest mental model | throws away the ability to use a CFD table as exported — the user would have to pre-convert `C_m` into a CP station, exactly the work B33/D-110 moved *into* the code; moves pins (`example_v2.csv` would need `C_m = 0`) | M |
| **(C) status quo + a documentation warning** | zero work | leaves a silent double-count path in the one input format the user is about to populate with real CFD data for two real vehicles (architecture-35 §35.8 item 3 explicitly asks the user for "`C_A, C_N, C_m` and CP station from the nose `l_p`" — **both**, which is precisely the ambiguous combination) | 0 |

**Recommendation.** **(A)**, and soon: architecture-35 §35.8 is about to request exactly the ambiguous
pair of inputs from the user for two real vehicles. (A) costs no pin movement, makes the request
unambiguous ("give me your CFD moment reference station and `C_m` about it"), and turns the CP and the
static margin into derived outputs — which is what every standard tool does. The paper edit is one
sentence and needs the user's explicit permission (LaTeX is read-only by project rule).

### §12.2 `AeroCoeffs.C_x` / `C_z` hold `C_A` / `C_N`, which have the opposite sign

**Verdict: naming only, no physics gap. Worth a rename.**

`AeroCoeffs` names its fields `C_x`, `C_z` and comments them "axial-force coefficient (today's
`C_A`)" / "normal-force coefficient (today's `C_N`)", and `forces.py` applies them as
`A = [-q·S·C_x, -q·S·C_z]`. In the standard body-axis notation `C_X` and `C_Z` are the force
components *along* `+x_body`/`+z_body`, so `C_X = -C_A` and `C_Z = -C_N`. The code's fields hold
`C_A`/`C_N` (the correct physical quantities, §1.4) under the names `C_x`/`C_z` (which standardly mean
the negatives). Source for the distinction: Jorgensen TR R-474 §2 (`C_A`, `C_N`); Etkin / Stevens &
Lewis (`C_X`, `C_Z`). `Params.Aero` has the same `C_x`/`C_z`/`C_m` field names, inherited from the
Step-50 rename of `A_x`/`A_z`/`A_m`.

**Cost.** Pure rename, pin-safe, but it touches `Aero` field names (so every config and template) —
`C_x`: ~155 `d_ref`-scale breadth. Realistically: do it only if and when §1.1 option (b) or (c) is
done, in the same step, so configs change once.

### §12.3 The `linearized` model uses `sin(alpha)`, not Barrowman's linear `alpha`

**Verdict: INVENTED (well documented), and defensible — but it is a deviation worth naming.**

`sim/aero.py::_linearized_coeffs` computes `C_z = C_N_alpha·sin(alpha)` and
`C_m = C_m_alpha·sin(alpha)`, where the linear theory (Barrowman; OpenRocket techdoc §3.2;
`main.tex`'s own linear formula) specifies `C_N = C_N_alpha·alpha`. The docstring gives a thorough
justification: `atan2`-based `alpha` is discontinuous at its branch cut (`u < 0`, `w` crossing zero),
which an unperturbed flight coasting through `V = 0` at apogee lands exactly on, and the resulting
sign flips collapsed `solve_ivp`'s step control (observed: minutes vs ~1 s). `sin(alpha)` removes the
discontinuity and is more physical at large alpha (`sin(pi) = 0`, correctly zero net side force
flying exactly tail-first for a body of revolution).

**Assessment.** The deviation is <0.4% at 8.6°, is documented in detail, and `sin(alpha)` is itself a
standard slender-body form (it is the small-alpha limit of Jorgensen's own `sin(2a)cos(a/2)`). I would
*not* change it. But it should be stated in the user-facing docs as "the linearized model is
`C_N_alpha·sin(alpha)`, not `C_N_alpha·alpha`", because a user comparing against OpenRocket/RASAero
at 15-20° will see a small systematic difference and should know why.

### §12.4 Dryden turbulence — scales/intensities standard, realization substituted

**Verdict: scale lengths and intensities CONFIRMED STANDARD; the realization method is a documented
substitution.**

`sim/wind.py::_dryden_scales` implements the MIL-F-8785C / MIL-HDBK-1797 low-altitude forms
`L_u = h/(0.177 + 0.000823h)^1.2` [ft] and `sigma_u = sigma_w/(0.177 + 0.000823h)^0.4` with
`sigma_w = 0.1·W20` and `W20` read at the spec's own 20 ft (6.096 m) reference height; above 2000 ft
the isotropic `L = 1750 ft`. All of that is verbatim the MIL spec. The 1000-2000 ft band, which the
spec leaves undefined, is linearly interpolated with the gap documented in the code.

The **realization** is a frozen sum of sinusoids with weights taken from the Dryden PSD, renormalised
so the realised variance is exactly `sigma²`, instead of the spec's filtered-white-noise transfer
function. This is a deliberate determinism choice (architecture.md §26, `lru_cache`'d per seed) and is
documented; a finite set of tones is band-limited and periodic where the standard realization is not.
Not an invented *convention* — an invented *realization* of a standard spectrum. No action beyond
keeping the caveat visible in the report/paper.

### §12.5 `_g_radial` altitude reference — see §8.3

### §12.6 `sim/aero.py` cites a backlog item that does not exist

`sim/aero.py` line ~140: "Mach/Re dependence (transonic peak 1.6-2.0, supercritical drop) is out of
scope (**backlog B42**)". `status_query.py search "B42"` returns no match in either `dev/status.json`
or `dev/status-archive.json`; `backlog_ideas` ends at **B33**. So the one `UNVERIFIED` physical
constant in the Jorgensen extension (`C_dn = 1.2`) has no tracked follow-up. Fix: either create the
backlog item (recommended — it is a real fidelity gap, see §9.1) or correct the citation. Zero cost,
pure traceability.

### §12.7 Propellant MOI placeholder `I_p ∝ m_p`

`sim/mass.py::moment_of_inertia` takes `I_p(t) = (I_d/m_d)·m_p` (or `I_p_spec·m_p` when set) — i.e.
the propellant is assumed to keep a constant specific MOI about its own centroid as it burns. This is
`main.tex`'s own `\todo`, cross-referenced to backlog B24 (real grain geometry), and is explicitly
labelled a placeholder in the docstring. **Not a convention invention** — an acknowledged modelling
placeholder with a tracked replacement. No standard is being misrepresented. The two-lumped-mass
decomposition itself (dry structure + remaining propellant, parallel-axis theorem) is the standard
first-order treatment. Noted here only so the user sees it on the same list; B27 item 2 already
flags that the paper's *linear* `l_g`/`I` models and the code's two-lump model agree only at the
endpoints.

### §12.8 Apogee predictor uses `v_z` only

`sim/control.py::_proportional_airbrake` predicts `h + v_z²/(2g)`, the drag-free ballistic rise using
the **vertical** velocity component only. That is the standard flight-computer estimator (and is
labelled as such), and ignoring the horizontal component is correct for a predicted *apogee altitude*.
The docstring correctly identifies it as a deliberate upper bound (drag ignored). **No gap.**

### §12.9 Wind direction and shear — CONFIRMED STANDARD

- `Wind.dir_deg` is "meteorological, from North, clockwise" and the velocity vector is built as
  `-W·(unit vector toward dir)` — the standard meteorological convention (direction the wind blows
  *from*). ✓
- Power-law shear `W(h) = W_ref·(h/h_ref)^0.143` with `h_ref = 10 m`: the exponent 1/7 and the 10 m
  reference height are the standard open-terrain values (and `h` is correctly AGL, not MSL, because a
  boundary-layer profile is referenced to the terrain). ✓
- Clamped below `h_ref` instead of extrapolated to zero at the ground — a documented, sensible choice
  (the power law is not valid in the roughness sublayer). ✓

---

## §13 Open questions for the user (morning list)

Ordered by how much they change if answered "follow the standard".

1. **§12.1 — What is `l_p_m`/`Aero.l_p`: the centre of pressure, or the moment reference station of
   your `C_m` column?** This must be settled *before* architecture-35 §35.8 item 3 asks you for
   "`C_A, C_N, C_m` and CP station from the nose `l_p`" for the two real vehicles — as written, that
   request invites a double-counted static moment. Recommended answer: it is the moment reference
   station; CP and static margin become derived outputs (option A, no pin movement).
2. **§1.1 — Do you want the real `C_m` sign convention now (D-111 option b), or the cheaper rename
   (option c)?** Option (b) moves every moment pin and edits the approved paper; option (c) removes
   the "standard symbol, non-standard meaning" trap at no pin cost.
3. **§2 — Should `C_A(alpha)` become the published `cos²alpha` form?** Option (b) moves pins for
   *every* non-zero-alpha flight, not just tail-first ones. Option (c) (plateau + `cos²` outside) is
   pin-free below the plateau.
4. **§9 — Approve a `research` task to read Jorgensen TR R-474 Fig. 4 / TN D-6996 from page images?**
   The 2026-10-19 session hit Exa and Firecrawl limits; §5 of
   `dev/docs/latex/research/jorgensen-params-findings.md` lists the exact URLs and printed page
   numbers. This is the prerequisite for removing the three `UNVERIFIED` labels and for the `alpha >
   90°` sign question (QA-13).
5. **§10 — Confirm the quaternion direction convention (body→inertial) together with the pending
   `I_a` review**, so that Phase 3 code and any externally-sourced attitude data are conjugated
   correctly on the way in.
6. **§1.3 — May `c_mq` be flipped by `cm_convention="standard"` like the table column already is?**
   Bit-for-bit safe today (no config combines the two). One line.
7. **§6 — May `manufacturer` be read as the full remainder of the header line?** One line, silent data
   loss today.

**Open factual questions I could not resolve from the repo + domain knowledge** (noted and moved past,
per the brief):

- Jorgensen's exact sign/absolute-value convention for the potential-flow term at `alpha > 90°`
  (needs TN D-6996 §2.1 page images; the project's own research note states the same blocker).
- The published `C_A(alpha = 180°)` procedure and numbers for conical/ogive noses with flat bases
  (TN D-6996; TM X-1658 has measured data to `alpha = 180°`).
- Whether `_ETA_VAL`'s third-party digitisation of TR R-474 Fig. 4 is accurate to the stated ±0.005
  (needs the figure itself).

---

## §14 Recommended order of work

| # | Item | Pins move? | LaTeX? | Size | Needs user "yes"? |
|---|---|---|---|---|---|
| 1 | §12.6 create/correct the `B42` backlog reference | no | no | XS | no |
| 2 | §9.1 (b) pin `_ETA_LAM`/`_ETA_VAL` against the research note; closes QA-9 | no | no | S | no |
| 3 | §1.3 flip `c_mq` under `cm_convention="standard"` | no | no | XS | informational |
| 4 | §6 (1) full-remainder `manufacturer`; (2)(3) fail-fast messages | no | no | S | informational |
| 5 | §12.1 **option (A)** — `l_p` = moment reference station, CP/static margin derived, single stability criterion | no | **yes** (1 sentence in `rocket-2d.tex` §geometry, follow-on in `analysis.tex`) | S-M | **yes** |
| 6 | §9 (d) `research` pass on TR R-474 / TN D-6996 page images | no | no | M, external | **yes** |
| 7 | §1.1 **option (b)** — standard `C_m`/`C_mq` sign throughout, delete `cm_convention` (or option (c), the rename, if (b) is still too expensive) | **yes** | **yes** | M | **yes** |
| 8 | §2 + §9 (c) — `cos²alpha` axial form with a real `C_A(180°)`, and the published Jorgensen moment coefficient | **yes** | **yes** | M-L | **yes** |
| 9 | §12.2 rename `C_x`/`C_z` → `C_A`/`C_N` (bundle into 7) | no | yes | S | bundled |
| 10 | §3, §8.3, §11 (gram-unit sanity check), §12.3 — documentation-only clarifications | no | no | S | no |

Items 1-4 are "match the spec more completely" and need no fork decision. Item 5 is the one I would
push hardest for, because it is cheap, pin-free, and it is about to be baked into the real-vehicle
data request. Items 7-8 are the genuine re-pin campaigns and should each be a dedicated step with its
own approval.
