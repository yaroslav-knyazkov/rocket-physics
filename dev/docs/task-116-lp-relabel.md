# Step 116 (D-125) — relabel `l_p` as the moment reference station; derive CP/static margin; single stability criterion

## Кратко (RU)

Тикет закрывает находку §12.1 аудита (`dev/docs/conventions-industry-standard-analysis.md`): поле
`Aero.l_p` / колонка `l_p_m` документировано как "станция ЦД от носика", но физически в `sim/dynamics.py`
читается как станция приведения момента `x_ref` — корректно, только если `l_p` это `x_ref`. Пользователь
одобрил **Option (A)**: релейбл без изменения арифметики динамики (ноль сдвига пинов полёта); ЦД и
статический запас в `sim/report.py` становятся *производными* величинами; один объединённый критерий
устойчивости вместо двух независимых. Разрешённые архитектурные развилки (решения приняты в этом
тикете, разработчику выбирать не нужно):

1. Формула производного ЦД — slope-форма через `aero.C_m`/`aero.C_N` (новый `fb`-параметр у `C_N`),
   с guard на `dC_z/dalpha ≈ 0` (деление на ноль).
2. Исправление применяется **только** при `aero.uses_l_p(p) is True` (станция/v2-таблица); legacy
   `Lengths.l1`-конфиги не трогаем (нет той же неоднозначности в документации поля).
3. Объединённый критерий `d/dalpha[(l_g-l_p)*C_z - d_ref*C_m] < 0` — считается **безусловно** для всех
   моделей (не требует `uses_l_p`), так как выражается через уже вычисленный `coeffs.l1`.
4. LaTeX — ровно два места: `rocket-2d.tex` строки 59-60 и `analysis.tex` строки 132-138 (готовый текст
   ниже, вставить дословно). Больше `dev/docs/latex/` нигде не трогать (правило read-only, кроме этого
   одобренного исключения).

Один числовой пин подвинется осознанно: `tests/test_report.py::test_static_margin_series_matches_cg_travel`
(станция-режим, новая формула меняет значение `margin[0]`) — тикет даёт готовую замену ассерта, не
руками вычисленное число. Все остальные тесты, которые затронуты, меняются по знаку/отношению, не по
литералу — см. §116.7.

**Правка после первой реализации (баг нашёл разработчик, подтверждён численно здесь же):** §116.4
исходно содержал внутреннее противоречие — цитировал критерий аудита `... < 0` (отрицательное =
восстанавливающий момент), но тут же писал «stable when `combined_slope >= 0`» (обратный знак), и
брал `.min()` там, где для этой величины нужен `.max()` (иначе худшее по полёту значение маскируется
клампом на краю таблицы). Исправлено: `combined_slope <= 0` — устойчиво, проверка через `.max()`,
возвращаемый ключ переименован в `max_stability_slope`. Один из трёх тестов комбинированного критерия
(`test_flipping_declared_convention_reports_instability`) при исходной геометрии физически перестаёт
алармить под правильным объединённым критерием (запас с избытком перекрывает вклад перевёрнутого
`C_m`) — это не баг, а корректное поведение новой модели; тикет даёт подрезанную геометрию (§116.7a,
численно проверена), которая восстанавливает прежний смысл теста ("перепутанный `cm_convention`
детектируется").

---

## Table of contents

- §116.1 Scope and non-goals
- §116.2 `sim/aero.py` — extend `C_N` with `fb`, no other behavior change
- §116.3 `sim/report.py::static_margin_cal` — derived-CP slope formula
- §116.4 `sim/report.py` — combined stability criterion, `stability_check` rewrite
- §116.5 `sim/aero.py` docstring/comment wording (no rename, no behavior change)
- §116.6 `configs/`/`data/` doc-comment wording
- §116.7 Tests — exact impact per file
- §116.8 LaTeX — the only two approved edits (D-125)
- §116.9 Known limitation note (`l_p == 0.0` double duty) + backlog suggestion
- §116.10 Definition of done

---

## §116.1 Scope and non-goals

**In scope:** `sim/aero.py` (one new optional parameter, docstring/comment wording only — no field
rename, no arithmetic change to `_resolve_arm`/`dynamics.py`), `sim/report.py` (`static_margin_cal`,
`stability_check`, one new helper), `configs/rockets/_TEMPLATE_rocket.py` (two comment lines),
`data/aero/example_v2.csv` (header comment), exactly two spots in `dev/docs/latex/` (see §116.8),
the test files listed in §116.7.

**Out of scope / do not touch:**
- `sim/dynamics.py` — zero changes, zero pin movement on any flight trajectory (D-125's whole point).
- Field/column renames (`l_p` stays `l_p`, `l_p_m` stays `l_p_m`) — Option (A) is a semantics/docs fix,
  not a rename.
- `Aero.l_p == 0.0` also meaning "off" — known limitation, documented not fixed (§116.9).
- Any `dev/docs/latex/` file or line other than the two edits in §116.8.
- `tests/test_aero_v2.py` — not touched by this ticket (verified: it never calls `static_margin_cal`/
  `stability_check`; it tests `aero.py`'s own loader/dispatch, which is unchanged in behavior).

## §116.2 `sim/aero.py` — extend `C_N` with `fb`, no other behavior change

**Why this is needed, not optional:** `cm_slope_series` already calls `aero.C_m(alpha, M, p, fb)` so a
brake-table flight's `C_m` slope is read from the correct (brake-blended) plane. The new CP/combined-
criterion code in §116.3/§116.4 needs the matching `C_z` slope the same way, but today's `C_N` wrapper
(`sim/aero.py:819-822`) bypasses `fb` entirely — it calls `_AERO_MODELS[p.aero.model](alpha, M, p)`
directly, not `_dispatch`, so it always reads the `f_b = 0` (closed) plane regardless of the flight's
actual brake state. Left as-is, the new diagnostics would be silently wrong during an open-brake segment
of a `Control.airbrake_aero == "table"` flight with a table whose `f_b` axis affects `C_N`.

**Fix:** mirror `C_m`'s signature exactly (`sim/aero.py:825-829`):

```python
# sim/aero.py, replace lines 819-822:
def C_N(alpha: float, M: float, p, fb: float = 0.0) -> float:
    """Normal-force coefficient (models.tex: `A_z = qSC_z`, `C_z == C_N`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps.
    Step 116: optional brake fraction `fb` (read only under `airbrake_aero="table"`),
    the same as `C_m` -- needed so `sim/report.py`'s derived-CP/combined-stability
    diagnostics (D-125) read the brake-blended plane, not always the closed one."""
    return _dispatch(alpha, M, p, fb).C_z
```

`fb` defaults to `0.0` and every existing call site (`tests/test_aero.py:59,75,163,244,506`) calls it
positionally with 3 args — unaffected, zero pin movement. `_dispatch` (line 737) already handles the
arity mismatch between the table model (which takes `fb`) and constant/linearized (which don't), so no
other change is needed here.

## §116.3 `sim/report.py::static_margin_cal` — derived-CP slope formula

**Derivation (matches audit §12.1 exactly, re-derived and cross-checked against
`dev/docs/latex/sections-ai/analysis.tex` eq. `eq:dtheta_dalpha`/`eq:static_margin`, both already in the
code's `C_m` sign convention per that file's own line 129-130):** the centre of pressure `x_cp` is the
station at which the pitching-moment slope about that station is zero. Shifting the reference station
from `x_ref` by `delta` changes the moment slope about the new station by `-delta/d_ref * dC_z/dalpha`
(the normal force now has a different arm); solving for the `delta` that zeroes the shifted slope gives

```
x_cp = x_ref - (dC_m/dalpha) / (dC_z/dalpha) * d_ref
```

— the slope form the audit specifies (avoids the point-wise `C_m/C_z` formula's division-by-zero
whenever `alpha` crosses zero, which happens routinely mid-flight, not just at `t=0`). Since
`aero.coefficients(...).l1 == x_ref - l_g(t)` already (the arm `_resolve_arm` computes, D-110,
untouched by this ticket), the derived arm from the CG is `x_cp - l_g(t) = l1 - (dC_m/dalpha)/(dC_z/dalpha)*d_ref`,
and the margin in calibers is that divided by `d_ref`:

```
margin(t) = l1(t)/d_ref - (dC_m/dalpha)/(dC_z/dalpha)     [evaluated at the flight's own (alpha, M)]
```

**Gating decision (resolves the ticket's open point 2): apply this correction only when
`aero.uses_l_p(p)` is `True`.** Reasoning: the over-determination the audit found is specifically a
*naming/documentation* problem of the station form (`l_p`/`l_p_m`, documented as "the CP" but read as
`x_ref`) — a direct `Lengths.l1` arm has no such mismatched claim; `Lengths.l1`'s own doc comment
(`configs/rockets/_TEMPLATE_rocket.py:62`) already says "CoP to CoG distance (static-margin lever arm)",
i.e. an input lever arm, not a promise that `C_m` about it is zero. Correcting legacy-arm configs too
would move pins in configs that are not implicated in the finding, for no documentation-honesty gain.
This also keeps `aero.C_N`'s new `fb` default-safe path untouched for every legacy-arm pin in the repo.

**Division-by-zero guard (new, not in the audit text, found while checking test impact — see
§116.7):** `tests/test_aero_fb.py`'s `_flight_rows` tables set `C_N = C_m = 0.0` at every grid point (a
drag-only synthetic table), so `dC_z/dalpha == 0.0` exactly — not just a momentary `alpha`-crossing-zero
case but constant. `dcm/dcz` is then a genuine `0/0`. Guard: when `abs(dC_z/dalpha)` is below a small
epsilon, there is no normal-force sensitivity to derive a CP correction from at that point — fall back
to no correction (the raw `l1/d_ref`), not an exception or a `NaN`.

**Exact replacement for `sim/report.py` (today's `static_margin_cal` is lines 69-83; `_CM_SLOPE_STEP` is
defined at line 104, keep it, add the new constant next to it):**

```python
_CZ_SLOPE_EPS = 1e-9  # |dC_z/dalpha| below this: no normal-force sensitivity to derive a CP
                       # correction from at this (alpha, M) (e.g. a drag-only test table with
                       # C_N == 0 identically) -- fall back to the raw arm, no correction.


def static_margin_cal(result, p, t_grid=None):
    """Static margin series in calibres, `(t, margin)`.

    Step 116 (D-125): `l_p`/`l_p_m` is the *moment reference station* `x_ref`, not necessarily the
    CP (architecture.md / conventions-industry-standard-analysis.md SS12.1). When the config uses a
    station (`aero.uses_l_p(p)`), the margin is corrected to the *derived* CP station, via the local
    slope ratio (central difference, the same `_CM_SLOPE_STEP` as `cm_slope_series`):

        margin(t) = l1(t)/d_ref - (dC_m/dalpha)/(dC_z/dalpha)

    where `l1(t) == x_ref - l_g(t)` (`aero.coefficients(...).l1`, D-110, unchanged). For a legacy
    direct-arm config (`not uses_l_p(p)`), `l1` is the input arm itself with no separate "station"
    reading to be ambiguous about, so the margin is reported as-is: `l1(t)/d_ref` (today's formula,
    bit-for-bit).
    """
    if p.aero.d_ref <= 0.0:
        raise ValueError("static_margin_cal needs Aero.d_ref > 0")
    t, y = _flight_grid(result, t_grid)
    use_derived_cp = aero.uses_l_p(p)
    margin = np.empty(t.size)
    for i, ti in enumerate(t):
        flow = flow_state(ti, y[:, i], p)
        fb = _brake_fraction(ti, y[:, i], p)
        arm = aero.coefficients(ti, y[:, i], p, flow, None, fb).l1
        correction = 0.0
        if use_derived_cp:
            dcm = (
                aero.C_m(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
                - aero.C_m(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
            ) / (2.0 * _CM_SLOPE_STEP)
            dcz = (
                aero.C_N(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
                - aero.C_N(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
            ) / (2.0 * _CM_SLOPE_STEP)
            if abs(dcz) > _CZ_SLOPE_EPS:
                correction = dcm / dcz
        margin[i] = arm / p.aero.d_ref - correction
    return t, margin
```

`_brake_fraction`/`_flight_grid` are unchanged (lines 86-101 today); `cm_slope_series` (lines 107-118)
is also unchanged — it is still a useful standalone diagnostic and `stability_check` keeps reporting its
value (§116.4).

## §116.4 `sim/report.py` — combined stability criterion, `stability_check` rewrite

**This criterion is mode-agnostic — applies unconditionally, no `uses_l_p` gate.** Unlike §116.3 (which
needs an absolute reference station to derive an absolute CP from), the combined criterion is a
*physical* restoring-moment-slope test expressed purely through quantities `dynamics.py` already uses:
the resolved arm `coeffs.l1` (whatever mode produced it) and the two coefficient slopes. The audit's
formula, `d/dalpha[(l_g-l_p)*C_z - d_ref*C_m] < 0` (nose-down restoring), rewrites directly in terms of
the already-resolved arm since `l_g - l_p == -l1` in every mode (station or legacy):

```
combined_slope(t) = -l1(t) * dC_z/dalpha - d_ref * dC_m/dalpha
```

**CORRECTION (post-implementation, developer-found bug — this replaces an earlier, self-contradictory
draft of this section that said "stable when `combined_slope(t) >= 0`" two sentences after quoting the
audit's own `< 0` convention; verified numerically against the real tables below before being written
down here, not re-derived on paper only):**

**Sign: negative `combined_slope` is restoring (stable), matching the audit's `< 0` literally and
`analysis.tex`'s `eq:dtheta_dalpha`/`eq:static_margin` (stability requires `d/dalpha[...] < 0`, line
117-125) — this is the OPPOSITE polarity from `cm_slope_series`'s own "positive = restoring" (that
one is `dC_m/dalpha` alone, a different quantity; do not carry its polarity over to this one.**

**Extremum: use `.max()`, not `.min()`.** Positive `combined_slope` is the destabilizing direction here,
so the worst case over a flight is its *maximum*, not its minimum. Verified concretely on
`test_negative_geometric_margin_warns`'s forward-CP fixture: `combined_slope` is `+1.285` early in
flight (the genuine destabilizing excursion, small `alpha`, within the table's range) and relaxes to
exactly `0.0` later once the flight tumbles past the table's `±10°` edge (held-edge clamping zeroes both
coefficient slopes there) — `.min()` over the grid picks up that clamp artifact (`0.0`, reads as
"barely stable") and completely misses the real `+1.285` excursion; `.max()` finds it.

**New helper (add next to `cm_slope_series`, same file):**

```python
def combined_stability_slope_series(result, p, t_grid=None):
    """`(t, d/dalpha[(l_g - l_p)*C_z - d_ref*C_m])` -- the single, reference-point-independent
    stability criterion (Step 116, D-125, conventions-industry-standard-analysis.md SS12.1).
    NEGATIVE = restoring (stable) in the code's C_m convention -- the opposite polarity from
    `cm_slope_series`'s own "positive = restoring" (that is `dC_m/dalpha` alone, a different
    quantity). Expressed via the already-resolved arm `l1 == l_p - l_g(t)` (or the legacy direct
    arm), so it needs no `aero.uses_l_p` gate -- it is the same quantity `dynamics.py` actually
    sums into the physical moment, for any aero model.
    """
    t, y = _flight_grid(result, t_grid)
    slope = np.empty(t.size)
    for i, ti in enumerate(t):
        flow = flow_state(ti, y[:, i], p)
        fb = _brake_fraction(ti, y[:, i], p)
        arm = aero.coefficients(ti, y[:, i], p, flow, None, fb).l1
        dcm = (
            aero.C_m(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
            - aero.C_m(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
        ) / (2.0 * _CM_SLOPE_STEP)
        dcz = (
            aero.C_N(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
            - aero.C_N(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
        ) / (2.0 * _CM_SLOPE_STEP)
        slope[i] = -arm * dcz - p.aero.d_ref * dcm
    return t, slope
```

**`stability_check` rewrite (replace lines 121-146 in full):**

```python
def stability_check(result, p, t_grid=None) -> dict:
    """Static-stability diagnostic (Step 116, D-125: single combined criterion, superseding the
    two-independent-tests shape of Step 99/D-111). Warns (`UserWarning`) when the combined
    restoring-moment slope (`combined_stability_slope_series`, negative = restoring) goes positive
    anywhere over the flight. Returns `{min_margin_cal, min_cm_slope, max_stability_slope, stable}`
    -- `min_margin_cal`/`min_cm_slope` stay as informational values (still meaningful on their own),
    but `stable` is driven only by `max_stability_slope` (the *max*, not the min -- see
    `combined_stability_slope_series`'s own docstring for why).
    """
    _, margin = static_margin_cal(result, p, t_grid)
    _, cm_slope = cm_slope_series(result, p, t_grid)
    _, combined = combined_stability_slope_series(result, p, t_grid)
    min_margin = float(margin.min())
    min_cm_slope = float(cm_slope.min())
    max_combined = float(combined.max())
    stable = max_combined <= 1e-9  # tolerance: finite-difference rounding on flat segments
    if not stable:
        warnings.warn(
            f"unstable: combined static-margin/pitching-moment-slope criterion reaches "
            f"{max_combined:.4g} > 0 (d/dalpha[(l_g-l_p)*C_z - d_ref*C_m] in the code convention, "
            "negative = nose-down restoring) -- check the CP/moment-reference station, geometry, "
            "and the table's `# cm_convention:`",
            UserWarning, stacklevel=2,
        )
    return dict(
        min_margin_cal=min_margin,
        min_cm_slope=min_cm_slope,
        max_stability_slope=max_combined,
        stable=stable,
    )
```

Single warning, single criterion; the message text deliberately contains both "unstable" and "margin"
(see §116.7 for why both substrings matter to existing test regexes). Note the returned key is
`max_stability_slope` (not `min_...` — it is genuinely a max, the sign convention is reversed from
`min_margin_cal`/`min_cm_slope`; do not "fix" this to `min_` for naming consistency, that would silently
reintroduce the `.min()` bug).

## §116.5 `sim/aero.py` docstring/comment wording (no rename, no behavior change)

Change "CP station from the nose" / "the CP" language to "moment reference station from the nose
(`x_ref`); the aerodynamic moment `C_m` is taken about this station; the centre of pressure is a
derived quantity, not an input" (shortened as fits each comment's existing style — do not force the
full sentence verbatim everywhere, match surrounding prose length). Exact spots, current text already
confirmed at these lines on this branch:

| Line(s) | Current text (abbreviated) | Change |
|---|---|---|
| `sim/aero.py:65-66` | "`l_p_m` (CoP station from the nose; the arm is `l_p_m - l_g(t)`...)" | "`l_p_m` (moment reference station from the nose, `x_ref`; the arm is `l_p_m - l_g(t)`...)" |
| `sim/aero.py:75` | "...carry the brake's effect on `C_A`, `C_N`, `C_m` and the CP station `l_p_m`" | "...and the moment reference station `l_p_m`" |
| `sim/aero.py:187` | `l_p` field comment: "CoP station from the nose [m]" | "moment reference station from the nose [m] (`x_ref`)" |
| `sim/aero.py:263-264` | "...xor `l_p_m` (CoP station from the nose; the arm is then `l_p_m - CoG(t)`)" | "...xor `l_p_m` (moment reference station from the nose, `x_ref`; the arm is then `l_p_m - CoG(t)`)" |
| `sim/aero.py:423-424` | `_arm_or_station` docstring: "`Aero.l_p` (a CP station, turned into an arm by `_resolve_arm`)" | "`Aero.l_p` (a moment reference station, turned into an arm by `_resolve_arm`)" |
| `sim/aero.py:428-430` | `uses_l_p` docstring: "True when the CP is given as a station from the nose..." | "True when the moment reference is given as a station from the nose (`x_ref`)..." |
| `sim/aero.py:443` | error message: "a CP station (Aero.l_p / table l_p_m) with the mass model off..." | "a moment reference station (Aero.l_p / table l_p_m) with the mass model off..." |
| `sim/aero.py:452` | `_resolve_arm` docstring: "Turn a CP station into the CoP-to-CoG arm..." | "Turn a moment reference station into the CoP-reference-to-CoG arm..." |
| `sim/aero.py:482` | error message: "a CP station (l_p / l_p_m) requires..." | "a moment reference station (l_p / l_p_m) requires..." |

Do not touch lines 470-471 or 513-516 (error messages there already say "`Aero.l_p`"/"station" without
claiming "CP", no wording problem) or `AeroCoeffs.l1`'s own field comment at line 408 (`"CoP(D)-to-CoG(B)
distance"`, main.tex's `D`/`B` point-naming, a different paper's notation — out of scope, not touched by
this ticket).

Also add one sentence to `uses_l_p`'s docstring (or `_arm_or_station`'s) for the known limitation — see
§116.9 for the exact wording and where.

## §116.6 `configs/`/`data/` doc-comment wording

- `configs/rockets/_TEMPLATE_rocket.py:96`: `"CoP station from the nose, constant/linearized models; arm = l_p - CoG(t); 0.0 = off (lengths.l1 is the arm)"` → `"moment reference station from the nose (x_ref), constant/linearized models; arm = l_p - CoG(t); 0.0 = off (lengths.l1 is the arm)"`.
- `configs/rockets/_TEMPLATE_rocket.py:211`: `"CoP station from the nose tip, ..."` → `"moment reference station from the nose tip (x_ref), ..."` (same clause structure, keep the rest of the line unchanged).
- Leave `configs/rockets/_TEMPLATE_rocket.py:62` (`Lengths.l1`'s own doc row) untouched — legacy arm, not in scope (§116.3's gating decision).
- `data/aero/example_v2.csv:4-7`: the header comment block starting `"#   - the CoP is given as a station from the nose tip, l_p_m [m]..."` → reword to `"the moment reference station is given from the nose tip, l_p_m [m] (x_ref; C_m is taken about this station, the CP is a derived quantity)"`, keep the rest of the comment (the `arm = l_p_m - l_g(t)` explanation, the `l1_m + 0.9 m` note) as-is.
- `data/aero/example.csv` — legacy `l1_m` table, out of scope (no "CP station" claim to fix there — its comment already says "the CoP (l1_m, the CoP-to-CoG distance...)" which is a direct-arm claim, consistent with §116.3's legacy-mode decision).
- No other `data/aero/*.csv` files exist on this branch (`Glob data/aero/*.csv` → only `example.csv`, `example_v2.csv`).

## §116.7 Tests — exact impact per file

| File / test | `uses_l_p`? | Impact | Action |
|---|---|---|---|
| `tests/test_report.py::test_static_margin_series_matches_cg_travel` | yes (`example_v2.csv`) | **pin moves** — `margin[0]` was asserted against the raw station literal `(1.18 - l_g0)/0.1`; the corrected formula subtracts a nonzero slope-ratio correction (`example_v2.csv`'s `C_m` has a `0.5/rad` slope, audit line 811) | Replace the hard-coded literal with an independently-computed cross-check (see snippet below) — do not hand-derive a new float literal |
| `tests/test_report.py::test_stable_table_reports_no_warning` | yes | `out["min_cm_slope"]` unaffected (same `cm_slope_series`, unchanged code); `out["stable"]` now driven by the combined criterion — verified numerically: `combined.max() == -0.815 <= 1e-9` → `True`, matches expected | No code change needed; run and confirm |
| `tests/test_report.py::test_flipping_declared_convention_reports_instability` | yes | **fixture change required, not just a re-run** — verified numerically that with this test's *original* geometry (`Weight(l_d=0.8, l_p=1.3)`), the combined slope stays at a constant `-0.715` (still comfortably stable) even with the declared convention wrong: this table's ample margin term (`-l1*dC_z/dalpha ≈ -0.765`) dominates the small `C_m`-flip contribution (`-d_ref*dC_m/dalpha`, magnitude `≈0.05-0.1`) regardless of its sign. The old two-independent-tests design flagged this as "unstable" purely because `dC_m/dalpha<0` was sufficient on its own (Step 99/D-111) — under the new, physically-correct unified criterion this specific geometry's ample margin genuinely makes the flipped-convention flight still net-restoring, so the test's old expectation (`stable is False`) would be *wrong*, not stale-but-harmless. See the exact fixed fixture below (§116.7a) — a thinned-margin geometry override, verified numerically to flip sign both ways | **Replace** `Weight(m=2.0, I=0.1, m_d=1.5, l_d=0.8, l_p=1.3, I_d=0.08, I_sp=200.0)` with the thin-margin override in §116.7a; keep everything else (the `_flipped_copy(..., "code")` call, both assertions) unchanged |
| `tests/test_report.py::test_negative_geometric_margin_warns` | yes | `out["min_margin_cal"] < 0.0` uses the corrected formula now; warning `match="margin"` still satisfied (new message text contains "margin", §116.4); verified numerically: `combined.max() == +1.285 > 1e-9` → `stable=False`, warning fires | No code change expected; run and confirm |
| `tests/test_aero_fb.py::test_static_margin_shifts_with_fb_and_diagnostic_shows_it` | yes (`l_p_m` column in `_flight_rows`), but `C_N ≡ 0` identically in that synthetic table | `dC_z/dalpha == 0` exactly → `_CZ_SLOPE_EPS` guard fires → correction `= 0.0` → formula reduces to today's `l1/d_ref` bit-for-bit | No change expected; run and confirm the `0.2/_D_REF` drop assertion still holds |
| `tests/test_aero_v2.py` | n/a | Tests `aero.py`'s loader/dispatch directly, never calls `static_margin_cal`/`stability_check`/`cm_slope_series` | Not touched |
| `tests/test_scenario_sweep.py::test_works_with_v2_table_and_margin_series` | yes | Only relational/`isfinite`/`approx`-between-two-computed-values assertions (no hard literal) | No change expected; run and confirm |
| `apps/motor_selection/scenario_sweep.py::_margins` | n/a (app code, not a test) | Consumes `static_margin_cal` for console/report output only, no pin | No action beyond confirming the import/signature still matches (unchanged) |

**Exact replacement for the one hard-literal test** (`tests/test_report.py`, replace the body from the
comment `# the arm l_p_m...` through the final `assert`):

```python
    # Step 116 (D-125): the derived-CP arm (l1 corrected by the local C_m/C_N slope ratio),
    # divided by d_ref -- cross-check the first point against the same formula computed
    # independently via aero's own per-coefficient slope helpers (not a hand-typed literal:
    # the correction term is new with this step, see sim/report.py S116.3).
    from sim import mass
    from sim.flow import flow_state
    y0 = r.raw.sol(0.0)
    l_g0 = mass.cog_position(mass.propellant_mass(y0[6], p), p)
    flow0 = flow_state(0.0, y0, p)
    step = __import__("sim.report", fromlist=["_CM_SLOPE_STEP"])._CM_SLOPE_STEP
    dcm = (aero.C_m(flow0.alpha + step, flow0.M, p) - aero.C_m(flow0.alpha - step, flow0.M, p)) / (2 * step)
    dcz = (aero.C_N(flow0.alpha + step, flow0.M, p) - aero.C_N(flow0.alpha - step, flow0.M, p)) / (2 * step)
    expected = (1.18 - l_g0) / 0.1 - dcm / dcz
    assert margin[0] == pytest.approx(expected, rel=1e-6)
```

(Prefer a normal `from sim.report import _CM_SLOPE_STEP` at the top of the test file over the
`__import__` one-liner above — written this way here only so the snippet is a drop-in patch to the
existing test body without touching its import block; use your judgement on which reads better in
context.)

### §116.7a Fixed fixture for `test_flipping_declared_convention_reports_instability`

Replace only the `Weight(...)` construction inside this one test (same `_params`/`_run` harness,
same `_flipped_copy(..., "code")` call, same two assertions — nothing else in the test changes):

```python
def test_flipping_declared_convention_reports_instability():
    with _flipped_copy("example_v2.csv", "test_v2_flipped.csv", "code") as name:
        # Step 116 (D-125): a thinner margin than _params()'s default geometry -- needed so a
        # wrongly-declared cm_convention actually flips the *combined* stability criterion, not
        # just the standalone cm_slope. At the default geometry (l_d=0.8, l_p=1.3) this table's
        # ample margin term dominates the C_m contribution regardless of its sign (verified
        # numerically: combined stays at a constant -0.715, still "stable" under the unified
        # criterion even with the wrong convention declared) -- this geometry is deliberately
        # thinned so the flip crosses zero (verified: -0.065 declared correctly vs +0.035
        # declared wrong).
        p = Params(
            weight=Weight(m=2.0, I=0.1, m_d=1.5, l_d=1.05, l_p=1.55, I_d=0.08, I_sp=200.0),
            lengths=Lengths(l2=0.4),
            aero=Aero(model="table", S=0.01, d_ref=0.1, table=name),
            solver=Solver(method="rk4", dt=0.01, t_max=2.0),
        )
        r = _run(p)
        with pytest.warns(UserWarning, match="unstable"):
            out = stability_check(r, p)
        assert out["stable"] is False
        assert out["min_cm_slope"] < 0.0
```

This no longer calls the shared `_params(name)` helper (whose geometry is now wrong for this one test)
— it builds `Params` directly, same fields/values `_params` uses otherwise, just the thinned
`Weight`. Numerically verified end-to-end (not just the `combined_slope` formula in isolation):
`stability_check` on this exact fixture gives `max_stability_slope ≈ +0.035` (`stable=False`,
warning fires) with the "code"-declared (wrong, unflipped) table, and `≈ -0.065` (`stable=True`, no
warning) if `_flipped_copy` is swapped to `"standard"` (correctly flipped) — confirming the fixture
discriminates the two cases the test name promises, under the corrected criterion.

Run the point-in-time test files first (`python -m pytest tests/test_report.py tests/test_aero_fb.py
tests/test_aero_v2.py tests/test_scenario_sweep.py -q`), then the full suite in the background per
`CLAUDE.md` before considering the step done — confirm no trajectory/integration pin outside
`sim/report.py`'s own diagnostics moved (the whole point of Option A is that `sim/dynamics.py` is
untouched).

## §116.8 LaTeX — the only two approved edits (D-125)

**`dev/docs/latex/` is otherwise strictly read-only per `CLAUDE.md`.** These two edits are the entire
scope of the exception the user approved for D-125 — do not touch anything else in either file, or any
other file under `dev/docs/latex/`.

**Edit 1 — `dev/docs/latex/sections-ai/rocket-2d.tex`, lines 59-60.** Current:

```latex
    \item $p$ --- aerodynamic reference point (centre of pressure), where $\vec{A}_f$ acts and
    about which $\vec{A}_m$ is taken.
```

Replace with:

```latex
    \item $p$ --- aerodynamic \emph{moment reference} point, where $\vec{A}_f$ is taken to act and
    about which $\vec{A}_m$ is taken; the centre of pressure is the derived station
    $l_p - C_m\,c/C_z$ (\autoref{sec:analysis_stability}).
```

(Label confirmed on this branch: `analysis.tex:106` is `\subsection{Static stability}\label{sec:analysis_stability}`,
the subsection containing both the static-margin paragraph (Edit 2 below) and `eq:static_margin` — use
this exact label, already verified to exist, not a guess.)

**Edit 2 — `dev/docs/latex/sections-ai/analysis.tex`, lines 132-138.** Current paragraph (the "Static
margin, in calibers" block):

```latex
\paragraph{Static margin, in calibers.} The rocketry convention divides the arm by the reference
length and flips the sign so that a stable rocket gets a positive number:
\begin{equation}
    \mathrm{SM} = \frac{l_p-l_g}{c}.
\end{equation}
The CoP then sits $\mathrm{SM}$ body diameters aft of the CoG, and \autoref{eq:static_margin} is
equivalent to $\mathrm{SM}>-C_{m,\alpha}/C_{z,\alpha}$.
```

Replace with:

```latex
\paragraph{Static margin, in calibers.} $p$ is a moment reference station, not necessarily the centre
of pressure (\autoref{sec:geometry}): the CP is the derived station at which the moment slope about it
vanishes,
\begin{equation}
    l_{cp} = l_p - c\,\frac{C_{m,\alpha}}{C_{z,\alpha}},
\end{equation}
and the rocketry convention divides the CP-to-CoG arm by the reference length, flipping the sign so a
stable rocket gets a positive number:
\begin{equation}
    \mathrm{SM} = \frac{l_{cp}-l_g}{c} = \frac{l_p-l_g}{c} - \frac{C_{m,\alpha}}{C_{z,\alpha}}.
\end{equation}
$\mathrm{SM}>0$ is then equivalent to \autoref{eq:static_margin}; the two coincide, $l_{cp}=l_p$, exactly
when $C_{m,\alpha}=0$ about $p$ (the degenerate case where $p$ already is the CP).
```

This keeps the existing `eq:static_margin` inequality (line 123-125, unchanged, out of scope) as the
underlying stability condition, and makes the SM formula consistent with §116.3/§116.4's code (derived
`l_cp`, single criterion) instead of contradicting the paper's own line-126-128 caveat the audit flagged.

## §116.9 Known limitation note (`l_p == 0.0` double duty) — document, do not fix

`Aero.l_p == 0.0` is simultaneously "off" (legacy arm mode, `_arm_or_station`/`uses_l_p`, lines 425/433)
and the most common real CFD moment-reference choice (the nose tip). A user cannot currently express
"my moment reference station is the nose tip" under `"constant"`/`"linearized"` — only a v2 table can
(`l_p_m = 0.0` in a table *is* expressible, since `uses_l_p` checks `table.l_p is not None`, not its
value; only the scalar `Aero.l_p` field has the 0.0-means-off collision). Add one sentence noting this
to `uses_l_p`'s docstring (`sim/aero.py:428-430`, appended, not replacing the wording change from
§116.5):

```python
def uses_l_p(p) -> bool:
    """True when the moment reference is given as a station from the nose (`x_ref`, an `l_p_m` table,
    or `Aero.l_p > 0` under constant/linearized) rather than as the arm `l1`.

    Known limitation (not fixed here): `Aero.l_p == 0.0` also means "off" for constant/linearized
    models, so a user cannot express "my moment reference station is the nose tip" there even though
    it is the most common CFD convention -- a v2 table does not have this problem (`l_p_m = 0.0` is a
    normal station value, only the scalar `Aero.l_p` field collides with its own off-switch)."""
```

Suggest filing this as backlog **B34** (next free ID — B33 is the highest currently used, confirmed via
`grep -n "B3[0-9]" dev/status.json dev/docs/*.md`); registering it in `dev/status.json`/`backlog.md` is
the orchestrator's/tracker's job, not this ticket's — just flag it in the step's completion report.

## §116.10 Definition of done

- [ ] `sim/aero.py`: `C_N` takes `fb=0.0`, calls `_dispatch` (§116.2); wording-only edits at the nine
      spots in §116.5's table; `uses_l_p` docstring gets the §116.9 limitation sentence.
- [ ] `sim/report.py`: `static_margin_cal` rewritten per §116.3 (gated on `uses_l_p`, `_CZ_SLOPE_EPS`
      guard); new `combined_stability_slope_series` (§116.4, ungated, NEGATIVE = restoring); `stability_check`
      rewritten to return `{min_margin_cal, min_cm_slope, max_stability_slope, stable}` with `stable`
      driven only by `max_stability_slope <= 1e-9` (`.max()`, not `.min()` — see §116.4's correction note).
- [ ] `configs/rockets/_TEMPLATE_rocket.py` lines 96 and 211 reworded per §116.6.
- [ ] `data/aero/example_v2.csv` header comment reworded per §116.6.
- [ ] `tests/test_report.py`'s one hard-literal pin replaced per §116.7; its
      `test_flipping_declared_convention_reports_instability` fixture replaced per §116.7a;
      `tests/test_aero_fb.py`, `tests/test_scenario_sweep.py` run and confirmed unchanged
      (sign/relational assertions only).
- [ ] `dev/docs/latex/sections-ai/rocket-2d.tex` lines 59-60 and `analysis.tex` lines 132-138 — exactly
      these two spots, per §116.8 (check the real `\autoref` label before pasting Edit 1).
- [ ] Point-in-time test files green, then full suite green in background (`CLAUDE.md` convention);
      confirm zero pin movement outside `sim/report.py`'s own diagnostic tests (dynamics/trajectory
      pins untouched, per D-125).
- [ ] `code-review` skill run before handing to QA (project convention, feature branch
      `feature/sim-paper-alignment`).

### [STEP-116] Relabel `l_p`/`l_p_m` as the moment reference station; derive CP/static margin; single stability criterion
- **Module/boundaries:** `sim/aero.py`, `sim/report.py`, `configs/rockets/_TEMPLATE_rocket.py`,
  `data/aero/example_v2.csv`, `tests/test_report.py`, `tests/test_aero_fb.py` (verify only),
  `tests/test_scenario_sweep.py` (verify only), `dev/docs/latex/sections-ai/rocket-2d.tex` (lines 59-60
  only), `dev/docs/latex/sections-ai/analysis.tex` (lines 132-138 only).
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (touches `sim/aero.py`/`sim/report.py`, shared modules other in-flight work
  on this branch may also touch; and the LaTeX exception is a one-off, sequence it with nothing else
  landing on `dev/docs/latex/` at the same time)

Implement per §116.1-§116.9 above; tick off §116.10 before handing to QA.
