# fx27 port -- developer progress notes

Spec: `dev/docs/architecture-38-fx27-port.md` (SS38, all sections).
Branch: `feature/fx27-port`. Decisions pre-made by the user: D-A=Option C,
D-B=both euroc scripts, location=`projects/fx27/`.

## Context7 / library lookups

None needed -- this port uses only this repo's own `apps/` API (numpy/
scipy/matplotlib stdlib usage only, no new third-party API surface).

## Checkpoints

- [x] FX27-1: cspace campaign configs (`projects/fx27/__init__.py`,
      `_paths.py`, `cspace/**`) -- done, verified: all 7 scenarios
      `assemble()` and `run_sim()` without raising.
- [x] FX27-2: euroc campaign configs (`euroc/**`) -- done, verified: 24
      runnable + 3 deferred combos, all 24 `assemble()`/`run_sim()`
      without raising (one combo, `pro75_4G/pro75-4025L1355`, produces a
      near-zero/slightly-negative apogee -- a legitimate "motor too weak,
      barely clears the rail" result per SS29.4.6, not an error; no
      scenario returned `apogee_altitude is None`).
- [x] FX27-3: generic `point/` layer -- all 7 modules written and smoke-
      tested (`flight.py`, `metrics.py`, `comparison.py`, `estimate.py`,
      `airbrake.py`, `plots.py`, `validity.py`). One real bug found and
      fixed during smoke-testing (see "Bugs found" below).
- [x] FX27-4: run scripts + README -- done. 7 entry points under
      `runs/**` plus `README.md`. All 7 smoke-tested by running them for
      real (not just imported) -- see "FX27-4/5 completion" below.
- [x] FX27-5: tests + AC-3 gate -- done. `tests/test_fx27_port.py`, 42
      tests, all passing, including AC-3 with the user-approved per-case
      tolerances (see "RESOLVED" below).
- [x] Full suite run -- `python -m pytest -q`, foreground, single call:
      **842 passed, 0 failed, 87 warnings, 855.72s.** No pin outside
      `tests/test_fx27_port.py` touched or moved.
- [x] `code-review` skill run on the full diff before handoff (see
      "code-review findings" below) -- 2 of 3 findings addressed, 1
      (pre-existing `projects/fx27/data/README.md` mislabeling) is out of
      this ticket's boundary (FX27-6, orchestrator's).

## AC-3 oracle (fx27's own hardcoded solved figures, target apogee 3000 m AGL)

| quantity | fx27 figure | measured | % error |
|---|---|---|---|
| `estimate_airframe_mass(pro54_transition)` | 4.2864 kg | 4.3840 kg | **+2.28%** |
| `estimate_cx(pro54_transition)` | 0.2351 | 0.2524 | **+7.35%** |
| `estimate_airframe_mass(pro75)` | 8.0654 kg | 8.1205 kg | **+0.68%** |
| `estimate_cx(pro75)` | 0.8304 | 0.8400 | **+1.16%** |

**3 of 4 within the 5% band; 1 of 4 (`estimate_cx(pro54_transition)`)
measures +7.35%, exceeding it.**

## RESOLVED (2026-11): user accepted the AC-3 miss as a documented caveat

The user independently re-ran `estimate_airframe_mass`/`estimate_cx` and
reproduced the exact same four numbers (4.3840 kg, 0.2524, 8.1205 kg,
0.8400) -- confirmed, not disputed -- and chose recommendation **1**
below ("accept as-is, document the miss"), operationalised as a
**per-case tolerance** in `tests/test_fx27_port.py` rather than one
blanket band for all four:

- `estimate_airframe_mass(pro54_transition)`, `estimate_airframe_mass
  (pro75)`, `estimate_cx(pro75)` -- asserted within the originally-
  specified **5%** (`test_ac3_estimate_airframe_mass_pro54_transition`,
  `test_ac3_estimate_airframe_mass_pro75`, `test_ac3_estimate_cx_pro75`).
- `estimate_cx(pro54_transition)` -- asserted within a wider, explicitly
  commented **10%** (`test_ac3_estimate_cx_pro54_transition_wider_
  tolerance`), citing this file's own diagnosis below. The test also
  asserts the measured error is STILL above the default 5% band, so a
  future reader cannot mistake "10% tolerance" for "this case got
  better" -- the band is wider because the physics genuinely differs,
  not because the number improved.

Separately, the "26 motors/23 runnable" figure in the user's own
original task prompt and in architecture-38's prose was the user's own
miscount (confirmed by the user) -- the real data (27 CSVs, which this
port was built against) is correct; no code change needed on this side.
The user will fix the prose reference in the architecture doc separately.

FX27-4 and FX27-5 proceeded after this resolution (see below).

## STOP: AC-3 measured failure -- original diagnosis (superseded by
## the RESOLVED section above, kept verbatim for the record)

Per the task's explicit instruction ("if AC-3 fails by more than 5%: stop,
do not tune anything to force a fit, report the measured numbers and your
diagnosis") -- this is that stop. **FX27-4 and FX27-5 were deliberately
not started.**

### Diagnosis: not a bug, a measured Option-C divergence larger than
### SS38.3.1's estimate, concentrated in exactly the vehicle SS38.3.1's
### own reasoning would flag as the worst case

Forward-simulated this project's Option C model at fx27's own *already-
solved* values (i.e. sanity-checking that the solver itself isn't
miscomputing anything):

| scenario @ fx27's solved value | this project's apogee | target | apogee error |
|---|---|---|---|
| `pro54_transition`, `m=4.2864 kg` | 3035.30 m | 3000 m | **+1.18%** |
| `pro54_transition`, `C_x=0.2351` | 3049.68 m | 3000 m | **+1.66%** |
| `pro75`, `m=8.0654 kg` | 3019.87 m | 3000 m | **+0.66%** |
| `pro75`, `C_x=0.8304` | 3015.84 m | 3000 m | **+0.53%** |

So the solver is correct -- at fx27's own numbers, this project's model
already lands at a *different* apogee than fx27 did, by 0.5-1.7%, before
any solving happens. SS38.3.1 predicted "~0.5%" apogee agreement and
explicitly warned that "a 0.5% apogee error near the root maps to roughly
a 1-3% error in the solved mass or C_D" -- i.e. it anticipated this
amplification and set the 5% acceptance band to absorb a 1-3x multiplier.
Measured amplification here: `pro54_transition`'s mass case is 1.18% ->
2.28% (~1.9x, inside the anticipated range); its C_x case is 1.66% ->
7.35% (~4.4x, outside it). `pro75`'s own two cases stay comfortably inside
(0.66%->0.68%, 0.53%->1.16%).

`pro54_transition` is the lightest of the two baseline airframes (5.835 kg
dry) paired with the K-class `pro54_2060K570` motor -- the highest-T/W,
fastest-burning combination in the cspace set (peak Mach 1.36 at
`C_x=0.2351`, vs `pro75`'s milder profile). This is exactly the vehicle
SS38.3.1's own reasoning (gravity-turn alpha sweep is largest, in relative
terms, for the vehicle that reaches apogee with the least horizontal
momentum preserved) would flag as the most exposed to the frozen-axis-
vs-true-point-mass divergence -- this is risk **R1** in SS38.10
("Option A's frozen-attitude error is larger than the SS38.3.1 estimate")
materialising for one specific vehicle/quantity combination, not a
uniform failure of the approach.

### What this does NOT mean

- It is not evidence of an implementation bug: the forward-simulation
  cross-check above shows the solver converges correctly to whatever
  apogee this project's own model actually produces at a given
  mass/C_x; the discrepancy is between this project's model and fx27's,
  not between the solver and this project's model.
- It is not evidence that Option C is wrong for the *other* three
  figures, which pass comfortably (and `pro75`'s own two cases have
  essentially no amplification at all).

### Recommendation for the orchestrator/user gate

Three options, not chosen here:

1. **Accept as-is, document the caveat per-scenario.** 3 of 4 pass; the
   failing one is a lightest/fastest vehicle where SS38.3.1 itself
   flagged the approximation as most exposed. Ship FX27-4/5 with the
   measured numbers printed (not hidden), and let `validity.py`'s
   per-scenario `alpha_max_deg_q_gt_1pct` carry the actual signal of how
   exposed a given run is (R9's "the diagnostic is a measured number, not
   a blanket assumption" principle already covers this case).
2. **Loosen AC-3's band for this one figure with an explicit written
   justification**, rather than silently retuning code to hit 5% --
   this is a decision for the user, not something to do unilaterally.
3. **Revisit SS38.3 (D-A) for the highest-T/W vehicles only** -- Option B
   (true point-mass RHS) was already costed at "roughly half to two-
   thirds of Step 32"; this single data point is not strong evidence that
   the cost is worth it project-wide, but it is evidence the cspace set
   has at least one vehicle where Option C is measurably weaker than
   estimated.

(Historical: at the time this diagnosis was written, no action had been
taken on any of the three options -- that stop is what the "RESOLVED"
section above closes out.)

## FX27-4/5 completion

All 7 `runs/**` entry points were run for real (not just imported) and
their output inspected:

- `cspace_point.py` -- summary, `--validity` line, 2 PNGs.
- `cspace_comparison.py` -- 7-row table, Mach-warning summary line (3/7
  exceeded 0.8), CSV + 2 PNGs.
- `cspace_ideal_mass.py` / `cspace_ideal_drag.py` -- reproduce the exact
  AC-3 numbers above, including the drag script's printed caveat line
  under `pro54_transition`'s row.
- `cspace_airbrake.py` -- all 4 ideal variants converge, `reachable=True`.
- `euroc_comparison.py` -- 24-row table, Mach-warning summary (21/24
  exceeded 0.8 -- the euroc N-class motors on light airframes are *far*
  into transonic/supersonic, a bigger caveat than cspace's), deferred
  list printed under the table (`pro75_2G/pro75-2412K1085`,
  `pro98_4G/pro98-9876M1890`, `pro98_6G/pro98-14200N3180`).
- `euroc_sweep.py` -- 24 rows, all `ok` (no fabricated static-margin
  `INFEASIBLE`, per the printed `Constraints(min_tw=0.0,
  min_margin_cal=-inf)` explanation).

`tests/test_fx27_port.py`: 42 tests, all passing (`python -m pytest
tests/test_fx27_port.py -q` -- 42 passed, 30s). Covers AC-1 (every
scenario assembles), AC-6 (`DEFERRED_MOTORS` pinned, `generate_scenarios`
exclusion verified both ways), AC-3 (the 4 oracle figures, per-case
tolerances as described above), AC-5 (airbrake convergence), and a
plot-data-series smoke test (asserts line counts/data, not pixels).

## `code-review` skill findings (run on the full diff before handoff)

Three findings; two addressed, one out of this ticket's boundary:

1. **`projects/fx27/data/README.md` mislabeled** (describes
   `projects/data/`, not this directory) -- already flagged as SS38.7.2/
   FX27-6, assigned to the orchestrator (needs a user "yes" for the git
   restore of `projects/data/README.md`). Not touched, per ticket
   boundary.
2. **`point/comparison.py::evaluate_scenarios` had no caller/test** --
   addressed: added
   `test_evaluate_scenarios_matches_the_run_many_plus_row_from_flight_
   reduction` to `tests/test_fx27_port.py`, pinning that it stays
   identical to the reduction the `runs/*` scripts hand-inline (they
   need the raw `FlightRun`s too, for plotting/validity, which is why
   they do not call `evaluate_scenarios` directly).
3. **`point/estimate.py`'s unreachable-target branch re-ran a flight
   that had already been simulated** (`apogee_at(required)` recomputed
   exactly `apogee_lo`/`apogee_hi`) -- addressed: `required`/`achieved`
   are now assigned together from the already-computed bound values,
   removing the redundant simulation. Re-verified by hand (unreachable-
   high and unreachable-low cases on `pro75`) and by the full
   `test_fx27_port.py` re-run (still 42/42 passing, including the AC-3
   tests that exercise the reachable branch).

## Bugs found (fixed before stopping)

- **`point/validity.py`, `check_validity`**: the first implementation
  passed `point_mass_flightpath`'s own *whole-flight* default grid and
  did not exclude the `V == 0` on-pad instant. Two consequences, both
  spurious (not real physics): (a) the on-pad instant's `still_air_
  residual` is genuinely undefined there (documented degenerate case,
  `theta_v = atan2(0,0) = 0`, `alpha = atan2(0,0) = 0`, leaving `residual
  = theta_rail` -- for the cspace 85 deg rail that is exactly the 1.484
  rad spuriously reported), and (b) the whole-flight grid pulls in the
  tail-first, no-recovery free-fall descent, where `alpha` legitimately
  approaches 180 deg -- not part of what fx27 (terminate_on_apogee=True)
  or this port's own D-19 ascent window ever looks at. Fixed: restrict
  `point_mass_flightpath`'s `t_grid` to `[0, apogee]` (falls back to the
  whole-flight default only for a degenerate flight with no apogee
  event), and mask out `V <= 0` samples from both `still_air_residual_max`
  and `alpha_max_deg_q_gt_1pct`. Re-verified: all 7 cspace scenarios now
  report `still_air_residual_max = 0.000e+00` (exact) and
  `alpha_max_deg_q_gt_1pct` in the physically-sane 30-45 deg range.

## Notes / deviations

- `projects/fx27/data/README.md` (mislabeled, SS38.7.2) and
  `projects/data/README.md` (missing) are OUT of my ticket boundaries
  (FX27-6 is assigned to the orchestrator, needs a user "yes" for the git
  restore). Not touched.
- euroc candidate-motor count: the architecture doc and the task prompt
  both say "26 total / 23 runnable", but the actual data (27 CSV files
  under `projects/fx27/data/motors/euroc-sweep/`, and the 27-row motor
  table in the task prompt itself) gives 27 total / 24 runnable (3
  deferred). Implemented against the real data (27/24), not the
  prose figure -- `DEFERRED_MOTORS` is still exactly the 3 named `-todo`
  motors either way, so this is a doc-prose discrepancy, not a spec
  conflict worth blocking on.
- `euroc/motors.py`'s zero-geometry recipe points every `Motor`, including
  the 3 deferred ones, at the real on-disk filename (with the `-todo`
  suffix for those 3) -- they are fully specified `Motor` objects, just
  never assembled into a runnable `Scenario` (`generate_scenarios()`
  excludes them). Supplying real data later is a CSV swap, not a code
  change.
