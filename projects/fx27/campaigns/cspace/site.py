"""projects/fx27/campaigns/cspace/site.py -- cspace launch site (dev/docs/
architecture-38-fx27-port.md SS38.4.1), mirroring fx27 data/cspace/
launch_data.py's `Environment` + rail fields.
"""

from __future__ import annotations

from apps.sim.schema import LaunchSite
from apps.sim.engine.params import Site

SITE = LaunchSite(
    name="cspace",  # REQ, - -- identifies this piece
    site=Site(
        lat0_deg=43.218436,  # REQ, deg -- fx27 Environment(latitude=43.218436)
        lon0_deg=-0.047333,  # REQ, deg -- fx27 Environment(longitude=-0.047333)
        h0_m=428.96,  # REQ, m -- fx27 Environment(elevation=428.96)
        azimuth_deg=0.0,  # REQ, deg -- fx27 heading=0.0. The library default is 90.0, NOT 0.0,
        #                            so this must be set explicitly (SS38.4.1); purely cosmetic
        #                            in a 2D, no-wind run (no lateral axis to point along).
        L_rail=5.0,  # REQ, m -- fx27 rail_length=5.0
        rail_angle_deg=85.0,  # REQ, deg -- fx27 inclination=85.0 (elevation from horizontal,
        #                                     same sense as this project's rail_angle_deg)
    ),
    notes=(
        "fx27/simulation data/cspace/launch_data.py: Environment(lat/lon/elevation) + "
        "rail_length/inclination/heading. ISA atmosphere, no wind, no sounding -- see "
        "cspace/weather.py."
    ),
)
