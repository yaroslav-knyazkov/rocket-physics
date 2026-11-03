"""projects/fx27/campaigns/euroc/site.py -- euroc launch site (dev/docs/
architecture-38-fx27-port.md SS38.4.1), mirroring fx27 data/euroc/
launch_data.py's `Environment` + rail fields.
"""

from __future__ import annotations

from apps.sim.schema import LaunchSite
from apps.sim.engine.params import Site

SITE = LaunchSite(
    name="euroc",  # REQ, - -- identifies this piece
    site=Site(
        lat0_deg=39.3897,  # REQ, deg -- fx27 Environment(latitude=39.3897)
        lon0_deg=-8.2890,  # REQ, deg -- fx27 Environment(longitude=-8.2890)
        h0_m=160.0,  # REQ, m -- fx27 Environment(elevation=160.0)
        azimuth_deg=133.0,  # REQ, deg -- fx27 heading=133.0. The library default is 90.0 --
        #                             must be set explicitly (SS38.4.1); cosmetic in a 2D,
        #                             no-wind run.
        L_rail=12.0,  # REQ, m -- fx27 rail_length=12.0
        rail_angle_deg=84.0,  # REQ, deg -- fx27 inclination=84.0
    ),
    notes=(
        "fx27/simulation data/euroc/launch_data.py: Environment(lat/lon/elevation) + "
        "rail_length/inclination/heading. ISA atmosphere, no wind, no sounding -- see "
        "euroc/weather.py."
    ),
)
