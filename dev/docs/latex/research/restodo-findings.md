# Findings for `\restodo` items and extra questions Q-A, Q-B, Q-C

Scope: facts only, no decisions. Line numbers refer to `sections-ai/*.tex` as read on 2026-10-17 (files are being edited, match by gist).
Tag legend: [SRC] = stated in a retrieved source; [DERIVED] = my own arithmetic/derivation from sourced numbers; [ASSUMPTION] = not sourced.

## 1. Mass flow from pressure-corrected T vs bare T0 (models.tex:213 and models.tex:~950)

**Answer.** Thrust is F = mdot*v_e + (p_e - p_a)*A_e [SRC: Sutton; NASA GRC; OpenRocket]. The mass flow of a choked nozzle is set by chamber conditions and throat area, not by ambient pressure [SRC: Stanford AA284A lecture 2, "mass flow equation (choked and isentropic flow...)"]. Ambient pressure enters only the pressure-thrust term. Published thrust curves are for standard pressure p0 = 101325 Pa; OpenRocket applies the altitude correction (p0 - p_a)*A_e on top of the published values and does nothing when the exit diameter is 0 [SRC: OpenRocket user guide, Thrust Curves]. So the physically consistent mass flow is mdot = T0(t)/(ISP*g0) with the stand-measured curve, as the report derives. Using the corrected T makes mdot grow with altitude (extra factor (p0-p_a)A_e/T0) and the burned mass then exceeds m0-m_f [DERIVED]. Size example [ASSUMPTION inputs]: 30 mm exit diameter, 10 km (p_a ~ 26.5 kPa): (p0-p_a)A_e ~ 53 N, ~10% of a 500 N motor. Zero for the default A_e = 0.
OpenRocket developer: motor mass "is assumed to reduce in proportion to the thrust"; it is not stated whether the corrected or the file thrust is meant (unresolved).

**Recommendation for the report.** Keep the T0 derivation; cite Sutton for "mdot is independent of ambient pressure"; the code deviation is a code-side discrepancy (change or not is a decision, not research). Both `\restodo` marks (mass section, state-vector section) are answered by this one fact.

**Sources.** Sutton & Biblarz, Rocket Propulsion Elements, 9th ed., ch. 2 (F = mdot v2 + (p2-p3)A2, quoted at https://ipv6.freelists.org/post/arocket/Pressure-Thrust-and-Momentum-Thrust,19 ); https://web.stanford.edu/~cantwell/AA284A_Course_Material/Karabeyoglu%20AA%20284A%20Lectures/AA284a_Lecture2.pdf ; https://openrocket.readthedocs.io/en/latest/user_guide/thrust_curves.html ; https://sourceforge.net/p/openrocket/mailman/message/29671720/

## 2. Size of dropped variable-mass terms vs pitch damping (models.tex:277)

**Answer.** (a) The jet-damping lever arm is not agreed [SRC]: |mdot|*(l_cn^2 - l_cc^2) (Duncan & Ensey 1964, Cambridge Rocket Society note), distance c.m. to nozzle exit, to throat, or sqrt(exit*throat) (Rosser et al.), mass-flow-centre distance (van der Ha, who notes the deciding experiment was never carried out). The report's (l_t - l_g)^2 is the throat variant. (b) Magnitude: for a 910 kg guided missile the aerodynamic damping derivative is "many times greater" than the jet one, jet damping neglected [Kowaleczko 2016]; for Army rocket-assisted projectiles pitch jet damping is "completely negligible" [DTIC ADA089980]. Opposite regime: RASAero II includes jet damping in its 3-DOF stability model, and its author says high thrust can let a statically unstable rocket fly while thrusting [RASAero II manual; arocket post, C. Rogers 2021]; the OpenRocket forum recipe adds C2r = mdot*(L_n - W)^2 to the aerodynamic part.
Order of magnitude [DERIVED, inputs ASSUMPTION]: jet = |mdot|*(l_t-l_g)^2 = 5 kg/s * 0.8^2 = 3.2 kg m^2/s (short, high-thrust). Aero = (1/4)*rho*v*S*c^2*C_mq (report eq. pitch_damping_moment); at v = 100 m/s, rho = 1.2, c = 0.1 m this is 2.4e-3*C_mq kg m^2/s. With C_mq ~ 10^2-10^3 for finned rockets (item 13) that is 0.2-2.4, so jet damping is comparable at low speed (near the rail) while aero grows with v (OpenRocket techdoc: aero damping "insignificant during most of the rocket flight"). The omitted omega*dI/dt term is of order |mdot|*d_p^2 (d_p = propellant-to-c.g. distance), same order as the jet term [DERIVED, not checked against a source].

**Recommendation for the report.** Replace the restodo by: "relative size depends on speed and mdot: comparable to aerodynamic damping at low v and high mdot, negligible for large missiles (Kowaleczko 2016); the lever-arm convention varies between authors". A number for the actual motor needs the project's own mdot, l_t - l_g, C_mq.

**Sources.** https://cambridgerocket.sourceforge.net/AerodynamicCoefficients.pdf (sec. 2.2, eq. 16-18) ; https://doi.org/10.15632/jtam-pl.54.3.893 ; https://apps.dtic.mil/sti/pdfs/ADA089980.pdf ; http://www.vanderha.com/J-2005b%20Jet%20Damping%20and%20Misalignment.pdf ; https://www.freelists.org/post/arocket/Dynamic-stability-in-supersonic-rockets,30 ; https://www.rocketryforum.com/threads/calculation-of-damping-moment-coefficient-and-damping-ratio-using-openrocket.30523/ ; https://www.rasaero.com/dloads/RASAero%20II%20Users%20Manual.pdf

## 3. Mass/inertia change from mechanisms, e.g. deployable surfaces (models.tex:303)

**Answer.** No source found. OpenRocket documents static mass/CG overrides per component and stage [SRC]; I found nothing on time-dependent mass/inertia from deployables in OpenRocket, RockSim or RASAero. The physics is the report's own additive first-moment/parallel-axis composition (eq. mass_cog, mass_inertia) with the moving part's l_g(t), I(t), plus the dI/dt term of item 2 [DERIVED].

**Recommendation.** Stays a research item (nothing citable); or reword as "a moving rigid sub-body enters eq. mass_cog and mass_inertia with its own time-dependent position".

**Sources.** https://openrocket.readthedocs.io/en/latest/user_guide/overrides_and_surface_finish.html (static overrides only)

## 4. Dry-rocket m_r, l_g,r, I_r,g from components, OpenRocket-style (models.tex:305)

**Answer.** OpenRocket builds the rocket from a component tree. Component masses come from manufacturer data, measurements, or volume times standard material density; CG of each component is estimated from material and geometry and combined into stage and rocket CG; overrides of mass/CG exist at component, subassembly and stage level [SRC: user guide]. Techdoc has a section "4.2.3 Mass and moment of inertia calculations" (listed in the contents; not read in detail). The motor is a homogeneous cylinder: filled-cylinder unit inertia times current mass [SRC: ThrustCurveMotor.java]. Caveats from the docs: glue and paint mass is not captured; overriding subcomponent masses changes rotational inertia.

**Recommendation.** Text: m_r = sum m_i; l_g,r = sum m_i l_i / m_r; I_r,g = sum (I_i + m_i d_i^2) (the report's own parallel-axis equation), component mass = density x volume, with OpenRocket as the precedent.

**Sources.** https://openrocket.readthedocs.io/en/latest/user_guide/overrides_and_surface_finish.html ; https://openrocket.sourceforge.net/techdoc.pdf (sec. 4.2.3) ; https://www.javatips.net/api/openrocket-master/core/src/net/sf/openrocket/motor/ThrustCurveMotor.java

## 5. CFD/data-extraction pipeline for the Table aero database; control-surface geometry and deflection law (models.tex:436)

**Answer.** Project-internal design question; no literature answer. Only external fact: Missile DATCOM tabulates coefficients over alpha, Mach, altitude (hence Re), sideslip and fin deflections delta1..4 [SRC: MathWorks datcomimport].

**Recommendation.** Stays a research item (the pipeline and control law are project definitions).

**Sources.** https://www.mathworks.com/help/aerotbx/ug/datcomimport.html

## 6. Optional drag polar C_x = C_x0 + k C_z^2 (models.tex:462)

**Answer.** For a slender body of revolution the natural force pair is axial and normal; drag and lift follow by rotation, D = N sin(a) + A cos(a) [SRC: Sforza, ScienceDirect eq. 8.56; OpenRocket techdoc uses "normal force and axial drag" and notes that at alpha > 0 normal force and drag are not perpendicular]. For small alpha with C_N = C_N,alpha*alpha this gives C_D = C_A + C_N,alpha*alpha^2 = C_A + C_N^2/C_N,alpha, i.e. a polar with k = 1/C_N,alpha arises from the rotation alone, and C_A itself also varies with alpha [DERIVED; NASA's report on Jorgensen's body method, NTRS 19730012271, has C_A with a cos^2(alpha) factor; no source I read gives a polar for finned bodies]. Caution [DERIVED, depends on the report's frame, not verified]: if the report's C_x is the body-axis axial coefficient, k*C_z^2 would double-count the N*sin(alpha) part; if it is the wind-axis drag the polar is meaningful. RASAero II outputs power-on/off drag vs alpha; OpenRocket's drag-vs-alpha correction was not retrieved. k = 1/(e*pi*AR) is the classical wing formula (textbook, not re-sourced).

**Recommendation.** Add the frame statement (axial vs drag) and the small-alpha identity; adopt-or-not is a decision.

**Sources.** https://www.sciencedirect.com/topics/engineering/form-drag-coefficient ; https://openrocket.sourceforge.net/techdoc.pdf (ch. 3 intro) ; https://ntrs.nasa.gov/api/citations/19730012271/downloads/19730012271.pdf ; https://www.rasaero.com/dloads/RASAero%20II%20Users%20Manual.pdf

## 7. Thrust noise: kappa, tau_c, roll-torque level (models.tex:691)

**Answer (partial).** kappa from thrust-misalignment statistics [Knauber, AIAA 95-2873]: misalignment is defined as the equivalent angle of the thrust vector at the throat; most upper-stage solid motors are designed for < 0.25 deg, some for 3-sigma < 0.15 deg; nozzle angle tolerance < 0.05 deg 3-sigma; SCOUT Castor II shows a 0.1 deg pitch-up bias over 79 flights; tail-off transients up to ~0.5 deg. Others: sigma ~ 0.1 deg (STAR-30BP, van der Ha 2005); 0.1 deg nominal and +-0.5 deg uniform in a sounding-rocket Monte Carlo (Black, Georgia Tech). So kappa ~ tan(delta) ~ 1.7e-3 (0.1 deg) to 8.7e-3 (0.5 deg) [DERIVED]. Knauber's classes: A steady, B slowly varying, C short transients (tail-off, igniter ejection), D ignition (15-30 ms), E/F static unbalance. Time structure is thus a quasi-constant random bias plus short transients at ignition and tail-off. No tau_c and no roll-torque level found; data are for large upper-stage SRMs, not hobby APCP motors.

**Recommendation.** Insert kappa ~ 1e-3 to 1e-2 with sources and describe the effect as a random-amplitude, nearly constant misalignment plus short transients rather than a stationary process; tau_c and roll torque stay open.

**Sources.** https://doi.org/10.2514/6.1995-2873 ; http://www.rsandt.com/media/Thrust%20Misalignments%20of%20Fixed-Nozzle%20Solid%20Rocket%20Motors.pdf ; http://www.vanderha.com/J-2005b%20Jet%20Damping%20and%20Misalignment.pdf ; https://repository.gatech.edu/server/api/core/bitstreams/fc26f02c-8ae0-4955-bf75-f403f3c2870b/content

## 8. Convergence study of RK45 vs fixed RK4 (models.tex:987)

**Answer.** Nothing to cite: this is the project's own experiment (error vs h and vs tolerance). General knowledge [ASSUMPTION, not re-verified]: SciPy RK45 is Dormand-Prince 5(4), classical RK4 is 4th order; expected slope ~h^4 on smooth segments, degraded by events, thrust-curve kinks and table lookups.

**Recommendation.** Stays a research item (experiment to run).

**Sources.** none.

## 9. Redefining apogee as maximum true altitude over curved ground (models.tex:1011)

**Answer.** No external source; the text itself calls it a modelling decision. The file's fact: the event is the launch-frame v_z crossing.

**Recommendation.** Stays a research item (decision).

**Sources.** none.

## 10. No pad contact: rocket slides backwards when thrust < weight on the rail (models.tex:1047)

**Answer.** Precedent exists. RASAero II release notes: "Corrected error in the first motion on the launch rail when the initial thrust was lower than weight. Rocket did not slide backwards on the rail, but negative acceleration was built up which had to be unwound into positive acceleration before the rocket would begin to move up the rail." So RASAero holds the rocket on the pad (it never slid backwards; the earlier bug was accumulated negative acceleration). Version number not captured in the retrieved text. OpenRocket/RockSim behaviour: not found.

**Recommendation.** Cite RASAero as precedent for clamping; the clamp formula in the report is its own.

**Sources.** http://www.rasaero.com/dl_software_ii.htm (release history)

## 11. Pitch rate omega_r not reset under canopy (models.tex:1071)

**Answer.** No source; code-consistency decision. Nothing found on rotational state after deployment in OpenRocket/RASAero docs (RASAero describes recovery events only).

**Recommendation.** Stays a research item (decision).

**Sources.** https://www.rasaero.com/dloads/RASAero%20II%20Users%20Manual.pdf

## 12. Neglected parachute effects (models.tex:1113)

**Answer.** Primary reference: Knacke, Parachute Recovery Systems Design Manual (NWC TP 6575), ch. 5: 5.3 stability incl. parachute-body system, 5.4 inflation (5.4.3 inflation time, 5.4.4 drag-area growth during filling, 5.4.6 opening-force methods, 5.4.7 typical diagrams), 5.6 reefing; ch. 7 main/drogue sequences, opening and snatch forces [SRC: table of contents]. Opening force F = C_x * X1 * (C_D S) * q at canopy stretch, with C_x quoted as 1.6 and X1 = 0.9 (infinite mass) for the main canopy; inflation time of 0.07-0.15 s for the small test canopy; Knacke's rules come from large canopies (Re ~ 1e7) and under-predict force and inflation time at small scale [SRC: small-UAS wind-tunnel paper, J. Aerosp. Technol. Manag.]. NASA CPAS uses an opening shock factor Ck vs mass ratio Rm [Potvin 2017]. Apparent (added) mass: no Knacke statement retrieved [ASSUMPTION that ch. 5 covers it].

**Recommendation.** Keep the list; cite Knacke ch. 5.4/5.6/5.3 per item and add one sentence on the small-scale Re caveat. No new equation needed.

**Sources.** https://www.manuallib.com/download/named/59/para-publishing-nwc-tp-6575-parachute-recovery-systems-design-manual.pdf ; https://www.scielo.br/j/jatm/a/rDFPNWbHLhSVrGTY4PhqtQB/?format=pdf&lang=en ; https://ntrs.nasa.gov/api/citations/20170003949/downloads/20170003949.pdf

## 13. Value or model for C_m,q (analysis.tex:178)

**Answer.** (1) Barrowman's thesis derives C_mq for body plus fins, subsonic and supersonic [NTRS 20010047838 abstract; formulas not read]. (2) Component sum, from an OpenRocket forum post (secondary): aerodynamic damping C2a = (V*A_ref*rho/2)*sum(C_N,alpha,i*(Z_i - W)^2). Equating with the report's (1/4)*rho*v*S*c^2*C_mq gives C_mq = 2*sum(C_N,alpha,i*((Z_i - W)/c)^2) [DERIVED; positive in the report's convention]. (3) OpenRocket's own estimate integrates cross-flow drag of a rotating cylinder (C_D = 1.1): C_damp = 0.55*l^4*r_t/(A_ref*d)*omega^2/v0^2 for body parts fore/aft of the CG, and 0.6*N*A_fin*xi^3/(A_ref*d)*omega^2/v0^2 for fins (N <= 4); "only a rough estimate" is required since damping matters at apogee [OpenRocket techdoc 3.2.3, eq. 3.57-3.60]. It is quadratic in omega, unlike the linear C_mq form. (4) Missile DATCOM computes C_mq and C_m,alpha-dot with the DAMP card. (5) Slender-body theory gives an integral of the normal-force distribution weighted by (x_cg - x)^2; CFD-fitted corrections G(x,M) exist (DTIC ADA417242). No tabulated C_mq values for a rocket retrieved.

**Recommendation.** Put model (2) in as the "distributed-force derivation" the text asks for, flagged secondary, and OpenRocket eq. 3.59/3.60 as an alternative; a number for the specific airframe needs a computation.

**Sources.** https://ntrs.nasa.gov/citations/20010047838 ; https://openrocket.sourceforge.net/techdoc.pdf (3.2.3) ; https://www.rocketryforum.com/threads/calculation-of-damping-moment-coefficient-and-damping-ratio-using-openrocket.30523/ ; http://mae-nas.eng.usu.edu/MAE_5900_Web/5900/USLI_2010/Flight_Mechanics/missile_datcom/Missile%20DATCOM%20Users%20Guide.pdf ; https://apps.dtic.mil/sti/pdfs/ADA417242.pdf

## Q-A. Inputs beyond (alpha, M, Re) in coefficient models for rocket/missile simulation

**Answer.**
- Always present [SRC]: Mach and altitude (Re from the standard atmosphere). Missile DATCOM: "Reynolds number is always required" (REN, or ALT with MACH/VINF, or PINF/TINF). Tabulations run over alpha, Mach, altitude, sideslip beta and fin deflection delta [MathWorks datcomimport; skyward-er datcom-parser]. RASAero II: coefficients each step from Mach, alpha, Re (from altitude) and power-on/power-off; roughness via equivalent sand roughness (default smooth); power-on base drag needs the nozzle exit diameter; Mach 0.01-25, alpha up to 15 deg.
- Rate derivatives [SRC]: pitch rate q gives C_mq, C_Nq, C_Aq; alpha-dot gives C_m,alpha-dot, C_N,alpha-dot; roll rate p gives C_lp, C_np, C_Yp; yaw rate r gives C_lr, C_nr, C_Yr. JSBSim form: C_m = C_m0 + C_m,alpha*alpha + C_m,de*de + C_m,iH*iH + (C_mq*q + C_m,alpha-dot*alpha-dot)*(c/2V).
- Non-dimensionalisation [SRC]: Missile DATCOM: longitudinal rate derivatives by q*LREF/(2*VINF); lateral by p*LATREF/(2*VINF), r*LATREF/(2*VINF). The report's omega*c/(2*v_rel) matches.
- alpha-dot is rarely separated from q: forced-oscillation tests, CFD and VSPAERO give only the sum (C_mq + C_m,alpha-dot); "in the equations of motion these terms often show up as the sum" [OpenVSP forum; MDPI Aerospace 2021; Cobalt AIAA-2016-1536]. For rectilinear flight q = alpha-dot but the derivatives remain physically distinct [EUCASS 2017-550]. So one lumped C_mq is usual practice.
- Control deflection delta: standard for controlled vehicles (C_m,delta; DATCOM fin deflection inputs). Sideslip beta: needed in 3D; for an axisymmetric body in a 2D pitch-plane model it is subsumed in alpha [ASSUMPTION].
- Not found in any retrieved standard output list (absence of evidence): derivatives wrt angular or linear acceleration. Thrust on/off: standard as power-on/off drag sets (RASAero) and base options; plume interaction beyond base drag not found.
- Significance (assessment, partly sourced): C_mq matters near apogee, at low v and for dynamic stability (OpenRocket techdoc: damping insignificant during most of the flight where velocity is large); Re and roughness mainly change friction drag C_x, little effect on C_N,alpha [ASSUMPTION; RASAero uses roughness as a drag input only]; Magnus/spin terms matter only for spinning bodies (Georgia Tech case: Magnus pitch force of the order of the damping moment).
- ESDU, Etkin, Zipfel pages were not retrieved; no direct ESDU citation.

**Recommendation for the report.** Extend the Table list: Mach and altitude (Re) always; power-on/off flag and roughness; C_mq (alpha-dot lumped) with q*c/(2V); delta for controlled vehicles. State that alpha-dot, accelerations and sideslip are not modelled in 2D.

**Sources.** http://mae-nas.eng.usu.edu/MAE_5900_Web/5900/USLI_2010/Flight_Mechanics/missile_datcom/Missile%20DATCOM%20Users%20Guide.pdf ; https://www.mathworks.com/help/aerotbx/ug/datcomimport.html ; https://github.com/skyward-er/datcom-parser ; https://www.rasaero.com/dloads/RASAero%20II%20Users%20Manual.pdf ; https://jsbsim-team.github.io/jsbsim-reference-manual/user/concepts/flight-control-and-systems-modeling/ ; https://groups.google.com/g/openvsp/c/QcTDBufqOoM ; https://doi.org/10.3390/aerospace8110354 ; http://www.cobaltcfd.com/pdfs/2016/AIAA-2016-1536.pdf ; https://www.eucass.eu/doi/EUCASS2017-550.pdf ; https://openrocket.sourceforge.net/techdoc.pdf ; https://repository.gatech.edu/server/api/core/bitstreams/fc26f02c-8ae0-4955-bf75-f403f3c2870b/content

## Q-B. Gravity: J2, ellipsoidal vs spherical-harmonic geopotential vs anomalies (one paragraph)

**Answer.** J2 = (C - A)/(M a^2) is the dynamical form factor (second zonal harmonic, J2 = -sqrt(5)*C20-bar) and the dominant correction to the point-mass potential, U = (GM/r)[1 - J2 (a/r)^2 P2(cos theta) - ...]. Value J2 = 1.08263e-3 (GRS80/WGS84; 1.082636e-3 in newer estimates) [Moritz GRS80; Featherstone; in-dubio-pro-geo]. Normal gravity on the WGS84 ellipsoid: equator 9.7803253359, poles 9.8321849378 m/s^2 (Somigliana, k = 0.00193185265241, e^2 = 0.00669437999014), spread 0.0518 m/s^2 (0.53%) [NIMA/BGI]. About two thirds of that is centrifugal (omega^2 a = 0.0339 m/s^2 at the equator, omega = 7.292115e-5 rad/s) and the rest oblateness/J2 (~1.5*J2*g ~ 0.016 m/s^2, 0.16%) [DERIVED]. Vertical: free-air gradient about -3.086e-6 s^-2 (-0.3086 mGal/m) [fatiando; in-dubio-pro-geo 3.085e-6], so 10 km lowers g by ~0.031 m/s^2 (0.3%) [DERIVED], comparable to the J2 latitude effect. A truncated spherical-harmonic model (EGM2008: complete to degree/order 2159, extra coefficients to 2190, from a 5 arc-minute grid) represents the global field down to roughly 9 km half-wavelength [Pavlis et al. 2012; NGA], as a smooth disturbance relative to the ellipsoid (geoid undulation, gravity disturbance). "Local gravity anomalies" are the observed difference Delta g = g_P - gamma_Q between measured gravity and normal gravity [Pavlis 2012, after Heiskanen & Moritz] and contain finer terrain and density structure than the truncated series. Anomaly size: typically tens of mGal (1 mGal = 1e-5 m/s^2), i.e. ~1e-4 to 1e-3 m/s^2, relative ~1e-5 to 1e-4 [ASSUMPTION, not retrieved]. For a <= 10 km rocket the relevant corrections are the ellipsoidal latitude variation (0.5%) and the free-air decrease (0.3% at 10 km); higher harmonics and local anomalies are two to three orders smaller than g and below other model errors (drag, wind).

**Recommendation.** Insert the paragraph: J2 value, Somigliana equator/pole values, free-air gradient, one sentence on EGM2008 vs anomalies, conclusion "ellipsoidal normal gravity plus free-air suffices for <= 10 km".

**Sources.** https://geoweb.mit.edu/~tah/12.221_2005/grs80_corr.pdf ; http://hdl.handle.net/20.500.11937/41042 ; http://in-dubio-pro-geo.de/index.php?file=register%2Fwgs84 ; https://bgi.obs-mip.fr/wp-content-omp/uploads/sites/46/2017/10/computations.pdf ; https://legacy.fatiando.org/api/gravmag.normal_gravity.html ; https://doi.org/10.1029/2011jb008916 ; https://earth-info.nga.mil/GandG/wgs84/gravitymod/egm2008/

## Q-C. Is a linear-in-time motor mass model used in practice?

**Answer.** Evidence points to impulse-proportional mass, not linear in time.
- OpenRocket (developer): "The mass is assumed to reduce in proportion to the thrust. (This is equivalent to assuming a constant exhaust velocity.)", CG at mid-motor, homogeneous cylinder of reducing mass [OpenRocket-devel list, 2012]. ThrustCurveMotor.java: inertia = filled-cylinder unit inertia x current mass; CG interpolated between per-point cg[] values [SRC].
- RocketPy and HPR Sim: m_p(t) = m_p0 (1 - I(t)/I_total), mdot = F/c with c = I_total/m_p0; ThrustCurve .rse mass columns are tabulated the same way; real consumption is only approximately proportional (Isp drifts with chamber pressure and erosion) [FusionSpace HPR docs, citing RocketPy SolidMotor].
- wRASP/RASP (ancestor of RockSim/RASAero inputs): forum answer gives M_i = (F_i*T_i/I_total)*M_total, "I believe this is what wRasp does" [secondary, unverified]. Cambridge Rocket Society note gives the same: dM_i = -M_f * integral(T dt)/integral_0^inf(T dt) [SRC].
- RockSim: a forum poster says "a linier graph should be fine, I believe thats how rocksim does it" [opinion, unverified]; another says .rse files carry a pre-calculated mass increment. No primary RockSim documentation retrieved, so its rule is unresolved.
- RASAero II: only stated that propellant weight sits at mid-motor length and used propellant is "decremented" [C. Rogers, Rocketry Forum]; formula not stated in what I retrieved.
- Linear mass flow is exact when thrust is constant (impulse-proportional reduces to linear). Nearly linear liquid-phase mass flows are reported for nitrous sounding rockets [Black, Georgia Tech]. No retrieved simulator documents a linear-in-time model for solid motors.

**Recommendation for the report.** State that the practical model is mass proportional to cumulative impulse (the ISP model of eq. mass_isp with constant effective exhaust velocity); keep the linear model as its constant-thrust special case or drop it. RockSim/RASAero rules remain unconfirmed.

**Sources.** https://sourceforge.net/p/openrocket/mailman/message/29671720/ ; https://www.javatips.net/api/openrocket-master/core/src/net/sf/openrocket/motor/ThrustCurveMotor.java ; https://hpr.fusionspace.co/physics/motor.html ; https://cambridgerocket.sourceforge.net/AerodynamicCoefficients.pdf ; https://www.rocketryforum.com/threads/estimating-propellant-weight-vs-burn-time.102929/ ; https://www.rocketryforum.com/threads/rasaero-ii-modelling-variable-mass-in-the-middle-of-the-rocket.150443/ ; https://repository.gatech.edu/server/api/core/bitstreams/fc26f02c-8ae0-4955-bf75-f403f3c2870b/content
