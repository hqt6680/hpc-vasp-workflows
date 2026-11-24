# 读取组内知识库

共用 zjt 账号，组内资料根为 `/public/home/zjt/task/now/hqt`。首次进入先读取该目录的 `AGENTS.md`。每次查阅都通过 SSH 重新读取所需内容。下面的 PowerShell 命令在安装后的技能目录执行，`$aliasName` 使用当前用户已确认的 SSH 别名。

```powershell
python scripts/read_group_library.py --ssh $aliasName
python scripts/read_group_library.py --ssh $aliasName Master/case_index.md
python scripts/read_group_library.py --ssh $aliasName Materials/examples/K2CrF4/workflow.md
```

- 首条命令读取方法索引，并列出可用算例。LLG、MC 和 TB2J 公共脚本在服务器 `Master/Simulation/`。
- 第二条命令列出已验收结果及其适用范围。第三条以 K₂CrF₄ 为例；读取其他算例时替换为索引给出的相对路径。
- **用 AICC**。按需读取 `.auto-computational-chemist/AGENTS.md`、`.auto-computational-chemist/site-zjt.md` 和所选工具的 `SKILL.md`。计算在用户自己的工作目录运行。

选其他服务器或个人资料目录时，通过用户已配置的 SSH 别名读取其指定路径。连接失败或资料无权读取时，报告具体缺项，恢复连接后重新读取。
