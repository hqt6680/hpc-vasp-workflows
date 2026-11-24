# 读取组内知识库

共用 zjt 账号，组内资料根为 `/public/home/zjt/task/now/hqt`。首次进入先读取该目录的 `AGENTS.md`。每次查阅都通过 SSH 重新读取所需内容。下面的 PowerShell 命令在安装后的技能目录执行，`$aliasName` 使用当前用户已确认的 SSH 别名。

```powershell
python scripts/read_group_library.py --ssh $aliasName
python scripts/read_group_library.py --ssh $aliasName Master/vasp_environment.md
```

- **找方法**。首条命令实时读取 `Master/README.md`。根据它的链接选择本次教程，按第二条命令的格式读取。LLG、MC 和 TB2J 的公共脚本在服务器 `Master/Simulation/`。
- **找算例**。首条命令同时枚举服务器 `Materials/examples/` 的当前目录和各例的 `workflow.md`。将返回的实际相对路径传给读取命令，再按需通过 SSH 查原始输入、输出或作业日志。
- **用 AICC**。按需读取 `.auto-computational-chemist/AGENTS.md`、`.auto-computational-chemist/site-zjt.md` 和所选工具的 `SKILL.md`。计算在用户自己的工作目录运行。

选其他服务器或个人资料目录时，通过用户已配置的 SSH 别名读取其指定路径。连接失败或资料无权读取时，报告具体缺项，恢复连接后重新读取。
