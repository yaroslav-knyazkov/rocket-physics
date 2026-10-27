# Step 117 (D-126) — rename the internal, always-code-sign `C_m`/`C_mq` to `C_m_code`/`C_mq_code`

## Кратко (RU)

Тикет закрывает §1.1 аудита (`dev/docs/conventions-industry-standard-analysis.md`), опцию (c),
одобренную пользователем как D-126: **код не меняется** (перевёрнутая математика `C_m` остаётся как
есть), но **внутреннее, всегда-code-convention значение после диспетчеризации** получает честное имя
`C_m_code`/`C_mq_code` вместо того, чтобы делить имя `C_m` со стандартным символом. Ключевое архитектурное
решение: граница ввода-вывода (`Params.aero.C_m`/`C_m_alpha`/`c_mq`, заголовки CSV-таблиц `C_m`/`c_mq`,
`cm_convention`) **не переименовывается** — она уже convention-aware с Step 99/D-111 (пользователь
объявляет `code|standard`, конвертация на загрузке), так что это и есть тот самый "свободный `C_m` на
границе ввода-вывода", о котором говорит D-126; переименовывать там нечего. Переименованию подлежат
только: `AeroCoeffs.C_m`/`C_mq` (возвращается `aero.coefficients(...)`), `_AeroTable.C_m`/`C_mq`
(загруженный/сконвертированный массив) и обёртки `aero.C_m()`/`aero.C_mq()` — то есть ровно те места,
которые всегда code-sign и могут молча обмануть читателя. Схема имён: суффикс `_code`
(`C_m_code`/`C_mq_code`), не `C_n` — коллизия с уже существующим `C_N` (нормальная сила) была признана
реальным риском читаемости. Реальный объём правок оказался заметно меньше оценки аудита (34/12 файлов):
большинство совпадений — это как раз граница ввода-вывода, которая не трогается. Правятся 5
production-файлов (`sim/aero.py`, `sim/forces.py`, `sim/control.py`, `sim/report.py`,
`sim/params.py` — только однострочный доворот докстринга `l_p`, не связанный с `C_m`) и 8 тестовых
файлов. Ноль числовых пинов, ноль правок в `dev/docs/latex/`, `_table_coeffs`'ый скалярный фолбэк
`c_mq` (строка ~667) не трогается — это Step 119/B36.

---

## Table of contents

- §117.1 Scope and non-goals
- §117.2 Design decision 1 — what gets renamed, what stays `C_m`
- §117.3 Design decision 2 — naming scheme
- §117.4 Design decision 3 — what "freeing the I/O boundary" means operationally, today
- §117.5 Pin safety — how this was checked
- §117.6 `sim/aero.py` — exact rename, grouped by function
- §117.7 `sim/forces.py`, `sim/control.py`, `sim/report.py` — exact rename
- §117.8 `sim/params.py` — one-line `l_p` docstring fix (unrelated bundled fix, point 6)
- §117.9 Tests — exact file-by-file impact
- §117.10 Acceptance checks (zero-remaining-matches)
- §117.11 Open questions / deliberately deferred
- §117.12 Definition of done

---

## §117.1 Scope and non-goals

**In scope:**
- `sim/aero.py`: `AeroCoeffs.C_m`/`C_mq` fields, `_AeroTable.C_m`/`C_mq` fields, the `C_m()`/`C_mq()`
  per-coefficient wrapper functions, every call site and docstring/comment mention of these specific,
  always-code-sign quantities inside this one file.
- `sim/forces.py`: the two `AeroCoeffs` attribute reads in `aero_moment_y` (`c.C_m`, `c.C_mq`) and the
  one docstring line naming them.
- `sim/control.py`: the docstring that lists `AeroCoeffs`' perturbable fields and the `_replace(...)`
  example.
- `sim/report.py`: every `aero.C_m(...)` call site (6, all added/kept by Step 116) and the docstring
  formula mentions that mirror them.
- `sim/params.py`: **one line only** — the `Aero.l_p` field's own docstring, a leftover from Step 116
  that commit `62733b1` did not touch (verified below, point 6 of the brief). This is bundled, trivial,
  and unrelated to the `C_m` rename — do not let it anchor any other change in this file.
- 8 test files (exact list, §117.9).

**Out of scope / do not touch:**
- `Params.aero.C_m`, `Params.aero.C_m_alpha`, `Params.aero.c_mq`, `Params.aero.cm_convention` — stay
  named exactly as today (§117.2's decision).
- Any `data/aero/*.csv` column header — stays `C_m`/`c_mq` (same decision).
- `configs/rockets/_TEMPLATE_rocket.py`, `configs/rockets/demo.py`, `configs/schema.py`, `run.py`,
  `apps/**` — verified (§117.2/§117.9): every occurrence in these files is an `Aero(...)` config
  construction, a `p.aero.C_m`/`p.aero.c_mq` config-field read, or prose describing the config field —
  none is the internal `AeroCoeffs`/`_AeroTable` field or the `aero.C_m()`/`aero.C_mq()` wrapper. **Zero
  files in `configs/`, `apps/`, `data/` need any edit for this step.**
- `_cm_to_code` — name unchanged (already honest: it converts *to* the code convention, regardless of
  what the converted field ends up being called). Its own parameter, confusingly also named `C_m` even
  when called with a `c_mq` value (`_cm_to_code(p.aero.c_mq, p)`), is a pre-existing wart orthogonal to
  this rename (a private helper's local parameter name, not a public symbol) — not fixed here, flagged
  in §117.11.
- `sim/aero.py`'s `_table_coeffs` scalar `c_mq` fallback (~line 667, `Params.aero.c_mq` used raw when a
  table lacks a `c_mq` column) — explicitly Step 119/B36, untouched.
- `cm_convention` mechanism itself (`_load_table`'s header parsing, `CM_CONVENTIONS`, `_cm_to_code`) —
  unchanged; this step renames a *consumer* of its output, not the mechanism.
- Any file under `dev/docs/latex/` — zero edits, no exceptions (see the brief's framing: the user's
  "yes" to option (c) never covered a LaTeX edit; flagged as a known, deliberately-deferred gap in
  §117.11, not decided here).
- Any numeric literal, any arithmetic expression, any test assertion's expected *value* — pure identifier/
  header/comment/docstring rename only (§117.5).

## §117.2 Design decision 1 — what gets renamed, what stays `C_m`

**The dividing line is not "input vs. output" in the generic sense — it is "does this symbol's meaning
depend on a declared `cm_convention`, or is it always, unconditionally, the code's own sign?"**

| Symbol | Layer | Convention-aware? | Decision |
|---|---|---|---|
| `Params.aero.C_m` | config field, `"constant"` model input | yes — flipped by `_cm_to_code` using `cm_convention` before use | **stays `C_m`** |
| `Params.aero.C_m_alpha` | config field, `"linearized"` model input | yes, same mechanism | **stays `C_m_alpha`** |
| `Params.aero.c_mq` | config field, scalar pitch-damping input (all 3 models) | yes (Step 115 fixed the constant/linearized path to flip it too) | **stays `c_mq`** |
| `Params.aero.cm_convention` | config field, the declaration itself | n/a — it's the flag | **stays `cm_convention`** |
| CSV column `C_m` | table input | yes — `# cm_convention:` header declares it, flipped on load | **stays `C_m`** |
| CSV column `c_mq` | table input | yes (Step 114 flip) | **stays `c_mq`** |
| `_AeroTable.C_m` | loaded/converted in-memory array | **no** — always already-flipped-to-code-sign by the time it's stored (the flip happens at load, `sim/aero.py:260-261`); nothing about reading this field tells you a conversion already happened | **RENAME → `C_m_code`** |
| `_AeroTable.C_mq` | same, Step 114's flip | same reasoning | **RENAME → `C_mq_code`** |
| `AeroCoeffs.C_m` | post-dispatch, every downstream consumer reads this | **no** — this is the exact harm the audit names: a standard symbol, non-standard meaning, consumed by `sim/forces.py`, `sim/dynamics.py` (via `l1`, unaffected itself), `sim/report.py` with zero local indication of the flip | **RENAME → `C_m_code`** |
| `AeroCoeffs.C_mq` | same | same | **RENAME → `C_mq_code`** |
| `aero.C_m(alpha, M, p, fb)` (function) | per-coefficient wrapper around `_dispatch(...).C_m` | no — same always-code-sign value as the field above, just reached a different way | **RENAME → `aero.C_m_code(alpha, M, p, fb)`** |
| `aero.C_mq(alpha, M, p)` (function) | same | same | **RENAME → `aero.C_mq_code(alpha, M, p)`** |
| `_cm_to_code` | the conversion helper itself | n/a | **stays** (already honest; see §117.1) |

**Why the config fields and CSV columns are not the harm, even though they're also named `C_m`:** a user
who writes `Aero(cm_convention="standard", C_m=0.3)` is using the standard symbol *correctly* for a value
they are declaring in the standard convention — the field's docstring, right next to it, says exactly
what convention applies, and `_cm_to_code` is the single, visible, auditable place the flip happens. The
harm the audit names is specifically that **after** that point, in `AeroCoeffs`/`_AeroTable`/the wrapper
functions, the *same* identifier `C_m` reappears with the opposite guarantee (always code-sign,
regardless of what was declared) and nothing marks the difference. Renaming only the post-conversion
layer removes exactly that ambiguity and nothing else; renaming the config/table layer too would not
remove any additional harm (that layer was never ambiguous) and would needlessly touch
`configs/`/`data/`/`apps/` for zero benefit — correctly out of scope per the brief's own framing of
option (c).

**`C_mq` renames in lockstep with `C_m`, not deferred.** Per the audit's §1.2, `C_mq` carries exactly
`C_m`'s flip (it is `C_m`'s derivative with respect to a nondimensional rate, nothing independent). Once
`AeroCoeffs.C_m` is honestly named `C_m_code`, leaving its sibling `AeroCoeffs.C_mq` under the old,
ambiguous name would be a *new*, freshly-introduced inconsistency within the same tuple — worse than
today's uniform-but-ambiguous state. Renaming both together is strictly better and costs nothing extra
(the audit's own 12-file/135-line estimate for `c_mq`/`C_mq` overlaps almost entirely with the 34-file
`C_m` estimate — same files, same functions, same commits touch both).

## §117.3 Design decision 2 — naming scheme

**Chosen: `_code` suffix (`C_m_code`, `C_mq_code`), not `C_n`.**

The audit offered `C_m_code` or `C_n` ("nose-down moment coefficient"). `C_n` is rejected: this codebase
already has `C_N` (capital N, normal-force coefficient, `sim/aero.py`'s `C_N` function and
`AeroCoeffs.C_z`/`Params.aero.C_N_alpha`) as an established synonym for normal force. Introducing `C_n`
(lowercase n) as a *different* quantity (pitching moment) one capitalization away from `C_N` (normal
force) in a project that already tracks two spellings of normal force (`C_z`/`C_N`) is a concrete,
foreseeable misread risk, not a hypothetical one — exactly the kind of new confusion a rename meant to
*reduce* confusion should not introduce. `C_m_code` is unambiguous, greppable (`C_m_code` cannot be
mistaken for `C_m_alpha` or a config field), and self-documenting (the suffix states the one fact that
actually matters: "this is in the code's sign convention, unconditionally").

**Applied uniformly to the damping derivative for parity: `C_mq_code`** (not `C_n_q` or any unrelated
scheme) — same suffix, same reasoning, keeps the sibling pair visually paired the way `C_m`/`C_mq` are
today.

## §117.4 Design decision 3 — what changes operationally today vs. what is still aspirational

Per D-126's own wording, this step "frees `C_m` for the real convention at the I/O boundary" — but
**nothing needs to be built for that today**, because (as §117.2 shows) the I/O boundary already *is*
convention-aware and already uses the bare name `C_m` correctly, since Step 99/D-111. There is no new
"standard-sign consumer" to write, and none is written here — that would be silently doing option (b)'s
(deferred) work.

**What this step actually changes, concretely:** before this step, two different layers of the same
codebase both answer to the identifier `C_m` with two different guarantees (config/table: "whatever
convention I declared"; `AeroCoeffs`/wrapper: "always code-sign, no matter what was declared") — a single
name, two meanings, depending on which side of `_cm_to_code`/the table-load flip you're reading. After
this step there is exactly one meaning left for the bare name `C_m` in this codebase (the I/O-boundary,
convention-declared one); the other meaning has its own, honest name (`C_m_code`). The inverted internal
math is unchanged; the sign flip at load is unchanged; the only thing that changes is which identifier a
reader sees when looking at the always-flipped internal value, so that seeing `AeroCoeffs.C_m_code`
(rather than `AeroCoeffs.C_m`) is itself the signal "this is already in code sign, not necessarily what
you declared." The symbol `C_m` is not "reserved but unused" anywhere new — it is already in active,
correct use at the I/O boundary; this step just stops a second, conflicting use of the same text
existing one layer downstream.

## §117.5 Pin safety — how this was checked

**Zero numeric pin movement; this is a pure identifier/header/comment/docstring rename.** Verified by
construction, not by running the suite blind:

- Every production-code edit in §117.6/§117.7 is one of: (a) a `dataclass`/`NamedTuple` field name in a
  `class` statement, (b) a keyword argument name in a call that constructs or `._replace()`s one of those
  types, (c) an attribute-access expression (`x.C_m` → `x.C_m_code`) reading such a field, (d) a `def`
  name and its call sites, (e) prose inside a docstring or `#` comment. None of these categories can
  change a float value: a keyword name does not affect which positional value flows into the field: it is
  still the exact same expression on the right-hand side of `=` in every edit below (confirm this
  visually against each "replace X with Y" block — the right-hand-side expression is never touched,
  only the left-hand-side name).
- The one place arithmetic and a rename are on the same line (`sim/aero.py` lines 573-574, 623-624,
  671-672, 731 and `sim/forces.py` lines 291-292) — in every one of these the renamed token is strictly
  the kwarg/attribute name; the formula producing the value (`_cm_to_code(p.aero.C_m, p)`,
  `_table_lookup(table, alpha, M, table.C_m)`, `(1.0 - w) * clamped.C_m + w * Cm_J`, `flow.q * p.aero.S *
  p.aero.d_ref * c.C_m`, etc.) is reproduced byte-for-byte in §117.6/§117.7's replacement blocks, with
  only the identifier(s) swapped.
- CSV data rows are untouched everywhere (CSV headers themselves are also untouched — §117.2's decision
  keeps them `C_m`/`c_mq`, so `data/aero/*.csv` has **zero** edits in this step, not even a header).
- Full suite expected: **705/705**, bit-for-bit, same as the post-Step-116 baseline — this step changes
  no test's expected *value*, only which identifier the test's code uses to read/construct the value.

## §117.6 `sim/aero.py` — exact rename, grouped by function

All line numbers are current on `feature/sim-paper-alignment` as of this ticket (verified by direct
read, not by trusting the audit's count). **Rule for every line below not explicitly reproduced**: if a
line contains `C_m`/`C_mq` and is not listed as "STAYS" in this section, treat it as covered by the
"RENAME" rule of the enclosing block (do not silently skip any occurrence inside a renamed block).

### Module docstring (lines 1-2, 35, 97)

```
# line 1-2, replace:
"""Aerodynamic coefficients C_x(alpha, M), C_z(alpha, M), C_m(alpha, M),
C_mq(alpha, M) and the CoP-to-CoG distance l1(alpha, M) -- an explicit
# with:
"""Aerodynamic coefficients C_x(alpha, M), C_z(alpha, M), C_m_code(alpha, M),
C_mq_code(alpha, M) and the CoP-to-CoG distance l1(alpha, M) -- an explicit
```

```
# line 35, replace:
`AeroCoeffs`'s own docstring lists the fields. `C_A`/`C_N`/`C_m`/`C_mq`/
# with:
`AeroCoeffs`'s own docstring lists the fields. `C_A`/`C_N`/`C_m_code`/`C_mq_code`/
```

```
# line 97, replace:
`C_A`/`C_m`/`cop_l1` for one uniform interface -- the `"constant"`/
# with:
`C_A`/`C_m_code`/`cop_l1` for one uniform interface -- the `"constant"`/
```

**Line 25** (history note, "`"constant"`'s `C_x`/`C_z`/`C_m` used to be raw-Newton/Newton-metre
placeholders"): rename `C_m` → `C_m_code` (describes the `AeroCoeffs` field this model populates).

**Lines 49, 68, 75, 116-117, 244** — **STAYS unchanged.** These are, respectively: the module's own CSV
format documentation (`alpha_deg,M,C_A,C_N,C_m,l1_m,c_mq`), prose about what `cm_convention` declares,
the table-column list in the `f_b` note, the `cm_convention` concept comment, and the CSV
required-column check (`missing = [c for c in (..., "C_m") if c not in header]`) — all I/O-boundary
column-name references (§117.2).

### `_load_table` (lines 179-334)

`_AeroTable` class fields (lines 179-187), replace:

```python
class _AeroTable(NamedTuple):
    M: np.ndarray       # (n_M,), ascending
    alpha: np.ndarray   # (n_alpha,), ascending, radians
    C_A: np.ndarray     # (n_M, n_alpha)
    C_N: np.ndarray     # (n_M, n_alpha)
    C_m: np.ndarray     # (n_M, n_alpha)
    l1: "np.ndarray | None"   # (n_M, n_alpha), CoP-to-CoG distance [m]; None for a v2 (`l_p_m`) table
    C_mq: "np.ndarray | None"  # (n_M, n_alpha), pitch-damping derivative, or None when the column is absent
    l_p: "np.ndarray | None" = None  # (n_M, n_alpha), moment reference station from the nose [m] (`x_ref`); None for a legacy (`l1_m`) table
```

with:

```python
class _AeroTable(NamedTuple):
    M: np.ndarray       # (n_M,), ascending
    alpha: np.ndarray   # (n_alpha,), ascending, radians
    C_A: np.ndarray     # (n_M, n_alpha)
    C_N: np.ndarray     # (n_M, n_alpha)
    C_m_code: np.ndarray     # (n_M, n_alpha) -- always code sign (post `cm_convention` flip at load, Step 117/D-126)
    l1: "np.ndarray | None"   # (n_M, n_alpha), CoP-to-CoG distance [m]; None for a v2 (`l_p_m`) table
    C_mq_code: "np.ndarray | None"  # (n_M, n_alpha), pitch-damping derivative (always code sign, Step 117), or None when the column is absent
    l_p: "np.ndarray | None" = None  # (n_M, n_alpha), moment reference station from the nose [m] (`x_ref`); None for a legacy (`l1_m`) table
```

Lines 259-261, 278-282 (**STAYS** — local variables `C_m_col`/`C_mq_col` and the CSV dict keys
`data["C_m"]`/`data["c_mq"]` are not public symbols; see §117.1's explicit out-of-scope note). Reproduced
for clarity, unchanged:

```python
    C_m_col = data["C_m"].astype(float)
    if cm_convention == "standard":  # D-111: textbook sign -> the code's (positive = nose-down)
        C_m_col = -C_m_col
    ...
    C_mq_col = data["c_mq"].astype(float) if "c_mq" in data.dtype.names else None
    if C_mq_col is not None and cm_convention == "standard":
        # Step 114: the textbook C_mq < 0 (damping) -> the code's sign (positive = damping),
        # the same flip as C_m above.
        C_mq_col = -C_mq_col
```

`_plane`'s `_AeroTable(...)` construction (lines 324-333), replace the two kwargs:

```python
# replace:
            C_m=_reshape(C_m_col),
            l1=_reshape(l1_col) if l1_col is not None else None,
            C_mq=_reshape(C_mq_col) if C_mq_col is not None else None,
# with:
            C_m_code=_reshape(C_m_col),
            l1=_reshape(l1_col) if l1_col is not None else None,
            C_mq_code=_reshape(C_mq_col) if C_mq_col is not None else None,
```

### `_at_fb` blend (lines 383-384)

Replace:

```python
        C_A=_mix(lo.C_A, hi.C_A), C_N=_mix(lo.C_N, hi.C_N), C_m=_mix(lo.C_m, hi.C_m),
        l1=_mix(lo.l1, hi.l1), C_mq=_mix(lo.C_mq, hi.C_mq), l_p=_mix(lo.l_p, hi.l_p),
```

with:

```python
        C_A=_mix(lo.C_A, hi.C_A), C_N=_mix(lo.C_N, hi.C_N), C_m_code=_mix(lo.C_m_code, hi.C_m_code),
        l1=_mix(lo.l1, hi.l1), C_mq_code=_mix(lo.C_mq_code, hi.C_mq_code), l_p=_mix(lo.l_p, hi.l_p),
```

### `AeroCoeffs` (lines 403-408) and `_cm_to_code` (lines 411-419, STAYS)

Replace:

```python
class AeroCoeffs(NamedTuple):
    C_x: float    # axial-force coefficient      (today's C_A)
    C_z: float    # normal-force coefficient     (today's C_N)
    C_m: float    # pitching-moment coefficient
    C_mq: float   # pitch-damping derivative
    l1: float     # CoP(D)-to-CoG(B) distance [m]
```

with:

```python
class AeroCoeffs(NamedTuple):
    C_x: float    # axial-force coefficient      (today's C_A)
    C_z: float    # normal-force coefficient     (today's C_N)
    C_m_code: float    # pitching-moment coefficient, ALWAYS code sign (post-dispatch/post-`_cm_to_code`;
                        # Step 117/D-126 rename -- do not read this as the declared `cm_convention`,
                        # it is already flipped to the code's convention regardless of input).
    C_mq_code: float   # pitch-damping derivative, same always-code-sign guarantee as C_m_code.
    l1: float     # CoP(D)-to-CoG(B) distance [m]
```

`_cm_to_code` (lines 411-419) **STAYS verbatim, including its `C_m` parameter name** (§117.1's explicit
call: a private helper's formal parameter, reused for both `C_m`- and `c_mq`-shaped inputs, pre-existing,
orthogonal to this rename — see §117.11).

### `_arm_or_station`/`uses_l_p`/`cg_station`/`_resolve_arm` (lines 422-462) — **no change**

None of these four functions mention `C_m`/`C_mq` at all (they operate on `l1`/`l_p`/the CoG station) —
confirmed by direct read; not touched by this ticket.

### `_constant_coeffs` (lines 551-576)

Docstring, replace:

```
    Step 55's actual fix: `C_x`/`C_z`/`C_m` are true dimensionless
```
with
```
    Step 55's actual fix: `C_x`/`C_z`/`C_m_code` are true dimensionless
```
and replace:
```
    `C_z`/`C_m` are deliberately unchanged (D-95).
```
with
```
    `C_z`/`C_m_code` are deliberately unchanged (D-95).
```

Return statement, replace:

```python
    return AeroCoeffs(
        C_x=p.aero.C_x * axial_flow_factor(alpha),
        C_z=p.aero.C_z,
        C_m=_cm_to_code(p.aero.C_m, p),
        C_mq=_cm_to_code(p.aero.c_mq, p),
        l1=_arm_or_station(p),
    )
```

with (note: `p.aero.C_m`/`p.aero.c_mq`, the config-field reads on the right-hand side, are **unchanged**
— only the kwarg names on the left change):

```python
    return AeroCoeffs(
        C_x=p.aero.C_x * axial_flow_factor(alpha),
        C_z=p.aero.C_z,
        C_m_code=_cm_to_code(p.aero.C_m, p),
        C_mq_code=_cm_to_code(p.aero.c_mq, p),
        l1=_arm_or_station(p),
    )
```

### `_linearized_coeffs` (lines 579-626)

Docstring, replace the two bare mentions:
```
    Phase 2.5 (after Step 35): `C_z`/`C_m`'s formula uses `sin(alpha)`
```
→
```
    Phase 2.5 (after Step 35): `C_z`/`C_m_code`'s formula uses `sin(alpha)`
```
and
```
    `C_z`/`C_m`'s sign and (being unbounded) magnitude every RHS call,
```
→
```
    `C_z`/`C_m_code`'s sign and (being unbounded) magnitude every RHS call,
```

Return statement, replace:

```python
    return AeroCoeffs(
        C_x=p.aero.C_A0 * axial_flow_factor(alpha),
        C_z=p.aero.C_N_alpha * np.sin(alpha),
        C_m=_cm_to_code(p.aero.C_m_alpha * np.sin(alpha), p),
        C_mq=_cm_to_code(p.aero.c_mq, p),
        l1=_arm_or_station(p),
    )
```

with (again, `p.aero.C_m_alpha`/`p.aero.c_mq` config reads unchanged):

```python
    return AeroCoeffs(
        C_x=p.aero.C_A0 * axial_flow_factor(alpha),
        C_z=p.aero.C_N_alpha * np.sin(alpha),
        C_m_code=_cm_to_code(p.aero.C_m_alpha * np.sin(alpha), p),
        C_mq_code=_cm_to_code(p.aero.c_mq, p),
        l1=_arm_or_station(p),
    )
```

### `_table_coeffs` (lines 629-692)

Docstring, four spots:
```
    """`"table"`: `C_A, C_N, C_m` and `l1` read from `p.aero.table`
```
→
```
    """`"table"`: `C_A, C_N, C_m_code` and `l1` read from `p.aero.table`
```
```
    `C_mq` (Step 44, architecture.md SS24.4): table-driven only when the
```
→
```
    `C_mq_code` (Step 44, architecture.md SS24.4): table-driven only when the
```
```
    `C_m` is a nose-down moment here), the opposite of the textbook
```
→
```
    `C_m_code` is a nose-down moment here), the opposite of the textbook
```
Line `` `C_mq < 0`, the same flip `C_m_alpha` already carries. `` **STAYS** (describes the textbook
symbol generically and the config field `C_m_alpha` — neither is the renamed field).

Body (lines 663-676), replace:

```python
    table = _at_fb(_load_table(p.aero.table), fb)
    if table.C_mq is not None:
        C_mq = _table_lookup(table, alpha, M, table.C_mq)
    else:
        C_mq = p.aero.c_mq
    clamped = AeroCoeffs(
        C_x=_table_lookup(table, alpha, M, table.C_A) * _table_axial_factor(table, alpha),
        C_z=_table_lookup(table, alpha, M, table.C_N),
        C_m=_table_lookup(table, alpha, M, table.C_m),
        C_mq=C_mq,
        # Step 99: legacy table -> the arm itself; v2 table -> the CP station
        # (turned into an arm by `_resolve_arm`, which knows the CoG).
        l1=_table_lookup(table, alpha, M, table.l1 if table.l1 is not None else table.l_p),
    )
```

with:

```python
    table = _at_fb(_load_table(p.aero.table), fb)
    if table.C_mq_code is not None:
        C_mq_code = _table_lookup(table, alpha, M, table.C_mq_code)
    else:
        C_mq_code = p.aero.c_mq
    clamped = AeroCoeffs(
        C_x=_table_lookup(table, alpha, M, table.C_A) * _table_axial_factor(table, alpha),
        C_z=_table_lookup(table, alpha, M, table.C_N),
        C_m_code=_table_lookup(table, alpha, M, table.C_m_code),
        C_mq_code=C_mq_code,
        # Step 99: legacy table -> the arm itself; v2 table -> the CP station
        # (turned into an arm by `_resolve_arm`, which knows the CoG).
        l1=_table_lookup(table, alpha, M, table.l1 if table.l1 is not None else table.l_p),
    )
```

(Judgment call, flagged per the brief's request: the local variable `C_mq`/now `C_mq_code` at lines
664-667 is renamed too, unlike `C_m_col`/`C_mq_col` in `_load_table`. Reasoning: this one is a 4-line-
lived local whose sole purpose is to become the `AeroCoeffs.C_mq_code` kwarg two lines below — keeping it
textually matched to the field it feeds avoids a misleading "local says C_mq, field says C_mq_code"
read directly adjacent in the same ~10 lines. `C_m_col`/`C_mq_col` in `_load_table` are different: they
live for ~70 lines, are never read again after the `_plane(...)` call, and renaming them buys nothing a
reader of `_load_table` would notice.)

`p.aero.c_mq` on its own line (the fallback) is a config-field read — **unchanged**.

### `_jorgensen_extend` (lines 700-732)

Docstring, replace:
```
    into Jorgensen's large-alpha model beyond the table edge. `C_mq` and `l1` stay the clamped
```
with
```
    into Jorgensen's large-alpha model beyond the table edge. `C_mq_code` and `l1` stay the clamped
```

Line 530 (same function's later docstring, Jorgensen OOB section — confirmed same function on this
branch), replace:
```
    "extension scales the edge C_m by Z(alpha)/Z(alpha_edge) with Z = sin(2a)cos(a/2), "
```
with
```
    "extension scales the edge C_m_code by Z(alpha)/Z(alpha_edge) with Z = sin(2a)cos(a/2), "
```

Body, replace:

```python
    cm_e = _table_lookup(table, a_e, M, table.C_m)
```
with
```python
    cm_e = _table_lookup(table, a_e, M, table.C_m_code)
```

and replace:

```python
    return clamped._replace(
        C_x=(1.0 - w) * clamped.C_x + w * Cx_J,
        C_z=(1.0 - w) * clamped.C_z + w * Cz_J,
        C_m=(1.0 - w) * clamped.C_m + w * Cm_J,
    )
```

with:

```python
    return clamped._replace(
        C_x=(1.0 - w) * clamped.C_x + w * Cx_J,
        C_z=(1.0 - w) * clamped.C_z + w * Cz_J,
        C_m_code=(1.0 - w) * clamped.C_m_code + w * Cm_J,
    )
```

### `coefficients` docstring (line 763) and `C_N`/`C_m`/`C_mq`/`cop_l1` wrappers (lines 818-857)

Line 763, replace:
```
    override or perturb `C_x`/`C_z`/`C_m`/`l1` as a
```
with
```
    override or perturb `C_x`/`C_z`/`C_m_code`/`l1` as a
```

Line 794 (prose comment just above the wrappers), replace:
```
    # it to compute a force (only tests and report.py's C_m slope diagnostic use these
```
with
```
    # it to compute a force (only tests and report.py's C_m_code slope diagnostic use these
```

`C_N`'s docstring (line 828), replace:
```
    the same as `C_m` -- needed so `sim/report.py`'s derived-CP/combined-stability
```
with
```
    the same as `C_m_code` -- needed so `sim/report.py`'s derived-CP/combined-stability
```
(`C_N` itself is unrenamed and keeps its `fb` parameter unchanged — this is a docstring-only edit.)

`C_m`/`C_mq` function definitions (lines 833-845), replace:

```python
def C_m(alpha: float, M: float, p, fb: float = 0.0) -> float:
    """Pitching-moment coefficient (models.tex: `A_m = qSd_ref*C_m`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps.
    Step 102: optional brake fraction `fb` (read only under `airbrake_aero="table"`)."""
    return _dispatch(alpha, M, p, fb).C_m


def C_mq(alpha: float, M: float, p) -> float:
    """Pitch-damping derivative (analysis.tex SSDynamic stability).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps,
    and `_table_coeffs`'s docstring for the sign convention and the
    optional-column fallback."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).C_mq
```

with:

```python
def C_m_code(alpha: float, M: float, p, fb: float = 0.0) -> float:
    """Pitching-moment coefficient, ALWAYS in the code's sign convention (models.tex:
    `A_m = qSd_ref*C_m`, but see Step 117/D-126 -- this value is already flipped to code
    sign regardless of the declared `cm_convention`; it is not the textbook-sign `C_m`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps.
    Step 102: optional brake fraction `fb` (read only under `airbrake_aero="table"`)."""
    return _dispatch(alpha, M, p, fb).C_m_code


def C_mq_code(alpha: float, M: float, p) -> float:
    """Pitch-damping derivative, ALWAYS in the code's sign convention (analysis.tex
    SSDynamic stability; Step 117/D-126 rename, same guarantee as `C_m_code`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps,
    and `_table_coeffs`'s docstring for the sign convention and the
    optional-column fallback."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).C_mq_code
```

`cop_l1` (lines 848-856) — **no change** (never mentions `C_m`/`C_mq`).

## §117.7 `sim/forces.py`, `sim/control.py`, `sim/report.py` — exact rename

### `sim/forces.py::aero_moment_y` (docstring line 257, body lines 291-292)

Docstring, replace:
```
    Step 55 (architecture-28-rewrite.md SS28.5): `C_m`/`C_mq` come from the
```
with
```
    Step 55 (architecture-28-rewrite.md SS28.5): `C_m_code`/`C_mq_code` come from the
```
and the pseudo-code line just below it, replace:
```
            A_m = q * S * d_ref * c.C_m
```
with
```
            A_m = q * S * d_ref * c.C_m_code
```

Line 264 (`` `c_m += q_hat*c_mq` ``) and line 275 (`` `c_mq = 0.0` (the default) makes this term exactly
`0.0` ``) **STAY unchanged** — the first is physics/math notation (lowercase, describing the formula
conceptually, not a Python identifier), the second is the `Params.aero.c_mq` config-field default
(§117.2).

Body, replace:

```python
    A_m =flow.q * p.aero.S * p.aero.d_ref * c.C_m
    A_m += 0.25 * flow.air.rho * flow.V * p.aero.S * p.aero.d_ref**2 * s[OMEGA] * c.C_mq
```

with:

```python
    A_m =flow.q * p.aero.S * p.aero.d_ref * c.C_m_code
    A_m += 0.25 * flow.air.rho * flow.V * p.aero.S * p.aero.d_ref**2 * s[OMEGA] * c.C_mq_code
```

(`c` is the `AeroCoeffs` returned by `aero.coefficients(...)` a few lines above — attribute access only,
no arithmetic changed.)

### `sim/control.py` module docstring (lines 18, 28)

Replace:
```
identical dispatch dict, `_AERO_COEFF_CONTROLLERS`/`aero_coeff_delta`, lets
a future controller perturb the airframe's own aero coefficients (`C_x`/
`C_z`/`C_m`/`C_mq`/the CoP arm `l1`) instead of (or in addition to) the
```
with
```
identical dispatch dict, `_AERO_COEFF_CONTROLLERS`/`aero_coeff_delta`, lets
a future controller perturb the airframe's own aero coefficients (`C_x`/
`C_z`/`C_m_code`/`C_mq_code`/the CoP arm `l1`) instead of (or in addition to) the
```

and replace the worked example:
```
- Write `_my_law(t, y, p, flow, base) -> AeroCoeffs`, returning
  `base._replace(C_x=base.C_x + dC_x, C_m=..., l1=...)` -- `NamedTuple.
```
with
```
- Write `_my_law(t, y, p, flow, base) -> AeroCoeffs`, returning
  `base._replace(C_x=base.C_x + dC_x, C_m_code=..., l1=...)` -- `NamedTuple.
```

### `sim/report.py` — six `aero.C_m(...)` call sites + docstring formulas

`static_margin_cal` (lines 100-103), replace:
```python
            dcm = (
                aero.C_m(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
                - aero.C_m(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
            ) / (2.0 * _CM_SLOPE_STEP)
```
with
```python
            dcm = (
                aero.C_m_code(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
                - aero.C_m_code(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
            ) / (2.0 * _CM_SLOPE_STEP)
```

`cm_slope_series` (lines 143-144), replace:
```python
        hi = aero.C_m(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
        lo = aero.C_m(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
```
with
```python
        hi = aero.C_m_code(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
        lo = aero.C_m_code(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
```

`combined_stability_slope_series` (lines 165-166), replace:
```python
        dcm = (
            aero.C_m(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
            - aero.C_m(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
        ) / (2.0 * _CM_SLOPE_STEP)
```
with
```python
        dcm = (
            aero.C_m_code(flow.alpha + _CM_SLOPE_STEP, flow.M, p, fb)
            - aero.C_m_code(flow.alpha - _CM_SLOPE_STEP, flow.M, p, fb)
        ) / (2.0 * _CM_SLOPE_STEP)
```

**Docstring formula mentions — renamed, since they literally describe the calls directly below/above
them:** line 82 (`margin(t) = l1(t)/d_ref - (dC_m/dalpha)/(dC_z/dalpha)`) → `dC_m_code/dalpha`; line 150
(`` `(t, d/dalpha[(l_g - l_p)*C_z - d_ref*C_m])` ``) → `d_ref*C_m_code`; line 195's warning-message text
(`` f"{max_combined:.4g} > 0 (d/dalpha[(l_g-l_p)*C_z - d_ref*C_m] in the code convention, " ``) →
`d_ref*C_m_code`.

**Lines 136, 152-153 STAY unchanged** — generic/conceptual prose, not mirroring a specific renamed call:
`` """`(t, dC_m/dalpha)` in the code's convention... """ `` (line 136, `cm_slope_series`'s own one-line
summary, already says "in the code's convention" so the ambiguity this ticket fixes doesn't bite here);
`` NEGATIVE = restoring (stable) in the code's C_m convention `` and `` (that is `dC_m/dalpha` alone, a
different quantity) `` (lines 152-153, same "already says it's the code convention" reasoning). Leaving
these as `C_m`/`dC_m` is a judgment call, not a mechanical necessity — flagged here so the developer does
not second-guess it mid-ticket; if in doubt, renaming these too is harmless (no pin impact either way,
pure prose) but not required for this ticket's acceptance.

## §117.8 `sim/params.py` — one-line `l_p` docstring fix (bundled, unrelated to the `C_m` rename)

**Confirmed via `git show 62733b1 --stat`: `sim/params.py` is absent from Step 116's file list** — Step
116 fixed the "CP station" wording in `sim/aero.py`, `configs/rockets/_TEMPLATE_rocket.py`, and
`data/aero/example_v2.csv`, but never touched this file's own copy of the same field's docstring, which
on this branch still reads (lines 105-106):

```python
    # Step 99 (D-111): CP station from the nose [m] for the constant/linearized models
    # (arm = l_p - CoG(t)); 0.0 = off, Lengths.l1 is the arm. A table carries its own l_p_m column.
    l_p: float = 0.0
```

Replace the comment (line 105 only, line 106 unchanged) with:

```python
    # Step 99 (D-111): moment reference station from the nose [m] (x_ref) for the
    # constant/linearized models
    # (arm = l_p - CoG(t)); 0.0 = off, Lengths.l1 is the arm. A table carries its own l_p_m column.
    l_p: float = 0.0
```

Do not touch anything else in `sim/params.py` — `Aero.C_m`/`C_m_alpha`/`c_mq`/`cm_convention` stay
exactly as they are (§117.2); this is the one-line doc fix point 6 of the brief asked for, not a reopen
of Step 116.

## §117.9 Tests — exact file-by-file impact

**Scope correction vs. the audit's estimate:** the audit's §1.1 table cites "34 files / 264 lines" for
`C_m` and "12 files / 135 lines" for `c_mq`/`C_mq` as the cost of **option (b)** (the full sign switch,
which touches every config/table/test reference to the symbol). Option (c) (this ticket) touches a much
smaller slice, because the config-field and CSV-header layer is explicitly excluded (§117.2). Verified
directly (`rg`/`Grep` over `tests/`, `configs/`, `apps/`, `data/`): of the 21 test files the audit's
estimate implies, only **8** actually call a renamed symbol.

| File | Lines (old → confirm renamed) | Action |
|---|---|---|
| `tests/test_aero.py` | 76 (`aero.C_m(...)`), 245 (`aero.C_m(...)`), 366/387/421/431/435 (`aero.C_mq(...)`), 384 (`table.C_mq is None`), 507-508 (`c.C_m`/`c.C_mq` and `aero.C_m(...)`/`aero.C_mq(...)`), 571 (`aero.AeroCoeffs(C_x=.., C_z=.., C_m=0.3, C_mq=0.4, l1=..)`) | Rename every listed call/attribute/kwarg to the `_code` form. Lines 164 (`p.aero.C_m_alpha`) and 435's `p.aero.c_mq` reference are config-field reads — **stay** |
| `tests/test_aero_v2.py` | 101-102 (`t_default.C_m`/`t_code.C_m`/`t_std.C_m`, table objects), 142 (`c.C_m`), 189/225 (`aero.C_m(...)`), 203/211/218 (`aero.C_mq(...)`), 281 (`t_new.C_m`/`t_old.C_m`) | Rename every listed occurrence. Lines 185, 200, 216, 223 (`Aero(model="constant", ..., C_m=0.2, c_mq=-5.0)`, config construction) **stay** |
| `tests/test_aero_oob.py` | 105 (`c.C_m`), 230 (`table.C_m`), 235 (`aero._table_coeffs(a, M, pj).C_m`), 291 (`c.C_m`, `t.C_m`) | Rename all four |
| `tests/test_aero_fb.py` | 99 (`for field in ("C_x", "C_z", "C_m", "l1"):` iterating `AeroCoeffs` fields via `getattr`) | Replace `"C_m"` with `"C_m_code"` in the tuple literal — the loop body (`getattr(ch, field)`) needs no change, it already reads whatever string is in the tuple |
| `tests/test_control.py` | 285-286 (`base._replace(..., C_m=base.C_m + dC_m, C_mq=base.C_mq + dC_mq, ...)`) | Rename both kwargs and both attribute reads. Line 256 (`Aero(model="constant", ..., C_m=0.1, c_mq=2.0)`, config construction) **stays** |
| `tests/test_qa_phase217_m1.py` | 76-77 (`c.C_x, c.C_z, c.C_m`twice), 104 (`aero._load_table(name).C_m[0, 0]`) | Rename all |
| `tests/test_report.py` | 69 (`aero.C_m(...)` ×2, cross-check snippet from Step 116's own ticket §116.7) | Rename both calls |
| `tests/test_step114_review_fixes.py` | 69 (`t.C_mq`), 84 (`aero._load_table(name).C_mq`), 123 (`aero._AeroTable(..., C_N=.., C_m=np.zeros((1,2)), l1=None, C_mq=None, l_p=..)`) | Rename all three |

**Explicitly verified to need zero changes** (every match is a `Params.aero.C_m`/`C_m_alpha`/`c_mq`
config-field construction or read, or a CSV-header string literal/prose comment — confirmed by direct
read of each, not assumed from the audit's file list): `tests/test_sampling.py`, `tests/test_dynamics3d.py`,
`tests/test_forces.py`, `tests/test_motor_selection.py`, `tests/test_dynamics.py`, `tests/test_plotting.py`,
`tests/test_configs.py`, `tests/test_analytic.py`, `tests/config_variants.py`, `tests/test_actuator.py`,
`tests/test_mach_warning.py`, `tests/test_wind.py`, `tests/test_flow.py`, `tests/test_atmosphere.py`,
`tests/test_scenario_sweep.py`, `tests/test_integrate.py`. Also verified zero changes needed:
`configs/schema.py`, `configs/rockets/_TEMPLATE_rocket.py`, `configs/rockets/demo.py`, `run.py`,
`apps/motor_selection/motors.py`, `apps/motor_selection/scenario_sweep.py`,
`apps/weight_aero_tradeoff/trade_surface.py`, `apps/common/study_vehicle.py`, `data/aero/example.csv`,
`data/aero/example_v2.csv`.

Run the point-in-time test files first:

```
python -m pytest tests/test_aero.py tests/test_aero_v2.py tests/test_aero_oob.py tests/test_aero_fb.py \
  tests/test_control.py tests/test_qa_phase217_m1.py tests/test_report.py tests/test_step114_review_fixes.py -q
```

then the full suite in the background per `CLAUDE.md`'s convention. Expected: **705/705**, unchanged
count, zero pin movement (every renamed assertion reads the exact same float it did before — only the
accessor name changed).

## §117.10 Acceptance checks (zero-remaining-matches)

After all edits, run (ripgrep, matching this project's established search tooling):

```
rg -n "\bC_m\b" sim/aero.py sim/forces.py sim/control.py sim/report.py
rg -n "\bC_mq\b" sim/aero.py sim/forces.py sim/control.py sim/report.py
```

Every remaining hit in these two outputs must be one of the lines explicitly marked **STAYS** in
§117.6/§117.7 above (the `_cm_to_code` parameter and its docstring; the module's own CSV-format
documentation line 49; lines 68/75/116-117/244's I/O-boundary prose; `sim/forces.py` lines 264/275;
`sim/report.py` lines 136/152-153). Any hit *not* on that list is a missed rename — fix before handing to
QA.

```
rg -n "\.C_m\b|\.C_mq\b|AeroCoeffs\(.*C_m=|AeroCoeffs\(.*C_mq=|_AeroTable\(.*C_m=|_AeroTable\(.*C_mq=" tests/
```

Should return **zero** hits after the rename (every one of these shapes should now read `C_m_code`/
`C_mq_code`); any surviving hit is a missed test-file rename.

```
rg -n "\bC_m\b|\bC_mq\b" data/aero/ configs/ apps/ run.py
```

Should be **unchanged** from before this ticket (these are all legitimate `C_m`/`c_mq` I/O-boundary
references, §117.2 — this check exists to catch an *accidental* rename in these files, not to find
missing ones).

## §117.11 Open questions / deliberately deferred

- **LaTeX honesty gap, not closed here.** The audit's own cost table for option (c) says "paper edit
  still needed" — `dev/docs/latex/sections-ai/rocket-2d.tex`'s `eq:aero_magnitudes` and
  `analysis.tex`'s static-margin/`C_m,alpha` discussion still use the plain symbol `C_m` for what, after
  this step, the code calls `C_m_code` internally (the paper was never asked to track an internal
  rename — it describes the physics, not Python identifiers, so there is no automatic mismatch, but the
  paper's own prose equating "positive `C_m`" with "nose-down" is the same inverted-convention
  description the code now flags more loudly with its own internal rename). Per the orchestrator's
  explicit correction: the user's "yes" to option (c) was never asked to cover a LaTeX edit, so **zero
  LaTeX edits happen in this step** — this is a known, deliberately out-of-scope gap, not a decision made
  here. Surface it back to the user only if/when a LaTeX edit is separately proposed.
- **`_cm_to_code`'s own parameter name (`C_m`, even when fed a `c_mq` value)** — pre-existing, not part of
  the harm the audit names (a private helper, not a public symbol), not fixed here (§117.1/§117.6). Could
  be renamed to something convention-neutral (e.g. `value`) in a future tidy-up step; flagging, not
  deciding.
- **`_table_coeffs`'s scalar `c_mq` fallback** (`sim/aero.py` ~line 667, `C_mq_code = p.aero.c_mq` when a
  table lacks a `c_mq` column) is untouched — Step 119/B36, a separate, already-queued finding (§1.3 of
  the audit) about whether that fallback should itself be flipped under `cm_convention="standard"`; this
  ticket's rename does not resolve or prejudge that question, it just carries the new name through the
  existing (unexamined) fallback logic unchanged.
- **Backlog B34** (Step 116's `l_p == 0.0` double-duty limitation) is unrelated to this ticket and not
  re-litigated here; mentioned only because §117.8 touches the same field's neighboring docstring line.

## §117.12 Definition of done

- [ ] `sim/aero.py`: `_AeroTable.C_m`/`C_mq` → `C_m_code`/`C_mq_code`; `AeroCoeffs.C_m`/`C_mq` →
      `C_m_code`/`C_mq_code`; `C_m()`/`C_mq()` functions → `C_m_code()`/`C_mq_code()`; every call site
      inside the file (`_load_table`, `_at_fb`, `_constant_coeffs`, `_linearized_coeffs`,
      `_table_coeffs`, `_jorgensen_extend`) updated per §117.6; all listed docstring/comment spots
      updated; all listed "STAYS" spots verified untouched.
- [ ] `sim/forces.py::aero_moment_y`: `c.C_m`/`c.C_mq` → `c.C_m_code`/`c.C_mq_code`; docstring line 257
      updated; lines 264/275 verified untouched.
- [ ] `sim/control.py`: docstring lines 18 and 28 updated.
- [ ] `sim/report.py`: all six `aero.C_m(...)` calls → `aero.C_m_code(...)`; docstring formula mentions
      at lines 82/150/195 updated; lines 136/152-153 verified untouched (judgment call, §117.7).
- [ ] `sim/params.py`: line 105's `l_p` comment reworded per §117.8; nothing else in this file touched.
- [ ] All 8 test files in §117.9's table updated; all 16 "zero changes needed" test files verified
      untouched (`git diff --stat` shows no hunks in them).
- [ ] Zero edits in `configs/`, `apps/`, `data/`, `dev/docs/latex/`.
- [ ] §117.10's four `rg` acceptance checks run and their results match the stated expectations.
- [ ] Point-in-time test files green (§117.9's `pytest` invocation), then full suite green in background
      — **705/705**, confirm zero pin movement (every changed assertion line reads the same float value
      as before, only via a renamed accessor).
- [ ] `code-review` skill run before handing to QA (project convention, feature branch
      `feature/sim-paper-alignment`).

### [STEP-117] Rename internal always-code-sign `C_m`/`C_mq` to `C_m_code`/`C_mq_code` (D-126, option c)
- **Module/boundaries:** `sim/aero.py`, `sim/forces.py`, `sim/control.py`, `sim/report.py`,
  `sim/params.py` (one line only, §117.8), `tests/test_aero.py`, `tests/test_aero_v2.py`,
  `tests/test_aero_oob.py`, `tests/test_aero_fb.py`, `tests/test_control.py`,
  `tests/test_qa_phase217_m1.py`, `tests/test_report.py`, `tests/test_step114_review_fixes.py`.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (touches `sim/aero.py`/`sim/forces.py`/`sim/report.py`, the same shared
  modules Step 116 and any other in-flight work on this branch also touch — sequence it, do not run
  alongside another ticket editing these files)

Implement per §117.1-§117.9 above; run §117.10's acceptance checks; tick off §117.12 before handing to
QA.
