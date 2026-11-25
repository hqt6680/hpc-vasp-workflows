# VASP / PBS 工作流交接

本机监听入口为 [scripts/pbs_watch.py](scripts/pbs_watch.py)，通过 SSH 读取已登记的 PBS 作业，并把事件回传到原 Codex 聊天。Codex Desktop 若已对该聊天退订，监听器在确认周额度和代理实例后，可通过官方深链接打开原聊天并重试该事件。

## zjt 的 MAGMOM 预检

2026-11-24 已修复服务器 AICC 的 `tools/vasp/scripts/check_inputs.py`。显式 `MAGMOM` 展开重复记法后，共线计算检查 N 个数，开启 `LNONCOLLINEAR` 或 `LSORBIT` 时检查 3N 个数，N 取自 POSCAR。MnInP₂Te₆ 的共线 SCF 和 TB2J 三个 SOC 方向均已通过离线预检，另有 11 个输入变体覆盖错误长度、开关和 INCAR 写法。

本站[预检补丁](.agents/skills/zjt-aicc/patches/magmom-preflight.patch)对应 AICC 上游 `e27b555ecfee3a7b66472c19c93b01ad0a1ccae1`。重装该版本时，在服务器 AICC 根目录用 `patch --dry-run -p1` 从标准输入检查补丁，再用 `patch -p1` 应用。原文件、复测脚本和日志在服务器 `hqt/.codex_reports/vasp_audits/magmom_preflight_20261124_JBgj3R/`，需要回退时按 `before/` 内的相对路径恢复。

## 启动和验证

Windows 端需要 Python 3.10+ 和 OpenSSH 客户端。缺少可用的 SSH 别名时，按[安装说明](share/vasp-pbs/references/setup.md)逐卡配置并验证免密复连。启用监听还需要 Node.js 18+ 和正在运行的 Codex Desktop。站点参数见 [PBS 监听说明](scripts/README.md) 和 [配置示例](share/vasp-pbs/assets/project/scripts/pbs_watch.config.example.json)。SSH 私钥、实际站点配置和监听数据库保存在各自设备。

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

## 组内工作区与服务器资料

组员默认库位于 `/public/home/zjt/.examples`，以其中的 `Master/README.md`、`Master/case_index.md` 和 `Materials/examples/` 为查询入口。四个标准算例各自的 `workflow.md` 记录已验收的输入、关键参数和结果。公共科学脚本的维护源仍在 `hqt/Master/Simulation`，维护后将验收的变更同步到发布库。组员初始化从发布库复制 AICC 到所选工作根，重跑时保留个人修改并迁移原有知识库链接。[SSH 读取入口](share/vasp-pbs/references/group-library.md)

专属 AICC 与新知识库入口使用技能包版本 `vasp-pbs-live-2026.11.25`，部署记录见服务器 `hqt/.codex_reports/vasp_audits/member_library_20261125/deployment.md`。此前 `vasp-pbs-live-2026.11.24.2` 已验证本机监听器、数据库与日志的恢复，以及旧版恢复兼容性。[本机恢复入口](share/vasp-pbs/scripts/local_workspace.py)

共用 zjt 账号时，先加载 `source "$HOME/bin/vasp6.5-env.sh"`。共线计算用 `$HOME/bin/vasp6.5-wannier`，非共线和 SOC 用 `$HOME/bin/vasp6.5so-wannier`。两个 6.5.1 文件与 hqt 构建逐字节一致，已通过依赖解析及单进程 Intel MPI 版本检查。站点环境说明和 std/ncl PBS 模板已同步；检查记录及原模板位于 `hqt/.codex_reports/vasp_audits/shared_bin_651_20261124_MqQpGD/`。
