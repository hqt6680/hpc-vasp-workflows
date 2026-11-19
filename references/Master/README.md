# 组内计算资料库

本包为组内计算资料库的离线副本，最近核查 2026-11-13。VASP 6.5.1、Wannier90 3.1.0、PBS 节点名、作业号和算例路径记录原站点的实测条件。接收者先核对自己的可执行程序、编译能力、资源和输入，再选用适合的流程。

| 要做的计算 | 先读 | 交给下一步的文件或参数 |
| --- | --- | --- |
| VASP、PBS、输入与输出检查 | [本站环境](vasp_environment.md) | 作业 ID、方法参数、输入和日志 |
| 结构优化、二维晶格约束、静态自洽 | [relax + SCF](relax+scf.md) | `CONTCAR`、均匀 k 网格的 `CHGCAR`、按需保留 `WAVECAR` |
| 能带、局域轨道投影、DOS/PDOS | [能带与 DOS](band_dos.md) | `EIGENVAL/PROCAR/DOSCAR`、路径、对齐能量与归一化 |
| 声子、软模动画、重构后重算 | [声子与重构](phonopy.md) | `FORCE_CONSTANTS`、`band.yaml`、模态或优化后的结构 |
| SOC、海森堡交换、MAE、DMI、Wannier/TB2J | [磁性计算](magnetism.md) · [TB2J](tb2j.md) | 有符号约定的能量差、最终磁态、键数及映射参数 |
| SOC 自旋转角与垂直偶极矩 | [自旋转角与偶极矩](spin_dipole.md) | 角度、磁矩方向、偶极矩和归一化 |
| Wannier 窗口与 cRPA 测 U/J | [测 U/J](U_cal.md) | `UIJKL`、`WANPROJ`、窗口与自旋通道、DFT+U 约定 |
| LLG、MC、纳米带与磁电场 | [自旋模拟入口](spin_simulation.md) | 配置、日志、构型、`summary.csv` 与收敛证据 |
| 查计算来源、重跑与未通过记录 | [K₂CrF₄ 全流程](K2CrF4.md) · [其他材料算例](case_index.md) | 原始目录、历史版本、可复用范围 |

## 开始一个算例

1. 读目标站点和项目的 `AGENTS.md` 与相关教程，再检查 `Materials/<材料>/` 的原始输入、输出和 PBS 脚本。先确认同一结构、赝势、泛函、磁态、U 定义和 k 网格是否适用于目标量。
2. 复算用独立目录。写明输入来源、改动、VASP 入口、PBS 资源与目标验收条件。每步先核对上游文件，再使用本步输出。
3. 记录正常退出、数值收敛和物理判据。部分历史证据的路径用于追溯来源。模板中的数字属于具体材料，复用于其他结构时按该材料重新选择。

## 教学视频

| 录屏 | 资料库对应内容 |
| --- | --- |
| [01 安装软件](https://www.bilibili.com/video/BV1yTHS6TE3y/) | Windows 端登录、文件管理和结构查看。集群实际编译环境见 [本站环境](vasp_environment.md)。 |
| [02 结构优化、自洽、能带](https://www.bilibili.com/video/BV1ZQpb6zEYV/) | K₂CrF₄ 输入、`OPTCELL=110`、SCF、线性 k 路径与作图。当前 6.5.1 优先用 INCAR 的晶格约束。 |
| [03 声子谱](https://www.bilibili.com/video/BV1cxJa65Ebi/) | 2×2×1 超胞、力常数、声子谱、M 点软模动画。 |
| [04 重优化、投影能带、态密度](https://www.bilibili.com/video/BV1JxHg6QE5K/) | M 点位移生成结构、重优化、取原胞、Cr–F 局域坐标。 |
| [05 海森堡交换作用](https://www.bilibili.com/video/BV1rVxk69EJm/) | K₂CrF₄ FM、C-AFM、条纹磁序和键数映射。 |
| [06 DM 相互作用](https://www.bilibili.com/video/BV1Ms476PENF/) | CoI₂ 手性构型及有向键的算术演示。MnInP₂Te₆ 有本站 CW/CCW 归档。 |

[原视频合集](https://space.bilibili.com/456626315/lists?sid=9275556) · [VASP 官方 Wiki](https://vasp.at/wiki/)

## 随包算例和模板

历史路径用于追溯原站点记录。需要复算时，在接收者的工作区准备匹配的输入和授权软件。VASP、POTCAR、原始波函数和电荷文件由接收者按站点规则准备。

- [MnInP₂Te₆ TB2J 实算](tb2j.md#6-mninp₂te₆-实算记录)附同 k 能带叠图、逐键 CSV、历史对照及教程用后处理脚本。文件位于 `../Materials/test/tb2j/`，脚本以实际算例输入运行。
- [Simulation](Simulation/README.md)附 C++/OpenMP 模板、示例配置、重绘和验证脚本。
- [cRPA、MAE 和转角核验摘要](evidence/README.md)摘自原站点历史记录。
- VASP/PBS 的 [std](../software/vasp-6.5.1/examples/std.pbs) 与 [ncl](../software/vasp-6.5.1/examples/ncl.pbs) 是可按实际环境修改的模板。
