# VASP / PBS 工作流与技能包

| 入口 | 用途 |
| --- | --- |
| [scripts/](scripts/) | PBS 监听、Codex Desktop 回传与本机工作流辅助 |
| [share/vasp-pbs/SKILL.md](share/vasp-pbs/SKILL.md) | VASP / PBS 技能、资料与标准算例入口 |
| [最新技能安装包](https://github.com/hqt6680/hpc-vasp-workflows/releases/latest) | 下载 `vasp-pbs-skill.zip` 后按包内说明加载 |

LLG、MC 和 TB2J 脚本使用 zjt 服务器的 `Master/Simulation` 主目录。入口和同步规则见 [AGENTS.md](AGENTS.md) 与[自旋模拟入口](share/vasp-pbs/references/Master/Simulation/README.md)。

重新打包运行 `python scripts/package_vasp_pbs.py <输出路径>`。技能包包含离线副本需要的 PBS 脚本。VASP、赝势和计算输入在各自集群环境准备。

本机 PBS 监听的安装、验证和回退见 [HANDOFF.md](HANDOFF.md)。
