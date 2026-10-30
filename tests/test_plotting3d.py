"""Tests for the Step 32 minimal 3D output (architecture-37-step32-3d-
integration-harness.md SS37.3/D-32.3, option O2): `plot_ground_track_3d`/
`plot_trajectory_3d`/`plot_attitude_history_3d`
(`apps.sim.engine.plotting`). Same matplotlib `Agg`-backend convention as
`tests/test_plotting.py`; physics-sanity + smoke checks only, per this
project's testing philosophy -- asserting the DATA SERIES, not the
figure (SS37.7/32.5's own acceptance detail: for a planar run the ground
track must be a straight line along x with y exactly 0.0).
"""

import math

import matplotlib

matplotlib.use("Agg")  # headless -- must run before pyplot is imported
# anywhere else in the process, same precedent as tests/test_plotting.py.

import matplotlib.figure
import numpy as np

from apps.sim.engine.integrate import run_sim_3d
from apps.sim.engine.params import Aero, Lengths, Params, Thrust, Weight
from apps.sim.engine.plotting import (
    plot_attitude_history_3d,
    plot_ground_track_3d,
    plot_trajectory_3d,
)
from apps.sim.engine.quaternion import from_euler
from apps.sim.engine.state3d import State3D, to_vector

_P = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0),
)
_THETA0 = math.radians(45.0)


def _planar_result():
    q0 = from_euler(0.0, _THETA0, 0.0)
    s0 = State3D(r=np.zeros(3), v=np.array([10.0, 0.0, -5.0]), q=q0, omega=np.zeros(3))
    y0 = to_vector(s0)
    return run_sim_3d(_P, y0)


def test_plot_ground_track_3d_is_a_straight_line_along_x_for_a_planar_run():
    r = _planar_result()
    fig = plot_ground_track_3d(r)

    assert isinstance(fig, matplotlib.figure.Figure)
    x_data = fig.axes[0].lines[0].get_xdata()
    y_data = fig.axes[0].lines[0].get_ydata()

    assert np.all(y_data == 0.0)  # bit-exact: no out-of-plane leakage
    assert np.all(np.diff(x_data) > 0.0)  # monotonically increasing downrange


def test_plot_trajectory_3d_returns_a_3d_figure_with_zero_lateral_track():
    r = _planar_result()
    fig = plot_trajectory_3d(r)

    assert isinstance(fig, matplotlib.figure.Figure)
    line = fig.axes[0].lines[0]
    _xs, ys, _zs = line._verts3d
    assert np.all(np.asarray(ys) == 0.0)


def test_plot_attitude_history_3d_matches_the_known_constant_pitch():
    """This scenario (`C_z=C_m=0.0`, on-axis thrust) holds theta exactly
    constant -- the recovered pitch history must match `_THETA0` (deg)
    at every sample, the harness-level analogue of `tests/
    test_forces3d.py`'s own `_s2d` round-trip check."""
    r = _planar_result()
    fig = plot_attitude_history_3d(r)

    assert isinstance(fig, matplotlib.figure.Figure)
    assert len(fig.axes) == 3
    yaw_deg = fig.axes[0].lines[0].get_ydata()
    pitch_deg = fig.axes[1].lines[0].get_ydata()
    roll_deg = fig.axes[2].lines[0].get_ydata()

    assert np.allclose(yaw_deg, 0.0, atol=1e-9)
    assert np.allclose(pitch_deg, math.degrees(_THETA0), atol=1e-9)
    assert np.allclose(roll_deg, 0.0, atol=1e-9)
