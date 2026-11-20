# VASP / PBS 工作流交接

本机监听入口为 [scripts/pbs_watch.py](scripts/pbs_watch.py)，通过 SSH 读取已登记的 PBS 作业，并把事件回传到原 Codex 聊天。Codex Desktop 若已对该聊天退订，监听器在确认周额度和代理实例后，可通过官方深链接打开原聊天并重试该事件。

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

全谱 DFPT 作业 `53586.master` 于 11 月 20 日 23:37 在 `node06` 启动，工作目录为 `phon3/dfpt/`，28 MPI ranks，`IBRION=8`、`EDIFF=1E-7`，PBS 已登记回传且省略 walltime。结束后核对基态和每个响应的原生电子收敛、参考原子力和 OUTCAR 的总力漂移。运行 `validate dfpt` 和 `spectrum`，检查 Γ、X、Y、M、Γ–X–M–Y–Γ–M 路径及 40×40×1 q 网格，比较原始和声学和则处理后的低频振型。验收后更新 Master 的重优化和声子教程。

下表为本次 SSH 核验的 SHA-256，路径相对于 `/public/home/zjt/task/now/hqt`。教程与作业表后续按验收结果更新。

| 文件 | SHA-256 |
| --- | --- |
| `Master/K2CrF4.md` | `c4bd21b34a0daf92e05f3c6df2d43122fe49ec2a0b2d3403c84e4edc79d0951c` |
| `Master/phonopy.md` | `9905a7f4c7540934f320d7f721731941b433374c35809c43d1abe0cb0726a77d` |
| `Master/relax+scf.md` | `f39402427724e60c7c7384817f963e6234413ef40e83990d2b359844fc52ec7d` |
| `Master/case_index.md` | `99e539ac4bb839b1fb67a3e0c4c839706171710524aeb0648cbce46d2cc67c35` |
| `Master/vasp_environment.md` | `8ef5337d470da662a6203f14fd31a5440746d280df43503d513f7b0e38d741ed` |
| `Materials/examples/K2CrF4/workflow.md` | `3874239a93cc9588078acf0a8bb8432a5deee171ea045808d9325d7a0922385c` |
| `Materials/examples/K2CrF4/gamma/hessian.py` | `ce4ff3ffbd39a86dc542dd67fd1d889d80626b574a758e4fc4294899cc13a7cf` |
| `Materials/examples/K2CrF4/gamma/hessian.pbs` | `933630f2ea55b70cf4b7eb2084e2f3b29882283a199686ff34c1e5fd8a734497` |
| `Materials/examples/K2CrF4/phon3/phon3.py` | `0d64f90c7815aa768cb32bff124218b7b19d683397e6bc2bff27a9c55aa21c20` |
| `Materials/examples/K2CrF4/phon3/run.pbs` | `e7b32812f30b755661fc5d882fe889e188f3ce8c9e496d7f7a4520e259754cf0` |
