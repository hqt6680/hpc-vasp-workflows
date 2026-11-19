# 结构优化与静态自洽

先确认晶胞、赝势和目标磁态。流程为 `POSCAR → relax/CONTCAR → scf/CHGCAR、WAVECAR → 能带/DOS/其他后处理`。环境、输入预检和提交见 [VASP 与 PBS](vasp_environment.md)。本例使用 K₂CrF₄ 七原子单层，其他材料重选参数。

## 1. 准备 relax

在新目录准备 `INCAR`、`POSCAR`、`POTCAR`、`KPOINTS`、`run.pbs`。K₂CrF₄ 的 POSCAR 顺序 `K Cr F`，原子数 `2 1 4`，赝势标签为 `K_sv`、`Cr_pv`、`F`。实际输入按归档 `Materials/K2CrF4/test` 复现，选 std，并以官方 `LATTICE_CONSTRAINTS` 代替 `OPTCELL`。

```ini
SYSTEM = K2CrF4 relax
ISTART = 0
ICHARG = 2
ENCUT = 600
PREC = Accurate
LREAL = Auto
GGA = PS
GGA_COMPAT = .FALSE.
ALGO = Normal
NELM = 100
NELMIN = 4
EDIFF = 1E-6
ISMEAR = 0
SIGMA = 0.05
NCORE = 4

ISPIN = 2
MAGMOM = 2*0 4 4*0
LDAU = .TRUE.
LDAUTYPE = 2
LDAUL = -1 2 -1
LDAUU = 0 2.1 0
LDAUJ = 0 0.6 0
LMAXMIX = 4
AMIX = 0.2
BMIX = 0.0001
AMIX_MAG = 0.8
BMIX_MAG = 0.0001

IBRION = 2
ISIF = 3
LATTICE_CONSTRAINTS = .TRUE. .TRUE. .FALSE.
NSW = 80
EDIFFG = -1E-2
LORBIT = 11
LWAVE = .FALSE.
LCHARG = .FALSE.
```

```text
Gamma 9x9x1
0
Gamma
9 9 1
0 0 0
```

- `GGA=PS` 为 PBEsol。`ENCUT=600 eV`、`9×9×1`、Cr `Ueff=2.1−0.6=1.5 eV` 和上述混合参数都是 K₂CrF₄ 的已用设置。`LDAUL/LDAUU/LDAUJ` 每种元素一项，`MAGMOM` 每个原子一项。无 U 时删去这组 U 标签并设 `LDAU=.FALSE.`。MnInP₂Te₆ 另见 [测 U 与用 U](U_cal.md)。
- 固定晶胞只放松离子用 `ISIF=2`，移除晶格约束和 `OPTCELL`。二维晶格面内优化时，示例的 `110` 掩码冻结 z 方向应变、允许面内剪切，适用于 `a,b` 在 xy、`c` 平行 z 的放置。倾斜晶胞需先核对坐标和预期自由度。老 `OPTCELL` 文件仅在支持它的构建使用，和 INCAR 同时存在时两者必须一致。`Selective dynamics` 控制原子自由度。
- 对新体系先确定对称性会否约束结构或磁态。复现本例保留归档的默认对称性，允许降对称/重构时另做降低对称性的计算。变胞需检查 Pulay 应力、`ENCUT`、k 密度，比较小能差时也应核验 `LREAL=.FALSE.` 等精度设置。

## 2. 验收 relax

```bash
grep -E 'reached required accuracy|General timing' OUTCAR
grep -E 'FORCES: max atom|in kB' OUTCAR | tail -4
tail -n 5 OSZICAR
test -s CONTCAR
```

检查最终电子迭代达到 `EDIFF`，离子优化主动停止，自由原子的最大力达到 `|EDIFFG|`，磁矩符合目标态。变胞另看允许方向的应力和最终晶格，确认受限方向保持不变。若电子步反复用尽 `NELM` 或离子步用尽 `NSW`，先诊断并续算，再交给后续步骤。重构分支应保留独立结构与证据，见 [K₂CrF₄ 算例](K2CrF4.md)。

## 3. 静态 SCF

新建 SCF 目录，将通过验收的 `relax/CONTCAR` 复制为 `POSCAR`。沿用一致的 POTCAR、泛函、磁态和 U。按用途复核均匀 k 网格。可以从头以最终晶胞建立基组。以下为对 relax INCAR 的修改，替换同名项并移除 `LATTICE_CONSTRAINTS`、`EDIFFG`、离子步专用 `POTIM` 和 `OPTCELL` 文件。

```ini
SYSTEM = K2CrF4 scf
ISTART = 0
ICHARG = 2
IBRION = -1
NSW = 0
ISIF = 2
EDIFF = 1E-6
LWAVE = .TRUE.
LCHARG = .TRUE.
```

复算 K₂CrF₄ 普通 SCF 采用归档的 `EDIFF=1E-6`。用于小能差、弱力或后续声子时，从更紧的阈值出发并按目标量做收敛检查。普通静态 SCF 要更新电荷，`ICHARG=11` 留给固定电荷后处理。WAVECAR 只为下游确实需要时保留。固定电荷的 DFT+U 后处理需要在产生及读取 CHGCAR 两侧都设置合适的 `LMAXMIX`，d 元素常用 4，f 元素常用 6。

检查 `OUTCAR` 的末次电子收敛、总能、费米能级、磁矩、力和应力，按下游要求确认 `CHGCAR/WAVECAR` 非空。能带和 DOS 读 [能带与态密度](band_dos.md)，SOC 读 [磁性计算](magnetism.md)。

**6.5.1 实测。** 本轮用 std 和官方 110 约束跑 `52242.master`，8 步结束，最大力 `0.0088 eV/Å`，`a=b≈4.130604 Å`、`c=24.25 Å`，最终 `TOTEN=−19.76157831 eV/胞`。同一历史 SCF 几何用 std 跑 `52244.master`，19 个电子步收敛，`TOTEN=−19.75385801 eV/胞`、`E_F=0.14557409 eV`，输出的 CHGCAR 用于此次能带和 DOS。MnInP₂Te₆ 用 Dudarev `Ueff=1.8736 eV` 的全流程另见 [Materials/test](case_index.md)。[K₂CrF₄ 复跑记录](K2CrF4.md#自编译复跑)

视频 [02 结构优化、自洽、能带](https://www.bilibili.com/video/BV1ZQpb6zEYV/) 对应 [晶格约束](https://www.bilibili.com/video/BV1ZQpb6zEYV/?t=531)、[结构优化](https://www.bilibili.com/video/BV1ZQpb6zEYV/?t=1643)、[自洽](https://www.bilibili.com/video/BV1ZQpb6zEYV/?t=2226)。官方 [ISIF](https://vasp.at/wiki/ISIF) · [LATTICE_CONSTRAINTS](https://vasp.at/wiki/LATTICE_CONSTRAINTS) · [EDIFFG](https://vasp.at/wiki/EDIFFG) · [ICHARG](https://vasp.at/wiki/ICHARG)。
