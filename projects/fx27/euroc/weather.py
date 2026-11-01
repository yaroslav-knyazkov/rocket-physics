"""projects/fx27/euroc/weather.py -- euroc weather (dev/docs/
architecture-38-fx27-port.md SS38.4.1): default rocketpy `Environment`,
i.e. ISA, dry air, no wind, no sounding case -- same choice as cspace.
"""

from __future__ import annotations

from apps.sim.schema import Weather
from apps.sim.engine.params import Atmosphere, Soundings, Wind

WEATHER = Weather(
    name="euroc_isa",  # REQ, - -- identifies this piece
    atmosphere=Atmosphere(
        model="isa",  # REQ, isa | sounding | field -- fx27 supplies no sounding data for euroc
        humid_air=False,  # OPT, bool -- False = dry-air ISA (fx27 default)
        dT_K=0.0,  # OPT, K -- no launch-day offset
    ),
    soundings=Soundings(),  # OPT -- inert while atmosphere.model == "isa"
    wind=Wind(model="none"),  # REQ, none | ... -- fx27 euroc launch_data.py sets no wind
    notes="fx27 data/euroc/launch_data.py: default rocketpy Environment, no wind, no sounding.",
)
