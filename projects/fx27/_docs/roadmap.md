## Кратко (RU)

- Живой roadmap проекта fx27, 2 секции: **General** (point-mass / vehicle-dynamics трек, этот оркестратор) и **Controller** (трек замкнутого контура, параллельная сессия — секция оставлена как заглушка, не моя зона).
- Протокол id: `<тип солвера>.<номер>`. Стадия 1 = point-mass (весь текущий трек). Стадия 2 = 2D (будущее, см. roadmap-пункт F7). Стадия 3 = 3D/6DOF (будущее). Номер внутри стадии — просто хронологический порядковый, без букв/групп.
- 2 поправки к списку пользователя (см. "Notes" под таблицей): пункт "euroc dm" никогда не был реализован (нет исходника у sibling-репозитория); пункт "airbrake sizing" — тот же артефакт, что и ideal-airbrake-строки 1.4/1.8, не отдельный шаг.

---

# fx27 Roadmap

## General

**Version-id protocol:** `<solver-stage>.<sequence>`.

- **Stage 1 — point mass.** Everything below right now. Attitude frozen (`C_z=C_m=c_mq=0`), one reference radius per rocket, no fin/CP geometry.
- **Stage 2 — 2D rigid body.** Reserved for when attitude dynamics turn back on (vehicle-dynamics roadmap item F7 — "very likely turn `omega`/`C_z`/`C_m` back on"). First item there is `2.1`, not a continuation of stage 1's numbering.
- **Stage 3 — 3D / full 6DOF.** Reserved the same way; first item `3.1`.

Sequence within a stage is plain chronological order of when the work actually happened — not grouped/lettered by analysis type (cspace vs euroc, dc vs dm are called out in the `name` column instead).

| id | name | current file | description |
|----|------|---|---|
| 1.1 | Cspace comparison (constant drag) | `runs/point/comparison.py --case cspace` | Baseline 3-rocket cspace flight comparison, constant-C_x (dc) rockets only. |
| 1.2 | Cspace ideal mass (constant drag) | `runs/point/ideal_mass.py` (dc rows) | Solves the minimum airframe mass that hits the 2500 m target apogee, per dc rocket. |
| 1.3 | Cspace ideal drag (constant drag) | `runs/point/ideal_drag.py` (dc rows) | Solves the C_x scale factor that hits the target apogee, per dc rocket. |
| 1.4 | Cspace ideal airbrake sizing (constant drag) | `runs/point/ideal_open_airbrake.py` (dc rows) | Open-loop Cd×Area brake sizing against the target apogee, 4 ideal dc variants. |
| 1.5 | Cspace comparison (Mach-dependent drag) | `runs/point/comparison.py --case cspace_dc_dm` | Same comparison, dc+dm rockets merged into one 7-row table. |
| 1.6 | Cspace ideal mass (Mach-dependent drag) | `runs/point/ideal_mass.py` (dm rows) | Same as 1.2, for the 3 dm rockets. |
| 1.7 | Cspace ideal drag (Mach-dependent drag) | `runs/point/ideal_drag.py` (dm rows) | Same as 1.3, for dm. |
| 1.8 | Cspace ideal airbrake sizing (Mach-dependent drag) | `runs/point/ideal_open_airbrake.py` (dm rows) | Same as 1.4, for the 4 ideal dm variants. |
| 1.9 | Euroc motor sweep, fx27-parity columns | `runs/point/comparison.py --case euroc` | 24 (config, motor) combos, fx27's own simpler flight-column set. |
| 1.10 | Euroc motor sweep, feasibility view | `runs/point/sweep.py` | Same 24 combos, richer columns (`J_total`, `t_burn`, `T/W`, `q_max`, `m_burnout`) for picking a motor per airframe. |
| 1.11 | Euroc motor sweep (Mach-dependent drag) | — not built | Deferred — the sibling repo has no euroc "dm" source to port from (see Notes). |
| 1.12 | Final cross-campaign comparison | `runs/point/comparison.py` (any `--case`) | Wrap-up comparison once configurations were chosen across cspace + euroc, dc + dm. |
| 1.13 | Theory-based Mach-dependent drag (in progress) | `data/cspace/aero/drag_theory.py`, `generate_theory_drag_tables.py` | Niskanen/OpenRocket-method C_D0(M) from component geometry, side-by-side comparison variant. Currently `PRO54_TRANSITION_DM` only. |

### Notes

- **1.11 was never built.** Not a gap in this doc — a real gap in the project. The sibling repo this project ports from has no euroc Mach-dependent-drag data to port.
- **"Airbrake sizing" is not a separate id.** It's the same artifact as 1.4/1.8 (`ideal_open_airbrake.py`) — cspace-only, dc+dm, never touched euroc. No distinct later version of it exists.
- **1.10 (`sweep.py`) is the "choosing a configuration" step**, not 1.9 — it's the richer, feasibility-metric view (`apps/optimization/motor_selection`) that's actually useful for picking a motor; 1.9 just replicates fx27's own simpler column set for a side-by-side check.

## Controller

*(Reserved for the controller-track session — not written by this track.)*
