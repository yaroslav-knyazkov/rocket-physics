# Review round 3 - handover notes

1. Frames: removed d/dt definitions of v, a, omega_r, epsilon_r from sec:frames; they live once in
   sec:states (eq:state_kinematics). Frames only names the quantities. Conventions appendix also
   lost the derivative.
2. A_m sign: KEPT (A_m = -qSc C_m y_r, positive C_m nose-down). Evidence: sim/forces.py
   aero_moment_y returns -A_m with A_m = q S d_ref C_m; dynamics sums it into M_y -> domega/dt;
   switching would contradict code and numeric pins. Conventions now states the convention and its
   consequences (C_m,alpha > 0 and C_m,q > 0 stable). analysis.tex re-trimmed, signs unchanged.
3. Models intro / references / gravity: verified, unchanged in substance. Backward pointers to
   Rocket 2D removed except where an equation is used (eq:aero_magnitudes now labelled in Rocket 2D).
4. Thrust: mass flow written \dot m_m everywhere (thrust formula, mass, states eq, variable-mass
   terms, notation table row added). Thrust magnitude and direction text shortened.
5. Mass: eq:mass_motor (m_m = m_0 + integral of \dot m_m, clamp m_m >= m_f) placed above the two
   models; linear and ISP models only supply \dot m_m.
6. Sweep: all files trimmed (models -237 lines, analysis -100, rocket-2d -14, appendix -4, backlog -1).

Open points / for the user:
- data/aero/example.csv: C_m has a NEGATIVE slope in alpha and its header calls it "restoring".
  In the code's sign (positive C_m nose-down) a negative slope is destabilising; the table is
  still stable only because the l1 (CoP aft) term dominates. Table comment or sign likely wrong.
- Cross-check: eq:pitch_damping_moment label is now unreferenced (harmless).
- Compile: 0 errors, 0 undefined refs, 0 overfull (one pre-existing Underfull in introduction).
