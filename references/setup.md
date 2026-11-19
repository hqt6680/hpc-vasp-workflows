# 配置和安装

## 安装技能

解压得到 `vasp-pbs/` 文件夹。将整个文件夹放到 VASP 工作区的 `.agents/skills/`，或放进接收者 Codex 的用户技能目录。用户技能目录优先用 `CODEX_HOME/skills`，未设置 `CODEX_HOME` 时用用户目录下的 `.codex/skills`。重新打开项目后可用 `$vasp-pbs` 调用。

组内教程随技能安装，可从 [组内计算资料库](Master/README.md) 查找。教程中的集群路径、程序入口、版本、节点及材料参数来自原算例。请让当前项目的 Codex 先核对自己的远端环境、算例输入和调度资源，再据此调整命令和参数。仅查阅资料时，安装技能文件夹即可。需要回传作业终态时，再配置下方监听器。

## 知识库更新

安装包内的 `references/` 是发布时的资料副本。组内知识库更新后，可用新版包的 `references/` 覆盖同名资料。项目自己的集群配置和监听状态继续在项目中维护。

## 配置项目监听器

1. 在 Windows 的 VASP 工作区打开 Codex Desktop，确认有 Python 3.10 或更高版本、Node.js 和 OpenSSH 客户端。把技能目录内 `assets/project/scripts/` 的文件复制到该工作区的 `scripts/`。将 `assets/project/AGENTS.md` 的回传规则合并到项目根的 `AGENTS.md`，已有同名文件时保留本地站点规则。
2. 将 `scripts/pbs_watch.config.example.json` 复制为 `scripts/pbs_watch.config.json`，按接收者实际站点填写下列字段。真实连接信息由接收者在本机维护。共享时只保留示例，避免复制 SSH 私钥、口令、代理凭据、聊天 UUID 和监听状态数据库。

| 字段 | 填写内容 |
| --- | --- |
| `ssh_host` | 接收者自己已配置的 OpenSSH 别名。 |
| `ssh_user` | 服务器登录账号，应与远端 `id -un` 及 PBS 作业所有者一致。 |
| `ssh_hostname` | 远端 `hostname -s` 的返回值。 |
| `remote_root` | 工作根的实际绝对路径，以 `pwd -P` 核验。 |
| `case_prefix` | 相对于工作根的算例目录前缀，例如 `Materials`。 |
| `job_id_suffix` | 调度器实际返回的作业 ID 后缀，格式以配置示例为准。 |
| `qstat_path` | 可选，远端 qstat 的绝对路径，默认 `/opt/pbs/bin/qstat`。 |
| `desktop_proxy` | 默认填 JSON 的 `null`，适用于直连的 Codex Desktop。需要绑定代理启动的实例时填写其 Electron `--proxy-server` 参数的实际值。 |

3. 通过自己的别名验证免密连接，并确认该站点支持 `qstat -xf -F json` 历史查询和作业记录中的 `PBS_O_WORKDIR`。监听器按 PBS 所有者、作业名与算例路径核对记录。
4. 保持 Codex Desktop 登录并能访问模型服务。监听器连接已有 Desktop 实例的本机 IPC。需要测试托盘场景时，分别检查回执、目标聊天实际收到的内容与是否启动新轮次。

## 安装、登记与处理

在目标 VASP 工作区的 PowerShell 执行一次安装。需要登录后自动恢复已有待监测作业时，可在安装命令上加 `-ResumeAtLogon`。

```powershell
.\scripts\install_pbs_watch.ps1 -Action Install
```

提交并核对 PBS 作业后，在工作区运行以下命令。将示例 ID、作业名、相对算例路径换成实值。Codex 终端已提供当前项目聊天 UUID 时可省略 `--thread`。从其他终端运行时传入本项目的聊天 UUID。

```powershell
python scripts/pbs_watch.py add 1234.cluster scf Materials/example --thread '00000000-0000-0000-0000-000000000000'
.\scripts\install_pbs_watch.ps1 -Action Start
python scripts/pbs_watch.py status
.\scripts\install_pbs_watch.ps1 -Action Status
```

监听器批量查询登记作业，常规间隔约两分钟。只有终态会向原项目聊天回传。没有待查询作业或待投递事件时自动退出。每个配置项目使用独立计划任务和状态数据库。使用 `-Action Stop` 可停止本机监听，服务器 PBS 作业继续运行。

- `pending` 表示等待投递，Desktop 暂不可用时保留该状态并按间隔重试。
- `steered`、`started` 表示 Desktop 已确认投递，仍需核验 PBS 和科学输出。处理完成后运行 `python scripts/pbs_watch.py ack <event_id>`。
- `sending` 表示投递结果未确认。先核对原聊天内容、PBS 记录和算例作业记录。确认未收到且需要重发时，用 `python scripts/pbs_watch.py retry <event_id>`，再用 `-Action Start`。

首次交付分别验证 PBS 查询、向实际项目聊天投递及计算验收。Desktop 更新后复测 IPC。遇到不兼容时，可通过 `status` 查本地记录，再经 SSH 手动核验当前阶段。
