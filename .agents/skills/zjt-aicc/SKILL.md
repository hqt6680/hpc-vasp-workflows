---
name: zjt-aicc
description: Use AI Computational Chemist (AICC) for materials or chemistry calculations on the zjt server in hqt, including VASP/DFT, electronic structure, SOC, phonons, input preparation, PBS submission and recovery, convergence checks, and research reproduction. 在 zjt 的 hqt 准备、运行、续算或验收科研计算时使用。
---

# AICC on zjt

1. Use the verified SSH entry for this cluster (`ssh -o BatchMode=yes zjt` when the alias is `zjt`). If it is missing or requires a password, follow the project's `share/vasp-pbs/references/setup.md` SSH setup, one question card at a time. Explicitly start in `/public/home/zjt/task/now/hqt` and verify the current identity, host, and resolved path. Read `hqt/AGENTS.md` first.
2. Under `hqt/.auto-computational-chemist`, read `AGENTS.md` for skill routing and `site-zjt.md` for the installed engine, PBS templates, and Python runtime. Read both through SSH. The site guide supplies the cluster facts for this workspace.
3. Select the relevant remote `SKILL.md`. Use `tools/vasp/SKILL.md` for VASP and `tools/hpc-submit/SKILL.md` for PBS. Start multi-stage or reproduction work with `procedures/comp-chem-workflow/SKILL.md`. Resolve `tools/`, `procedures/`, and `knowledge/` relative to the collection root, and `scripts/` and `references/` relative to the selected skill directory.
4. Read `Master/README.md` for the method and `Master/case_index.md` for a validated case with the same observable, structure and magnetic state. Use its `workflow.md` for inputs, parameters, run order, acceptance checks and result files. Run in the user's case directory. For an active job, consult the case's PBS table.
5. When updating a reference, document the validated route and its scope. Keep pending calculations under “待建设” and job history in the PBS table.
