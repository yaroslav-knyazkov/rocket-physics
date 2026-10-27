# Step 108 — baro sensor channel + real alpha-beta estimator

## Кратко (RU)

Тикет закрывает хвост Milestone M3's сенсорной цепочки, оставленный Step 107 заглушкой
(`controllers/estimator.py`): добавляет реальный баро-канал (`sim/sensors.py`, новая группа
`Sensors` в `sim/params.py`) и настоящий альфа-бета (constant-velocity) фильтр в
`controllers/estimator.py`, выбираемый новым полем `Control.estimator_model` (default `"stub"` —
старое поведение Step 107 бит-в-бит; `"alpha_beta"` — opt-in). Баро "труба": истинное давление
из уже существующего `sim.atmosphere.air_state` → НОВАЯ публичная функция-инверсия
`atmosphere.isa_pressure_altitude` (чистый алгебраический обратный ход того же `_LAYERS`-профиля,
`_isa_air_state` НЕ трогается) → первый порядок лага (замкнутая форма, тот же стиль, что и
`_ramp` для актюатора) → гауссов шум (`np.random.default_rng([seed, k])`, тот же
счётчик-based паттерн, что уже описан в архитектуре §35.4.4) → квантование. Все четыре поля
`Sensors` по умолчанию `0.0`/`0` → канал бит-в-бит воспроизводит истинную AGL-высоту при
`atmosphere.model == "isa"` (default) — "exact inverse", как того требует приёмочный пункт
Step 108 в архитектурном документе.

**Ключевые решения архитектора (инженерные, HOW, не вынесены на пользователя):**
- `estimator.step` сохраняет СТАРУЮ 3-позиционную сигнатуру и поведение бит-в-бит под
  `model="stub"` (default) — новый альфа-бета путь требует `p` (для гейнов), добавлен как
  keyword-only `model=`/`p=` с безопасными default'ами; старые прямые вызовы
  (`tests/test_controllers.py`) и `laws.py`'s старый call site не меняют результат без явного
  opt-in через `Control.estimator_model`.
- Решение "default input законов" (`proportional_drag`/`pi_apogee`): estimator_model остаётся
  `"stub"` по умолчанию — альфа-бета не становится новым дефолтом (см. §108.8.1 почему).
- `sim/integrate.py` НЕ получает eager-guard для `estimator_model` (в отличие от
  `airbrake_model`/`actuator.model`) — `controllers/__init__.py`'s собственный docstring прямо
  запрещает `sim/` импортировать `controllers/`; поэтому валидация `estimator_model` остаётся
  ленивой (`ValueError` внутри `estimator.step` при первом вызове) — осознанная асимметрия,
  см. §108.8.2.
- Новая публичная функция `sim/atmosphere.py::isa_pressure_altitude` — единственное добавление
  в этот файл (чистая, алгебраическая инверсия того же `_LAYERS`), `_isa_air_state` (пин-
  критичная) не тронута ни байтом; инверсия дублирует (не переиспользует) крошечный кусок
  форвард-математики для расчёта clamp-границ, чтобы не трогать пинованную функцию (тот же
  принцип "дублировать, не рефакторить", что task-104/107 уже применяли).
- Гейны `estimator_alpha=0.5`/`estimator_beta≈0.1667` — placeholder (Benedict-Bordner
  "critically damped" соотношение при alpha=0.5), НЕ выверено через Context7/реальные данные
  датчика (инструмент Context7 в этой сессии недоступен — раскрыто явно, не угадано тихо);
  требуют повторной настройки, когда придут реальные параметры барометра (§35.8 пункт 10).
- Шум/лаг/квантование применяются в ПРОСТРАНСТВЕ ВЫСОТЫ (после инверсии давления), не в
  пространстве давления — совпадает с тем, как сам архитектурный документ называет поле
  (`baro_sigma_m`, метры, не Па) в своём acceptance-пункте для Step 108.

---

## Table of contents

- §108.1 Scope and non-goals
- §108.2 Ground truth recap (verified against the code, not assumed)
- §108.3 API shape — decisions and rationale
  - §108.3.1 `sim/atmosphere.py` — new public pressure-altitude inverse
  - §108.3.2 `sim/params.py` — new `Sensors` group; `Control` new fields
  - §108.3.3 `sim/sensors.py` — the baro channel (new module)
  - §108.3.4 `sim/control.py` — exact before/after (wiring)
  - §108.3.5 `controllers/estimator.py` — the real alpha-beta filter
  - §108.3.6 `controllers/laws.py` — one-line wiring change
  - §108.3.7 `configs/schema.py` — `Rocket.sensors` + `assemble()`
- §108.4 Config template docs — exact before/after
- §108.5 Pin safety — grep commands + findings
- §108.6 Test plan
- §108.7 Test-impact table
- §108.8 Open design decisions / flags for the orchestrator
- §108.9 Definition of done

---

## §108.1 Scope and non-goals

**In scope:**
- `sim/atmosphere.py`: one new public function, `isa_pressure_altitude(p_Pa) -> float` (the
  algebraic inverse of `_isa_air_state`'s pressure column), plus two small new module-level
  constants for its own clamp bounds. `_isa_air_state` and every existing function/constant:
  **zero diff**.
- `sim/params.py`: new `Sensors` dataclass group (`baro_sigma_m`, `baro_tau_s`,
  `baro_resolution_m`, `baro_seed`); `Params.sensors` field; three new `Control` fields
  (`estimator_model`, `estimator_alpha`, `estimator_beta`).
- `sim/sensors.py` (**new module**): `SensorState` (NamedTuple), `measure(t, y, p, prev) ->
  (Measurement, SensorState)` — the real baro channel: ISA pressure-altitude inversion, then
  first-order lag, then noise, then quantisation, in that order.
- `sim/control.py`: `sample_airbrake`'s sampled-law branch — replace the one
  `_ideal_measurement(t, y, p)` call with `sensors.measure(t, y, p, prev_sens_state)`; thread
  `sens_state` through `SampledLawHold.sens_state` (field already present since Step 107, default
  `None`, no shape change); delete `_ideal_measurement` (dead code once this lands — Step 107's
  own hand-off note, §107.12 item 1, explicitly allows either deleting it or keeping it, and no
  Step 107 test calls it directly).
- `controllers/estimator.py`: add the real alpha-beta filter as a SECOND, explicitly selectable
  code path (`_step_alpha_beta`, `AlphaBetaState`), dispatched from the existing public `step(...)`
  via a new keyword-only `model=` (default `"stub"`, preserving the exact Step 107 behaviour and
  call shape for every existing 3-positional-arg caller).
- `controllers/laws.py`: one-line change at each of the two existing `estimator.step(...)` call
  sites (`proportional_drag`, `pi_apogee`) — thread `model=c.estimator_model, p=p` through, both
  inert at the `"stub"` default.
- `configs/schema.py`: `Rocket.sensors: Sensors` field; `assemble()`'s `Params(...)` call gains
  one `sensors=sc.rocket.sensors` keyword (required by the existing AST-pinned keyword-set test,
  §108.5).
- `configs/rockets/_TEMPLATE_rocket.py`: new `### Sensors` table (mandatory — the existing
  `test_tables_cover_every_field` test requires one for every nested dataclass group `Rocket`
  holds, §108.4); three new `### Control` rows; a new fully-commented `sensors=Sensors(...)` block
  in the constructor body (same style as the existing commented-out `sections=Sections(...)`
  block — no literal "model" switch field to keep active, so the whole group is shown commented).
- `tests/test_sensors.py` (**new file**): the baro channel's own unit tests.
- `tests/test_controllers.py`: new section for the alpha-beta filter; **zero diff** to the existing
  stub tests (they call `estimator.step(t, h, prev)` with exactly 3 positional args — see
  §108.2 — so they keep exercising `model="stub"`'s default path, bit-for-bit).
- `tests/test_control.py`: new section for `sensors.measure` wired through `sample_airbrake`
  (the registered-law dispatch branch); existing sections in this file untouched.

**Out of scope / explicitly NOT this ticket's job:**
- **IMU channel / `Measurement.a_imu`** — D-115 took option (b) (baro + alpha-beta only); `a_imu`
  stays `None` forever in this ticket, exactly as Step 107 left it.
- **Kalman filter / `rho_hat` from ISA-at-`h_hat`** — Step 107's own §107.12 item 3 left this as a
  later upgrade contingent on a pure `isa_density(h_msl)` helper; not needed here, not attempted.
- **`estimator_model` becoming the new default for `proportional_drag`/`pi_apogee`** — stays
  `"stub"` by default; see §108.8.1 for the reasoning (this is the one call in this ticket closest
  to a real fork, flagged there rather than decided silently).
- **An eager `run_sim`-entry validation guard for `estimator_model`** (unlike
  `airbrake_model`/`actuator.model`) — layering (`sim/` must not import `controllers/`) rules it
  out; see §108.8.2.
- **Refactoring `_isa_air_state` to share code with the new inverse** — deliberately duplicated
  instead (§108.3.1); the pinned forward function keeps zero diff.
- **Step 109's closed-loop harness** — this ticket only wires the channel + filter; running them
  against the full nonlinear sim with dispersions is Step 109's job (depends_on this ticket).

## §108.2 Ground truth recap (verified against the code, not assumed)

- `controllers/estimator.py` (36 lines) is EXACTLY the stub quoted in the task brief: `EstimatorState(t_prev, h_prev)`,
  `step(t, h_baro, prev) -> (h_hat, v_hat, new_state)`, backward difference, `v_hat=0.0` on the
  first call (`prev is None or prev.t_prev is None`). Its own docstring (lines 1-15) already names
  this exact hand-off: "Step 108 replacing this module's body entirely ... cannot break a law that
  only ever treats `EstimatorState` as opaque state threaded back in next tick" — confirmed:
  `laws.py` never reaches into `EstimatorState`'s fields, only threads `prev.est` back.
- `controllers/laws.py` (95 lines): `proportional_drag`/`pi_apogee` both call
  `estimator.step(t_k, meas.h_baro, prev.est)` as their ONLY use of `meas` — `meas.a_imu` is never
  read. `_k(c, f_b)` reads `c.onboard_rho0` (nominal constant, not ISA-at-`h_hat`, per §107.3.3).
- `sim/control.py` (lines 275-542, confirmed by direct read): `sample_airbrake`'s sampled-law
  branch (lines 293-304) does exactly:
  ```python
  prev_actuator_hold, prev_ctrl_state = (
      (prev.actuator_hold, prev.ctrl_state) if isinstance(prev, SampledLawHold) else (prev, None)
  )
  if _in_coast_window(t, y, p):
      meas = _ideal_measurement(t, y, p)  # Step 108 replaces this one call (SS107.3.2/SS107.12)
      cmd, ctrl_state = _SAMPLED_LAWS[name](t, meas, p, prev_ctrl_state)
  else:
      cmd, ctrl_state = 0.0, prev_ctrl_state  # outside the window: command 0, state frozen
  actuator_hold = _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev_actuator_hold)
  return SampledLawHold(actuator_hold=actuator_hold, ctrl_state=ctrl_state)
  ```
  `SampledLawHold` (line 507-521) already carries `sens_state: Any = None` — present, unused,
  exactly as Step 107 left it for this ticket.
  `_ideal_measurement` (line 485-504): `return Measurement(h_baro=gravity.altitude_agl(y, p))` —
  reads `gravity.altitude_agl`, never `atmosphere.py`.
  `Measurement` (line 476-482): `h_baro: float`, `a_imu: Optional[float] = None`.
- `sim/atmosphere.py`: `air_state(t, y, p) -> AirState` (line 271) dispatches on
  `p.atmosphere.model` ("isa" default, "sounding", "field") and returns `AirState(rho, p, T, a, mu)`
  — all five from one consistent `(T, p)` pair. `_isa_air_state` (line 87-135) is the ONLY tier
  with a closed-form, invertible `h -> pressure` map: a 7-layer piecewise table (`_LAYERS`, line
  76-84), geopotential altitude `H = R_isa*h_msl/(R_isa+h_msl)` (line 106), then per-layer either a
  power law (`L != 0`) or an exponential (`L == 0`) for pressure. Crucially, **pressure is computed
  from the lapse-rate `T` BEFORE `dT_K` is added** (line 114-129): `dT_K` (Step 105's dispersion
  hook) only perturbs `T` (hence `rho`/`a`/`mu`) AFTER `press` is already fixed — so in the "isa"
  tier, pressure is a pure function of `h_msl` alone, independent of `dT_K`. This means the baro
  channel's "pressure-altitude" reading recovers the TRUE altitude exactly under the "isa" tier
  REGARDLESS of `dT_K` — a property inherited from the existing atmosphere model, not introduced
  by this ticket (worth knowing, not a bug to fix here).
  `_H_MSL_MIN = -5000.0`, `_H_MSL_MAX = 86000.0` (B13 clamp, line 61-62) bound the forward formula's
  own domain.
  `gravity.altitude_msl(y, p) = altitude_agl(y, p) + getattr(p.site, "h0_m", 0.0)` (gravity.py
  line 291-300) — the AGL/MSL relationship the new inverse must mirror in reverse.
- `sim/params.py`: `Control` (line 195-219), `Actuator` (line 222-245), `Solver` (line 248-255,
  `sample_rate_hz: float = 0.0`), `Params` (line 258-277, twelve groups + `actuator`). No `Sensors`
  group exists yet.
- `configs/schema.py`: `Rocket` (line 271-296) owns `control`/`actuator` (vehicle control
  hardware, same owning piece); `assemble()` (line 345+) builds `Params(...)` with one keyword per
  group, `actuator=sc.rocket.actuator` (line 372) being the most recent precedent to follow.
  `tests/test_config_pieces.py::test_assemble_params_call_keyword_set_equals_params_fields_exactly`
  (line 152-168) parses `assemble`'s own AST and asserts its `Params(...)` call's keyword set
  equals `{f.name for f in dataclasses.fields(Params)}` EXACTLY — a new `Params.sensors` field
  without a matching `sensors=...` keyword in `assemble` fails this test immediately (by design —
  this is the "someone forgot to wire the new group" tripwire).
- `configs/rockets/_TEMPLATE_rocket.py`: `tests/test_template_docs.py::test_tables_cover_every_field`
  (line 86-111) requires, for every `dataclasses.is_dataclass` field value the `ROCKET` piece
  holds (resolved at runtime, so a DEFAULT-valued `Sensors()` instance still counts), a `### <Type>`
  table whose row-name set equals that type's own field names exactly (5 cells per row,
  `REQ`/`OPT` literal in cell 2). `test_inline_comments_follow_convention` only checks comments on
  constructor KEYWORDS THAT ARE ACTUALLY PRESENT in the `ROCKET = Rocket(...)` call — a field left
  unset (using its dataclass default, like `sections` today) needs no inline comment at all, only
  the docstring table is mandatory.
- `controllers/__init__.py` docstring, verbatim: "sim/ never imports this package (rationale:
  controller experiments churn constantly and must not touch the physics package or its pins,
  SS35.4's own layering rule)." This directly rules out an eager `run_sim`-entry validation guard
  for `estimator_model` (§108.8.2) — such a guard would need `sim/integrate.py` to call into
  `controllers/estimator.py`, inverting this stated layering.
- Context7 MCP was NOT available as a tool in this architect session (no `resolve-library-id`
  tool was exposed). The alpha-beta (g-h) filter formulation and gain relation used below
  (§108.3.5) come from general, well-established estimation-theory knowledge (Kalata's
  parameterisation; the Benedict-Bordner critically-damped relation), not a verified library
  citation — disclosed here rather than presented as checked. If the user/orchestrator wants this
  independently verified (e.g. via the `research` agent against a primary source), that is a
  reasonable ask before trusting the exact numeric gain defaults long-term; the gains are inert
  placeholders behind `estimator_model="stub"` either way, so there is zero pin risk either way.

## §108.3 API shape — decisions and rationale

### §108.3.1 `sim/atmosphere.py` — new public pressure-altitude inverse

```python
def isa_pressure_altitude(p_Pa: float) -> float:
    """Inverse of `_isa_air_state`'s own pressure column: given a static
    pressure [Pa], returns h_msl [m] -- the altitude a barometric
    altimeter calibrated to the STANDARD ISA profile would report for
    that pressure, regardless of which atmosphere tier actually produced
    it (sim/sensors.py's own baro channel, Step 108).

    Algebraic inverse of the SAME `_LAYERS` table `_isa_air_state` reads
    (not a numerical root-find) -- so `isa_pressure_altitude(p)` for a `p`
    that came from `_isa_air_state(h).p` recovers `h` to float64 rounding,
    WITHIN one layer (sim/sensors.py's "all-zero sensor returns the
    truth" acceptance test relies on exactly this). `_isa_air_state`
    itself is untouched by this function -- deliberately duplicates the
    tiny forward-pressure core below rather than refactoring the pinned
    function to share it (same "duplicate, don't refactor a pinned path"
    call task-104/107 already made for their own near-identical copies).

    Clamped into the forward formula's own domain
    (`_H_MSL_MIN`/`_H_MSL_MAX`, B13) before inverting: a pressure outside
    `[_isa_pressure_core(_H_MSL_MAX), _isa_pressure_core(_H_MSL_MIN)]` is
    clamped to the nearer boundary first, so a pathological input cannot
    produce a NaN/log-of-negative. In this ticket's own call pattern
    (sim/sensors.py always feeds it a TRUE, noiseless pressure from
    `air_state`, never a noisy one -- noise is added in altitude space,
    AFTER this call, see §108.3.3) the clamp never actually triggers for
    any realistic flight; it exists so this function is safe to call on
    its own, as a public API, same defensive standing as B13 itself.
    """
    p_Pa = min(max(p_Pa, _ISA_P_AT_H_MSL_MAX), _ISA_P_AT_H_MSL_MIN)
    H_b, L, T_b, p_b = _LAYERS[0]
    for base_H, lapse, layer_T_b, layer_p_b in _LAYERS:
        if p_Pa > layer_p_b:   # haven't climbed into this layer yet (mirrors "if H < base_H: break")
            break
        H_b, L, T_b, p_b = base_H, lapse, layer_T_b, layer_p_b
    if L != 0.0:
        T = T_b * (p_Pa / p_b) ** (-L * _R_D / _G_ISA)
        H = H_b + (T - T_b) / L
    else:
        H = H_b - (_R_D * T_b / _G_ISA) * math.log(p_Pa / p_b)
    return float(_R_ISA * H / (_R_ISA - H))


def _isa_pressure_core(h_msl: float) -> float:
    """Private, tiny DUPLICATE of `_isa_air_state`'s own h->pressure core
    (table walk + T + press, nothing else) -- used ONLY to compute the two
    module-level clamp-bound constants below, at import time. Exists so
    `isa_pressure_altitude`'s clamp bounds are derived from `_LAYERS`
    itself (self-consistent if the table ever changes) without importing
    anything from, or editing a single character of, `_isa_air_state`.
    """
    h_msl = min(max(h_msl, _H_MSL_MIN), _H_MSL_MAX)
    H = _R_ISA * h_msl / (_R_ISA + h_msl)
    H_b, L, T_b, p_b = _LAYERS[0]
    for base_H, lapse, layer_T_b, layer_p_b in _LAYERS:
        if H < base_H:
            break
        H_b, L, T_b, p_b = base_H, lapse, layer_T_b, layer_p_b
    T = T_b + L * (H - H_b)
    if L != 0.0:
        return p_b * (T / T_b) ** (-_G_ISA / (L * _R_D))
    return p_b * math.exp(-_G_ISA * (H - H_b) / (_R_D * T_b))


# Clamp bounds for isa_pressure_altitude's own input domain, derived once
# from _isa_pressure_core (above) rather than hardcoded literals.
_ISA_P_AT_H_MSL_MIN = _isa_pressure_core(_H_MSL_MIN)  # ~108008 Pa
_ISA_P_AT_H_MSL_MAX = _isa_pressure_core(_H_MSL_MAX)  # ~0.37 Pa
```

Placement: directly after `_isa_air_state`'s own block (after line ~136), before
`sat_vapor_pressure`. `math` needs importing at module top (`sim/atmosphere.py` currently has no
`import math` — check at implementation time; `np.exp`/`np.log` are already used elsewhere in the
file and could substitute if preferred, but plain `math` matches `_isa_air_state`'s own style
of using bare Python floats, not numpy scalars, for this kind of scalar formula).

**Why not add this to `sim/gravity.py` instead** (where `altitude_msl`/`altitude_agl` live):
rejected — the ISA `_LAYERS` table and its constants are `atmosphere.py`'s own, private data; a
function that inverts them belongs next to the table it inverts, not in the module that only
converts AGL<->MSL (which this new function does NOT do at all — it stops at `h_msl`; converting
that to AGL is `sim/sensors.py`'s own one-line job, mirroring `gravity.altitude_msl`'s own
`+ h0_m` convention in reverse, see §108.3.3).

### §108.3.2 `sim/params.py` — new `Sensors` group; `Control` new fields

```python
@dataclass(frozen=True)
class Sensors:
    """Step 108 (architecture-35-paper-alignment.md SS35.4.4, D-115): the
    baro-pressure sensing channel's own hardware characteristics -- noise,
    lag, quantisation. All four fields default to exactly the values that
    make `sim.sensors.measure` reproduce the truth altitude bit-for-bit
    under the "isa" atmosphere tier (D-115's own "all-zero sensor" case) --
    zero pin risk for every existing scenario/test, none of which sets
    these fields.
    """
    baro_sigma_m: float = 0.0        # m, Gaussian noise sigma on the pressure-altitude reading; 0.0 = inert (noiseless)
    baro_tau_s: float = 0.0          # s, first-order lag time constant on the reading; 0.0 = inert (instantaneous)
    baro_resolution_m: float = 0.0   # m, quantisation step; 0.0 = inert (no quantisation)
    baro_seed: int = 0               # RNG seed for the noise draw; only read when baro_sigma_m != 0.0
```

`Control` gains three new fields (appended after `onboard_rho0`, same "inert at default" standing
as every other Step 107 addition):

```python
    # Step 108 (architecture-35-paper-alignment.md SS35.4.4, D-115): which
    # estimator a registered sampled law's own estimator.step call uses.
    # "stub" (default) is Step 107's own two-point backward difference,
    # UNCHANGED, bit-for-bit; "alpha_beta" is Step 108's real filter
    # (gains below). Read only by controllers/laws.py -- unreachable
    # (inert) under every memoryless airbrake_model value, same standing
    # as airbrake_ki/onboard_* above.
    estimator_model: str = "stub"     # stub | alpha_beta
    estimator_alpha: float = 0.5      # alpha_beta only: position gain, dimensionless (0, 1)
    estimator_beta: float = 0.1667    # alpha_beta only: velocity gain, dimensionless (0, 1) -- UNVERIFIED placeholder, see §108.8.3
```

`Params` gains one field, same pattern as `actuator` (added right after it, same conceptual
grouping -- vehicle control/sensing hardware):

```python
    sensors:    Sensors    = field(default_factory=Sensors)
```

### §108.3.3 `sim/sensors.py` — the baro channel (new module)

```python
"""Step 108 (architecture-35-paper-alignment.md SS35.4.4, D-115): the
baro-pressure sensing channel a registered sampled law (controllers/)
reads through -- the REAL sensor, replacing Step 107's own
`sim.control._ideal_measurement` stub at its one call site
(sim/control.py's sample_airbrake, SS107.12).

Pipeline, in order: true pressure (sim.atmosphere.air_state, whichever
tier is active) -> ISA pressure-altitude inversion (sim.atmosphere.
isa_pressure_altitude) -> first-order lag (closed form, same style as
sim.control._ramp) -> Gaussian noise (counter-based, architecture-35
SS35.4.4: "np.random.default_rng([seed, k])") -> quantisation. All four
Sensors fields default to inert, so sim.sensors.measure reproduces the
truth altitude bit-for-bit under the default "isa" atmosphere tier.

sim/ layering: this module is part of sim/ (reads sim.atmosphere,
sim.control's Measurement type), NOT controllers/ -- the sensor's own
physics belongs with the plant, same status as sim.control's actuator
model (Step 103). controllers/ never sees the true state `y`; it only
ever sees this module's own `Measurement` output.
"""

from __future__ import annotations

import math
from typing import NamedTuple, Optional

import numpy as np

from sim import atmosphere
from sim.control import Measurement


class SensorState(NamedTuple):
    t_prev: Optional[float] = None
    h_lag_prev: Optional[float] = None


def measure(t: float, y: np.ndarray, p, prev: "Optional[SensorState]") -> "tuple[Measurement, SensorState]":
    """`(Measurement, new_state)`. Called once per tick, only while
    sim.control._in_coast_window(t, y, p) holds (sample_airbrake's own
    gate, unchanged from Step 107) -- `prev` is this channel's own
    SensorState from the previous such call, or None at the first one.
    """
    s = p.sensors
    air = atmosphere.air_state(t, y, p)
    h_press = atmosphere.isa_pressure_altitude(air.p) - getattr(p.site, "h0_m", 0.0)

    if prev is None or prev.t_prev is None or s.baro_tau_s <= 0.0:
        h_lag = h_press
    else:
        dt = t - prev.t_prev
        h_lag = h_press + (prev.h_lag_prev - h_press) * math.exp(-dt / s.baro_tau_s)

    if s.baro_sigma_m != 0.0:
        k = int(round(t * p.solver.sample_rate_hz))
        rng = np.random.default_rng([s.baro_seed, k])
        h_noisy = h_lag + rng.normal(0.0, s.baro_sigma_m)
    else:
        h_noisy = h_lag

    if s.baro_resolution_m > 0.0:
        h_out = round(h_noisy / s.baro_resolution_m) * s.baro_resolution_m
    else:
        h_out = h_noisy

    return Measurement(h_baro=float(h_out)), SensorState(t_prev=t, h_lag_prev=h_lag)
```

Design notes:
- **Noise/lag/quantisation all operate in ALTITUDE space** (metres), post pressure-inversion, not
  in raw pressure (Pa) space -- matches the architecture doc's own acceptance-test field name
  (`baro_sigma_m`, SS35.6 Step 108 bullet), and sidesteps a pressure->altitude noise-sigma
  conversion that would vary with altitude (the local lapse slope `dp/dh`) for no modelled benefit
  given no real sensor datasheet exists yet (§35.8 item 10: "REQ for Step 108; defaults used
  otherwise").
- **The lag filter's own internal state (`h_lag_prev`) stores the PRE-noise, PRE-quantisation
  value**, not the final `h_out` -- so quantisation/noise jitter does not feed back into next
  tick's lag computation (a sensing element's physical dynamics shouldn't "remember" the ADC's own
  rounding). Only `h_lag` is threaded in `SensorState`.
- **Tick index `k` for the noise seed is DERIVED from `t`** (`round(t * sample_rate_hz)`), not
  stored as a counter in `SensorState` -- matches the architecture doc's own "stateless... a tick
  re-evaluation is bit-identical" description (SS35.4.4) and needs no extra state field. Safe
  because `sample_rate_hz > 0.0` is guaranteed whenever this code path runs at all (`run_sim`'s
  existing eager guard, SS107.7, requires it for any registered sampled law) and `T_s = 1/
  sample_rate_hz` is a small, fixed period the segmented-RK45 path (Step 104) also holds exact tick
  boundaries for -- float drift across a flight's few hundred ticks stays comfortably under 0.5
  ticks, so `round()` never lands on the wrong integer.
- **`h_lag <= 0.0` special-case for `baro_tau_s`** mirrors `sim.control._ramp`'s own infinite-rate
  special-case (there, to dodge `inf * 0.0 == nan`; here, to dodge `dt / 0.0` raising
  `ZeroDivisionError` for plain Python floats) -- same house pattern, not a new one.
- **Why pressure comes from `atmosphere.air_state`, not `gravity.altitude_agl` directly** (unlike
  the old `_ideal_measurement`): the whole point of a BARO channel is that it reads PRESSURE, which
  only equals a simple function of true altitude under the "isa" tier -- under "sounding"/"field"
  (Steps 18/20), the true local pressure can differ from standard ISA at the same true altitude,
  and inverting it through the STANDARD ISA profile (what a real altimeter's firmware assumes) is
  exactly the realistic altimeter error this channel should reproduce for free, with no new noise
  model needed for that particular effect.

### §108.3.4 `sim/control.py` — exact before/after (wiring)

Before (Step 107, lines 293-304, quoted in full in §108.2):
```python
    if name in _SAMPLED_LAWS:
        prev_actuator_hold, prev_ctrl_state = (
            (prev.actuator_hold, prev.ctrl_state) if isinstance(prev, SampledLawHold) else (prev, None)
        )
        if _in_coast_window(t, y, p):
            meas = _ideal_measurement(t, y, p)  # Step 108 replaces this one call (SS107.3.2/SS107.12)
            cmd, ctrl_state = _SAMPLED_LAWS[name](t, meas, p, prev_ctrl_state)
        else:
            cmd, ctrl_state = 0.0, prev_ctrl_state  # outside the window: command 0, state frozen
        actuator_hold = _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev_actuator_hold)
        return SampledLawHold(actuator_hold=actuator_hold, ctrl_state=ctrl_state)
```

After:
```python
    if name in _SAMPLED_LAWS:
        prev_actuator_hold, prev_ctrl_state, prev_sens_state = (
            (prev.actuator_hold, prev.ctrl_state, prev.sens_state)
            if isinstance(prev, SampledLawHold) else (prev, None, None)
        )
        if _in_coast_window(t, y, p):
            meas, sens_state = sensors.measure(t, y, p, prev_sens_state)
            cmd, ctrl_state = _SAMPLED_LAWS[name](t, meas, p, prev_ctrl_state)
        else:
            cmd, ctrl_state, sens_state = 0.0, prev_ctrl_state, prev_sens_state  # outside the window: both frozen
        actuator_hold = _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev_actuator_hold)
        return SampledLawHold(actuator_hold=actuator_hold, ctrl_state=ctrl_state, sens_state=sens_state)
```

Additional changes:
- New top-level import: `from sim import sensors` (alongside the existing `from sim import
  gravity, thrust_curve`, line 91) -- no cycle (`sim/sensors.py` imports `sim.atmosphere` and
  `sim.control.Measurement`, never `sim.control` as a whole, so `sim/control.py` importing
  `sim/sensors.py` at module scope is one-directional; verify at implementation time that
  `from sim.control import Measurement` inside `sensors.py` doesn't trigger a circular-import
  error given `sim/control.py`'s own `from sim import sensors` -- if Python's import machinery
  complains, the fallback is importing `Measurement` lazily inside `sensors.measure`, or moving
  `Measurement`'s definition to live in `sim/sensors.py` instead and having `sim/control.py`
  import it FROM there; flag to the orchestrator if this fallback is needed, it is a (small) shape
  change to where `Measurement` lives, not something to do silently).
- **Delete `_ideal_measurement`** (lines 485-504) — Step 107's own §107.12 item 1 explicitly
  permits this ("`_ideal_measurement` itself is then dead code Step 108 may delete ... either way,
  no Step 107 test calls it directly"); confirmed by §108.5's grep that nothing else references it.
- `gravity` import (line 91) stays — still used by `_proportional_airbrake` (line 138).
- Module docstring and `SampledLawHold`'s own docstring: update the "Step 108 placeholder, always
  None here" sentence (SampledLawHold docstring, lines 513-516) to say what it now carries.

### §108.3.5 `controllers/estimator.py` — the real alpha-beta filter

```python
"""Two estimator models for a registered sampled law's own state:
"stub" (Step 107, default) -- a trivial two-point backward difference,
exact whenever the measurement itself is exact; "alpha_beta" (Step 108,
opt-in via Control.estimator_model) -- a real constant-velocity
alpha-beta (g-h) filter: position+velocity recursively updated from a
single noisy/lagged altitude measurement per tick.

laws.py calls only `step(...)`, never reaches into either state type's
own fields (Step 107's own docstring already established this contract;
Step 108 does not change it) -- so this module's body can be replaced/
extended without laws.py changing shape, only ONE call-site keyword.
"""

from typing import NamedTuple, Optional


class EstimatorState(NamedTuple):
    """"stub" model's own state -- UNCHANGED from Step 107, bit-for-bit."""
    t_prev: Optional[float] = None
    h_prev: Optional[float] = None


class AlphaBetaState(NamedTuple):
    """"alpha_beta" model's own state: the filter's own last position/
    velocity ESTIMATE (not the raw measurement) plus the tick time it was
    produced at."""
    t_prev: Optional[float] = None
    h_hat: float = 0.0
    v_hat: float = 0.0


def _step_stub(t: float, h_baro: float, prev: "Optional[EstimatorState]"):
    """Step 107's own body, UNCHANGED."""
    if prev is None or prev.t_prev is None:
        return h_baro, 0.0, EstimatorState(t_prev=t, h_prev=h_baro)
    dt = t - prev.t_prev
    v_hat = (h_baro - prev.h_prev) / dt if dt > 0.0 else 0.0
    return h_baro, v_hat, EstimatorState(t_prev=t, h_prev=h_baro)


def _step_alpha_beta(t: float, h_baro: float, prev: "Optional[AlphaBetaState]", alpha: float, beta: float):
    """Constant-velocity alpha-beta (g-h) filter, Kalata's own
    parameterisation: predict `h_pred = h_hat_prev + v_hat_prev*dt`, then
    correct both states from the residual `r = h_baro - h_pred`:
    `h_hat = h_pred + alpha*r`, `v_hat = v_hat_prev + (beta/dt)*r`. Same
    "nothing to predict from yet" first-call convention as the stub
    (`v_hat = 0.0`, `h_hat = h_baro`) -- and same `dt <= 0.0` guard
    (returns the PREVIOUS estimate unchanged rather than dividing by
    zero/a negative dt, which a repeated or out-of-order tick could in
    principle produce).
    """
    if prev is None or prev.t_prev is None:
        return h_baro, 0.0, AlphaBetaState(t_prev=t, h_hat=h_baro, v_hat=0.0)
    dt = t - prev.t_prev
    if dt <= 0.0:
        return prev.h_hat, prev.v_hat, AlphaBetaState(t_prev=t, h_hat=prev.h_hat, v_hat=prev.v_hat)
    h_pred = prev.h_hat + prev.v_hat * dt
    r = h_baro - h_pred
    h_hat = h_pred + alpha * r
    v_hat = prev.v_hat + (beta / dt) * r
    return h_hat, v_hat, AlphaBetaState(t_prev=t, h_hat=h_hat, v_hat=v_hat)


def step(t: float, h_baro: float, prev, *, model: str = "stub", p=None):
    """`(h_hat, v_hat, new_state)`. `model="stub"` (default) is Step
    107's own body, bit-for-bit, for every existing 3-positional-arg
    caller (laws.py before this ticket; tests/test_controllers.py's own
    direct unit tests) -- `p` is ignored in that branch. `model=
    "alpha_beta"` reads its two gains from `p.control.estimator_alpha`/
    `p.control.estimator_beta` -- `p` is REQUIRED (AttributeError on
    `None`, no extra validation, SS7) in that branch only.

    Unknown `model` raises ValueError here -- the one validation point
    for this field (sim/integrate.py cannot eagerly guard it without
    importing controllers/, which sim/ never does; see the ticket's own
    §108.8.2 for why this is a deliberate, documented asymmetry with
    airbrake_model/actuator.model's eager guards).
    """
    if model == "stub":
        return _step_stub(t, h_baro, prev)
    if model == "alpha_beta":
        return _step_alpha_beta(t, h_baro, prev, p.control.estimator_alpha, p.control.estimator_beta)
    raise ValueError(f"estimator.step: unknown model {model!r} (known: 'stub', 'alpha_beta')")
```

Why `model`/`p` are keyword-only (`*,`): makes it syntactically impossible for a future 4th
positional argument to collide with either, and documents at the call site that these are optional
knobs, not part of the stub's core 3-argument shape every existing caller already depends on.

### §108.3.6 `controllers/laws.py` — one-line wiring change

Both `proportional_drag` and `pi_apogee` change their one `estimator.step(...)` call from:
```python
h_hat, v_hat, est_new = estimator.step(t_k, meas.h_baro, prev.est)
```
to:
```python
h_hat, v_hat, est_new = estimator.step(t_k, meas.h_baro, prev.est, model=c.estimator_model, p=p)
```
(`c = p.control`, already bound at the top of both functions.) At the `estimator_model="stub"`
default this is bit-for-bit the old call (same positional args, `model="stub"` matches the
function's own default, `p` ignored) — zero behaviour change for either law unless a config
explicitly sets `estimator_model="alpha_beta"`.

### §108.3.7 `configs/schema.py` — `Rocket.sensors` + `assemble()`

```python
    actuator: Actuator = dataclasses.field(default_factory=Actuator)
    # Step 108 (architecture-35-paper-alignment.md SS35.4.4, D-115): the
    # baro channel's own hardware characteristics -- same owning piece as
    # control/actuator above (vehicle control/sensing hardware, not a
    # run-level/weather/site concern).
    sensors: Sensors = dataclasses.field(default_factory=Sensors)
    sections: Sections = dataclasses.field(default_factory=Sections)
```
(inserted between the existing `actuator` and `sections` fields of `Rocket`, line ~294-295)

New import: `from sim.params import Sensors` (alphabetical slot among the existing
`from sim.params import ...` single-name imports, lines 68-81).

`assemble()`'s `Params(...)` call gains one keyword, next to `actuator=sc.rocket.actuator` (line
372):
```python
        actuator=sc.rocket.actuator,
        sensors=sc.rocket.sensors,
```
This is NOT optional — `tests/test_config_pieces.py::
test_assemble_params_call_keyword_set_equals_params_fields_exactly` (§108.2) fails immediately
without it, by design.

## §108.4 Config template docs — exact before/after

`configs/rockets/_TEMPLATE_rocket.py`:

1. New import: `from sim.params import Actuator, Aero, Control, Lengths, Recovery, Sensors` (add
   `Sensors` to the existing alphabetical tuple, line 149).
2. New `### Control` table rows (append to the existing table, line 117-133):
   ```
   | estimator_model | OPT | stub \| alpha_beta | "stub" | which estimator a registered sampled law's own filter uses |
   | estimator_alpha | OPT | - | 0.5 | alpha_beta only: position gain (0, 1) |
   | estimator_beta  | OPT | - | 0.1667 | alpha_beta only: velocity gain (0, 1) -- UNVERIFIED placeholder |
   ```
3. New `### Sensors` table (own section, after `### Actuator`, before the closing `"""`):
   ```
   ### Sensors
   | field             | REQ/OPT | unit / choices | default | what it does |
   |-------------------|---------|-----------------|---------|--------------|
   | baro_sigma_m      | OPT     | m               | 0.0     | Gaussian noise sigma on the pressure-altitude reading; 0.0 = inert |
   | baro_tau_s        | OPT     | s               | 0.0     | first-order lag time constant on the reading; 0.0 = inert |
   | baro_resolution_m | OPT     | m               | 0.0     | quantisation step; 0.0 = inert (no quantisation) |
   | baro_seed         | OPT     | -               | 0       | RNG seed for the noise draw; only read when baro_sigma_m != 0.0 |
   ```
4. Constructor body: three new commented-out lines inside the existing `control=Control(...)`
   block (after `onboard_rho0=1.225,`'s own commented line), same "leave at defaults" style:
   ```python
       # estimator_model="stub",               # OPT, stub | alpha_beta -- which estimator a registered sampled law uses
       # estimator_alpha=0.5,                  # OPT, - -- alpha_beta only: position gain (0, 1)
       # estimator_beta=0.1667,                # OPT, - -- alpha_beta only: velocity gain (0, 1); UNVERIFIED placeholder
   ```
   and a new, fully commented-out `sensors=Sensors(...)` block after the existing
   `actuator=Actuator(...)` block (before `notes=(...)`), same style as the existing fully
   commented-out `sections=Sections(...)` block (no single literal "switch" field exists for this
   group, so none of its lines are left active):
   ```python
       # sensors left at its default (Sensors()) -- a noiseless, lagless,
       # unquantised pressure-altitude reading. Fill it in once you have
       # real barometer datasheet numbers (architecture-35-paper-
       # alignment.md SS35.8 item 10).
       # sensors=Sensors(  # OPT, Sensors group -- baro-pressure sensing channel; default is noiseless/lagless/unquantised
       #     baro_sigma_m=0.0,       # OPT, m -- Gaussian noise sigma; 0.0 = inert
       #     baro_tau_s=0.0,         # OPT, s -- first-order lag time constant; 0.0 = inert
       #     baro_resolution_m=0.0,  # OPT, m -- quantisation step; 0.0 = inert
       #     baro_seed=0,            # OPT, - -- RNG seed; only matters when baro_sigma_m != 0.0
       # ),
   ```

This satisfies `test_tables_cover_every_field` (row-set match for both `### Control` and the new
`### Sensors`) and leaves `test_inline_comments_follow_convention` untouched (no new ACTIVE
keyword added to the real `ast.Call`, same standing as the already-commented `sections` block).

## §108.5 Pin safety — grep commands + findings

Re-run before closing the ticket; all five expected to show ONLY this ticket's own new lines:

```bash
grep -rn "_ideal_measurement" sim/ controllers/ tests/     # expect: zero hits after this ticket lands (deleted, §108.3.4)
grep -rn "estimator\.step(" controllers/ tests/             # expect: laws.py's two sites (now with model=/p=) + test_controllers.py's direct stub calls (unchanged, 3 positional args)
grep -n "_isa_air_state" sim/atmosphere.py                   # expect: identical to pre-ticket (function body byte-for-byte unchanged)
grep -rn "sens_state" sim/control.py                         # expect: SampledLawHold field (unchanged declaration) + the two new read/write sites in sample_airbrake
grep -rn "Params(" configs/schema.py                         # expect: exactly one call site, now with sensors=sc.rocket.sensors added
```

Expected pin impact: **none**. Every new field (`Sensors.*`, `Control.estimator_*`) defaults to a
value that reproduces exactly Step 107's own behaviour; the new `isa_pressure_altitude` function
is additive; `sample_airbrake`'s sampled-law branch is the only place this ticket's NEW code runs,
and it is unreachable without `p.control.airbrake_model` already being a registered sampled law
AND `_in_coast_window` holding AND (for any measurable difference beyond Step 107's own path)
`p.control.estimator_model="alpha_beta"` or a nonzero `Sensors` field, all of which are brand new,
default-inert knobs no existing config/test sets.

## §108.6 Test plan

`tests/test_sensors.py` (new):
1. All-default `Sensors()`, `atmosphere.model="isa"` (default): `sensors.measure(t, y, p, None)`'s
   `Measurement.h_baro` equals `gravity.altitude_agl(y, p)` to float64 rounding (documented
   "exact inverse" acceptance bullet) -- at `t=0` and at a second, later `t` with `prev` threaded.
2. `isa_pressure_altitude(_isa_air_state(h_msl, ...).p) == h_msl` to within 1e-6 m, parametrised
   over several `h_msl` values spanning layer 0 (troposphere, 0-11 km -- every demo/real-config
   flight in this project's scope stays well inside this single layer) and at least one value
   each in layers 1 and 2 (crossing a layer boundary, confirming the per-layer selection logic
   mirrors the forward loop correctly at the boundary itself).
3. Noise: `baro_sigma_m = 2.0`, all other `Sensors` fields inert, constant true altitude (a static
   `y`) over 5000 ticks at a fixed `sample_rate_hz`; sample std of the returned `h_baro` series
   matches `2.0` within a generous statistical tolerance (e.g. +-5% at `n=5000`, exact bound left
   to the developer's own CI justification); same `(seed, k)` pair reproduces the identical noise
   draw on a second, independent call (determinism, not just distribution).
4. Lag: `baro_tau_s = 0.1`, zero noise/quantisation, a step change in true altitude; the returned
   `h_baro` series matches the analytic first-order step response `h_in - (h_in - h_0)*exp(-t/tau)`
   to float64 rounding (closed form, exact -- same standing as `_ramp`'s own acceptance test).
5. Quantisation: `baro_resolution_m = 0.5`, zero noise/lag; every returned `h_baro` is an exact
   multiple of `0.5`.
6. All three effects composed (nonzero `baro_sigma_m`/`baro_tau_s`/`baro_resolution_m` together):
   smoke test only -- no crash, output stays within a sane physical bound of the true altitude
   given the configured sigma/resolution.
7. `_in_coast_window` gating (via `sim.control.sample_airbrake`, not `sensors.measure` directly):
   `sens_state` is frozen (unchanged) outside the coast window, exactly mirroring `ctrl_state`'s
   own existing frozen behaviour (Step 107's own test already covers `ctrl_state`; this ticket adds
   the equivalent assertion for `sens_state`).

`tests/test_controllers.py` (new section, alpha-beta):
8. First call (`prev is None`): `h_hat == h_baro`, `v_hat == 0.0`, `state ==
   AlphaBetaState(t_prev=t, h_hat=h_baro, v_hat=0.0)` -- mirrors the existing stub's own first-call
   test (line 91-94) exactly, for the new model.
9. Noiseless constant-velocity ramp (`h(t) = h0 + v0*t`, fed exactly every tick): after enough
   ticks for the filter's own geometric transient to decay (developer picks the tick count from
   the chosen `alpha`/`beta`'s own decay rate -- e.g. `(1-alpha)**n` comfortably below the test's
   tolerance), `h_hat`/`v_hat` converge to `h(t)`/`v0` within a tight tolerance (e.g. 1e-6).
10. Noise attenuation: feed many ticks of a KNOWN constant altitude plus i.i.d. Gaussian noise
    (sigma known); assert the FILTERED `h_hat` series has a materially smaller sample std than the
    raw noise sigma (an empirical, generously loose bound -- e.g. `std(h_hat) < 0.7 * sigma` -- NOT
    a specific theoretical steady-state-variance formula; §108.2's own disclosure applies: the
    exact g-h filter noise-reduction-ratio formula was not independently verified against a
    primary source in this ticket, so the test does not pin to it).
11. `estimator.step(t, h, prev)` (3 positional args, no `model=`) is bit-identical to Step 107's
    pre-ticket behaviour -- re-run the EXISTING two stub tests (lines 91-104) unmodified and
    confirm they still pass; add one more case calling `estimator.step(t, h, prev, model="stub",
    p=None)` explicitly and asserting the result equals the bare 3-arg call.
12. Unknown `model` string raises `ValueError`.
13. `proportional_drag`/`pi_apogee` with `estimator_model="alpha_beta"` set on a `Control` fixture:
    runs without error, state threads across ticks (same "law called once per tick with `prev`
    state" style test Step 107 already has for the stub, SS107.10).

`tests/test_control.py` (new section):
14. `sample_airbrake` dispatch through a tiny registered dummy law: with `Sensors()` all-default
    and `atmosphere.model="isa"`, the dummy law's own `meas.h_baro` equals the true AGL altitude
    (end-to-end through the real wiring, not just `sensors.measure` in isolation).
15. The two existing Step 107 sections of this file (registry mechanics, `_in_coast_window`/
    dispatch wiring) re-run unmodified, still green.

## §108.7 Test-impact table

| File | Change | Reason |
|---|---|---|
| `sim/atmosphere.py` | New: `isa_pressure_altitude`, `_isa_pressure_core`, two module constants | §108.3.1 |
| `sim/atmosphere.py` | `_isa_air_state` and every other existing function/constant | **No change** |
| `sim/params.py` | New `Sensors` dataclass; `Params.sensors` field; three new `Control` fields | §108.3.2 |
| `sim/sensors.py` | **New file**: `SensorState`, `measure` | §108.3.3 |
| `sim/control.py` | `sample_airbrake`'s sampled-law branch: thread `sens_state`, call `sensors.measure` | §108.3.4 |
| `sim/control.py` | New import `from sim import sensors`; delete `_ideal_measurement` | §108.3.4 |
| `sim/control.py` | `_proportional_airbrake`, `_full_airbrake`, `_no_airbrake`, `AirbrakeHold`, `_ramp`, `_actuator_ideal`, `_actuator_full`, `register_sampled_law`, `_in_coast_window` | **No change** |
| `controllers/estimator.py` | New: `AlphaBetaState`, `_step_alpha_beta`; `step` gains `model=`/`p=` keywords; `_step_stub` (renamed body, identical) | §108.3.5 |
| `controllers/laws.py` | Two call sites: `estimator.step(...)` gains `model=c.estimator_model, p=p` | §108.3.6 |
| `configs/schema.py` | `Rocket.sensors` field; `assemble()`'s `Params(...)` call gains `sensors=` keyword; one new import | §108.3.7 |
| `configs/rockets/_TEMPLATE_rocket.py` | New `### Sensors` table; three new `### Control` rows; new commented constructor block | §108.4 |
| `tests/test_sensors.py` | **New file**, ~7 tests | §108.6 |
| `tests/test_controllers.py` | ~6 new tests, new section; existing stub tests re-run unmodified | §108.6 |
| `tests/test_control.py` | ~2 new tests, new section; existing sections re-run unmodified | §108.6 |
| All other tests | **No change expected** | Every new field/model/function is unreachable without an explicit, new, opt-in choice |

## §108.8 Open design decisions / flags for the orchestrator

1. **`estimator_model` does NOT become the new default input to `proportional_drag`/`pi_apogee`.**
   This is the one call in this ticket closest to an actual fork, so it is flagged rather than
   decided silently: keeping `"stub"` as the default (a) matches the brief's own explicit
   "zero numeric pin movement... old callers unaffected unless they explicitly opt in" requirement
   with the LEAST new surface area to review, and (b) means Step 109's closed-loop harness (the
   first consumer meant to evaluate these laws rigorously, depends_on this ticket) gets to CHOOSE
   `estimator_model="alpha_beta"` explicitly in its own scenario/ensemble setup, rather than
   inheriting a new default silently. If the orchestrator/user would rather the real filter become
   the new default for `proportional_drag`/`pi_apogee` specifically (not every registered law, not
   every existing config), that is a one-line change (flip `Control.estimator_model`'s own default
   from `"stub"` to `"alpha_beta"`) — but it is a genuine behaviour change for anyone who has
   already started tuning `proportional_drag`/`pi_apogee` gains against the stub's own (simpler,
   exact-under-noiseless-measurement) dynamics, so it is called out here rather than assumed.
2. **No eager `run_sim`-entry validation guard for `estimator_model`**, unlike
   `airbrake_model`/`actuator.model`. Both of those guards live in `sim/integrate.py` and call
   `sim.control.known_actuator_models()`/`known_sampled_laws()` -- functions that live INSIDE
   `sim/control.py` itself. `estimator_model`'s two valid values are implemented in
   `controllers/estimator.py`, and `controllers/__init__.py`'s own docstring states plainly that
   `sim/` never imports `controllers/` ("controller experiments churn constantly and must not
   touch the physics package or its pins"). Adding an eager guard here would require
   `sim/integrate.py` to import `controllers/`, inverting that stated rule. The validation instead
   happens lazily, one layer up, inside `estimator.step` itself (raises `ValueError` on an unknown
   `model` string) — still fails fast, within the SAME tick the bad value would first be read, just
   not at `run_sim`'s own entry point. Flagging this asymmetry explicitly rather than silently
   either violating the layering rule or silently accepting a less-eager failure mode.
3. **`estimator_alpha=0.5`/`estimator_beta≈0.1667` are UNVERIFIED placeholders.** Context7 was not
   reachable as a tool in this architect session (§108.2); the values used (Kalata's g-h filter
   parameterisation, Benedict-Bordner's critically-damped relation `beta = alpha^2/(2-alpha)` at
   `alpha=0.5`) come from general estimation-theory knowledge, not a checked primary source. They
   are inert unless `estimator_model="alpha_beta"` is explicitly set, so there is no pin risk
   either way -- but if the user wants real gain-selection guidance (e.g. derived from an actual
   future barometer's noise sigma and the sample rate, per the standard "tracking index" design
   method), that is a good candidate for the `research` agent against a primary source, or a
   revisit once §35.8 item 10's real barometer numbers arrive, whichever comes first. Not blocking
   this ticket's own acceptance (the gains are a default value on an opt-in path, not a correctness
   claim about any specific real sensor).
4. **Noise/lag/quantisation modelled in altitude space, not pressure space** (§108.3.3) — a
   deliberate simplification matching the architecture doc's own `baro_sigma_m` field name, not an
   oversight; noted for the record in case a future, more physically literal pressure-domain noise
   model is wanted once real datasheet numbers exist.
5. **Possible circular-import fallback** (§108.3.4): if `from sim import sensors` in
   `sim/control.py` together with `from sim.control import Measurement` in `sim/sensors.py` turns
   out to be a genuine circular import at implementation time (it should not be, by the dependency
   direction described, but Python's import machinery is occasionally stricter about `from X
   import Y` than a pure dependency-graph read suggests), the fallback is moving `Measurement`'s
   definition into `sim/sensors.py` and having `sim/control.py` import it from there instead. This
   is a small shape change (where one NamedTuple type lives) flagged here rather than done
   silently if it becomes necessary — report back if so, do not just pick one and move on.

## §108.9 Definition of done

- [ ] `sim/atmosphere.py`: `isa_pressure_altitude`/`_isa_pressure_core` + two new constants added
      per §108.3.1; `_isa_air_state` and every other existing symbol: **zero diff** (confirmed by
      §108.5's grep).
- [ ] `sim/params.py`: `Sensors` dataclass + `Params.sensors` field + three new `Control` fields,
      per §108.3.2.
- [ ] `sim/sensors.py` (new file) implemented per §108.3.3.
- [ ] `sim/control.py`: `sample_airbrake` wired per §108.3.4; `_ideal_measurement` deleted;
      `_proportional_airbrake`/`_full_airbrake`/`_no_airbrake`/`AirbrakeHold`/`_ramp`/
      `_actuator_ideal`/`_actuator_full`/`register_sampled_law`/`_in_coast_window`: **zero diff**.
- [ ] `controllers/estimator.py` implemented per §108.3.5; the existing two stub tests
      (`tests/test_controllers.py` lines 91-104) pass UNMODIFIED.
- [ ] `controllers/laws.py`: the two one-line call-site changes per §108.3.6; every other line
      unchanged.
- [ ] `configs/schema.py`: `Rocket.sensors` field + `assemble()` keyword + import, per §108.3.7.
- [ ] `configs/rockets/_TEMPLATE_rocket.py`: new `### Sensors` table + three new `### Control`
      rows + new commented constructor blocks, per §108.4; `tests/test_template_docs.py` green.
- [ ] `tests/test_sensors.py` (new): ~7 tests per §108.6, all passing.
- [ ] `tests/test_controllers.py`: ~6 new tests per §108.6; the FULL pre-existing file re-run
      unchanged and still passing.
- [ ] `tests/test_control.py`: ~2 new tests per §108.6; existing sections re-run unchanged.
- [ ] §108.5's five grep commands re-run, zero surprising matches.
- [ ] Point-in-time run: `python -m pytest tests/test_sensors.py tests/test_controllers.py
      tests/test_control.py tests/test_template_docs.py tests/test_config_pieces.py
      tests/test_atmosphere.py -q` green.
- [ ] Full suite green in background per `CLAUDE.md`'s convention. Any failure outside the files
      listed above is an undiscovered regression — report it, do not silently patch around it.
- [ ] §108.8's five open design decisions reported to the orchestrator in the step-closing message
      (items 1-2 are the ones most likely to warrant a user-facing follow-up; items 3-5 are
      disclosures, not blockers).
- [ ] `code-review` skill run before handing to QA (project convention, feature branch
      `feature/sim-paper-alignment`).

---

### [STEP-108] Baro sensor channel + real alpha-beta estimator
- **Module/boundaries:** `sim/atmosphere.py` (one new function + two helpers, additive only),
  `sim/params.py` (`Sensors` dataclass + `Control` fields), `sim/sensors.py` (new file),
  `sim/control.py` (sampled-law branch wiring + delete `_ideal_measurement`),
  `controllers/estimator.py` (new alpha-beta path), `controllers/laws.py` (two call-site edits),
  `configs/schema.py` (`Rocket.sensors` + `assemble()`), `configs/rockets/_TEMPLATE_rocket.py`
  (doc tables), `tests/test_sensors.py` (new), `tests/test_controllers.py` (new section),
  `tests/test_control.py` (new section).
- **Assignee:** developer.
- **depends_on:** [107] (builds directly on `SampledLawHold.sens_state`, `Measurement`,
  `_in_coast_window`, the estimator stub's own call shape — all Step 107 deliverables).
- **parallel_safe:** false (touches `sim/control.py`, already the most contended file in this
  milestone; also depends_on 107 directly).
- **Spec slice:** this file in full (`dev/docs/task-108-sensors-estimator.md`); architecture
  cross-reference `dev/docs/architecture-35-paper-alignment.md` §35.4.4 (chain) and D-115 (scope).
  Read §108.3 for exact before/after code, §108.6 for the test plan, §108.9 for the DoD checklist
  — do not re-read the whole architecture-35 document, this ticket already extracted every slice
  it needs.

Implement per §108.3-§108.4, TDD per §108.6 (tests first), run the point-in-time command in §108.9
before the full suite, report §108.8's open items in the closing message, then the full suite in
the background as the step gate. One step = one commit `Step 108 (Phase 2.17): baro sensor channel
+ real alpha-beta estimator`.
