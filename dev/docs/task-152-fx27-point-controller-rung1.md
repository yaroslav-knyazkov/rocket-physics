## Кратко (RU)

- Задача (Step 152, Phase 2.17): добавить в `projects/fx27` замкнутый контур управления аэротормозом «Rung 1» (идеальный актуатор, бесшумные датчики, один Tier-1 закон), по образцу существующей пары `solvers/point/airbrake.py` + `runs/point/airbrake.py`.
- **Решение пользователя (обновлено): файл данных airbrake ДОБАВЛЯЕТСЯ сейчас**, а не откладывается. Новая директория `projects/fx27/campaigns/cspace/data/airbrake/` (по образцу `data/aero/`, `data/motors/`) с CSV-таблицами `M,cd_brake,area_design_m2` на семью ракет (`pro54-transition-airbrake.csv`, `pro75-airbrake.csv`). Одна строка = константный случай (формат естественно поддерживает и «одно число», и Mach-зависимую кривую — интерполяция `np.interp` коллапсирует в константу при одной строке).
- Загрузчик — новый модуль `projects/fx27/campaigns/cspace/airbrake_data.py` (свой, не переиспользует приватный `apps/sim/engine/aero.py::_load_table_impl` — тот заточен под другую форму таблицы, 2D по (M, alpha) с аэродинамическими коэффициентами; новый загрузчик проще: один столбец M, плюс `cd_brake`/`area_design_m2`). Путь — через новый `_paths.py::cspace_airbrake(filename)`, тот же приём, что `cspace_motor`/`cspace_aero`.
- **Рабочий процесс разделён**: `solvers/point/airbrake.py`/`runs/point/airbrake.py` (существующий статический solve) остаются БЕЗ ИЗМЕНЕНИЙ и не вызываются из контроллера вообще. Пользователь сам прогоняет `runs/point/airbrake.py`, смотрит на `area_design_m2`, и вручную вписывает число (или не меняет — файл будет содержать начальное placeholder-значение, взятое из текущего default-прогона solve_airbrake, явно помеченное как подлежащее ручной проверке) в новый CSV. `solvers/point/controller.py` читает ТОЛЬКО этот CSV через `airbrake_data.py`, никогда не вызывает `size_airbrake`.
- Остальное из первого раунда не меняется: модульная раскладка `solvers/point/controller.py` + `runs/point/controller.py`, сценарии — те же 4 «ideal»-варианта `dc` cspace, тесты — в `tests/test_fx27_port.py`.

---

## Table of contents

- S0 — Context recap (what already exists, cited by file:line)
- S1 — New module: `solvers/point/controller.py`
- S2 — New module: `runs/point/controller.py`
- S3 — Scenario choice: why the 4 ideal `dc` variants
- S4 — The airbrake hardware data file: location, format, loader (ADDED NOW)
- S5 — TDD brief for `developer`
- S6 — Rejected options

---

## S0 — Context recap (cited, not restated)

Everything below is already built and tested; this ticket is pure consumption/wiring, same posture as `apps/control/flight_software/harness.py`'s own module docstring (`harness.py:18-23`).

- `apps.control.flight_software.harness.run_closed_loop(p: Params, s0: State) -> HarnessResult` — `harness.py:209-222`. Returns `.metrics` (`apogee_m`, `apogee_error_m`, `actuator_saturation_fraction`, `actuator_travel`) and `.result`/`.actuator_t`/`.actuator_f` — `harness.py:58-110`.
- Rung-1 invariants, confirmed from `tests/test_harness.py`'s own oracle cross-check (`test_closed_loop_matches_step107_oracle_under_noiseless_sensors`, `tests/test_harness.py:110-120`): `Actuator()` all-defaults (`model="ideal"`), `Sensors()` all-defaults (noiseless), a registered Tier-1 law. `apps.control.flight_software` must be imported for its side effect (registers `proportional_drag`/`pi_apogee` into `apps.sim.engine.control._SAMPLED_LAWS`, `control.py:456-477`) **before** `assemble`/`run_closed_loop` dispatch by name — `tests/test_harness.py:20-21` shows the exact idiom (`import apps.control.flight_software  # noqa: F401`).
- `Control`/`Actuator`/`Sensors` field names/units/defaults — `apps/sim/engine/params.py:201-278` (already read in full for this ticket; do not re-read the whole file, these line numbers are current as of Step 151/152).
  - `Control.airbrake_model` must be a `known_sampled_laws()` name (`control.py:480-484`) for a Tier-1 sampled law to run at all — `"proportional_drag"` is the simpler one, no `airbrake_ki` needed (`params.py:222` is PI-only).
  - `Control.airbrake_Cd`/`airbrake_S_max` are plain scalar `float` fields (`params.py:206-207`) — the engine dynamics (`apps/sim/engine/control.py`'s `"additive"` path) only ever consumes ONE constant Cd and ONE constant area per flight, never a Mach-indexed curve. This caps what a Mach-dependent airbrake-hardware table can mean for Rung 1: it must be collapsed to a single `(cd, area)` pair at one reference Mach before it reaches `Control` (S4 below) — there is no library-level seam for a dynamic brake-Cd(M) curve today, and adding one is out of scope for this ticket.
  - `Control.onboard_mass`/`onboard_CdA0`/`onboard_CdA_brake`/`onboard_rho0` feed `drag_aware_predicted_apogee` (`apps/control/flight_software/laws.py`, not re-read here beyond signature already given in the task context) — all **zero by default = inert**, so nothing already flying is affected by this ticket.
  - `Actuator()`/`Sensors()` defaults are already the Rung-1 case (`model="ideal"`; all-zero noiseless) — the ticket does **not** need to construct non-default instances for Rung 1, only `Control` needs non-default values.
  - `Solver.sample_rate_hz` must be `> 0.0` for any sampled law to run at all (`params.py:371`, `harness.py:139`): the new scenario's `Solver` must set this.
- Scenario/Config plumbing (`apps/sim/schema.py`, already read in full relevant to this ticket):
  - `Scenario.rocket.{control,actuator,sensors}` are the groups `assemble()` sources `Params.{control,actuator,sensors}` from (`schema.py:383-387`) — i.e. these three groups are owned by the `Rocket` piece, not `Scenario` directly.
  - `Scenario.overrides: dict[str, Any]` (`schema.py:349`) is applied as dotted-path keys **after** the groups above are assembled (`schema.py:396-398`, via `apps.sim.engine.params.replace`, `params.py:406-424`) — this is the existing, idiomatic way to bolt scenario-specific tweaks onto a shared base `Rocket`/`Scenario` without touching the base `Rocket` object at all (same mechanism `Config.derive`/`with_variant` already use, `schema.py:106-129`). **Use this path**, not `dataclasses.replace(scenario.rocket, ...)` — it keeps `rockets.py`/`scenarios.py` completely untouched (requirement: library core and existing fx27 config modules are out of scope).
  - `Scenario.solver` is a top-level `Scenario` field (`schema.py:346`), independent of `Rocket` — `dataclasses.replace(scenario, solver=dataclasses.replace(scenario.solver, sample_rate_hz=...))` is how `sample_rate_hz` gets set.
  - fx27's cspace motors carry no mass model (`Weight.m_d` stays `None` for every fx27 scenario — confirmed, no `mass_model`/`m_d` fields anywhere in `projects/fx27/campaigns/cspace/motors.py`), so `Params.weight.m` is the one constant mass for the whole flight — `onboard_mass = cfg.params.weight.m` is unambiguous for fx27 (no dry/wet split to pick between, unlike a generic `apps/` scenario that does have a mass model).
- `projects/fx27/solvers/point/airbrake.py::size_airbrake(cfg, target_apogee_m, cda_bounds, cd_brake, margin, brake_count) -> BrakeSizing` (already read, full file, 75 lines) stays **completely unchanged and is never called by `controller.py`** (user decision this round: the static sizing tool and the closed-loop demo are now two deliberately decoupled workflows — see S4).
- fx27's existing data-file convention (both already read in full):
  - `projects/fx27/campaigns/cspace/data/aero/pro54-equal-drag.csv` — header row `alpha_deg,M,C_A,C_N,C_m,l1_m`, `#`-prefixed provenance/comment lines above the header, loaded by `apps/sim/engine/aero.py`'s own **private**, 2D-(M, alpha)-grid loader (`_load_table_impl`, `aero.py:218-267`: strips `#` lines, requires a header row naming the mandatory columns, `np.genfromtxt(..., names=True, dtype=float)`, QA checks for duplicate/missing columns and non-finite values). This loader is internal to `apps/sim/engine/aero.py` and shaped for a materially different table (2D grid, aero coefficients) — not reusable as-is for a 1D `M -> (cd, area)` curve; reuse the **convention** (CSV, `#` comment/provenance header, one data header row, `np.genfromtxt`, explicit QA errors) in a new, fx27-owned, much smaller loader (S4), not the function itself.
  - `projects/fx27/_paths.py` — `cspace_motor`/`cspace_aero` (`_paths.py:31-50`) are absolute-path helpers over `Path(__file__).resolve().parent`, sidestepping `apps.sim.engine.datafiles.resolve`'s cwd-relative foot-gun (`_paths.py`'s own module docstring). A third helper, `cspace_airbrake`, follows the exact same one-line pattern (S4).

---

## S1 — New module: `projects/fx27/solvers/point/controller.py`

Same shape as `solvers/point/airbrake.py` (thin wrapper + dataclass result + `print_*_report`). Reads the new airbrake-hardware data file (S4) via `campaigns/cspace/airbrake_data.py` — does **not** import or call `size_airbrake`/`BrakeSizing` (user decision this round: the two tools are decoupled, see S0's last bullet).

```python
"""projects/fx27/solvers/point/controller.py -- fx27's Rung-1 closed-loop
airbrake demo: ideal actuator, noiseless sensors, one Tier-1 sampled law
(apps.control.flight_software.laws), assembled on top of one of fx27's own
cspace scenarios and a HAND-ENTERED airbrake hardware data file
(campaigns/cspace/data/airbrake/*.csv, via campaigns/cspace/airbrake_data.py)
-- NOT `solvers/point/airbrake.py`'s own live sizing solve. That solver
stays a separate, user-driven "what area do I need" tool; its output is
meant to be read by a human and hand-copied into the hardware CSV once
accepted, not consumed programmatically here (dev/docs/task-152-fx27-
point-controller-rung1.md S4).
"""

from __future__ import annotations

import dataclasses

import apps.control.flight_software  # noqa: F401  (import-time side effect: registers the Tier-1 laws)
from apps.control.flight_software import harness
from apps.sim.schema import Config, Scenario, assemble

from projects.fx27.campaigns.cspace.airbrake_data import AirbrakeHardware

DEFAULT_LAW = "proportional_drag"          # the simpler Tier-1 law (no ki term)
DEFAULT_SAMPLE_RATE_HZ = 20.0              # matches tests/test_harness.py's own _closed_loop_params default
DEFAULT_MACH_REF = 0.3                     # subsonic post-burnout/coast regime -- see S4 for why a single ref Mach


@dataclasses.dataclass(frozen=True)
class Rung1Demo:
    """Everything one Rung-1 closed-loop run produced: the scenario actually
    flown, the assembled Config, the hardware data row(s) it was resolved
    from, and the harness's own flat metrics."""

    scenario: Scenario
    cfg: Config
    hardware: AirbrakeHardware
    harness: harness.HarnessResult


def build_rung1_scenario(
    scenario: Scenario,
    hardware: AirbrakeHardware,
    *,
    law: str = DEFAULT_LAW,
    kp: float,
    ki: float = 0.0,
    target_apogee_m: float,
    mach_ref: float = DEFAULT_MACH_REF,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
    estimator_model: str = "stub",
) -> Scenario:
    """`scenario` plus the Rung-1 `Control` overrides and a sampled solver
    (`Scenario.overrides`, SS schema.py:396-398 -- does NOT touch
    `scenario.rocket`). `Actuator`/`Sensors` are left at their library
    defaults (already the Rung-1 case: ideal actuator, noiseless sensors --
    see S0). `hardware.cd_at(mach_ref)`/`.area_at(mach_ref)` collapse the
    data file's own M-indexed row(s) to the single constant pair `Control`
    actually takes (S0's `Control.airbrake_Cd`/`airbrake_S_max` note) --
    this is a no-op (exact passthrough) when the CSV has exactly one row,
    by construction of `np.interp` (S4).
    """
    cfg = assemble(scenario)  # only to read cfg.params.aero/weight below
    onboard_CdA0 = cfg.params.aero.S * cfg.params.aero.C_x
    cd = hardware.cd_at(mach_ref)
    area = hardware.area_at(mach_ref)
    control_overrides = {
        "control.airbrake_model": law,
        "control.airbrake_target_apogee_m": target_apogee_m,
        "control.airbrake_kp": kp,
        "control.airbrake_ki": ki,
        "control.airbrake_Cd": cd,
        "control.airbrake_S_max": area,
        "control.onboard_mass": cfg.params.weight.m,
        "control.onboard_CdA0": onboard_CdA0,
        "control.onboard_CdA_brake": cd * area,
        "control.estimator_model": estimator_model,
    }
    overrides = {**scenario.overrides, **control_overrides}
    return dataclasses.replace(
        scenario,
        overrides=overrides,
        solver=dataclasses.replace(scenario.solver, sample_rate_hz=sample_rate_hz),
    )


def run_rung1_demo(
    scenario: Scenario,
    hardware: AirbrakeHardware,
    *,
    target_apogee_m: float = 2500.0,
    law: str = DEFAULT_LAW,
    kp: float,
    ki: float = 0.0,
    mach_ref: float = DEFAULT_MACH_REF,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> Rung1Demo:
    """`build_rung1_scenario` wires `hardware`'s own Cd/area plus a Tier-1
    law into a sampled-data `Scenario`; `harness.run_closed_loop` flies it.
    `hardware` is the CALLER's responsibility to pick (S2's own
    scenario-name -> hardware-file mapping) -- this function does not look
    it up by rocket name itself, keeping it a pure function of its
    arguments. `kp` has no safe library-wide default (depends on target/
    mass scale) -- caller must pass one; see S5 note on picking it
    empirically.
    """
    rung1_scenario = build_rung1_scenario(
        scenario, hardware, law=law, kp=kp, ki=ki, target_apogee_m=target_apogee_m,
        mach_ref=mach_ref, sample_rate_hz=sample_rate_hz,
    )
    cfg = assemble(rung1_scenario)
    result = harness.run_closed_loop(cfg.params, cfg.s0)
    return Rung1Demo(scenario=rung1_scenario, cfg=cfg, hardware=hardware, harness=result)


def print_rung1_report(demo: Rung1Demo, config_name: "str | None" = None) -> None:
    """Target vs. achieved apogee, error, actuator saturation/travel, plus
    the resolved hardware numbers actually flown (read back from
    `demo.cfg.params.control`, the already-assembled scalars -- not
    re-derived) -- same print-report shape as `solvers/point/
    airbrake.py::print_brake_report`."""
    m = demo.harness.metrics
    c = demo.cfg.params.control
    label = config_name or demo.scenario.name
    print(f"Rung-1 closed loop: {label}")
    print(f"  target apogee              {c.airbrake_target_apogee_m:.1f} m")
    print(f"  achieved apogee            {m['apogee_m']:.1f} m")
    print(f"  apogee error               {m['apogee_error_m']:+.1f} m")
    print(f"  actuator saturation        {m['actuator_saturation_fraction']:.2%}")
    print(f"  actuator travel            {m['actuator_travel']:.3f}")
    print(f"  brake Cd (hardware file)   {c.airbrake_Cd:.3f}")
    print(f"  brake area (hardware file) {c.airbrake_S_max:.6f} m^2")
```

Notes for `developer` (not load-bearing, just flagging intent so the implementation doesn't silently drift):
- `kp`/`ki` have **no safe default already in this codebase for fx27's own mass/apogee scale** (the only existing oracle gain, `_KP = 0.001` in `tests/test_harness.py:33`, is tuned for a ~500 m/small-mass demo scenario, not fx27's ~2500-3000 m vehicles) — this is implementation-level tuning, not an architectural decision; pick a starting value, verify the closed-loop apogee lands in a plausible band (not instantly saturating at `f_max=1.0` for the whole flight, not staying at `f_min=0.0` the whole flight), and document the chosen value's provenance in a code comment the same way `tests/test_harness.py:26-33` documents its own oracle's gain.
- `mach_ref=0.3` is a placeholder "reasonable post-burnout coast speed" choice, not a derived/verified number — if `developer` wants a more honest value, compute each scenario's own actual Mach at burnout (`result.events["burnout"]`, already available from a first `run()` through `solvers/point/flight.py`) and pass that instead; not required for this ticket to land, flagging so it isn't mistaken for a precise figure later.

---

## S2 — New module: `projects/fx27/runs/point/controller.py`

Same shape as `runs/point/airbrake.py` — a `main()` loop over named scenarios, calling the solver wrapper and printing a report. Adds one fixed scenario-name -> hardware-file mapping (only 2 entries needed: the two rocket FAMILIES with an "ideal" variant in this demo, `pro54_transition` and `pro75` — `pro54_equal` has no ideal variant in `SCENARIOS` at all, see `scenarios.py`, so it needs no hardware file yet either).

```python
"""projects/fx27/runs/point/controller.py -- Rung-1 closed-loop demo for the
4 ideal cspace variants (dc only -- see dev/docs/task-152-fx27-point-
controller-rung1.md S3 for why not the base rockets or the dm set yet).

Run: `python -m projects.fx27.runs.point.controller`.
"""

from __future__ import annotations

from projects.fx27.campaigns.cspace import airbrake_data
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.solvers.point.controller import print_rung1_report, run_rung1_demo

TARGET_APOGEE_M = 2500.0          # matches runs/point/airbrake.py's own target
KP = <picked per S1's note>        # developer fills in after an empirical check

# (scenario dict key, rocket-family hardware data) -- one hardware file per
# physical airframe family, reused by both its "ideal mass" and "ideal
# drag" variant (same airframe body, same brake, S4).
IDEAL_VARIANTS_DC = (
    ("pro54_transition (ideal mass)", airbrake_data.PRO54_TRANSITION_AIRBRAKE),
    ("pro54_transition (ideal drag)", airbrake_data.PRO54_TRANSITION_AIRBRAKE),
    ("pro75 (ideal mass)", airbrake_data.PRO75_AIRBRAKE),
    ("pro75 (ideal drag)", airbrake_data.PRO75_AIRBRAKE),
)


def main(argv=None) -> None:
    for name, hardware in IDEAL_VARIANTS_DC:
        scenario = SCENARIOS[name]
        demo = run_rung1_demo(scenario, hardware, target_apogee_m=TARGET_APOGEE_M, kp=KP)
        print_rung1_report(demo, config_name=name)
        print()


if __name__ == "__main__":
    main()
```

No `__init__.py` work needed — `projects/fx27/runs/point/__init__.py` and `projects/fx27/solvers/point/__init__.py` already exist (confirmed via `git status`/`ls`, both already tracked/untracked-but-present in the current working tree's reorg).

---

## S3 — Scenario choice: the 4 ideal `dc` variants, not the base rockets, not `dm` (yet)

**Unchanged from the first round.** Chosen: the same 4 "ideal" `dc` variants `runs/point/airbrake.py` already reports on (`pro54_transition`/`pro75` x `ideal mass`/`ideal drag`).

Reasoning:
- `runs/point/airbrake.py` already establishes, for exactly these 4 configs, "how much brake area is needed to pull this rocket's own (idealized, ~3000 m-class) trajectory down to a 2500 m target if the brake opens fully from burnout" (static sizing). The Rung-1 closed-loop demo answers the natural next question for the SAME 4 configs and the SAME target: "how close does an active, modulated law actually get, instead of a fixed full-open brake?" — now a genuinely independent comparison (not a shared live computation) since S4's decoupling means the two reports no longer even call the same function.
- The 3 base (non-ideal) rockets have no established 2500 m narrative in this project (`scenarios.py`'s own docstring: the base 3 just fly as-is, the project's real target for THEM is ~3000 m via the idealized variants, not 2500 m) — running the Rung-1 demo against them would need a new target-apogee justification with no existing reference point.
- The `dm` idealized variants (`scenarios_dm.py`) are a legitimate follow-up (same rockets, different aero representation) but are explicitly out of scope for a first Rung-1 ticket — add them the same way Step 151 (architecture-42 SS42.8) added them to `runs/point/airbrake.py`, as a second loop, once the `dc` path is landed and reviewed. They would reuse the SAME two hardware CSVs (same physical airframe/brake, only the aero *representation* differs between dc and dm).

---

## S4 — The airbrake hardware data file: location, format, loader (ADDED NOW — supersedes the prior "defer" recommendation)

**User decision this round: add the data file now**, with an explicit workflow split: `solvers/point/airbrake.py`/`runs/point/airbrake.py` (unchanged) stay the tool a human uses to compute/verify a candidate brake area for a target apogee; the number that comes out is **hand-reviewed and hand-entered** into the new file below; `solvers/point/controller.py` reads only the file, never calls `size_airbrake`. This is a deliberate decoupling (the controller's source of truth for "what hardware is actually installed" is a file a human edits, not a live solve), not an oversight.

### Location and naming

New directory, sibling of the existing `data/aero/` and `data/motors/` (same campaign, same convention):

```
projects/fx27/campaigns/cspace/data/airbrake/
    pro54-transition-airbrake.csv
    pro75-airbrake.csv
```

One file per physical rocket **family** (airframe + installed brake), not per scenario-dict-key — `pro54_transition (ideal mass)` and `pro54_transition (ideal drag)` are the same physical airframe/brake with two different idealized aero/mass representations (`scenarios.py`'s own naming convention, already documented there), so they share one hardware file. `pro54_equal` gets no file yet (no ideal variant uses it in `SCENARIOS`, S3) — add one only when/if a controller demo is scoped for it.

`_paths.py` gets a third helper, exact same shape as the two that already exist there (`_paths.py:31-50`):

```python
AIRBRAKE_CSPACE = _HERE / "campaigns" / "cspace" / "data" / "airbrake"


def cspace_airbrake(filename: str) -> str:
    """Absolute path to a cspace airbrake-hardware CSV under
    `campaigns/cspace/data/airbrake/` -- same rationale as `cspace_motor`/
    `cspace_aero`: an absolute path sidesteps `datafiles.resolve`'s
    cwd-relative rule 2."""
    return str(AIRBRAKE_CSPACE / filename)
```

### File format

Reuses the aero-table CONVENTION (CSV, `#`-prefixed provenance/comment lines above one header row, house `np.genfromtxt` idiom, no pandas — `aero.py:45`, `:218-267`) but with its own, much smaller column set — the aero loader's own code is not reused (S0's last bullet: it is private, and shaped for a 2D (M, alpha) grid of aero coefficients, not a 1D `M -> (cd, area)` curve).

Header: `M,cd_brake,area_design_m2`. A single data row **is** the constant case (M value present for format uniformity, but functionally irrelevant with one row — see loader below); two or more rows are a genuine Mach-dependent curve, linearly interpolated.

```csv
# pro54_transition airbrake hardware data (dev/docs/task-152-fx27-point-
# controller-rung1.md S4). HAND-ENTERED, not generated: area_design_m2
# below is <solvers/point/airbrake.py::size_airbrake>'s own printed
# "area, design" figure for this rocket at a 2500 m target (default
# margin=2.0, brake_count=3, cd_brake=1.0) as of <date> -- re-run
# `python -m projects.fx27.runs.point.airbrake` and overwrite this row if
# a different margin/target is wanted. PLACEHOLDER until a human
# reviews/accepts this number -- do not treat as a verified hardware spec.
M,cd_brake,area_design_m2
0.0,1.0,<size_airbrake's own area_design_m2 for pro54_transition>
```

(`pro75-airbrake.csv` is the same shape, `pro75`'s own sizing figure.) Seeding with `size_airbrake`'s own current default-run output, clearly labeled PLACEHOLDER, is the pragmatic way to land a non-blocking, honestly-labeled starting value — it is explicitly not a claim that this is the final/accepted number (that is the user's call, per the stated manual workflow).

### Loader module: `projects/fx27/campaigns/cspace/airbrake_data.py`

```python
"""projects/fx27/campaigns/cspace/airbrake_data.py -- loads the hand-entered
airbrake hardware CSVs under data/airbrake/ (dev/docs/task-152-fx27-point-
controller-rung1.md S4). Fx27-owned, small, NOT a reuse of apps/sim/engine/
aero.py's private 2D-table loader (different table shape, see that
module's own docstring for why).
"""

from __future__ import annotations

import dataclasses

import numpy as np

from projects.fx27._paths import cspace_airbrake

_REQUIRED_COLUMNS = ("M", "cd_brake", "area_design_m2")


@dataclasses.dataclass(frozen=True)
class AirbrakeHardware:
    """One rocket family's own airbrake hardware curve -- `M` ascending,
    `cd_brake`/`area_design_m2` the same length. A length-1 table IS the
    constant case: `cd_at`/`area_at` use `np.interp`, which returns the
    sole value for every query when `xp` has length 1 -- no special-casing
    needed in this class or in any caller."""

    M: np.ndarray
    cd_brake: np.ndarray
    area_design_m2: np.ndarray

    def cd_at(self, mach: float) -> float:
        return float(np.interp(mach, self.M, self.cd_brake))

    def area_at(self, mach: float) -> float:
        return float(np.interp(mach, self.M, self.area_design_m2))

    def cda_at(self, mach: float) -> float:
        return self.cd_at(mach) * self.area_at(mach)


def load_airbrake_hardware(path: str) -> AirbrakeHardware:
    """Parse one hardware CSV: strip `#` comment lines (same convention as
    aero.py's loader), require the header + >=1 data row, require ascending
    M (silently-wrong `np.interp` otherwise -- a QA check, not decoration),
    require every value finite."""
    data_lines = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            data_lines.append(line)
    if len(data_lines) < 2:
        raise ValueError(f"Airbrake hardware file '{path}' has no data rows")
    header = [h.strip() for h in data_lines[0].split(",")]
    missing = [c for c in _REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"Airbrake hardware file '{path}': missing column(s) {missing}")
    data = np.atleast_1d(np.genfromtxt(data_lines, delimiter=",", names=True, dtype=float))
    for col in data.dtype.names:
        if not np.all(np.isfinite(data[col])):
            raise ValueError(f"Airbrake hardware file '{path}': column {col!r} has a non-finite value")
    M = data["M"].astype(float)
    if np.any(np.diff(M) <= 0.0) and M.size > 1:
        raise ValueError(f"Airbrake hardware file '{path}': M column must be strictly ascending")
    return AirbrakeHardware(
        M=M, cd_brake=data["cd_brake"].astype(float), area_design_m2=data["area_design_m2"].astype(float),
    )


PRO54_TRANSITION_AIRBRAKE = load_airbrake_hardware(cspace_airbrake("pro54-transition-airbrake.csv"))
PRO75_AIRBRAKE = load_airbrake_hardware(cspace_airbrake("pro75-airbrake.csv"))
```

### Why a single reference Mach for Rung 1, even with a Mach-dependent file format

`Control.airbrake_Cd`/`airbrake_S_max` are plain scalar `float` fields consumed as ONE constant pair for the whole flight (S0) — there is no library-level mechanism today for the sim dynamics to look up a brake Cd(M) curve tick-by-tick. The file format supports a multi-row Mach curve (future-proofing: once a real wind-tunnel/CFD Cd(M) sweep for the actual brake exists, it can be entered directly, no format migration needed), but `build_rung1_scenario` always resolves it to one `(cd, area)` pair at one `mach_ref` before handing it to `Control`. This is consistent with — not a workaround for — Rung 1's own stated assumption set (linear drag, instantaneous actuation): a constant-coefficient brake model is what "Rung 1" already means architecturally, independent of this data-file decision. Extending the engine itself to look up a live Cd(M) during flight would be a Rung 2+/library-level change, out of scope here.

---

## S5 — TDD brief for `developer`

**Test location: `tests/test_fx27_port.py`** (the existing single test file covering ALL of fx27 — `projects/fx27` has no per-feature test files and no test directory of its own; `tests/test_fx27_port.py` is 16.2 KB, well under this project's ~150 KB archive threshold, so a new section fits without needing a new file). Follow the existing plain-function pytest style already used for the sizing solver, `test_airbrake_solve_converges_for_one_ideal_variant` (`tests/test_fx27_port.py:195-212`), as the closest precedent for imports/assembly idiom.

Write these FIRST (red), then implement S1/S2/S4 to make them pass (green):

**Data loader (`airbrake_data.py`) — test first, independent of the controller wiring:**

1. **`test_airbrake_hardware_single_row_is_constant_at_every_mach`** — load one of the two real seeded CSVs (or a `tmp_path`-written single-row fixture), assert `cd_at(0.0) == cd_at(0.9) == pytest.approx(the row's own cd_brake)`, same for `area_at`. Regression for "a length-1 table collapses to a constant" (the format's whole reason for existing).
2. **`test_airbrake_hardware_multi_row_interpolates_linearly`** — write a `tmp_path` fixture CSV with 2+ distinct M rows, assert `cd_at`/`area_at` at a midpoint Mach sit strictly between the two bracketing rows' own values (a direct `np.interp` cross-check, not a new numeric pin).
3. **`test_airbrake_hardware_rejects_missing_column`** / **`test_airbrake_hardware_rejects_non_ascending_M`** / **`test_airbrake_hardware_rejects_non_finite_value`** — three small `tmp_path`-fixture QA tests, mirroring the aero loader's own QA posture (`aero.py`'s QA-1/QA-2/QA-3 style) for this new, smaller loader.
4. **`test_cspace_airbrake_module_level_constants_load_without_raising`** — importing `projects.fx27.campaigns.cspace.airbrake_data` succeeds and `PRO54_TRANSITION_AIRBRAKE`/`PRO75_AIRBRAKE` are both `AirbrakeHardware` instances (the two real seeded CSVs parse).

**Controller wiring (`solvers/point/controller.py` + `runs/point/controller.py`):**

5. **`test_rung1_scenario_sets_the_three_invariant_pieces`** — build one Rung-1 scenario (any one of the 4 ideal `dc` variants, with its matching hardware constant), assemble it, assert: `cfg.params.actuator.model == "ideal"`, `cfg.params.sensors == Sensors()` (all-default, noiseless), `cfg.params.control.airbrake_model in known_sampled_laws()`.
6. **`test_rung1_control_cd_and_area_match_the_hardware_file_at_mach_ref`** — assert `cfg.params.control.airbrake_Cd == pytest.approx(hardware.cd_at(mach_ref))` and `cfg.params.control.airbrake_S_max == pytest.approx(hardware.area_at(mach_ref))`, and `cfg.params.control.onboard_CdA_brake == pytest.approx(hardware.cda_at(mach_ref))`. This is the regression test for the S4 decoupling decision: these three numbers must trace to the data file, not to any `solve_airbrake`/`BrakeSizing` call.
7. **`test_rung1_controller_module_does_not_import_solve_airbrake`** — a cheap, explicit lock-in: `import projects.fx27.solvers.point.controller as controller; assert "size_airbrake" not in dir(controller)` (or equivalently, assert the module's own `__dict__` has no `size_airbrake`/`BrakeSizing` name) — makes the "decoupled from the sizing tool" decision an executable fact, not just a docstring claim.
8. **`test_rung1_onboard_cda0_derives_from_the_scenario_own_aero`** — assert `cfg.params.control.onboard_CdA0 == pytest.approx(cfg.params.aero.S * cfg.params.aero.C_x)` (unchanged from the first round — this piece was never about the hardware file).
9. **`test_rung1_demo_completes_with_a_finite_plausible_apogee`**, parametrized over the 4 `IDEAL_VARIANTS_DC` `(name, hardware)` pairs — run `run_rung1_demo`, assert `math.isfinite(demo.harness.metrics["apogee_m"])` and a LOOSE sanity band around `target_apogee_m` (e.g. within a few hundred metres — this is a smoke test for "the wiring works and the law is doing something sane," not a bit-for-bit pin; do not over-tighten this into a de facto pin on `kp` or on the placeholder hardware numbers).
10. **`test_controller_runs_point_cli_runs_without_raising`** — `import projects.fx27.runs.point.controller as controller_cli; controller_cli.main()` completes without raising (same convention already used for the existing `point.py` CLI smoke tests, `tests/test_fx27_port.py:359-374`).

Do NOT write a bit-for-bit numeric pin on the achieved apogee or actuator trajectory in this ticket — `kp` is being picked empirically (S1 note) and the hardware CSV values are explicitly labeled PLACEHOLDER (S4); pinning now would freeze two arbitrary/unreviewed choices as if they were verified results.

---

## S6 — Rejected options

- **Editing `scenario.rocket` directly** (`dataclasses.replace(scenario.rocket, control=..., actuator=..., sensors=...)`) instead of `Scenario.overrides` — rejected: works identically for `assemble()`'s purposes, but `overrides` is the already-established idiom for "this one scenario needs scenario-specific tweaks without forking the base `Rocket` object" (same mechanism `Config.derive`/`with_variant` use), and keeps `rockets.py` conceptually untouched (it stays a pure hardware/airframe description, no controller state leaks into it).
- **Merging `controller.py` into `airbrake.py`** (one file, one report) — rejected: `airbrake.py` is a pure, already-tested, already-reported static solve, now explicitly decoupled from the controller (S4); `controller.py` reads a different input (the hardware CSV, not a live solve) and adds a materially different thing (a full closed-loop flight through the harness). Keeping them separate files matches the existing one-topic-per-file convention (`flight.py`, `airbrake.py`, `estimate.py`, `metrics.py`, `plots.py`, `comparison.py` are all already split this way under `solvers/point/`).
- **`controller.py` calling `size_airbrake` live and feeding its `BrakeSizing.area_design_m2` straight into `Control`** (this document's own first-round design) — superseded by the user's explicit decision this round: the sizing tool and the installed-hardware number must be two separate, independently-reviewable things (a live solve vs. a hand-accepted file), not the same computation reused twice.
- **Reusing `apps/sim/engine/aero.py`'s own `_load_table_impl`** for the new hardware file — rejected: that function is private to its module, and shaped for a 2D (M, alpha) grid of aero coefficients (`alpha_deg`/`C_A`/`C_N`/`C_m`/arm columns) — a materially different, more complex table than a 1D `M -> (cd, area)` curve. Reusing the CONVENTION (CSV, `#` comments, header row, `np.genfromtxt`, explicit QA errors) in a new, small, fx27-owned loader is the right-sized amount of reuse.
- **A single, shared/generic hardware file for all cspace rockets** instead of one per family — rejected: `pro54_transition` and `pro75` are physically different airframes (different body radius, different installed brake area) with no reason to share one brake-area number; one file per family (matching the existing `data/aero/*.csv` one-file-per-airframe convention) keeps each family's own hand-reviewed number independently editable.
- **NOT adding a data file (prior round's recommendation)** — superseded by explicit user instruction this round; the reasoning that made it a close call (every Rung-1 number WAS derivable from existing modules) is still true in isolation, but the user's stated workflow intent (sizing tool and installed-hardware value as two deliberately separate artifacts, the latter hand-reviewed) is a legitimate product requirement independent of whether the numbers happen to be re-derivable — the file is also the natural landing place for a REAL measured hardware number once one exists, without a later migration.
