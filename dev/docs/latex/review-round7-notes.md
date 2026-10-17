# Review round 7 - change log

Line refs: models.tex (M), other-dynamics.tex (O), appendix.tex (A), main.tex. Approximate after edits.

1. Thrust noise (M ~730): `\vec{T}_s = kappa T xi z_t` (z_t from eq:thrust_frame); one sentence: enters EOM as part of thrust at t, adds moment about g. Bullet list folded into one sentence. Roll torque: 2 sentences from round7 findings (out of plane, no 2D effect, star/finned grains, 163 N m SCOUT peak, no prediction method), `\restodo` for small-motor magnitude/model. New bib `knauberroll`.
2. Relwind merged into sec:aero as first subsubsection (M ~342, label sec:relwind kept). Single alpha definition (atan2, body frame, (-180,180]); alpha text removed from "Axial force" paragraph; hat u / hat n dropped (unused); "Dynamic pressure" text shortened.
3. Dryden (M ~675-770): cut to essentials. 8785C only; scales eq now via sigma_w (and L_w = h added); compact band table; PSDs u,v; synthesis eq; composition; one limitation sentence. In-plane components stated (w always, u projected, v out of plane / 3D). `\simtodo` w not implemented; one-line note that HDBK-1797 uses L_w=h/2, L_v=L_u/2 (do not mix). New bib `milf8785` (secondary: MathWorks doc; primary spec not read).
4. Earth rotation (M ~800-890): "Checks" sentences deleted; classical checks cut to one sentence; "One residual inconsistency" replaced by one-line `\simtodo` (Omega frame).
5. New `sections-ai/other-dynamics.tex` (`\section{Other dynamics models}`, label sec:other_dynamics) with rail, recovery, air brake; wrapped in aitext in main.tex after models. Models intro (M lines 3-7) updated. Labels unchanged.
6. `F_ch` -> `\vec{R}_{ch}` (eq:chute_eom, eq:chute_force, terminal speed text, A, inventory). P rejected: `P` is the ground point under the rocket (`\vec{O^*P}`, black sec:position_altitude). R chosen though `\vec{R}_0` (launch-site position) and `R_e` exist: the subscript `ch` keeps it distinct.
7. Lumped alternative (O, "Lumped alternative" paragraph): (C_D S)_sys constant or table vs speed; valid for steady descent; misses inflation, shock, pendulum, added mass, risers. Cites Whitmore (sum of drag areas), OpenRocket/RocketPy (recovery device only, via ortech + hprrec). New bibs `whitmore`, `hprrec`.
8. Air brake (O): two variants of the rocket's own aero (own component, eq:airbrake_component; whole-rocket table with f_b axis, per Farha); eq:airbrake_force kept as simplest case (Delta C_x = C_D,b S_b f_b / S). `\simtodo`: only the additive axial term is implemented (forces.py L223-227, times axial_flow_factor). CP shift stated from Farha (3.37 -> 0.25 cal), `\restodo` only for missing C_N data. Law and trigger subsubsections kept; "sampled mode below" now a reference to sec:sampled. aero section no longer mentions the brake (axial-factor sentence and "separate additive drag area" removed). New bib `farha`.
9. Notation (A ~25-110): added z_t, T_s/kappa/xi/tau_c, rho_pr/a_b/n, l_e (round-6 leftovers were absent), R_ch, (C_D S)_sys, f_b, S_b/C_D,b, brake component symbols, tau_s/f_s. Inventory updated (relwind in aero, brake, other_dynamics). code-vs-paper.md: "Round 7 additions" section (Dryden w, v no 2D effect, brake representation, Omega frame, vertical wind, T_s, R_ch).
10. Compile: `~/AppData/Local/Programs/tectonic/tectonic.exe main.tex` (tectonic not on PATH). 0 errors, 0 undefined refs, 0 overfull; main.pdf written in place. Underfull-only warnings remain in the bibliography.
11. Vertical wind (M ~sec:vertical_wind): itemize of orographic lift / thermal updraft / measured balloon profile, each with its own `\restodo`; "Neither fits ..." dropped; `\simtodo` w_z = 0 in all tiers.

Other changes: sample period in sec:sampled renamed T_s -> tau_s (clash with thrust side force T_s).

Open points
- Author name: findings call the SCOUT roll-torque and thrust-misalignment author "Knacke"; the existing bibitem and I use Knauber (R. N. Knauber, believed correct; T. W. Knacke is the parachute manual). Please confirm.
- Process slip: I appended the code-vs-paper.md section with a Bash heredoc (not Write/Edit). Content is correct; no other file was written that way.
- The `L_w` transition/isotropic values (L_w follows L_u above 1000 ft) are in the band table as an extension; check vs spec.
- Sign convention of w (z-down) not yet written in the composition equation (w not implemented).
- The MIL-F-8785C citation is secondary (MathWorks doc); primary text not read.
