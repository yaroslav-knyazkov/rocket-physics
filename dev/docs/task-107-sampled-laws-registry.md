# Step 107 — sampled laws registry + drag-aware predictor law

## Кратко (RU)

Тикет реализует Milestone M3's первый шаг: реестр "sampled laws" (`sim/control.py`'s
`register_sampled_law`) и новый пакет `controllers/` (флайт-софт вне `sim/`) с двумя законами
(`proportional_drag`, `pi_apogee`) и ЗАГЛУШКОЙ эстиматора (`controllers/estimator.py` — тривиальный
differencer, НЕ альфа-бета фильтр; настоящий фильтр и настоящий баро-канал — Step 108, не этот тикет).
Закрытая форма drag-aware предиктора апогея сверена с `model-proposals.md` строка 88 — транскрипция в
постановке задачи совпадает буквально, без ошибок.

**Ключевые решения архитектора (инженерные, не вынесены на пользователя — все D-114/D-115/D-116 уже
принят пользователем 2026-10-18, это лишь HOW):**
- Новый тип `SampledLawHold` (НЕ путать с Step 103's `AirbrakeHold` — разные NamedTuple, разная цель)
  оборачивает `(actuator_hold, ctrl_state, sens_state=None)`; канал `sample_airbrake` диспетчеризует на
  НОВЫЙ `_SAMPLED_LAWS` словарь, если `p.control.airbrake_model` там зарегистрирован, иначе — старый
  путь (`_AIRBRAKE_CONTROLLERS`), без изменений.
- Поле `sens_state` — заглушка на будущее (Step 108 заполнит); добавлено сейчас с default `None`, чтобы
  Step 108 не сломал форму `SampledLawHold`.
- Эстиматор-заглушка (`controllers/estimator.py::step`) — тривиальная обратная разность по высоте
  (`v_hat = (h-h_prev)/dt`), точна при идеальном (безшумном) датчике — закрывает тест "ideal sensor"
  без настоящего альфа-бета фильтра.
- `rho_hat` берётся из НОВОГО поля `Control.onboard_rho0` (номинальная константа, по умолчанию 1.225
  кг/м^3 — ISA на уровне моря), НЕ из ISA по `h_hat` — чтобы не трогать `sim/atmosphere.py` (вне границ
  этого тикета). Oracle-тест предиктора — ЧИСТО математический (сверяет закрытую форму с численным
  интегрированием ТОЙ ЖЕ ОДУ с постоянным `k`), не через `run_sim`/реальную ISA — иначе 0.1% было бы
  недостижимо из-за реального изменения плотности с высотой.
- Окно активности (burnout..apogee) законы САМИ не видят (спецификация: "controller never sees y") —
  гейтинг остаётся на уровне канала `sample_airbrake` (у которого есть `y`), НЕ внутри закона; вне окна
  закон вообще не вызывается, `cmd=0.0`, состояние замораживается (известное, документированное
  упрощение, не фикс).
- Новые поля `Control`: `airbrake_ki`, `onboard_mass`, `onboard_CdA0`, `onboard_CdA_brake`,
  `onboard_rho0` — все default = inert (`0.0`, кроме `onboard_rho0=1.225`, физическая константа без
  риска для пинов: путь недостижим без регистрации нового закона).
- Эгерная валидация в `run_sim`: зарегистрированное имя закона требует `sample_rate_hz>0` — иначе
  `ValueError` сразу (тот же паттерн, что `known_actuator_models()`).

---

## Table of contents

- §107.1 Scope and non-goals
- §107.2 Ground truth recap (verified against the code, not assumed)
- §107.3 API shape — decisions and rationale
- §107.4 `sim/control.py` — exact before/after
- §107.5 `controllers/` package — new files, exact content
- §107.6 `sim/params.py` — exact before/after (`Control` fields)
- §107.7 `sim/integrate.py` — exact before/after (eager validation)
- §107.8 Config template docs — exact before/after
- §107.9 Pin safety — grep commands + findings
- §107.10 Test plan
- §107.11 Test-impact table
- §107.12 Open questions / hand-off to Step 108
- §107.13 Definition of done

---

## §107.1 Scope and non-goals

**In scope:**
- `sim/control.py`: `register_sampled_law`/`known_sampled_laws`/`_SAMPLED_LAWS` (the registry),
  `Measurement`/`SampledLawHold` (NamedTuples), `_ideal_measurement` (Step 107's own ideal-sensor stub),
  `_in_coast_window` (a NEW, separate gate — `_proportional_airbrake` is NOT touched/refactored), and
  the extended dispatch inside `sample_airbrake`/`airbrake_deploy_fraction`.
- `controllers/` (new package): `__init__.py` (registers the two laws at import), `laws.py`
  (`drag_aware_predicted_apogee`, `proportional_drag`, `pi_apogee`, their state NamedTuples),
  `estimator.py` (**stub only** — a trivial backward-difference differencer, not the real alpha-beta
  filter; see §107.12 for the exact hand-off to Step 108).
- `sim/params.py`: five new `Control` fields (§107.6). No new dataclass group.
- `sim/integrate.py`: one new eager-validation guard in `run_sim` (§107.7), mirroring the existing
  `known_actuator_models()` check already there.
- `configs/rockets/_TEMPLATE_rocket.py`: `### Control` table rows + commented example lines for the
  five new fields (§107.8).
- `tests/test_control.py`: new section for the registry mechanics + `_in_coast_window`/dispatch wiring.
- `tests/test_controllers.py` (new): the predictor oracle test, the two laws' unit tests, and the
  integration-level "open-loop sanity" test.

**Out of scope / explicitly NOT this ticket's job (do not pre-build):**
- **`sim/sensors.py`, a real baro channel, noise/lag/quantisation, the real alpha-beta filter** — all
  Step 108 (D-115). `controllers/estimator.py` here is a stub (§107.12 spells out exactly what Step 108
  replaces and why nothing calling it today breaks).
- **`_proportional_airbrake` and the legacy `"proportional"`/`"full"`/`"none"` laws** — zero diff. The
  new gate (`_in_coast_window`) is a textually SEPARATE copy of the same two-line condition, not a
  refactor of the existing one (same judgment call task-104's own ticket made, §104.1: "if in doubt,
  duplicate the four lines instead — a correctness risk on the untouched default path is not worth a
  few lines of DRY-ness").
- **`sim/atmosphere.py`** — not touched. The predictor's `rho_hat` is a nominal constant
  (`Control.onboard_rho0`), not an ISA-at-`h_hat` lookup (§107.3.3 explains why, and leaves the door open
  for a later step to do better once a pure `h -> rho` helper is factored out of `atmosphere.py`, which
  is itself out of scope here).
- **`apps/airbrake_control/` (harness, metrics, gain sweep)** — Step 109.
- **A true continuous-time integral gain with proper `T_s` scaling beyond what's cheaply derivable from
  consecutive `t_k` values already in state** — see §107.3.4's `pi_apogee` design; no new field for it.

## §107.2 Ground truth recap (verified against the code, not assumed)

- `sim/control.py` (full file read, 433 lines, this session, on `feature/sim-paper-alignment`):
  `register_sampled_law` **does not exist**. `AirbrakeHold` (line 271) is Step 103's own actuator-state
  NamedTuple — `t_k, f_k, cmd_eff, cmd_queue` — unrelated to a law registry; reusing the bare word "Hold"
  for anything new in this ticket risks confusion, hence the new type is named `SampledLawHold`, never
  `*Hold` alone.
  - `sample_airbrake(t, y, p, prev)` (line 244): `cmd = _AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t,
    y, p); return _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev)` — exactly two lines, both
    extended below (§107.4).
  - `airbrake_deploy_fraction(t, y, p, hold=None)` (line 215): when `hold` carries an `"airbrake"` value,
    `isinstance(v, AirbrakeHold)` picks the ramp branch, else returns `v` (a plain float) as-is. This is
    the one spot that needs an unwrap step prepended for the new `SampledLawHold` case (§107.4).
  - `_proportional_airbrake` (line 102): activation gate is `if thrust_curve.thrust(t, y, p) > 0.0 or
    y[VZ] >= 0.0: return 0.0` — the exact two conditions `_in_coast_window` (new, §107.4) duplicates
    verbatim, inverted to a boolean (`return not (...)`), as a SEPARATE function.
  - `known_actuator_models()` (line 376) is the existing precedent for "a named entry point into a
    module-private dispatch dict, read once by `run_sim` at entry" — `known_sampled_laws()` follows the
    identical shape.
  - Module docstring ends at line 75; the Step 103 explanatory text (lines 262-268) is a standalone
    comment block immediately before `class AirbrakeHold`, NOT part of the module docstring — the house
    style this ticket's own Step 107 comment block follows (§107.4), plus one short paragraph appended
    to the top docstring itself (after the Step 65 paragraph, before the closing `"""`).
- `sim/params.py` (full file read, 306 lines): `Control` (lines 194-207) has exactly the eight fields
  the task brief named, nothing else; `Actuator` (lines 210-233) is untouched by this ticket (no new
  field needed there). The five new `Control` fields slot in additively after `airbrake_aero` (§107.6).
- `sim/sampling.py` (full file, 84 lines): `_CHANNELS = {"airbrake": control.sample_airbrake}`;
  `sample(t, y, p, prev)` passes each channel its OWN previous value out of `prev.values.get(name)` —
  confirmed this module needs **zero changes**: `sample_airbrake`'s return value is `Any` by this
  module's own contract (its docstring: "deliberately `Any`, not `float`... a future channel can hold a
  tuple... not just a scalar"), so returning a `SampledLawHold` instead of a `float`/`AirbrakeHold`
  composes with the existing loop with no edit required here.
- `sim/gravity.py`: `g(t, y, p)` (line 149) and `altitude_agl(y, p)` (line 269) are the two primitives
  `_proportional_airbrake` already uses and `_ideal_measurement`/the oracle test reuse the SAME `g`
  convention (`p.g0` under `gravity.model="constant"`, the scenario default).
- `sim/state.py`: `VZ` index confirmed (`range(7)`, position 3) — already imported in `control.py`
  (`from sim.state import VZ`).
- `sim/integrate.py::run_sim` (lines 622-730, this session's read): the eager-validation precedent is
  `if p.actuator.model not in control.known_actuator_models(): raise ValueError(...)` (lines 672-677),
  immediately followed by the `sample_rate_hz`/`method` gates (lines 679-696). The new sampled-law guard
  (§107.7) is inserted in the same block, same style, same "raise before any integration" placement.
- `dev/docs/latex/model-proposals.md` line 88 (feature branch, `git show
  feature/sim-paper-alignment:dev/docs/latex/model-proposals.md`), verbatim: `ĥ_a = h + (m/2k) ln(1 + k
  v_z²/(m g))`, `k = ½ρ(C_x S + C_D,b S_b f_b)` (vertical ballistic coast closed form). **Confirms the
  task brief's transcription is correct, no error** — the only notational difference is `m/2k` written
  without parens vs. the brief's `m/(2k)`, same quantity (standard math convention — `/` binds to the
  immediately preceding factor only when unambiguous; written with explicit parens below, no ambiguity).
- `tests/test_step114_review_fixes.py:21` confirms cross-test-file helper reuse IS existing house style
  (`from tests.test_scenario_sweep import LARGE`) — `tests/test_controllers.py` reuses
  `tests/test_control.py`'s `_launch_params`/`_launch_state`/`_LAUNCH_*` the same way (§107.10).
- `tests/test_template_docs.py` (full file read): `test_tables_cover_every_field` requires the
  `### Control` table's row-name SET to exactly equal `{f.name for f in dataclasses.fields(Control)}` —
  **order-independent, but every field, including ones left at their default and never passed as a live
  kwarg, must have a row.** `test_inline_comments_follow_convention` only checks LIVE keyword arguments
  inside the constructor call (via AST), not commented-out example lines — so the five new fields can be
  documented as table rows AND as commented-out example lines (matching every existing optional field's
  own treatment in this template), with zero risk of tripping that second test.

## §107.3 API shape — decisions and rationale

### §107.3.1 The registry itself

```python
_SAMPLED_LAWS: "dict[str, Callable]" = {}


def register_sampled_law(name: str, fn: "Callable") -> None:
    """Register fn(t_k, meas, p, state) -> (cmd, state) under `name`, read
    by sample_airbrake's dispatch (below) whenever p.control.airbrake_model
    == name. Collides only with the three BUILT-IN memoryless names (none/
    proportional/full) -- raises ValueError there (silently shadowing one
    of this project's off-switch/legacy names would be a nasty, hard-to-
    debug mistake for every subsequent call in the same process). Any
    other name, including re-registering the SAME name a second time, is a
    plain overwrite -- no raise -- the simplest, most dict-assignment-like
    behaviour, consistent with every other dispatch dict in this codebase
    being a bare literal (this is the first RUNTIME registration API this
    project has had; there is no stricter precedent to match).
    """
    if name in _AIRBRAKE_CONTROLLERS:
        raise ValueError(
            f"register_sampled_law: {name!r} collides with a built-in "
            f"airbrake_model name (known: {sorted(_AIRBRAKE_CONTROLLERS)})."
        )
    _SAMPLED_LAWS[name] = fn


def known_sampled_laws() -> "tuple[str, ...]":
    """The registered sampled-law names -- sim.integrate.run_sim's own
    eager-validation guard (Step 107, mirroring known_actuator_models())
    calls this instead of reaching into _SAMPLED_LAWS directly."""
    return tuple(_SAMPLED_LAWS)
```

**Why not merge `_SAMPLED_LAWS` into `_AIRBRAKE_CONTROLLERS` itself** (one dict, mixed memoryless/
stateful entries): rejected — `sample_airbrake`'s dispatch needs to know WHICH shape a given name's
function has (`(t, y, p) -> float` vs `(t_k, meas, p, state) -> (cmd, state)`) before calling it; one
dict holding two incompatible call signatures under one name-space is exactly the kind of implicit
state-space expansion the project's `rk45_seg` precedent (task-104 §104.2) already rejected for a
structurally similar reason. Two dicts, one membership check (`name in _SAMPLED_LAWS`), is the smaller,
more explicit change — and the collision guard above prevents the one failure mode (same name in both)
that would make the membership check ambiguous.

### §107.3.2 `Measurement` and the Step 107 ideal-sensor stub

```python
class Measurement(NamedTuple):
    """What a registered sampled law is allowed to see -- never `y`
    (architecture-35-paper-alignment.md SS35.4.4: "the controller never
    sees y"). `a_imu` is `None` until Step 108 wires an IMU channel (D-115
    only commits to baro + alpha-beta; IMU is option (c), not taken)."""
    h_baro: float
    a_imu: "Optional[float]" = None


def _ideal_measurement(t: float, y: np.ndarray, p) -> Measurement:
    """Step 107's own stub sensor: truth-equals-measurement, no noise, no
    lag, no quantisation -- exactly what the roadmap's own "ideal sensor"
    test wording (Step 107's acceptance bullet) requires to be testable
    BEFORE Step 108's real sim/sensors.py exists. Reads gravity.altitude_
    agl (the same primitive _proportional_airbrake's own predictor already
    reads), never atmosphere.py or any noise model.

    SUPERSEDED BY STEP 108 (does not change this ticket's own tests, see
    SS107.12): sample_airbrake's sampled-law branch (SS107.4) calls this
    function by name, in exactly one place. Step 108 replaces that ONE
    call site with `sensors.measure(t, y, p, prev_sens_state)` (returning
    a `(Measurement, sens_state)` pair instead of a bare `Measurement`),
    and threads the returned `sens_state` into `SampledLawHold.sens_state`
    (already present, default None, SS107.3.3) -- `_ideal_measurement`
    itself is then dead code Step 108 may delete, but nothing in THIS
    ticket's tests calls it directly (they go through run_sim/
    sample_airbrake), so deleting it breaks no Step 107 test.
    """
    return Measurement(h_baro=gravity.altitude_agl(y, p))
```

### §107.3.3 `SampledLawHold` — the channel's own `prev` under a registered law

```python
class SampledLawHold(NamedTuple):
    """The channel's own `prev` (sim.sampling's sense) when p.control.
    airbrake_model is a REGISTERED sampled law -- wraps the actuator's own
    held value (float under actuator.model=="ideal", AirbrakeHold -- Step
    103's own type, UNTOUCHED -- under "full") together with the LAW's own
    ctrl_state (opaque, law-specific: None for a stateless law, a small
    NamedTuple with an integrator for pi_apogee). `sens_state` is a Step-
    108 placeholder (always None here, Step 107 never writes anything
    else into it) -- present now so Step 108 does not need to change this
    NamedTuple's SHAPE, only what it puts in that one field (no API break,
    per the task brief's own requirement).
    """
    actuator_hold: "float | AirbrakeHold"
    ctrl_state: Any
    sens_state: Any = None
```

**Why a NEW type, not adding fields to Step 103's own `AirbrakeHold`:** `AirbrakeHold` already has a
proven, pinned shape (`t_k, f_k, cmd_eff, cmd_queue`) read by `airbrake_deploy_fraction`'s ramp branch
and constructed by `_actuator_full`; piling law/sensor state onto it would conflate two orthogonal
concerns (actuator dynamics vs. controller state) inside one NamedTuple and risks a future edit to one
concern accidentally touching the other's pinned fields. A wrapper is strictly additive and leaves
`AirbrakeHold` provably untouched (§107.9's grep confirms no edit lands inside its own class body).

**Why the law's own state is not simply threaded as the channel's bare `prev`** (i.e., skip the
actuator entirely, no wrapper): rejected — the actuator dispatch (`_ACTUATOR_MODELS[p.actuator.model]`)
still has to run every tick regardless of which law produced `cmd` (Step 103's rate/range/delay model is
orthogonal to Step 107's law choice — both can be `"full"`/`"pi_apogee"` simultaneously). The wrapper is
what lets BOTH independent pieces of per-tick state travel together as one `Any` value through
`sim.sampling`'s single-slot-per-channel contract.

### §107.3.4 The drag-aware predictor and the oracle test's own scope

```python
def drag_aware_predicted_apogee(h: float, v: float, g: float, m: float, k: float) -> float:
    """Closed form for a drag-only vertical ballistic coast (model-
    proposals.md line 88; architecture-35-paper-alignment.md SS35.4.4):

        h_a = h + (m / (2*k)) * ln(1 + k*v**2 / (m*g))

    `k` is the drag "area coefficient", 0.5*rho_hat*(C_dA0 + C_dA_brake*
    f_b) [kg/m] -- NOT the raw C_x or S alone. `v` enters squared, so its
    sign is irrelevant (works for either up- or down-positive velocity
    conventions, matching how _proportional_airbrake's own `y[VZ]**2`
    already sidesteps the same question).

    `k <= 0.0` -- the vacuum limit, `h + v**2/(2*g)` (the Taylor expansion
    of `ln(1+x)/x -> 1` as `x -> 0`; computed directly, not by evaluating
    the log formula at k=0, which would be a 0/0 division) -- this is also
    what every registered law's own onboard model reduces to under the
    Control defaults (onboard_CdA0=0.0, onboard_CdA_brake=0.0), so a user
    who registers a new law but forgets to set an onboard drag model gets
    the same upper-bound prediction _proportional_airbrake's own legacy
    formula already uses, not a crash.

    No guard against `m <= 0.0` with `k > 0.0` (division by zero/nan) --
    house no-validation convention (SS7), same standing as every other
    model-selection/physical-parameter field in this codebase; documented
    here, not defended against: `onboard_mass` must be set together with
    `onboard_CdA0`/`onboard_CdA_brake` whenever either is nonzero.
    """
    if k <= 0.0:
        return h + v**2 / (2.0 * g)
    return h + (m / (2.0 * k)) * math.log(1.0 + k * v**2 / (m * g))
```

**Where `rho_hat` comes from (the task brief's own open question, resolved):** a NEW `Control.
onboard_rho0` field, a nominal CONSTANT (default `1.225`, ISA sea level) — not an ISA-at-`h_hat` lookup.
Rationale, in order:
1. **File-boundary discipline.** This ticket's stated boundaries (`sim/control.py`, `controllers/`,
   `sim/params.py`, tests) do not include `sim/atmosphere.py`. `atmosphere.air_state(t, y, p)` needs the
   full state `y` internally (`_isa_air_state` reads `gravity.altitude_msl(y, p)`) — there is no existing
   pure `h -> rho` helper that takes a bare scalar altitude, and factoring one out is itself an
   `atmosphere.py` edit, out of scope here.
2. **The oracle test does not need it anyway.** "Oracle test: equals the simulated apogee of a drag-only
   vertical coast to < 0.1%" (the roadmap's own acceptance line) is read here as a PURE closed-form
   self-consistency check: numerically integrate `dv/dt = -g - (k/m)*v*v`, `dh/dt = v` for a FIXED,
   CONSTANT `k` (the same `k` the closed form uses), and compare to `drag_aware_predicted_apogee`'s own
   output for the SAME `h0, v0, g, m, k` — this is model-proposals.md's own "Analytic regression suite"
   item (line 104: "drag-only vertical coast closed form... pins one model end-to-end, independent of
   numerical pins"), not a comparison against `run_sim`'s real, altitude-varying ISA density. Running the
   comparison through `run_sim`'s real atmosphere instead would make the two inputs to the comparison
   PHYSICALLY DIFFERENT (constant-k closed form vs. a trajectory where k genuinely varies with altitude)
   and could not hit 0.1% for anything but a sub-10-metre coast (ISA density falls ~1/8000 per metre of
   altitude) — that is not what "oracle test" means here; it is a correctness check on the ALGEBRA, not
   an end-to-end physics validation (the latter is Step 109's closed-loop-harness job, comparing against
   the FULL nonlinear sim, not this ticket's).
3. A later step MAY upgrade `rho_hat` to a real ISA-at-`h_hat` lookup once Step 108 (or a dedicated small
   step) factors a pure `isa_density(h_msl) -> float` helper out of `sim/atmosphere.py` — flagged in
   §107.12, not built here (same "don't thread a field through before it's needed" precedent task-104's
   own ticket cites for `C_x180`, §104.14 item 3 there / Step 118's own ticket).

**Oracle test sketch (lives in `tests/test_controllers.py`, no `run_sim` call):**

```python
def test_drag_aware_predictor_matches_numerically_integrated_constant_k_coast():
    h0, v0, m, g, k = 0.0, 100.0, 0.5, 9.80665, 0.0008  # [kg/m], an arbitrary positive k

    def rhs(t, state):
        h, v = state
        return [v, -g - (k / m) * v * v]

    def v_zero(t, state):
        return state[1]
    v_zero.terminal = True
    v_zero.direction = -1

    sol = solve_ivp(rhs, (0.0, 20.0), [h0, v0], events=v_zero, rtol=1e-12, atol=1e-12)
    h_apogee_numeric = sol.y_events[0][0][0]

    h_apogee_closed = laws.drag_aware_predicted_apogee(h0, v0, g, m, k)
    assert abs(h_apogee_closed - h_apogee_numeric) / h_apogee_numeric < 0.001


def test_drag_aware_predictor_reduces_to_vacuum_limit_at_k_zero():
    h0, v0, g = 0.0, 80.0, 9.80665
    assert laws.drag_aware_predicted_apogee(h0, v0, g, m=1.0, k=0.0) == h0 + v0**2 / (2.0 * g)
```

### §107.3.5 The activation window — a new, separate gate, not a refactor

```python
def _in_coast_window(t: float, y: np.ndarray, p) -> bool:
    """Unpowered-ascent, pre-apogee -- a SEPARATE copy of the exact
    condition _proportional_airbrake applies inline (that function is NOT
    touched/refactored here, SS107.1), used only by sample_airbrake's new
    sampled-law branch, below. A registered law never sees `y`
    (architecture-35-paper-alignment.md SS35.4.4), so the window has to be
    decided at the channel level, which legitimately has `y` (the plant
    truth sampled once per tick) -- not inside the law itself.

    Known, documented simplification (same standing as `_trigger_after_
    apogee`'s own "pre-apogee vz dip" caveat, this module's docstring):
    outside this window the law is not called at all this tick (SS107.4),
    so a stateful law's internal filter/integrator does not warm up until
    the window opens -- not fixed here, not a regression (the legacy
    laws have no state to warm up in the first place, so this is a new
    kind of simplification specific to a stateful law, not a narrowing of
    an existing guarantee).
    """
    return not (thrust_curve.thrust(t, y, p) > 0.0 or y[VZ] >= 0.0)
```

## §107.4 `sim/control.py` — exact before/after

**Imports (line 78).** Replace:
```python
from typing import NamedTuple
```
with:
```python
from typing import Any, Callable, NamedTuple, Optional
```

**Module docstring** (append after the Step 65 paragraph, before the closing `"""` at line 75):
```python
Step 107 (architecture-35-paper-alignment.md SS35.4.4, task-107-sampled-
laws-registry.md): `register_sampled_law`/`known_sampled_laws` let a
STATEFUL law (estimator + controller, outside this module -- `controllers/
laws.py`) plug into the same `p.control.airbrake_model` dispatch key the
three memoryless laws already use, read only by `sample_airbrake` under
`p.solver.sample_rate_hz > 0.0` (`sim/integrate.py`'s eager guard rejects
any other combination before integration starts). `_proportional_airbrake`
and the other two memoryless laws are not edited by this step.
```

**New section, placed after `known_actuator_models` (today's line 385) and before the Step 57
aero-coefficient-seam comment block (today's line 388).** Full content, in order: the §107.3.1 registry
block, the §107.3.2 `Measurement`/`_ideal_measurement` block, the §107.3.3 `SampledLawHold` block, the
§107.3.5 `_in_coast_window` block. A short header comment above the whole section:
```python
# ----------------------------------------------------------------------
# Step 107 (architecture-35-paper-alignment.md SS35.4.4, task-107-
# sampled-laws-registry.md): the sampled-law registry -- any STATEFUL
# estimator+law pair (controllers/laws.py) can plug into the same
# p.control.airbrake_model dispatch key the three memoryless laws above
# already use. No law is written in this module -- see controllers/.
# ----------------------------------------------------------------------
```

**`sample_airbrake` (today's lines 244-259).** Replace the two-line body:
```python
    cmd = _AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t, y, p)
    return _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev)
```
with:
```python
    name = p.control.airbrake_model
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

    cmd = _AIRBRAKE_CONTROLLERS[name](t, y, p)
    return _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev)
```
Also update this function's own docstring with one new paragraph: `"Step 107: if p.control.
airbrake_model names a REGISTERED sampled law instead, dispatch there (ctrl_state threaded via
SampledLawHold) -- see task-107-sampled-laws-registry.md."`

**`airbrake_deploy_fraction` (today's lines 215-241).** Insert one line right after `v =
hold.values["airbrake"]` (today's line 236), before the existing `if isinstance(v, AirbrakeHold):`:
```python
        if isinstance(v, SampledLawHold):
            v = v.actuator_hold
```
Nothing else in this function changes. Also update its docstring with: `"Step 107: a SampledLawHold's
own actuator_hold is unwrapped first -- the ramp/passthrough logic below is otherwise unaware a sampled
law was involved."`

## §107.5 `controllers/` package — new files, exact content

New top-level package, sibling to `sim/`/`apps/`/`configs/` (architecture-35-paper-alignment.md SS35.4's
layering rule, already quoted in the task brief: "imports `sim/` and registers into `sim.control` at
import; `sim/` never imports `controllers/`").

**`controllers/__init__.py`:**
```python
"""Flight software under design (Phase 2.17 Milestone M3, architecture-35-
paper-alignment.md SS35.4.4) -- estimator + sampled laws. Imports sim/ and
registers into sim.control at import time; sim/ never imports this
package (rationale: controller experiments churn constantly and must not
touch the physics package or its pins, SS35.4's own layering rule).

Importing this package (`import controllers`, or any of its submodules)
is what makes `p.control.airbrake_model in ("proportional_drag",
"pi_apogee")` resolvable at all -- sim.control.known_sampled_laws() is
empty until this module's own import-time side effect runs once.
"""

from sim import control

from controllers import laws

control.register_sampled_law("proportional_drag", laws.proportional_drag)
control.register_sampled_law("pi_apogee", laws.pi_apogee)
```

**`controllers/estimator.py`** (stub only — see §107.12 for the exact Step 108 hand-off):
```python
"""Stub only (Step 107, task-107-sampled-laws-registry.md) -- the REAL
alpha-beta filter (h_hat, v_hat from noisy/lagged baro altitude) is Step
108's job (architecture-35-paper-alignment.md SS35.4.4, D-115). This stub
gives Step 107's own laws (controllers/laws.py) something state-shaped to
carry between ticks without inventing an ad hoc shape each law would
otherwise duplicate: a trivial two-point backward-difference estimator,
exact (zero error) whenever the measurement itself is exact (Step 107's
own sim.control._ideal_measurement) -- see SS107.12 for exactly what Step
108 replaces here and why no Step 107 test breaks when it does.

laws.py calls only `step(...)`, never reaches into EstimatorState's own
fields -- so Step 108 replacing this module's body entirely (a real
filter needs gains, not just two numbers) cannot break a law that only
ever treats EstimatorState as opaque state threaded back in next tick.
"""

from typing import NamedTuple, Optional


class EstimatorState(NamedTuple):
    t_prev: Optional[float] = None
    h_prev: Optional[float] = None


def step(t: float, h_baro: float, prev: "Optional[EstimatorState]"):
    """`(h_hat, v_hat, new_state)`. `v_hat = 0.0` at the very first call
    (`prev is None`, or a freshly-constructed `EstimatorState()` with
    `t_prev is None`) -- the same "nothing to difference against yet"
    convention `sim.control._actuator_full`'s own `f_0 = 0.0` literal
    uses for its own first tick.
    """
    if prev is None or prev.t_prev is None:
        return h_baro, 0.0, EstimatorState(t_prev=t, h_prev=h_baro)
    dt = t - prev.t_prev
    v_hat = (h_baro - prev.h_prev) / dt if dt > 0.0 else 0.0
    return h_baro, v_hat, EstimatorState(t_prev=t, h_prev=h_baro)
```

**`controllers/laws.py`:**
```python
"""Sampled, stateful airbrake laws (Phase 2.17 Milestone M3, architecture-
35-paper-alignment.md SS35.4.4) -- registered into sim.control at
controllers/__init__.py's own import time, never called directly by
sim/. Each law has the signature fn(t_k, meas, p, state) -> (cmd, state)
sim.control.register_sampled_law documents.
"""

import math
from typing import Any, NamedTuple, Optional

import numpy as np

from controllers import estimator


def drag_aware_predicted_apogee(h: float, v: float, g: float, m: float, k: float) -> float:
    # ... exact body, SS107.3.4 ...
    if k <= 0.0:
        return h + v**2 / (2.0 * g)
    return h + (m / (2.0 * k)) * math.log(1.0 + k * v**2 / (m * g))


def _k(c, f_b: float) -> float:
    """0.5*rho_hat*(C_dA0 + C_dA_brake*f_b) -- the predictor's own `k`,
    built from the onboard model's Control fields (SS107.6). `f_b` is the
    LAST tick's own commanded fraction (the law's own previous `cmd`,
    carried in its state) -- a one-tick-delayed self-consistency, same
    spirit as the legacy predictor's own "if drag vanished right now"
    simplification, documented not fixed."""
    return 0.5 * c.onboard_rho0 * (c.onboard_CdA0 + c.onboard_CdA_brake * f_b)


class ProportionalDragState(NamedTuple):
    est: "Optional[estimator.EstimatorState]" = None
    f_b_prev: float = 0.0


def proportional_drag(t_k, meas, p, state):
    c = p.control
    prev = state if state is not None else ProportionalDragState()
    h_hat, v_hat, est_new = estimator.step(t_k, meas.h_baro, prev.est)
    k = _k(c, prev.f_b_prev)
    h_a = drag_aware_predicted_apogee(h_hat, v_hat, p.g0, c.onboard_mass, k)
    error = h_a - c.airbrake_target_apogee_m
    cmd = float(np.clip(c.airbrake_kp * error, 0.0, 1.0))
    return cmd, ProportionalDragState(est=est_new, f_b_prev=cmd)


class PiApogeeState(NamedTuple):
    est: "Optional[estimator.EstimatorState]" = None
    integral: float = 0.0
    f_b_prev: float = 0.0


def pi_apogee(t_k, meas, p, state):
    c = p.control
    prev = state if state is not None else PiApogeeState()
    dt = 0.0 if prev.est is None or prev.est.t_prev is None else t_k - prev.est.t_prev
    h_hat, v_hat, est_new = estimator.step(t_k, meas.h_baro, prev.est)
    k = _k(c, prev.f_b_prev)
    h_a = drag_aware_predicted_apogee(h_hat, v_hat, p.g0, c.onboard_mass, k)
    error = h_a - c.airbrake_target_apogee_m
    unsat = c.airbrake_kp * error + c.airbrake_ki * prev.integral
    cmd = float(np.clip(unsat, 0.0, 1.0))
    # Anti-windup (conditional/clamping integration, no new gain field):
    # stop integrating further in the direction that is ALREADY saturated.
    saturated_high = cmd >= 1.0 and error > 0.0
    saturated_low = cmd <= 0.0 and error < 0.0
    new_integral = prev.integral if (saturated_high or saturated_low) else prev.integral + error * dt
    return cmd, PiApogeeState(est=est_new, integral=new_integral, f_b_prev=cmd)
```

Note on `airbrake_ki`'s units: `pi_apogee`'s integral term is `ki * sum(error * dt)` — a genuine
time-integral (dt is derived from consecutive `t_k` values via `prev.est.t_prev`, reusing data the
estimator stub already carries, not a separate field) — so `ki` has ordinary `1/(m*s)` units, not a
"per-sample" fudge factor. `0.0` at a law's very first tick (`dt = 0.0` there) is the same "first tick is
special" convention this codebase already uses throughout (`_actuator_full`'s `f_0 = 0.0`, estimator's
own `v_hat = 0.0`).

## §107.6 `sim/params.py` — exact before/after (`Control` fields)

Insert after `airbrake_aero` (today's line 207), before the closing field of the dataclass:
```python
    # Step 107 (architecture-35-paper-alignment.md SS35.4.4, task-107-
    # sampled-laws-registry.md): gains/onboard model read ONLY by a
    # registered sampled law (sim.control.known_sampled_laws()) -- inert
    # (unreachable) under every memoryless airbrake_model value, zero pin
    # risk. airbrake_kp/airbrake_target_apogee_m above are REUSED by
    # proportional_drag (same meaning: P gain / target on predicted
    # apogee error) -- no duplicate field for those two.
    airbrake_ki: float = 0.0          # pi_apogee's integral gain [1/(m*s)]; 0.0 = inert
    onboard_mass: float = 0.0         # kg, onboard model's own mass estimate (nominal, not truth)
    onboard_CdA0: float = 0.0         # m^2, onboard model's own baseline drag area (C_x*S, lumped); 0.0 = vacuum-limit predictor
    onboard_CdA_brake: float = 0.0    # m^2, onboard model's own FULLY-OPEN brake drag area increment (C_D,b*S_b, lumped)
    onboard_rho0: float = 1.225       # kg/m^3, nominal air density the predictor uses; 1.225 = ISA sea level (not ISA-at-h_hat, SS107.3.4)
```
Also update the existing `airbrake_model` inline comment (today's line 196) — pre-existing staleness
(it never mentioned `"full"`, added at Step 65) fixed as a zero-risk side effect of touching this exact
line for Step 107's own addition:
```python
    airbrake_model: str = "none"          # none | proportional | full | <registered sampled-law name> (needs solver.sample_rate_hz>0)
```

## §107.7 `sim/integrate.py` — exact before/after (eager validation)

Insert immediately after the existing actuator-model guard (today's lines 672-677), before the
`sample_rate_hz`/`method` gate (today's line 679):
```python
    if p.control.airbrake_model in control.known_sampled_laws() and sample_rate_hz <= 0.0:
        raise ValueError(
            f"p.control.airbrake_model={p.control.airbrake_model!r} is a "
            f"registered sampled law (known: {sorted(control.known_sampled_laws())}) "
            "and requires p.solver.sample_rate_hz > 0.0 (architecture-35-"
            "paper-alignment.md SS35.4.4, task-107-sampled-laws-registry.md): "
            "a sampled law carries state across ticks and only makes sense "
            "under the sampled-data/ZOH mode."
        )
```
Also add one sentence to `run_sim`'s own docstring, after the existing Step 103 paragraph (today's lines
655-662): `"Step 107: a registered sampled law (sim.control.known_sampled_laws()) also raises here,
immediately, if sample_rate_hz <= 0.0 -- same eager-validation rationale as the actuator-model guard
above (task-107-sampled-laws-registry.md)."`

No other line in `run_sim` changes. `controllers/` is never imported by `sim/integrate.py` (or any other
`sim/` module) — `control.known_sampled_laws()` simply returns `()` (empty) unless and until something
outside `sim/` has imported `controllers` first; this is intentional (the layering rule, SS35.4) and
means a `Params` naming an unregistered sampled-law string behaves EXACTLY like any other unknown
`airbrake_model` string today (a lazy `KeyError` at first dispatch, SS7) if `controllers` was never
imported in that process — not a new failure mode, not guarded against here.

## §107.8 Config template docs — exact before/after

`configs/rockets/_TEMPLATE_rocket.py`, `### Control` table (today's lines 117-128). Add five rows after
the `airbrake_aero` row (line 128), and update the `airbrake_model` row's "unit/choices" cell:
```
| airbrake_model           | OPT     | none \| proportional \| full \| a registered sampled-law name | "none" | airbrake controller; "none" = every field below inert |
...
| airbrake_ki              | OPT     | 1/(m*s)                                     | 0.0              | pi_apogee's integral gain; 0.0 = inert (sampled laws only) |
| onboard_mass             | OPT     | kg                                          | 0.0              | sampled laws' onboard mass estimate (nominal, not truth) |
| onboard_CdA0             | OPT     | m^2                                         | 0.0              | sampled laws' onboard baseline drag area (C_x*S, lumped) |
| onboard_CdA_brake        | OPT     | m^2                                         | 0.0              | sampled laws' onboard brake drag-area increment (C_D,b*S_b, lumped) |
| onboard_rho0             | OPT     | kg/m^3                                      | 1.225            | sampled laws' nominal air density (not ISA-at-h_hat, task-107) |
```
And, inside the `control=Control(...)` call (today's lines 234-247), add five more commented-out example
lines after the existing `airbrake_aero` one (line 246), matching the file's own established style
exactly (one line per field, `# OPT, unit -- description` tail):
```python
        # airbrake_ki=0.0,                     # OPT, 1/(m*s) -- pi_apogee's integral gain; sampled laws only
        # onboard_mass=0.0,                    # OPT, kg -- sampled laws' onboard mass estimate
        # onboard_CdA0=0.0,                    # OPT, m^2 -- sampled laws' onboard baseline drag area (C_x*S)
        # onboard_CdA_brake=0.0,               # OPT, m^2 -- sampled laws' onboard brake drag-area increment
        # onboard_rho0=1.225,                  # OPT, kg/m^3 -- sampled laws' nominal air density
```
These are Python COMMENTS, not live kwargs — `test_inline_comments_follow_convention` (§107.2) only
inspects actual AST keyword nodes, so this addition cannot trip it; `test_tables_cover_every_field`
(§107.2) is the one that requires the five new table rows to exist (it fails loudly, naming the missing
field, if any row is forgotten — re-run it after this edit, do not just trust the diff by eye).

`configs/scenarios/_TEMPLATE_scenario.py` is **not touched** — confirmed by this session's own grep
(§107.2): it documents no `Control`/`Actuator` fields at all (those live on `Rocket`, not `Scenario`).

## §107.9 Pin safety — grep commands + findings

All run and read directly during this ticket's drafting:

```bash
# 1. The two new sampled-law names must not already be in use anywhere (so
#    "unreachable without an explicit new choice" holds for the new dispatch path).
rg -n '"proportional_drag"|"pi_apogee"' .
# -> No matches (confirmed 2026-10-24, before this ticket existed).

# 2. register_sampled_law/known_sampled_laws/SampledLawHold/Measurement must not
#    already exist under those names anywhere (collision check).
rg -n "register_sampled_law|known_sampled_laws|SampledLawHold|class Measurement" sim/ controllers/ tests/
# -> No matches (controllers/ does not exist yet on this branch).

# 3. AirbrakeHold's own constructor call sites -- confirm none use POSITIONAL
#    args (which the SampledLawHold wrapper's existence could not break anyway,
#    since AirbrakeHold's own class body is untouched, but confirmed defensively).
rg -n "AirbrakeHold\(" sim/ tests/
# -> sim/control.py's own _actuator_full (keyword args, t_k=/f_k=/cmd_eff=/cmd_queue=);
#    tests/test_actuator.py constructs it directly for unit tests of _ramp/_actuator_full,
#    also keyword-only. Confirms this ticket's additive-only change to AirbrakeHold's
#    surroundings (never its own body) cannot break either.

# 4. Every existing airbrake_model value in tests/configs -- confirm none collides
#    with the two new registered names or with the new eager-validation guard.
rg -n 'airbrake_model\s*=' tests/ configs/ apps/
# -> Every existing value is "none"/"proportional"/"full" (confirmed by direct read of
#    the match list) -- none is "proportional_drag"/"pi_apogee", so the new run_sim
#    guard (SS107.7) cannot fire for any existing test/config: `p.control.airbrake_model
#    in control.known_sampled_laws()` is False for every one of them regardless of
#    sample_rate_hz, UNCONDITIONALLY (known_sampled_laws() is also empty unless
#    something imported controllers/ first, a second independent reason the guard
#    cannot fire for any existing call site).

# 5. Does anything construct Control(...) positionally (risk: a new field inserted
#    in the middle of the dataclass would shift positional args)?
rg -n "Control\(" tests/ configs/ apps/ sim/ | rg -v "Control\([a-zA-Z_]+="
# -> No matches -- every call site uses keyword arguments exclusively; the five new
#    fields are appended at the END of the dataclass body regardless, so even a
#    hypothetical positional call would be unaffected, but this confirms the stronger
#    claim (no positional construction exists at all).
```

**Re-run these same five commands as an acceptance gate after implementation** — if any surfaces a NEW
match contradicting the "no existing test/config reaches the new path by accident" claim, stop and
report it.

## §107.10 Test plan

**`tests/test_control.py` — new section** (registry mechanics + dispatch wiring, mirrors the existing
Step 57 seam test's own register/try/finally/delete pattern, lines 264-338):

1. `test_register_sampled_law_collides_with_a_builtin_name_raises` — `register_sampled_law("none", ...)`
   / `("proportional", ...)` / `("full", ...)` each raise `ValueError`; `_SAMPLED_LAWS` unchanged after.
2. `test_register_sampled_law_then_known_sampled_laws_round_trips` — register a test-only dummy
   `fn(t_k, meas, p, state) -> (0.3, state)` under `"test_s107_dummy"`, assert it's in
   `control.known_sampled_laws()`; `del control._SAMPLED_LAWS["test_s107_dummy"]` in `finally`.
3. `test_sample_airbrake_dispatches_to_a_registered_law_once_per_tick` — register a counting dummy law
   (closure incrementing a `list`-based counter each call); build a `Params` with `airbrake_model=
   "test_s107_counter"`, `solver.sample_rate_hz=10.0`, `solver.method="rk4"`, and a scenario where
   `_in_coast_window` is `True` for the WHOLE short test duration (no motor — `thrust=Thrust()` — and
   `y[VZ] < 0` throughout, e.g. a short free-fall-upward synthetic scenario, or simply call
   `control.sample_airbrake(t, y, p, prev)` directly in a small loop over `t = 0, 0.1, 0.2, ...` rather
   than through `run_sim`, to avoid needing a full flight — developer's call on the cleanest way to
   avoid entangling this unit test with event detection); assert the counter equals the number of calls
   made, each exactly once (not 4x, the RK4-substep trap `sample_airbrake`'s own "once per tick" design
   exists to avoid).
4. `test_sample_airbrake_threads_prev_ctrl_state_across_ticks` — the same counting dummy also records
   the `state` argument it was called with each time; assert call `k+1`'s own `state` argument is
   exactly call `k`'s own RETURNED state (object identity or equality, developer's choice) — the direct
   "prev state is threaded" proof the roadmap's own bullet asks for.
5. `test_sample_airbrake_outside_the_coast_window_does_not_call_the_law` — same counting dummy, a state
   where `_in_coast_window` is `False` (e.g. `thrust > 0`); assert the counter stays `0` and the returned
   `SampledLawHold.actuator_hold` reflects `cmd=0.0`.
6. `test_airbrake_deploy_fraction_unwraps_sampled_law_hold_ideal_actuator` — construct a
   `SampledLawHold(actuator_hold=0.7, ctrl_state=None)` directly, wrap it in a `sampling.Hold`, call
   `airbrake_deploy_fraction(t, y, p, hold)` with `actuator.model="ideal"`; assert it returns `0.7`
   (the unwrap-then-passthrough path).
7. `test_airbrake_deploy_fraction_unwraps_sampled_law_hold_full_actuator` — same, but
   `actuator_hold=AirbrakeHold(t_k=0.0, f_k=0.2, cmd_eff=0.9, cmd_queue=())`, `actuator.model="full"`;
   assert the result matches `_ramp(0.2, 0.9, t - 0.0, ...)` computed by hand for a chosen `t`.
8. `test_unknown_sampled_law_name_without_controllers_imported_raises_keyerror` — `_in_coast_window`
   True, `airbrake_model="not_a_real_law"`, `sample_rate_hz>0.0`; `control.sample_airbrake(...)` raises
   `KeyError` (same lazy SS7 convention as every other unknown model-selection string) — confirms this
   ticket introduces no NEW silent-failure mode for a genuine typo.
9. **Full existing suite re-run, zero diff expected** — `_proportional_airbrake` untouched; this IS the
   "`proportional` (legacy, `h + v^2/2g`) numbers unchanged" acceptance bullet.

**`tests/test_controllers.py` (new)** — `import controllers` (or `from controllers import laws`) at
module level is REQUIRED before any test below that relies on `"proportional_drag"`/`"pi_apogee"` being
resolvable through `run_sim`; reuses `tests.test_control`'s `_launch_params`/`_launch_state`/
`_LAUNCH_WEIGHT`/`_LAUNCH_LENGTHS`/`_LAUNCH_THRUST`/`_LAUNCH_AERO` via
`from tests.test_control import _launch_params, _launch_state` (confirmed house precedent, §107.2 item).

10. `test_drag_aware_predictor_matches_numerically_integrated_constant_k_coast` — §107.3.4's oracle test
    verbatim, < 0.1% relative error.
11. `test_drag_aware_predictor_reduces_to_vacuum_limit_at_k_zero` — §107.3.4's second snippet, exact
    equality (pure arithmetic, no tolerance needed).
12. `test_drag_aware_predictor_continuous_near_k_zero` — evaluate at `k=1e-9` and `k=0.0`; assert the two
    outputs agree to within a tight numerical tolerance (confirms no discontinuity at the branch
    boundary — a light sanity check, not a second oracle test).
13. `test_estimator_step_first_call_returns_zero_velocity` — `estimator.step(0.0, 100.0, None)` returns
    `(100.0, 0.0, EstimatorState(t_prev=0.0, h_prev=100.0))`.
14. `test_estimator_step_backward_difference_on_a_linear_ramp` — three consecutive calls at
    `t=0,1,2` with `h_baro = 10*t` (a noiseless linear climb); assert `v_hat == 10.0` exactly from the
    second call onward (the stub's own "exact under an ideal sensor" claim).
15. `test_proportional_drag_zero_gain_keeps_cmd_at_zero_and_updates_state` — `airbrake_kp=0.0`; `cmd ==
    0.0` every call, but `ProportionalDragState.est` still advances (the estimator runs regardless of
    the law's own output, confirming the "estimator always runs when the law is called" design).
16. `test_proportional_drag_matches_proportional_structure_at_zero_k` — with
    `onboard_CdA0=onboard_CdA_brake=0.0` (the defaults, `k=0`), `proportional_drag`'s own predicted
    apogee reduces to the vacuum-limit formula; compare its `cmd` output at a hand-picked
    `(meas, state)` against a hand-computed `clip(kp*(h + v_hat**2/(2g) - target), 0, 1)` value.
17. `test_pi_apogee_integral_accumulates_error_over_dt_and_resets_at_first_tick` — three consecutive
    calls at known `t_k`s with a known constant `error` sign/magnitude (fix `h_hat`/`v_hat` by feeding a
    `Measurement` sequence that keeps `h_a` constant, isolating the integral term); assert
    `PiApogeeState.integral` grows by `error*dt` each tick, `0.0` contribution at the very first call
    (`dt=0.0` there).
18. `test_pi_apogee_anti_windup_freezes_integral_while_saturated_in_the_same_direction` — force a large
    sustained positive `error` so `cmd` saturates at `1.0`; assert `integral` stops growing once
    saturated (compare two consecutive `PiApogeeState.integral` values post-saturation: equal, not
    growing), then confirm it resumes growing once `error` is driven negative (desaturating).
19. `test_sampled_law_state_resets_between_independent_run_sim_calls` — run the SAME scenario twice
    (`airbrake_model="pi_apogee"`, two separate `run_sim(p, s0)` calls, fresh `p` each time — no shared
    mutable module state) and assert the two runs' own apogee results are IDENTICAL (bit-for-bit or
    extremely tight tolerance) — the direct proof of "resets between runs" the roadmap's own bullet asks
    for; a failure here would indicate an accidental module-level mutable default or similar leak.
20. `test_proportional_drag_open_loop_sanity_ideal_sensor_ideal_actuator` — the roadmap's own acceptance
    bullet: `_launch_params(airbrake_model="proportional_drag", airbrake_kp=<developer-tuned>,
    airbrake_target_apogee_m=<well below the unconstrained apogee>, onboard_mass=<matching
    _LAUNCH_WEIGHT.m>, onboard_CdA0=<matching the scenario's own true C_x*S>, onboard_rho0=1.225)`,
    `actuator.model="ideal"` (the default), `solver.sample_rate_hz=<developer-chosen, e.g. 20.0>`,
    `solver.method="rk4"`; assert the resulting apogee is LOWER than the unconstrained (`"none"`) apogee
    AND within some loosely-bounded, named tolerance of the target (documented as "the controller's own
    steady-state error", not an exact hit — same style as `test_proportional_airbrake_lowers_apogee_
    and_saturates_during_coast`'s own loose assertions).
21. `test_pi_apogee_open_loop_sanity_reduces_steady_state_error_vs_proportional_drag` — same scenario,
    `airbrake_model="pi_apogee"` with a nonzero `airbrake_ki`; assert its FINAL apogee error (vs target)
    is smaller in magnitude than `proportional_drag`'s own (the textbook "integral action removes
    P-only steady-state error" property) — a comparative, not absolute, assertion, so it does not depend
    on hand-tuned gains hitting an exact number.
22. `test_full_traceability_comparison_table` (OPTIONAL, developer's call, not a hard requirement) — a
    single test/script producing the roadmap's own acceptance artifact: apogee for
    `none/full/proportional/proportional_drag` (and `pi_apogee`) on the nominal demo flight, printed or
    asserted into a simple ordering (`none`'s apogee >= every controlled variant's). This satisfies
    "Acceptance: comparison table `none / full / proportional / proportional_drag` on the nominal
    flight" from the roadmap row — report it in the PR/ticket-closing message either way, pytest
    assertion or plain printed table (developer's choice, not graded on exact format).

## §107.11 Test-impact table

| File | Change | Reason |
|---|---|---|
| `sim/control.py` | New: `Measurement`, `_ideal_measurement`, `SampledLawHold`, `_in_coast_window`, `register_sampled_law`, `known_sampled_laws`, `_SAMPLED_LAWS` | The registry itself (§107.3-§107.4) |
| `sim/control.py` | `sample_airbrake`: new sampled-law branch | Wiring (§107.4) |
| `sim/control.py` | `airbrake_deploy_fraction`: one new unwrap line | Wiring (§107.4) |
| `sim/control.py` | Module + two function docstrings: new paragraphs | House documentation convention |
| `sim/params.py` | `Control`: five new fields + one updated inline comment | §107.6 |
| `sim/integrate.py` | `run_sim`: one new eager-validation guard + one docstring sentence | §107.7 |
| `configs/rockets/_TEMPLATE_rocket.py` | `### Control` table: five new rows + updated `airbrake_model` row; five new commented example lines | §107.8 |
| `controllers/__init__.py`, `controllers/laws.py`, `controllers/estimator.py` | New package | §107.5 |
| `tests/test_control.py` | ~9 new tests, new section | §107.10 |
| `tests/test_controllers.py` | New file, ~13 new tests | §107.10 |
| `_proportional_airbrake`, `_full_airbrake`, `_no_airbrake`, `AirbrakeHold`, `_ramp`, `_actuator_ideal`, `_actuator_full`, `sim/sampling.py`, `sim/atmosphere.py` | **No change** | Confirmed additive/already-generic (§107.2/§107.9) |
| All other tests | **No change expected** | The two new law names are unreachable without an explicit, new, opt-in choice AND `controllers/` being imported (§107.9) |

## §107.12 Open questions / hand-off to Step 108

1. **The `_ideal_measurement` -> `sensors.measure` hand-off, exact mechanics.** Step 108 adds
   `sim/sensors.py` (new `Sensors` `Params` group) and replaces `sample_airbrake`'s one call to
   `_ideal_measurement(t, y, p)` (SS107.4) with `sensors.measure(t, y, p, prev_sens_state) ->
   (Measurement, sens_state)`, storing the returned `sens_state` into `SampledLawHold.sens_state`
   (field already present, default `None`, SS107.3.3 — no shape change needed). `_ideal_measurement`
   itself may then be deleted by Step 108 or kept as a documented "noiseless" sensor variant (Step 108's
   own call) — either way, no Step 107 test calls it directly (they all go through `run_sim`/
   `sample_airbrake`), so neither choice breaks anything built here.
2. **`controllers/estimator.py`'s real alpha-beta filter.** Step 108 is free to replace this module's
   entire body (constants/gains it needs are Step 108's own `Params` additions, not predicted here) —
   `laws.py` only ever calls `estimator.step(t, h_baro, prev_est) -> (h_hat, v_hat, new_est)`; as long as
   Step 108 preserves that exact call shape (it very likely will — "two numbers plus opaque state" is
   the natural shape for any single-channel filter), `proportional_drag`/`pi_apogee` need zero edits.
   Flag to the orchestrator only if Step 108 discovers it genuinely needs a DIFFERENT call shape (e.g. a
   second input channel beyond `h_baro`) — that would be a real, if small, API change worth a second
   look, not a silent widening.
3. **`rho_hat` as a nominal constant vs. ISA-at-`h_hat`** (SS107.3.4, item 3) — deliberately left as a
   later upgrade, contingent on a pure `isa_density(h_msl) -> float` helper being factored out of
   `sim/atmosphere.py` (out of scope for both this ticket and, probably, Step 108 — a candidate for its
   own small step if the open-loop sanity numbers in §107.10's test 20/21 turn out to need it for
   realism; not required for ANY of this ticket's own acceptance criteria).
4. **`airbrake_ki`/`onboard_*` field reuse vs. the architecture doc's literal `kp, ki, kd` list**
   (§35.4.1's informal Params-fields table): this ticket reuses the EXISTING `airbrake_kp`/
   `airbrake_target_apogee_m` fields for `proportional_drag` (same meaning as the legacy law) rather than
   adding a duplicate `law_kp`, and deliberately does NOT add an unused `airbrake_kd` field (`pi_apogee`
   has no D term; a dead field "for a future PID law" repeats the exact premature-schema precedent
   task-104's own ticket explicitly declined for `Aero.C_x180`, §104.14 item 3). Noted here as a
   deviation from the architecture doc's literal field list, not escalated — an engineering-naming
   sub-choice, same standing as `rk45_seg`'s own literal string.
5. **Step 109's closed-loop harness** will be the first consumer to run `proportional_drag`/`pi_apogee`
   against the FULL nonlinear sim with real dispersions (Step 105/106) and the REAL sensor (Step 108) —
   this ticket's own open-loop sanity test (§107.10 test 20/21) is intentionally a much weaker claim
   ("closer to target than no control, ideal sensor/actuator") and should not be mistaken for Step 109's
   own, much more rigorous metrics.

## §107.13 Definition of done

- [ ] `sim/control.py`: registry + `Measurement`/`SampledLawHold`/`_ideal_measurement`/
      `_in_coast_window` implemented per §107.3-§107.4; `sample_airbrake`/`airbrake_deploy_fraction`
      wired; module + two function docstrings updated; `_proportional_airbrake`/`_full_airbrake`/
      `_no_airbrake`/`AirbrakeHold`/`_ramp`/`_actuator_ideal`/`_actuator_full` have **zero diff**.
- [ ] `controllers/__init__.py`, `controllers/laws.py`, `controllers/estimator.py` implemented per
      §107.5; `controllers/estimator.py` is explicitly documented as a stub (§107.12's hand-off is
      spelled out in its own module docstring, not just this ticket).
- [ ] `sim/params.py`: five new `Control` fields + the `airbrake_model` comment fix, per §107.6.
- [ ] `sim/integrate.py`: one new eager-validation guard + docstring sentence, per §107.7.
- [ ] `configs/rockets/_TEMPLATE_rocket.py`: five new table rows + updated `airbrake_model` row + five
      new commented example lines, per §107.8; `tests/test_template_docs.py` still green (re-run it
      explicitly — it is the one test that would catch a forgotten table row).
- [ ] `tests/test_control.py`: ~9 new tests per §107.10, all passing; the FULL pre-existing file re-run
      unchanged and still passing (the "`proportional` numbers unchanged" acceptance bullet).
- [ ] `tests/test_controllers.py` (new): ~13 new tests per §107.10, all passing.
- [ ] §107.9's five grep commands re-run, zero surprising matches.
- [ ] Point-in-time run: `python -m pytest tests/test_control.py tests/test_controllers.py
      tests/test_template_docs.py tests/test_integrate.py -q` green.
- [ ] Full suite green in background per `CLAUDE.md`'s convention. Any failure outside the files listed
      above is an undiscovered regression — report it, do not silently patch around it.
- [ ] §107.10 test 22's comparison table (`none/full/proportional/proportional_drag[/pi_apogee]`)
      measured and reported in the PR/ticket-closing message, satisfying the roadmap's own acceptance
      line.
- [ ] `code-review` skill run before handing to QA (project convention, feature branch
      `feature/sim-paper-alignment`).

---

### [STEP-107] Sampled laws registry + drag-aware predictor law
- **Module/boundaries:** `sim/control.py` (registry + dispatch wiring), `sim/params.py` (`Control`
  fields), `sim/integrate.py` (one guard), `controllers/__init__.py` + `controllers/laws.py` +
  `controllers/estimator.py` (new package), `configs/rockets/_TEMPLATE_rocket.py` (doc table),
  `tests/test_control.py` (new section), `tests/test_controllers.py` (new file).
- **Assignee:** developer
- **depends_on:** [103] (DONE — commit `6390c1d`/`f17a88a`/`0c98e2e`)
- **parallel_safe:** false — `sim/control.py`, `sim/params.py`, `sim/integrate.py` are shared,
  frequently-touched modules on this branch; sequence against any other in-flight ticket editing them,
  do not run alongside one in parallel.

Implement per §107.3-§107.8 above; write §107.10's tests first where practical (TDD skill — the pure
`drag_aware_predicted_apogee`/`estimator.step` tests have no reason to wait on the registry/dispatch
wiring). Verify §107.9's pin-safety greps after implementation. Report §107.10 test 22's comparison
table and tick off §107.13 before handing to QA.
