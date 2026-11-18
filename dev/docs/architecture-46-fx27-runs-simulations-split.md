# Architecture 46 — fx27 `runs/` one-file-per-version split

## Кратко (RU)

- Пользователь явно отменил своё же решение D-192 (принятое минутами ранее в этой же сессии): вместо
  консолидированной структуры «один файл на тип анализа + флаг `--case`/аргумент» (это и есть то, что
  построили Phase 2.27/2.28) нужна структура «один файл на каждую версию roadmap.md» в `runs/point/`,
  где можно просто запустить файл и получить результат той конкретной исторической версии.
- Это **документированный факт, не вопрос**: Phase 2.27/2.28 консолидировали 3+ отдельных скрипта
  `comparison.py`/`comparison_dc_dm.py`/`euroc/comparison.py` в один `runs/point/comparison.py --case
  {cspace,cspace_dc_dm,euroc}`; этот документ её разворачивает обратно на 12 отдельных файлов (13 id
  минус 1.11 "не построено" минус 1.13 "вне охвата, Phase 2.29 в процессе").
- **Развилка снята пользователем** (уточнение 2026-11-18, в этой же сессии): слово "simulations" в
  исходной просьбе означало сегодняшнюю `solvers/point/` как есть, а не новое имя/новый слой. Никакого
  переименования и никакого разделения `solvers/point/` на два пакета — она остаётся ровно в
  сегодняшнем виде (все 8 файлов, корнеискатели и раннеры полёта вместе, как сейчас). Каждый новый
  `NN_...py` импортирует из `projects.fx27.solvers.point.*` ровно так же, как сегодняшние
  `runs/point/*.py` уже делают.
- `data/` (сценарии/ракеты, уже консолидированные в Phase 2.28) этим раундом **не трогаются** —
  переписывается только `runs/point/`; `solvers/point/` не трогается вообще.
- `controller.py` (трек Controller, отдельная таблица roadmap.md, другая сессия) не трогается — не
  перемещается, не переименовывается.
- 12 новых файлов версий + 1 переименование (`sweep.py` -> `10_...py`). Никаких правок в тестовых
  файлах не требуется — `solvers/point/` не меняется, импорты туда остаются прежними.
- Нумерация файлов — с ведущими нулями (`01`...`13`), чтобы алфавитная сортировка в файловом
  менеджере совпадала с порядком roadmap.md (без нулей `10` отсортировался бы перед `2`).

---

## Table of contents

- [S46.1 Context and what this reverses](#s461-context-and-what-this-reverses)
- [S46.2 Resolution — no `simulations` layer; `solvers/point/` stays as-is](#s462-resolution--no-simulations-layer-solverspoint-stays-as-is)
- [S46.3 Scope boundaries (confirmed against roadmap.md)](#s463-scope-boundaries-confirmed-against-roadmapmd)
- [S46.4 Target directory structure](#s464-target-directory-structure)
- [S46.5 File-naming convention for version ids](#s465-file-naming-convention-for-version-ids)
- [S46.6 Per-id file contract (what each NN file does)](#s466-per-id-file-contract-what-each-nn-file-does)
- [S46.7 id 1.12 ambiguity — "final cross-campaign comparison"](#s467-id-112-ambiguity--final-cross-campaign-comparison)
- [S46.8 Test-file impact — none](#s468-test-file-impact--none)
- [S46.9 Rejected options](#s469-rejected-options)
- [S46.10 Tickets](#s4610-tickets)

---

## S46.1 Context and what this reverses

D-192 (2026-11-18, same session, minutes before this one) approved keeping the point-mass track's
*consolidated* structure: one file per analysis **type**, selected by a `--case`/argument, covering all
historical variants internally. That is exactly what Phase 2.27 (`architecture-43-fx27-restructure.md`)
and Phase 2.28 (`architecture-44-fx27-campaigns-reorg.md`) built:

- `runs/cspace/comparison.py` + `comparison_dc_dm.py` + `runs/euroc/comparison.py` (3 files) were merged
  into **one** `runs/point/comparison.py --case {cspace,cspace_dc_dm,euroc}`.
- `ideal_mass.py`/`ideal_drag.py`/`ideal_open_airbrake.py` already loop over **both** dc and dm scenarios
  internally in one run (not separately runnable historical versions).

The user has now reversed that call: **"for each 'id' create a separate file"** — `runs/` becomes
click-and-run, one file per roadmap.md version id. The shared logic those files call into is **unchanged**:
`projects/fx27/solvers/point/` (see S46.2 — the user clarified "simulations" referred to this existing
directory, not a new one).

This document is the architecture for that reversal. Nobody reading the history later should be confused:
D-192 chose consolidation; this decision (recorded live in `dev/status.json`, 2026-11-18) explicitly
un-does it, by the user's own explicit request, minutes later, in full knowledge of what D-192 had just
built.

`dev/docs/fx27-point-mass-version-history.md` (written for D-192) remains valid and useful as-is — it is
the chronological *development* history (which Phase/Step built what). This document is about the
*current-state* file layout going forward; it does not replace that history doc. That history doc's own
closing section ("Structural Question for Orchestrator") anticipated exactly this fork and left it
explicitly open — see its last ~15 lines.

`projects/fx27/_docs/roadmap.md`'s **General** table (13 ids, ids 1.1–1.13) is the authoritative source
for what the 13 versions *are* — this document does not re-derive them, only re-homes their
implementation.

---

## S46.2 Resolution — no `simulations` layer; `solvers/point/` stays as-is

This section previously carried a `decision_required` fork (3-option table: mechanical rename, new
`simulations/` layer mirroring `apps/sim` vs `apps/optimization`, or fold-everything-together) asking
whether "simulations" in the user's instruction meant a new package/rename or was just loose phrasing for
today's existing `solvers/point/` directory.

**Resolved by the user directly** (2026-11-18, same session, in response to the architect's flagged
fork): *"when I was saying /simulations i meant /solvers. why do you want to create a new layer? solver is
not enough?"* — the user was using "simulations" as a plain-English description of what
`projects/fx27/solvers/point/` already *is* (run a flight, report on it, size a brake, estimate a
parameter — "all or most of the logic" the `runs/` scripts call into), not asking for a rename or a split.

**Outcome:**
- No rename. `solvers/point/` keeps its name.
- No split. All 8 files stay in one package exactly as today — `flight.py`, `metrics.py`, `comparison.py`,
  `plots.py`, `validity.py`, `controller.py` (flight-running family) and `estimate.py`,
  `ideal_open_airbrake.py` (root-finder family) remain side by side, mixed, as they are right now. The
  `apps/sim` vs `apps/optimization` precedent this architect raised does **not** apply inside
  `projects/fx27/` — noted for the record, not acted on.
- Every new `NN_...py` file created by this document imports from `projects.fx27.solvers.point.*`
  (and `projects.fx27.data.*`) exactly the way today's consolidated `runs/point/*.py` files already do —
  S46.6's table below is written directly against `solvers.point.*`, no further substitution needed.
- `controller.py` is untouched — not moved, not renamed, not part of this round at all (it belongs to the
  separate Controller-track roadmap table in `roadmap.md`, a parallel session's own work).

No further `grilling`/approval needed on this point — it is a plain clarification of what the user already
asked for, not a new fork.

---

## S46.3 Scope boundaries (confirmed against roadmap.md)

Re-read directly from `projects/fx27/_docs/roadmap.md` General table (ids 1.1–1.13) before writing this
document (not re-derived from memory) — the "current file" column there is what this document splits
**from**:

| Confirmed unchanged by this round | Why |
|---|---|
| `apps/**` (all of it) | Task scope: nothing under `apps/` changes. `solvers.point.flight.run` still calls `apps.sim.schema.assemble` + `apps.sim.engine.integrate.run_sim` unchanged; `solvers.point.estimate` still re-exports `apps.optimization.apogee_targeting.solve` unchanged. |
| `projects/fx27/data/**` | Scenario/rocket dicts (`data/cspace/scenarios.py`, `scenarios_dm.py`, `rockets.py`, `rockets_ideal.py`, `data/euroc/*`) stay exactly as Phase 2.28 left them — consolidated, not re-split. Every new `NN` file **imports** from `data/`, none of them add, remove, or rename anything there. |
| `projects/fx27/solvers/point/**` (all 8 files) | Per S46.2's resolution — untouched, no rename, no split, no content edit. Every new `NN` file imports from it exactly as today's consolidated `runs/point/*.py` files already do. |
| `data/cspace/aero/**`, `projects/fx27/_docs/roadmap.md`'s own row 1.13 and its current files (`drag_theory.py`, `generate_theory_drag_tables.py`) | Explicitly out of scope — Phase 2.29 (architecture-45) is reported in progress by another developer subagent on the orchestrator's own full-suite check right now. **Do not touch.** Flagged below (S46.9) as a known follow-up once Phase 2.29 lands: id 1.13 gets its own `13_...py` file in a later round. |
| Roadmap id 1.11 | "Not built" per roadmap.md's own Notes — no file to create, nothing to split. Skipped, not a gap in this document. |
| `projects/fx27/runs/point/point.py` | Not a roadmap-id artifact (roadmap.md's own Notes section does not list it; it is the project's single-flight diagnostic tool, tested by `tests/test_fx27_port.py:360/374`'s CLI smoke test). Left exactly as-is, including its `from projects.fx27.solvers.point.flight/plots/validity import ...` lines — no edit at all, since `solvers/point/` does not move (S46.2). |
| Controller-track roadmap section (`solvers/point/controller.py`, `runs/point/controller.py`, `data/cspace/airbrake_data.py`) | Separate roadmap table (`roadmap.md`'s own "Controller" section), built by a parallel orchestrator session already (Steps 152–153), already one-file-per-id from the start (never consolidated behind a `--case` flag) — not what D-192 or this reversal is about, and confirmed by the user (S46.2) as **not touched at all** this round, not even moved. |

---

## S46.4 Target directory structure

```
projects/fx27/
  data/                         <- UNCHANGED (Phase 2.28 scope, not touched this round)
    cspace/
      rockets.py, rockets_ideal.py, scenarios.py, scenarios_dm.py, aero/, motors/, airbrake_data.py
    euroc/
      rockets.py, motors.py, scenarios.py, site.py, weather.py

  solvers/                      <- UNCHANGED (S46.2 — not touched this round, no rename, no split)
    point/
      __init__.py
      flight.py, metrics.py, comparison.py, plots.py, validity.py, controller.py, estimate.py,
      ideal_open_airbrake.py     <- all 8 files, same content, same package, as today

  runs/
    point/
      __init__.py
      point.py                   <- UNCHANGED (not a roadmap id; imports from solvers.point unchanged)
      regenerate_ideal_own.py    <- UNCHANGED (one-off tool, not a roadmap id; imports apps.optimization directly)
      controller.py              <- UNCHANGED (Controller-track id 1.1; separate roadmap table, not touched)

      01_cspace_comparison_dc.py           # roadmap 1.1
      02_cspace_ideal_mass_dc.py            # roadmap 1.2
      03_cspace_ideal_drag_dc.py             # roadmap 1.3
      04_cspace_ideal_airbrake_dc.py          # roadmap 1.4
      05_cspace_comparison_dc_dm.py            # roadmap 1.5
      06_cspace_ideal_mass_dm.py                # roadmap 1.6
      07_cspace_ideal_drag_dm.py                  # roadmap 1.7
      08_cspace_ideal_airbrake_dm.py                # roadmap 1.8
      09_euroc_comparison_fx27_columns.py             # roadmap 1.9
      10_euroc_sweep_feasibility.py                    # roadmap 1.10 (renamed from sweep.py, content unchanged)
      # 1.11 — not built, no file (roadmap.md Notes)
      12_final_cross_campaign_comparison.py             # roadmap 1.12 (see S46.7)
      # 1.13 — out of scope this round (Phase 2.29 in progress elsewhere)

  _docs/
    roadmap.md                  <- UNCHANGED this round except its "current file" column for ids
                                    1.1-1.10/1.12, which gets updated to point at the new NN
                                    filenames as part of T1-T4 below (small, mechanical, same ticket
                                    that creates each file)

DELETED (content redistributed into the NN files above, nothing lost):
  runs/point/comparison.py
  runs/point/ideal_mass.py
  runs/point/ideal_drag.py
  runs/point/ideal_open_airbrake.py
  runs/point/sweep.py            <- actually renamed, not deleted-and-rewritten (T4)
```

---

## S46.5 File-naming convention for version ids

A literal `1.1_cspace...py` filename is not usable in a plain `from pkg.1_1_foo import x` source-level
import statement (a leading digit is tokenized as a numeric literal by Python's grammar — verified
directly: `SyntaxError: invalid decimal literal`). It IS fine for `python -m pkg.01_foo`-style invocation
(`runpy`/`importlib` resolve the dotted path as strings against the filesystem, not as parsed source) —
confirmed directly in this environment. User's call, applied: **drop the stage digit and the `v` letter
entirely** — the files already live in `runs/point/`, which only ever holds stage-1 files, so repeating
"1" in every filename is redundant. Convention: **`<seq2>_<slug>.py`**, zero-padded 2-digit sequence
(`01` not `1`), no letter/stage prefix.

- `01` … `13` is the zero-padded sequence number, matching roadmap.md's id digits one-to-one (`1.1` ->
  `01`, `1.10` -> `10`, etc.) so a reader can always reconstruct the roadmap id from the filename and
  vice versa. The one place the dropped prefix needs a workaround: `12_final_cross_campaign_comparison.py`
  cannot use a literal `from projects.fx27.runs.point.01_cspace_comparison_dc import main` statement
  (same leading-digit `SyntaxError`) — it uses `importlib.import_module("projects.fx27.runs.point.
  01_cspace_comparison_dc").main()` instead (dynamic lookup, not a parsed import statement).
- **Zero-padding is required, not cosmetic**: without it, `10_....py` sorts alphabetically *before*
  `2_....py` in any plain directory listing or `ls`/Explorer view (`"1"` < `"2"` as the first char after
  comparing equal prefixes, but `"10"` vs `"2"` compares digit-by-digit as `"1"` < `"2"` too — the actual
  failure is `10` landing between `1` and `2`, not after `9`), which defeats the entire point
  of "click any file and get results in version order." Two-digit padding is sufficient headroom for
  roadmap.md's own stage-2/stage-3 reservations (`2.1`, `3.1`, …) without ever needing 3 digits at this
  project's scale.
- `<slug>` is a short human-readable description, not load-bearing for sorting or imports — chosen per
  S46.6's table below, matching roadmap.md's own `name` column as closely as line length allows.
- This is a **mechanical, non-ambiguous choice** — not raised as a `decision_required` fork. Flagged here
  only so the rationale (padding) is on record, since an un-padded scheme would look equally plausible at
  a glance and silently break sort order once id 1.10 exists.

---

## S46.6 Per-id file contract (what each NN file does)

Every file below is a **thin script**: imports a specific scenario/rocket dict (or subset) from
`projects/fx27/data/`, calls into `projects.fx27.solvers.point.*` (unchanged, per S46.2 — both the
flight-running functions and the root-finder wrappers live there, exactly as today), with the literal
parameters that reproduce that one historical version's output byte-for-byte relative to today's
consolidated behavior for that `--case`/subset. No new computation, no new tolerance, no new CLI flag
beyond what the corresponding branch of the file it is extracted from already had.

| File | Roadmap id | Extracted from (today) | Imports from `data/` | Calls (module.function) | Body = |
|---|---|---|---|---|---|
| `01_cspace_comparison_dc.py` | 1.1 | `runs/point/comparison.py`'s `_run_cspace()` | `data.cspace.scenarios.SCENARIOS` | `solvers.point.comparison.run_many/print_table/save_csv`, `solvers.point.metrics.row_from_flight`, `solvers.point.plots.plot_displacement_comparison/plot_kinematics_comparison`, `solvers.point.validity.check_validity/print_validity` (under `--validity`) | `_run_cspace()`'s body verbatim, promoted to `main()`; `--validity`/`--show` flags kept |
| `02_cspace_ideal_mass_dc.py` | 1.2 | `runs/point/ideal_mass.py`'s `_FX27_SOLVED` loop only (drop the `_OWN_AND_FX27_DM` loop) | `data.cspace.rockets_ideal.{PRO54_TRANSITION_IDEAL_MASS_KG, PRO75_IDEAL_MASS_KG}`, `data.cspace.scenarios.SCENARIOS` | `solvers.point.estimate.estimate_airframe_mass` | dc-only half of today's `main()` |
| `03_cspace_ideal_drag_dc.py` | 1.3 | `runs/point/ideal_drag.py`'s `_FX27_SOLVED`/`_CAVEAT` loop only | `data.cspace.rockets_ideal.{PRO54_TRANSITION_IDEAL_DRAG_CX, PRO75_IDEAL_DRAG_CX}`, `data.cspace.scenarios.SCENARIOS` | `solvers.point.estimate.estimate_cx` | dc-only half, including the `pro54_transition` AC-3 caveat print |
| `04_cspace_ideal_airbrake_dc.py` | 1.4 | `runs/point/ideal_open_airbrake.py`'s `IDEAL_VARIANTS_DC` loop only | `data.cspace.scenarios.SCENARIOS` | `solvers.point.ideal_open_airbrake.size_airbrake/print_brake_report` | dc-only half |
| `05_cspace_comparison_dc_dm.py` | 1.5 | `runs/point/comparison.py`'s `_run_cspace_dc_dm()` | `data.cspace.scenarios.SCENARIOS` + `data.cspace.scenarios_dm.SCENARIOS_DM` | same `solvers.point.*` calls as 01 | `_run_cspace_dc_dm()`'s body verbatim, promoted to `main()` |
| `06_cspace_ideal_mass_dm.py` | 1.6 | `runs/point/ideal_mass.py`'s `_OWN_AND_FX27_DM` loop only | `data.cspace.rockets_ideal.{PRO54_TRANSITION_DM_IDEAL_MASS_KG, PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG, PRO75_DM_IDEAL_MASS_KG, PRO75_DM_IDEAL_OWN_MASS_KG}`, `data.cspace.scenarios_dm.SCENARIOS_DM` | `solvers.point.estimate.estimate_airframe_mass` | dm-only half, "NOT an oracle" framing kept verbatim |
| `07_cspace_ideal_drag_dm.py` | 1.7 | `runs/point/ideal_drag.py`'s `_OWN_AND_FX27_DM` loop only | `data.cspace.rockets_ideal.{*_DM_IDEAL_DRAG_CX_SCALE, *_DM_IDEAL_OWN_DRAG_CX_SCALE}`, `data.cspace.scenarios_dm.SCENARIOS_DM` | `solvers.point.estimate.estimate_cx_scale` | dm-only half |
| `08_cspace_ideal_airbrake_dm.py` | 1.8 | `runs/point/ideal_open_airbrake.py`'s `IDEAL_VARIANTS_DM` loop only | `data.cspace.scenarios_dm.SCENARIOS_DM` | `solvers.point.ideal_open_airbrake.size_airbrake/print_brake_report` | dm-only half |
| `09_euroc_comparison_fx27_columns.py` | 1.9 | `runs/point/comparison.py`'s `_run_euroc()` | `data.euroc.scenarios.generate_scenarios()` | same `solvers.point.*` calls as 01, no figures (euroc never plotted) | `_run_euroc()`'s body verbatim, promoted to `main()` |
| `10_euroc_sweep_feasibility.py` | 1.10 | `runs/point/sweep.py`, unchanged | `data.euroc.{motors.{DEFERRED_MOTORS,MOTORS}, rockets.ROCKETS, scenarios.CANDIDATES, site.SITE, weather.WEATHER}` | `apps.optimization.motor_selection.scenario_sweep.{Constraints,print_table,save_csv,sweep_scenario}` (direct `apps/` import — this file never went through `solvers/point/`, so it is a pure rename) | 100% unchanged, file renamed only |
| `12_final_cross_campaign_comparison.py` | 1.12 | New composition — see S46.7 | all three of the above (`data.cspace.*`, `data.cspace.scenarios_dm`, `data.euroc.scenarios`) | sequentially calls `01`/`05`/`09`'s own `main()` functions via `importlib.import_module(...)` (leading-digit module names, not a literal `from ... import` statement — S46.5), not reimplemented | thin orchestrator, see S46.7 |

Every file's module docstring states its roadmap id and a back-link, e.g.:
`"""projects/fx27/runs/point/02_cspace_ideal_mass_dc.py -- roadmap General id 1.2
(see projects/fx27/_docs/roadmap.md). ..."""` — carrying forward the substantive rationale paragraphs
each extracted-from file already has (AC-3 caveat text, "NOT an oracle" framing, etc.) verbatim, since
those are documentation of *physics/measurement* facts, not of the old consolidated-file structure, and
remain true regardless of which file they live in.

Run convention unchanged: `python -m projects.fx27.runs.point.01_cspace_comparison_dc` (etc.) — same
`-m`-from-repo-root convention every existing `runs/*` entry point already uses and documents in its own
docstring.

---

## S46.7 id 1.12 ambiguity — "final cross-campaign comparison"

Flagged explicitly (not a blocking `decision_required` — low stakes, architect's call per the task's own
instruction to flag only genuine ambiguity) because roadmap.md's row for 1.12 does not, on inspection,
describe a *distinct computation* the way every other id does:

> `1.12 | Final cross-campaign comparison | runs/point/comparison.py (any --case) | Wrap-up comparison
> once configurations were chosen across cspace + euroc, dc + dm.`

Unlike every other row, the "current file" column is "(any `--case`)" — i.e. today, 1.12 is not a fourth
branch of `comparison.py`, it is a *usage note* about re-running 1.1/1.5/1.9 once configurations are
locked in. Two readings:

- **(a) 1.12 is not a new artifact at all** — just a documentation note that 1.1/1.5/1.9 get re-run once
  per campaign wrap-up. Under this reading, no `12_...py` file should exist; roadmap.md's row 1.12
  should instead be edited to say "see 1.1/1.5/1.9, re-run after configuration selection" with no
  standalone file.
- **(b) 1.12 earns a real file because its distinguishing feature actually is "cross-campaign"** — a
  single run that reports cspace (dc), cspace (dc+dm), *and* euroc together, which none of 1.1/1.5/1.9
  alone do (each is scoped to one campaign). This is the reading taken in S46.4/S46.6 above:
  `12_final_cross_campaign_comparison.py` is a thin orchestrator that calls all three `main()`
  functions in sequence and prints a one-line banner between them — genuinely new (if trivial) behavior,
  not a duplicate of any single existing id, and it gives "click one file, see the full picture across
  both campaigns" a literal, runnable meaning.

**Recommendation: (b)**, as specified in S46.6 — it is consistent with "for each id, a separate file" and
gives 1.12 content that is not a copy-paste of 1.1, 1.5, or 1.9. If the orchestrator/user prefer (a), drop
the `12` deliverable from ticket T4 (S46.10) and edit roadmap.md's row 1.12 instead — a one-line
change, flagged here so it is not lost if that's the chosen resolution. Confirmed by the user (b) this
round — T4 proceeds as designed.

---

## S46.8 Test-file impact — none

Confirmed via repo-wide grep — only two test files import `solvers/point/`'s library modules by path
(`tests/test_fx27_port.py` lines 40–44, 360/374; `tests/test_regenerate_ideal_own.py` lines 42, 46–48),
and none of them import the old consolidated `runs/point/comparison.py`/`ideal_mass.py`/`ideal_drag.py`/
`ideal_open_airbrake.py`/`sweep.py` scripts at the module or CLI level (the only `runs/point/*` CLI
smoke-tested is `point.py`, which this round does not touch).

Since `solvers/point/` is **not moved, not split, not renamed** (S46.2), none of those existing import
lines change. Deleting the 4 old consolidated `runs/point/*.py` scripts and renaming `sweep.py` has
**zero** pytest impact — no test file needs editing as part of this round.

Full-suite run still required at the end of the ticket sequence per this project's own step discipline
(`CLAUDE.md` "Дисциплина шага") — background it, chunk if needed, per the environment traps already
documented there — as a confirmation that this expectation (0 test changes, 0 behavior change) holds,
not because any edit is anticipated.

---

## S46.9 Rejected options

- **Keep the `--case`/argument-selected consolidated scripts and just add a thin "please pick a version"
  wrapper CLI on top.** Rejected — does not satisfy "click run on *any* file," which specifically wants
  each version individually double-clickable/`python -m`-able without an extra argument; a wrapper CLI
  reintroduces exactly the indirection the user is trying to remove.
- **Introducing a new `simulations/` package, or splitting `solvers/point/` into two packages, mirroring
  `apps/sim` vs `apps/optimization`.** Raised as a `decision_required` fork in an earlier draft of this
  document; resolved directly by the user (S46.2) — "simulations" meant today's `solvers/point/` as-is,
  no new layer wanted. Recorded here so the earlier framing (visible in this document's git history/prior
  revision) is not mistaken for a live option.
- **Building id 1.13's file this round anyway, since its roadmap row exists.** Rejected per explicit task
  scope: Phase 2.29 (architecture-45) is reported in progress by another developer subagent on the
  orchestrator's own full-suite check at the time of writing; touching `data/cspace/aero/` or `rockets.py`
  risks a merge conflict with live work. Flagged as a known, deliberate follow-up (not a gap) — once
  Phase 2.29 lands, a `13_cspace_comparison_dc_dm_theory.py` (or similar, naming TBD at that time) can
  be added in a trivial follow-up ticket using this same convention.

---

## S46.10 Tickets

No import-path changes anywhere in this ticket set (S46.2/S46.8) — every ticket below imports from
`projects.fx27.solvers.point.*` and `projects.fx27.data.*` exactly as today's consolidated `runs/point/*.py`
files already do. `solvers/point/`, `data/`, `apps/**`, `runs/point/point.py`, `runs/point/
regenerate_ideal_own.py`, and `runs/point/controller.py` are all untouched by this ticket set.

### [T1] Split `comparison.py` into `01`/`05`/`09` (+ delete old file)
- **Module/boundaries:** create `projects/fx27/runs/point/01_cspace_comparison_dc.py`,
  `05_cspace_comparison_dc_dm.py`, `09_euroc_comparison_fx27_columns.py`; delete
  `projects/fx27/runs/point/comparison.py`.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true (does not overlap T2/T3's file sets; T4 depends on this ticket's output, see below)

Spec slice: S46.6's table rows for 1.1/1.5/1.9; source bodies are today's `runs/point/comparison.py`'s
`_run_cspace`/`_run_cspace_dc_dm`/`_run_euroc` functions (read that file before deleting it). Also update
`projects/fx27/_docs/roadmap.md`'s "current file" column for ids 1.1/1.5/1.9 to point at the 3 new
filenames (mechanical, same ticket).

### [T2] Split `ideal_mass.py` into `02`/`06` (+ delete old file)
- **Module/boundaries:** create `02_cspace_ideal_mass_dc.py`, `06_cspace_ideal_mass_dm.py`; delete
  `runs/point/ideal_mass.py`.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true

Spec slice: S46.6 rows 1.2/1.6. Update roadmap.md's current-file column for 1.2/1.6.

### [T3] Split `ideal_drag.py` into `03`/`07` (+ delete old file)
- **Module/boundaries:** create `03_cspace_ideal_drag_dc.py`, `07_cspace_ideal_drag_dm.py`; delete
  `runs/point/ideal_drag.py`.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true

Spec slice: S46.6 rows 1.3/1.7 (keep the `pro54_transition` AC-3 caveat text verbatim in `03`). Update
roadmap.md's current-file column for 1.3/1.7.

### [T4] Split `ideal_open_airbrake.py` (runs/) into `04`/`08`, build `12` orchestrator, rename `sweep.py` -> `10`
- **Module/boundaries:** create `04_cspace_ideal_airbrake_dc.py`, `08_cspace_ideal_airbrake_dm.py`,
  `12_final_cross_campaign_comparison.py`; delete `runs/point/ideal_open_airbrake.py`; rename
  `runs/point/sweep.py` -> `runs/point/10_euroc_sweep_feasibility.py` (content unchanged, only the
  filename and its own docstring's self-reference).
- **Assignee:** developer
- **depends_on:** [T1] (`12` imports/calls `01`/`05`/`09`'s `main()` functions, so T1 must
  land first)
- **parallel_safe:** false (depends on T1's output files existing)

Spec slice: S46.6 rows 1.4/1.8/1.10, S46.7 (1.12's contract, confirmed reading (b)). Update roadmap.md's
current-file column for 1.4/1.8/1.10/1.12.

### [T5] Full-suite verification + roadmap.md final sweep
- **Module/boundaries:** no new code; run the full test suite (chunked, background, per `CLAUDE.md`'s own
  environment-trap note) after T1–T4 land; do a final `Grep` across the repo for any remaining
  `runs.point.comparison|ideal_mass|ideal_drag|ideal_open_airbrake|sweep\b` references outside this
  document/history docs (dev/docs/*, which are historical and left as-is) to confirm nothing still points
  at a deleted file.
- **Assignee:** developer
- **depends_on:** [T1, T2, T3, T4]
- **parallel_safe:** false (final gate, by construction)

Spec slice: this whole document, S46.8 for the expected test-impact baseline (0 test changes expected).
