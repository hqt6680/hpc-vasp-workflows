# 在 Windows 上用 agent 做 VASP 计算

你可以在自己的 Windows 项目里告诉 agent 想算什么。它会通过 SSH 去组里的服务器查教程、准备输入，再按你的要求把作业交给 PBS。结构、赝势和计算结果都留在服务器上。

## 第一次用

在 Windows 上新建一个空文件夹，用 Codex 打开它。复制本仓库的 Git 链接，把下面这句话发给 agent 即可。

> 请从〈粘贴仓库链接〉把 VASP 工作流部署到当前 Windows 文件夹。问我需要哪些信息，装好后帮我确认能读到服务器上的 AICC。

准备好平时登录集群用的 **SSH 别名**和**自己的服务器工作目录**。Windows 需要 Python 3.10 或更高版本和 OpenSSH 客户端，使用仓库链接还需要 Git 和仓库读取权限。当前安装器适配组内的 PBS 集群。如果你习惯用 VS Code 看服务器文件，在 Remote - SSH 里选同一个别名，再打开自己的服务器工作目录即可。

部署时还有两个选择，可以分开回答。

- **要用组内默认知识库吗？** 启用后，工作目录里的 `knowledge/default/` 通向最新教程，`knowledge/examples/` 通向原始算例。组里更新后，下次查阅就能读到。
- **现在有想让 agent 学习的目录吗？** 可以给它一个自己做过的算例，让它把参数怎么选、结果怎么看整理到 `knowledge/personal/`。暂时想不到就答“以后再说”，之后随时可以补。

## AICC 装在哪里？

Windows 项目安装的技能是 `.agents/skills/vasp-pbs/`。**AICC（AI Computational Chemist）在服务器上共用一份**。安装器在本机 `.vasp-local/knowledge.md` 记下连接信息和 AICC 位置，并在你的服务器工作目录写入或合并 `AGENTS.md`。个人工作目录里的这份规则指向共享安装。agent 通过 SSH 读取 AICC 的站点说明和本次任务用到的技能。即使跳过默认知识库，也能使用 AICC。

## 试一次计算

比如，你已经把结构放进自己的服务器目录，可以这样开口。

> 我的 POSCAR 在〈服务器算例目录〉。请参考组里已验收的能带算例，帮我准备一套无 SOC 的自洽和能带输入，解释一下 k 点怎么选，先做到预检。

1. **选参考。** agent 先读你的工作目录规则。启用默认库时，它会按目标物理量、结构和磁态选已验收的算例，读对应的 `workflow.md`。遇到自洽接能带这样的多阶段任务，还会先读 AICC 的 `comp-chem-workflow`，再为你的材料准备输入。
2. **检查输入。** agent 读取 AICC 的 `tools/vasp/SKILL.md`，在算例目录运行 `check_inputs.py`。例如，元素顺序要和 POTCAR 对上，共线磁矩与非共线磁矩的分量数也要分别核对。做到这里就可以先看输入和预检提示。
3. **提交计算。** 你要求提交后，agent 按 AICC 的 `tools/hpc-submit/SKILL.md` 核对资源，用 `qsub` 提交当前阶段的 PBS 脚本。组内的新算例使用 VASP 6.5.1。共线计算选 `std.pbs`，经 MPI 启动 `$HOME/bin/vasp6.5-wannier`。SOC 或非共线计算选 `ncl.pbs`，启动 `$HOME/bin/vasp6.5so-wannier`。
4. **验收结果。** 作业结束后，agent 用 AICC 的 `parse_vasp.py` 从已有输出提取能量、力等信息，结合本次目标检查收敛。例如，做能带前要先确认自洽阶段的电荷密度可用，再接下一步。

如果想在作业结束时收到原聊天的提醒，可以另外启用 Windows 监听器，需要 Node.js 18 或更高版本和已登录的 Codex Desktop。以后想清理这台电脑上的部署，直接在项目里说“恢复本机部署”。个人笔记和服务器上的作业、知识库都会保留。[部署、监听与恢复说明](share/vasp-pbs/references/setup.md)

也可以从[最新发行版](../../releases/latest)下载 `vasp-pbs-skill.zip`。维护技能包时，在仓库根运行 `python scripts/package_vasp_pbs.py <输出路径>`。
