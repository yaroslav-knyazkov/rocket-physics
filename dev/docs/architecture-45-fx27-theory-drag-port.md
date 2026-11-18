## Кратко (RU)

- Документ описывает перенос 3 MATLAB-скриптов (`temporary/drive-download-20261117T190208Z-1-001/cd_mach_03_{same,decrease_D,increase_D}.m`), присланных пользователем, в проект — как ТЕОРЕТИЧЕСКИЙ (semi-empirical, Niskanen-thesis/OpenRocket method) источник таблиц C_D0(M) для конфигураций fx27 cspace.
- **Исправлено сопоставление файл→ракета** (пользователь подтвердил физический факт: PRO54_TRANSITION сужается 80мм→59мм): `cd_mach_03_same.m` → `PRO54_EQUAL_DM` (без изменений), `cd_mach_03_increase_D.m` → `PRO54_TRANSITION_DM` (ИСПРАВЛЕНО — геометрия файла: D1=80мм→D2=59мм переход + боат-тейл до 48.3мм, подтверждено пользователем), `cd_mach_03_decrease_D.m` → `PRO75_DM` (ИСПРАВЛЕНО методом исключения — **не подтверждено** пользователем напрямую, требуется отдельный вопрос прежде чем кто-то будет портировать эту геометрию).
- **Объём сокращён на этот этап: реализуется ТОЛЬКО `PRO54_TRANSITION_DM`** (пользователь: «implement it only for 1 configuration for now»). `PRO54_EQUAL_GEOMETRY`/`PRO75_GEOMETRY` как конкретные инстансы — отложены (тот же паттерн, добавляются позже по желанию пользователя); дизайн `Geometry`/`compute_cd0` остаётся общим (работает для любой геометрии), конкретно сейчас заполняется только одна.
- Размещение: новый модуль `projects/fx27/data/cspace/aero/drag_theory.py` (общая физика + геометрия текущего варианта, дублированные хелперы `ormach_blend/qr/cone` схлопнуты в одну копию) + новый отдельный генератор `generate_theory_drag_tables.py` (не `generate_dm_tables.py` — другая провенанс). Инвариант «one-off, не импортируется в runtime, вывод закоммичен» сохранён (как у `generate_dm_tables.py` и `regenerate_ideal_own.py`).
- **Шов M=0.7 — реальный, подтверждён самим MATLAB-скриптом** (его собственный `fprintf` печатает величину скачка между «paper»-методом и OpenRocket-методом на стыке). Решение: НЕ блендить — использовать формулу OpenRocket/Niskanen на всём диапазоне 0.1–1.3 (она уже там определена), «paper»-метод в финальную кривую не включать (в оригинале он был только сравнительной линией на графике). Шов M=1.3→1.3 (транс→сверхзвук) непрерывен по построению (обе ветви — одна и та же формула в этой точке) — проверяется юнит-тестом, не требует решения пользователя. (Эти два решения не затронуты правкой — подтверждены как есть.)
- **Главная развилка (decision_required + needs_approval, подтверждена как есть): перезаписывать существующий CSV или делать side-by-side.** Существующий `tests/test_fx27_port.py::test_dm_aero_table_matches_fx27_source_curve_at_sample_points` — жёсткий числовой пин на ТЕКУЩЕЕ (sibling-repo-ported) значение `pro54_transition_dm`, включая точку M=0.0, которой в новой теоретической кривой вообще нет (она начинается с M=0.1). Прямая перезапись сломает этот пин молча. Рекомендация: генерировать НОВЫЙ файл (`pro54-transition-drag-theory.csv`) и НОВЫЙ Rocket-вариант для сравнения, не трогая существующий `*_DM`/CSV/тест — продвижение (замена) — отдельное решение после того, как пользователь посмотрит на дельту.
- Тесты — новая физика, не реорг: `tests/test_fx27_drag_theory.py`, по конвенции TDD, сейчас — только для `PRO54_TRANSITION_GEOMETRY`. Покрытие: 3 хелпера `ormach_*` (алгебраические проверки, геометрия-независимы), непрерывность на M=1.3, физическая вменяемость (CD0>0, в разумных пределах), отчёт о дельте теория/старый CSV — всё для одного варианта.
- Тикеты для разработчика — секция §6 ниже, с точными путями файлов и сигнатурами функций.

---

## Table of contents

- §1 [Context and scope](#s1-context-and-scope)
- §2 [Source geometry mapping](#s2-source-geometry-mapping)
- §3 [Decision: file/function layout](#s3-decision-file-function-layout)
- §4 [Decision: Mach-regime seam handling](#s4-decision-mach-regime-seam-handling)
- §5 [Decision: CSV replacement strategy](#s5-decision-csv-replacement-strategy)
- §6 [Ticket list](#s6-ticket-list)
- §7 [Test coverage plan](#s7-test-coverage-plan)
- §8 [Rejected options](#s8-rejected-options)

---

## S1. Context and scope <a name="s1-context-and-scope"></a>

Three near-identical MATLAB scripts (`temporary/drive-download-20261117T190208Z-1-001/`) each compute a
zero-lift drag coefficient `C_D0(M)` for one of fx27's 3 cspace airframes, for a Haack-series nose +
body tube(s) + one transition/flare/boat-tail segment + 3 fins + 2 launch lugs. Each script stitches
three regimes:

- **subsonic, M 0.1-0.75**, step 0.01: a semi-empirical "paper" method (`CD_NBT + CDB + CD_F + CDLL`).
- **transonic, M 0.1-1.3**, step 0.01 (named `Mo`/`CD0_or` in the source — note this range ALREADY
  covers the "subsonic" range too, see §4): the Niskanen-thesis/OpenRocket method, cited inline by
  thesis equation number (`Eq. 3.77` etc.).
- **supersonic extension, M 1.3-3.0**, step 0.01 (`M_sup`/`CD0_sup`): the same method's supersonic
  branches, hand-extended by whoever wrote these scripts (comment: "ADDED BY CLAUDE").

The 3 files map onto the 3 existing fx27 `*_DM` rocket variants. **This mapping was corrected by the
user after the first draft of this doc** (the first draft carried forward the orchestrator's own
unverified guess, 2 of 3 rows wrong) — see the full correction and confidence level in §2:

| MATLAB file | fx27 rocket variant | rear-body geometry block | confidence |
|---|---|---|---|
| `cd_mach_03_same.m` | `PRO54_EQUAL_DM` | constant 8 cm tube (no transition) | confirmed (unambiguous) |
| `cd_mach_03_increase_D.m` | `PRO54_TRANSITION_DM` | transition 8 cm -> 5.9 cm + boat-tail 5.72 cm -> 4.83 cm | **confirmed by user** (real vehicle: 80mm->59mm) |
| `cd_mach_03_decrease_D.m` | `PRO75_DM` | diverging shoulder/flare, 8 cm -> 10.3 cm | **UNCONFIRMED** (by elimination only -- needs a direct question to the user before anyone ports this geometry) |

**This stage implements only `PRO54_TRANSITION_DM`** (user: "implement it only for 1 configuration for
now") — see §3/§6 for how the (still-generic) module design reflects that scope cut.

**Placement (confirmed, not re-litigated here):** this is a drop-in replacement for the data source
`projects/fx27/data/cspace/aero/generate_dm_tables.py` currently reads from (a sibling repo's bare
`Mach,Cd` CSV — an external *inventory*, not derived from any theory). It is NOT wired into
`apps/sim/engine/` at runtime: that engine is contractually offline/deterministic
(CLAUDE.md "Профиль проекта"), the geometry is fixed per rocket config, and the existing `Aero(model=
"table", ...)` loader (`apps/sim/engine/aero.py`) already does everything needed with zero changes —
confirmed by reading that module (see its own docstring, "Table format" section, and
`_load_table_impl`'s validation: a rectangular `(M, alpha)` grid, `alpha_deg,M,C_A,C_N,C_m,l1_m`
columns, edge-hold interpolation, no extrapolation). Two existing precedents in this exact codebase
already use "one-off generator, static output committed, never imported at runtime, never exercised
by pytest's collection" for exactly this reason: `projects/fx27/runs/point/regenerate_ideal_own.py`
and `generate_dm_tables.py` itself.

Out of scope (explicit): nothing else under `temporary/` is touched; `apps/sim/engine/aero.py` is
read-only reference, not modified (its loader/schema already supports what we need); the LaTeX report
is not touched.

## S2. Source geometry mapping <a name="s2-source-geometry-mapping"></a>

**Mapping correction (this revision):** the first draft of this doc used an orchestrator-supplied
guess for the file-to-rocket mapping that was wrong on 2 of 3 rows. The user then supplied the
deciding real-world fact directly: **`PRO54_TRANSITION` physically narrows from 80 mm to 59 mm**
(a converging transition), which matches `cd_mach_03_increase_D.m`'s actual geometry content (`D1=0.08
m -> D2=0.059 m` transition, then a boat-tail `D_fore=0.0572 m -> D3=0.0483 m`) — **not**
`cd_mach_03_decrease_D.m` as the first draft stated. The corrected mapping:

- `cd_mach_03_same.m` -> `PRO54_EQUAL_DM` — unchanged, unambiguous (constant tube, no transition).
- `cd_mach_03_increase_D.m` -> `PRO54_TRANSITION_DM` — **corrected, confirmed by the user's own
  vehicle knowledge** (80mm -> 59mm, matches this file's `D1`/`D2` exactly).
- `cd_mach_03_decrease_D.m` -> `PRO75_DM` — **corrected only by elimination** (it is the one file
  left once the other two are assigned). **Not independently confirmed by the user.** Before anyone
  ports this geometry (a future ticket, deferred — see §3/§6), the orchestrator should ask the user to
  confirm `PRO75`'s own real diameter progression directly, the same way `PRO54_TRANSITION`'s 80mm->59mm
  fact was just confirmed, rather than relying on elimination a second time.

All 3 scripts share: Haack-series nose (`L=0.30 m`, `D1=0.08 m`, shape param `C=0` -> this is the
Von Kármán nose, not a general Haack series with `C != 0`), 3 fins (`CR=CT=0.10 m`, `SS=0.08 m`,
`tf=0.0025 m`, sweep `0.0577 m`), 2 launch lugs/rail buttons (`dB=0.01 m`, `hB=0.008 m`), mid-flight
altitude `h_alt = 2601/2 m`, design speed `v_design = 2601/23.1 m/s`, `finProfile='square'`,
`Rs=20e-6 m`, Stoney nose-wave tables, `A_motor=0` (coasting).

They differ only in the rear-body block:

- **`PRO54_EQUAL_DM`** (`cd_mach_03_same.m`): one constant tube, `L1 = (85+10+33.6+3.61) cm` (lengths of
  the other scripts' transition/tube/boat-tail collapsed into one combined tube length to hold overall
  rocket length constant), `D1=D2=D3=D_fore=0.08 m`, `Ltr=Lbt=0`. **Deferred this stage** (§3/§6).
- **`PRO54_TRANSITION_DM`** (`cd_mach_03_increase_D.m`) — **the only geometry shipped this stage**:
  `L1=0.85 m` tube at `D1=0.08 m`, `Ltr=0.10 m` **converging** transition to `D2=0.059 m`, `L2=0.336 m`
  tube at `D2`, then a `Lbt=0.0361 m` boat-tail from `D_fore=0.0572 m` to `D3=0.0483 m`.
- **`PRO75_DM`** (`cd_mach_03_decrease_D.m`, **mapping unconfirmed** — see above): `L1=0.85 m` tube at
  `D1=0.08 m`, then a `Ltr=0.10 m` **diverging** flare to `D2=0.103 m`, then `L2=0.336 m` tube at `D2`;
  no boat-tail (`Lbt=0`, `D_fore=D3=D2`). **Deferred this stage** (§3/§6), and must not be ported until
  the mapping itself is confirmed.

**Naming note (documentation only, not a decision):** the MATLAB filenames' "decrease_D"/"increase_D"
do not literally match their own geometry's diameter direction at first glance, under EITHER mapping —
`cd_mach_03_decrease_D.m`'s rear block is titled "DIVERGING SHOULDER / FLARE" (diameter *increases*
aft) and `cd_mach_03_increase_D.m`'s rear block is a converging transition + boat-tail (diameter
*decreases* aft) — i.e. the names, read literally, point the opposite way from both the corrected
mapping above and the original (wrong) guess. This note exists only so a future reader is not tempted
to re-derive the mapping from the filenames; use the user-confirmed fact in the bullet list above
instead.

Reference area `SBT = (pi/4)*D1^2` in **every** variant (D1, the forward/nose-adjacent diameter,
never the aft diameter) — `cd_mach_03_decrease_D.m` says this explicitly ("Reference area remains
based on D1"); the other two scripts have `D1 == D2 == D3` or `D1` already the max, so it is true there
too without being stated. Fineness ratio `FR = Lt / Dmax` where `Dmax = max(D1, D2, D3, D_fore)` is the
one place the 3 scripts differ in which name they used — unified in the port (§3) into one formula
that is correct for all 3 (reduces to `Lt/D1` whenever `D1` happens to be the max, matching
`cd_mach_03_same.m`/`cd_mach_03_increase_D.m`'s literal `FR = Lt/D1`).

## S3. Decision: file/function layout <a name="s3-decision-file-function-layout"></a>

**Confirming the orchestrator's placement strategy (`decision_required` only on the two sub-questions
below; the overall placement itself was already decided with the user's go-ahead).**

New files, both under `projects/fx27/data/cspace/aero/` (alongside the existing `generate_dm_tables.py`):

1. **`drag_theory.py`** — the shared physics, parameterized by geometry. Contents:
   - `_ormach_blend`, `_ormach_qr`, `_ormach_cone` — the 3 duplicated MATLAB local functions, collapsed
     to one copy each (verbatim port of the math, vectorized with numpy).
   - `Geometry` — a frozen dataclass holding **every** geometry/physical constant each script reads
     (not just the rear-body block that differs) — see §3 rationale below for why all fields are
     spelled out per variant rather than factored into a shared-base-plus-override shape.
   - `compute_cd0(geo: Geometry) -> tuple[np.ndarray, np.ndarray]` — the single public entry point:
     returns `(M_grid, cd0_grid)`, `M_grid` ascending from 0.10 to 3.00 (step 0.01, 291 points),
     continuous (§4).
   - **This stage ships exactly ONE module-level `Geometry` instance: `PRO54_TRANSITION_GEOMETRY`**
     (user: "implement it only for 1 configuration for now"). `Geometry`/`compute_cd0` themselves stay
     fully generic — nothing in their design is specific to this one variant — so adding
     `PRO54_EQUAL_GEOMETRY`/`PRO75_GEOMETRY` later is a same-pattern, same-module addition (one more
     `Geometry(...)` literal + one more `compute_cd0` call at the generator, no new design work).
     `PRO54_EQUAL_GEOMETRY` can be added as soon as the user wants it (its source mapping is
     confirmed). **`PRO75_GEOMETRY` must not be added until the user confirms which `.m` file is
     actually `PRO75`'s geometry** (currently `cd_mach_03_decrease_D.m` only by elimination — §2).

2. **`generate_theory_drag_tables.py`** — a NEW dedicated one-off generator (not folded into
   `generate_dm_tables.py`): imports `drag_theory.compute_cd0` + the 3 `Geometry` instances, writes 3
   CSVs in the existing table format. Kept separate from `generate_dm_tables.py` because the two
   generators have different provenance (one ports an external sibling-repo inventory CSV; this one
   computes from first-principles theory) — mixing them in one file would blur that distinction the
   same way `regenerate_ideal_own.py` and `generate_dm_tables.py` are kept as two separate one-off
   scripts today for an analogous reason. Mirrors `generate_dm_tables.py`'s own shape (`_convert_one`
   analogue + `main()`), same module docstring conventions (ONE-OFF, not imported at runtime, not
   exercised by pytest, output committed, run via `python -m` from repo root).

**Why `Geometry` spells out all fields per variant instead of a shared base + override dict:** the 3
scripts share most constants (nose, fins, lugs, altitude) only *incidentally* — nothing in the physics
requires it, and a future change to one variant's fin geometry (say) must not risk silently also
changing another variant's via a shared mutable/partial default. Spelling out all ~25 fields 3 times is
more verbatim-reviewable against the 3 `.m` files side by side (a reviewer can diff one `Geometry(...)`
block against one `.m` file's geometry section directly) than reconstructing "shared base, diff
applied" would be. This is a design call, not a decision point — flagged here for transparency, not for
sign-off.

**`FR` formula unification:** `drag_theory.py` computes `FR = Lt / max(D1, D2, D3, D_fore)` uniformly
for all 3 geometries (§2) rather than branching per variant — correct for all 3 cases, matches each
source script's own value exactly (verified algebraically in §2).

## S4. Decision: Mach-regime seam handling <a name="s4-decision-mach-regime-seam-handling"></a>

**`decision_required`** — flagging per the task brief: a real discontinuity exists in the source math,
and I am recommending a specific resolution rather than silently picking one.

**Finding:** the "subsonic, M 0.1-0.75" **paper** method and the "transonic, M 0.1-1.3" **OpenRocket**
method are two independent semi-empirical formulas, and the OpenRocket method's own Mach array (`Mo =
0.10:0.01:1.30`) **already covers the full 0.1-1.3 range**, including the nominal "subsonic" band. The
scripts keep both only because the paper method's curve is plotted as a validation/comparison baseline
(the grey dashed "OpenRocket (M < 0.7 comparison)" line) — the paper method's own `CD0` array is never
exported or consumed downstream of the plot (`fprintf`'s one-line console printout at the design Mach
is the only other use). `cd_mach_03_increase_D.m` (lines ~265-267) has the author's own diagnostic that
explicitly computes and prints the step size between the two methods at M=0.7 ("step of %.4f at the
join") — i.e. the author of these scripts was already aware this gap exists and never closed it; the
two curves are not meant to be blended, only compared.

**Recommendation:** use the OpenRocket/Niskanen formula **for the entire 0.1-1.3 range**, and drop the
paper method from the ported `C_D0(M)` curve entirely (it is not part of `compute_cd0`'s output; it
played no role beyond a comparison line in the original scripts). This is not a blend or a compromise —
it eliminates the seam rather than choosing a side of it, since the formula that is supposed to be
"the" curve from 0.7 upward was already defined all the way down to 0.1 in the source.

| Option | Pros | Cons |
|---|---|---|
| **A (recommended): OpenRocket formula across 0.1-1.3, drop paper method** | No seam to handle at all; uses the more modern/cited (thesis Eq.-numbered) method uniformly; matches what the source scripts already compute, just stops computing the now-unused paper curve | Paper method's result (closer to what was perhaps independently validated against something else) is discarded, not retained even as a cross-check |
| B: blend paper and OpenRocket across the M 0.6-0.8 band (smoothstep, same shape as the source's own `ormach_blend` at the M 0.9-1.1 sub/supersonic sub-blend) | Preserves some contribution from the paper method | Introduces a blend the original author never specified or validated; hides the step rather than explaining it; more code for no evident benefit |
| C: keep the step as-is (use paper method 0.1-0.7, OpenRocket 0.7-1.3) | Most literal 1:1 port of "what the plots show" | Ships a genuine, documented discontinuity into a production drag table that `apps/sim/engine/aero.py`'s `np.interp`-based table lookup will linearly interpolate straight through — a sharp kink in `C_D0(M)` right at M=0.7, with no physical justification, that will show up in every simulated flight that passes through M=0.7 |

The M=1.3 seam (transonic -> supersonic extension) is **not** a decision point: both branches evaluate
the identical formula shape at M=1.3 (skin friction, stagnation `q_r`, base drag, and the Stoney
nose-wave interpolation all use the same expressions on both sides of the boundary, and the two Stoney
tables' M=1.30 entries agree, `CD=0.20`, by construction) — i.e. continuity there is a property of the
source math itself, not a porting choice. §7's continuity test verifies this numerically to confirm the
port preserves it (it would be a genuine porting bug, not a design question, if it did not).

## S5. Decision: CSV replacement strategy <a name="s5-decision-csv-replacement-strategy"></a>

**`decision_required` + `needs_approval`** — this is the numerical-pin-adjacent concern CLAUDE.md flags.

**Finding:** `tests/test_fx27_port.py::test_dm_aero_table_matches_fx27_source_curve_at_sample_points`
hard-pins the CURRENT (sibling-repo-ported, non-theoretical) CSV values at `M=0.0` and `M=3.0` for all
3 `*_DM` variants, e.g.:

```python
_DM_AERO_SAMPLES = {
    "pro54_transition_dm": [(0.0, 1.245), (3.0, 0.308)],
    "pro54_equal_dm":      [(0.0, 1.472), (3.0, 0.372)],
    "pro75_dm":            [(0.0, 1.466), (3.0, 0.374)],
}
```

The new theory-derived curve does not even have an `M=0.0` row (it starts at `M=0.1`, per the source
scripts), and its `M=3.0` value comes from an entirely different, independently-computed method — so
overwriting the existing CSVs in place would silently break this test (or require quietly rewriting the
pin values to match, which is exactly the kind of change CLAUDE.md's "Числовые «пины»" note says needs
explicit user sign-off, not a silent developer edit). There is no way to know, without the user looking
at the actual delta, whether the magnitude of the change is a minor refinement or something that
invalidates existing fx27 cspace comparison plots/campaign conclusions produced under the old table.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A (recommended): side-by-side, non-destructive.** Generate a new file per geometry (`pro54-transition-drag-theory.csv` this stage; `pro54-equal-`/`pro75-drag-theory.csv` once/if those geometries are added, §2/§3) via the new generator; add a matching new `Rocket` variant in `rockets.py` (`PRO54_TRANSITION_THEORY_DM` this stage) pointing at it, alongside — not replacing — the existing `*_DM` variant/CSV/test. User (or a follow-up comparison run/plot) reviews the delta before any promotion. | Zero risk to existing pins/tests/plots; the comparison itself becomes a reviewable artifact; existing `*_DM` keep working exactly as today while the new variant is evaluated | More files/variants to track until a promotion decision is made; the "right" table is ambiguous for a while (two tables per rocket) | No cost (code only) |
| B: overwrite the existing CSV outright, update the pin test's expected values to match the new theory output | Smallest number of files/variants; one table per rocket, immediately | Breaks a numeric pin without the user having seen the delta first; if fx27 cspace comparison campaign plots/conclusions (architecture-40) were produced against the old table, this silently invalidates them without a visible before/after | No cost (code only), but risk of needing a second pass if the user wants the old values back |
| C: overwrite, but keep a single frozen copy of the old CSVs under a `*-sibling-port.csv` name for the record | Middle ground — one "live" table, old one preserved for reference | Still breaks the pin test immediately; "preserved for reference" vs "side-by-side for comparison" is a thin distinction if nothing actually compares them | No cost |

**Recommendation: Option A.** The existing `*_DM` Rocket variants, their CSVs, and
`test_dm_aero_table_matches_fx27_source_curve_at_sample_points` are untouched by this stage's tickets.
A later stage (after the user has seen the delta — see §7's delta-report test/notes) decides whether to
promote the new `*_THEORY_DM` variants to be the default `*_DM` ones (at that point: rename files,
update `rockets.py`, update the pin test's expected values with the user's explicit "yes" — a separate,
future decision, out of scope for this ticket set).

## S6. Ticket list <a name="s6-ticket-list"></a>

Ready for `developer` to implement directly. All 4 tickets touch only files under
`projects/fx27/data/cspace/aero/` and `tests/`, plus one line each in `rockets.py` for ticket 3 — no
overlap with any other in-flight fx27 work; sequential by `depends_on`, not safely parallelizable
against each other (shared module), but safely parallelizable against unrelated work elsewhere in the
repo.

### [T45-1] `drag_theory.py` — shared physics module
- **Module/boundaries:** `projects/fx27/data/cspace/aero/drag_theory.py` (new file only)
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true

**Scope this stage: `PRO54_TRANSITION_DM` only.** Port the physics from `cd_mach_03_increase_D.m`
ONLY (the corrected source file for `PRO54_TRANSITION_DM` — §2; re-read it directly from
`temporary/drive-download-20261117T190208Z-1-001/cd_mach_03_increase_D.m` during implementation, do
not reuse any geometry values drafted under the earlier, wrong mapping). Keep `Geometry`/
`_ormach_blend`/`_ormach_qr`/`_ormach_cone`/`compute_cd0` themselves fully generic (they must still
work correctly for any of the 3 rear-body shapes — constant tube, converging transition+boat-tail,
diverging flare — not hardcoded to this one geometry) — only the *data* (which `Geometry` instances
exist as module-level constants) is scoped down:

```python
@dataclasses.dataclass(frozen=True)
class Geometry:
    # nose (shared across all 3, but spelled out per instance -- SS3 rationale)
    L: float          # m, nose length
    D1: float         # m, nose-base / forward-tube diameter (= SBT's reference diameter, always)
    haack_C: float    # Haack series shape param (0.0 = Von Karman, all 3 source scripts)
    # rear body (the ONE block that differs per variant -- SS2)
    L1: float; D2: float; L2: float; Ltr: float; Lbt: float; D_fore: float; D3: float
    # fins (shared)
    CR: float; CT: float; SS: float; tf: float; N: int; sweep_len: float
    # lugs (shared)
    nB: int; dB: float; hB: float
    # flight condition (shared)
    h_alt_m: float; v_design: float
    # OpenRocket-method inputs (shared)
    Rs: float = 20e-6
    fin_profile: str = "square"

def _ormach_blend(M: np.ndarray, sub_fn, sup_fn) -> np.ndarray: ...
def _ormach_qr(M: np.ndarray) -> np.ndarray: ...
def _ormach_cone(M: np.ndarray, se: float) -> np.ndarray: ...

def compute_cd0(geo: Geometry) -> tuple[np.ndarray, np.ndarray]:
    """Returns (M_grid, cd0_grid), M_grid = 0.10..3.00 step 0.01 (291 pts), ascending,
    continuous. 0.10-1.30: OpenRocket/Niskanen method (thesis Eq. 3.77-3.97, App. B) --
    the ONLY method used in this range (SS4: the source scripts' separate "paper" method,
    M 0.1-0.75, is NOT ported -- it was a comparison baseline, never exported in the
    source). 1.30-3.00: the supersonic extension, continuous with the 1.30 boundary by
    construction (both branches are the same formula shape there -- SS4). Geometry-generic:
    works for a constant tube, a converging transition+boat-tail, or a diverging flare rear
    body (the boattail/flare branch below handles all 3 shapes) -- NOT specific to whichever
    Geometry instance is passed in."""

PRO54_TRANSITION_GEOMETRY = Geometry(...)  # cd_mach_03_increase_D.m's transition+boat-tail block
                                            # -- the ONLY concrete instance shipped this stage (SS2/SS3).
# PRO54_EQUAL_GEOMETRY (cd_mach_03_same.m) and PRO75_GEOMETRY (cd_mach_03_decrease_D.m, mapping
# UNCONFIRMED -- SS2) are deferred: same pattern, add later, do not add PRO75_GEOMETRY before the
# user confirms the file mapping.
```

Internal structure of `compute_cd0`: a private `_cd0_transonic(Mo, geo) -> np.ndarray` (the OpenRocket
method, M 0.10-1.30, i.e. what the MATLAB calls `CD0_or` computed over the full `Mo` range, steps 1-6 of
each script's "ADDED BY CLAUDE" section) and a private `_cd0_supersonic(M_sup, geo) -> np.ndarray` (the
"1.3-3 SUPERSONIC" section), concatenated at `M=1.30` by `compute_cd0` (the M=1.30 row comes from
`_cd0_transonic`; `_cd0_supersonic` starts its own array at `M=1.30` too for the continuity check in
§7, but `compute_cd0` keeps only one of the two 1.30 rows in its returned grid — use
`_cd0_transonic`'s, dropping `_cd0_supersonic`'s duplicate point).

Rear-body-dependent logic: `_cd0_transonic`/`_cd0_supersonic`'s boattail/flare branch must handle all 3
possible `(bt_fore, bt_aft)` relationships generically — `cd_mach_03_decrease_D.m`'s own `if/elseif/
else` (`bt_fore(kk) > bt_aft(kk)` -> boat-tail base-drag law, `bt_fore(kk) < bt_aft(kk)` -> flare
wave-drag law via `_ormach_cone`, else -> zero contribution) is the fullest version of this branch
across the 3 source scripts and generalizes correctly to all 3 rear-body shapes (verified
algebraically, SS2) — port that 3-way branch, not `cd_mach_03_increase_D.m`'s own narrower 2-way
version (boat-tail-only, with an explicit `==` guard, because THIS stage's own geometry,
`PRO54_TRANSITION_GEOMETRY`, never needs the diverging/flare branch — both of its rear segments
converge). **Known test-coverage gap this stage:** because `PRO54_TRANSITION_GEOMETRY` never exercises
the flare branch, T45-4 cannot cover it with a geometry-driven test this round — it is implemented
generically (so the eventual `PRO75_GEOMETRY`/diverging-flare addition does not need a code change,
only a new `Geometry` instance), but its correctness there is unverified until that future geometry is
added and tested.

### [T45-2] `generate_theory_drag_tables.py` — one-off generator
- **Module/boundaries:** `projects/fx27/data/cspace/aero/generate_theory_drag_tables.py` (new file only)
- **Assignee:** developer
- **depends_on:** [T45-1]
- **parallel_safe:** false (depends on T45-1's `compute_cd0` signature)

**Scope this stage: `PRO54_TRANSITION_DM` only — one `(name, Geometry)` pair, one output file.**
Mirrors `generate_dm_tables.py`'s shape (module docstring: ONE-OFF, not imported at runtime, not
exercised by pytest, output committed, `python -m projects.fx27.data.cspace.aero.
generate_theory_drag_tables` from repo root). Call `drag_theory.compute_cd0(drag_theory.
PRO54_TRANSITION_GEOMETRY)`, write `pro54-transition-drag-theory.csv` next to the existing CSVs in the
**existing table format** (`apps/sim/engine/aero.py`'s v1 format, same as `generate_dm_tables.py`'s own
`_convert_one`). Structure `main()` as a loop over a (small, currently 1-entry) `(name, Geometry)` list
— not a single hardcoded call — so adding `PRO54_EQUAL_GEOMETRY`/`PRO75_GEOMETRY` later (once shipped
in `drag_theory.py`, T45-1) is a one-line addition to that list, not a rewrite of this script.

```
alpha_deg,M,C_A,C_N,C_m,l1_m
-89.0,0.10,<cd0>,0.0,0.0,1.0
89.0,0.10,<cd0>,0.0,0.0,1.0
-89.0,0.11,<cd0>,0.0,0.0,1.0
89.0,0.11,<cd0>,0.0,0.0,1.0
... (291 Mach values x 2 alpha rows = 582 rows)
```

Output filename (SS5 Option A — side-by-side, not overwriting): **`pro54-transition-drag-theory.csv`**
only, this stage. (`pro54-equal-drag-theory.csv`/`pro75-drag-theory.csv` are future additions, the
latter blocked on the mapping confirmation in §2.)

Header comment block: same style as `generate_dm_tables.py`'s own (cite this architecture doc,
§S1/S2/S4/S5, instead of architecture-40; state the method — "Niskanen thesis / OpenRocket
semi-empirical method, M 0.10-1.30, hand-extended supersonic 1.30-3.00" — and that this is a
THEORY-derived table, not a ported external inventory, so a future reader does not confuse it with
`generate_dm_tables.py`'s provenance).

### [T45-3] New `PRO54_TRANSITION_THEORY_DM` rocket variant for comparison
- **Module/boundaries:** `projects/fx27/data/cspace/rockets.py` (append-only: 1 new module-level
  constant + its `_TABLE_*` path line; no edits to any existing line)
- **Assignee:** developer
- **depends_on:** [T45-2]
- **parallel_safe:** false (T45-2 must have produced the CSV first; touches a shared file other
  in-flight fx27 tickets may also touch — check `git status`/recent commits before starting)

**Scope this stage: one new variant only.**

```python
_TABLE_PRO54_TRANSITION_THEORY = cspace_aero("pro54-transition-drag-theory.csv")

PRO54_TRANSITION_THEORY_DM = dataclasses.replace(
    PRO54_TRANSITION, name="pro54_transition_theory_dm",
    aero=_dm_aero(PRO54_TRANSITION.aero, _TABLE_PRO54_TRANSITION_THEORY),
    notes="... theory-derived (Niskanen/OpenRocket method, ported from cd_mach_03_increase_D.m) "
          "C_A(M) table, SS5 Option A comparison variant -- NOT a replacement for "
          "pro54_transition_dm, see architecture-45.",
)
# PRO54_EQUAL_THEORY_DM / PRO75_THEORY_DM: future additions, same pattern, once T45-1/T45-2 ship
# the corresponding Geometry/CSV (PRO75's own file mapping needs user confirmation first -- SS2).
```

Do NOT add this to `SCENARIOS_DM` (`scenarios_dm.py`) or any comparison-plot script in this ticket —
that would implicitly make it part of the existing 7-row comparison set
(`test_cspace_dm_has_exactly_the_seven_comparison_rows` would need to change, which is exactly the kind
of scope creep SS5 Option A is designed to avoid). It exists only so a human (or a follow-up,
separately-scoped comparison script/notebook) can load and inspect it.

### [T45-4] Tests
- **Module/boundaries:** `tests/test_fx27_drag_theory.py` (new file only)
- **Assignee:** developer
- **depends_on:** [T45-1, T45-2]
- **parallel_safe:** false (depends on both prior tickets' concrete output)

**Scope this stage:** the 3 generic helper-algebra tests (§7 items 1-3) are geometry-independent and
stay as specified. Items 4-7 (geometry-dependent: SBT/FR/SW hand-checks, continuity, physical sanity,
delta-report) are scoped to `PRO54_TRANSITION_GEOMETRY` / `pro54_transition_dm` ONLY this round — see
§7 for the updated per-item detail. When `PRO54_EQUAL_GEOMETRY`/`PRO75_GEOMETRY` are added in a future
stage, items 4-7 get a parametrized/repeated counterpart for each new geometry then, not now.

## S7. Test coverage plan <a name="s7-test-coverage-plan"></a>

New physics logic — D-181's "no new tests for fx27 reorg-only work" exemption does NOT apply (per the
task brief). Follow this project's `tdd` skill convention (tests before/alongside the port, not after).
All tests are fast pure-numpy, run directly under pytest (unlike `regenerate_ideal_own.py`'s heavy
solver calls, which are deliberately NOT re-run under pytest per that file's own precedent) — this
module has no solver/IO dependency, so the `test_regenerate_ideal_own.py` precedent of testing only the
lightweight helper and NOT re-running the heavy part does not apply here; `compute_cd0` itself is cheap
enough to call directly in every test.

1. **`_ormach_qr` algebraic checks** (no geometry needed): `_ormach_qr(np.array([1.0]))` must equal
   `1 + 0.25 + 0.025 = 1.275` (subsonic branch at the M=1 boundary, both branch formulas' `M<1`/`M>=1`
   split evaluated at exactly `M=1.0` — use the `M<1` branch's value as the asserted one, since `1.0` is
   `~s` false i.e. routed to the supersonic formula by the source's own `s = M<1` test, so assert
   against `1.84 - 0.76 + 0.166 + 0.035 = 1.281` instead — confirm which branch numpy's `<` actually
   selects for `M==1.0` before writing the assertion, since this is the exact boundary value and an
   off-by-one in the branch split is a classic port bug). Also check `_ormach_qr` is continuous across
   its own `M=1` boundary to within float tolerance (evaluate both formulas at `M=1.0` directly and
   compare, independent of the `s`/`~s` routing).
2. **`_ormach_blend` boundary behavior:** `_ormach_blend(M, sub_fn, sup_fn)` at `M=0.9` must equal
   `sub_fn(0.9)` exactly (weight 0), at `M=1.1` must equal `sup_fn(1.1)` exactly (weight 1), and at
   `M=1.0` (midpoint) must equal the 50/50 average of `sub_fn(0.9)` and `sup_fn(1.1)` (per the source's
   own `w = (M-0.9)/0.2` linear blend formula).
3. **`_ormach_cone` sanity:** at `M=1.3` (`Mh`, the thesis's own hinge Mach in the source), the mid-
   regime polynomial branch and the high-regime closed-form branch (`2.1*se^2 + 0.5*se/sqrt(M^2-1)`)
   must agree to float tolerance (continuity at the branch's own stated hinge).
4. **`PRO54_TRANSITION_GEOMETRY`'s `SBT`/`FR`/`SW` computed values** (this stage's only geometry):
   hand-check `SBT = (pi/4)*0.08^2 ~= 0.005027 m^2`, and `FR = Lt/Dmax` against the hand-computed
   `Lt`/`Dmax` from §2's constants: `Lt = L + L1 + Ltr + L2 + Lbt = 0.30 + 0.85 + 0.10 + 0.336 + 0.0361
   = 1.6221 m`, `Dmax = max(D1=0.08, D2=0.059, D_fore=0.0572, D3=0.0483) = D1 = 0.08 m` (the forward
   tube stays the widest point on this converging/boat-tailed geometry), `FR ~= 20.28`. (When
   `PRO54_EQUAL_GEOMETRY` is added later, note for the implementer: its `Lt` works out to the same
   `1.6221 m` by the source script's own deliberate length-preservation convention, §S2 — a handy
   cross-check at that point, not needed now.)
5. **Continuity at M=1.30** (the port-correctness check for SS4's "not a decision point" claim): call
   `compute_cd0(PRO54_TRANSITION_GEOMETRY)`, and separately evaluate the transonic branch's own formula
   and the supersonic branch's own formula both AT `M=1.30`, asserting they agree to within `1e-9`
   relative — this is the test that would actually catch a porting bug in either branch's M=1.30
   boundary handling, not just assert the output array has no visible jump.
6. **Physical sanity bounds** for `PRO54_TRANSITION_GEOMETRY`'s full `compute_cd0` output: `cd0_grid` is
   finite and `> 0.0` everywhere (M 0.10-3.00), and stays under a generous ceiling (e.g. `< 2.0`) —
   loose bounds, not tight pins, since there is no independent MATLAB run available in this environment
   to produce an exact oracle value; these bounds exist to catch a gross sign/unit error (e.g. a
   dropped `/SBT` normalization), not to pin exact values.
7. **Delta-report vs. the existing sibling-ported CSV**, `pro54-transition-drag.csv` only this stage
   (task requirement, SS5's input): load the existing `pro54-transition-drag.csv` (via
   `apps/sim/engine/aero.py`'s own `_load_table`, or a plain CSV read — developer's choice) and the new
   `pro54-transition-drag-theory.csv`, compare `C_A` at the Mach values the two tables share (old
   table's grid is 0-3.0 step 0.025; new table's is 0.1-3.0 step 0.01 — compare at the old grid's
   points that fall inside the new table's range, `np.interp`-ing the new table onto the old grid's
   Mach values). Write the per-point delta (and max/mean abs delta) to
   `dev/docs/architecture-45-fx27-theory-drag-port-delta.md` (or print via `-s`/captured stdout the test
   asserts against a loose bound, e.g. `max abs delta < 1.0` — a bound wide enough not to fail on a
   large-but-plausible refinement, narrow enough to fail on an obvious unit/sign bug) — the point of
   this test is to SURFACE the delta for the user's SS5 promotion decision, not to gate the port on a
   specific tolerance.

## S8. Rejected options <a name="s8-rejected-options"></a>

- **Folding the generator into `generate_dm_tables.py`:** rejected (SS3) — different provenance
  (external sibling-repo CSV vs. first-principles theory); mixing would blur which rows in the output
  came from which source, and complicate a future removal of either source independently.
- **Shared-base-plus-override `Geometry` construction:** rejected (SS3) — a partial/diffed
  representation is less directly reviewable against the 3 source `.m` files and risks an accidental
  cross-variant coupling through a shared mutable default.
- **Blending across the M=0.7 seam (Option B, SS4):** rejected — invents a transition the source
  authors never specified, for no benefit over simply not computing the now-redundant paper-method leg.
- **Overwriting the existing CSVs now (Option B, SS5):** rejected — breaks a committed numeric pin
  (`test_fx27_port.py`) without the user having seen the delta; this is exactly the class of change
  CLAUDE.md's numeric-pin note requires explicit sign-off for, and sign-off needs something to look at
  first.
- **Porting all 3 geometries in this stage's tickets:** rejected per explicit user instruction
  ("implement it only for 1 configuration for now") — not a technical objection to the other 2; they are
  deferred as straightforward future additions (§2/§3), with `PRO75_GEOMETRY` additionally blocked on
  a mapping confirmation the user has not yet given.
