r"""configs/weather/_TEMPLATE_weather.py -- TEMPLATE, fill in your own
numbers (Step 72, dev/docs/architecture-31-config-separation.md SS31.5).

This file is a blank `Weather` piece: one flying day's air -- the
atmosphere model, the sounding case it may read, and the wind, all in
one piece because a single radiosonde ascent measures all three
(SS31.3.3, D-53). Every field below is commented
`# REQ|OPT, <unit or choices> -- <one line>` (SS32.8): REQ = you must
fill it in, OPT = leaving it alone gives correct, intentional behaviour.
The per-field tables at the end of this docstring list every field with
its default.

This module is **never registered** -- it is deliberately absent from
`configs/weather/__init__.py`'s `_MODULES` tuple, and must stay
absent. It still imports cleanly on its own --
`python -c "import configs.weather._TEMPLATE_weather"` must succeed --
so the file does not silently rot; pinned by
`tests/test_config_registries.py` (SS31.8 #6).

To use this template:
  1. Fill in every `# REQ` field below with your own numbers.
  2. Rename this file (and the `name="my_weather"` string below) to
     whatever you want your weather called.
  3. Add `from configs.weather import <your_module_name>` and one line
     to `configs/weather/__init__.py`'s `_MODULES` tuple.

### Weather
| field      | REQ/OPT | unit / choices   | default       | what it does |
|------------|---------|------------------|---------------|--------------|
| name       | REQ     | -                | --            | registry key; must equal the filename |
| atmosphere | OPT     | Atmosphere group | Atmosphere()  | atmosphere model; default is dry ISA |
| soundings  | OPT     | Soundings group  | Soundings()   | the sounding case and its interpolation grid |
| wind       | OPT     | Wind group       | Wind()        | wind and turbulence; default is no wind |
| notes      | OPT     | -                | ""            | provenance: forecast, sounding case, estimate, date |

### Atmosphere
| field     | REQ/OPT | unit / choices            | default | what it does |
|-----------|---------|---------------------------|---------|--------------|
| model     | OPT     | isa \| sounding \| field  | "isa"   | atmosphere model; "isa" needs no sounding data |
| humid_air | OPT     | bool                      | False   | True needs a sounding/field dewpoint (model != "isa") |
| dT_K      | OPT     | K                         | 0.0     | ISA launch-day temperature offset (dispersion hook, apps/common/ensemble.py, Step 105); read only by the "isa" tier; 0.0 = off, skipped entirely |

### Soundings
| field             | REQ/OPT | unit / choices | default | what it does |
|-------------------|---------|----------------|---------|--------------|
| case              | OPT     | folder under data/soundings/ | "" | sounding case; "" = unused while model == "isa" |
| horizontal_interp | OPT     | idw \| rbf     | "idw"   | horizontal interpolation; read only once a real case is set |
| grid_top_m        | OPT     | m              | 30000.0 | top of the interpolation grid; read only once a real case is set |
| grid_step_m       | OPT     | m              | 100.0   | vertical grid step; read only once a real case is set |
| idw_epsilon_m     | OPT     | m              | 500.0   | IDW smoothing length; read only with horizontal_interp == "idw" |

### Wind
| field                    | REQ/OPT | unit / choices                       | default | what it does |
|--------------------------|---------|--------------------------------------|---------|--------------|
| model                    | OPT     | none \| analytic \| sounding \| field | "none" | wind model; "none" = no wind |
| ref_ms                   | OPT     | m/s                                  | 0.0     | reference wind speed; read only once model != "none" |
| dir_deg                  | OPT     | deg                                  | 0.0     | meteorological direction: from North, clockwise |
| ref_h_m                  | OPT     | m                                    | 10.0    | height ref_ms is measured at |
| shear_exp                | OPT     | -                                    | 0.143   | power-law shear exponent, "analytic" model only |
| turbulence_model         | OPT     | none \| dryden                       | "none"  | turbulence model; "none" = no turbulence |
| turbulence_sigma_high_ms | OPT     | m/s                                  | 0.0     | turbulence intensity (sigma); read only once turbulence_model != "none" |
| turbulence_ref_speed_ms  | OPT     | m/s                                  | 100.0   | turbulence reference speed; read only once turbulence_model != "none" |
| turbulence_seed          | OPT     | -                                    | 0       | RNG seed for the turbulence model; fix it for reproducible runs |
"""

from __future__ import annotations

from configs.schema import Weather
from sim.params import Atmosphere, Soundings, Wind

WEATHER = Weather(
    name="my_weather",  # REQ, - -- registry key; rename to match the filename once you rename it

    atmosphere=Atmosphere(  # OPT, Atmosphere group -- atmosphere model; default is dry ISA
        model="isa",       # OPT, isa | sounding | field -- "isa" needs no sounding data at all
        humid_air=False,   # OPT, bool -- False = dry-air ISA; True needs a sounding/field dewpoint (model != "isa")
        # Switch to "sounding" or "field" later if/when you have real
        # sounding data for the day you're flying (sim/atmosphere.py) --
        # a separate conversation, not needed for a first run.
    ),

    soundings=Soundings(  # OPT, Soundings group -- sounding case and interpolation grid; inert while model == "isa"
        case="",                      # OPT, folder under data/soundings/ -- sounding case; "" = unused while model == "isa"
        horizontal_interp="idw",      # OPT, idw | rbf -- horizontal interpolation; read only once a real case is set
        grid_top_m=30000.0,           # OPT, m -- top of the interpolation grid; read only once a real case is set
        grid_step_m=100.0,            # OPT, m -- vertical grid step; read only once a real case is set
        idw_epsilon_m=500.0,          # OPT, m -- IDW smoothing length; read only with a real case and horizontal_interp == "idw"
        # Leave this whole group at its defaults unless atmosphere.model
        # or wind.model above/below is "sounding" -- this is the shared
        # data layer both read from the same case folder (SS31.3.3).
    ),

    wind=Wind(  # OPT, Wind group -- wind and turbulence; default is no wind
        model="none",                  # OPT, none | analytic | sounding | field -- wind model; "none" = no wind
        ref_ms=0.0,                    # OPT, m/s -- reference wind speed; read only once model != "none"
        dir_deg=0.0,                   # OPT, deg -- meteorological convention: from North, clockwise
        ref_h_m=10.0,                  # OPT, m -- the height ref_ms is measured at
        shear_exp=0.143,               # OPT, - -- power-law shear exponent, "analytic" model only
        turbulence_model="none",       # OPT, none | dryden -- turbulence model; "none" = no turbulence
        turbulence_sigma_high_ms=0.0,  # OPT, m/s -- turbulence intensity (sigma); read only once turbulence_model != "none"
        turbulence_ref_speed_ms=100.0, # OPT, m/s -- turbulence reference speed; read only once turbulence_model != "none"
        turbulence_seed=0,             # OPT, - -- RNG seed for the turbulence model; fix it for reproducible runs
        # Leave this whole group at "none" for a no-wind flight (what
        # isa_dry_calm.py does); fill it in once you want a real wind
        # case, analytic or sounding-driven (sim/wind.py).
    ),

    notes=(
        "My actual weather -- <say where these numbers came from: "
        "forecast, sounding case, estimate, date>."
    ),  # OPT, - -- provenance: forecast, sounding case, estimate, date
)
