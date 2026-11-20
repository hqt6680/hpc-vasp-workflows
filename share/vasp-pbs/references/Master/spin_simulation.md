# LLG、MC 与纳米带

可运行模板在 [Simulation/README.md](Simulation/README.md)，参数详见 `Master/Simulation/docs/PARAMETERS.md`。C++11/OpenMP 是独立的经典自旋模型。若参数来自 DFT，先统一 [J、D、各向异性约定](magnetism.md) 与程序的自旋归一化、单位和近邻计数。

## 开始一套计算

1. 将 `Master/Simulation` 复制到新的算例目录，按目标设置独立 INI 和输出目录。先确定三壳层 J、DMI 类型/符号、`K`、磁矩、温度/磁场、电场耦合，以及开放或周期边界。程序的单离子项为 `−K Σ S_z²`。检查目标方向与 DFT 笛卡尔轴映射。已有结果复用按目录条件匹配，改变哈密顿量、种子或积分设置用新的输出目录，避免缓存混用。
2. `bash build.sh` 后用 `bash run.sh --dry-run` 核对生效参数；再用 README 的低步数 LLG/MC 示例检查输出。正式计算通过 `wz.pbs` 单节点 OpenMP 提交，按实际可用节点与线程数编辑脚本。
3. LLG 检查步长、总时间、扭矩和路径依赖。MC 检查平衡轮数、测量轮数、种子、接受率与采样误差，现有摘要里的最终构型量是瞬时值。MC 要求 `T>0`，电场耦合走 LLG。保留 `run_settings.ini`、`summary.csv`、末态和作业日志，重绘用 `Master/Simulation/docs/REPLOT.md`。

## MnInP₂Te₆ 历史结果

- 归档在 `Materials/MnInP2Te6/simulation/`，真实结果由其历史二进制和配置产生。`result/MnInP2Te6/llg/` 有全周期 `128×128` 的温度、磁场和磁电场，以及 `32/64/128×128` 的 x 开放、y 周期条带温度与电场分支。
- 电场条带 `32e.ini`、`64e.ini`、`128e.ini` 使用 `J1=1.71 meV`、`J2=J3=0`、`K=−0.5125 meV`、Bloch `D=0.63 meV`、`T=0`、`Bz=0`。每组用对应温度末态起算，`Ez` 输入 `0,0.2,…,2`，各点接前点构型，每点 50 ps/500000 步。旧参数 `Ez` 无已核准的物理换算，坐标用 `x/a,y/a`。
- 三个尺寸各 11 个电场点完成固定步数。开放边界下积分拓扑荷 `Q` 可连续变化，不能直接四舍五入成纹理个数。最大残余扭矩约 `0.0066–0.1375 meV`，引用时写为各点 50 ps 末态。证据在 `.codex_reports/MnInP2Te6/ribbon_electric_20261110/model_audit.md`。
- 当前 `Master/Simulation` 已独立编译并通过部署、输出布局和日志回归。运行入口实测含小规模 LLG/MC；归档未发现 `Materials/MnInP2Te6/simulation/result` 下的生产 MC 结果。详情见 `Master/Simulation/docs/VALIDATION.md`。
