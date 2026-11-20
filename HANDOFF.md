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

2026-11-20 23:10，旧 IPC 管道缺失时，计划任务通过 Desktop App Tools 把真实 PBS 事件 53522 送入原聊天的活动轮次。监听器核对轮次和完整消息，记录 `steered`，经 SSH 验收后已 `acked`。恢复本版监听后重启同一计划任务即可加载脚本。App Tools 在空闲聊天的表现待真实事件验证。

2026-11-20 验证通过 42 项 Python 测试、6 项 Node.js 测试和技能包打包。在 Windows 计划任务上，真实待回传事件触发原聊天重开，随后收到 `started` 回执。更新脚本后重启 `CodexVaspPbsWatch` 计划任务，按真实事件的 `started` 或 `steered` 回执确认回传。回退可检出 `5e3eec6` 上的相关监听脚本再重启任务，保留 `%LOCALAPPDATA%/CodexVaspPbs` 的数据库。

## K₂CrF₄ 重构相与声子接续

科研算例的权威版本位于 zjt 的 `/public/home/zjt/task/now/hqt/Materials/examples/K2CrF4/`，用 `ssh -o BatchMode=yes zjt` 访问。连接后先核对账号、主机和实际路径，读取 `hqt/AGENTS.md`、`Master/README.md` 与算例 `workflow.md`。算例输入、运行日志和结果由服务器保存，按本节记录的脚本指纹定位接手版本。

2026-11-20 已独立验收 `52590.master` 的 Γ/M DFPT。VASP 6.5.1、Phonopy 2.19.1，28 原子公度超胞、Γ 5×5×1 电子网格、`IBRION=8`、`EDIFF=1E−8`。基态达到电子阈值，12 个响应方向均完成。相同的原始和声学和则处理结果给出 Γ 点最低非平移模约 `+0.621891 THz`、M 点最低模约 `+1.567035 THz`。这两个点已通过，完整 q 网格稳定性仍待验收。结果入口为 `gamma/check/mix2e8/result.json`，优化结构为 `gamma/relax/mix2/CONTCAR`。

下一步使用 `phon3/` 的 56 原子 2×2×1 超胞和 Γ 4×4×1 电子网格，先检验平衡点。该网格展开后对应母胞 Γ 8×8×1。11 月 20 日 20:06 核对时，`53525.master` 正在 `node06` 以 28 MPI ranks 运行，原作业时限已延至 12 小时。工作目录为 `phon3/eq/`，已登记本机 PBS 监听。后续提交按项目规则默认省略 `walltime`。此前 Γ/M 计算的参考最大残力约 `0.00143749 eV/Å`，完整谱阶段先按目标最大残力 `0.001 eV/Å` 核对平衡超胞，必要时继续优化。

11 月 20 日 23:03 已对 `53525.master` 写入 `STOPCAR`（`LABORT=.TRUE.`）。第 22–37 步的总能和带能变化均已低于用户选定的 `1E-7` eV，原始 INCAR 为 `EDIFF=1E-8`。回传后经 SSH 核对 PBS 退出原因、VASP 是否完成收尾、末步两项能量变化、磁态和 56 个原子的最终力。仅在输出完整且最大力达标时放行平衡点。若原验收器因手动停止或原阈值退出，保留原判定并按本次约定另记复核结果。

原阈值验收命令如下。运行环境为 `/public/home/zjt/anaconda3/envs/python3.10/bin/python`，依赖 Phonopy 2.19.1、NumPy、spglib 和 Matplotlib。

```bash
PY=/public/home/zjt/anaconda3/envs/python3.10/bin/python
"$PY" -B phon3/phon3.py validate eq
```

平衡点通过后，用 `prepare dfpt`、`preflight dfpt` 生成并核对下一步，在 `phon3/dfpt/` 通过 `../run.pbs` 提交。每步提交前查重并核对实际空闲小节点。每个新作业更新算例 PBS 表，按本机 `scripts/README.md` 登记回传。DFPT 完成后运行 `validate dfpt` 和 `spectrum`，检查 Γ、X、Y、M、Γ–X–M–Y–Γ–M 路径及 40×40×1 q 网格，保留原始与声学和则处理后的频率及低频振型。完整谱通过后更新服务器 Master 的重优化和声子教程。

下表为本次 SSH 核验的 SHA-256，路径相对于 `/public/home/zjt/task/now/hqt`。教程与作业表后续按验收结果更新。

| 文件 | SHA-256 |
| --- | --- |
| `Master/K2CrF4.md` | `c4bd21b34a0daf92e05f3c6df2d43122fe49ec2a0b2d3403c84e4edc79d0951c` |
| `Master/phonopy.md` | `2bdccd61f01b3334ed223620ec6191e72f8f38a2426b01bd16a062608ec1d473` |
| `Master/relax+scf.md` | `f39402427724e60c7c7384817f963e6234413ef40e83990d2b359844fc52ec7d` |
| `Master/case_index.md` | `99e539ac4bb839b1fb67a3e0c4c839706171710524aeb0648cbce46d2cc67c35` |
| `Master/vasp_environment.md` | `8ef5337d470da662a6203f14fd31a5440746d280df43503d513f7b0e38d741ed` |
| `Materials/examples/K2CrF4/workflow.md` | `847032e40260434c32914bffb9d8d9be5660e54d15c3cba82a9589b313a22f15` |
| `Materials/examples/K2CrF4/gamma/hessian.py` | `ce4ff3ffbd39a86dc542dd67fd1d889d80626b574a758e4fc4294899cc13a7cf` |
| `Materials/examples/K2CrF4/gamma/hessian.pbs` | `933630f2ea55b70cf4b7eb2084e2f3b29882283a199686ff34c1e5fd8a734497` |
| `Materials/examples/K2CrF4/phon3/phon3.py` | `75a727b0e28dca2bbacac6f04a42bf5910ca81139c1f32abd3c90192f49a1d94` |
| `Materials/examples/K2CrF4/phon3/run.pbs` | `e7b32812f30b755661fc5d882fe889e188f3ce8c9e496d7f7a4520e259754cf0` |
