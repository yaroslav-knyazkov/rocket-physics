# Step 118 (D-127) — axial force shape outside the 85° plateau: cos²-shaped hybrid, not the invented ramp

## Кратко (RU)

Тикет закрывает §2 аудита (`dev/docs/conventions-industry-standard-analysis.md`), опцию (c),
одобренную пользователем как D-127: **внутри плато `|alpha| <= 85°` — бит-в-бит без изменений**
(ноль сдвига пинов), **снаружи плато — форма становится `cos²`-образной** вместо прежнего линейного
по `cos(alpha)` пандуса. Формула: `r = cos(alpha)/cos(85°)` (как раньше), `f(alpha) = clip(r*|r|, -1,
+1)` — одна строка кода, без отдельной ветки для плато (клип уже даёт точно `1.0` внутри плато
автоматически, проверено численно). Якоря `90°→0`, `95°→-1` сохранены бит-в-бит. Это НЕ настоящая
двухякорная форма Jorgensen (`C_A(0)cos²alpha` / `C_A(180)cos²alpha`, с `Aero.C_x180`) — та форма
(вариант b) требует второй константы и якорения в `alpha=0/180°`, не в `85°`; она явно вне рамок этого
шага (сдвигает пины, отдельное решение). Взаимодействие с §9 (true cos² в ветке Jorgensen OOB,
`_jorgensen_extend`) — **нейтральное**: эта ветка не трогается, несогласованность форм на границе
таблицы не устраняется и не усугубляется, просто обе формы теперь одного семейства ("квадрат
косинуса"), хоть и с разным якорем/масштабом. Единственная числовая переменная, которая требует
правки — допуск теста непрерывности (`3e-3 → 6e-3`), потому что наклон у квадратичной формы у края
плато ровно вдвое больше линейного. Пинов в диапазоне `(85°,95°)` не найдено ни одного (grep +
прочтение динамических tail-first тестов — они на неравенствах, не на литералах).

---

## Table of contents

- §118.1 Scope and non-goals
- §118.2 Chosen functional form
- §118.3 Why this form (and what was rejected)
- §118.4 Interaction with §9 (Jorgensen OOB branch) — confirmed neutral
- §118.5 Limitation — not Jorgensen's two-anchor form, deliberately
- §118.6 `sim/aero.py` — exact before/after
- §118.7 `sim/forces.py`, `_table_axial_factor` — confirmed no change needed
- §118.8 Tests — exact before/after
- §118.9 Pin safety — how this was checked
- §118.10 Test-impact table
- §118.11 Open questions
- §118.12 Definition of done

---

## §118.1 Scope and non-goals

**In scope:**
- `sim/aero.py`: `axial_flow_factor` (lines 160-167) — body and docstring; the comment above
  `_COS_ALPHA0` (lines 123-125) — comment only, the constant's value and name are unchanged.
- `sim/forces.py`: docstring check only (confirmed below, no edit needed).
- `tests/test_aero.py` lines 580-603: the section header comment and
  `test_axial_flow_factor_is_continuous_across_the_ramp`'s tolerance constant + a docstring explaining
  why. The other two boundary tests in this block need **no value change** (verified below).
- `tests/test_forces.py::test_airbrake_term_flips_tail_first`: verification only that no change is
  needed (it computes `expected` dynamically).

**Out of scope / do not touch:**
- `Aero.C_x180` (config field) — untouched, no new use introduced.
- `sim/aero.py::_jorgensen_extend` (lines 702-732, including its `Cx_J = x0*c2 / -x180*c2` lines
  712-716) — the table model's `table_oob="jorgensen"` branch, untouched (§118.4).
- `sim/aero.py::_table_axial_factor` (lines 170-176) — confirmed below it needs no docstring edit.
- Any LaTeX file under `dev/docs/latex/` — D-127 says none.
- Any model dispatch structure, any new parameter threaded into `axial_flow_factor`'s signature, any
  call site's call shape (`_constant_coeffs` line 573, `_linearized_coeffs` line 623, `_table_coeffs`
  line 671, `sim/forces.py` line 243) — all four stay exactly `<base> * axial_flow_factor(alpha)` /
  `_table_axial_factor(table, alpha)`, unchanged call shape, only the callee's internals change.
- The `85°`/`95°` anchor values themselves — D-127 preserves them; not reopened here.

## §118.2 Chosen functional form

Unchanged: `_COS_ALPHA0 = cos(85°)` (name, value, line 125 — no edit to this line itself).

New formula, replacing the old `f(alpha) = clip(cos(alpha)/cos(85°), -1, +1)`:

```
r = cos(alpha) / cos(85°)                  # identical definition to today's ratio
f(alpha) = clip(r * |r|, -1.0, +1.0)       # the only change: square the magnitude, keep the sign
```

**This needs no separate plateau branch.** For `|alpha| <= 85°`, `cos` is strictly decreasing on
`[0°, 180°]` (and even, so this covers negative `alpha` too), so `cos(alpha) >= cos(85°) > 0`, hence
`r >= 1`, hence `r*|r| >= 1`, and the `min(1.0, ...)` clip holds it at exactly `1.0` — the same
mechanism that already makes today's code exactly `1.0` in the plateau (clipping an over-1 ratio), just
squared first. **Verified numerically** (not asserted blind): at `alpha = math.radians(85.0)`,
`cos(alpha)` computed via `np.cos` and `_COS_ALPHA0` built via `np.radians(85.0)` give `r == 1.0`
bit-for-bit (`math.radians` and `np.radians` agree exactly at `85.0`), so `r*|r| == 1.0` exactly too —
confirmed by direct computation, see §118.9.

At `alpha = 90°`: `r = 0`, `f = 0` (unchanged anchor). At `alpha = 95°`: `cos(95°) = -cos(85°)` exactly
(co-function identity, `cos(90°+x) = -sin(x) = -cos(90°-x)`), so `r = -1` exactly, `r*|r| = -1`, clip
leaves `-1` (unchanged anchor). Beyond `95°`, `|r| > 1` so `|r*|r|| > 1`, clipped to `±1` (unchanged
"reaches -1 by 95° and stays there" behaviour). **All four of the existing tests' anchor points are
reproduced bit-for-bit** — confirmed by direct computation for every literal value in
`test_axial_flow_factor_is_one_inside_85_deg_exactly` and
`test_axial_flow_factor_zero_at_90_and_minus_one_beyond_95` (§118.9).

**Implementation note for the developer:** write this as `r * abs(r)` (not
`math.copysign(r*r, r)` or an explicit `if`/`else`) — this mirrors the existing odd-extension idiom
already used in the same file, `_jorgensen_extend`'s `sa = sin(alpha); Cz_cf = ... * sa * abs(sa)`
(line 722), for stylistic consistency within `sim/aero.py`. `r * abs(r)` and `sign(r) * min(1, r*r)`
are mathematically identical once passed through the same `min(1.0, max(-1.0, ...))` clip; prefer the
former, it is a strictly smaller diff from today's line (one `* abs(r)` inserted before the existing
clip) and needs no new branch.

## §118.3 Why this form (and what was rejected)

**Why not literal, unnormalised `cos²(alpha)`:** `cos²(85°) ≈ 0.0076`, wildly discontinuous with the
plateau's `1.0` — D-127 and the brief both require continuity at `85°`, so a literal substitution is
disqualified outright, not a close call.

**Why renormalise relative to `cos²(85°)` (i.e. `r²` with `r = cos(alpha)/cos(85°)`) rather than
relative to `cos²(0°) = 1` (i.e. plain `cos²(alpha)`, Jorgensen's own normalisation) with some other
blend into the plateau:** the task is specifically a **pure function of `alpha` alone**, anchored so
that it is *exactly* `1.0` on the plateau and continuous at its edge — any normalisation anchored at
`alpha=0` instead of `alpha=85°` reproduces the literal-`cos²` discontinuity problem at `85°` (since
`cos²(0°)=1 ≠ cos²(85°)·k` for any single scale `k` that also keeps the `90°/95°` anchors exactly where
they are) and would need an additional blend/renormalisation device *on top* — more moving parts, for a
step whose only approved goal is "cos²-shaped outside the plateau, hybrid, zero pin movement inside
it" (D-127's exact wording), not a literature-exact reproduction. Anchoring at the plateau edge itself
is the minimal device that satisfies every one of D-127's stated constraints simultaneously with no
extra tunable.

**Why "cos²-shaped" is still an honest description despite the 85°-anchor, not Jorgensen's 0°/180°
anchor:** the *functional family* is the same — the output is proportional to the square of a cosine
ratio, decaying from a maximum magnitude plateau to zero at `90°` and growing back to a reversed-sign
maximum magnitude by `95°`+, exactly the qualitative shape Jorgensen's `cos²alpha` has (fast falloff
near normal incidence, not the old form's linear falloff) — it is a renormalisation of that family to
this project's own, already-approved, already-tested plateau-and-anchor contract, not a reproduction
of Jorgensen's literal equation. §118.5 states this limitation explicitly so nobody downstream
mistakes this for "the Jorgensen formula, implemented."

**Candidate from the brief, evaluated:** the brief's own suggested form, `f = sign(r) * min(1, r²)`,
is mathematically identical to `clip(r*|r|, -1, +1)` (verified: for `r² >= 1`,
`sign(r)*min(1,r²) = sign(r)*1`, matching the clip's saturated branch with the correct sign; for
`r² < 1`, `sign(r)*r² = r*|r|`, matching the clip's unsaturated branch exactly) — adopted, just written
as the smaller, branch-free diff described in §118.2.

## §118.4 Interaction with §9 (Jorgensen OOB branch) — confirmed neutral

The audit's §2 "Interaction with §9" paragraph (lines 307-312) documents that for a `table` model under
`table_oob="jorgensen"`, the **in-range** clamped `C_x` carries `axial_flow_factor`'s ramp (via
`_table_axial_factor`, applied only when the table's own alpha grid stays strictly inside `(-90°,
90°)`), while the **out-of-range** branch (`_jorgensen_extend`, lines 712-716) computes
`Cx_J = x0*cos²(alpha)` (nose-first) / `-x180*cos²(alpha)` (tail-first) — the literal, `0°`/`180°`-
anchored Jorgensen form — and the two are joined by a smoothstep blend over `oob_blend_deg`. The audit
calls this "a real internal inconsistency": the same physical quantity has two different
alpha-dependences on either side of the table edge.

**This step is neutral to that inconsistency — it neither fixes nor worsens it in kind.**
`_jorgensen_extend` is completely untouched (out of scope, §118.1); it keeps using the true,
`x0`/`x180`-anchored `cos²alpha`. This step only reshapes `axial_flow_factor`, the in-range side of the
seam, from a linear-in-`cos(alpha)` ramp to a squared-ratio-in-`cos(alpha)` curve anchored at `85°`.
The structural mismatch the audit names — two different functional forms meeting at a blended seam,
with the mismatch invisible inside `±10°` of a table's own alpha range but not between `10°` and
`90°` — is **unaffected in structure**: there are still two different forms, still joined by the same
blend, for any table whose own grid extends into `(85°, 90°)` territory before the OOB branch takes
over. One secondary, purely informational observation (not a fix, not claimed as one): both sides of
the seam are now members of the same "squared cosine" functional family (one anchored at `85°`, one at
`0°`/`180°`), rather than one linear and one squared — a step closer in *kind*, not in *magnitude* or
*anchor*. State this plainly to the orchestrator: **neutral, not a fix, not a regression.**

## §118.5 Limitation — not Jorgensen's two-anchor form, deliberately

`axial_flow_factor` remains a **pure function of `alpha` alone** — no `p`/`Aero.C_x180` parameter is
threaded into its signature, matching every call site's existing usage
(`_constant_coeffs`/`_linearized_coeffs`/`_table_coeffs`/`sim/forces.py`'s airbrake term, §118.1). This
is a deliberate, flagged limitation, not an oversight: a function that only ever sees `alpha` can at
best be a **shape multiplier** applied on top of whatever base axial value (`C_x`, `C_A0`, a table
lookup) the calling model already produced — exactly the role it plays today and continues to play.
The literature's actual two-anchor form, `C_A(alpha=0°)·cos²alpha` for nose-first and
`C_A(alpha=180°)·cos²alpha` for tail-first, needs a **second, independently-measured constant**
(`Aero.C_x180`, already present in the schema but today only consumed by `_jorgensen_extend`) and
anchors its magnitude at `0°`/`180°`, not at `85°`. Implementing that honestly is option (b) from the
audit's own table — it moves pins for **every** flight with nonzero `alpha`, not just tail-first ones,
and is explicitly out of scope for this step (D-127 approved option (c), the hybrid, not (b)). Do not
silently upgrade this ticket's scope to thread `C_x180` in "while we're at it" — that is a separate,
pin-moving decision requiring its own user approval, exactly the precedent the brief points to (Step
116's D-129).

## §118.6 `sim/aero.py` — exact before/after

**Comment above `_COS_ALPHA0` (lines 123-125).** Replace:

```python
# Step 93 (Phase 2.16, D-91/D-92, architecture-34 SS34.3): half-width of the
# nose-first plateau of the axial flow-direction factor.
_COS_ALPHA0 = float(np.cos(np.radians(85.0)))
```

with (constant's name/value/line unchanged, comment only):

```python
# Step 93 (Phase 2.16, D-91/D-92, architecture-34 SS34.3): half-width of the
# nose-first plateau of the axial flow-direction factor. Step 118 (D-127,
# conventions-audit SS2 option c): outside this plateau the factor is now a
# cos^2-shaped (not linear) transition anchored at this same 85 deg edge --
# see axial_flow_factor's own docstring for the formula and the reasoning.
_COS_ALPHA0 = float(np.cos(np.radians(85.0)))
```

**`axial_flow_factor` (lines 160-167).** Replace:

```python
def axial_flow_factor(alpha: float) -> float:
    """Flow-direction factor of the axial force, `f = clip(cos(alpha) /
    cos(85 deg), -1, +1)` (D-92). Exactly `1.0` for `|alpha| <= 85 deg`
    (nose-first flight is bit-for-bit unchanged), `0` at `+-90 deg`, `-1`
    for `|alpha| >= 95 deg`: the axial force then points toward the nose,
    i.e. against the motion of a tail-first vehicle (architecture-34 SS34.3).
    """
    return min(1.0, max(-1.0, float(np.cos(alpha)) / _COS_ALPHA0))
```

with:

```python
def axial_flow_factor(alpha: float) -> float:
    """Flow-direction factor of the axial force. Let `r = cos(alpha) /
    cos(85 deg)`; `f = clip(r * |r|, -1, +1)` (D-92/D-127). Exactly `1.0`
    for `|alpha| <= 85 deg` (nose-first flight is bit-for-bit unchanged --
    `r >= 1` there, so `r*|r| >= 1` and the clip holds it at exactly `1.0`),
    `0` at `+-90 deg`, `-1` for `|alpha| >= 95 deg`: the axial force then
    points toward the nose, i.e. against the motion of a tail-first vehicle
    (architecture-34 SS34.3).

    Step 118 (D-127, conventions-audit SS2 option c): outside the plateau
    this is `cos^2`-shaped -- proportional to `(cos alpha / cos 85 deg)^2`,
    a squared ratio anchored at the plateau's own 85 deg edge so it stays
    exactly continuous there -- replacing the earlier, invented linear-in-
    `cos(alpha)` ramp. This is a renormalised cos^2 *family* curve, NOT
    Jorgensen's own two-anchor form (`C_A(0)*cos^2(alpha)` nose-first,
    `C_A(180)*cos^2(alpha)` tail-first, anchored at alpha=0/180 deg and
    needing a second, separately-measured constant, `Aero.C_x180`) -- this
    function stays a pure function of `alpha` alone, matching every call
    site's existing usage. See dev/docs/task-118-axial-cos2-hybrid.md
    SS118.5 for why that is a deliberate limitation, not an oversight.
    """
    r = float(np.cos(alpha)) / _COS_ALPHA0
    return min(1.0, max(-1.0, r * abs(r)))
```

No other line in this function changes.

## §118.7 `sim/forces.py`, `_table_axial_factor` — confirmed no change needed

- **`sim/forces.py` lines 241-243** (the airbrake term's comment, `"the brake is a body-axis axial drag
  too, so it follows the same flow-direction factor as C_x"`) — read in full, confirmed it does not
  describe `axial_flow_factor`'s *shape* (linear vs squared), only that it reuses the same function. No
  edit needed.
- **`sim/aero.py::_table_axial_factor` (lines 170-176)** — its docstring only describes *when*
  `axial_flow_factor` is applied to a table (alpha grid strictly inside `±90°`), not the shape of the
  factor itself. No edit needed.
- **`_constant_coeffs`/`_linearized_coeffs`/`_table_coeffs` docstrings** (lines ~567-570, ~618-620,
  ~654-657) — each mentions `axial_flow_factor(alpha)` by name and the `|alpha| <= 85 deg` bit-for-bit
  guarantee only (still true), never the shape beyond it. No edit needed.

## §118.8 Tests — exact before/after

### `tests/test_aero.py`

**Section header (lines 581-582).** Replace:

```python
# ----------------------------------------------------------------------
# Step 93 (Phase 2.16, D-91..D-93): the axial coefficient follows the flow
# direction -- f(alpha) = clip(cos(alpha)/cos(85 deg), -1, 1).
# ----------------------------------------------------------------------
```

with:

```python
# ----------------------------------------------------------------------
# Step 93 (Phase 2.16, D-91..D-93), reshaped Step 118 (D-127): the axial
# coefficient follows the flow direction -- f(alpha) = clip(r*|r|, -1, 1)
# with r = cos(alpha)/cos(85 deg) (cos^2-shaped outside the 85 deg plateau,
# exactly 1.0 for |alpha| <= 85 deg).
# ----------------------------------------------------------------------
```

**`test_axial_flow_factor_is_one_inside_85_deg_exactly` (lines 586-588): NO CHANGE.** Verified
numerically for every literal in the loop (`0, 10, -30, 80, 85, -85` deg) that the new formula still
returns exactly `1.0` (§118.9).

**`test_axial_flow_factor_zero_at_90_and_minus_one_beyond_95` (lines 591-595): NO CHANGE.** Verified
numerically that `abs(f(±90°)) < 1e-12` still holds (new value `~4.9e-31`, far inside the tolerance)
and `f(deg) == -1.0` exactly for `deg in (95, -95, 120, 180, -180)` under the new formula (§118.9).

**`test_axial_flow_factor_is_continuous_across_the_ramp` (lines 598-603): tolerance constant changes.**
The new shape's maximum slope magnitude in the sampled window is exactly double the old one's: the old
ramp's slope at the `85°` edge is `tan(85°)/cos(85°) ≈ 11.43`/rad; the new shape's slope there is
`d(r²)/dalpha = 2·r·(dr/dalpha)`, and since `r=1` at that exact point this is exactly `2×` the old
value, `≈ 22.86`/rad (confirmed by direct symbolic derivative and by numerically re-running the test's
own sampling loop against the new formula: empirical max consecutive-sample delta over `84°..96°` at
the same `0.01°` step is `0.0039859`, vs. the old formula's `0.0019949` -- ratio `1.9989`, i.e. the
"exactly double" prediction holds empirically too). Replace:

```python
def test_axial_flow_factor_is_continuous_across_the_ramp():
    prev = aero.axial_flow_factor(math.radians(84.0))
    for deg in np.linspace(84.0, 96.0, 1201)[1:]:
        cur = aero.axial_flow_factor(math.radians(deg))
        assert abs(cur - prev) < 3e-3  # slope <= 11.5/rad * 0.01 deg step
        prev = cur
```

with:

```python
def test_axial_flow_factor_is_continuous_across_the_ramp():
    """Step 118 (D-127): the cos^2-shaped transition's slope at the 85/95 deg
    edges is exactly double the old linear ramp's (d(r^2)/dalpha = 2*r*dr/dalpha,
    r=1 at the edge) -- empirically ~22.86/rad vs. ~11.43/rad, so this test's
    tolerance doubles too (3e-3 -> 6e-3, same ~1.5x safety margin over the
    theoretical per-step bound, ~3.99e-3, that the old tolerance used over its
    own ~1.99e-3 bound)."""
    prev = aero.axial_flow_factor(math.radians(84.0))
    for deg in np.linspace(84.0, 96.0, 1201)[1:]:
        cur = aero.axial_flow_factor(math.radians(deg))
        assert abs(cur - prev) < 6e-3  # slope <= 23/rad * 0.01 deg step
        prev = cur
```

**Do not just bump the tolerance without reading the comment update above** — a future reader needs to
know *why* it doubled, or they will assume a regression the next time this shape changes.

### `tests/test_forces.py`

**`test_airbrake_term_flips_tail_first` (lines 969-981): NO CHANGE.** Confirmed by reading the body
(lines 975-980): `expected = -flow.q * 1.2 * 0.01 * aero.axial_flow_factor(flow.alpha)` calls the real
function dynamically rather than hardcoding a literal, so it tracks whatever shape
`axial_flow_factor` has automatically. The two sampled `vz` values (`-60.0`, `+60.0`) correspond to
`alpha = 0` and `alpha = π` exactly (nose-first/tail-first, not near the `85-95°` window), so this test
exercises the formula at the two unaffected, unchanged anchor points regardless.

## §118.9 Pin safety — how this was checked

- **Literal-value grep across `tests/`** for any numeric degree/alpha literal landing strictly inside
  `(85°, 95°)`: none found. Every `85`/`90`/`95`-adjacent literal in the test suite is either this
  ticket's own three `axial_flow_factor` tests (covered above, all anchor points reproduced exactly) or
  an unrelated angle (heading `chi`, wind-direction veering, latitude for `gamma0`, quaternion
  singularity documentation, `math.radians(90.0)` reproduction checks) — confirmed by direct read of
  every grep hit, not assumed from the pattern match alone.
- **Dynamic (integrated-trajectory) tail-first tests, checked individually, not just grepped:**
  - `tests/test_dynamics.py::test_demo_descent_without_recovery_is_dissipative_not_free_fall_faster`
    (Step 93/D-91) — asserts specific energy is non-increasing and impact speed is below the drag-free
    bound, both **inequalities**, not literal pinned floats; insensitive to the exact shape of
    `axial_flow_factor` between `85°` and `95°` even if the tumbling descent transiently passes through
    that window.
  - `tests/test_dynamics.py::test_apogee_triggered_parachute_ignores_the_pad_sag` — same kind of
    event-timing/qualitative check, not a float pin through the `85-95°` window.
  - `tests/test_dynamics.py`'s sign-regression test (lines ~160-233,
    `test_...` comparing corrected vs. `_buggy_derivatives`): the "corrected" branch uses
    `aero=Aero(model="linearized", ..., C_A0=0.0, ...)` — `C_A0=0.0` means the axial coefficient (and
    hence `axial_flow_factor`'s output) is multiplied by zero at every call, so this test is immune to
    this step by construction, confirmed by reading its `Params` construction directly. The "buggy"
    branch uses the same `C_A0=0.0` params. Neither branch's pinned `alpha(t)` samples
    (`-0.38, -1.65, +2.11, +0.47, -0.11` rad) are themselves axial-force outputs — they are
    `flow_state(...).alpha`, upstream of and independent of this change.
  - `tests/test_qa_phase217_m1.py`, `tests/test_step114_review_fixes.py` — read directly, neither
    exercises a dynamic tail-first trajectory sampling the `85-95°` window; both use static
    `aero.coefficients`/`_table_coeffs`/`_load_table` calls at fixed `alpha` values outside that band
    (or, where a table-OOB test uses `alpha=90°` exactly, e.g. `tests/test_aero_oob.py:265`, it goes
    through `_jorgensen_extend`, not `axial_flow_factor`, and only asserts `C_z`, not `C_x` — confirmed
    by reading the test body).
- **Expected full-suite result: 705/705, unchanged count.** If the full run (background, per
  `CLAUDE.md`'s convention) surfaces a failure in any file **other than** `tests/test_aero.py` (the one
  known, flagged tolerance change), treat it as an undiscovered dynamic pin that moved and **stop and
  report it to the orchestrator with the exact before/after numbers** for a user-facing approval
  question (same precedent as Step 116's D-129) — do not silently "fix" it by reverting the shape or by
  loosening an unrelated test's tolerance.

## §118.10 Test-impact table

| File | Change | Reason |
|---|---|---|
| `tests/test_aero.py` | Section header comment (lines 581-582) reworded | Describes the new formula |
| `tests/test_aero.py` | `test_axial_flow_factor_is_one_inside_85_deg_exactly` | **No change** — values unaffected |
| `tests/test_aero.py` | `test_axial_flow_factor_zero_at_90_and_minus_one_beyond_95` | **No change** — values unaffected |
| `tests/test_aero.py` | `test_axial_flow_factor_is_continuous_across_the_ramp` | Tolerance `3e-3 -> 6e-3` (slope doubles) + docstring added |
| `tests/test_forces.py::test_airbrake_term_flips_tail_first` | **No change** | Computes `expected` dynamically |
| All other 697 tests | **No change expected** | No literal alpha in `(85°, 95°)` found; dynamic tail-first tests are inequality-based |

## §118.11 Open questions

1. **Does this fix the §2/§9 interaction inconsistency?** No — confirmed neutral (§118.4). Flagging
   again here because it is the one place the brief explicitly asked for a plain yes/no/neutral
   answer: **neutral**, not a fix, not a regression. If the user wants that inconsistency actually
   resolved, that is option (b) (or (d)), a separate, larger, pin-moving decision — not bundled here.
2. **Is a pure-`alpha` function the right long-term home for this, given it can never implement the
   literal Jorgensen two-anchor form?** Flagged as a deliberate limitation (§118.5), not resolved here.
   If/when the user wants the literal form, `Aero.C_x180` already exists in the schema for it — option
   (b) would thread it through, at the cost of re-pinning every nonzero-alpha flight.
3. **Should `85°`/`95°` become configurable fields instead of hardcoded anchors?** Out of scope — D-127
   explicitly preserves them as fixed anchors; not reopened by this step.
4. **Magnitude note, informational only:** the new shape falls off noticeably faster than the old one
   just past the plateau edge — e.g. at `87°` the old ramp gives `f ≈ 0.600`, the new shape gives
   `f ≈ 0.360` (both computed directly, not estimated) — which is *more* physically correct (matches
   the true `cos²` falloff character near normal incidence) even though the anchor point differs from
   Jorgensen's own. No action needed; noted for whoever next touches this function so the magnitude
   change isn't mistaken for a bug.

## §118.12 Definition of done

- [ ] `sim/aero.py`: `_COS_ALPHA0`'s comment updated (lines 123-125, value/name unchanged);
      `axial_flow_factor` body + docstring replaced per §118.6; no other line in the file touched.
- [ ] `sim/forces.py`: confirmed no edit needed (§118.7).
- [ ] `tests/test_aero.py`: section header comment reworded; `test_axial_flow_factor_is_continuous_across_the_ramp`'s
      tolerance `3e-3 -> 6e-3` with the new docstring; the other two boundary tests verified unchanged
      and still passing.
- [ ] `tests/test_forces.py`: verified `test_airbrake_term_flips_tail_first` needs no change and still
      passes.
- [ ] Point-in-time run: `python -m pytest tests/test_aero.py tests/test_forces.py -q` green.
- [ ] Full suite green in background per `CLAUDE.md`'s convention — **705/705**. Any failure outside
      `tests/test_aero.py` reported to the orchestrator as a found pin (§118.9), not silently handled.
- [ ] `code-review` skill run before handing to QA (project convention, feature branch
      `feature/sim-paper-alignment`).

### [STEP-118] Axial flow factor: cos²-shaped hybrid outside the 85° plateau (D-127, option c)
- **Module/boundaries:** `sim/aero.py` (`axial_flow_factor`, its docstring, the `_COS_ALPHA0` comment),
  `tests/test_aero.py` (the three `axial_flow_factor` tests and their section header).
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (touches `sim/aero.py`, the same shared module Step 116/117 and any other
  in-flight work on this branch also touch — sequence it, do not run alongside another ticket editing
  this file)

Implement per §118.2/§118.6 above; run §118.8's test edits; verify §118.9's pin-safety claims hold
after implementation (run the point-in-time tests, then the full suite); tick off §118.12 before
handing to QA.
