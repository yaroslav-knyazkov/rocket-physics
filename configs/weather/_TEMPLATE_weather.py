"""configs/weather/_TEMPLATE_weather.py -- TEMPLATE, fill in your own
numbers (Step 72, dev/docs/architecture-31-config-separation.md SS31.5).

This file is a blank `Weather` piece: one flying day's air -- the
atmosphere model, the sounding case it may read, and the wind, all in
one piece because a single radiosonde ascent measures all three
(SS31.3.3, D-53). Every field below is commented with its unit, its
meaning, and the consequence of leaving it at the placeholder value.

This module is **never registered** -- it is deliberately absent from
`configs/weather/__init__.py`'s `_MODULES` tuple, and must stay
absent. It still imports cleanly on its own --
`python -c "import configs.weather._TEMPLATE_weather"` must succeed --
so the file does not silently rot; pinned by
`tests/test_config_registries.py` (SS31.8 #6).

To use this template:
  1. Fill in every `# <-- fill this in` field below with your own numbers.
  2. Rename this file (and the `name="my_weather"` string below) to
     whatever you want your weather called.
  3. Add `from configs.weather import <your_module_name>` and one line
     to `configs/weather/__init__.py`'s `_MODULES` tuple.
"""

from __future__ import annotations

from configs.schema import Weather
from sim.params import Atmosphere, Soundings, Wind

WEATHER = Weather(
    name="my_weather",  # <-- rename this string to match the filename once you rename it

    atmosphere=Atmosphere(
        model="isa",       # <-- isa | sounding | field; "isa" needs no sounding data at all
        humid_air=False,   # <-- dry-air ISA; True needs a sounding/field dewpoint (model != "isa")
        # Switch to "sounding" or "field" later if/when you have real
        # sounding data for the day you're flying (sim/atmosphere.py) --
        # a separate conversation, not needed for a first run.
    ),

    soundings=Soundings(
        case="",                      # <-- fill this in: case folder under data/soundings/; "" = unused while model == "isa"
        horizontal_interp="idw",      # <-- idw | rbf; read only once a real case is set
        grid_top_m=30000.0,           # <-- m; read only once a real case is set
        grid_step_m=100.0,            # <-- m; read only once a real case is set
        idw_epsilon_m=500.0,          # <-- m; read only once a real case is set and horizontal_interp == "idw"
        # Leave this whole group at its defaults unless atmosphere.model
        # or wind.model above/below is "sounding" -- this is the shared
        # data layer both read from the same case folder (SS31.3.3).
    ),

    wind=Wind(
        model="none",                  # <-- none | analytic | sounding | field
        ref_ms=0.0,                    # <-- fill this in: reference wind speed, m/s; read only once model != "none"
        dir_deg=0.0,                   # <-- meteorological convention, from North, clockwise, deg
        ref_h_m=10.0,                  # <-- m; the height ref_ms is measured at
        shear_exp=0.143,               # <-- [-]; power-law shear exponent, "analytic" model only
        turbulence_model="none",       # <-- none | dryden
        turbulence_sigma_high_ms=0.0,  # <-- m/s; read only once turbulence_model != "none"
        turbulence_ref_speed_ms=100.0, # <-- m/s; read only once turbulence_model != "none"
        turbulence_seed=0,             # <-- RNG seed for the turbulence model; fix it for reproducible runs
        # Leave this whole group at "none" for a no-wind flight (what
        # isa_dry_calm.py does); fill it in once you want a real wind
        # case, analytic or sounding-driven (sim/wind.py).
    ),

    notes=(
        "My actual weather -- <say where these numbers came from: "
        "forecast, sounding case, estimate, date>."
    ),
)
