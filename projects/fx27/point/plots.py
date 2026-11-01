"""projects/fx27/point/plots.py -- fx27's `point_comparison.
plot_displacement_comparison` (2x2) and `plot_kinematics_comparison`
(2x3), assembled entirely from public `apps/` helpers (dev/docs/
architecture-38-fx27-port.md SS38.5.6). No `apps/` change: `flight_path_
angle` and `frames.to_body` are already public; the rest is dense-grid
sampling + matplotlib layout.

`_variant_style`/`_family_colors` read fx27's own naming convention
(SS38.5.2: `"<family>"` / `"<family> (ideal mass)"` / `"<family> (ideal
drag)"`) -- that string IS the styling protocol, not a separate lookup
table.

fx27's `hypot(x, y)` downrange collapse is deliberately NOT reproduced:
this engine's model is planar, so `y[X]` already *is* the downrange
(SS38.13's rejected-options table) -- copying the `hypot` would be
cargo-culting a correction this project does not need.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from apps._shared.flight_stats import flight_path_angle
from apps.sim.engine import dynamics, frames
from apps.sim.engine.gravity import altitude_agl
from apps.sim.engine.integrate import Result
from apps.sim.engine.state import THETA, VX, VZ, X

_GRID_N = 500


def _ascent_grid(r: Result) -> np.ndarray:
    """Dense time grid, clipped at apogee -- fx27's figures are
    ascent-only (`terminate_on_apogee=True`); this engine's apogee event
    is non-terminal, so the clip is explicit here (SS38.5.6)."""
    t_apogee = r.events.get("apogee")
    t_end = t_apogee if t_apogee is not None else float(r.t[-1])
    return np.linspace(0.0, t_end, _GRID_N)


def _series(r: Result) -> dict:
    t = _ascent_grid(r)
    y = r.raw.sol(t)
    p = r.params

    x = y[X]
    altitude = altitude_agl(y, p)
    vx, vz = y[VX], y[VZ]
    theta = y[THETA]
    theta_v = flight_path_angle(vx, vz)
    speed = np.hypot(vx, vz)

    # D-20's idiom (flight_stats.max_accel): re-evaluate the RHS the
    # integrator itself saw, not a finite-difference of the velocity grid.
    dydt = np.array([dynamics.derivatives(ti, y[:, i], p) for i, ti in enumerate(t)])
    ax, az = dydt[:, VX], dydt[:, VZ]
    accel = np.hypot(ax, az)

    v_body = np.array([frames.to_body(np.array([vx[i], vz[i]]), theta[i]) for i in range(t.size)])
    a_body = np.array([frames.to_body(np.array([ax[i], az[i]]), theta[i]) for i in range(t.size)])

    return dict(
        t=t, x=x, altitude=altitude, theta_v=theta_v, speed=speed, accel=accel,
        vx_body=v_body[:, 0], vz_body=v_body[:, 1],
        ax_body=a_body[:, 0], az_body=a_body[:, 1],
    )


def _family(name: str) -> str:
    """Strip the `" (ideal mass)"`/`" (ideal drag)"` suffix (SS38.5.2's
    naming convention IS the styling protocol, SS38.5.6)."""
    return name.split(" (", 1)[0]


def _variant(name: str) -> "str | None":
    if "(" not in name:
        return None
    return name.rsplit("(", 1)[1].rstrip(")")


def _family_colors(names: "list[str]") -> "dict[str, str]":
    cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0", "C1", "C2", "C3", "C4", "C5"])
    families = sorted({_family(n) for n in names})
    return {fam: cycle[i % len(cycle)] for i, fam in enumerate(families)}


def _variant_style(name: str) -> str:
    """Solid for the base, dashed for "ideal mass", dotted for "ideal
    drag" -- same per-family colour, variant distinguished by linestyle
    (fx27's own `_variant_style` behaviour, copied in spirit)."""
    variant = _variant(name)
    if variant is None:
        return "-"
    if "mass" in variant:
        return "--"
    if "drag" in variant:
        return ":"
    return "-."


def plot_displacement_comparison(results: "dict[str, Result]", title: str = "Displacement comparison"):
    """2x2: `z(x)` flight path, `theta(t)` flight-path angle, `z(t)`
    altitude, `x(t)` downrange (fx27's own 4-panel figure, SS38.5.6)."""
    colors = _family_colors(list(results))
    fig, ((ax_zx, ax_theta), (ax_zt, ax_xt)) = plt.subplots(2, 2, figsize=(12, 9))
    for name, r in results.items():
        s = _series(r)
        color = colors[_family(name)]
        style = _variant_style(name)
        ax_zx.plot(s["x"], s["altitude"], color=color, linestyle=style, label=name)
        ax_theta.plot(s["t"], np.degrees(s["theta_v"]), color=color, linestyle=style, label=name)
        ax_zt.plot(s["t"], s["altitude"], color=color, linestyle=style, label=name)
        ax_xt.plot(s["t"], s["x"], color=color, linestyle=style, label=name)

    ax_zx.set_xlabel("Downrange x [m]"); ax_zx.set_ylabel("Altitude [m]"); ax_zx.set_title("Flight path z(x)")
    ax_theta.set_xlabel("Time [s]"); ax_theta.set_ylabel("Flight-path angle [deg]"); ax_theta.set_title("theta_v(t)")
    ax_zt.set_xlabel("Time [s]"); ax_zt.set_ylabel("Altitude [m]"); ax_zt.set_title("z(t)")
    ax_xt.set_xlabel("Time [s]"); ax_xt.set_ylabel("Downrange [m]"); ax_xt.set_title("x(t)")
    for ax in (ax_zx, ax_theta, ax_zt, ax_xt):
        ax.grid(True)
    ax_zx.legend(fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def plot_kinematics_comparison(results: "dict[str, Result]", title: str = "Kinematics comparison"):
    """2x3: `|v|(t)`, body-axis `v_x`/`v_z`, `|a|(t)`, body-axis `a_x`/
    `a_z` (fx27's own 6-panel figure, SS38.5.6). The "body axis" here is
    the real `theta` state, not fx27's hand-rolled frozen axis -- under
    Option C `theta` happens to be constant at the rail angle (SS38.2.1),
    so the two agree by construction."""
    colors = _family_colors(list(results))
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    (ax_v, ax_vxb, ax_vzb), (ax_a, ax_axb, ax_azb) = axes
    for name, r in results.items():
        s = _series(r)
        color = colors[_family(name)]
        style = _variant_style(name)
        ax_v.plot(s["t"], s["speed"], color=color, linestyle=style, label=name)
        ax_vxb.plot(s["t"], s["vx_body"], color=color, linestyle=style, label=name)
        ax_vzb.plot(s["t"], s["vz_body"], color=color, linestyle=style, label=name)
        ax_a.plot(s["t"], s["accel"], color=color, linestyle=style, label=name)
        ax_axb.plot(s["t"], s["ax_body"], color=color, linestyle=style, label=name)
        ax_azb.plot(s["t"], s["az_body"], color=color, linestyle=style, label=name)

    ax_v.set_title("|v|(t)"); ax_v.set_ylabel("m/s")
    ax_vxb.set_title("v_x body (frozen at rail angle)")
    ax_vzb.set_title("v_z body (frozen at rail angle)")
    ax_a.set_title("|a|(t)"); ax_a.set_ylabel("m/s^2")
    ax_axb.set_title("a_x body (frozen at rail angle)")
    ax_azb.set_title("a_z body (frozen at rail angle)")
    for ax in (ax_v, ax_vxb, ax_vzb, ax_a, ax_axb, ax_azb):
        ax.set_xlabel("Time [s]")
        ax.grid(True)
    ax_v.legend(fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    return fig
