# Step 102 notes -- air brake as a table axis (f_b)

## Design (as built)
- `Control.airbrake_aero`: `"additive"` (default, legacy) | `"table"`. Validated in `aero.validate` (called by `assemble`): unknown value, `"table"` without `Aero.model == "table"`, or a table lacking an `f_b` column -> `ValueError`.
- Table loader: optional `f_b` column; rectangular `(f_b, M, alpha)` grid; `f_b` axis must start at 0.0 and have >= 2 values. `_AeroTable` gains `f_b` (grid) and `planes` (tuple of 2-D tables); the top-level arrays are the `f_b = 0` plane, so additive mode and all existing helpers (`uses_l_p`, validators) are unchanged. Tables without the column take the identical code path (bit-identical).
- `_at_fb(table, fb)`: linear blend of the two bracketing planes' grids, clamped at both ends; at a plane's own `f_b` (and outside the range) the plane object is returned untouched -> `f_b = 0` equals the closed table exactly. Linear interpolation makes grid-blend == coefficient-blend.
- Composition with Step 112: order is f_b blend first, then `(M, alpha)` lookup, then the Jorgensen extension on the blended table (edge values `cm_e`, `lp_e`, `x0` are those of the blended plane).
- `fb` evaluated once per RHS call in `dynamics.derivatives` (`control.airbrake_deploy_fraction`) and passed to `aero_force_body`, `aero_moment_y`, `aero.coefficients(..., fb)`. Previously evaluated once inside `aero_force_body`; count unchanged (test asserts 1 call in both modes). Direct callers of the forces may omit `fb` (computed on demand).
- In table mode `aero_force_body` skips the additive brake term and the extra axial-flow factor (the table is authoritative).
- `report.static_margin_cal` / `cm_slope_series` use the continuous-law `f_b` (new `_brake_fraction`) so the margin series shows the CP shift (Farha effect); a sampled-data run's held value is not reproduced there (documented).
- `aero.C_m` wrapper gained optional `fb` (used by the slope series).

## Deviations
- Tests are in the new file `tests/test_aero_fb.py` (not appended to `test_aero.py`/`test_forces.py`/`test_control.py`): keeps the table-writing helpers together.
- `report.py` touched (outside the ticket boundary list) -- required by the ticket's "diagnostic shows it" test item.
- `configs/rockets/_TEMPLATE_rocket.py` gained the `airbrake_aero` row (outside the boundary list, but `tests/test_template_docs.py` requires every Control field documented).
- Operational slip: a hung first test run was killed with `taskkill /IM python.exe`, which may have killed a concurrent QA pytest run; a leftover temp table `data/aero/test_fb_margin.csv` was captured by the orchestrator's WIP commit and is now deleted in the working tree (commit the deletion).

## Library docs
No external library API questions (numpy only; no Context7 lookups).
