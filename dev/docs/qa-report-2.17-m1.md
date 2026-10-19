# QA report Phase 2.17 M1 (Steps 97, 98, 99, 100, 112)

## Кратко (RU)

- Вердикт: PASS с замечаниями. Блокеров нет, 1 major, 9 minor, 3 информационных пункта. Критерии приёмки шагов 97, 98, 99, 100, 112 выполнены.
- Целевые файлы шагов (107 тестов) и смежные модули (test_mass, thrust_curve, dynamics, control, flow, motor_selection, aero, motor_file, integrate) зелёные. Полный прогон не запускался (по условию).
- Major (QA-1): некорректная строка `# cm_convention:` (лишний текст, `=`, регистр) молча игнорируется, остаётся `code` и знак C_m не переворачивается. Нужен fail-fast.
- Minor: нет валидации `k_J`, `k_t` (k_t=0 даёт ZeroDivisionError внутри RHS), `d_exit<0`, дубликаты заголовков и NaN в таблице, дубли имён моторов и пустой список в sweep; тест `test_example_v2_flies_stable` не различает устойчивую и неустойчивую конвенцию.
- Вне M1: `tests/test_template_docs.py` красный из-за параллельного Шага 102 (`Control.airbrake_aero` не описано в шаблоне) — не дефект M1.
- Репродьюсеры: `tests/qa_phase217_m1.py` (12 xfail strict + 4 passing), запуск явно, `pytest` его не собирает.

## Scope and method

Worktree `.worktrees/merge-develop`, branch feature/sim-paper-alignment. No full suite (concurrent Step 102 edits `aero/forces/dynamics/params`). Targeted runs only. Tickets read from `dev/docs/architecture-35-paper-alignment.md` (Steps 97, 98, 99, 100, 112).

Runs:

| Run | Result |
|---|---|
| `test_analytic, test_thrust_scatter, test_aero_v2, test_report, test_aero_oob, test_scenario_sweep` | 107 passed (12.6 s) |
| `test_mass, test_thrust_curve, test_dynamics, test_control, test_flow, test_motor_selection, test_aero, test_motor_file, test_integrate` | all passed (72 + 79 incl. rerun) |
| `test_template_docs` | 1 FAILED: `_TEMPLATE_rocket ### Control: undocumented={'airbrake_aero'}` — caused by Step 102 work in progress, not M1 |
| `tests/qa_phase217_m1.py` | 4 passed, 12 xfailed (reproducers) |

Note: suite output passes while Step 102 edits are live in the same tree, so results reflect the tree at the time of the run only.

## Step 97 — safety net + B32 fixes

Acceptance: MET.

- Analytic oracles (vacuum apogee, drag-only closed form 1%, canopy terminal speed 1%) present and green. Tolerance justification in the docstring is correct.
- Mass floor (`dynamics.py` L242): `dm_dt=0` at `y[M] <= m_d`; verified `propellant_mass` clamps at 0 so a solver sliver (~1e-7 kg) is harmless. Extreme scatter flights (k_J, k_t in [0.01, 100] x [0.01, 20]) all end exactly at `m_d`, never below (min mass 2.195 = m_d).
- Chute Coriolis: legacy expression kept bit-for-bit when `earth_rotation` is off (test asserts `np.array_equal` against the explicit legacy formula); on adds Coriolis once. Correct.
- `after_apogee`: `t >= 0.1 and vz > 0`. Boundary t = 0.1 triggers (matches "not for t < 0.1").
- Re fallback `l_ref == 0 -> d_ref`; honours nonzero `l_ref`. A negative `l_ref` is not rejected (negative Re) — trivial, see QA-10.
- Test quality: adequate. `after_apogee` is only checked by a direct predicate call, not inside a pad flight (acceptable).

## Step 98 — stand thrust, mass flow, scatter

Acceptance: MET (burned mass = m_prop for k_J, k_t in {0.9, 1, 1.1}; impulse = k_J J; burnout = k_t t_b; mass_flow independent of altitude and A_e; `d_exit -> A_e`; conflict d_exit + A_e != 0 -> ValueError).

- Default path: `thrust_stand`/`mass_flow` skip the multiplication at k_J = k_t = 1. My added probe `test_mass_flow_default_matches_legacy_expression_through_derivatives` confirms `derivatives()[M] == -T_raw/(I_sp g0)` bit-for-bit over the K570 curve. Burnout event uses `thrust()` so it follows `k_t` automatically.
- Extremes (demo + K570, RK45): k_t 0.01 (burn 0.036 s) and k_t 20 (burn 72 s), k_J 0.01..100 all run; mass lands on `m_d` exactly.
- Ticket test "mass-model apogee for demo unchanged (pin)" has no dedicated numeric pin in `test_thrust_scatter.py`; relies on existing suite pins (not run in full by me). See QA-9.

Defects:

- **QA-4 (minor)** No validation of `Thrust.k_J`, `k_t`. Reproduced on the demo scenario via `assemble` + `run_sim`: `k_t = 0.0` raises `ZeroDivisionError: float division by zero` from inside the RHS (not at assemble); `k_t = -1` silently gives no thrust (and no mass flow); `k_J = 0.0` burns the propellant (mass reaches `m_d`) with zero thrust; `k_J = -1` gives negative thrust, accepted. Expected: `ValueError` at `assemble` for `k_J <= 0` or `k_t <= 0`. Repro: `tests/qa_phase217_m1.py::test_nonpositive_scatter_factors_fail_fast_at_assemble`.
- **QA-5 (minor)** `Motor.d_exit < 0` is silently squared: `d_exit=-0.05` gives `A_e = 0.0019635` (same as +0.05); `nan` gives `A_e = nan`. Expected `ValueError`. Repro: `test_negative_d_exit_is_rejected`.

## Step 99 — aero table v2

Acceptance: MET with a deviation (see QA-11). Loader accepts exactly one of `l1_m`/`l_p_m` (both and neither are errors); the arm equals `l_p - cog_position` at 3 times (tested); `standard` flips `C_m` exactly; `l_g` missing -> fail-fast; legacy `example.csv` derivative and 3-s flight pinned bit-for-bit (explicit numeric pins in the test, strict).

Loader edge matrix (probed on throw-away tables):

| Case | Result |
|---|---|
| both / neither arm column | ValueError (good) |
| `# cm_convention:` declared twice | ValueError (good) |
| `# cm_convention: Standard` | ValueError (good) |
| `# cm_convention: standard  (textbook)` | accepted, convention silently stays `code` (**QA-1**) |
| `#cm_convention=standard`, `# CM_CONVENTION: standard` | accepted, silently `code` (**QA-1**) |
| duplicate header `C_m,C_m` or `l_p_m,l_p_m` | accepted; numpy renames the 2nd to `C_m_1`, 2nd column ignored (**QA-2**) |
| `nan` / `abc` cell | accepted, loaded as NaN (**QA-3**) |
| missing `C_m` / `alpha_deg` column | raw `ValueError: no field of name C_m` (**QA-10**) |
| header only | `IndexError: index 0 is out of bounds` (**QA-10**) |
| single row table | loads |
| duplicate row | ValueError "not a rectangular grid" (good) |
| `standard` table + stable airframe | flies; `stability_check` reports stable |
| flipped declared convention | `stability_check` warns "unstable ... dC_m/dalpha < 0" (good) |

Defects:

- **QA-1 (major)** `_CM_CONVENTION_RE = ^#\s*cm_convention\s*:\s*(\S+)\s*$` only matches an exact line. Any near-miss (trailing remark, `=` separator, upper case key, `cm-convention`) is treated as an ordinary comment: the table loads as `code` and the C_m sign is NOT flipped, so a textbook-sign table (stable airframe) flies with an anti-restoring moment, with no error or warning at load. This is exactly the silent sign error D-111 was meant to avoid. Expected: any comment line containing `cm_convention` (case-insensitive) that does not match the strict form raises `ValueError` (or at minimum a warning). Repro: `test_malformed_cm_convention_line_is_not_silently_ignored` (3 parametrised variants).
- **QA-2 (minor)** Duplicate column headers are silently renamed and the later column ignored. Expected `ValueError("duplicate column")`. Repro: `test_duplicate_column_header_is_rejected`.
- **QA-3 (minor, pre-existing loader behaviour, now more exposed by v2)** NaN / non-numeric cells load as NaN and propagate to the RHS. Expected `ValueError` naming the table. Repro: `test_nan_or_non_numeric_cell_is_rejected`.
- **QA-8 (minor, test quality)** `tests/test_aero_v2.py::test_example_v2_flies_stable` asserts `max|omega| < 5`. Measured: the correct `standard` table gives 4.90; the deliberately flipped (unstable) convention gives 4.60. The test passes for both, so it does not verify "a stable airframe flies stable" (ticket acceptance). Suggest comparing the two runs or asserting on the decay of `|alpha|`/`theta` oscillation. Stability is covered only indirectly by `test_report.py` diagnostics.
- **QA-11 (info)** Ticket acceptance says flipping the convention makes the diagnostic report "negative margin warning". Implemented as a `dC_m/dalpha < 0` warning (margin is independent of the C_m sign); documented in step-99-notes. `stability_check` is a separate opt-in call, not wired into `print_run_summary`, so a user who never calls it gets no warning (see QA-1).

## Step 100 — scenario sweep, B26 thin slice

Acceptance: MET. Row fields present and in the declared order; infeasible motor (T/W < 5) flagged `tw_liftoff` and ranked last; `mach_range` and `static_margin` constraints flagged by dedicated tests; `derive_history` agrees with `endpoints` to 1e-12 and with simulated `y[M]` to 1e-9 (tight solver, documented in the test); provenance dict has model, inputs, SHA-256; old `compare_motors` tests untouched and green (`test_motor_selection` passed).

Physical sanity, `python run_motor_sweep.py --scenario demo --motors cti_k570 --target 5000`:

| Quantity | Value | Check |
|---|---|---|
| J_total / burn | 2062 N s / 3.59 s | matches the .eng record |
| T/W at liftoff | 28.6 | ~280 N per kg of launch mass (3.19 kg); plausible for a K570 |
| mass at burnout | 2.195 kg | = m_d, consistent with 0.99 kg propellant |
| v_max / M_max | 588 m/s / 1.75 | ideal dV = I_sp g ln(3.185/2.195) ~ 774 m/s minus gravity/drag: plausible |
| apogee | 5947 m | constant-C_x aero (see below) |
| rail exit speed | "-" | demo site has no rail, NaN by design |
| static margin | 5.56 cal constant | `constant` model has fixed `l1`, plausible |

`MachRangeWarning` fires (constant aero at M 1.75), status still "ok": the constraint set does not include the Mach-validity warning for Mach-independent aero models. Apogee 5947 m from a 54 mm rocket at M 1.75 with constant C_x is not credible; the warning is correct and visible.

Other probes: unknown scenario -> `KeyError` traceback (functional, unfriendly); unknown motor lists the registered ones (good); `--motors synthetic_large.csv` -> clear KeyError.

Defects:

- **QA-6 (minor)** `SweepResult.results` is keyed by motor name, so `--motors cti_k570,cti_k570` (or two motors with the same `name`) yields 2 rows but 1 flight; overlay and CSV silently duplicate. Expected: dedupe/ValueError on duplicate names. Repro: `test_sweep_duplicate_motor_names_do_not_collide`.
- **QA-7 (minor)** `--motors ,` (empty list) prints an empty table, writes empty CSV/PNG and exits 0 (matplotlib "No artists with labels" warnings). Expected: error. Repro: `test_cli_empty_motor_list_is_an_error`.
- **QA-12 (info)** The CLI default solver is the scenario's (RK45); a table-aero v2 scenario with `table_oob="clamp"` stalls RK45 after apogee (diagnosis-rk45-v2-table.md). Only an `AeroRangeWarning` is issued, there is no hang guard in the sweep. The in-tree test uses RK4; whether the sweep should default to RK4 or require `jorgensen` is the open decision recorded in the Step 112 ticket.
- Weak spots in tests (QA-9 below): `test_row_fields_present_and_ordered` J_total assertion branches on `row.motor`; infeasible-by-exception (a motor that fails `assemble`) aborts the whole sweep instead of becoming a flagged row (design choice; not specified).

## Step 112 — Jorgensen large-alpha extension

Acceptance: MET (tests 1-9 present and green; measured nfev recorded in step notes: 854 ballistic / 2726 with chute vs clamp stall; defaults bit-identical in range; clamp warning once per run; validation rules).

Probes at M = 0.5, `example_v2.csv`, `S_p=0.08`, `l_pc=0.7`:

- Exactly +-180 deg: finite, `C_x = -0.3 (= -C_A(0))`, `C_z = C_m = 0`, odd across the wrap (also tested at +-1e-4 deg).
- Zero air-relative velocity on the pad (vx = vz = 0, and +-1e-12, +-1e-300): `derivatives` finite for clamp and jorgensen. A passing probe is kept in the QA file.
- Table-edge continuity: `C_z` 0.5236 at 10 deg -> 0.659 at 12 -> 4.48 at 20 (C_N slope jumps by an order of magnitude past the table edge because `S_p/S = 35`; consistent with the formula, an input-scale effect rather than a defect, but the user should know the demo-style `S_p` makes the crossflow dominate beyond 10 deg).
- `C_m` changes sign right after the edge (+0.087 at 10 deg, -1.22 at 12 deg, -292 at 90 deg). Total moment `l1*C_z + d*C_m` stays restoring at 12 deg and becomes destabilising at 90 deg because `l_pc = 0.7 < l_g ~ 0.88`. This is the behaviour the ticket states ("if l_pc < l_g the crossflow moment destabilises").
- Ballistic descent sanity (no chute): theta stays exactly 90 deg through the whole flight (no transverse perturbation, so no moment). Reaches the ground at ~33 s.

Test-quality remarks (QA-9, minor):

- Ticket test 2 (ascent bitwise equal) was replaced by `rel=1e-5` on altitude and vz at 15 s; the justification (pad alpha noise puts early steps outside the table) is plausible and recorded in step-112-notes, but the weaker test no longer proves that the extension is inert while inside the table during an actual flight. Test 4 (coefficients bitwise inside the table) covers the coefficient level.
- `test_analytic_at_90_deg` and `test_moment_arm_correction` rebuild `eta` from `aero._ETA_LAM/_ETA_VAL`, so the digitised Hoerner/Jorgensen values themselves are not pinned (any table edit passes).
- Continuity and slope bounds are generous (400 eps, slope < 400): they detect jumps but not a 2x slope regression.
- Model caveat (info, QA-13): near +-180 deg the potential term `Z ~ -e|e|` makes the extension pull toward the tail-first attitude (the moment as printed stabilises tail-first flight, whereas a fin-stabilised body is unstable there). The step notes already list this as an unconfirmed paper sign; the effect is tiny (`cos(a/2)` factor). Reported for the user's attention, not as a defect.

## Pin / bit-identity claims

- Step 97 legacy chute expression, Step 98 default thrust/mass flow, Step 99 legacy table, Step 112 in-range coefficients: each has an explicit bitwise test; my added `derivatives()[M]` probe also passes.
- Not verified by me: whole-suite pins (full suite forbidden at the moment). The rocket template doc test failure is from Step 102, so it cannot be used as evidence either way for M1.

## Defect list

| ID | Sev | Step | Summary |
|---|---|---|---|
| QA-1 | major | 99 | malformed `# cm_convention:` line silently ignored -> C_m sign not flipped |
| QA-2 | minor | 99 | duplicate CSV column header silently renamed |
| QA-3 | minor | 99 | NaN / non-numeric cell loaded as NaN |
| QA-4 | minor | 98 | no validation of `k_J`, `k_t` (k_t = 0 -> ZeroDivisionError in RHS; k_J <= 0 accepted) |
| QA-5 | minor | 98 | negative or NaN `Motor.d_exit` accepted |
| QA-6 | minor | 100 | duplicate motor names collide in `SweepResult.results` |
| QA-7 | minor | 100 | empty `--motors` list: empty output, exit 0 |
| QA-8 | minor | 99 | `test_example_v2_flies_stable` passes for the unstable (flipped) table too (4.60 vs 4.90 vs bound 5) |
| QA-9 | minor | 98/112 | weak or tautological assertions (no demo mass-model pin for Step 98; Step 112 test 2 weakened; eta table not pinned; loose slope bounds) |
| QA-10 | minor | 99/97 | raw `no field of name ...` / `IndexError` for missing columns / header-only table; negative `l_ref` accepted |
| QA-11 | info | 99 | stability diagnostic is opt-in and keyed on the C_m slope, not the margin (ticket wording) |
| QA-12 | info | 100/112 | sweep on v2 table with default RK45 and `clamp` can stall (warning only) |
| QA-13 | info | 112 | tail-first attractor from the printed potential sign (model choice, documented) |

Out of M1 scope, for the orchestrator: `tests/test_template_docs.py` fails on `_TEMPLATE_rocket` (`Control.airbrake_aero` undocumented) — Step 102 in progress.

## Artifacts

- Reproducers: `tests/qa_phase217_m1.py` (not auto-collected; `python -m pytest tests/qa_phase217_m1.py -q` -> 4 passed, 12 xfailed). Drop `xfail` markers as defects are fixed (strict: an unexpected pass fails the run).
- Output of the sanity run: `output/motor_sweep_demo.csv`, `output/motor_sweep_demo_overlay.png` (gitignored).
