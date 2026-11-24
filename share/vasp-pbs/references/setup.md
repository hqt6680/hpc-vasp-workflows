# 配置和安装

## 安装技能

从 Git 链接部署时，在克隆目录执行 `python scripts/package_vasp_pbs.py <临时目录>/vasp-pbs-skill.zip`。解压后把 `vasp-pbs/` 放到组员 Windows 项目的 `.agents/skills/`。使用发行包时从解压步骤开始。将包中 `assets/project/AGENTS.md` 的知识库约定合并到组员项目已有规则，首次部署就继续完成下面两项选择。新对话可用 `$vasp-pbs` 调用。

安装后先做下面两项选择。查阅共享内容使用[服务器知识库入口](group-library.md)，待需要作业回传时再配置监听器。

## 知识库设置

首次部署先核对用户自己的 SSH 别名和远程计算工作目录。共用 zjt 登录账号的组员可以选择不同的工作目录。向用户分别询问下面两项，已有明确选择时直接采用。

1. 是否使用默认组内知识库？选择使用时，通过[服务器知识库入口](group-library.md)验证能读到当前教程索引和算例目录。选择跳过时，后续仍可启用。AICC 是独立的计算工具。在 zjt 上读取共享根 `/public/home/zjt/task/now/hqt/.auto-computational-chemist/` 的 `AGENTS.md` 和 `site-zjt.md`，按任务调用相应工具。使用其他站点时核对实际安装位置。
2. 是否现在指定个人学习目录？可给出一个或多个远程路径，也可回答“以后再说”。收到路径后先核对真实位置，仅阅读指定范围内的说明、代表性输入、作业脚本及必要输出摘要。遇到指向范围外的引用，先记录出处。

确认选择后，在技能目录运行下面的命令。`$aliasName`、`$windowsProject` 和 `$remoteWorkdir` 分别取自本人的 SSH 别名、Windows 项目根和个人远程工作根。跳过默认库时将 `--group` 换成 `--no-group`。共用账号的每个人使用各自的工作根。

```powershell
python scripts/setup_workspace.py --ssh $aliasName --project $windowsProject --workdir $remoteWorkdir --group
```

程序在 Windows 项目根创建或合并 `AGENTS.md`，把站点选择写入 Git 忽略的 `.vasp-local/knowledge.md`。在远程工作根创建或合并 `AGENTS.md` 并初始化 `knowledge/personal/README.md`。启用默认库时创建 `knowledge/group` 和 `knowledge/examples` 两个目录链接，分别指向服务器的 `Master/` 和 `Materials/examples/`。关闭默认库时移除对应链接，个人总结保留。

若指定了学习目录，agent 接着在服务器读这些目录，把提炼出的方法写入 `knowledge/personal/` 并更新个人索引，记录来源路径、适用材料、参数依据和验收状态。以后收到“学习目录 …”时按相同流程追加。核对初始化结果时分别检查远端 `AGENTS.md`、个人索引和已启用的链接。

## 知识库更新

组内方法在服务器 `hqt/Master/` 维护。每次查阅通过 SSH 获取当前索引、教程和算例；新增算例由实时目录列表发现。算例输入、输出和复算脚本留在服务器。知识库内容的更新即时可读，技能升级保留本机登记的选择。

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
