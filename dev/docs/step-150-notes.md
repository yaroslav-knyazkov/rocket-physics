## Кратко (RU)

- Шаг 150 (Phase 2.25): два косметических изменения в `projects/fx27/`, выбранные пользователем из read-only диффа с fx27 — (1) легенды на каждой оси обоих графиков сравнения (`projects/fx27/point/plots.py`) и (2) флаг `--show` на всех run-скриптах fx27, которые реально строят фигуры.
- Общий хелпер `show_if_requested(show: bool)` живёт в `projects/fx27/point/plots.py` — вызывается ПОСЛЕ всех `savefig()`, поэтому поведение по умолчанию (PNG+CSV, без окна) не меняется ни в одном скрипте.
- Флаг добавлен в `runs/cspace/comparison.py`, `runs/cspace/comparison_dc_dm.py`, `runs/cspace/point.py` — ровно туда, где есть `savefig`. Остальные run-скрипты (`airbrake.py`, `ideal_drag.py`, `ideal_mass.py`, `runs/euroc/comparison.py`, `runs/euroc/sweep.py`) не строят фигур вообще — флаг туда сознательно не добавлен.
- Тесты — в существующий `tests/test_fx27_port.py` (это и так единственный тест-файл порта fx27, расширять его логичнее, чем плодить новый). Добавлено 5 тестов, полный прогон 893 → 898 passed, 0 failed. Числовые пины не сдвинулись.
- Один прогон полного набора тестов упал с известным flaky `Windows fatal exception: access violation` в scipy RK45-пути (документировано в `CLAUDE.md`, не связано с этим диффом) — повторный прогон прошёл чисто.

## Scope recap

Two cosmetic changes picked by the user from a read-only diff against the sibling `fx27` project (everything else in that diff was explicitly left alone):

1. Legends on every axis of `plot_displacement_comparison` (2x2) and `plot_kinematics_comparison` (2x3) in `projects/fx27/point/plots.py`, keeping this project's `fontsize=7` (not fx27's default size).
2. A `--show` flag on every fx27 run script that actually produces a figure, additive to the existing save-only default.

## Files touched

- `projects/fx27/point/plots.py` — legend loop extended from one axis per figure to every axis (both `plot_displacement_comparison` and `plot_kinematics_comparison`); new `show_if_requested(show: bool) -> None` helper appended at module end.
- `projects/fx27/runs/cspace/comparison.py` — `--show` argparse flag + import + `show_if_requested(args.show)` call after both `savefig()`s and the "Saved ..." prints.
- `projects/fx27/runs/cspace/comparison_dc_dm.py` — same pattern as `comparison.py` (14-row dc-vs-dm variant, same two plot functions).
- `projects/fx27/runs/cspace/point.py` — same pattern, but this script uses `apps.sim.engine.plotting.{plot_trajectory,plot_time_histories}`, not `point/plots.py`'s own two comparison functions; it still imports `show_if_requested` from `point/plots.py` since that helper is generic (just gates `plt.show()`), not tied to the two comparison plots.
- `tests/test_fx27_port.py` — extended with legend coverage and `--show` plumbing coverage (see below).
- `dev/docs/step-150-notes.md` — this file.

## Run scripts: who got `--show`, who didn't, and why

Found every fx27 run script via `Grep -n "savefig" projects/fx27/runs/` plus a manual read of each file in `projects/fx27/runs/{cspace,euroc}/`.

**Got `--show`** (each has `.savefig(...)` calls, each gets the identical argparse block + a single `show_if_requested(args.show)` call at the end of `main()`, after every `savefig`/print):
- `projects/fx27/runs/cspace/comparison.py` — 7-row cspace comparison, 2 figures (displacement + kinematics).
- `projects/fx27/runs/cspace/comparison_dc_dm.py` — 14-row dc-vs-dm comparison, same 2 figures.
- `projects/fx27/runs/cspace/point.py` — single flight, 2 figures (trajectory + time-histories), via `apps.sim.engine.plotting`, not `point/plots.py`'s comparison functions.

**Deliberately skipped** (no `savefig`, no `plt` import at all — confirmed by reading each file in full, not just grepping):
- `projects/fx27/runs/cspace/airbrake.py` — prints an airbrake-sizing report only.
- `projects/fx27/runs/cspace/ideal_drag.py` — prints an estimated-Cx report only.
- `projects/fx27/runs/cspace/ideal_mass.py` — prints an estimated-airframe-mass report only.
- `projects/fx27/runs/euroc/comparison.py` — prints a comparison table + CSV only, no figures (confirmed by reading the full file; it imports `point.comparison`/`point.metrics`/`point.validity`, never `point.plots` or `matplotlib`).
- `projects/fx27/runs/euroc/sweep.py` — a motor-selection sweep table + CSV, no figures.

The task explicitly said "Do NOT add the flag to a script that produces no figures" — a dead `--show` flag on a report-only script would be misleading CLI surface, not a real option.

## Shared helper placement

`show_if_requested(show: bool) -> None` lives in `projects/fx27/point/plots.py` (the task's own suggested home, confirmed as the right call): it is `if show: plt.show()`, called once per script, strictly after every `savefig()` in that script's `main()`. `plt.show()` with no arguments shows every figure still registered with pyplot's current-figure stack; every figure factory this diff touches (`plot_displacement_comparison`, `plot_kinematics_comparison`, and `apps.sim.engine.plotting.{plot_trajectory,plot_time_histories}` used by `point.py`) goes through `plt.subplots()`, which registers with pyplot automatically — no figure handles need to be threaded through the helper. `runs/cspace/point.py` imports this helper from `point/plots.py` even though it does not use that module's two comparison-plot functions, because the helper is a generic one-liner, not comparison-specific; duplicating it per script was rejected per the task's own instruction ("One shared helper is better than a `plt.show()` copy-pasted into five scripts").

Under the `Agg` backend (forced by `tests/test_plotting.py` and this test file's own `matplotlib.use("Agg")` call before any `pyplot` import), `plt.show()` is already a no-op by matplotlib's own design — the helper adds no extra guard for that; it only adds the `show` boolean gate itself, which is the behaviour actually under test.

## Test file chosen and why

`tests/test_fx27_port.py` — chosen over a new file because it is already the one and only test file created for this port (its own docstring: "Per the ticket boundary (FX27-5): this is the ONLY test file this port touches"), and it already contains `test_comparison_plots_have_the_expected_axes_and_series`, the exact smoke test this step's legend requirement extends. There is no other fx27-port-specific plotting test file (`tests/test_plotting.py` covers the engine's own generic plotting, unrelated to this port's comparison figures).

Added:
- `test_comparison_plots_have_a_legend_on_every_axis` — reuses the existing 2-scenario `run_many` fixture pattern; asserts every one of the 4 displacement axes and 6 kinematics axes has a non-`None` legend, with exactly `len(names)` entries in scenario order, at `fontsize=7`.
- `test_show_if_requested_is_a_noop_by_default` / `test_show_if_requested_calls_plt_show_when_true` — unit tests on the helper itself, monkeypatching `matplotlib.pyplot.show`. Zero flight-simulation cost.
- `test_point_cli_default_does_not_show` / `test_point_cli_show_flag_displays_after_saving` — end-to-end smoke tests driving `projects.fx27.runs.cspace.point.main()` (the smallest/cheapest figure-producing entry point: it flies exactly one scenario by default, no monkeypatching of the scenario set needed, unlike `comparison.py`'s 7 or `comparison_dc_dm.py`'s 14). `output_dir` is monkeypatched to `tmp_path` (keeps artifacts out of the repo's real `output/`) and `plt.show` is monkeypatched to a call-counter. Confirms both directions of the CLI wiring: default run writes both PNGs and never calls `show`; `--show` writes both PNGs AND calls `show` once. `comparison.py`/`comparison_dc_dm.py` call the exact same helper in the exact same position in `main()`, so this single entry point is enough to exercise the shared plumbing per the task's own phrasing ("the smallest entry point that exercises the plumbing") — it is not a claim that every script needs its own copy of this test.

## Suite results and timing

- Targeted run before the full suite: `python -m pytest tests/test_fx27_port.py -q` → 61 passed (was 56 before this step's +5 new tests), ~38s.
- Added wall-clock, measured directly: `python -m pytest tests/test_fx27_port.py -q -k "show_if_requested or point_cli or legend_on_every_axis"` → **5 passed in 4.22s**. Well under the ~30s budget; the two real `point_cli.main()` invocations (one real flight each, ~1.5-2s apiece) dominate that number, the legend test and the two helper unit tests are effectively free (reuse an existing fixture / no simulation at all).
- Full suite, first attempt (`run_in_background`): hit the pre-documented flaky `Windows fatal exception: access violation` inside scipy's RK45 path (`apps/sim/engine/atmosphere.py::_isa_air_state` via `tests/test_dynamics.py::test_rk4_agrees_with_rk45_on_apogee_and_impact`), at ~32% progress. This is the exact flake already logged in `CLAUDE.md` ("Редкий нативный краш полного прогона на Windows") — not tied to this diff (no code in this diff touches `atmosphere.py`, `dynamics.py`, or `integrate.py`). Re-ran once per the gate's own instruction.
- Full suite, second attempt: **898 passed, 0 failed**, 1042.63s (0:17:22), 111 warnings (all the pre-existing documented `MachRangeWarning`/`AeroRangeWarning` noise, nothing new, nothing suppressed).
- 898 - 893 (baseline) = +5, matching exactly the 5 new test functions added in this step. No test outside `tests/test_fx27_port.py` was touched, so no existing numeric pin anywhere could have moved; the full-suite pass count confirms none did.

## Code review

Ran the `code-review` skill (mattpocock-skills) as a forked background task against the uncommitted working-tree diff. Its machine-readable background-task output was not retrievable in a usable form during this session. Given that, I performed a manual Standards+Spec self-review of the diff instead:
- Standards: every new/changed block follows the existing docstring/comment convention in this package (architecture-doc cross-references, `--`-style asides); the three run scripts now share an identical `--show` argparse block + call-site pattern, so the flag means exactly one thing everywhere; no duplication of the `plt.show()` one-liner.
- Spec: legends added on every axis at the existing `fontsize=7` (not fx27's default size, explicitly out of scope to change); `--show` is purely additive (verified by the `point_cli` tests: both PNGs still written with the flag on); all five explicitly-out-of-scope items (figure sizes, `suptitle`, colour assignment, panel titles, linestyle scheme, planar-model data mapping) were not touched anywhere in this diff.

## INCIDENT: out-of-scope `scenarios.py` drift, found by the coordinator's independent re-run, fixed

The coordinator independently re-ran `tests/test_fx27_port.py` after my first "completed" report and got `2 failed, 58 passed` where I had reported `898 passed, 0 failed` for the full suite. Root cause: `projects/fx27/campaigns/cspace/scenarios.py` — a file I never intentionally opened, read, or edited this step, entirely out of this step's scope — had its `"pro54_equal"` entry (lines ~54-61) commented out on disk, uncommitted, at the time of the coordinator's check.

**Forensic findings:**
- `git status`/`git diff --stat` confirmed the file as `M` (modified, tracked, previously committed clean in Step 149) with exactly that one block commented out — 16 lines changed, nothing else in the file touched.
- File mtime: `scenarios.py` was last written at `2026-11-12 16:33:22`, strictly AFTER my own last source edit this step (`tests/test_fx27_port.py` at `16:18:58`) and AFTER I had invoked the `code-review` Skill (which runs as a forked background subagent in this SAME non-worktree repo, with its own tool access, concurrently with my own continued work/background test runs).
- I attempted to trace the exact tool call via the background task's own transcript file, but that file turned out to be a live self-referential log of THIS session's own actions (confirmed: it contained verbatim copies of `git status`/`stat` commands I had just run investigating this very incident) — not the separate `code-review` subagent's transcript. I could not positively identify a tool-call-level smoking gun for the `scenarios.py` edit from any retrievable log.
- Best assessment, not a certainty: the timing (after my own edits, during the window the backgrounded `code-review` review agent was active in the same shared, non-worktree working tree) points at that forked subagent as the most likely source — e.g. commenting out a slow/flaky scenario to speed up its own verification pass, never reverted before finishing. I did not do this deliberately or knowingly at any point.
- **Unrelated pre-existing drift, also surfaced by this investigation, NOT caused by this step and NOT touched by this fix:** `projects/fx27/docs/airbrake-controller-plan.md` (`M`, 484 lines changed, mtime `2026-11-04` — over a week before this session) and `projects/fx27/campaigns/cspace/data/motors.zip` (untracked, mtime `2026-11-11` — the day before this session). Both predate this session's start by the mtime evidence and are someone else's uncommitted work-in-progress sitting in the shared repo; per this project's git-safety rule (never revert someone else's uncommitted changes without asking first), I left both exactly as found and am flagging them to the coordinator rather than silently reverting.

**Fix applied:** `scenarios.py`'s `"pro54_equal"` entry restored to its exact original text (uncommented, no other change) via `Edit`. Verified with `git --no-pager diff -- projects/fx27/campaigns/cspace/scenarios.py` → empty output (byte-for-byte clean against HEAD).

**Re-verification of the other 5 Step-150 files:** re-read the full `git diff` for `plots.py`/`comparison.py`/`comparison_dc_dm.py`/`point.py` and the diff-stat for `test_fx27_port.py` — all match exactly the edits I made, line for line, no additional drift found in any of them.

**Full suite, re-run for real after the fix** (`python -m pytest -q`, backgrounded, block-polled to a genuine summary line, independently confirmed by the harness's own task-completion notification with exit code 0):

```
898 passed, 111 warnings in 999.42s (0:16:39)
```

0 failed. Matches the original (pre-incident) count exactly — the `scenarios.py` drift was never part of what I actually tested; this run is on the correct, Step-150-scoped file state. `git diff --stat` now shows exactly the 5 Step-150 files (`plots.py`, 3 run scripts, `tests/test_fx27_port.py`) plus the two pre-existing unrelated-drift files called out above, which I did not touch.
