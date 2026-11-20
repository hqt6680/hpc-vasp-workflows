# MnInP₂Te₆ TB2J

Source `../scf`, which matches `../relax/CONTCAR` and `../band/POSCAR`.
Fixed test geometry (a=7.02958685 Å, c=20 Å), same PBE PAW and PBE+Ueff=1.8736 eV on Mn, ENCUT=600 eV, Gaussian 0.05 eV, Γ 9×9×1. SOC x/y/z uses VASP 6.5.1 ncl, SAXIS fixed to Cartesian z and each Mn MAGMOM aligned to its own Cartesian axis. Start without external CHGCAR to avoid transferring a spin axis. Check the final direction and EDIFF before using each spinor Hamiltonian. Full uniform mesh via ISYM=-1. 28 ranks, KPAR=7, NCORE=1 for ncl and NBANDS=112. Legacy 58 spinors (Mn d, Te p, P p) plus In s/p to capture hybridization; 66 spinors total. Windows will be chosen from actual eigenvalues/projections. Export Wannier matrices first and run Wannier90 separately.

- SOC z: PBS `52255.master`.

- SOC x: PBS `52256.master`.

## Evidence

- The original dependency chain 52257–52268 was withdrawn before any of those jobs started (PBS F/substate 91, no start time or exit status). The separately accepted stages below supersede those entries.

- The test scalar-relativistic bands cross the Fermi level. The In s/p projection contributes on average 0.143 per eigenstate in the absolute range −1.1 to −0.5 eV of the test path. Include In s/p in the 66-spinor starting basis and verify using the SOC path.
- TB2J 0.9.22 / HamiltonIO 0.3.8 in `env/` (pins in `tb2j-requirements.txt`). The installed reader omits both Wigner–Seitz weights and per-pair shortest images. `prepare_tb2j_hr.py` folds these into a separate unit-degeneracy HR and compares spectra through the actual reader. On historical input, the raw reader deviated by up to 231 meV from the globally weighted reference at 12 test points. The pair-weighted staged file reproduced the pair-mode Hamiltonian eigenvalues to 2.4e−14 eV. These checks concern the reader, and the historical electronic/magnetic results remain prior trial data.
- Historical outputs also exercise the exchange audit: it detects the ~1 meV discrepancy between two Jiso fields for the same bond. A synthetic x/y/z case with trace standardization exercises full-rank reconstruction and the validation of transverse projections.
- Preflight: correct PAW species ordering and 30 vector MAGMOM components. The AICC scalar MAGMOM count warning was replaced by checking the actual 3N components. ISYM=-1 preserves the full k mesh and 9×9×1 follows the reference method.

- The independent 120-point line runs use 80 spinor bands to reduce memory on the small nodes. Their target is the occupied and near-Fermi interpolation window; the uniform SOC runs keep 112 spinor bands for the outer Wannier window. The path check must confirm the available 80 bands extend above the comparison interval.

- VASP 6.5.1's in-process interface uses INCAR `NUM_WANN` for the AMN dimension. The legacy mode can leave the minimal user .win without metadata. The held y branch was updated before start to use explicit `NUM_WANN=66` and `WANNIER90_WIN`. The active x/z legacy exports will be inspected for dimensions; if they require a corrected export, preserve their SCF and rerun only the interface from the validated same-axis converged state where possible.

- For already-running legacy x/z, the on-disk input consumed at interface time contains 112 valid trial projectors, with the intended 66 first, to avoid zero/uninitialized trailing projectors from VASP's PAW-based internal count. Original intended and interface inputs are preserved as `wannier90.target.win` and `wannier90.padded.win`. The post-check retains exactly the intended columns only after verifying the LOCPROJ spin pair order and complete AMN indices, and reconstructs standalone .win from the exact VASP full mesh. The y job uses the direct explicit 66-projector interface. Compare x/y/z conventions and projected spectra during validation.

- The first y SCF attempt started from the converged scalar `test/scf/CHGCAR` as an initial guess (`ICHARG=1`, full SOC self-consistency), with its magnetization FFT grid and PAW spin occupancies placed in Cartesian y, x/z set to zero, and charge + PAW charge retained byte-for-byte. `SAXIS=0 0 1` throughout. Geometry, POTCAR, FFT grid and LMAXMIX were checked. The seed and its manifest are kept as `y/CHGCAR.seed` and `y/seed.json`. Confirm that VASP read all three channels and compare the final Mn moment and electronic state to x/z.

## PBS submission sequence

- Withdrew pending `52268.master` from `audit/job.id`.
- Withdrew pending `52267.master` from `merge.id`.
- Withdrew pending `52266.master` from `y/tb2j.id`.
- Withdrew pending `52265.master` from `x/tb2j.id`.
- Withdrew pending `52264.master` from `z/tb2j.id`.
- Withdrew pending `52263.master` from `y/post.id`.
- Withdrew pending `52262.master` from `x/post.id`.
- Withdrew pending `52261.master` from `z/post.id`.
- Withdrew pending `52260.master` from `y/band/job.id`.
- Withdrew pending `52259.master` from `x/band/job.id`.
- Withdrew pending `52258.master` from `z/band/job.id`.
- Withdrew pending `52257.master` from `y/job.id`.

Only the currently runnable stage is submitted. Validate each producing step before releasing the next one.

- SOC y submitted after x/z scheduler completion and input preflight, PBS `52274.master`, node04.

- SOC z and x completed successfully after 42 and 41 DAV iterations at EDIFF=1e-8. Mn moment 4.253 μB each, angular deviation 0° and 0.0135°. Both show bands 72/73 crossing the uniform-grid Fermi level (z −0.80840238 eV, x −0.81605811 eV). AICC parser reports in each branch's aicc.txt; vector and matrix checks in source.json. Both original AMN exports had 100 columns; verified the first 66 against site, orbital and spin order and kept the original as wannier90.export.amn. The reduced AMN and reconstructed .win use 112 bands and the exact 81 k points. MMN uses 8 neighbours.
- Band z submitted after validating the SOC source, PBS 52275.master, node03, 80 spinor bands on G–M–K–G. Band x remains ready for submission when a small-node slot opens.

- Startup check for socy: VASP read the scalar charge density from the input CHGCAR and initialized the spin density from the Cartesian y MAGMOM. The log reports "magnetization density of overlapping atoms calculated", so the copied PAW/spin channels in the trial seed were not accepted. This is still a fully self-consistent SOC run. Check the final Mn direction and the metallic bands before releasing its downstream stages.

- Band z 52275.master passed AICC and fixed-density validation. 120 k points, 80 spinor bands, Mn 4.244 μB, angle 0.076°. The line-run EF is diagnostic, Wannier and TB2J use the uniform-grid EF. Submitted Wannier z fits as 52278.master on node03.

- Requested cancellation of SOC y 52274.master after about 50 min with no first DAV or progress beyond initial charge setup. The custom CHGCAR had incompatible fixed-width records in the zero spin grids; VASP accepted charge and fell back to the initial magnetic moments. Prepared a fresh retry with ICHARG=2, matching the successful x/z initialization, explicit 66-projector export, and WAVECAR output for recovery.

- Original SOC y 52274.master ended with PBS exit 271 after cancellation. Fresh SOC y started as 52279.master in y on node04.

- Cleanup: removed the failed y_seed directory (591 MiB), retired PBS marker copies, superseded tutorial draft, failed seed helper and empty files from completed jobs. PBS IDs and the failure diagnosis remain above.

- Band x passed input preflight and submitted as 52285.master on node03, the same small node used for band z.

- Wannier z 52278.master failed its fit gate. All three trial windows reproduce the same-k path, but none reached MLWF localization convergence. Fits 1 and 3 reached disentanglement convergence, with near-EF RMS/maximum errors of 0.079/0.283 and 0.075/0.237 meV. Late localization increased In-pair separation above the 0.8 Å check (1.22–1.48 Å across trials), although atom assignment and Mn pairs remain good. Initial projected gauges for windows 1 and 3 have maximum pair separations 0.0394 and 0.0390 Å, respectively. Staged projected.pbs to test these windows with num_iter=0 on the same matrices, requiring converged disentanglement, correct projection order and centres, band agreement and reader checks. Also compare the two accepted windows at fixed TB2J parameters before final interpretation. Current active jobs are socy 52279.master on node04 and bandx 52285.master on node03. When a small-node slot opens, submit the z projection trial and continue per-axis path and fit gates.

- Removed the unused large checkpoint and Hamiltonian exports of z/fit2 after recording the failed disentanglement and band diagnostics. Kept the input, logs, centre and fit metrics.

- Band x 52285.master passed AICC and fixed-density validation (120 k points, 80 spinor bands, Mn 4.242 muB, axis deviation 0.133 degrees). Started z projection-window trials as 52290.master on node03.

- Projected Wannier z 52290.master passed both windows. Maximum pair separations were 0.03938 and 0.03898 angstrom, near-EF maximum path errors 1.312 and 1.318 meV, and the 140-point HamiltonIO check agreed within 3e-14 eV. Main window z/proj is selected and z/proj2 is reserved for sensitivity. Started corresponding x fits as 52291.master on node03.

- After both projected z fits passed, removed superseded MLWF trial checkpoints and Hamiltonian exports in z/fit and z/fit3. Retained the logs, input windows and diagnostics.

- Projected Wannier x 52291.master passed both windows. Near-EF maximum errors 1.074 and 0.924 meV, maximum spinor pair distance 0.00942 and 0.00661 angstrom. Retained x/proj as the primary shared window and x/proj2 for sensitivity. Submitted x TB2J mesh, pole and temperature sweep as 52292.master on node03.

- Submitted z TB2J numerical integration sweep as 52293.master on node03 after x job ended.

- TB2J x 52292.master passed checks on all five settings, with 42 directed bonds each and Mn moment 4.459–4.460 muB aligned within 0.006 degrees of VASP. 25 to 35 mesh changes max Jiso/D/Jani by 0.00157/0.00123/0.00377 meV. Pole-count change was below 0.00001 meV. The 300 to 150 K change at 35 mesh was 0.08668/0.06459/0.30206 meV, so evaluate temperature and possible mesh dependence of the merged anisotropic terms.

- TB2J z 52293.master passed all five runs, 42 directed bonds, Mn moment 4.4588–4.4599 muB, less than 0.002 degree from VASP. From 25 to 35 mesh the largest Jiso/D/Jani changes were 0.00478/0.00136/0.00484 meV. Pole-count change was below 0.00001 meV. From 300 to 150 K the largest changes were 0.08603/0.07002/0.32954 meV. Submitted x/z sensitivity runs in 52294.master on node03 to compare the second Wannier window against n180 and verify whether the 150 K shifts persist on a 51×51×1 integration mesh. Reuse these matched settings for y once it passes validation.

- Sensitivity job 52294.master passed all four checks. In x/z, changing to the alternate projection window at 300 K changed Jiso/D/Jani by at most 0.00319/0.00277/0.00372 and 0.00222/0.00198/0.00521 meV. Refining the 150 K grid from 35 to 51 changed them by at most 0.00647/0.00442/0.00436 and 0.00628/0.00272/0.01262 meV, respectively. Thus the earlier 300–150 K differences cannot be explained by the tested k-mesh error. Here K parameterizes the numerical CFR broadening. The staged merge reads all matched data and reports low-broadening mesh and alternate-window sensitivity separately. After y band and projection acceptance, run the five main settings and the matching w180/t150k51 integrations for y before merging.

- SOC y 52279.master passed PBS and VASP checks (42 DAV, 81 k points, 112 bands, 66 AMN spinors, E_F -0.81566490 eV, Mn (0,4.253,0) muB). Charge and wavefunction exports are nonempty. Submitted bandy as 52295.master on node04 after verifying the fixed-density input and 30-component MAGMOM.

- Band y 52295.master passed PBS and fixed-density VASP checks (12 DAV, 120 path k points, 80 bands, Mn 4.242 muB, axis deviation 0.091 degrees). Started the two matched Wannier windows as 52296.master on small node03.

- Projected Wannier y 52296.master passed both windows and staged-Hamiltonian reader checks. Near-EF path maximum errors 0.874 and 1.041 meV, spinor-pair maximum separations 0.00897 and 0.00693 angstrom. Submitted the seven x/z-matched TB2J settings as 52297.master on small node03.

- TB2J y 52297.master passed all seven matched settings with 42 directed Mn1 bonds each and Mn axis deviation below 0.004 degrees. Rechecked 21 completed run manifests, six weighted Hamiltonian hashes and common directed bond keys. At 150 K, changing the mesh from 35 to 51 changed the maximum Jiso/DMI/Jani components by 0.00744/0.00508/0.00739 meV. From 300 K to 150 K the largest changes were 0.08856/0.07258/0.30378 meV. Submitted the three-axis merge and projection checks as 52303.master on small node03.

- Merge 52303.master finished on small node03, PBS F/0, 16 s. Independently reread and checked all seven output pickles, text/Multibinit exports, 42 directed keys per setting, reversal identities and C3 key completeness. The moment/DMI/symmetric exchange ranks are 3/3/6. All seven numerical comparisons were reproduced from the underlying pickles. The final summary and SOC/Wannier overlays were generated from accepted inputs with the case Python environment, without a separate PBS audit job.
- The 300 K baseline is `merged/n180` (35×35×1, 180 CFR poles), and the 150 K comparison is `merged/t150k51` (51×51×1, 180 poles). The 300 K first shell averages Jiso=0.917484 meV at 7.029587 Å (six directed bonds). The 150 K first shell averages 0.869473 meV. See `audit/summary.md` and the two `bonds.csv` files for signed components and `audit/soc_band_overlay.pdf` for the same-k DFT/Wannier band overlay.
- The 300→150 K CFR comparison changes Jiso/D/Jani by at most 0.09014/0.07266/0.00984 meV. The DMI change exceeds the 0.05 meV comparison threshold and is much larger than the 150 K mesh refinement change (0.00357 meV). The n180 fit-to-branches maximum transverse residuals are 0.08724 meV for DMI and 0.05397 meV for the full symmetric exchange block. Keep both finite-broadening results and record these residuals when interpreting small terms. The VASP/Wannier source mesh remains 9×9×1.
- Historical comparison is archived in `audit/history.md` and `audit/history_merged_{n180,t150k51}.{json,csv}`. Exact directed-key matching gives 42 common bonds. The historical first-shell Jiso detail differs from its table by 1 meV on six directed bonds. Pickle and Multibinit agree and provide the archived values used in the comparison.
