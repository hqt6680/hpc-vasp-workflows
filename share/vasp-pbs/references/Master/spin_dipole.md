# SOC 自旋转角与垂直偶极矩

适用于固定几何下的自旋方向扫描。组内示例在 `Materials/MnInP2Te6/sp/double/`，20 原子、2 个反平行 Mn。目录名 `ac`、`bc` 对应 Cartesian xz、yz，晶格 `b` 与 Cartesian y 并不平行。下面的全角流程从 x 或 y 出发，过 z 后扫到 −x 或 −y。历史 `bc` 输出在 90° 后折返，见页末复核。

1. 在独立目录取同一 POSCAR、POTCAR 和均匀 k 网格，沿用组内输入的 PBE、`IVDW=11`、`LDAUTYPE=1`、Mn `U=1.9262 eV`、`J=0.4384 eV`。新算用 [6.5.1 ncl](vasp_environment.md) 和 [SOC 设置](magnetism.md#2-soc-自洽)，保持 `NSW=0`。首角从头自洽，后续可读相邻角度的兼容 WAVECAR/CHGCAR，以 `ISTART=1, ICHARG=1` 重新自洽。另选角独立启动或反向扫描，检查路径依赖。
2. 两个 Mn 用 spinor z 方向的 `+4`、`−4 μB` 初始化。按扫描面填 `SAXIS=(cos θ,0,sin θ)` 或 `(0,cos θ,sin θ)`。历史例的其余核心设置如下。`DIPOL` 的分数坐标应与实际薄膜中心核对。

```ini
LSORBIT = .TRUE.
MAGMOM = 36*0 0 0 4 0 0 -4 18*0
LMAXMIX = 4
LDIPOL = .TRUE.
IDIPOL = 3
DIPOL = 0.5 0.5 0.5
```

3. 每角保存独立 `OUTCAR/OSZICAR` 和初始设置。核对电子收敛、最终两个 Mn 的物理磁化方向及反平行状态。`SAXIS` 定义自旋基底，最终方向要从磁矩验证。记录 OUTCAR 最后一个 `dipolmoment` 的 Cartesian z 分量，单位 `e·Å/计算胞`。比较不同面积时用 `p_z/A`；需要体极化或 Berry 相位极化时另行定义所用方法和几何。[VASP SAXIS](https://vasp.at/wiki/SAXIS) · [LDIPOL](https://vasp.at/wiki/LDIPOL) · [LCALCPOL](https://vasp.at/wiki/LCALCPOL)

```bash
awk '/dipolmoment/{pz=$4; seen=1} END {if (!seen) exit 1; print pz}' OUTCAR
```

`ac`（41853）和 `bc`（42571）的 `OUTCAR-{0,10,…,180}-P.1` 各 19 个文件均有 `EDIFF` 和正常结束标记。逐点偶极矩与各自 `Dipole_trend.dat` 完全一致。用 OUTCAR 的 spinor→Cartesian 矩阵复核，Mn 保持反平行，首个 Mn 偏离实际 `SAXIS` 小于 `0.6°`。`ac` 的标签与实际方向一致，`bc` 文件名的 `100,110,…,180°` 实际为 `80,70,…,0°`。比较角度依赖须用输出矩阵重建横轴，或重跑全角流程。`bcnew` 只有输入。

`ac` 数值范围 `+0.000008～+0.000299 e·Å`，`bc` 为 `−0.000265～+0.000026 e·Å`。该量很小，物理量化仍需测试真空、k 网格、FFT/ENCUT、对称性及扫描路径。复核见 [spin-dipole-audit.txt](evidence/spin-dipole-audit.txt)。
