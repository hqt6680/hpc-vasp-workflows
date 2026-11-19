---
name: zjt-aicc
description: Use AI Computational Chemist (AICC) for materials or chemistry calculations on the zjt server in hqt, including VASP/DFT, electronic structure, SOC, phonons, input preparation, PBS submission and recovery, convergence checks, and research reproduction. 在 zjt 的 hqt 准备、运行、续算或验收科研计算时使用。
---

# AICC on zjt

1. Connect with `ssh -o BatchMode=yes zjt`. Explicitly start in `/public/home/zjt/task/now/hqt` and verify the current identity, host, and resolved path. Read `hqt/AGENTS.md` first.
2. Under `hqt/.auto-computational-chemist`, read `AGENTS.md` for skill routing and `site-zjt.md` for the installed engine, PBS templates, and Python runtime. Read both through SSH. The site guide supplies the cluster facts for this workspace.
3. Select the relevant remote `SKILL.md`. Use `tools/vasp/SKILL.md` for VASP and `tools/hpc-submit/SKILL.md` for PBS. Start multi-stage or reproduction work with `procedures/comp-chem-workflow/SKILL.md`. Resolve `tools/`, `procedures/`, and `knowledge/` relative to the collection root, and `scripts/` and `references/` relative to the selected skill directory.
4. Use the intended calculation subdirectory under hqt and the project's established settings. Check inputs before authorized execution and validate outputs after it completes. Use the local and remote workspace rules for SSH, scientific data, and job ownership.
