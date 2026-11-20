# cRPA 测 U/J 与 DFT+U

示例 `Materials/MnInP2Te6/U_test` 已用自编译 VASP 6.5.1 + Wannier90 3.1.0 跑完。无 SOC、共线自旋、PBE、无 U。流程为 `SCF → 空带/WAVEDER → Wannier 目标子空间 → 静态 cRPA → 按目标模型使用 U/J`。本例材料、轨道、窗口和资源均需随新算例重新选择。

## 1. SCF 与空带

分别新建 `01_scf`、`02_empty`、`03_crpa`。三步使用同一 `POSCAR/POTCAR`，元素顺序 `Te Mn In P`，原子数 `6 1 1 2`。本例 `KPOINTS` 为 Gamma `9 9 1`，零偏移。全流程使用同一兼容入口，复现此例用 ncl 编译的 `vasp6.5so-wannier` 运行共线模式，`LSORBIT` 与 `LNONCOLLINEAR` 均保持关闭。用 [PBS ncl 模板](vasp_environment.md) 分别提交。

`01_scf/INCAR`

```ini
SYSTEM = MnInP2Te6 cRPA SCF
ISTART = 0
ICHARG = 2
ENCUT = 600
PREC = Accurate
LREAL = .FALSE.
LASPH = .TRUE.
GGA = PE
GGA_COMPAT = .FALSE.
ALGO = Normal
NELM = 120
EDIFF = 1E-7
ISMEAR = 0
SIGMA = 0.05
ISPIN = 2
MAGMOM = 6*0 4 0 2*0
ISYM = 0
LMAXMIX = 4
LDAU = .FALSE.
NSW = 0
NCORE = 4
KPAR = 1
NBANDS = 64
LORBIT = 11
LWAVE = .TRUE.
LCHARG = .TRUE.
```

SCF 作业达到 `EDIFF` 后，将 `POSCAR/POTCAR/KPOINTS/CHGCAR/WAVECAR` 复制进空的 `02_empty`。沿用 SCF INCAR，替换下列值并增加 `LOPTICS`。保留 `LORBIT=11` 供选窗口。

```ini
SYSTEM = MnInP2Te6 cRPA empty
ISTART = 1
ICHARG = 11
NBANDS = 140
LOPTICS = .TRUE.
LCHARG = .FALSE.
```

这一步固定电荷，重求较多的空带并产生 `WAVEDER`。归档采用 `ALGO=Normal` 并达到 `EDIFF`。官方还有 `ALGO=Exact` 的空带流程，切换时应核验内存、输出与结果。两个阶段原作业分别为 `51434.master`、`51440.master`，申请 28 MPI ranks。`OUTCAR` 的实际 `NBANDS` 分别为 70、140，均为 41 个不可约 k 点。第二步验收 `WAVECAR/WAVEDER/PROCAR/vasprun.xml` 非空，并把实际空带数传给下一步。查看 `OUTCAR` 中 WAVECAR 读取信息、实际 k 点、`NBANDS` 和末次电子迭代。[VASP cRPA 示例](https://vasp.at/wiki/CRPA_of_SrVO3)

## 2. 选 Wannier 子空间

本例取 `Mn:d` 五个、`Te:p` 十八个、`P:p` 六个，共 29 个 Wannier 函数。`NTARGET_STATES=1 2 3 4 5` 是本例检查后的 Wannier 编号。用均匀 k 网格的 `PROCAR/vasprun.xml` 分析 Mn-d 和配体杂化。窗口以 `.eig` 的原始本征能为准，若从 `E−EF` 的图上取值，先加回所用的 `EF`。

| 检查 | 判据 | 本例归档值 |
| --- | --- | --- |
| 外窗口 `−8～5 eV` | 各自旋每个 k 点至少 29 个候选态 | 81 个 k 点上，自旋 1 为 41–44，自旋 2 为 40–43 |
| 冻结窗口 `−8～0.8 eV` | 在外窗口内，各自旋每个 k 点至多 29 个态 | 自旋 1 为 26–27，自旋 2 为 24–25 |
| 目标轨道 | 检查轨道归属、周期边界下的中心、spread、同路径同零点的插值能带 | 两自旋前 5 个中心距 Mn 位点分别至多 0.0063 Å、0.0572 Å |

新材料先做独立 Wannier 预检。复制匹配的结构、均匀 k 网格、电荷和波函数，使用第 3 节同一投影和窗口，普通库模式使用 `ALGO=None`、`LWANNIER90=.TRUE.`、`LWANNIER90_RUN=.TRUE.`。移除 cRPA 专用设置，核验输出的完整 k 网格及两自旋，需时单独生成匹配的全网格波函数和投影。在同次 `.amn/.mmn/.eig` 上可独立测试新窗口。投影种类、原子顺序或 k 网格改变时重新生成相关矩阵。该预检要看实际接口输出，文件齐全后再开正式 cRPA。[VASP Wannier 接口](https://vasp.at/wiki/LWANNIER90_RUN) · [NTARGET_STATES](https://vasp.at/wiki/NTARGET_STATES)

## 3. 静态 cRPA

在空的 `03_crpa` 放入 `02_empty` 的 `POSCAR/POTCAR/KPOINTS/WAVECAR/WAVEDER`、`01_scf` 的 `CHGCAR`。沿用空带 INCAR，**移除** `LOPTICS`、`NELM`、`EDIFF`、`LORBIT`，替换并补齐以下设置。工作目录中的旧 `WANPROJ/WFULL*.tmp/.win/.chk` 会影响新算，开始前核对目录干净。归档的 `ENCUTGWSOFT` 实际值为 240 eV，显式写出便于复算；生产精度需测试响应截断及软截断。

```ini
SYSTEM = MnInP2Te6 cRPA
ALGO = CRPA
NBANDS = 140
NCORE = 1
KPAR = 1
NCSHMEM = 1
ENCUTGW = 300
ENCUTGWSOFT = 240
PRECFOCK = Fast
NUM_WANN = 29
NTARGET_STATES = 1 2 3 4 5
LWRITE_WANPROJ = .TRUE.
LWRITE_MMN_AMN = .TRUE.
LWAVE = .FALSE.
LCHARG = .FALSE.

WANNIER90_WIN = "
begin projections
Mn:d
Te:p
P:p
end projections
dis_win_min = -8.0
dis_win_max = 5.0
dis_froz_min = -8.0
dis_froz_max = 0.8
dis_num_iter = 1000
dis_conv_tol = 1e-8
num_iter = 500
conv_tol = 1e-8
guiding_centres = true
write_hr = true
bands_plot = true
bands_num_points = 80
begin kpoint_path
G 0.0 0.0 0.0 M 0.5 0.0 0.0
M 0.5 0.0 0.0 K 0.33333333 0.33333333 0.0
K 0.33333333 0.33333333 0.0 G 0.0 0.0 0.0
end kpoint_path
"
```

示例在约 502 GiB 的 node01 申请 48 槽，脚本中令 `NP=28`，实际只起 28 ranks。使用同一环境脚本和 `PBS_NODEFILE`。计算前查节点资源和磁盘余量，按 [本站规则](vasp_environment.md) 给师兄预留大节点。历史输出约 66 GiB、耗时约 19 h 11 min，预留足够 walltime。正式作业 `51648.master` 脚本、输出和参数都在 `U_test/03_crpa/`。cRPA 选 std 或 ncl 的适配路径，归档复现用 ncl。6.5.1 参考本页的 `ALGO=CRPA`，Wiki 中 6.6 起可用的选项需另核版本。[VASP 已知问题 #107、#112](https://vasp.at/wiki/Known_issues) · [WANPROJ](https://vasp.at/wiki/WANPROJ) · [cRPA 理论](https://vasp.at/wiki/CRPA_formalism)

## 4. 验收和提取

```bash
grep 'General timing' OUTCAR | tail -1
head -n 2 WANPROJ
find . -maxdepth 1 -name 'WFULL*.tmp' -size +0c | wc -l
grep -E 'spin components:|screened Hubbard [UuJ] =' OUTCAR | tail -12
for f in UIJKL.up.up.1 UIJKL.up.dn.1 UIJKL.dn.dn.1; do
    head -n 4 "$f"
    awk 'NF==6 && $1~/^[1-5]$/ && $1==$2 && $2==$3 && $3==$4 {print $1,$5}' "$f" | sort -nk1
done
```

- 已复核本例 `WANPROJ` 为 `2 81 140 29`，41 个非空 `WFULL`，三份 `ω=0` 的屏蔽矩阵齐全，矩阵同轨道平均与 OUTCAR 一致。`UIJKL` 为屏蔽相互作用，`VIJKL` 为裸库仑。OUTCAR 中 `U` 为同轨道平均，`u` 为不同轨道直接项，`J` 为不同轨道交换项。证据在 [crpa-audit.txt](evidence/crpa-audit.txt)。
- 两自旋 Wannier 解纠缠达到设定阈值，分别为 273、892 步。局域化均用完 500 步，末步 spread 变化分别约 `−3.0×10⁻⁵`、`−1.42×10⁻⁴ Å²`。归档未启用 `conv_window` 判据。发布或迁移前仍需对照目标投影能带，并检查 k 网格、空带数、响应截断、窗口和局域化设置的敏感性。

| 静态自旋块 | U (eV) | u (eV) | J (eV) | U−J (eV) |
| --- | ---: | ---: | ---: | ---: |
| ↑↑ | 2.7238 | 1.4290 | 0.6456 | 2.0782 |
| ↑↓ | 2.4270 | 1.2871 | 0.5689 | 1.8581 |
| ↓↓ | 2.1914 | 1.1758 | 0.5068 | 1.6846 |

## 5. 给后续 DFT+U 的参数

本例工作约定对三个独立自旋块等权平均，`U≈2.4474 eV`、`J≈0.5738 eV`，Dudarev 可试用 `Ueff=1.8736 eV`。这是将 Wannier 子空间结果用于 PAW DFT+U 的近似，未做完整 Slater 参数拟合。`Materials/MnInP2Te6/relax` 历史采用 `LDAUTYPE=1`，分别填 `U=2.4474 eV`、`J=0.5738 eV`；与下列 `LDAUTYPE=2` 的新算应分别登记方法，换方法需重新优化或做同口径自洽。

```ini
LDAU = .TRUE.
LDAUTYPE = 2
LDAUL = -1 2 -1 -1
LDAUU = 0 1.8736 0 0
LDAUJ = 0 0 0 0
LMAXMIX = 4
```

这里 `LDAUU` 已填入 `U−J`。改 U 或模型后重新自洽，避免直接固定无 U 的旧电荷。K₂CrF₄ 的历史 Cr `Ueff=1.5 eV` 另见 [算例](K2CrF4.md)。[VASP DFT+U](https://vasp.at/wiki/LDAUTYPE)

交给 AI 复核时提供 `INCAR/POSCAR/KPOINTS`、两个自旋 `.eig/.wout/.win`、`OUTCAR` 和 `UIJKL/VIJKL`。要求逐 k 检查窗口，区分解纠缠、局域化和 cRPA 三个状态，按频率和自旋提取矩阵，并保留每个数的来源。
