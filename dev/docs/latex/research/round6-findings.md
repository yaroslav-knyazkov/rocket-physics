# Round 6 findings: T1 high-alpha aerodynamics, T2 variable-mass rotation, T3 grain geometry, T4 pitch damping

Scope: facts only, no decisions. Date 2026-10-17. Tags: [SRC] stated in a retrieved source; [DERIVED] my own algebra from sourced facts; [ASSUMPTION] not sourced.
Earlier sources (restodo-findings.md items 2, 6, 13, Q-A, Q-C) are cited by item number, not repeated.

## T1. High / full-range angle-of-attack aerodynamics

**Answer.**

(a1) Allen-Perkins viscous crossflow (originally alpha up to ~20-30 deg) [SRC: Allen & Perkins, "Characteristics of flow over inclined bodies of revolution", https://digital.library.unt.edu/ark:/67531/metadc58746/m2/1/high_res_d/19930086529.pdf], wind axes:
- C_L = (k2-k1)(S_b/A) sin2a cos(a/2) + eta*c_dc*(A_p/A) sin^2a cos a
- C_DF = C_DF(a=0) cos^3 a + (k2-k1)(S_b/A) sin2a sin(a/2) + eta*c_dc*(A_p/A) sin^3 a
- c_dc = section drag of an infinite circular cylinder, "constant and equal to 1.2" for cross-Reynolds number ~1e4 to 2e5 at low cross Mach number; eta = finite/infinite cylinder drag ratio; A_p planform area, A reference area, S_b base area.
- Consistency check: D = N sin a + A cos a applied to the body-axis form below gives exactly these cos^3 / sin^3 terms [DERIVED].

(a2) Jorgensen, NASA TN D-6996 (1972), "Prediction of static aerodynamic characteristics for space-shuttle-like and other bodies at angles of attack from 0 to 180 deg", https://ntrs.nasa.gov/api/citations/19730006261/downloads/19730006261.pdf. Body axes, bodies of revolution [SRC, eqs. 1-3 as extracted]:
- C_N = (A_b/A) sin2a' cos(a'/2) + eta*C_dn*(A_p/A) sin^2 a',  0 <= a <= 180 deg (eq. 1)
- C_A = C_A(a=0) cos^2 a for 0-90 deg; C_A = C_A(a=180) cos^2(180-a) for 90-180 deg (eqs. 2-3)
- C_m = [(V - A_b(l - x_m))/(A d)] sin2a' cos(a'/2) + eta*C_dn*(A_p/A)((x_m - x_c)/d) sin^2 a' (0-90 deg; eq. 5 for 90-180 deg not captured).
- First term = slender-body potential theory, second = viscous crossflow. The form (C_Nalpha/2) sin2a cos(a/2) is the same with C_Nalpha = 2 A_b/A [DERIVED]. The definition of a' and the sign convention of C_N beyond 90 deg were not captured by the extraction; read pp. 3-6 of the PDF before quoting them.
- Crossflow: M_n = M sin a, Re_n = Re sin a (eqs. 7-8) [SRC]. C_dn(M_n) per Jorgensen Fig. 1 as tabulated by HPR Sim (https://hpr.fusionspace.co/physics/aero.html): 1.20 up to M_n 0.2, 1.334 at 0.5, 1.985 at 1.0, 1.266 at 4.8. Supercritical Re_n: C_dn can fall to "between about 0.15 and 0.30" (Jorgensen p. 15, quoted by the HPR page) [SRC, secondary].
- eta (Jorgensen Fig. 4, circular cylinder, Re_n = 88000), L/d -> eta: 1 -> 0.52; 1.5 -> 0.57; 3 -> 0.62; 4.5 -> 0.62; 8 -> 0.64; 10 -> 0.68; 12 -> 0.70; 18 -> 0.73; 20 -> 0.76; 40 -> 0.82 [SRC]. Measured "only at very low subsonic Mach numbers"; for supersonic/hypersonic eta "probably can be assumed to be unity" [SRC].
- Broadside (a = 90 deg): all normal force is the viscous term [SRC]; C_N(90) = eta*C_dn*A_p/A, so eta*C_dn ~ 0.62-0.98 for L/d 1-40 with C_dn = 1.2 [DERIVED from the two tables].
- Validity [SRC]: Allen's approach agrees with data to ~20 deg; "at higher alpha ... little or no verification, but logic dictates that it should give increasingly better results as alpha increases to 90 deg". NASA TR R-474 (Jorgensen 1977, https://ntrs.nasa.gov/citations/19770026166): agreement for M 0.6-2.9; alpha 0-180 deg only at M = 2.9, 0-60 deg for M 0.6-2.0.
- C_A(0) and C_A(180) are computed or measured separately (wave + skin friction + base pressure) [SRC: TN D-6996 contents], so the axial magnitude differs between 0 and 180 deg; the cos^2 model gives C_A = 0 at 90 deg.

(a3) Newtonian / modified Newtonian: used by Jorgensen only for cross-section shape ratios C_N/(C_N)cir (slender-body vs Newtonian compared) and noted as successful at hypersonic booster conditions [SRC: TN D-6996; NASA TN D-7228 https://ntrs.nasa.gov/api/citations/19730012271/downloads/19730012271.pdf]. C_p = C_p,max cos^2(local incidence) not re-sourced [ASSUMPTION: textbook]; low relevance at M < 1.

(a4) Missile DATCOM: modified Allen-Perkins below 30 deg and Jorgensen slender-body theory above 30 deg, with a visible discontinuity near 30 deg at M ~0.9-1.1 [SRC: Nguyen et al., J. JSASS 57 (2014), https://doi.org/10.2322/tjsass.57.210]. Version 97 rated to alpha 90 deg [SRC: AIAA 2004-1246, http://mae-nas.eng.usu.edu/MAE_5900_Web/5900/USLI_2010/Flight_Mechanics/missile_datcom/datcom_assessment.pdf; Abney & McDaniel AIAA 2005-5086: "reasonably predict ... up to 90 degrees", subsonic]. Normal force underpredicted above ~50 deg on a Standard Missile model [SRC: Dunn 1989, http://hdl.handle.net/10945/26851]. Methods reaching 180 deg: Baker 1978 (0.6<M<3.0, 0-180 deg), Devan/Mason/Moore AIAA-82-0250 (M up to 8, alpha 180) [SRC: Dunn table; citation lists at https://doi.org/10.2514/6.1999-4258]. Max 20 alphas per case [SRC: user guide].

(a5) Rocket tools:
- OpenRocket axial drag vs alpha: "two-part polynomial ... starts from 1 at alpha=0, increases to 1.3 at alpha=17 deg and then decreases to zero at alpha=90 deg; the derivative is also zero at these points"; empirical, no reference [SRC: techdoc quoted at https://www.rocketryforum.com/threads/openrocket-angle-of-attack-and-drag-scaling.140006/]. OpenRocket fin C_Nalpha uses min(alpha, pi - alpha, STALL_ANGLE), a reflection about 90 deg [SRC: FinSetCalc.java, https://www.javatips.net/api/openrocket-master/core/src/net/sf/openrocket/aerodynamics/barrowman/FinSetCalc.java]. Techdoc distinguishes C_D from C_A beyond zero alpha [SRC: techdoc 3.4].
- RASAero II: coefficients each step from Mach, alpha, Re, power on/off; alpha between 0 and 15 deg via Run Test; body viscous crossflow by Jorgensen's method in the Rogers Modified Barrowman option [SRC: https://www.rasaero.com/dloads/RASAero%20II%20Users%20Manual.pdf; https://www.nakka-rocketry.net/Appendix-C.htm].
- HPR Sim: Barrowman slope * sin a / a plus body lift eta*C_dn*(A_plan/A_ref) sin^2 a (Jorgensen eq. 2.12); earlier used Galejs K (1.0-1.5) * (A_p/A_ref) sin^2 a [SRC: HPR page; Cambridge note eq. 34].
- ESDU 89014: C_N = C_Nalpha0 sin a cos a + crossflow term, alpha to 90 deg, M to 5 [SRC secondary: https://www.aspirespace.org.uk/downloads/Rocketry%20aerodynamics.pdf].

(b) Practitioner extensions found [SRC]: (i) one formula = attached small-alpha term + sin^2 a crossflow term (Allen-Perkins/Jorgensen, DATCOM, RASAero, HPR Sim); (ii) method switch at a threshold, discontinuity accepted (DATCOM at 30 deg); (iii) reflection alpha -> 180-alpha (OpenRocket fins; Jorgensen separate C_A(180)); (iv) axial coefficient scaled by cos^2 a (Jorgensen) or a fitted polynomial (OpenRocket). A C_x0 cos^2 a fit is Jorgensen's eq. 2. No source found describing blending CFD at small alpha with a crossflow model at a defined matching alpha beyond these [absence of evidence].

(c) Experimental data, 0-180 deg:
- NASA TM X-1658, Jernell (1968), Langley Unitary Plan tunnel: cylinder, cone-cylinder, ogive-cylinder bodies, M 1.50-2.86, alpha -5 to 185 deg, Re = 1.0e6 per ft, moments at 50% length; normal force follows planform area; more rearward planform centroid -> more rearward CP [SRC: https://ntrs.nasa.gov/api/citations/19680026721/downloads/19680026721.pdf].
- TN D-6996 compares its method to nine bodies at M = 2.86 (alpha 0-180) [SRC]; a rocket booster model M 0.6-4, alpha 0-180 [SRC: TN D-7228 introduction].
- Low-speed finite cylinders: Wieselsberger (L/D = 5, normal flow), Zdravkovich, Hoerner "Fluid-Dynamic Drag"; CFD study of L/D 1 and 2 at yaw 0-90 deg: normal-flow drag nearly independent of aspect ratio at supercritical Re, experimental data at intermediate yaw for short cylinders "not available in the literature" [SRC: Prosser & Smith AIAA 2015-1931, https://fun3d.larc.nasa.gov/papers/aiaa-2015-1931.pdf]. Hoerner's table (https://archive.org/stream/FluidDynamicDragHoerner1965/Fluid-dynamic_drag__Hoerner__1965_djvu.txt) not read.
- AGARD datasets: none identified.

**Recommendation for the report.**
- Use Jorgensen's structure: C_N = attached term + eta*C_dn*(A_p/S) sin^2 a; C_A = C_A(0 or 180) cos^2 a; drag/lift by rotation. State validity: unverified above ~20 deg at subsonic speed; Re_n = Re sin a may be supercritical (C_dn 0.15-1.2).
- Broadside drag magnitude ~ eta*C_dn*A_p/S with eta*C_dn ~ 0.6-1.0 for L/d 1-40; axial magnitude goes to ~0 at 90 deg in both Jorgensen and OpenRocket scaling, consistent with the report's sign factor f(alpha) ~ 0 near 90 deg [DERIVED].
- Open: C_A(180) for the project body (blunt base first); Jorgensen eq. 5 / a' convention for a > 90 deg; no AGARD data; Hoerner table.

## T2. Variable-mass rotational dynamics

**Answer.**

Derivation basis [SRC]: moment equation of a non-inertial variable-mass system by control volume (Shames Sec. 5.10; Meirovitch Sec. 12.7; Cornelisse, Schoyer, Wakker "Rocket Propulsion and Spaceflight Dynamics" Sec. 4.2; Flandro et al. Sec. 3.1; Eke & Wang) as cited in van der Ha & Janssens, J. Spacecraft Rockets (2005), http://www.vanderha.com/J-2005b%20Jet%20Damping%20and%20Misalignment.pdf. Split: M_in = M_Cor + M_rel with M_Cor = -2 int r x (w x V_xyz) dm, M_rel = -int r x DV_xyz/Dt dm. History: Rosser et al. first presented jet damping; Ellis & McArthur and Thomson (book, Introduction to Space Dynamics, Dover 1986, ch. 7; AIAA J. 4, 766, 1966) gave Euler-like forms; Thorpe introduced control volume [SRC: https://ar5iv.labs.arxiv.org/html/1612.00884].

Result (van der Ha eq. 17; steady flow; rho_e = c.m.-to-exit vector, v_e exhaust velocity, beta mass flow rate) [SRC]:
- I*w_dot + w x H + beta*{rho_e x (w x rho_e)} + beta*(rho_e x v_e) = M_external
- beta*rho_e x (w x rho_e) = jet-damping torque; beta*rho_e x v_e ~ thrust-misalignment torque; I = instantaneous inertia. The intermediate eq. 15 contains -I_dot*w, which cancels against the angular momentum carried by the internal flow via eq. 16, so eq. 17 has no explicit I_dot*w term.
- Planar pitch (w = omega_y perpendicular to rho_e): I_yy*omega_dot = M_ext - |mdot|*rho_e^2*omega + misalignment torque [DERIVED from eq. 17].

Form with I_dot kept (Duncan & Ensey 1964): tau = -Mdot*(l_cn^2 - l_cc^2)*omega, l_cn = c.m.-to-nozzle-exit, l_cc = c.m.-to-propellant c.m. [SRC: https://cambridgerocket.sourceforge.net/AerodynamicCoefficients.pdf eq. 16-18]. Equivalent to d(I omega)/dt = M - |mdot| l_cn^2 omega with I_dot = -|mdot| l_cc^2 [DERIVED]. So I*omega_dot vs d(I omega)/dt must be stated consistently.

Disputed points [SRC via van der Ha]: (1) lever arm: c.m.-to-exit (Meyer; van der Ha eq. 17), to throat (Javorsek & Longuski), sqrt(rho_e^2 - rho_bs^2) with burning-surface coordinate rho_bs (Misterek et al.), geometric mean of exit and throat (Rosser), mass-flow centre (van der Ha); "many different expressions are in use". (2) Thomson's model with I_dot terms predicts spin changes not observed; Thomson & Reiter (AIAA J. 3, 413, 1965, https://doi.org/10.2514/3.2880) found the model without I_dot terms matches Thor-Able flight data. (3) Stabilising only if c.m.-to-exit distance exceeds the transverse radius of gyration (Thomson). NASA reports: flexible variable-mass rocket with internal flow (https://ntrs.nasa.gov/api/citations/19700010018/downloads/19700010018.pdf) reduces flow effects to Coriolis, unsteady-flow and reactive forces; Kane-based study (https://ntrs.nasa.gov/api/citations/19980210404/downloads/19980210404.pdf) says jet damping and inertia-variation moments "have dominant effects" for variable-mass systems in general.

Magnitude: Thomson & Reiter: "In rockets operating in air, jet damping is usually second in importance to aerodynamic moments. In vacuum ... can be the most important torque" [SRC]. Army RAPs: "completely negligible" (DTIC ADA089980); 910 kg missile: aerodynamic damping "many times greater" (Kowaleczko 2016); typical model rocket: aerodynamic damping much larger, propulsive "negligible" (Apogee Newsletter 195, https://apogeerockets.com/education/downloads/Newsletter195.pdf); Mandell leaves jet damping out as small [SRC: Fetter, http://www.speedmotionrockets.com/Rotational%20Dynamic%20Stability%20-%20Rev%201_2.pdf]. Counter-case: statically unstable DC-X scale model flew straight on a high-thrust L motor while thrusting (C. Rogers, https://www.freelists.org/post/arocket/Dynamic-stability-in-supersonic-rockets,30). Numbers: restodo item 2 (jet 3.2 vs aero 0.2-2.4 kg m^2/s at 100 m/s, assumed inputs).

Hobby formula: C2R = mdot*(L_ne - W)^2, L_ne nose-to-nozzle, W nose-to-CG (Mandell et al., "Topics in Advanced Model Rocketry", MIT Press 1973, ch. 2; reproduced in Newsletter 195 and https://www.rocketryforum.com/threads/calculation-of-damping-moment-coefficient-and-damping-ratio-using-openrocket.30523/) [SRC, secondary]. RockSim does not compute it while on the rod.

Simulators [SRC]: RASAero II includes the jet damping coefficient in the powered phase (manual foreword; Rogers post). RockSim includes C2R. OpenRocket: techdoc 3.2.3 has only aerodynamic cylinder cross-flow damping; the forum recipe adds C2R externally because "OR does not provide" it [absence in what was read]. RocketPy: variable-mass equations assuming steady irrotational internal gas flow; interpolated m, m', m'', c.m. and derivatives, inertia tensor I and I'; nozzle-exit integral with exit radius r_n and v_e; Rocket.get_inertia_tensor_derivative_at_time exists [SRC: Context7 /rocketpy-team/rocketpy, docs/technical/equations_of_motion.md]. The final RocketPy rotational equation text was not retrieved; whether an explicit -mdot*rho_e^2*omega term appears is unconfirmed.

**Recommendation for the report.**
- Write I_yy*omega_dot = M_aero + M_thrust - |mdot| l_e^2 omega with l_e = c.m.-to-nozzle-exit (note throat and other lever arms in the literature), and say whether the left side is I*omega_dot or d(I omega)/dt; if I_dot omega is kept use |mdot|(l_cn^2 - l_cc^2).
- Magnitude sentence: aerodynamic damping dominates for large/fast vehicles and model rockets in flight; jet damping comparable only at low speed and high mdot (restodo item 2); RASAero and RockSim include it, OpenRocket (as read) does not.
- Open: final RocketPy equation; RASAero lever arm; project sign conventions (damping must oppose omega).

## T3. Propellant grain geometry (solid motors)

**Answer.**

Burn-rate law r = a*p^n (Saint-Robert/Vieille), n < 1 for stable burning; Nakka KNSU example a = 8.26 mm/s (MPa units), n = 0.319 [SRC: https://www.nakka-rocketry.net/design1.html]. Reference: Sutton & Biblarz, Rocket Propulsion Elements (9th ed.), solid-propellant fundamentals chapter; chapter/equation numbers not verified. openMotor states its calculations come from Sutton and Nakka [SRC: https://github.com/reilleya/openMotor/].

Kn and pressure: Nakka defines Kn = A_b/A_t, Po chamber pressure, rho propellant density, c* characteristic velocity (equation image not machine-read) [SRC]. Equilibrium (mass generated = mass discharged) [DERIVED]:
- rho_p*A_b*a*p^n = p*A_t/c*  =>  p_c = (a*rho_p*c**Kn)^(1/(1-n)), Kn = A_b/A_t; matches the user's formula. Nakka's unit-conversion factor for a (MPa to Pa) is needed [SRC].
- Web regression: dx/dt = a*p_c(x)^n with p_c from Kn(x); burn ends at x = web; mdot_gen = rho_p*A_b*r [DERIVED]. Geometry inputs are surface area, volume, web left and port area as functions of regressed distance (openMotor getSurfaceAreaAtRegression, getVolumeAtRegression, getWebLeft, getPortArea, getVolumeSlice) [SRC: https://openmotor.readthedocs.io/en/latest/motorlib.html].

Burning area (outer D, core d, length L, web t = (D-d)/2) [SRC: Nakka design1]:
- Hollow cylinder, all surfaces burning: A_b,init = (pi/2)(D^2-d^2) + pi L (D+d); final = pi (D+d)(L-t).
- Outer inhibited (core + ends): A_b,init = (pi/2)(D^2-d^2) + pi d L; final = pi D (L-2t).
- Outer and ends inhibited, core burning (tube): A_b = pi L (D+d) when "both ends inhibited" (burning on outer and core) = constant.
- BATES, N segments, outer inhibited: A_b = N[(pi/2)(D^2-d^2) + pi L d], d = d0 + 2x, L = L0 - 2x; final = N pi D (L0-2t); A_b,max at x = (L0-2 d0)/6.
- Rod-and-tube: A_b = pi (d + D_r) L, neutral.
- End burner: constant, equal to the end face (neutral) [SRC: https://deepwiki.com/reilleya/openMotor/2.2-grain-geometry].
- Star, finocyl, moon, C, D, X-core: no closed form in sources read. openMotor rasterises the grain face, computes distance with the Fast Marching Method, takes level-set contour lengths as perimeter; BATES and end burner closed form [SRC: openMotor docs; https://www.rocketryforum.com/threads/openmotor-changes-in-grain-shape-due-to-combustion.193941/]. Profiles: star progressive then regressive, finocyl progressive-regressive-neutral, BATES and rod-tube neutral; initial Kn 55.6 (BATES) to 137 (star) in a 0.85 kg KNSB case [SRC: https://doi.org/10.30574/gjeta.2026.28.1.0167].

Mass, CG, inertia from geometry [DERIVED, standard solid formulas]:
- Segment (R = D/2, r = d/2, length L): m = rho_p pi (R^2 - r^2) L; burned mass = rho_p (V0 - V(x)).
- I_axial = (1/2) m (R^2 + r^2); I_transverse about own centre = (m/12)(3(R^2 + r^2) + L^2).
- BATES: both ends regress equally, so each segment's centre stays at its original midpoint; stack CG changes only via segment masses; stack inertia by parallel axis, I = sum(I_t,i + m_i d_i^2). End burner: remaining cylinder of length L(t), CG at L(t)/2 from the unburned end.
- OpenRocket instead treats the motor as a homogeneous cylinder with mass proportional to impulse (restodo Q-C); difference not quantified.

Simulator inputs [SRC: openMotor README/docs; Nakka]: a, n (with pressure range), density, c* or (k, T0, M), per-segment geometry (D, d, L, inhibition, number, spacing), nozzle throat and exit diameter, efficiency corrections (openMotor adjusts C_F using DTIC A099791 and RASAero "Departures from Ideal Performance"). openMotor loop: compute Kn, then pressure, then thrust, then regress the web over the timestep, repeat until burnout [SRC]. Erosive burning and ignition options: not verified.

**Recommendation for the report.** Give r = a p^n, Kn, the p_c formula with the one-line mass balance, mdot = rho_p A_b r, A_b(x) for BATES/hollow cylinder, and the hollow-cylinder m, CG, I formulas; say star/finocyl need numerical (FMM) regression. Open: Sutton chapter/equation numbers; real c* efficiency, erosive burning, ignition and tail-off transients (outside a quasi-steady Kn model).

## T4. Pitch damping coefficient C_mq

**Answer.**

Form and normalisation [SRC]:
- Missile DATCOM: pitch-rate derivatives non-dimensionalised by q*LREF/(2*VINF); lateral by p*LATREF/(2*VINF), r*LATREF/(2*VINF) (DAMP card, http://mae-nas.eng.usu.edu/MAE_5900_Web/5900/USLI_2010/Flight_Mechanics/missile_datcom/Missile%20DATCOM%20Users%20Guide.pdf).
- JSBSim: C_m = ... + (C_mq q + C_m,alphadot alphadot)(c/2V) (restodo Q-A).
- So A_m = q S c (C_m + C_mq omega_hat), omega_hat = omega c/(2 v_rel) is the standard form and matches the report [SRC + DERIVED]. Barrowman defines C_mq as dC_m/d(q L_r/2V) [SRC: NTRS 20010047838, glyphs garbled]. In the nose-up-positive convention C_mq < 0 for stability; with the report's nose-down-positive C_m the sign must be checked against omega [ASSUMPTION].
- A lumped (C_mq + C_m,alphadot) is common (restodo Q-A).

Constant, Mach, or alpha-Mach? [SRC unless marked]:
- Barrowman/hobby: component sum of C_Nalpha_i (Z_i - W)^2 (restodo item 13); depends on Mach through C_Nalpha_i and on CG, not on alpha; Barrowman assumes alpha near zero (https://open-aerospace.github.io/barrowman/barrowman.html).
- OpenRocket: no C_mq; cross-flow drag integral of rotating cylinder (C_D = 1.1): body C_damp = 0.55 l^4 r_t/(A_ref d) omega^2/v0^2 (eq. 3.59), fins 0.6 N A_fin xi^3/(A_ref d) omega^2/v0^2 (eq. 3.60), N <= 4; "insignificant during most of the rocket flight" [techdoc 3.2.3, https://openrocket.sourceforge.net/techdoc.pdf]. No Mach or alpha dependence; quadratic in omega.
- RASAero II: static and dynamic derivatives computed every step including aerodynamic damping and jet damping; formula not stated in pages read (manual foreword).
- Missile DATCOM: with DAMP, C_Nq, C_mq, C_m,alphadot, C_N,alphadot etc. are computed as functions of alpha for each Mach/altitude entry (manual lists them under "as a function of angle of attack"; per-point tabulation inferred) -> C_mq(alpha, Mach).
- RocketPy: LinearGenericSurface damping coefficients may each be a function of alpha, beta, Mach, Re, q, r, p (callable or CSV) [Context7 /rocketpy-team/rocketpy, generic_surface.md]; defaults for standard surfaces not retrieved.
- No source treats C_mq as one fixed constant for the whole flight; practice is a Mach table (or alpha-Mach table from DATCOM) or a component sum evaluated at current conditions.

**Recommendation for the report.** State A_m = q S c (C_m + C_mq omega_hat) with omega_hat = omega c/(2 v_rel) (DATCOM normalisation); say C_mq is in general C_mq(Mach, alpha) and usually lumped with C_m,alphadot; constant C_mq is a simplification. Open: RASAero formula, RocketPy defaults, numeric C_mq for the project airframe.
