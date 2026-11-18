<!-- STATUS: in-progress -->
# Airbrake (drag-modulation) apogee controller — research findings

Pre-implementation research only. No design decisions made here; findings are reported with
sources for the orchestrator/architect to evaluate.

## Scope

Two areas:
1. Sensors and state estimation typically used for apogee-targeting airbrake control.
2. Control-law architectures actually used/published for this specific problem.

Method: web search (Exa) across competition team technical reports (Spaceport America Cup / IREC,
EuRoC, AIAA student papers), commercial altimeter documentation, and peer-reviewed/conference papers
on airbrake apogee control. No single source was treated as authoritative; claims are cross-checked
across multiple independent teams/papers where possible.

---

## Area 1 — Sensors and state estimation

### 1.1 Barometric altitude referenced to launch-pad pressure is the dominant primary altitude source

Confirmed across both commercial dual-deploy altimeters and competition airbrake avionics.

- **Commercial altimeters (apogee-detection market, not airbrake-specific but same sensing
  problem):** the RRC3 manual states the unit "continuously updates the 'floor' (or launch) altitude
  using a running average method" while on the pad, and converts pressure to altitude using the NOAA
  "Pressure Altitude" method referenced to that pad baseline, not a fixed ISA/day-of-launch density
  assumption. — *Apogee Components, RRC3 User Manual*, https://www.apogeerockets.com/downloads/PDFs/RRC3-user-manual.pdf
- The PerfectFlite StratoLoggerCF manual: "the altimeter converts the pressure differential to a
  precise measurement of altitude above launch point according to the US Standard Atmosphere model" —
  i.e. altitude is derived as a pressure *differential from the pad reading*, with the standard
  atmosphere used only for the pressure→altitude slope, not as an absolute density model. —
  http://www.perfectflite.com/Downloads/StratoLoggerCF%20manual.pdf
- Altus Metrum (TeleMega/TeleMetrum) flight computers: "Our flight computers use a Kalman
  sensor-fusing filter ... Below 30km altitude ... we use both the barometer and the accelerometer to
  update the flight state ... That works super well, pegging apogee within a few sensor samples
  essentially every time." Above 30 km (where the barometer is non-functional) it falls back to
  accelerometer-only, explicitly flagged as the degraded mode. — https://altusmetrum.org/FAQs/apogee-above-100k.html
- Among competition airbrake teams found in Area-1 search, barometer + IMU (accelerometer, often
  with gyro/magnetometer) is the near-universal sensor suite for the airbrake control loop itself:
  Terrapin Rocket Team / Karkinos (UMD, SAC): "barometer, IMU, and GPS" feeding an Extended Kalman
  Filter — https://rockets.umd.edu/past-projects/terpulence-ii ; OSU "Ramkoers" uses a BMP390
  altimeter + BNO055 accelerometer — https://halebrown.io/assets/pdfs/Team_68_Project_Technical_Report_to_the_2024_Spaceport_America_Cup.pdf ;
  Longhorn Rocketry "Experimental Air Braking" uses an MPL3115A barometric sensor + ADXL377 high-g
  accelerometer + LSM9DS1 IMU — https://www.shawnvictor.net/experimental-air-braking.html ; Cowboy
  Rocketworks (OSU) uses a BMP280 barometer + ADXL377 accelerometer — https://www.soundingrocket.org/uploads/9/0/6/4/9064598/54_project_report.pdf ;
  UPC Ares team's airbrake Kalman filter design is explicitly barometer+IMU based —
  https://hdl.handle.net/2117/446745.
- No team or commercial-altimeter source found treats "altitude inferred from air density alone via
  a fixed ISA model with no pad-pressure reference" as the production approach. This part of the
  hypothesis is **confirmed**: pad-referenced pressure differential is standard; a day-of-launch
  reference reading (or continuous running-average baseline on the pad) is used specifically to avoid
  the day-to-day atmospheric deviation problem.

### 1.2 Baro-inertial fusion (Kalman or complementary) for vertical velocity is the dominant architecture; pure baro differentiation alone is explicitly flagged as noisy/problematic

- Rocketry Forum community discussion (practitioner consensus, not peer-reviewed but widely
  corroborated by vendor docs below): "Velocity is derived from baro, just like the Stratologger, RRC2,
  and every other baro-only altimeter... until you get near Mach... To get accurate velocity at speeds
  above about 700 ft/sec you really need to integrate an accelerometer." —
  https://www.rocketryforum.com/threads/altimeters-with-accelerometers-and-realtime-output.127927/
- Direct practitioner quote on baro-only noise: "RRC3 is a baro only unit so it is not a terribly
  good source for velocity... Numerically differentiated data (altimeter data or otherwise) are
  inherently noisy. (Hence the filter.)" The poster had to apply a Savitzky–Golay filter to get a
  usable velocity estimate from RRC3 baro data post-flight. —
  https://www.rocketryforum.com/threads/interpret-my-data-rrc3-brb900.137850/
- Altus Metrum explicitly runs a **Kalman sensor-fusing filter** combining barometer + accelerometer
  (+ a basic Newtonian motion model) for height/vertical-speed/vertical-acceleration state, and falls
  back to accelerometer-only above 30 km where baro is unusable — confirming fusion is the normal
  design, with baro-only or accel-only as explicitly inferior fallback modes, not the preferred
  architecture. — https://altusmetrum.org/FAQs/apogee-above-100k.html
- Apogee TeleMega documentation: "The unit integrates the accelerometer output to find velocity;
  when that value is >200m/s, it ignores any barometric readings" — i.e. uses accelerometer-derived
  velocity specifically to gate/sanity-check the barometric apogee determination during
  high-speed/transonic flight, a form of fusion/cross-validation rather than either sensor alone. —
  https://www.apogeerockets.com/index.php?main_page=product_info&products_id=1708
- Forum discussion on accelerometer-only drift ("Flight Computers: Accelerometers vs Barometric
  Sensors"): practitioners note "you can't really trust the z-axis accelerometer's altitude data...
  The accelerometer will definitely give you a better velocity figure, though, since it's not dependent
  on your rocket's path" — i.e. community understanding matches the hypothesis that baro gives reliable
  absolute altitude but poor/noisy differentiated velocity, while accelerometer integration gives good
  velocity but drifts/accumulates path-dependent error for altitude — motivating fusion of the two
  rather than using either alone. — https://www.rocketryforum.com/threads/flight-computers-accelerometers-vs-barometric-sensors.148020/
- Competition airbrake teams specifically use Kalman filters fusing barometer + IMU for the state fed
  to the controller: Terrapin/Karkinos EKF (barometer, IMU, GPS) —
  https://rockets.umd.edu/past-projects/terpulence-ii, and in detail in Kyle Kingsberry's portfolio
  write-up: "The Kalman filter combined data from barometric pressure sensors, accelerometers, and
  gyroscopes to produce optimal state estimates" — https://www.kylek.tech/projects/terrapin-rocket-team-airbrake ;
  UMD's own published comparative-controller paper models the "State Estimation Model" as "a Kalman
  Filter using ... noisy height, acceleration, and tilt" matching their real in-flight estimator — UMD,
  *The Evaluation of Various Controller Architectures for an Air Brake on a High-Powered Model Rocket*,
  https://api.drum.lib.umd.edu/server/api/core/bitstreams/c267150f-d411-40df-9880-4e780d6b364b/content ;
  UGA IREC team: "By using an altimeter to measure altitude and an IMU to measure acceleration, we will
  derive velocity" feeding an MPC — https://region2.aiaastudentconference.org/collection/2025/manuscripts/98650.pdf ;
  UNH SEDS HAAMSHR system integrates IMU acceleration twice for velocity/altitude estimates (a
  simpler/pure-inertial variant, noted as an exception — see 1.2a below) —
  https://scholars.unh.edu/cgi/viewcontent.cgi?article=1960&context=honors.
- A 2025 AIAA paper on sounding-rocket airbrake guidance (Woody & Van Bibber) explicitly states its
  state estimator: "A Kalman filter was implemented for altitude and vertical velocity estimates,
  fusing acceleration measurements from the IMU with altitude measurements from the global navigation
  satellite system (GNSS)" — a baro-free variant using GNSS instead of barometer for the absolute
  altitude channel, still following the same general fusion pattern (absolute-position sensor +
  accelerometer, Kalman-fused) rather than pure baro differentiation or pure inertial integration. —
  Woody, K.; Van Bibber, C., *Apogee Altitude Control of Sounding Rockets With an Analytic Guidance
  Algorithm*, AIAA 2025-0111, https://doi.org/10.2514/6.2025-0111 (preprint copy:
  https://www.scribd.com/document/847195739/3671885).

**1.2a Exception/nuance found:** the UNH SEDS HAAMSHR report describes a simpler pure-inertial
scheme ("The control system integrates IMU acceleration readings twice to obtain instantaneous
velocity and altitude estimates") without mentioning barometric fusion in the quoted control-loop
description — this is a counter-example to "fusion is universal," though it is a smaller/simpler
team project relative to the EKF-based SAC-caliber teams above, and the report doesn't fully detail
whether a barometer is used elsewhere (e.g. for an independent apogee-detect/recovery channel) while
the airbrake loop itself runs on double-integrated accelerometer data. —
https://scholars.unh.edu/cgi/viewcontent.cgi?article=1960&context=honors

**Overall for 1.2:** the hypothesis is **substantially confirmed** — baro-inertial (or GNSS-inertial)
Kalman/complementary fusion for velocity is the typical architecture among SAC/IREC/EuRoC-caliber
airbrake teams, motivated by exactly the noise/drift tradeoff stated in the hypothesis — with at least
one smaller-team counter-example using pure double-integrated accelerometer data instead.

### 1.3 Pitot/dynamic-pressure tube: generally secondary (drag-coefficient verification), not the primary velocity backbone — with nuance on noise location

- Direct, detailed evidence from a sounding-rocket club's critical review of flight data (ICAS 2022
  paper from a student rocketry effort, not a competition team per se but the most quantitative source
  found on pitot-vs-baro-vs-IMU velocity in-flight): "A consistent trend across all flights is that the
  pitot tube velocity is below the filtered velocity at motor burnout, then above the filtered velocity
  near apogee... the directly calculated CD's first decrease, then increase greatly — the EKF CD's
  follow similar trends but more muted... The pitot tube only CD's tend to be closer than the altitude
  derived CD's." This paper explicitly uses the pitot tube as an **independent drag-coefficient
  measurement/verification channel** compared against EKF (baro+IMU fused) output and against
  altitude-derived velocity — not as the primary velocity source for a control loop (this specific
  rocket did not run a closed-loop airbrake, but the data-quality characterization is directly
  relevant). — https://www.icas.org/icas_archive/ICAS2022/data/papers/ICAS2022_0414_paper.pdf
  - Note on **where** the noisiest regime is: contrary to a purely "noise grows near apogee because
    q→0" framing, this report finds disagreement/noise issues throughout — including at burnout — and
    attributes some of it to sensor lag/time-constants and leaky tubing (explicitly reported hardware
    issues: "the pitot tube for this flight was not fully sealed," "the pitot tube for that flight was
    also leaky," "due to a resolution limitation, the pitot tube data was not useful" across multiple
    flights). This confirms pitot/dynamic-pressure sensing has **real, repeated practical reliability
    problems in practice** (sealing, resolution, lag), independent of the fundamentally small-q-near-
    apogee noise-amplification argument.
  - The paper's own 1D analysis also explicitly notes velocity-derivation difficulty specifically
    near apogee: "It is cutoff four seconds before apogee because at that point the velocity is small
    and the derived acceleration is noisy" (referring to the derivative of pitot-tube velocity) — this
    directly supports the q→0-near-apogee noise-amplification part of the hypothesis.
- A 2025 AIAA paper on in-flight drag determination (Bawa & Michalski) uses "real-time onboard
  measurements of translational acceleration, static pressure, and temperature" (not dynamic/pitot
  pressure) for a one-dimensional momentum-based drag reconstruction during **supersonic** flight —
  i.e. an accelerometer+static-pressure (not pitot) based approach to drag/Cd reconstruction, consistent
  with pitot/dynamic pressure not being the default choice even for post-flight Cd work. — Bawa, V.;
  Michalski, Q., *An Experimental Framework for In-Flight Determination of Rocket Aerodynamic Drag*,
  AIAA 2025-104785, https://doi.org/10.2514/6.2025-104785
- No airbrake competition team report found in this search (Terrapin, UMD comparative-controller
  paper, UGA, OSU, Cowboy Rocketworks, UPC Ares, UNH SEDS, Mississippi State Space Cowboys, Virginia
  Tech ROADKILL) lists a pitot/dynamic-pressure tube as part of their primary airbrake control sensor
  suite — all rely on barometer + IMU (± GPS) for the controller's state estimate. This is a consistent
  absence across ~8 independent team reports, which is itself informative even though none of them
  explicitly argues against pitot-based sensing (it is simply not present).
- General airspeed-calibration literature (NASA, not rocket-specific) on pitot/static systems
  confirms pitot total-pressure measurement is generally reliable "for well-sited or aligned probes,"
  but flags flow-angle and boundary-layer siting sensitivity as calibration concerns — consistent with
  the "flow interference near fins/body" part of the hypothesis, though this source is about aircraft
  air-data systems, not sounding rockets specifically, and is included for engineering-principle
  support rather than rocket-specific confirmation. — Haering, E.A. Jr., *Airdata Measurement and
  Calibration*, NASA Dryden, https://ntrs.nasa.gov/api/citations/19990063780/downloads/19990063780FINAL.pdf

**Overall for 1.3:** the hypothesis is **confirmed by omission and by the one detailed quantitative
source found** — pitot/dynamic-pressure sensing, where it appears at all in the rocketry literature
surveyed, is used as a secondary/verification channel for drag-coefficient estimation (ICAS 2022 paper)
or not mentioned at all in airbrake-controller sensor suites (all competition reports surveyed). The
specific q=0.5·ρ·V² / V=sqrt(2·ΔP/ρ) noise-amplification-near-apogee argument is directly supported by
the ICAS paper's own analysis cutoff ("cutoff four seconds before apogee... velocity is small and the
derived acceleration is noisy"). Practical reliability issues (leaky/unsealed tubing, resolution limits)
were also independently reported, reinforcing — via a different mechanism — the same "not primary"
conclusion. No source was found that uses a pitot tube as the primary/backbone velocity source for
closed-loop airbrake apogee control.

### 1.4 Angle of attack / horizontal velocity: no GPS-free AoA measurement found; near-vertical 1D treatment is common but not universal

- The UMD comparative-controller paper explicitly states its controller's assumption: "the MPC
  assumes that the rocket's tilt off of the vertical is always zero" in the nominal/control model, while
  the underlying Simulink *plant* model is 2D/3D — i.e. the controller itself treats the problem as 1D
  along the vertical even though the real flight is multi-dimensional; tilt/orientation is tracked by
  the EKF for projecting accelerometer readings onto the vertical axis, but the control law's forward
  apogee-prediction model collapses to 1D. — UMD, *The Evaluation of Various Controller Architectures...*,
  https://api.drum.lib.umd.edu/server/api/core/bitstreams/c267150f-d411-40df-9880-4e780d6b364b/content
- The AIAA sounding-rocket guidance paper (Woody & Van Bibber) explicitly handles non-zero tilt
  rather than assuming it away: "the velocity vector of a rocket is almost never vertical. To account
  for this, the orientation of the rocket must always be known so that the vertical component of
  acceleration can be projected from the sensor measurements" — using gyro-based dead-reckoning
  attitude estimation (explicitly noted as having "lack of observability" issues) to project the
  along-axis accelerometer reading onto the vertical, rather than measuring true aerodynamic angle of
  attack or horizontal velocity directly. This is a middle ground: not a literal "assume AoA=0"
  simplification, but also not a direct AoA or horizontal-velocity measurement — it is inertial attitude
  used to resolve a 1D-vertical dynamics model, with GNSS supplying the absolute-altitude fusion input
  (not horizontal velocity). — https://doi.org/10.2514/6.2025-0111
- No source found in this search directly measures true angle of attack (e.g. via vanes, multi-port
  pressure probes, or flush air-data sensing) on a competition/amateur airbrake rocket. GPS, where used
  (Terrapin/Karkinos: "barometer, IMU, and GPS"), is used in the reports found primarily in the context
  of state estimation generally and recovery/tracking, not explicitly described as providing a
  horizontal-velocity term consumed by the airbrake control law in the sources reviewed (none of the
  excerpts obtained went into that level of detail on GPS's specific role in the Terrapin EKF).
- A general rocket-dynamics reference (Nakka) on angle-of-attack/yaw definitions and wind-gust-induced
  AoA confirms the aerodynamics terminology and that gusts/transients are a real source of AoA in
  flight, but is a general-aerodynamics reference, not evidence about instrumentation choices. —
  https://www.nakka-rocketry.net/articles/AS_rocketry_aerodynamics.pdf

**Overall for 1.4:** **partially confirmed, with an important nuance.** No source measures AoA or
earth-frame horizontal velocity directly without GPS. However, the surveyed teams split between (a)
explicitly assuming zero tilt in the control-law's forward model (UMD/Karkinos) and (b) explicitly
tracking attitude via gyro dead-reckoning to project accelerometer data onto the true vertical, without
assuming zero tilt (Woody & Van Bibber). Both avoid direct AoA/horizontal-velocity sensing, but "treat
near-vertical flight as strictly 1D with no attitude correction at all" is not universal — attitude-
projection of the accelerometer reading (while still not full 3-DOF translational state estimation) is
also practiced and explicitly motivated by exactly the concern the hypothesis raises (velocity vector
"almost never vertical").

---

## Area 2 — Control-law architecture for airbrake apogee targeting

### 2.1 Summary of what was actually found, by architecture type

| Architecture | Found in practice (flown/competition) | Found in academic papers (simulation-only or unclear flight status) |
|---|---|---|
| Predictive P/PID on apogee-error (forward-sim at fixed extension, PID on error) | UMD/Karkinos tested this in simulation as a baseline but **MPC outperformed it** and is their actually-used architecture (ambiguous — see 2.2); Virginia Tech ROADKILL uses a PID on (optimal Cd − current Cd) — a predictive-error PID variant | UMD comparative paper tests 4 PID variants explicitly as a studied baseline, not the winner |
| Switching-curve / bounding-trajectory (predict apogee at both brake limits, interpolate) | UNH SEDS HAAMSHR: explicit **bisection search over drag coefficient bounds**, closest documented real-world analogue to the hypothesis's "bounding trajectory blend," feeding a lookup table | EUCASS 2019 paper (ISAE?) formally defines boundary trajectories γmin(v)/γmax(v) bounding the reachable/controllable state-space region, used to build an offline bang-bang-flavored lookup-table policy, not a per-cycle online interpolation |
| MPC (receding horizon / binary-search apogee-error minimization) | **Most frequently reported as the actually-selected/flown architecture** among documented competition teams: UMD/Karkinos (binary search over 0–85° in 5° steps, 10 Hz), UGA IREC, Mississippi State Space Cowboys, Simple Latte (uOttawa), TARS (Bregin & Jaffar) | Same — most "MPC" implementations found are a brute-force/binary-search one-step-ahead optimization (hold-constant-then-forward-simulate), not a full receding-horizon trajectory optimization over an extension-vs-time profile |
| Adaptive/online Cd-mismatch correction layer | Virginia Tech ROADKILL (PID correcting measured-vs-modeled Cd); LASC paper's Gain Scheduling layer on top of P+PI/LQR | LASC 2025 paper (Marinato et al.) explicitly adds a "Gain Scheduling adaptive layer" to both a classical cascade (P+PI) and an LQR controller |
| Bang-bang / minimum-time optimal | Not found flown as the final online controller (acknowledged in EUCASS paper as the "true" unconstrained-optimal solution shape, but deliberately avoided/softened because of actuator rate limits) | EUCASS 2019 paper explicitly: "solving optimal control problems can result in bang-bang type controllers, which would not capture the true behavior of this system" (due to actuator delay/rate limits) |
| LQR / gain-scheduled LQR | Tested as a studied baseline (UMD, did not win); used as one of two final candidate architectures in LASC 2025 paper, matched with Kalman filter + gain scheduling | — |
| Sliding-mode control | Not found applied to this specific problem in any source surveyed | Not found — only a generic optimal-control lecture note mentioning that bang-bang solutions are "compare[d] to... sliding mode controllers" in general optimal-control theory, not rocket-airbrake-specific — https://archive.control.lth.se/media/Education/EngineeringProgram/FRTN05/2013/lec10_2013.pdf |
| Feedback linearization | Not found in any source surveyed for this specific problem |
| Analytic/closed-form guidance law (not literally PID on raw state, not MPC) | **Found as a distinct, named approach**: Woody & Van Bibber's "Analytic Guidance Algorithm" — derives a closed-form required-deceleration profile from coast-phase kinematics via separation of variables, "without knowledge of the rocket's aerodynamic characteristics," then uses plain PI control to track that commanded acceleration (not apogee-error) with the airbrake | AIAA 2025-0111 |

### 2.2 Direct evidence detail

- **UMD/Karkinos — the most detailed head-to-head comparison found.** Their own published paper
  directly compares MPC, four PID variants (two different error definitions: raw-height-error vs.
  predicted-apogee-error), and two LQR variants (same two error definitions) in a validated Simulink
  model, scored on apogee error under uncertainty, robustness, and actuator conservation: "The MPC
  resulted in the lowest score, making it the most suitable controller... through a cumulative weighted
  apogee error... this paper determined that the Model-Predictive Controller, rather than
  Proportional-Integral-Derivative or Linear-Quadratic Regulator controllers, was best suited." Their
  MPC is a **brute-force binary search over flap angle (0–85°, 5° resolution) at 10 Hz, each candidate
  forward-simulated to apogee assuming the angle is held constant for the rest of flight** — i.e.
  exactly the hypothesis's "Predictive P/PD" forward-simulation mechanism, just with the error fed to a
  discrete search-and-select rather than a continuous P/PD gain, and explicitly named "MPC" by the
  authors despite not optimizing a time-varying extension profile. — UMD, *The Evaluation of Various
  Controller Architectures for an Air Brake on a High-Powered Model Rocket*,
  https://api.drum.lib.umd.edu/server/api/core/bitstreams/c267150f-d411-40df-9880-4e780d6b364b/content
  - Kyle Kingsberry's first-person account of implementing this same Terrapin MPC confirms the
    algorithm structure independently: "Executed a binary search across the airbrake deployment range
    (0°–90°). For each candidate angle, ran a forward trajectory simulation from the current state to
    predicted apogee. Identified the deployment angle that brought the predicted apogee closest to the
    target altitude." He also reports a field-discovered sensor problem directly relevant to Area 1:
    airbrake deployment near Mach 1 caused local pressure disturbances producing 50–200 m baro altitude
    errors, corrected empirically via a wind-tunnel-derived function f(h,v,δ) = c·q·sin(δ), c=0.052,
    R²=0.97. — https://www.kylek.tech/projects/terrapin-rocket-team-airbrake
  - **Terminology note / possible contradiction to flag:** both UMD sources call this architecture
    "MPC," but by the classic controls-theory definition (optimize a control sequence/profile over a
    receding horizon, not just a single held-constant-value one-step-ahead search), this is closer to
    the hypothesis's "Predictive P-style" bucket (option 1) than to "true" MPC (option 3, which would
    optimize an extension-vs-time profile under rate constraints). This is a terminology mismatch
    between the rocketry-team usage of "MPC" and the controls-literature usage, worth flagging
    explicitly rather than smoothing over: **in the surveyed rocketry sources, "MPC" almost always means
    "one-step-ahead binary/brute-force search over a constant-extension forward simulation," not a
    multi-step receding-horizon trajectory optimization.**
- **UGA IREC, Mississippi State Space Cowboys, uOttawa "Simple Latte"** all explicitly describe their
  chosen/planned architecture as "Model Predictive Control" in the same loose sense (forward
  simulation + search/selection over candidate drag/extension values, graded by predicted apogee error),
  reinforcing that this loosely-defined "MPC" label is the most common self-description among
  SAC/IREC-caliber teams for *some* predictive forward-simulation approach, even though implementation
  details vary and are not always disclosed in the detail UMD provides. —
  https://region2.aiaastudentconference.org/collection/2025/manuscripts/98650.pdf ;
  Sprague, T.; Sanipara, N.; Belew, A., *Design and Analysis of a High-Powered Rocket Airbrake System*,
  https://doi.org/10.2514/6.2024-85628 ; https://www.soundingrocket.org/uploads/9/0/6/4/9064598/55_project_report.pdf
- **TARS (Bregin & Jaffar, AIAA 2024-2388):** "a state-estimation scheme and a model predictive
  controller are developed, tested, and experimentally validated" for apogee targeting — another named
  MPC implementation, cited directly by the Woody & Van Bibber 2025 paper as prior work that performs
  "extensive wind tunnel testing on the air brake to estimate the parameters of an apogee prediction
  function. This function is numerically integrated in flight, predicting the apogee altitudes of
  various air brake positions to determine the best control action" — again the same
  forward-simulate-and-select pattern. — https://doi.org/10.2514/6.2024-2388
- **UNH SEDS HAAMSHR — closest documented analogue to the hypothesis's "switching-curve / bounding
  trajectory blend" (option 2):** their controller forward-integrates acceleration/velocity/altitude
  to predict apogee, then "employs a bisection algorithm. At each control loop iteration, the algorithm
  maintains an upper and lower bound on the drag coefficient. The midpoint... is evaluated... This
  process converges the required drag coefficient over successive control loop cycles. The converged
  coefficient is then mapped to a corresponding servo angle via a lookup table, with linear
  interpolation." This is bisection over a Cd bound (converging across *multiple* control cycles) rather
  than a one-shot proportional interpolation between two forward-simulated apogee extremes computed in a
  *single* cycle, so it is a cousin of the hypothesis's option 2 rather than an exact match — but it is
  the only source found that frames the problem explicitly in terms of bounding the achievable range and
  searching within it. — https://scholars.unh.edu/cgi/viewcontent.cgi?article=1960&context=honors
- **EUCASS 2019 "Chance-Constrained Optimal Altitude Control of a Rocket" — closest match to a formal
  switching-curve/bounding-trajectory *and* bang-bang discussion, academic/offline-table approach:**
  explicitly defines two boundary trajectories "γmin(v) and γmax(v)... computed by back-propagating
  f(·) in time from the apogee altitude hgoal±Δhgoal, assuming full and zero deployment of the
  airbrakes" to bound the reachable/controllable state-space region — directly matching the
  hypothesis's description of predicting apogee at both brake extremes to bound the problem. However,
  rather than interpolating a continuous extension in real time between the two bounds, this paper
  solves a full chance-constrained infinite-horizon optimal control problem **offline**, storing the
  result as a **state-feedback lookup table** flown on the actual rocket, reporting "a successfully flown
  apogee altitude error of 1% for a target altitude of 800m." The paper explicitly discusses why it
  avoids a literal bang-bang controller despite that being the natural unconstrained-optimal shape:
  "solving optimal control problems can result in bang-bang type controllers, which would not capture
  the true behavior of this system" because "the airbrakes actuator delays are comparable to control
  update rates," so input-rate constraints are built into the offline optimization instead. This is
  presented as **flown** (the France-based EuRoC-caliber team the paper doesn't explicitly name, but
  the paper cites the Spaceport America Cup and describes an actual single-attempt competition flight
  with reported real apogee error), making it one of the few sources here combining real flight results
  with a non-MPC, non-PID named architecture (offline chance-constrained DP/optimal control → online
  lookup table). — https://www.eucass.eu/doi/EUCASS2019-0388.pdf
- **Adaptive/online drag-mismatch correction layer (hypothesis option 4) — found as a real,
  documented practice, both in a flown system and in a 2025 academic comparison:**
  - Virginia Tech "ROADKILL" report: "The current step drag coefficient is computed from the
    filtered altitude, the z-axis component of acceleration, and the fused climb rate... The difference
    of the estimated optimal drag coefficient... and the current computed drag coefficient is given as
    the input for a... PID controller. A PID controller is used to adapt an interpolated curve
    correlating the simulated drag coefficient and percentage deployment of the ADS." This is a direct
    real-world instance of option 4 (online model-mismatch correction feeding a PID), implemented as the
    team's primary controller rather than an add-on layer. — https://rocketryatvirginiatech.org/_astro/2024-2025_ROADKILL_Report.BljWahVu.pdf
  - LASC 2025 paper (Marinato et al.) independently and explicitly frames "Gain Scheduling" as "an
    adaptive layer... applied to both strategies [P+PI cascade and LQR]" to "ensure robust performance"
    across "a wide operational envelope," reporting apogee error held below 2% in simulation — i.e. the
    same conceptual layering (adaptive correction on top of a simpler controller) independently reached
    by a different team for a different (model-rocket-scale, LASC) competition. — Marinato, M.S. et al.,
    *Design and Comparative Analysis of Adaptive Control Strategies for Model Rocket Apogee Precision*,
    https://doi.org/10.1109/sepoc67005.2025.11297638
- **Related but distinct: active fault/effectiveness diagnosis, not a control law per se.** A 2026
  preprint (Pendyala, Martin, Venza) studies how to *detect* reduced airbrake effectiveness
  (actuator/aero degradation) under atmospheric uncertainty using diagnostic test pulses scored by
  information gained vs. apogee cost — this is adjacent to "adaptive correction" (option 4) but is
  specifically about fault diagnosis rather than routine Cd-mismatch feedback; included here because it
  is the most recent (2026) academic work found still actively extending this exact problem space, and
  because it explicitly assumes "most of these studies [cites drag modulation/controller design/adaptive
  apogee prediction] assume the airbrake effect is known well enough for control" — implying the authors
  view routine online Cd-correction as already the accepted baseline practice for this research line,
  with their own contribution addressing the harder fault case on top of it. — Pendyala, N.; Martin, B.;
  Venza, F., *Cost–Information Tradeoffs in Active Diagnosis of Rocket Airbrake Effectiveness Under
  Atmospheric Uncertainty*, https://doi.org/10.31224/8473
- **Sliding-mode control / feedback linearization:** no source found applying either specifically to
  rocket airbrake/drag-modulation apogee control. The only "sliding mode" hit was a generic university
  optimal-control lecture slide noting that bounded-input optimal control problems tend toward bang-bang
  solutions, "compare lecture on sliding mode controllers" — a theoretical cross-reference in a general
  controls course, not evidence of rocketry application. This is a **gap, not a contradiction**: absence
  of evidence, not evidence of rejection — it may simply not have surfaced in this search, or genuinely
  not be published for this exact application.
- **Bang-bang / on-off control as the literal final controller:** not found flown as-is in any source;
  every source that raises bang-bang control (EUCASS 2019, UMD baseline framing) treats it either as the
  theoretical limiting case to be *avoided/softened* because of actuator rate limits, or as a baseline not
  selected. This directly supports the hypothesis's framing of the "switching-curve blend" as a
  *softened* real-time analogue of bang-bang, consistent with why teams instead reach for continuous
  proportional/predictive/MPC-labeled methods or offline-optimized lookup tables with built-in rate
  constraints.
- **A distinct, independently-named alternative not explicitly in the hypothesis's list: closed-form
  analytic guidance + PI tracking (Woody & Van Bibber, AIAA 2025-0111).** Rather than predicting apogee
  numerically (forward simulation/search) or optimizing online (MPC) or running raw-state PID, this
  paper **analytically derives**, via separation of variables on the coast-phase equations of motion, the
  instantaneous deceleration the vehicle needs to be experiencing right now in order to reach the target
  apogee exactly — explicitly "without knowledge of the rocket's aerodynamic characteristics" — and then
  uses an ordinary PI controller to drive the airbrake so that *measured* vertical deceleration tracks
  that *commanded* deceleration (not to drive predicted-apogee-error or raw altitude/velocity to a
  setpoint). The authors report "preliminary analysis of the guidance algorithm shows good agreement
  with test flight data," i.e. this has been flight-tested, not simulation-only. This is architecturally
  distinct from both plain state-feedback PID (which the hypothesis correctly argues is a poor fit) and
  from forward-simulation-based MPC/predictive-P — it sidesteps needing a full drag/Cd model altogether
  by working in closed-form kinematics plus a tracked-acceleration inner loop. Given it is explicitly
  framed by its authors as a "novel guidance and control system," it does not appear to be a widely-used
  prior-art approach elsewhere in the literature surveyed — it appears to be its own contribution, albeit
  one with reported flight validation. — Woody, K.; Van Bibber, C., AIAA 2025-0111,
  https://doi.org/10.2514/6.2025-0111

### 2.3 "Simplest thing that works" — explicit consensus signal

No single source makes a blanket claim like "PID is definitively insufficient, use X" as a declared
industry consensus; this is a fragmented, actively-researched space where different SAC/IREC/EuRoC/LASC
teams land on different architectures, generally justified by their own simulation comparisons rather
than citing an external consensus. That said, the pattern across sources skews toward:

- The one head-to-head, quantitative, same-team comparison found (UMD/Karkinos) favors a
  **brute-force one-step-ahead forward-simulation-and-select scheme** (loosely labeled "MPC" by the team)
  over raw-state PID and LQR, specifically because it directly optimizes the terminal quantity (apogee)
  rather than an instantaneous setpoint — this is presented by the paper as the deciding factor, matching
  the hypothesis's own stated reasoning for why plain PID is a poor fit.
  — https://api.drum.lib.umd.edu/server/api/core/bitstreams/c267150f-d411-40df-9880-4e780d6b364b/content
- At the same time, multiple teams (UMD comparative paper's own PID/LQR variants, Virginia Tech
  ROADKILL, LASC 2025 paper) do successfully fly or simulate **PID/LQR driven by predicted-apogee-error
  (not raw altitude/velocity error)** rather than discarding PID outright — i.e. the actually-common
  "simplest-thing-that-works" pattern across these sources is not "avoid PID entirely" but **"replace
  the PID/LQR error signal from raw state to predicted-terminal-apogee error, computed via a forward
  simulation or closed-form kinematic model each cycle"** — which collapses the hypothesis's option-1
  ("Predictive P/PD") and parts of option 3/4 into a single widely-recurring pattern: *a one-step-ahead
  apogee predictor (closed-form kinematics or forward-integrated numerical sim) feeding a conventional
  low-order controller (P, PI, or PID) on the predicted-apogee error, sometimes layered with gain
  scheduling or Cd-mismatch adaptation.* True receding-horizon trajectory optimization over a full
  extension-vs-time profile (hypothesis's strict option 3) was **not found as a flown implementation**
  in any source surveyed — every "MPC" label found in a flown/competition-report context resolves, on
  inspection of its described algorithm, to a one-step-ahead held-constant-extension search, not a
  genuine multi-step profile optimization under actuator-rate constraints. The EUCASS 2019 offline
  chance-constrained lookup table is the one exception that does formally handle a full
  trajectory/profile-level optimization — but it is computed offline, not re-solved online each cycle,
  so it does not match the hypothesis's strict "receding horizon, re-solved each cycle" definition of
  option 3 either.

---

## Gaps and unresolved items

- Could not confirm the specific internal role of GPS/GNSS velocity (if any) in the Terrapin/Karkinos
  EKF's airbrake control loop — the sources found describe the sensor suite ("barometer, IMU, and GPS")
  but not the EKF's exact use of the GPS channel in enough detail to say whether it contributes a
  horizontal-velocity term consumed by the controller.
  - Whether any flown competition airbrake system uses a true receding-horizon MPC (multi-step
  extension-vs-time profile optimization under actuator rate constraints, re-solved every cycle) could
  not be confirmed — every "MPC"-labeled flown/reported system examined in detail resolved to a
  one-step-ahead forward-simulate-and-select scheme.
- Could not find a source directly describing or rejecting sliding-mode control or feedback
  linearization for this specific rocket-airbrake application — absence of evidence only, not located
  in Exa search results for the queries used.
- The "Industrial Monitor Direct" blog hit (knowledgebase article dated 2026-10-14,
  https://industrialmonitordirect.com/blogs/knowledgebase/configuring-rocket-airbrake-pid-for-predicted-apogee)
  reads like generic/SEO-oriented technical content rather than a primary source tied to any specific
  flown rocket or team; it was not used as a citation basis for any claim above and is flagged here only
  because it surfaced in search — do not treat it as a primary source if encountered again.
- Not independently verified: whether the EUCASS 2019 chance-constrained-DP rocket was flown by a named,
  identifiable team (the paper references Spaceport America Cup contextually and reports flown-flight
  apogee error, but the excerpt obtained did not include an explicit team name/rocket name) — flagged as
  a minor provenance gap, not a contradiction of the finding itself.

---

End of findings.
