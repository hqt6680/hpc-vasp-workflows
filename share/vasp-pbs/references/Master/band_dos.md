# 能带、投影能带与态密度

原站点参考环境为自编译 VASP 6.5.1。以下两步法适用于 PBE、PBEsol 等常规半局域泛函及匹配的 DFT+U。共线计算用 `bin/vasp6.5-wannier`，SOC 用 `bin/vasp6.5so-wannier`。准备自洽输入见 [结构弛豫与静态自洽](relax+scf.md)，SOC 自洽见 [磁性计算](magnetism.md)。

## 1. 均匀网格自洽

取已验收弛豫的 `CONTCAR` 为 `POSCAR`，沿用对应 `POTCAR`、泛函、U 和磁态。采用均匀 k 网格，静态自洽输出 `CHGCAR`；如需续算或 Wannier 接口，保留 `WAVECAR`。

```ini
ISTART = 0
ICHARG = 2
NSW = 0
IBRION = -1
LCHARG = .TRUE.
LWAVE = .TRUE.
LORBIT = 11
LMAXMIX = 4
```

这里 `LMAXMIX=4` 对应 d 电子 DFT+U；f 电子用 6。生成固定电荷计算所需的 `CHGCAR` 时就设好这个值。K₂CrF₄ 历史例的元素顺序 `K Cr F`、原子数 `2 1 4`、`GGA=PS`、`ENCUT=600` eV、Gamma `9×9×1`、Cr 的 `LDAUTYPE=2`、`Ueff=2.1−0.6=1.5` eV。具体数值按材料重新选取。

## 2. 路径能带与投影

在新目录复制同一次 SCF 的 `POSCAR/POTCAR/CHGCAR`，另写路径 `KPOINTS`。继承该次 SCF 的物理设置和相同的共线或 SOC 程序，修改静态控制量如下。改 k 点列表时从头初始化波函数，沿用已收敛的固定电荷。

```ini
ISTART = 0
ICHARG = 11
NSW = 0
IBRION = -1
LORBIT = 11
LCHARG = .FALSE.
LWAVE = .FALSE.
```

K₂CrF₄ 的历史正方原胞路径是 Γ–X–M–Γ。坐标基于本次 `POSCAR` 的倒格矢。超胞、旋转晶胞或其他晶系须按实际倒格子重建路径和标签。

```text
K2CrF4 square primitive cell
20
Line-mode
Reciprocal
0.0 0.0 0.0  ! GAMMA
0.5 0.0 0.0  ! X

0.5 0.0 0.0  ! X
0.5 0.5 0.0  ! M

0.5 0.5 0.0  ! M
0.0 0.0 0.0  ! GAMMA
```

画图取路径的本征值与 k 距离，零点取**同方法、同结构的均匀网格**费米能级 `E_F`。可在 6.5.1 的路径 INCAR 设置数值 `EFERMI`，或在后处理时明确传入参考值，二者避免重复平移。半局域计算也可把均匀网格放在 `KPOINTS`、路径放在 `KPOINTS_OPT` 同作业计算，两步法目录里保持无残留的 `KPOINTS_OPT`。 [VASP 路径能带](https://vasp.at/wiki/Band-structure_calculation_using_DFT)

本站 VASPKIT 1.5.0 的 `211` 读 `EIGENVAL/KPOINTS` 得到 `BAND.dat/KLABELS`，`213` 读 `PROCAR` 得到元素分辨 `PBAND_*`。在后处理目录运行 `vaspkit -task 211 -fermi 0.14557409`，数值换为本算例均匀网格的 `E_F`。`213` 同样可传 `-fermi`。本机开启了自动绘图时按提示选择图类与轨道。检查输出是本征值 `E` 还是已平移的 `E − E_F`。元素或轨道投影表示 PAW 投影权重，注明选取的原子、轨道和自旋。SOC 输出是自旋量子化基底下的自旋分量，按量子化轴和电荷权重解释。 [VASPKIT 教程](https://vaspkit.com/tutorials.html) · [VASP LORBIT](https://vasp.at/wiki/LORBIT) · [VASP PROCAR](https://vasp.at/wiki/PROCAR)

按 Cr–F 键解释局域 d 轨道时，先由 POSCAR 的周期近邻确定局域坐标与右手性。刚性旋转可用 `A_new=A_old R`（晶格矢量按行），`Direct` 坐标不变，Cartesian 坐标同乘 `R`。检查 `RᵀR=I`、`det R=+1` 及 Cr–F 距离和角度，再在匹配的几何上重做投影。另一种方法是对含相位的投影振幅或轨道密度矩阵换基。`PROCAR` 的五项 d 权重缺少交叉项，无法一般地恢复旋转后的各轨道权重。SOC 计算还应同步变换物理磁化方向。复刻论文 Fig. 3 时用面外 z、最长 Cr–F 键为 x。 [组内 02，42:44](https://www.bilibili.com/video/BV1ZQpb6zEYV/?t=2564) · [组内 04 局域轴，21:34](https://www.bilibili.com/video/BV1JxHg6QE5K/?t=1294) · [原论文 Fig. 3](https://arxiv.org/html/2304.09359#S3.SS3)

## 3. DOS / PDOS

从最终结构做静态均匀网格计算。可在同一网格 SCF 输出 `DOSCAR`，也可新建更密的均匀网格目录，使用同方法收敛的 `CHGCAR` 做 `ICHARG=11`，验证固定电荷近似对关注能窗的影响。`LORBIT=11` 输出逐原子与 `lm` 投影，按需要增大 `NEDOS` 和设定 `EMIN/EMAX`。加密 k 网格并检查展宽，`NEDOS` 只控制能量采样。`ISMEAR=-5` 需要能构造四面体的均匀网格并检查适用性。低维网格和费米面尚未确认时，先用 `ISMEAR=0` 并验证 `SIGMA`。 [VASP DOSCAR](https://vasp.at/wiki/DOSCAR) · [VASP 展宽方法](https://vasp.at/wiki/Smearing_technique)

VASPKIT 常用 `111` 提取总 DOS、`113` 提取元素 PDOS、`115` 选择原子和轨道。核对横轴零点、DOS 单位（`states/eV/cell` 或另行归一化）以及是否为显示而反号绘制 ↓。DOS 用静态均匀网格，线模式 `DOSCAR` 仅是路径采样附带输出。若目标是判定金属、半金属或窄隙，联合均匀网格本征值、费米占据和网格/展宽收敛。

## 4. 历史算例与验收

以下路径相对于 `<原站点工作根>/Materials`。表中历史 VASP 为 6.1.0，技术状态从 `OUTCAR`、`EIGENVAL`、`DOSCAR` 和对应日志核对。

| 历史目录 | 证据与结论 |
|---|---|
| `K2CrF4/scf/nosoc` | 均匀 `9×9×1`，15 个不可约 k 点、42 条带/自旋，`DOSCAR` 的 `E_F = 0.14557410` eV。可用作这组共线能带的零点与 DOS/PDOS 的历史来源。 |
| `K2CrF4/scf/soc` | 同一结构，81 个 k 点、77 条 spinor 能带，`DOSCAR` 的 `E_F = 0.14569876` eV。 |
| `K2CrF4/band` 与 `K2CrF4/projection/band` | 60 个路径 k 点、42 条带/自旋。有 `BAND.dat` 和 K/Cr/F 的 `PBAND_*_UP/DW.dat`。历史作业读 15 个 k 点的 `WAVECAR` 时提示 k 点数改变。`BAND_GAP` 使用路径 `E_F = 0.03788105` eV 得到 0.0074 eV 的采样间隔。按均匀网格的 `E_F` 直接比较两份 `EIGENVAL`，网格和路径的 ↑ 31–33 带、↓ 28 带能量范围均跨该参考值。这组数据支持费米能级穿带，精细费米面仍需密网格。 |
| `K2CrF4/projection/scf` | `POSCAR/OUTCAR` 记录的是旋转后的原胞，面法向沿 Cartesian x。相邻的 `projection/band` 仍沿 Cartesian z，并与 `band` 的 `OUTCAR/EIGENVAL` 逐字节相同。沿用旋转几何时，须在同一晶胞重新生成对应的电荷和路径。 |
| `MnInP2Te6/band/{nosoc,soc}` | 两支均有路径 `EIGENVAL` 与 `BAND.dat`。如重画，先核对与 `scf/{nosoc,soc}` 的输入及电荷来源，历史均匀网格 OUTCAR 的 `E_F` 分别约 −0.8058、−0.8156 eV，路径旧值约 −0.9402、−0.9099 eV。 |

检查清单：

- SCF 与路径的晶胞、元素/赝势顺序、磁序、泛函、U、SOC 和 `LMAXMIX` 匹配，路径日志确认读取指定 `CHGCAR`。
- `OUTCAR` 有电子收敛与计时汇总，`EIGENVAL`、`PROCAR` 的实际 `NKPTS/NBANDS` 一致，路径段数与 `KLABELS` 对应。
- 保留输入、原始本征值、投影、后处理设置和 `E_F` 来源。新作业以自身的均匀网格输出为准。

**6.5.1 实测。** `52244.master` 的 `9×9×1` SCF、`52245.master` 的 60 点路径和 `52246.master` 的 `15×15×1` 固定电荷 DOS 均退出 0。后两步读入同一次 SCF 电荷和磁化密度，输入 `POSCAR/POTCAR/CHGCAR` 的 SHA-256 一致。三套数据在各自参考下均复现 ↑ 31–33、↓ 28 带跨 `E_F`。DOS 加密例实际为 36 个不可约 k 点、42 带/自旋、`NEDOS=3001`、`E_F=0.15245435 eV`。复验 VASPKIT 1.5.0 的 `211/213/111/113`，产生总能带、Cr 投影、TDOS 和 Cr PDOS；`BAND.dat` 的首条能量与 `EIGENVAL − E_F` 一致。证据见 `hqt/.codex_reports/vasp_audits/master_library_20261113/vasp-replay/electronic-audit.txt`。
