"""Tests for apps/_shared/ (Step 64, roadmap.md,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.5/SS30.8; renamed
from tests/test_apps_common.py at Phase 2.19 Step 131,
dev/docs/architecture-apps-sim-restructure.md, following apps/common/'s
move to apps/_shared/).

`tests/test_motor_selection.py` must not be edited for this step (the
ticket's own gate), so this is a new, separate file. Its one pinned check
is the identity the whole promotion rests on: `compare_motors.MotorStats`
must be `apps._shared.flight_stats.FlightStats` itself -- not an equal but
separate dataclass -- so the re-export can never silently drift into a
second, divergent definition.
"""

import apps._shared.flight_stats as flight_stats_module
from apps.optimization.motor_selection import compare_motors


def test_motor_stats_alias_is_flight_stats_identity():
    """`compare_motors.MotorStats` is the same object as
    `apps._shared.flight_stats.FlightStats` (identity, not just equality) --
    the promotion (Step 64) re-exports rather than re-defines."""
    assert compare_motors.MotorStats is flight_stats_module.FlightStats
