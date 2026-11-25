# 配置和安装

## 安装技能

从 Git 链接部署时，在项目外的临时目录克隆并运行 `python scripts/package_vasp_pbs.py <临时目录>/vasp-pbs-skill.zip`。使用发行包时直接解压到临时目录。从解压包按下列顺序部署。程序负责复制技能和合并规则，并在写入前登记本机文件的归属。agent 完成部署后清理本次创建的临时克隆、压缩包和解压目录。新对话可用 `$vasp-pbs` 调用。

**每次只发一张卡，只问一件事。** 先读当前项目已有的 `.vasp-local/knowledge.md` 和用户已给出的信息，跳过已知项。对每个缺项单独调用客户端的问答卡工具（如 `request_user_input_async`），每次 `questions` 只放一个问题。地址、名称和路径用自由输入，开关给出可选答案。收到该卡的实际回答后再决定下一张，预选项和等待超时都不算回答。客户端没有卡片工具时，每轮只发当前这一问并等待回复。以下顺序供 agent 执行。

## 建立可复用的 SSH 连接

1. **找已有入口。** 优先用项目记录或用户指定的名称。否则从当前 Windows 用户的 OpenSSH 配置（含 `Include`）找与目标集群匹配的具体 `Host`，写成 IP 的名称也有效。用 `ssh -G <别名>` 核对生效的主机、用户、端口和密钥路径。多个候选无法区分时，单卡问“你平时用哪个入口登录这台集群？”，提供候选和“新建别名”。对已确定的目标执行下方免交互验证，成功就进入工作区设置。`ssh -G` 对未配置的名称也会给出默认值，是否可用以实际登录为准。
2. **缺少入口时逐卡建别名。** 依次单独问“这个连接想用什么别名？”、“服务器的地址是什么？”、“用哪个账号登录？”、“SSH 端口是多少？（通常是 22）”。已知项跳过。别名以字母或数字开头，可含字母、数字、点、短横线和下划线。若所选名称已指向其他服务器，回到别名卡选一个空闲名称。当前工作区初始化脚本适配组内 `zjt` 账号，先核对目标账号再初始化。
3. **保存连接。** agent 在 `%USERPROFILE%\.ssh\config` 合并目标 `Host` 段，保留已有配置和 `Include`。下面是最终配置的例子，按实际回答及选用的密钥替换。先用 `ssh -G` 复核，注意 `Host *` 等通配段的先后顺序。若已有可用公钥，直接尝试免交互验证。

```sshconfig
Host vasp-cluster
    HostName login.example.org
    User zjt
    Port 22
    IdentityFile ~/.ssh/id_ed25519_vasp_cluster
    IdentitiesOnly yes
```

4. **配好免密登录。** 初次连接由用户在本机交互终端将主机指纹与集群提供的指纹核对后接受。指纹有变化时先向管理员核实。连接超时或地址无法解析时，先检查网络、VPN、地址和端口，再重试原入口。若只是需要服务器密码或私钥口令，继续使用同一别名，按以下顺序处理。

   - 优先使用本人为该站点选定的密钥。需要新建时，选取未占用的本机文件名，运行 `ssh-keygen -t ed25519 -f $keyPath`，由用户在本机终端设置密钥口令。将目标别名的 `IdentityFile` 指向该路径。
   - 用 Windows 的 `ssh-agent` 保存解锁状态。服务尚未启用自动启动时，在管理员 PowerShell 执行 `Set-Service ssh-agent -StartupType Automatic`，按需执行 `Start-Service ssh-agent`。随后以部署用户身份在普通终端执行 `ssh-add $keyPath`，用 `ssh-add -l` 核对指纹，并重试免交互登录。[Windows OpenSSH 密钥管理](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)
   - 如果服务器尚未授权该公钥，在用户可交互的本机终端通过该别名登录，由用户在 SSH 提示处输入首次登录密码。核对远端账号后，仅把对应 `.pub` 公钥登记到该账号的 `~/.ssh/authorized_keys`。按公钥内容去重，保留其他条目和已有的密钥限制。新建的 `~/.ssh` 和 `authorized_keys` 权限分别为 `700` 和 `600`。密码与密钥口令只在本机程序的隐藏提示处输入，私钥留在 Windows 用户目录。

5. **验证保存的配置。** 在新的普通 PowerShell 中，将 `$aliasName` 设为刚保存的名称。使用与初始化和监听器相同的 SSH 客户端，只给别名，不额外指定账号、端口或密钥。以下命令适用于组内服务器。

```powershell
ssh -T -o BatchMode=yes -o PreferredAuthentications=publickey -o StrictHostKeyChecking=yes -o ConnectTimeout=10 $aliasName 'cd /public/home/zjt/task/now/hqt && id -un && hostname -s && pwd -P && cat AGENTS.md'
```

退出码为零，账号、主机和实际路径符合目标，并已读到远端规则时，才进入下一步。失败时根据 SSH 的报错处理当前项，再从新终端复测。如果站点要求每次交互认证，请用户与管理员核实该账号支持的非交互登录方式。

## 知识库设置

SSH 验证通过后，按顺序只发尚未回答的卡。

1. “你自己的服务器计算工作目录是哪个？” 接收个人工作根的绝对路径。共用登录账号的组员各用自己的目录。
2. “是否使用默认组内知识库？” 选“使用”时，验证能读到当前教程索引和算例目录。选“跳过”可在以后启用。AICC 独立配置，在 zjt 上读取共享根 `/public/home/zjt/task/now/hqt/.auto-computational-chemist/` 的 `AGENTS.md` 和 `site-zjt.md`。[服务器知识库入口](group-library.md)
3. “现在要学习你的个人算例吗？” 选“现在学习”后才另发一张“要学习哪个服务器目录？”路径卡，可填一个或多个路径。选“以后再说”直接跳过路径卡。收到路径后先核对真实位置，仅阅读指定范围内的说明、代表性输入、作业脚本及必要输出摘要。遇到指向范围外的引用，先记录出处。

确认选择后，在技能目录运行下面的命令。`$aliasName`、`$windowsProject` 和 `$remoteWorkdir` 分别取自本人的 SSH 别名、Windows 项目根和个人远程工作根。跳过默认库时将 `--group` 换成 `--no-group`。共用账号的每个人使用各自的工作根。

```powershell
python scripts/setup_workspace.py --ssh $aliasName --project $windowsProject --workdir $remoteWorkdir --group
```

程序在 Windows 项目根创建或合并 `AGENTS.md`，把站点选择写入 Git 忽略的 `.vasp-local/knowledge.md`。在远程工作根创建或合并 `AGENTS.md` 并初始化 `knowledge/personal/README.md`。启用默认库时创建 `knowledge/default` 和 `knowledge/examples` 两个目录链接，分别指向服务器的 `Master/` 和 `Materials/examples/`。旧版部署创建的 `knowledge/group` 链接在重新部署时自动迁移。关闭默认库时移除对应链接，个人总结保留。

若指定了学习目录，agent 接着在服务器读这些目录，把提炼出的方法写入 `knowledge/personal/` 并更新个人索引，记录来源路径、适用材料、参数依据和验收状态。以后收到“学习目录 …”时按相同流程追加。核对初始化结果时分别检查远端 `AGENTS.md`、个人索引和已启用的链接。

最后，若用户尚未选择回传方式，单独发“现在启用 PBS 作业回传吗？”卡。选“现在启用”后按下文配置和测试。选“以后再说”即可结束本次部署。

## 知识库更新

组内方法在服务器 `hqt/Master/` 维护。每次查阅通过 SSH 获取当前索引、教程和算例；新增算例由实时目录列表发现。算例输入、输出和复算脚本留在服务器。知识库内容的更新即时可读，技能升级保留本机登记的选择。

## 配置项目监听器

1. 在 Windows 的 VASP 工作区打开 Codex Desktop，确认有 Python 3.10 或更高版本、Node.js 和 OpenSSH 客户端。在技能目录执行 `python -B scripts/local_workspace.py install --project "$windowsProject" --watcher`，由安装器写入及登记项目监听脚本和回传规则。
2. agent 编辑程序准备的 `scripts/pbs_watch.config.json`，复用前面已验证的别名、账号、主机和个人工作根，并从实际 PBS 记录核对可查的字段。其余需要用户决定的字段仍逐张发卡，每张只问一项。真实连接信息在接收者本机维护。

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

## 恢复本机

用户要求恢复或卸载当前 Windows 部署时，在 **Windows 项目根** 执行下列命令。恢复程序也可从新解压的发行包运行，将 `--project` 指向原 Windows 项目。

```powershell
python -B .agents/skills/vasp-pbs/scripts/local_workspace.py restore --project .
```

恢复在本机完成。程序停止并注销本次部署创建的项目计划任务，删除该项目新增的监听数据库、日志、缓存、配置、技能和脚本，移除托管的 Markdown 段及空目录。部署前已有的文件与目录、托管段以外的笔记和其他项目的任务会保留。已修改的工具文件会逐项报告。远端作业继续运行，删除本机监听记录后该项目停止回传。

旧版本请从新版发行包调用恢复命令。对于缺少安装清单的工作区，程序按已发布文件指纹和托管标记识别旧安装。手工改写且无法识别的文件保留在原处。
