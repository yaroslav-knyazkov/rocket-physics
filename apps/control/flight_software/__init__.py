"""Flight software under design (Phase 2.17 Milestone M3, architecture-35-
paper-alignment.md SS35.4.4) -- estimator + sampled laws. Imports sim/ and
registers into sim.control at import time; sim/ never imports this
package (rationale: controller experiments churn constantly and must not
touch the physics package or its pins, SS35.4's own layering rule).

Importing this package (`import apps.control.flight_software`, or any of
its submodules) is what makes `p.control.airbrake_model in
("proportional_drag", "pi_apogee")` resolvable at all --
sim.control.known_sampled_laws() is empty until this module's own
import-time side effect runs once.
"""

from sim import control

from apps.control.flight_software import laws

control.register_sampled_law("proportional_drag", laws.proportional_drag)
control.register_sampled_law("pi_apogee", laws.pi_apogee)
