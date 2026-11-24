# VASP / PBS 工作流交接

本机监听入口为 [scripts/pbs_watch.py](scripts/pbs_watch.py)，通过 SSH 读取已登记的 PBS 作业，并把事件回传到原 Codex 聊天。Codex Desktop 若已对该聊天退订，监听器在确认周额度和代理实例后，可通过官方深链接打开原聊天并重试该事件。

## zjt 的 MAGMOM 预检

2026-11-24 已修复服务器 AICC 的 `tools/vasp/scripts/check_inputs.py`。显式 `MAGMOM` 展开重复记法后，共线计算检查 N 个数，开启 `LNONCOLLINEAR` 或 `LSORBIT` 时检查 3N 个数，N 取自 POSCAR。MnInP₂Te₆ 的共线 SCF 和 TB2J 三个 SOC 方向均已通过离线预检，另有 11 个输入变体覆盖错误长度、开关和 INCAR 写法。

本站[预检补丁](.agents/skills/zjt-aicc/patches/magmom-preflight.patch)对应 AICC 上游 `e27b555ecfee3a7b66472c19c93b01ad0a1ccae1`。重装该版本时，在服务器 AICC 根目录用 `patch --dry-run -p1` 从标准输入检查补丁，再用 `patch -p1` 应用。原文件、复测脚本和日志在服务器 `hqt/.codex_reports/vasp_audits/magmom_preflight_20261124_JBgj3R/`，需要回退时按 `before/` 内的相对路径恢复。

## 启动和验证

Windows 端需要 Python 3.10+、Node.js 18+、可用的 SSH 别名和正在运行的 Codex Desktop。站点参数见 [PBS 监听说明](scripts/README.md) 和 [配置示例](share/vasp-pbs/assets/project/scripts/pbs_watch.config.example.json)。SSH 密钥、实际站点配置和监听数据库保存在各自设备。

```powershell
.\scripts\install_pbs_watch.ps1 -Action Install -ResumeAtLogon
python scripts/pbs_watch.py status
python -m unittest discover -s scripts -p 'test_*.py'
node --test scripts/test_desktop_delivery.mjs
python scripts/package_vasp_pbs.py "$env:TEMP/vasp-pbs-skill.zip"
```

## 状态和回退

2026-11-23，node12 根分区释放空间后使用率降至 3%，已恢复常规选用。定向 PBS 作业 `53808.master` 通过本地盘读写、共享盘写入、双进程 Intel MPI 通信及标准输出和错误回传验证。记录位于服务器 `hqt/.codex_reports/pbs/node12_disk_20261123/README.md`。

2026-11-20 23:10，旧 IPC 管道缺失时，计划任务通过 Desktop App Tools 把真实 PBS 事件 53522 送入原聊天的活动轮次。监听器核对轮次和完整消息，记录 `steered`，经 SSH 验收后已 `acked`。模拟事件也已验证活动聊天接收和空闲聊天自动开启新轮次，两组各收到一条，排队均为零。项目监听器和技能包共用 [desktop_followup.py](scripts/desktop_followup.py) 选择通道并读取回执。更新后重启同一计划任务即可加载脚本。

2026-11-20 验证通过 42 项 Python 测试、6 项 Node.js 测试和技能包打包。在 Windows 计划任务上，真实待回传事件触发原聊天重开，随后收到 `started` 回执。更新脚本后重启 `CodexVaspPbsWatch` 计划任务，按真实事件的 `started` 或 `steered` 回执确认回传。回退可检出 `5e3eec6` 上的相关监听脚本再重启任务，保留 `%LOCALAPPDATA%/CodexVaspPbs` 的数据库。

## K₂CrF₄ 重构相与声子接续

科研算例的权威版本位于 zjt 的 `/public/home/zjt/task/now/hqt/Materials/examples/K2CrF4/`，用 `ssh -o BatchMode=yes zjt` 访问。连接后先核对账号、主机和实际路径，读取 `hqt/AGENTS.md`、`Master/README.md` 与算例 `workflow.md`。算例输入、运行日志和结果由服务器保存，按本节记录的脚本指纹定位接手版本。

2026-11-20 已独立验收 `52590.master` 的 Γ/M DFPT。VASP 6.5.1、Phonopy 2.19.1，28 原子公度超胞、Γ 5×5×1 电子网格、`IBRION=8`、`EDIFF=1E−8`。基态达到电子阈值，12 个响应方向均完成。相同的原始和声学和则处理结果给出 Γ 点最低非平移模约 `+0.621891 THz`、M 点最低模约 `+1.567035 THz`。这两个点已通过，完整 q 网格稳定性仍待验收。结果入口为 `gamma/check/mix2e8/result.json`，优化结构为 `gamma/relax/mix2/CONTCAR`。

全谱使用 `phon3/` 的 56 原子 2×2×1 超胞和 Γ 4×4×1 电子网格，等效母胞 Γ 8×8×1。`53525.master` 按 STOPCAR 结束，原始输入为 `EDIFF=1E-8`，原验收器退出码为 1。第 38 步两项能量变化为 1.09E−10 和 2.51E−8 eV，按约定的 `1E-7` eV 复核通过。Cr 同向磁矩为 3.708 μB，最大原子力为 0.00080820 eV/Å。复核数据在 `phon3/eq/stop-review.json`。

在算例根可重现手动停算复核。运行环境为 Phonopy 2.19.1、NumPy、spglib 和 Matplotlib。

```bash
PY=/public/home/zjt/anaconda3/envs/python3.10/bin/python
"$PY" -B phon3/phon3.py stop-review eq
```

单个 56 原子作业 `53586.master` 已按要求终止（F/271，第 7 个电子步）。全谱改用 `phon3/small.py` 和 `phon3/small.pbs`。三个 28 原子超胞分别计算 Γ/X、Γ/Y、Γ/M，均用 `IBRION=8`、`EDIFF=1E-7`。每组的 32 个电子 k 点由母胞 Γ 8×8×1 折叠得到。用历史力常数回算，40×40×1 网格上全部 42 支的最大频差小于 3E−7 THz。

11 月 23 日复核，Γ/X `53592.master`（node06）验收通过，12 个响应收敛，最大残力 0.000788 eV/Å。Γ/M `53594.master`（node14）的基态、12 个响应及 84×84 Hessian 已通过复核。用户接受该结果的最大残力 0.001511 eV/Å（常规门槛 0.001 eV/Å）。`phon3/m/result.json` 记录实测值和授权，`small.py` 仅对该 Γ/M 输出识别此例外。两组的实际电子 k 点与权重已核对。此前撤回的 `53593.master` 日志在 `phon3/m/stopped-53593/`。

Γ/Y `53804.master` 已从 node14 队列改派到 node12，11 月 23 日 11:25 在 28 核上启动，沿用原作业号及回传登记。回传后从算例根执行 `"$PY" -B phon3/small.py validate y`，通过后合并三个分支。

全部结束后在算例根执行 `"$PY" -B phon3/small.py merge`。逐组验收基态和各响应、参考残力、总力漂移、磁态和电子网格。复核三份 Γ 矩阵的一致性和四点傅里叶回算误差，检查 `phon3/spectrum-small/` 的 Γ–X–M–Y–Γ–M 色散、40×40×1 网格及施加声学和则前后的低频振型，通过后更新 Master。

本机监听支持迁移前的聊天工作目录。该目录内的“源码”和 `scripts` 两个目录联接分别指向实际 Git 工作区和它的脚本目录。登记和投递均核验聊天归属。

下表为本次 SSH 核验的 SHA-256，路径相对于 `/public/home/zjt/task/now/hqt`。教程与作业表后续按验收结果更新。

| 文件 | SHA-256 |
| --- | --- |
| `Master/K2CrF4.md` | `c4bd21b34a0daf92e05f3c6df2d43122fe49ec2a0b2d3403c84e4edc79d0951c` |
| `Master/phonopy.md` | `9905a7f4c7540934f320d7f721731941b433374c35809c43d1abe0cb0726a77d` |
| `Master/relax+scf.md` | `f39402427724e60c7c7384817f963e6234413ef40e83990d2b359844fc52ec7d` |
| `Master/case_index.md` | `99e539ac4bb839b1fb67a3e0c4c839706171710524aeb0648cbce46d2cc67c35` |
| `Master/vasp_environment.md` | `46e8f5ef61f7ebc122d494cf744a4e20a69e27acd0e7a8192c58c13a4eaff850` |
| `Materials/examples/K2CrF4/workflow.md` | `005bec88a6e70446a60c26cc033f85616174cc1e8464562954fe51c694f5945e` |
| `Materials/examples/K2CrF4/gamma/hessian.py` | `ce4ff3ffbd39a86dc542dd67fd1d889d80626b574a758e4fc4294899cc13a7cf` |
| `Materials/examples/K2CrF4/gamma/hessian.pbs` | `933630f2ea55b70cf4b7eb2084e2f3b29882283a199686ff34c1e5fd8a734497` |
| `Materials/examples/K2CrF4/phon3/phon3.py` | `0d64f90c7815aa768cb32bff124218b7b19d683397e6bc2bff27a9c55aa21c20` |
| `Materials/examples/K2CrF4/phon3/run.pbs` | `e7b32812f30b755661fc5d882fe889e188f3ce8c9e496d7f7a4520e259754cf0` |
| `Materials/examples/K2CrF4/phon3/small.py` | `da91bcef5b3546278026ca2567f5a492fd7b252d575cacb22276258c5c75306e` |
| `Materials/examples/K2CrF4/phon3/small.pbs` | `c5f0b7ca58a2e9746d9281ab13d701b66cc7321a6844b713a1e2a759d5ce403a` |
