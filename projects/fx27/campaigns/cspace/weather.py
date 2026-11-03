"""projects/fx27/campaigns/cspace/weather.py -- cspace weather (dev/docs/
architecture-38-fx27-port.md SS38.4.1): default rocketpy `Environment`,
i.e. ISA, dry air, no wind, no sounding case.
"""

from __future__ import annotations

from apps.sim.schema import Weather
from apps.sim.engine.params import Atmosphere, Soundings, Wind

WEATHER = Weather(
    name="cspace_isa",  # REQ, - -- identifies this piece
    atmosphere=Atmosphere(
        model="isa",  # REQ, isa | sounding | field -- fx27 supplies no sounding data for cspace
        humid_air=False,  # OPT, bool -- False = dry-air ISA (fx27 default)
        dT_K=0.0,  # OPT, K -- no launch-day offset
    ),
    soundings=Soundings(),  # OPT -- inert while atmosphere.model == "isa"
    wind=Wind(model="none"),  # REQ, none | ... -- fx27 cspace launch_data.py sets no wind
    notes="fx27 data/cspace/launch_data.py: default rocketpy Environment, no wind, no sounding.",
)
