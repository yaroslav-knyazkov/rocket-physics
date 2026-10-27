# Step 119 (D-128) — B36 fix: `_table_coeffs`'s scalar `c_mq` fallback must respect a sign convention

## Кратко (RU)

D-128 принял «B36 чинить сейчас» в общем виде. Факт-чек показал: это **не механическая
однострочная правка**, а развилка. У таблицы (`.csv`) есть **своя** декларация `cm_convention`
в заголовке файла — она используется только для разворота колонок `C_m`/`c_mq` при загрузке и
затем **отбрасывается**, не хранится в `_AeroTable`. У `Params.aero.cm_convention` — **отдельное**
поле уровня `Params`, по документации (`sim/params.py`, комментарий к самому полю) относящееся
**только к constant/linearized моделям**. Сегодня скалярный fallback `c_mq` для `"table"`-модели
(когда в файле нет колонки `c_mq`) читает `p.aero.c_mq` сырым, без единого разворота — баг.

Два содержательных варианта фикса:
- **Вариант A** — fallback разворачивается по `Params.aero.cm_convention` (как уже сделано в Step
  115 для constant/linearized). Тривиально, бит-в-бит для ВСЕХ текущих конфигов и тестов (включая
  единственный живой кейс `test_example_v2_flies_stable`) — проверено прогоном, числа идентичны
  байт-в-байт. Но концептуально слабее: поле `cm_convention` документировано как относящееся
  только к constant/linearized, так что применение его к table-модели — это НОВОЕ, не описанное
  ранее использование поля.
- **Вариант B** — fallback разворачивается по конвенции, **заявленной самой таблицей** (её `#
  cm_convention:` в заголовке файла), требует протащить это значение в `_AeroTable` новым полем
  (table-level, не Params-level). Архитектурно точнее (таблица уже документирована как
  self-describing источник конвенции; `Params.aero.cm_convention`'s собственный докстринг явно
  говорит «of the constant/linearized coefficients», НЕ table). Численно посчитано (не оценка):
  на реальном прогоне `test_example_v2_flies_stable` разница мала и тест **продолжает проходить**
  с комфортным запасом (отношение `0.6666 → 0.6632`, порог теста `< 0.8`) — ни коллапса, ни
  разворота маржи вопреки опасению в постановке задачи.

**Рекомендация: вариант B.** Он единственный, который реально закрывает B36 (делает скаляр
эквивалентным отсутствующей колонке таблицы — ровно то, зачем fallback существует), не ломает ни
одного теста (проверено прогоном, не прогнозом) и не придаёт полю `cm_convention` нового,
недокументированного кросс-модельного смысла. Стоимость — на одно NamedTuple-поле и несколько
строк больше, чем вариант A, но без скоуп-крипа (поле только для этого одного use-case).

**Пин-риск: подтверждён нулевым для всего остального репозитория** (только два `.csv`-файла в
`data/aero/`, только один живой ненулевой `c_mq` + table + "standard"-таблица кейс во всей тестовой
суите — `test_example_v2_flies_stable`; остальные вызовы с `example_v2.csv` используют `c_mq=0.0`
(default) и не затрагиваются ни одним вариантом). Единственный тест, у которого числа РЕАЛЬНО
сдвигаются под вариантом B — `test_example_v2_flies_stable`, и сдвиг крошечный (пятый знак после
запятой), тест остаётся зелёным без правки. Нужен ли отдельный "да" пользователя на этот сдвиг —
решает оркестратор; моя честная оценка (см. ответ в чате) — это уже входит в объём того, что D-128
одобрил абстрактно ("B36 чинить сейчас... с пин-риском"), и численный результат ещё и благоприятен
(тест не трогается). Но это сам по себе реальный архитектурный развилок (table-level vs
Params-level convention), не мной подписанный молча — см. §119.1 и финальный ответ в чат.

---

## Table of contents

- §119.1 The fork — table-level vs Params-level convention for the scalar fallback (decision point)
- §119.2 Design recommendation and rationale
- §119.3 Actual computed numbers — `test_example_v2_flies_stable` before/after (all three variants)
- §119.4 Other live cases checked (none found beyond the one test)
- §119.5 `sim/aero.py` — exact before/after
- §119.6 `tests/test_aero_v2.py` — new coverage
- §119.7 Pin impact — **read before implementing**
- §119.8 Test-impact table
- §119.9 Definition of done

---

## §119.1 The fork — table-level vs Params-level convention for the scalar fallback

**This is a genuine design fork, not a mechanical one-liner.** Confirmed by reading the code, not
assumed from the ticket prompt:

- `sim/aero.py::_load_table` (lines 220-253) parses a table file's own `# cm_convention: <code|
  standard>` header line into a **local variable** `cm_convention`, used only to flip `C_m_col`
  (line 278-279) and `C_mq_col` (lines 297-300) **at load time**. It is never stored on the returned
  `_AeroTable` (confirmed: `_AeroTable`'s field list, lines 197-209, has no `cm_convention` field).
- `sim/params.py`'s `Aero.cm_convention` field (line 112) is a **separate** `Params`-level field,
  default `"code"`. Its own docstring (line 109-111): *"C_m sign convention of the constant/
  linearized coefficients: ... A table declares its own via a `# cm_convention:` header line."* —
  i.e. by this field's own documentation, it is explicitly scoped to the **constant/linearized**
  models; a table is documented as self-describing via its own header, a *different* mechanism.
- `Aero.c_mq`'s field comment (lines 99-104), written at Step 115, says the scalar "IS flipped by
  `cm_convention="standard"` for the constant/linearized models ... matching the table's `c_mq`
  column, which was already flipped there since Step 114" — this is true only for the two scalar
  models; it says nothing about what convention governs `_table_coeffs`'s *own* scalar fallback,
  which is the one path Step 115 explicitly left alone (backlog B36).

So there are two conventions in play that have no defined relationship today, and the scalar
`c_mq` fallback in `_table_coeffs` sits at their intersection:

| | Governs | Scope per its own docs |
|---|---|---|
| `Params.aero.cm_convention` | `_constant_coeffs`/`_linearized_coeffs`'s scalar `C_m`/`c_mq` | "of the constant/linearized coefficients" (`sim/params.py` line 109) |
| a table's own `# cm_convention:` header | that table's own `C_m`/`c_mq` *columns*, at load time | self-describing, table-local |
| `_table_coeffs`'s scalar `c_mq` fallback (used when the table has no `c_mq` column) | **undefined today — this ticket's subject** | — |

### Option A — fallback reads `Params.aero.cm_convention`

```python
C_mq_code = _cm_to_code(p.aero.c_mq, p)   # same helper _constant_coeffs/_linearized_coeffs use
```

- **Pros:** one line, reuses the existing `_cm_to_code` helper verbatim, perfectly symmetric with
  the already-fixed constant/linearized paths, zero new state.
- **Cons:** does not actually make the fallback "stand in for a missing column" in the sense B36
  describes — a user relying on a `"standard"`-declaring table and leaving `Params.aero.cm_convention`
  at its default (`"code"`, the normal way to use a self-describing table per the field's own
  docstring) gets **no flip at all**, i.e. the bug is unchanged in the one realistic usage pattern
  (never set `Params.aero.cm_convention` when using a table). It also stretches the field's own
  documented scope ("of the constant/linearized coefficients") to a third model it explicitly does
  not claim to cover.
- **Pin impact:** zero. No test or config in the repo sets `Params.aero.cm_convention` on a `"table"`
  model Params (confirmed by grep across `tests/`, `configs/`, `apps/` — `cm_convention` only
  appears paired with `model="constant"`/`model="linearized"` or not at all). Computed and confirmed
  (§119.3): bit-identical before/after for `test_example_v2_flies_stable`.
- **Cost:** trivial (1 line in `_table_coeffs`, 1 doc line, no new field).

### Option B — fallback reads the table's own declared convention (recommended)

Requires threading the table's own parsed convention through a new `_AeroTable` field (its only job:
carry this one value for this one fallback — no broader refactor of `_load_table`).

```python
class _AeroTable(NamedTuple):
    ...
    C_mq_code: "np.ndarray | None"
    l_p: "np.ndarray | None" = None
    f_b: "np.ndarray | None" = None
    planes: "tuple | None" = None
    cm_convention: str = "code"   # NEW: this table's own declared convention (Step 119/B36),
                                  # used only by _table_coeffs's scalar c_mq fallback when the
                                  # table has no c_mq column of its own.
```

```python
# _table_coeffs, the fallback branch:
if table.C_mq_code is not None:
    C_mq_code = _table_lookup(table, alpha, M, table.C_mq_code)
elif table.cm_convention == "standard":
    C_mq_code = -p.aero.c_mq
else:
    C_mq_code = p.aero.c_mq
```

- **Pros:** makes the scalar fallback behave exactly like a `c_mq` *column* in the same file would
  have behaved under the same header declaration — the one thing B36 is actually asking for ("the
  scalar fallback should respect the SAME convention the table itself declares, since it stands in
  for a missing table column"). Consistent with `Params.aero.cm_convention`'s own documented scope
  (table conventions live in the table header, not in `Params`). Does not change the meaning of any
  existing field.
- **Cons:** one new `_AeroTable` field (small, but real, API-surface growth); `_at_fb`'s `_replace(...)`
  blend helper (line 400-403) does not need to touch it (a string field blends trivially — both
  bracketing planes of the same loaded table always carry the same `cm_convention`, since it is a
  per-file, not per-plane, property; confirmed `_plane()` builds every plane from the same parsed
  `cm_convention` local variable, so `lo.cm_convention == hi.cm_convention` always — `_replace` leaves
  it at `lo`'s value unchanged, which is correct).
- **Pin impact:** computed, not estimated (§119.3) — one test's numbers move by ~0.5% (fifth decimal
  digit), well inside its existing `< 0.8 *` margin (new ratio 0.6632 vs. threshold 0.8, old was
  0.6666). No other test is numerically affected (§119.4 — only `c_mq != 0.0` combined with a
  `"table"` model and a missing `c_mq` column is live anywhere in the repo, and that is exactly this
  one test).
- **Cost:** small (new field + 2 lines in `_table_coeffs` + the field needs to be set at both
  `_plane()` construction sites... actually one, see §119.5 — `_load_table` has one `_plane()`
  helper reused for every plane).

### Option C — require the user to declare both and validate they match (rejected)

Add a fail-fast check: if `model == "table"`, the table lacks a `c_mq` column, `p.aero.c_mq != 0.0`,
and `p.aero.cm_convention` was left at its default while the table declares `"standard"` (or any
mismatch between the two) — raise `ValueError`.

- **Pros:** closes the exact silent-trap pattern the audit (§1.3) warns about in general, forces
  explicitness.
- **Cons:** materially larger change (new validation branch in `aero.validate`, not just a sign
  flip); **breaks the live test** (`_short_flight_alpha` sets `c_mq=0.5` against a `"standard"`-
  declaring table without ever setting `Params.aero.cm_convention`) — would require editing the test
  to explicitly set `cm_convention="standard"` on top of fixing the fallback itself, which is a much
  bigger surface than "B36 chinit' sejchas" was framed as. Also: this validation has nothing to
  enforce if Option B is taken (there would no longer be a second, independent convention to drift
  from — the fallback reads the table's own declaration directly, so there is nothing to validate).
- **Verdict:** not recommended as the primary fix; worth a one-line mention as a follow-on hardening
  idea only if Option A is chosen instead of B (under Option A, the mismatch Option C warns about
  still exists structurally). Not implemented here — out of this ticket's scope either way.

### Recommendation

**Option B.** It is the only option that actually fixes what B36 describes (observed as: a user
supplying a scalar `c_mq` alongside a `"standard"`-declaring table, with no `c_mq` column, gets a
value with the wrong sign relative to their declared convention) rather than leaving that exact
scenario a silent no-op fix. Its pin impact is fully computed, not assumed, and is favorable: the one
live test keeps a comfortable margin. Option A is defensible as "simpler, zero behavior change" but
does not close the trap in the one realistic usage pattern (self-describing table, `Params`-level
field left at default) — i.e. it is a fix only on paper, not in the one scenario that was reported as
already live.

**Orchestrator note:** I flag this plainly as a design fork the ticket prompt was right to suspect —
options A and B produce different runtime numbers for a real, already-passing test, and reasonable
engineers could pick either (A is "minimal, symmetric with Step 115"; B is "actually fixes the
reported trap"). Both are pin-safe (B's shift is tiny and stays inside the test's margin), so this is
not a blocking approval gate the way a pin-breaking change would be, but it is a real design decision
about what `cm_convention` means for the table model going forward, worth a conscious "yes" rather
than a silent pick — see my chat reply.

---

## §119.2 Design recommendation and rationale (summary)

Implement **Option B**: thread the table's own declared convention through a new `_AeroTable.
cm_convention` field (default `"code"`, matching `_load_table`'s existing local-variable default),
set once per loaded table (every plane shares the same value — confirmed, see §119.1), and consulted
only by `_table_coeffs`'s scalar fallback branch. No other call site reads it. No change to
`_load_table`'s existing column-flip logic (`C_m_col`/`C_mq_col`, lines 278-279/297-300) — that logic
already produces the right `C_mq_code` array when a column IS present; this ticket only touches the
"no column at all" branch.

---

## §119.3 Actual computed numbers — `test_example_v2_flies_stable` before/after

Computed by direct execution (`python -c` repro against the real `sim/` package, real RK4 flight,
real `example_v2.csv`/its flipped-header copy) — not estimated. Repro mirrors `_short_flight_alpha`
exactly (same `Params`, same initial `State`, same `t=0.02 s` sample point at index 20, `dt=0.001`),
parameterizing `c_mq` to simulate each option's fallback value without touching `sim/aero.py`:

| | `a_stable` (example_v2.csv, declares "standard") | `a_flipped` (header replaced with "code") | ratio `a_stable/a_flipped` | test assertion `a_stable < 0.8*a_flipped` |
|---|---|---|---|---|
| **Baseline (today, bug)** | 0.008803 | 0.013206 | 0.6666 | **PASS** (0.008803 < 0.010565) |
| **Option A** (`Params.aero.cm_convention`, default `"code"`, never set by the test) | 0.008803 | 0.013206 | 0.6666 | **PASS**, bit-identical to baseline |
| **Option B** (table's own declared convention; `c_mq` effectively `-0.5` for the "standard" table, `+0.5` unchanged for the "code" copy) | 0.008758 | 0.013206 | 0.6632 | **PASS**, margin essentially unchanged |

**Reading:** Option A is a pure no-op for this test (confirmed bit-for-bit, not just argued) because
the test never sets `Params.aero.cm_convention` away from its default. Option B does change
`a_stable` (the only place `c_mq`'s sign differs from baseline), but the magnitude is small — at
`t=0.02 s` the body's angular rate `omega` has barely developed from its zero initial condition, so
the pitch-damping term's own contribution (which is what `c_mq` scales) is still minor relative to
the restoring-moment (`C_m`) term driving `alpha` back down. The ratio moves from `0.6666` to
`0.6632` against a `0.8` pass threshold — no collapse, no sign flip, comfortable margin preserved.
**No test edit is needed under either option.**

Repro script (for the record, not committed — paste-and-run against the working tree if the number
needs re-verifying before/after the real edit):

```python
import math, os
import numpy as np
from sim import aero
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Aero, Lengths, Params, Solver, Weight
from sim.state import State

def short_flight_alpha(table, c_mq, cm_convention="code"):
    p = Params(
        weight=Weight(m=0.5, I=0.05), lengths=Lengths(l2=0.4, l_g=0.9),
        aero=Aero(model="table", S=0.02, d_ref=0.08, table=table, c_mq=c_mq,
                   cm_convention=cm_convention),
        solver=Solver(method="rk4", dt=0.001, t_max=0.1),
    )
    aero.validate(p)
    r = run_sim(p, State(x=0.0, z=0.0, vx=3.0, vz=-150.0, theta=math.pi/2 - 0.1, omega=0.0))
    assert np.max(np.abs(r.y[5])) < 8.0
    return abs(flow_state(0.0, r.y[:, 20], p).alpha)

# baseline / Option A: c_mq=0.5 for both tables (fallback never flips today; Option A
# would read Params.aero.cm_convention, left at default "code" -> same raw value)
# Option B: c_mq=-0.5 for the "standard" table only, simulating the table-convention flip
```

After the real `sim/aero.py` edit lands (Option B), re-run
`python -m pytest tests/test_aero_v2.py::test_example_v2_flies_stable -q` directly (no simulation
needed at that point) to confirm the actual (not simulated) number matches `a_stable ≈ 0.008758`.

---

## §119.4 Other live cases checked (none found beyond the one test)

Checked every place `c_mq` appears alongside a `"table"` model across the whole repo (not just the
ticket prompt's suggested grep — re-verified independently):

| File / test | `c_mq` value | Table | Table's declared convention | Affected by A? | Affected by B? |
|---|---|---|---|---|---|
| `tests/test_aero_v2.py::_legacy_params` (→ `test_legacy_example_csv_*`) | `0.5` | `example.csv` | none declared → `"code"` default | No (no flip under "code") | No (no flip under "code") |
| `tests/test_aero_v2.py::_short_flight_alpha` (→ `test_example_v2_flies_stable`) | `0.5` | `example_v2.csv` (+ its "code"-relabelled copy) | `"standard"` (/ `"code"` for the copy) | No (Params-level field never set) | **Yes** — computed in §119.3 |
| `tests/test_aero_v2.py::_v2_example_params` | `0.5` | `example_v2.csv` | `"standard"` | — | — dead helper, **never called** anywhere in the file (confirmed by grep: `_v2_example_params()` has zero call sites) |
| `tests/test_report.py::_params` (3 call sites) | `0.0` (default, not set) | `example_v2.csv` | `"standard"` | No (`-0.0 == 0.0`) | No (`-0.0 == 0.0`) |
| `tests/test_aero_oob.py` (table="example_v2.csv") | not set → `0.0` | `example_v2.csv` | `"standard"` | No | No |
| `tests/test_scenario_sweep.py` (table="example_v2.csv") | not set → `0.0` | `example_v2.csv` | `"standard"` | No | No |
| `configs/`, `apps/` | no config sets `c_mq` with `model="table"` (only mentions are a template field comment and a docstring parameter list) | — | — | No | No |

`data/aero/` contains exactly two files (`example.csv`, `example_v2.csv` — confirmed by `Glob`).
`example.csv` declares no `cm_convention` (defaults `"code"`, confirmed by reading its header, lines
1-20 — no `# cm_convention:` line present) and has no `c_mq` column either, so its fallback is
exercised but inert under both options (no flip at "code"). **`test_example_v2_flies_stable` is the
only live, nonzero-sign-sensitive case in the repository.**

---

## §119.5 `sim/aero.py` — exact before/after

### `_AeroTable` (lines 197-209)

Before:
```python
class _AeroTable(NamedTuple):
    M: np.ndarray
    alpha: np.ndarray
    C_A: np.ndarray
    C_N: np.ndarray
    C_m_code: np.ndarray
    l1: "np.ndarray | None"
    C_mq_code: "np.ndarray | None"
    l_p: "np.ndarray | None" = None
    f_b: "np.ndarray | None" = None
    planes: "tuple | None" = None
```

After (one new field, documented, trailing so every positional/keyword construction site below stays
valid without edits except the one that sets it):
```python
class _AeroTable(NamedTuple):
    M: np.ndarray
    alpha: np.ndarray
    C_A: np.ndarray
    C_N: np.ndarray
    C_m_code: np.ndarray
    l1: "np.ndarray | None"
    C_mq_code: "np.ndarray | None"
    l_p: "np.ndarray | None" = None
    f_b: "np.ndarray | None" = None
    planes: "tuple | None" = None
    cm_convention: str = "code"  # Step 119 (D-128/B36): this table's own declared `# cm_convention:`
                                  # header value ("code" default, same as _load_table's own local
                                  # default). Used ONLY by _table_coeffs's scalar c_mq fallback, to
                                  # flip a user-supplied constant exactly as a c_mq *column* in this
                                  # same file would have been flipped. Every plane of a multi-f_b
                                  # table shares the same value (it is a per-file, not per-plane,
                                  # property) -- _at_fb's _replace() leaves it untouched, correctly.
```

### `_load_table`'s `_plane()` closure (lines 324-351)

Before (closing lines of `_plane`):
```python
        return _AeroTable(
            M=M_grid,
            alpha=alpha_grid,
            C_A=_reshape(C_A_col),
            C_N=_reshape(C_N_col),
            C_m_code=_reshape(C_m_col),
            l1=_reshape(l1_col) if l1_col is not None else None,
            C_mq_code=_reshape(C_mq_col) if C_mq_col is not None else None,
            l_p=_reshape(l_p_col) if l_p_col is not None else None,
        )
```

After:
```python
        return _AeroTable(
            M=M_grid,
            alpha=alpha_grid,
            C_A=_reshape(C_A_col),
            C_N=_reshape(C_N_col),
            C_m_code=_reshape(C_m_col),
            l1=_reshape(l1_col) if l1_col is not None else None,
            C_mq_code=_reshape(C_mq_col) if C_mq_col is not None else None,
            l_p=_reshape(l_p_col) if l_p_col is not None else None,
            cm_convention=cm_convention,  # Step 119/B36: the enclosing _load_table's already-
                                           # parsed, already-validated local variable (line 246) --
                                           # no new parsing, just carrying the existing value through.
        )
```

(`cm_convention` the local variable, parsed at lines 224-253, is already in scope inside `_plane` —
no new parameter needed.)

### `_table_coeffs` (lines 683-687)

Before:
```python
    table = _at_fb(_load_table(p.aero.table), fb)
    if table.C_mq_code is not None:
        C_mq_code = _table_lookup(table, alpha, M, table.C_mq_code)
    else:
        C_mq_code = p.aero.c_mq
```

After:
```python
    table = _at_fb(_load_table(p.aero.table), fb)
    if table.C_mq_code is not None:
        C_mq_code = _table_lookup(table, alpha, M, table.C_mq_code)
    elif table.cm_convention == "standard":
        # Step 119 (D-128/B36): the table has no c_mq column of its own -- the scalar fallback
        # must respect the SAME convention the table declares, exactly as a c_mq *column* in
        # this same file would have been flipped at load time (lines ~297-300 above). Mirrors
        # the textbook-C_mq<0 -> code-sign flip documented there.
        C_mq_code = -p.aero.c_mq
    else:
        C_mq_code = p.aero.c_mq
```

(`table.cm_convention` can only be `"code"` or `"standard"` — `_load_table` already fails fast on
any other value, lines 249-253, before an `_AeroTable` is ever constructed, so no third branch/`else`
error path is needed here.)

### `_table_coeffs`'s docstring (lines 655-664)

The existing paragraph is stale (predates this fix, never mentions `cm_convention` at all) —
update it alongside the code change:

Before (relevant sentence only):
```
    `C_mq_code` (Step 44, architecture.md SS24.4): table-driven only when the
    table has a `c_mq` column, otherwise the constant `p.aero.c_mq` --
    SIGN: positive c_mq is DAMPING in this document's convention (positive
    `C_m_code` is a nose-down moment here), the opposite of the textbook
    `C_mq < 0`, the same flip `C_m_alpha` already carries.
```

After (append, do not remove the existing sentence -- it is still true for the table-column case):
```
    `C_mq_code` (Step 44, architecture.md SS24.4): table-driven only when the
    table has a `c_mq` column, otherwise the constant `p.aero.c_mq` --
    SIGN: positive c_mq is DAMPING in this document's convention (positive
    `C_m_code` is a nose-down moment here), the opposite of the textbook
    `C_mq < 0`, the same flip `C_m_alpha` already carries.

    Step 119 (D-128/B36): when the column is absent, the fallback scalar is flipped by the
    TABLE's own declared `cm_convention` (not `Params.aero.cm_convention`, which this field's own
    docstring scopes to the constant/linearized models only) -- the fallback stands in for a
    missing column, so it is interpreted exactly as a column would have been.
```

---

## §119.6 `tests/test_aero_v2.py` — new coverage

Add one focused unit test exercising the fallback directly (fast, no RK4 flight needed), analogous
in spirit to `test_cm_convention_standard_flips_exactly_and_default_is_code` already in this file:

```python
def test_table_cm_convention_flips_scalar_c_mq_fallback():
    """Step 119 (D-128/B36): a table with no c_mq column of its own must flip the scalar
    Aero.c_mq fallback by the TABLE's own declared cm_convention -- not by
    Params.aero.cm_convention (that field's docstring scopes it to constant/linearized only)."""
    with _table("test_v2_fallback_std.csv", _v2_text(header="# cm_convention: standard\n")) as n_std, \
         _table("test_v2_fallback_code.csv", _v2_text(header="# cm_convention: code\n")) as n_code, \
         _table("test_v2_fallback_default.csv", _v2_text()) as n_default:
        p_std = _mass_params(n_std, aero=Aero(model="table", S=0.01, d_ref=0.1, table=n_std, c_mq=5.0))
        p_code = _mass_params(n_code, aero=Aero(model="table", S=0.01, d_ref=0.1, table=n_code, c_mq=5.0))
        p_default = _mass_params(n_default, aero=Aero(model="table", S=0.01, d_ref=0.1, table=n_default, c_mq=5.0))
        y = _y(1.8)
        flow = flow_state(0.0, y, p_std)
        assert aero.coefficients(0.0, y, p_std, flow).C_mq_code == -5.0     # standard -> flipped
        assert aero.coefficients(0.0, y, p_code, flow).C_mq_code == 5.0    # code -> unflipped
        assert aero.coefficients(0.0, y, p_default, flow).C_mq_code == 5.0  # no header -> default "code"
```

(Fixture note: `_mass_params`'s signature in this file is `_mass_params(table, **kw)` building its
own `Params(...)`-- the exact call shape above needs adjusting to that helper's real keyword surface
when implemented; verify against the live helper at implementation time, do not copy-paste blind.)

No change needed to `test_example_v2_flies_stable` itself (§119.3 — passes unchanged, comfortable
margin).

---

## §119.7 Pin impact — needs orchestrator/user sign-off before implementation

**Read this section before writing any code.**

- **D-128 already approved "fix B36 now, despite the pin risk, explicitly accepted."** This ticket's
  own numeric work (§119.3) found the actual pin risk is **smaller than the abstract approval
  anticipated**: the one live test's margin barely moves (`0.6666 → 0.6632` against an `0.8`
  threshold) and needs **no test edit**.
- **What IS new relative to the abstract D-128 approval:** the *design fork* itself (§119.1, Option A
  vs. B) was not part of what the user was shown when giving D-128 — D-128 approved "fix the bug",
  not "which of two different, both-pin-safe interpretations of 'the fix' to take." Recommending
  Option B is an architectural choice (new `_AeroTable` field, a second, table-scoped reading of
  "convention" alongside the existing `Params`-scoped one) that a different engineer could reasonably
  make differently (Option A). My assessment: this is minor enough (small, localized, pin-safe
  either way, numbers computed not guessed) that it does not need to go back to the user as its own
  gate — but the orchestrator should make that call, not me silently.
- **No LaTeX file is touched.** No config file needs updating. No other test needs updating.
- **Full suite target:** 705/705 unchanged pass count, zero new failures, zero skipped. (The repo's
  current full count was mid-run at ticket-writing time — confirm the exact baseline number from the
  orchestrator's own last full-suite run before treating "705" as gospel; this ticket adds exactly
  one new test, so the post-fix target is baseline + 1.)

---

## §119.8 Test-impact table

| Test | Before (current code) | After (Option B) | Needs edit? |
|---|---|---|---|
| `test_example_v2_flies_stable` | passes, ratio 0.6666 | passes, ratio 0.6632 | No |
| `test_legacy_example_csv_derivatives_bit_identical` | passes (c_mq=0.5, example.csv "code" default, no flip) | unchanged | No |
| `test_legacy_example_csv_flight_bit_identical` | passes (same reasoning) | unchanged | No |
| `test_static_margin_series_matches_cg_travel` / `test_stable_table_reports_no_warning` / `test_flipping_declared_convention_reports_instability` / `test_negative_geometric_margin_warns` (`test_report.py`) | passes (c_mq=0.0 default, fallback inert) | unchanged | No |
| `tests/test_aero_oob.py`, `tests/test_scenario_sweep.py` (example_v2.csv users) | passes (c_mq=0.0 default) | unchanged | No |
| NEW `test_table_cm_convention_flips_scalar_c_mq_fallback` | n/a | passes (new) | Added |
| Everything else in the suite | passes | unchanged (no code path touched outside `_table_coeffs`'s fallback branch and `_AeroTable`'s field list) | No |

---

## §119.9 Definition of done

- [ ] `_AeroTable` gets the new `cm_convention: str = "code"` field (§119.5), documented.
- [ ] `_load_table`'s `_plane()` passes its already-parsed `cm_convention` local variable through.
- [ ] `_table_coeffs`'s fallback branch flips by `table.cm_convention`, not `Params.aero.cm_convention`
      (§119.5) — exact code per this ticket, comment included.
- [ ] `_table_coeffs`'s docstring updated (append, do not delete the existing sentence).
- [ ] New unit test added (§119.6), passing.
- [ ] `test_example_v2_flies_stable` re-run directly (not simulated) post-edit; confirm
      `a_stable ≈ 0.008758` (fifth-decimal match is enough; this is a physics simulation, not a
      literal pin) and the test still passes.
- [ ] Full suite run (`python -m pytest -q`, background per CLAUDE.md), zero new failures, exactly
      one new passing test vs. the pre-ticket baseline count.
- [ ] No `sim/forces.py`, `sim/params.py`, LaTeX, or config file touched (confirm via `git diff
      --stat` before committing — this ticket's only code file is `sim/aero.py` plus the one test
      file).
- [ ] Commit message: `Step 119 (Phase 2.17): B36 fix -- table-model scalar c_mq fallback honors the table's own cm_convention (D-128)`.
