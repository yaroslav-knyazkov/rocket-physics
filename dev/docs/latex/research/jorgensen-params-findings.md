# Jorgensen large-alpha parameters: fact-check

Date: 2026-10-19. Tools: Exa, Firecrawl. Both hit limits mid-session (Firecrawl: insufficient credits; Exa: free rate limit). Items not covered are listed in section 5.

## 1. eta vs fineness ratio L/d

Definition (primary, NASA TR R-474, sec. 2.3.2, https://ntrs.nasa.gov/api/citations/19770026166/downloads/19770026166.pdf):
"eta is the crossflow drag proportionality factor, that is, the ratio of the crossflow drag coefficient for a finite-length cylinder to that for an infinite-length cylinder."
"Values of eta for circular cylinders at very low crossflow Mach numbers (from ref. 56) are plotted as a function of length/diameter ratio in figure 4."
Measured "only at very low subsonic Mach numbers (refs. 56 and 57)". Flat-plate values are "only slightly less" than circular-cylinder values.
For high crossflow Mach numbers: "For most supersonic and hypersonic values of M_n, eta probably can be assumed to be unity."
TN D-7228 (https://ntrs.nasa.gov/api/citations/19730012271/downloads/19730012271.pdf): "For bodies at supersonic and hypersonic free-stream Mach numbers, experience to date has shown that it is best to assume that eta = 1."

Figure 4 is a graph; the PDF text has no numeric table. I could not read the image myself. The only numeric reading found is a third-party hand digitization of Fig. 4 (printed p. 77, circular-cylinder curve at Re_n = 88,000, from Goldstein), quoted below with its stated accuracy of about +-0.005. Source: HPR Sim crate `hpr_aero::crossflow`, https://hpr.fusionspace.co/api/src/hpr_aero/crossflow.rs.html. It is secondary, not Jorgensen's own numbers.

| L/d | 2 | 4 | 6 | 8 | 10 | 12 | 15 | 20 | 25 | 30 | 35 | 40 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eta (Fig. 4, low M_n) | 0.577 | 0.607 | 0.643 | 0.668 | 0.685 | 0.701 | 0.724 | 0.753 | 0.775 | 0.795 | 0.805 | 0.815 |

The same source holds values constant outside 2..40 (eta = 0.577 below L/d = 2, 0.815 above 40). Those are its clamps, not Jorgensen data. It lists no value for L/d = 1.

Cross-check with the primary source: Jorgensen says Fig. 6 starts (M_n = 0) at about 0.68 and 0.70 "obtained from fig. 4" for the fineness 10 and 12 bodies. This matches the table (0.685 / 0.701).

Verdict on the ticket (0.63 at L/d=1 up to 0.90 at L/d=40):
- Not supported. The Fig. 4 reading gives about 0.58 at L/d=2 and about 0.815 at L/d=40, not 0.90. 0.63 corresponds to L/d of about 5.
- Do not take eta = 0.90 at L/d = 40 from Fig. 4 at low Mach.
- eta rises with crossflow Mach number. Fig. 6 (printed p. 78), bodies with L/d = 10 and 12, M_n = 0.4 to 1.6, hand-read by the same third party:

| M_n | 0 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 | 1.1 | 1.2 | 1.4 | 1.6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eta | 0.69 | 0.717 | 0.804 | 0.815 | 0.845 | 0.994 | 0.979 | 0.769 | 0.910 | 0.937 | 0.985 | 0.984 |

The dip at M_n = 1.0 comes from dividing eta*C_dn (Fig. 5) by the C_dn peak of Fig. 1 (third-party interpretation, same source).
Jorgensen uses Figs. 5 and 6 "in lieu of better information" (p. 18, as quoted by the same source).
Fig. 5, eta*C_dn for L/d 10 and 12 at alpha of 45 to 60 deg (hand-read, same source): M_n 0.5: 1.08, 0.6: 1.20, 0.7: 1.33, 0.8: 1.52, 0.9: 1.55, 1.0: 1.52, 1.1: 1.63, 1.2: 1.61, 1.4: 1.51, 1.6: 1.46.

## 2. Crossflow drag C_dn of a circular cylinder

Primary (TR R-474 sec. 2.3.1, same PDF as above):
- Fig. 1 gives C_dn vs M_n over 0 to 8, built from refs. 44-49 and Macha's Ames 2x2 ft transonic tunnel data. Newtonian theory agrees closely at high M_n.
- Transonic data are "very limited". The black symbols are values extrapolated to d = 0 from cylinders of 1.9 to 5.1 cm, because C_dn rose with decreasing diameter for M_n of about 0.9 to 1.2.
- Critical Reynolds number effect: "if the crossflow Reynolds number Re_n exceeds the critical value of about 2 x 10^5, the value of C_dn decreases considerably" (for M_n below about 0.5). Figs. 2 and 3 show this, with "considerable uncertainty".
- The subcritical subsonic value 1.2 and the supercritical drop to "between about 0.15 and 0.30" are quoted from TR R-474 p. 15 by the HPR source. I did not see those lines in the primary text I retrieved.
- Table 1 of TR R-474 lists a 2-D circular cylinder (Newtonian C_dn 1.33, modified Newtonian 1.20, measured 1.20).
- MIT 2.154 lecture 10, https://ocw.mit.edu/courses/2-154-maneuvering-and-control-of-surface-and-underwater-vehicles-13-49-fall-2004/82221f01b957f94f3767621a759445de_lec10.pdf (secondary, simplified): C_dn = 1.2 for Re_n < 3e5, 0.3 for 3e5 to 7e5, 0.6 above 7e5.

Hand-read Fig. 1, subcritical (same HPR source, +-0.01): 

| M_n | 0 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 | 1.1 | 1.2 | 1.4 | 1.6 | 2.0 | 2.8 | 4.8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C_dn | 1.20 | 1.20 | 1.21 | 1.271 | 1.334 | 1.458 | 1.552 | 1.515 | 1.560 | 1.985 | 1.785 | 1.676 | 1.555 | 1.489 | 1.403 | 1.336 | 1.266 |

Note: the value of 1.985 at M_n = 1.0 is that source's reading of a steep peak (it puts the peak at M_n of about 0.96). Treat it as approximate.
Trend: about 1.2 subsonic, rising to a transonic peak of about 1.6 to 2.0, then falling toward about 1.3 at high M_n (supersonic Newtonian limit about 1.33 for modified/Newtonian 2-D circle).

## 3. Normal force formula

TN D-7228 eq. (1) (https://ntrs.nasa.gov/api/citations/19730012271/downloads/19730012271.pdf, alpha from 0 to 90 deg, constant cross-section shape; text extraction is garbled, structure confirmed by the MIT lecture):
C_N = (A_b/A_r) sin(2 alpha) cos(alpha/2) + eta C_dn (A_p/A_r) sin^2(alpha), and C_A = C_A(alpha=0) cos^2(alpha). 
- A_b = base area (cross-section area at the aft end, for bodies with a blunt base), A_p = planform area, A_r = reference area.
- TR R-474 eq. (2.12), solved for eta C_dn (eq. 2.22 as quoted): eta C_dn = [C_N - sin2alpha cos(alpha/2) (A_b/A_r)] / [(A_p/A_r) sin^2 alpha].
- General form, eq. (2.20) (verbatim from scrape): C_N = sin2alpha cos(alpha/2)/A_r * INT (C_n/C_n0)_SB dA/dx dx + 2 eta C_dn sin^2 alpha / A_r * INT (C_n/C_n0)_Newt r dx. For a circular body the integral of r dx equals A_p/2, which gives the simple form above.
- Eq. (2.11) (pitching moment) has the same two-term structure; the force acts at the planform centroid in the viscous term (HPR source citing eq. 2.21).
- C_L = C_N cos(alpha) - C_A sin(alpha), C_D = C_N sin(alpha) + C_A cos(alpha) (eqs. 2.16, 2.17). Jorgensen: for alpha well away from 0 and 180 deg, precise C_A "is not necessary".
- Mach range and alpha: TR R-474 compares to data for alpha 0 to 180 deg only at M = 2.9; 0 to 60 deg for M = 0.6 to 2.0.

Application for alpha > 90 deg: TN D-7228 states the formulas for alpha 0 to 90 deg. Its predecessor TN D-6996 (Jorgensen 1973) extends to 0 to 180 deg, and TR R-474 uses the same C_N, C_m formulas to 180 deg (abstract: "angles of attack extend from 0 deg to 180 deg for M = 2.9"). The dA/dx term is the "for positive dA/dx" form (eq. 2.20 qualifier), so the potential-flow term applies only on the forward, expanding part of the body. I could not retrieve the exact sign/absolute-value convention for alpha > 90 deg from the text. Assumption: with sin2alpha negative for alpha > 90 deg, the first term changes sign naturally, and sin^2 alpha stays positive. Verify in TN D-6996 / R-474 sec. 2.1 before implementing.

C_A for alpha > 90 deg (eqs. 2.18, 2.19, verbatim from scrape): C_A ~ C_A(alpha=0) cos^2 alpha for 0 to 90 deg; C_A ~ C_A(alpha=180) cos^2 alpha for 90 to 180 deg. "A more precise method is also outlined in reference 9 [TN D-6996], along with procedures for determining C_A(alpha=0) and C_A(alpha=180) for often used conical and tangent ogive noses and flat bases."

## 4. C_A (drag) at alpha = 180 deg

- Jorgensen's method does not set C_A(180) = C_A(0). It treats them as separate inputs, with a procedure in TN D-6996 (https://ntrs.nasa.gov/citations/19730006261) that depends on the aft-end shape (flat base facing the flow acts as a blunt nose). I could not retrieve its numbers.
- Same-structure implementation (Advanced Model Rocket Flight Simulation Software, https://jdiazchao.com/papers/Advanced_Model_Rocket_Flight_Simulation_Software.pdf): C_A = C_A(0) cos^2 alpha for 0 to 90 deg, C_A(180) cos^2 alpha for 90 to 180 deg; for the aft end facing the flow, "the pressure drag coefficient may be considered the same as the stagnation pressure" (Hoerner). The numeric value was not in the extracted text.
- OpenRocket base drag (https://openrocket.sourceforge.net/techdoc.pdf, eq. 3.94): C_D,base = 0.12 + 0.13 M^2 (M < 1), 0.25/M (M >= 1). Relevant to the forward-flying C_A(0); it does not hold when the base faces the flow.
- Flat-ended cylinder drag (Hoerner): not retrieved this session (Exa rate limit). From memory only, no source: a flat-faced circular cylinder in axial flow has C_D of about 0.8 (L/d large) to about 1.1 (disc/short) based on frontal area. Mark as UNVERIFIED assumption. The ticket's 1.0 to 1.2 is also unverified.
- Physical expectation (assumption, not sourced): C_A(180) for a rocket flying base-first is well above C_A(0) of a pointed nose (0.3 to 0.5) because the nozzle/base is a bluff face; C_A(180) = C_A(0) is not a conservative default.

## 5. Not covered / next steps

1. Numeric Fig. 4 values are from a third-party hand reading; for a primary check, view page images of TR R-474 printed p. 77 (PDF page about 85 of 246) or ref. 56 (Goldstein, Modern Developments in Fluid Dynamics).
2. TN D-6996 text for C_A(180) and the treatment of alpha > 90 deg is not read. PDF: https://ntrs.nasa.gov/api/citations/19730006261/downloads/19730006261.pdf. Needs Firecrawl credits or a manual read.
3. Allen & Perkins NACA Report 1048 (1951), NASA TM X-73123: not searched.
4. Flat-faced cylinder drag from Hoerner: not retrieved.
5. TM X-1658 (Jernell 1968, https://ntrs.nasa.gov/citations/19680026721) has measured bodies of revolution at M 1.5 to 2.86 to alpha = 180 deg, including C_A(180); it was not read.
