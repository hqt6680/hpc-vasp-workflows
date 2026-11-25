# 读取组内知识库

共用 zjt 账号，默认知识库在 `/public/home/zjt/.examples`。首次进入先读取该目录的 `AGENTS.md`。目录中的 `Master/`、`Materials/examples/` 和站点模板是服务器上的独立副本。索引中的相对路径按文档所在目录解析。下面的 PowerShell 命令在安装后的技能目录执行，`$aliasName` 使用当前用户已确认的 SSH 别名。

```powershell
python scripts/read_group_library.py --ssh $aliasName
python scripts/read_group_library.py --ssh $aliasName Master/case_index.md
python scripts/read_group_library.py --ssh $aliasName Materials/examples/K2CrF4/workflow.md
```

- 首条命令读取教程首页和已发布的算例索引。索引只收录 K₂CrF₄、MnInP₂Te₆‑TB2J、MnInP₂Te₆‑cRPA 和 CoI₂‑DMI 四个标准算例。LLG、MC 和 TB2J 公共脚本的发布副本在 `Master/Simulation/`。
- 第二条命令列出已验收结果及其适用范围。第三条以 K₂CrF₄ 为例；读取其他算例时替换为索引给出的相对路径。
- **用 AICC**。进入本人配置的远程工作根，读取该工作根下的 `.auto-computational-chemist/AGENTS.md`、`.auto-computational-chemist/site-zjt.md` 和所选工具的 `SKILL.md`。通过本目录的脚本预检和验收。

选其他服务器或个人资料目录时，通过用户已配置的 SSH 别名读取其指定路径。连接失败或资料无权读取时，报告具体缺项，恢复连接后重新读取。
