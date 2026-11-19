# K₂CrF₄ 单层算例

证据位于 `hqt/Materials/K2CrF4/`，下文目录均相对该路径。新算用 [自编译 VASP 6.5.1](vasp_environment.md)。旧算的版本以 `OUTCAR` 首行为准。原始结构、输入和输出留在各自算例目录。

## 方法与数据流

主分支为 7 原子母胞 `K Cr F = 2 1 4`。多数历史任务使用 PBEsol（`GGA=PS`），PAW 数据集 `K_sv / Cr_pv / F`，`ENCUT=600 eV`。Cr 的 Dudarev 参数为 `LDAUTYPE=2, LDAUU=0 2.1 0, LDAUJ=0 0.6 0`，即 `Ueff=1.5 eV`。该数值来自归档 INCAR。关于计算 U 的流程见 [cRPA](U_cal.md)。

```text
relax/CONTCAR ──→ scf/nosoc；同一 POSCAR 用于 band 和 projection/band
             ├──→ scf/soc
             ├──→ aniso 的共线电荷参考 ──→ SOC 方向扫描
             ├──→ J/{FM,C-AFM,ST} 的磁构型比较
             └──→ phonopy/POSCAR-unitcell ──→ M 点软模 MPOSCAR
                                                 ↓
                 phonopy-new/POSCAR-unitcell ←── relax-new/PPOSCAR
```

`scf/nosoc`、`scf/soc`、`band`、`J/FM`、`aniso` 的 `POSCAR` 均与 `relax/CONTCAR` 的 SHA-256 一致。声子支路的三处传递也逐字节一致，`phonopy/MPOSCAR` 和 `MPOSCAR-001` 均对应 `relax-new/POSCAR`。J 分支按实际磁胞逐项核对结构和键数。

## 历史目录索引

| 目录 | 做过的计算及关键证据 |
|---|---|
| `relax` | VASP 6.1.0，`38514`，7 原子，Γ `9×9×1`，8 个离子步达到 `EDIFFG=-0.01 eV/Å`。`OUTCAR` 最大力 `0.0088 eV/Å`，最终 `a=b≈4.130604 Å`、`c=24.25 Å`。旧脚本使用 `OPTCELL=110`。新算改用官方约束写法，见 [弛豫与静态自洽](relax+scf.md)。 |
| `relax-new` | VASP 6.1.0，28 原子调制结构，Γ `3×3×1`。`50245` 因 `MAGMOM` 只展开了 7 个值而失败，`50247` 完成 15 个离子步，最大力 `0.0067 eV/Å`。`PPOSCAR` 是对称化后的 14 原子结构，用于新声子母胞。 |
| `scf/nosoc`、`projection/scf` | VASP 6.1.0 共线静态自洽，Γ `9×9×1`。前者保留 `38573/39809` 日志，后者为 `39802/39814`。现存 `OUTCAR` 均达电子阈值，`E-fermi≈0.1456 eV`，总磁矩约 `3.9405 μB/cell`。 |
| `scf/soc` | VASP 6.1.0 非共线入口，`40121`，Γ `9×9×1`，SOC 自洽达电子阈值。保留自洽 `WAVECAR`、`CHGCAR` 及矢量磁矩。 |
| `band`、`projection/band` | VASP 6.1.0，固定电荷 `ICHARG=11`，Γ–X–M–Γ，`LORBIT=11`。两目录现存 `OUTCAR`、`PROCAR`、`vasprun.xml`、`KPOINTS`、`BAND_GAP` 和 `CHGCAR` 的哈希一致，投影结果按一套归档计。现存两个 SCF 目录的 `CHGCAR` 与该带图目录的 `CHGCAR` 哈希各异，历史电荷复制关系待考。`PBAND_*` 按 K、Cr、F 和上下自旋分开。见 [能带和投影](band_dos.md)。 |
| `J/FM`、`J/C-AFM`、`J/ST` | VASP 6.1.0，`41042/41043/41046`，同组设置下的无 SOC 磁构型静态总能，均正常结束且达到电子阈值。FM 为 7 原子，另两态为 14 原子。先做每 Cr 归一，拟合 J 另需明确哈密顿量与周期键计数。 |
| `aniso` | VASP 6.1.0，`40122`。`aniso.pbs` 先在该目录用 81 点显式 k 网格生成共线自洽电荷，保存 `scf.0`，随后在同一电荷与网格上打开 SOC，用 `ICHARG=11` 扫描方向。`Eab/Eac/Ebc` 各 21 个能量点，`OUTCAR` 对应最后方向。见 [磁性与磁各向异性](magnetism.md)。 |
| `phonopy` | VASP 6.1.0 DFPT（`39304`），7 原子母胞 → `2×2×1`、28 原子超胞，Phonopy 2.19.1 插值得到 M 点虚频 −24.981334147 THz。保留 `anime.ascii`、`modulation.yaml` 和 `MPOSCAR*`。 |
| `phonopy-new` | VASP 6.1.0 DFPT（`50307`），14 原子重构母胞 → `2×2×1`、56 原子超胞。最低频率 −0.299765744 THz（Γ）。两套均用 Γ `3×3×1` 电子网格，2026-11-13 的 Phonopy 后处理与归档逐字节一致。见 [声子谱和结构重构](phonopy.md)。 |
| `test`、`test/632` | 同一 7 原子弛豫的版本对照。自编译 VASP 6.5.1 `ncl` 入口在共线模式运行（`51351`，退出 0），自编译 VASP 6.3.2 对应 `51353`（退出 0）。`51352` 的 `AMIX` 读取失败，单列为历史失败。两次成功结果与旧 `relax` 均为 8 步，`E0≈−19.761038 eV/cell`，最大力 `0.0088 eV/Å`，`c=24.25 Å`。 |

## 自编译复跑

2026-11-13，VASP 6.5.1、Intel MPI 单线程、每个 PBS 作业 28 ranks。证据在 `hqt/.codex_reports/vasp_audits/master_library_20261113/vasp-replay/`。

| PBS 作业 | 复核结果 |
| --- | --- |
| `52242.master` std relax | 官方 `LATTICE_CONSTRAINTS=110`，8 个离子步、最大力 `0.0088 eV/Å`，`c=24.25 Å` 保持不变。`TOTEN=−19.76157831 eV/胞`。 |
| `52244.master` std SCF | 复制历史均匀网格 SCF 的几何，19 个电子步，`TOTEN=−19.75385801 eV/胞`，按输出精度与原 SCF 相同。`E_F=0.14557409 eV`。 |
| `52245/52246.master` std 能带及 DOS | 同一新 SCF 电荷、60 点路径和 `15×15×1` 加密网格，均电子收敛。两支自旋均有跨过费米能的能带，重新生成 VASPKIT 能带、投影、DOS/PDOS。 |
| `52243.master` ncl SOC | 用历史 `9×9×1` 几何与输入，删除旧 `ISPIN=2`。38 个电子步收敛，81 个 k 点、77 条 spinor 带。`TOTEN=−19.77310587 eV/胞`、总自旋磁矩约 `(−0.00004, −0.00006, 3.93998) μB/胞`，在输出精度内复现历史值。 |
| `52247/52248/52250.master` std 磁序 | 统一四 Cr `2×2×1` 超胞与 `5×5×1` 网格，FM、C-AFM、ST 均收敛并保持最终磁序。FM 最低。`−J` 约定的 `J1=30.924 meV`、`J2=4.508 meV` 只对应这组高对称相的模型。见 [磁性教程](magnetism.md)。 |

首次 SCF `52241.master` 在 node01 进入电子主循环后六分钟仍无 DAV 记录，改用 node02 的独立目录复跑成功。首次 ST `52249.master` 在 node12 的 PBS 启动阶段没有会话和 VASP 输出，改用 node14 的独立目录复跑成功。两个首轮尝试都已取消。

## 结果使用边界

- 能带归档 `BAND_GAP` 给出路径上的 `0.0074 eV`，参考费米能 `0.0379 eV` 来自线段计算。正式报告须回到均匀网格自洽参考，检查费米附近占据、全布里渊区和网格收敛后判定金属或窄隙。
- 由 `J/*/OSZICAR` 最终 `E0` 按 Cr 数归一，FM/C-AFM/ST 分别为 `−19.753318/−19.625164/−19.669308 eV/Cr`（四舍五入到 `1 μeV/Cr`）。归档设置下 FM 最低。跨磁胞的电子采样密度须另行核对，J 的定量值依赖可比 k 网格、实际局域磁矩与模型约定。
- `Eac`、`Ebc` 的极差为 `0.25872 meV/cell`，`Eab` 极差为 `0.00001 meV/cell`（等于表格量化步长）。归档固定电荷扫描支持面内偏好。绝对 MAE 需更密 k 网格及方向可比的能量计算复核。
- 重构后最低频率在 Γ。施加 Phonopy 力常数对称化后，重构谱 Γ 最低频率由 −0.299765744 变为 −0.000120541 THz，`40×40×1` q 网格中未见低于 −0.01 THz 的模。旧 M 点大虚频保留。动力学稳定性仍需在同一重构母胞上做超胞、电子 k 网格和力精度收敛。 [声子后处理复验](phonopy.md#4-已验证的组内结果)

## 原论文对照

Ji 等的 Fig. 1、3、4 分别给出高对称原型的 M 点 Jahn–Teller 不稳定、费米能级穿带及 FM 磁序。论文用 cRPA 得到 Cr `Ueff=1.5 eV`，本站 K₂CrF₄ 用该值做了 DFT+U。论文 `P2₁/c` 基态还含八面体倾斜与旋转，报告间接隙约 `0.73 eV`、单位自旋最近邻 `J₁=11.75 meV`（磁力定理）。[论文原文](https://arxiv.org/html/2304.09359)

本站原型的四个面内 Cr–F 键均约 `2.0653 Å`。M 软模重构后每个 Cr 有两个 `1.9681 Å` 短键和两个 `2.2263 Å` 长键，两个 Cr 的长键轴近乎垂直，符合交错的面内 Jahn–Teller 畸变。几何对称性在 `10⁻⁵ Å` 容差为 `P4bm`，在 `10⁻⁴–10⁻² Å` 为 `P4/mbm`。原型为 `P4/mmm`。证据见 `phonopy-replay/primitive-check/`，空间群判定只使用原子坐标。
