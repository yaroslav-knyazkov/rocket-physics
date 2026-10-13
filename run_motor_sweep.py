"""Root wrapper 2 of 5 (roadmap.md Step 69, D-29): the motor selection
sweep app, `apps/motor_selection/compare_motors.py`'s `main()` -- a front
door so `python run_motor_sweep.py` works the same way `python run.py`
does, without replacing the app's own
`python -m apps.motor_selection.compare_motors` invocation
(architecture-30-apps-4-5-and-configs.md SS30.3)."""

from apps.motor_selection.compare_motors import main

if __name__ == "__main__":
    main()
