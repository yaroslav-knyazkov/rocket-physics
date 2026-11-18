# fx27 Point-Mass Analysis Version History

## Кратко (RU)

Хронологическое разложение точечно-массовой работы проекта fx27 (Phase 2.21–2.28, Steps 144–151) в таблицу версий. Каждая строка — реальная стадия разработки с привязкой к Phase/Step, документу архитектуры и коммиту. Таблица показывает, какие явления были в фокусе на каждом этапе, какие коррекции были внесены позже, и как консолидирована сегодняшняя структура. Пользовательская черновая таблица (1a–5b) расширена в реальную хронологию и скорректирована там, где фактическая история расходится с этикетками.

---

## Overview of Phases and Steps

This document traces the chronological development of the fx27 point-mass track (Phases 2.21–2.28, Steps 144–151 and beyond) through commit-identified milestones. The user's original informal labels (1a–5a) are mapped to real Phases/Steps; label 5b (airbrake behaviour/controller) belongs to a parallel orchestrator session, not this track.

---

## Version History Table

| Version | What it covers | Phase/Step | Architecture doc | Key commit(s) | Current file(s) | Corrections/later fixes |
|---------|---|---|---|---|---|---|
| **1a–1d (dc comparison + ideal mass/drag/airbrake)** | 7-row cspace constant-drag (dc) comparison: baseline + 4 ideal variants (mass/drag × 2, airbrake sizing) | Phase 2.21–2.26, Steps 144–151 | A-38, A-39, A-41, A-42 | 97bae52 (S144), eb16b0b (S148), 5be01a9 (S149), 1a3588d (S151) | `runs/point/comparison.py --case cspace`, `ideal_mass.py`, `ideal_drag.py`, `ideal_open_airbrake.py` | AC-3 caveat: `estimate_cx(pro54_transition)` +7.35% (documented, user accepted); ideal-mass/drag rows re-pointed in Step 149 from fx27 oracle to own solver |
| **2a–2d (dm variants)** | Mach-dependent (dm) variants: 3 dm rockets, 7-row comparison (dc+dm merged), ideal mass/drag/airbrake for dm | Phase 2.22–2.26, Steps 145–151 | A-40, A-42 | 38914dd (S145), 5be01a9 (S149), 1a3588d (S151) | `scenarios_dm.py`, `runs/point/comparison.py --case cspace_dc_dm`, `ideal_mass.py`/`ideal_drag.py` dm rows, `ideal_open_airbrake.py` dm rows | dm ideal-mass/drag measured in Step 149 (not fx27 oracle); dm comparison merged in Phase 2.27 |
| **3a (euroc motor sweep, dc)** | 24 runnable (config, motor) combos × 12 airframes × 27 candidate motors (3 deferred), constant-drag only | Phase 2.21–2.26, Steps 144–151 | A-38, A-39 | 97bae52 (S144; unchanged after) | `data/euroc/scenarios.py`, `runs/point/sweep.py`, `runs/point/comparison.py --case euroc` | None — dc euroc baseline unchanged throughout |
| **3b (euroc dm)** | — | **Not ported** | — (A-40: euroc dm not in sibling) | — | — | Deferred; user declined speculative euroc dm work |
| **3c (chosen-configuration comparison)** | Comparison across chosen configs (dc + dm variants, cspace + euroc) unified in one script with case selector | Phase 2.27–2.28, Steps 152–153 | A-43, A-44 | 25ee30f (S152), 804a258 (S153) | `runs/point/comparison.py --case {cspace,cspace_dc_dm,euroc}` (merged) | Merge completed in Phase 2.27; unified CLI with flag |
| **4 (airbrake sizing, static solver)** | Static airbrake-sizing solver: given vehicle + target apogee 2500 m, solve for required `Cd × Area` | Phase 2.21–2.26, Steps 144–151, 152 | A-38, A-42, A-43, A-44 | 97bae52 (S144), 25ee30f (S152, renamed), 804a258 (S153, relocated) | `solvers/point/ideal_open_airbrake.py`, `runs/point/ideal_open_airbrake.py` | Renamed Phase 2.28 to free `airbrake.py` name for controller (parallel session) |
| **5a (comparison across chosen configurations)** | Same as item 3c — unified comparison entry point with case/config selection | Phase 2.27–2.28, Steps 152–153 | A-43, A-44 | 25ee30f (S152), 804a258 (S153) | `runs/point/comparison.py` with `--case` flag | Fully consolidated in Phase 2.28 |
| **5b (airbrake behaviour, controller)** | — | **Parallel orchestrator session** (Phase 2.17, Step 146 / Task-152) | task-152, qa-report-step146 | — | `solvers/point/controller.py`, `runs/point/controller.py`, `data/cspace/airbrake_data.py` | Out of scope; separate track |

---

## Detailed Phase Breakdown

### Phase 2.21, Step 144 — Promote apogee-target solver (Architecture-39)

**What:** Generalize and promote the root-finding logic for "given parameter X, find X that hits target apogee" from project-internal tooling to a reusable public API in `apps/optimization/apogee_targeting/solve.py`.

**Scope:** `estimate_airframe_mass`, `estimate_cx`, `solve_for_target_apogee` (the generic solver).

**Why:** fx27 port needs to replicate fx27's own `mass_estimation.estimate_mass` and `drag_estimation.estimate_drag` without depending on rocketpy. Only fx27 had a brentq-based root-finder; rocket-physics' `apps/optimization/` had grid sweeps and airbrake solvers but no generic scalar apogee-to-parameter root finder.

**Current location:** `apps/optimization/apogee_targeting/solve.py` (public functions), re-exported via `projects/fx27/solvers/point/estimate.py`.

---

### Phase 2.22, Step 145 — Campaigns reorg + dm drag (Architecture-40)

**What:** Two independent changes:
  - **Part A:** Reorganize `cspace/` + `euroc/` into `campaigns/cspace/` + `campaigns/euroc/` (approved user layout).
  - **Part B:** Port Mach-dependent ("dm") aero tables from sibling repo: 3 new `Rocket` variants with `aero.model="table"`, plus 4 ideal-dm variants.

**Coverage:** Items 2a–2d (dm variants of cspace comparison, mass/drag, airbrake).

**Key technical decision:** Mach-dependent drag curve (holistic `C_A(M)` from sibling repo) becomes `Aero.cx_scale` multiplier applied after table dispatch. No changes to `apps/sim/engine/aero.py`; the `"table"` model and `cx_scale` hook already existed (Step 105).

**Data files created:**
  - `campaigns/cspace/data/aero/pro54-equal-drag.csv`, `pro54-transition-drag.csv`, `pro75-drag.csv` (3 Mach-dependent `C_A(M)` tables, generated once, committed as static assets).
  - `campaigns/cspace/scenarios_dm.py` (new dict, 7 rows, mirrors `scenarios.py` but with `*_dm` rockets).

**Current structure:** Post Phase 2.28 reorganization, these live under `projects/fx27/data/cspace/aero/` and `data/cspace/`.

---

### Phase 2.23, Step 148 — Idealized regenerate script (Architecture-41)

**What:** Create infrastructure for this project to solve and store its **own** idealized-rocket values (mass/drag for target 3000 m AGL), computed via `estimate_airframe_mass` / `estimate_cx`, decoupled from fx27's hardcoded oracle values.

**Scope:** New module `rockets_ideal_own.py` (8 constants: 4 dc, 4 dm), regenerate script `generate_rockets_ideal_own.py` (one-off, not imported at runtime).

**Why:** fx27's oracle (`rockets_ideal.py`) is immutable (AC-3 test boundary); dm "ideal" values in `rockets_dm.py` were fx27-ported arithmetic, not this project's solver output. Neither represented this project's own capability. Architecture-39's public solvers now enable building a self-generated ideal-rocket file.

**Guardrail:** New files do not touch the oracle files at all; script can only write to `rockets_ideal_own.py` by hardcoded path.

**Later refactored (Step 151):** These 8 values migrate into `rockets_ideal.py` Section B1; the separate files are deleted.

---

### Phase 2.24, Step 149 — Re-point ideal rows (Addendum to 41)

**What:** Update `scenarios.py` and `scenarios_dm.py` to use this project's own ideal-rocket values (from Step 148) instead of fx27's oracle.

**Scope:** 4 dc ideal rows + 4 dm ideal rows, each re-pointed to `rockets_ideal_own.PRO*_IDEAL_OWN_*` names.

**Verification:** Measured that all 8 scenarios (dc and dm) now hit target 3000 m within tolerance.

**Later refactored:** Step 151 consolidates `rockets_ideal.py` to hold both Section A (oracle, immutable) and Section B (own solve), eliminating the separate `rockets_ideal_own.py` file.

---

### Phase 2.25, Step 150 — Plot cosmetics

**What:** Small UI improvements: legends on every axis of displacement/kinematics comparison plots, plus a `--show` CLI flag on cspace scripts that produce figures.

**Coverage:** Cosmetic only; does not affect version/functionality of the analysis itself.

**Current structure:** `projects/fx27/solvers/point/plots.py` (helper function), integrated into run scripts.

---

### Phase 2.26, Step 151 — Rockets_ideal consolidation (Architecture-42)

**What:** Merge `rockets_ideal.py` (Section A: oracle) + `rockets_ideal_own.py` (Section B1: own solve) + tail of `rockets_dm.py` (Section B2: fx27-measured dm deltas) into one file `rockets_ideal.py` with clearly marked sections.

**Scope:**
  - Section A: 4 fx27 oracle constants, byte-for-byte untouched, test-pinned (AC-3).
  - Section B1: 8 own-solver constants (migrated from `rockets_ideal_own.py`).
  - Section B2: 4 fx27-measured dm figures (migrated from tail of `rockets_dm.py`), explicitly marked NOT oracle.

**Implementation details:**
  - New public function `estimate_cx_scale` added to `apps/optimization/apogee_targeting/solve.py`.
  - Rename script: `generate_rockets_ideal_own.py` → `regenerate_ideal_own.py`.
  - Test file rename/retarget: `tests/test_rockets_ideal_own.py` → `tests/test_regenerate_ideal_own.py`.
  - Extend output scripts: `ideal_mass.py`/`ideal_drag.py`/`ideal_open_airbrake.py` gain dm rows with "NOT an oracle" labels.

**Result:** 899 passed tests (baseline 898 + 1 new test for `estimate_cx_scale`); AC-3 boundary verified byte-for-byte.

**Correction found and fixed:** `ideal_drag.py` for `pro54_transition` shows +7.35% error vs. fx27 — not a Step 151 bug, but Step 151's output clarified that this is a known, documented caveat (measured in Step 149, user accepted per architecture-38 Option C reasoning).

---

### Phase 2.27 — Restructure solvers/point + runs/point (Architecture-43)

**What:** Reorganize directory layout from "one folder per competition" (`runs/cspace/`, `runs/euroc/`) to "one file per analysis type" (`runs/point/`), and move the shared library from `point/` to `solvers/point/`.

**Scope:**
  - `projects/fx27/point/` → `projects/fx27/solvers/point/` (library, 8 files unchanged in content).
  - `projects/fx27/runs/{cspace,euroc}/*.py` → `projects/fx27/runs/point/*.py` (run scripts, all imports updated).
  - Merge `runs/cspace/comparison.py` + `comparison_dc_dm.py` + `euroc/comparison.py` into one `runs/point/comparison.py` with `--case {cspace,cspace_dc_dm,euroc}` selector.

**Result:** One unified interface for all analysis types (comparison, sweep, ideal mass, ideal drag, airbrake), case-selected by CLI flag.

**Current file:** `runs/point/comparison.py --case cspace/cspace_dc_dm/euroc`.

---

### Phase 2.28 — Campaigns → data rename (Architecture-44)

**What:** Final structural cleanup:
  - Rename `projects/fx27/campaigns/` → `projects/fx27/data/`.
  - Flatten nested `data/` directories: `cspace/data/aero/` → `cspace/aero/`, `cspace/data/motors/` → `cspace/motors/`, etc.
  - Merge `campaigns/cspace/rockets.py` + `rockets_dm.py` into one `rockets.py` file (both dc and dm variants in one place).
  - Move regenerate script `regenerate_ideal_own.py` from `data/cspace/` to `runs/point/` (data files stay in `data/`, tools go in `runs/`).
  - Rename `solvers/point/airbrake.py` → `solvers/point/ideal_open_airbrake.py` (and same for `runs/point/`) to free the name `airbrake.py` for future closed-loop controller (parallel session, out of scope here).

**Coordination with parallel session:** Another orchestrator session was building closed-loop controller files (`solvers/point/controller.py`, `runs/point/controller.py`, `data/cspace/airbrake_data.py`) in parallel. This reorg incorporates those files' paths into the unified `data/` structure.

**Result:** Fully consolidated, flattened structure with clear separation: `data/` = inputs (rockets, scenarios, motors, aero tables, airbrake hardware specs); `solvers/point/` = generic solver library; `runs/point/` = entry-point scripts.

---

### Phase 2.29 — Theory drag port (Architecture-45)

**What:** Port MATLAB scripts provided by user (theoretical Mach-dependent drag using Niskanen thesis + OpenRocket method) into `projects/fx27/data/cspace/aero/drag_theory.py` and generate side-by-side CSV `pro54-transition-drag-theory.csv` for validation against existing measured/ported dm tables.

**Scope (cut for now):** Only `PRO54_TRANSITION_DM` geometry implemented; `PRO54_EQUAL_DM` and `PRO75_DM` geometries deferred (user: "implement for 1 configuration for now").

**Current structure:** `projects/fx27/data/utils/aero/drag_theory.py` (theory module, moved from `data/cspace/aero/` in Step 157 -- campaign-agnostic), `data/cspace/aero/generate_theory_drag_tables.py` (one-off generator, stays cspace-specific), output CSV `pro54-transition-drag-theory.csv`.

**Key findings:** Theory curve and existing ported dm table diverge; no decision yet on replacement vs. side-by-side. See architecture-45 §5 (CSV replacement strategy decision pending user review).

---

## Structural Consolidation: Before and After

### Before (Phases 2.21–2.26, Steps 144–151)

```
projects/fx27/
  _paths.py
  campaigns/              (location: config data, pre-Phase-2.28 name)
    cspace/               (3 rockets: dc and dm variants)
    euroc/                (12 configs)
  point/                  (library code: flight sim, metrics, plots, solvers)
  runs/
    cspace/               (6 entry points: point, comparison, comparison_dc_dm, etc.)
    euroc/                (2 entry points: comparison, sweep)
```

### After (Phases 2.27–2.28)

```
projects/fx27/
  _paths.py
  data/                   (renamed from campaigns/, flattened aero/motors nesting)
    cspace/
      rockets.py          (merged: dc + dm, both variants)
      scenarios.py, scenarios_dm.py
      aero/               (flattened from data/aero/)
        pro54-*.csv, pro75-*.csv (3 Mach-dependent tables + 1 theory table)
      motors/             (flattened from data/motors/)
      airbrake_data.py    (new, parallel-session addition)
    euroc/
  solvers/point/          (moved from point/)
  runs/point/             (consolidated from runs/cspace/ + runs/euroc/)
    comparison.py --case cspace/cspace_dc_dm/euroc  (merged, one file)
    sweep.py, ideal_mass.py, ideal_drag.py, ideal_open_airbrake.py, controller.py, point.py
    regenerate_ideal_own.py  (relocated from data/cspace/)
```

---

## Key Corrections and Later Fixes

### AC-3 Caveat: `estimate_cx(pro54_transition)` +7.35%

**Found in:** Step 149 measurement against fx27 oracle.

**Details:** This project's `estimate_cx` returns 0.2524 for `pro54_transition`; fx27 returns 0.2351. Difference: +7.35%.

**Root cause (not a bug):** This project's Option C model (frozen attitude, force along body axis) differs from fx27's true point-mass model (force along velocity vector) by ~0.5–1.7% in apogee. For the lightest, highest-T/W vehicle (`pro54_transition`), the solver's root-finding for `C_x` amplifies this ~4.4× due to sensitivity. Result is within the ~5% acceptance threshold for Option C (see architecture-38 SS38.3.1).

**Status:** User accepted as a documented caveat (2026-11). `tests/test_fx27_port.py` encodes wider tolerance for this one case.

**Documentation:** `projects/fx27/README.md` §"The acceptance oracle (AC-3) and its one documented caveat"; `dev/docs/fx27-port-progress-notes.md` STOP: AC-3 measured failure (full diagnosis).

### Ideal-Mass/Drag Re-pointing (Step 149)

**What changed:** `scenarios.py` and `scenarios_dm.py` ideal rows were re-pointed from fx27's oracle (`rockets_ideal.py`) to this project's own solver output (`rockets_ideal_own.py`).

**Why:** fx27's oracle is immutable (AC-3); but once this project has its own apogee-targeting solver (Step 144), the ideal rows should float with this project's own physics and baseline rockets, not anchor to fx27's figures.

**Verification:** All 8 ideal rows measured to hit target 3000 m within ±1.0 m tolerance; max error 0.078 m across all 8.

### Airbrake Sizing Rename (Phase 2.28)

**Before:** `solvers/point/airbrake.py` (static Cd×A solver), `runs/point/airbrake.py` (entry point).

**After:** Renamed to `ideal_open_airbrake.py` in both locations to free the name `airbrake.py` for future closed-loop controller logic (parallel orchestrator session).

**Impact:** User-facing CLI remains `python -m projects.fx27.runs.point.ideal_open_airbrake` (similar to all other tool names like `ideal_mass.py`/`ideal_drag.py`).

### DM Rows: "NOT an oracle" Labels (Steps 150–151)

**What:** dm ideal-mass/drag/airbrake rows extended in Phase 2.26, explicitly labeled "NOT an oracle" to distinguish from dc rows' fx27-reference framing.

**Why:** dm figures were either measured in this project (ideal mass/drag) or carried forward from fx27's dm-curve measured-delta (not a solved target like dc). No dm target-apogee oracle exists; dm rows are informational, not pinned.

**Visible in:** `ideal_mass.py` and `ideal_drag.py` output lines for `*_dm` cases show "(this project's own last regen=X, drift ±Y%)" and "[NOT an oracle -- SS40.8: ...], not fx27's dc-row framing "error vs fx27 solved=X".

---

## End of Point-Mass Track; Controller Track Begins

The point-mass analysis work documented above spans Phases 2.21–2.28 (Steps 144–151, plus the Phase 2.27/2.28 reorganizations).

**Item 5b (airbrake behaviour, closed-loop controller)** is **not part of this track**. It belongs to a parallel orchestrator session:
  - **Phase 2.17, Step 146:** Controller integration harness (`apps/control/flight_software/harness.py` + tests).
  - **Phase 2.17, Task-152 (Step 152):** Rung-1 closed-loop demo (`solvers/point/controller.py` + `runs/point/controller.py`).

Those live in a different phase number (2.17 vs. 2.21+) and involve the control/flight-software stack, not point-mass analysis. The parallel session coordinates with the point-mass track only on shared file locations (e.g., renaming `airbrake.py` → `ideal_open_airbrake.py` to free the namespace, and placing `airbrake_data.py` under `data/cspace/` following the unified directory structure established by Phase 2.28).

---

## Current Consolidated Structure: Snapshots and File Mapping

### Today's Unified `runs/point/comparison.py`

Covers all versions 1a, 1d, 2a, 2d, 3a, 3c via one script with case selection:

```bash
python -m projects.fx27.runs.point.comparison --case cspace
       # → 7-row dc cspace (items 1a–1d, excluding 1b/1c which are ideal-only)

python -m projects.fx27.runs.point.comparison --case cspace_dc_dm  
       # → 14-row dc+dm cspace (items 1a–2d)

python -m projects.fx27.runs.point.comparison --case euroc
       # → 24-row euroc dc constant-drag (item 3a)
```

Same file, different output based on `--case` flag. Plots and CSV both produced.

### Today's Specialized Entry Points

| Analysis type | File | Covers |
|---|---|---|
| Ideal mass (dc + dm) | `runs/point/ideal_mass.py` | Items 1b, 2b |
| Ideal drag (dc + dm) | `runs/point/ideal_drag.py` | Items 1c, 2c |
| Ideal airbrake sizing (dc + dm) | `runs/point/ideal_open_airbrake.py` | Items 1d, 2d |
| Motor sweep | `runs/point/sweep.py` | Item 3a (euroc only) |
| Single flight | `runs/point/point.py` | Diagnostic (not in user outline) |

### Structural Question for Orchestrator

**Note for future work:** The user's initial outline suggests discrete "versions" (1a, 1b, 1c…) that might map to independent, runnable snapshots at specific commits. Today's structure is fully consolidated — one `comparison.py` with case selection, one ideal-mass/drag/airbrake script per type with internal `SCENARIOS`/`SCENARIOS_DM` dicts covering all variants.

Whether to introduce per-version snapshot files (e.g., `v1a_cspace_dc_comparison.py` frozen at a point in git history, `v2a_cspace_dm_comparison.py` at another) is a **separate structural decision not in scope for this document**. This version history documents *what was built and when*; the choice of how to expose historical snapshots is orthogonal and pending user/orchestrator guidance.

