## Кратко (RU)

- Шаг 99 (Фаза 2.17): аэро-таблица v2 — станция ЦД от носа `l_p_m` вместо плеча `l1_m`, заголовок `# cm_convention: standard|code`.
- Плечо = `l_p - l_g(t)`; `l_g(t)` берётся из `mass.cog_position` (модель масс включена) или из `Lengths.l_g`.
- Знак `C_m` кода не менялся (D-111 c): `standard` инвертируется при загрузке, по умолчанию `code`.
- Плечо тяги `aB` не трогали: для конфигов с `l_p` требуется `misalign_deg == 0` (fail-fast в `aero.validate`).
- Старые таблицы и полёты бит-в-бит (пины в `tests/test_aero_v2.py`); `example.csv` не изменён, добавлен `example_v2.csv`.

# Step 99 notes

Context7 not needed (no library API questions).

## Design
- `sim/aero.py`: loader accepts exactly one of `l1_m` / `l_p_m` (both/neither -> ValueError); `# cm_convention:` header parsed (default `code`; `standard` negates `C_m` at load; unknown -> ValueError). `_AeroTable.l1` is None for v2 tables, new `l_p` field.
- Models stay 3-arg (`(alpha, M, p)`; an existing test monkeypatches `_AERO_MODELS`). A CP station travels through `AeroCoeffs.l1` as the station; `coefficients()` (has `y`) converts it to the arm via `_resolve_arm` -> `l_p - cg_station(y, p)`. Legacy: pass-through (same object, bit-identical).
- `cop_l1` wrapper has no state: for station configs it uses launch mass CoG.
- Constant/linearized models: new `Aero.l_p` (0.0 = off) and `Aero.cm_convention` ("code" default). For tables the header governs; `Aero.cm_convention` is NOT applied to a table.
- `Lengths.l_g` (CoG station, mass model off). `cg_station` fail-fast if `<= 0`.
- `aero.validate(p)` is called in `configs.schema.assemble` (no-op for legacy): convention known, `l_g` present when needed, `misalign_deg == 0` for station configs.

## Thrust-arm choice (ticket)
Kept the smaller change: `aB = -(l1 + l2)` unchanged; for station configs the on-axis thrust moment is zero, so `Lengths.misalign_deg` must be 0 — enforced fail-fast in `aero.validate` (stronger than "documented"). Deriving the thrust station from `Sections.L_total` was not done: `Params` carries no `Sections`. `sim/dynamics.py` therefore needed no edit (it already passes `y` to `aero.coefficients`).

## Diagnostics (`sim/report.py`)
- `static_margin_cal(result, p, t_grid=None) -> (t, margin_cal)`, `cm_slope_series`, `stability_check` (UserWarning "unstable..." for negative margin or negative dC_m/dalpha in the code convention; returns dict). The margin alone is independent of the C_m sign, so "flipped convention -> instability" is detected through the C_m slope check.
- Not wired into `print_run_summary` (would change printed output).

## Deviations
- Tests for the aero part live in the new `tests/test_aero_v2.py` (not appended to `tests/test_aero.py`, which is CRLF); `tests/test_report.py` new as specified.
- Template docs (`configs/rockets/_TEMPLATE_rocket.py`) updated incl. docstring tables (`test_template_docs` requires every field).
- `example_v2.csv`: example.csv numbers, `l_p_m = l1_m + 0.9`, `cm_convention: standard` (so C_m is flipped to a restoring slope; example.csv itself unchanged, B31 stays open).
