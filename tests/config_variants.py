"""tests/config_variants.py -- test-only pieces and configs (Phase 2.16,
Step 88, dev/docs/architecture-33-configs-one-demo.md SS33.3.2).

A plain module (not `test_*`, so not collected; `tests/` is a package).
Every piece is moved verbatim from the `configs/` module it replaces
(numbers, comments, notes), so the exact-equality pins that read these
keep their meaning. None of them is registered in `configs/`.

- `TOY_05KG_ROCKET`, `TOY_05KG`: from `configs/rockets/toy_05kg.py` +
  `configs/scenarios/toy_05kg.py` (the 0.5 kg / S=0.005 / C_x=0.5
  placeholder vehicle, `run.py`'s historical literal). Its site/weather
  (`_ORIGIN_MSL_SITE`, `_ISA_DRY_CALM_WEATHER`) are inlined copies of
  `configs/sites/origin_msl.py` / `configs/weather/isa_dry_calm.py`
  (Step 123, D-139/D-140) rather than imports from them.
- `HIGHLAND_SITE`, `BREEZY_WEATHER`, `HIGHLAND`: from
  `configs/sites/highland_1500m.py`, `configs/weather/breezy_isa.py` and
  `configs/scenarios/demo_75mm_highland.py`, composed with the study
  vehicle (`apps/input/study_vehicle.py`).
- `CTI_K570_ISP`: from `configs/motors/cti_k570_isp.py` (the D-59 "isp"
  twin of `cti_k570`).
- `ALL`: every variant Config, for the "every test variant flies" test.
"""

from __future__ import annotations

from apps.input import study_vehicle
from apps.sim.schema import Airframe, Config, LaunchSite, Motor, Rocket, Scenario, Weather
from apps.sim.engine.params import Aero, Atmosphere, Lengths, Site, Thrust, Wind

# ----------------------------------------------------------------------
# toy_05kg
# ----------------------------------------------------------------------

TOY_05KG_ROCKET = Rocket(
    name="toy_05kg",
    airframe=Airframe(
        m=0.5,      # 0.5 kg dry+propellant mass
        I=0.05,     # kg*m^2, rough estimate for a small rocket
    ),
    lengths=Lengths(
        l1=0.3,     # m, CoP -> CoG distance
        l2=0.4,     # m, CoP -> thrust point distance
    ),
    # sections left at its default -- no measured section geometry for
    # this rocket (SS32.2.3).
    aero=Aero(
        # Step 55 (architecture-28-rewrite.md SS28.5.4): "constant"'s
        # C_x/C_z/C_m are true, q-scaled coefficients now, not raw
        # Newton/Newton-metre placeholders -- S/d_ref are therefore
        # required for any nonzero force/moment to result at all
        # (pre-Step-55, C_x=0.5 alone meant "0.5 N of drag for the
        # whole flight", which was never physical). Values match the
        # atmosphere-sweep scenario further down in run.py.
        S=0.005,    # m^2, reference area
        d_ref=0.08,  # m, reference length (moment arm + Reynolds number)
        C_x=0.5,    # axial-force coefficient [-]
        C_z=0.0,    # normal-force coefficient [-]
        C_m=0.0,    # pitching-moment coefficient [-]
    ),
)

_PLACEHOLDER_MOTOR = Motor(
    name="placeholder",
    thrust=Thrust(motor_curve="placeholder.csv"),  # replaced per entry; never read as-is
    # mass_model left at its default "none" -- constant-mass flight.
)

# Step 123 (Phase 2.18, D-139/D-140): inlined, not imported from
# `configs/sites/origin_msl.py` / `configs/weather/isa_dry_calm.py` (the
# registry subpackages this file no longer needs). Both are still
# argument-free (`Site()`, bare `Weather(name=...)`), matching those two
# modules' own deliberate choice to track `sim/params.py`'s defaults
# rather than freeze them (see those modules' docstrings) -- this is a
# literal copy of that choice, not a new one.
_ORIGIN_MSL_SITE = LaunchSite(name="origin_msl", site=Site())
_ISA_DRY_CALM_WEATHER = Weather(name="isa_dry_calm")

TOY_05KG: Config = Scenario(
    name="toy_05kg",
    rocket=TOY_05KG_ROCKET,
    motor=_PLACEHOLDER_MOTOR,
    site=_ORIGIN_MSL_SITE,
    weather=_ISA_DRY_CALM_WEATHER,
    notes=(
        "run.py's / App 2's historical placeholder scenario: a generic "
        "small model-rocket scale, unchanged since Step 1/Step 4."
    ),
).config

# ----------------------------------------------------------------------
# highland: the study vehicle flown from a different site, in different weather
# ----------------------------------------------------------------------

HIGHLAND_SITE = LaunchSite(
    name="highland_1500m",
    site=Site(
        lat0_deg=39.7,          # illustrative high-desert latitude, not a surveyed field
        lon0_deg=-104.9,        # illustrative; paired only with analytic (location-independent) weather
        h0_m=1500.0,            # the number this module exists for -- feeds the atmosphere column
        L_rail=3.0,             # a short rail/rod, m
        rail_angle_deg=85.0,    # tilted off vertical -- drives a non-trivial s0.theta (F5/D-51a)
    ),
    notes=(
        "The architect's own synthetic high-altitude site -- 1500 m MSL and "
        "an 85 deg rail tilt, picked to exercise the site-elevation-feeds-"
        "atmosphere coupling (SS31.2 F1) and the rail-angle-drives-s0 "
        "derivation (SS31.2 F5) end to end. Not a surveyed field; lat/lon "
        "are illustrative only."
    ),
)

BREEZY_WEATHER = Weather(
    name="breezy_isa",
    atmosphere=Atmosphere(model="isa"),
    wind=Wind(model="analytic", ref_ms=6.0, dir_deg=225.0),
    notes=(
        "ISA air (same model as isa_dry_calm) plus a steady 6 m/s analytic "
        "wind from the southwest. No sounding case -- deliberately safe to "
        "pair with any site (SS31.10 risk 3)."
    ),
)

HIGHLAND: Config = Scenario(
    name="study_75mm_highland",
    rocket=study_vehicle.ROCKET,
    motor=study_vehicle.MOTOR,
    site=HIGHLAND_SITE,
    weather=BREEZY_WEATHER,
    notes="One vehicle, two sites, zero duplication.",
).config

# ----------------------------------------------------------------------
# cti_k570_isp
# ----------------------------------------------------------------------

CTI_K570_ISP = Motor(
    name="cti_k570_isp",
    thrust=Thrust(motor_curve="Cesaroni_2060K570-17A.eng"),
    mass_model="isp",
    I_sp=212.41,
    notes=(
        "Same real Cesaroni K570 curve as cti_k570.py, 'isp' mass model "
        "with I_sp hand-entered (212.41 s, matching cti_k570.py's own "
        "measured I_sp_eff to 2 decimal places) instead of derived from "
        "the curve's own total impulse -- the direct D-59 comparison "
        "point for the 'isp' vs 'endpoints' models."
    ),
)

ALL: tuple[Config, ...] = (TOY_05KG, HIGHLAND)
