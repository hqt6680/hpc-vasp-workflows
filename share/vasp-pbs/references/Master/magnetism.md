# 磁序、SOC、磁晶各向异性与交换

原站点参考环境为自编译 VASP 6.5.1。共线用 `bin/vasp6.5-wannier`（`vasp_std`），非共线及 SOC 用 `bin/vasp6.5so-wannier`（`vasp_ncl`）。PBS 模板在 `software/vasp-6.5.1/examples/`，按 [静态自洽教程](relax+scf.md) 检查输入。以下历史证据路径相对于 `<原站点工作根>/Materials`。

## 1. 共线磁序与交换 J

1. 在同一已验收几何上建立足以表示所有候选磁序的公用超胞，每个磁序一个静态 SCF 目录。固定泛函、赝势、U、电子精度和展宽。用公用超胞可直接保持同一 k 网格、FFT 和能量归一化。
2. `ISPIN=2`，按 POSCAR 原子顺序填写每个原子一个 `MAGMOM`，例如 `K Cr F / 2 1 4` 的原胞 FM 用 `2*0 4 4*0`，14 原子的反平行初值用 `4*0 4 -4 8*0`。先绘制 Cr 子晶格或列出坐标与符号，确认棋盘和条纹分别对应哪些键。
3. `OUTCAR` 同时检查电子收敛、最后一份磁矩表及总能。验收磁序以最终局域磁矩为准。用相同的能量定义并记录单位，含电子展宽时检查能差对 `SIGMA` 和 k 网格的依赖。
4. 写清哈密顿量符号、每条键计一次还是两次、自旋取单位向量还是长度 `S`。按 POSCAR 周期邻居逐壳数键，以每个磁序的自旋点积之和建立线性方程。至少需要足够多的独立磁序，并用额外磁序检验拟合。

例如，只保留正方晶格的各向同性最近邻 `J1` 和对角次近邻 `J2`，取 `H = −Σ(i<j) Jij (ei·ej)`，其中 `ei` 为单位自旋，键计一次。每磁性原子的能量 `e` 满足下式。

```text
e_FM      = e0 - 2*J1 - 2*J2
e_checker = e0 + 2*J1 - 2*J2
e_stripe  = e0        + 2*J2
J1 = (e_checker - e_FM) / 4
J2 = (2*e_stripe - e_FM - e_checker) / 8
```

此模型要求三种磁序处于同一几何、各壳层键等价且能差数值收敛。`J > 0` 偏好平行。转入长度为 `S` 的自旋模型或按有序对双计数时显式换算。三角磁晶格和低对称晶格需另数键。

组内视频以 `H = +Σ Jij (ei·ej)` 写方程，采用计算胞总能（FM 一 Cr、AFM 和 ST 各两 Cr）。复算时先用每 Cr 能量，视频的 J 与上式的 J 符号相反。 [组内 05 交换与方程，36:40](https://www.bilibili.com/video/BV1rVxk69EJm/?t=2200)

**历史 K₂CrF₄。** 三支 6.1.0 算例均达到电子停止条件，`GGA=PS`、`ENCUT=600` eV、Cr 的 Dudarev `Ueff = 1.5` eV，`EDIFF=1E-7`。数据取各自 `OUTCAR` 最后一份 `TOTEN` 与磁矩表。

| 目录 | 晶胞 / Cr 数 | 最终 Cr 局域磁矩 (μB) | TOTEN (eV/计算胞) |
|---|---|---|---:|
| `K2CrF4/J/FM` | 正方原胞 / 1 | +3.651 | −19.75385798 |
| `K2CrF4/J/C-AFM` | √2×√2 / 2 | +3.589, −3.589 | −39.25343923 |
| `K2CrF4/J/ST` | 2×1 / 2 | +3.608, −3.608 | −39.34113518 |

三支历史都填了 `9×9×1`，实际倒空间密度随超胞改变。表中每 Cr 归一化的历史能量次序为 FM、ST、C-AFM，从低到高。按上面的 `−J` 号约定，仅代入历史 `TOTEN` 得 `J1≈31.785 meV`、`J2≈4.930 meV`。这组数值用于复核方程和单位。正式提取 J 应统一超胞并测试 k 密度、展宽和能量定义。

**同胞复跑。** 用 `K2CrF4/phonopy/POSCAR` 的高对称 `2×2×1` 超胞（28 原子、4 Cr），按面内 `(00,10,01,11)` 排列四个 Cr。统一 Gamma `5×5×1`、`ISYM=0`、`LREAL=.FALSE.`、`EDIFF=1E-7`，其他物理设置延续 PBEsol 和 `Ueff=1.5 eV`。`MAGMOM` 写成 `8*0` 加中间四个 Cr 初值，最后 `16*0`。

| 磁序 / PBS | 四个 Cr 初值 (μB) | 最终 Cr 磁矩 (μB) | TOTEN (eV/超胞) |
| --- | --- | --- | ---: |
| FM / `52247.master` | `4 4 4 4` | `3.645 3.645 3.645 3.645` | −78.99762834 |
| C-AFM / `52248.master` | `4 -4 -4 4` | `3.590 -3.590 -3.591 3.590` | −78.50285075 |
| ST / `52250.master` | `4 -4 4 -4` | `3.606 -3.606 3.606 -3.606` | −78.67810839 |

三支均正常结束并保持目标磁序。ST、C-AFM 分别比 FM 高 `79.880`、`123.694 meV/Cr`。上述 `−J` 模型得到 `J1=30.924 meV`、`J2=4.508 meV`，用 `energy(sigma->0)` 则为 `31.064`、`4.486 meV`。默认实际 `NBANDS` 为 `147/140/140`，三支最高带均高于各自费米能 `2.65 eV` 以上且无占据。结果对应这套高对称结构与采样，定量使用前需做 k 网格、展宽及模型收敛，并区分软模重构相。证据见 `.codex_reports/vasp_audits/master_library_20261113/vasp-replay/exchange-audit.txt`。

**历史 MnInP₂Te₆。** `J/{FM,AFM,ds,neel}` 都有共线收敛输出，`J/soc/{xfm,xafm,zfm,zafm}` 有 SOC 收敛输出。共线组的 AFM 为 40 原子，其余为 90 原子，`Ueff = 1.1094` eV。SOC 组为 20 原子，采用 `LDAUTYPE=1`，Mn 的 `U = 1.9262` eV、`J = 0.4384` eV。两组采用各自的方法，提取参数时各自构建可比较的数据集。

## 2. SOC 自洽

以已弛豫结构做均匀网格静态 SCF，复制收敛共线输入后按实际体系调整。以下是 K₂CrF₄ 七原子胞、初始磁矩沿 Cartesian z 的关键修改，沿用 `GGA=PS`、同套 PAW 和 DFT+U。

```ini
ISTART = 0
ICHARG = 2
NSW = 0
IBRION = -1
LSORBIT = .TRUE.
SAXIS = 0 0 1
MAGMOM = 6*0 0 0 4 12*0
ISYM = -1
GGA_COMPAT = .FALSE.
LREAL = .FALSE.
LORBIT = 11
LORBMOM = .TRUE.
LMAXMIX = 4
LWAVE = .TRUE.
LCHARG = .TRUE.
```

`LSORBIT` 会开启 `LNONCOLLINEAR`，删除继承的 `ISPIN=2`。POSCAR 有 N 个原子时 `MAGMOM` 展开为 3N 个数。默认 `SAXIS=0 0 1` 时自旋分量与 Cartesian 轴重合。若改 `SAXIS`，磁矩输出和 `MAGMOM` 在 spinor 基底中解释，方向比较时统一变换。SOC/磁态改变可能导致不同的对称性和 k 列表。首次移植从新目录自洽，或在核对 k 网格、磁化密度及版本兼容后用 `ICHARG=1` 读电荷重新自洽。历史 `K2CrF4/scf/soc` 用 6.1.0，在默认轴下收敛到总自旋磁矩约 `(−0.00004, −0.00006, 3.93998)` μB/胞。 [VASP LSORBIT](https://vasp.at/wiki/LSORBIT) · [VASP ISPIN](https://vasp.at/wiki/ISPIN) · [VASP SAXIS](https://vasp.at/wiki/SAXIS)

6.5.1 的 `52243.master` 按历史 `ISYM=0`、`LREAL=Auto` 复跑，移除旧 `ISPIN=2`，关闭不需要的重启文件输出。38 个电子步收敛，实际 81 个 k 点和 77 条 spinor 带，`TOTEN=−19.77310587 eV/胞` 与上述总磁矩均复现历史值。更严格的方向能差仍应单独按 MAE 流程检验。

## 3. 磁晶各向异性 MAE

力定理流程为**共线准确自洽 → 固定电荷 SOC 扫方向**。以共线基态输出 `CHGCAR`，源计算和方向计算采用一致的完整 k 列表，必要时从源 SCF 起关闭对称。设置 `PREC=Accurate`、`LREAL=.FALSE.`、匹配的 U 与 `LMAXMIX`；各方向保持相同的实际 `NBANDS`，spinor 数可从共线每自旋带数的两倍起检查。

每个方向新建目录，复用同一份源 `CHGCAR`、结构、赝势和 k 网格。用 `vasp_ncl`，沿用上一节非共线设置，改 `ICHARG=11`、`LWAVE=.FALSE.`、`LCHARG=.FALSE.`。如读经核对兼容的同源共线 `WAVECAR`，所有方向都用相同波函数来源和 `ISTART=1`，并核实日志确实读入。K₂CrF₄ 历史做法将磁矩留在 spinor z 分量，通过 `SAXIS` 改 Cartesian 方向。a、b、c 分别为 `1 0 0`、`0 1 0`、`0 0 1` 只适用于该正交、与 Cartesian 对齐的晶胞。

提取同一种能量，以最低方向 `E0` 为零，报告 `1000*(E方向−E0)/N磁性原子`（meV/磁性原子）。保留每个方向的 `OUTCAR/OSZICAR`、日志、角度与实际 Cartesian 轴，并核对最终磁矩。重点检查 k 网格、展宽、`EDIFF`、对称性与目标能差尺度，可用几个主方向全自洽 SOC 交叉验证。含有磁偶极形状各向异性的模型需要单独计算其贡献。 [VASP 固定电荷 MAE](https://vasp.at/wiki/Determining_the_Magnetic_Anisotropy) · [VASP 自洽 SOC MAE](https://vasp.at/wiki/Including_the_Spin-Orbit_Coupling)

**历史 K₂CrF₄。** `K2CrF4/aniso/aniso.pbs` 先生成一轮共线 SCF，再做 `ab/ac/bc` 各 21 点（表第一列乘 10°）。`Eab/Eac/Ebc` 与 `aniso_40122.master.out` 共见 63 个方向和 1 个源 SCF。重查各段最后的 DAV，均达到 `10⁻⁷ eV`。由 `Eac` 的 0° 与 90° 得 `E_c − E_a = +0.25872` meV/Cr，历史结果支持面内较低。面内差在输出舍入尺度，易轴未分辨。脚本逐次覆盖中间 `INCAR/OUTCAR`，留存的单个 OUTCAR 代表最后一个方向。

**历史 MnInP₂Te₆。** `MnInP2Te6/aniso` 用 PBE、`LDAUTYPE=1`，Mn `U=1.9262 eV`、`J=0.4384 eV`。`39312` 的 64 段同样达到电子阈值。表中 `E_z−E_x=+0.48900`、`E_z−E_y=+0.48937 meV/Mn`，面内极差 `0.00043 meV/Mn`，后者接近电子阈值量级。两个材料的方向表都与 PBS 日志中的舍入总能一致。证据见 [mae-audit.txt](evidence/mae-audit.txt)。

## 4. DMI 的 CW/CCW 能差

`MnInP2Te6/D/{CW,CCW}` 为同一个 40 原子超胞和相同 Gamma `3×9×1`、PBE、`IVDW=11`、SOC、`ISYM=-1`、`LDAUTYPE=1`（Mn 的 `U = 1.96` eV、`J = 0.43` eV）。四个 Mn 按传播方向由 POSCAR 第 25–28 个原子依次指定。

```ini
# CW
MAGMOM = 72*0  4 0 0  0 0 -4  -4 0 0  0 0 4  36*0
# CCW 在自己的 INCAR 中替换为
# MAGMOM = 72*0  4 0 0  0 0 4  -4 0 0  0 0 -4  36*0
```

两支历史 6.1.0 输出电子收敛，最终 Mn 磁矩约 4.20 μB 并保持 xz 平面各自手性。末尾 `TOTEN` 分别为 CW −172.65185362 eV、CCW −172.64864359 eV，对应 `E_CCW − E_CW = +3.21003` meV/超胞。`energy(sigma->0)` 给出 +4.04406 meV/超胞。这两种能量差异需要展宽及 k 网格收敛检查。

要映射到键上的 `Dij`，先声明 `H_DMI = Σ Dij·(ei×ej)` 的符号与有向键计数，按几何和两个手性计算叉积系数。组内 06 用 `test/CoI2` 演示四自旋 90° 排列。仅有四条等价有向键贡献同一 D 投影、每条计一次时，两个手性的系数差绝对值为 8。对这里的 Mn 晶格须重数键和方向。 [组内 06 手性构造，10:42](https://www.bilibili.com/video/BV1Ms476PENF/?t=642) · [CW/CCW 能量映射示例](https://doi.org/10.1103/PhysRevLett.115.267210)

视频另展示 CoI₂ 的历史能量 CW −39.49710406 eV、ACW −39.51250030 eV。按视频的键方向和符号，差值除以 8 得 +1.92453 meV。画面还出现异常大的原子力，且演示输入中的 `LAMBDA=0` 没有罚项。该数值只复核算式。需用两份原始输出验收结构、电子收敛和最终手性后再引用。[组内 06 算式，43:10](https://www.bilibili.com/video/BV1Ms476PENF/?t=2590) · [输出检查，44:30](https://www.bilibili.com/video/BV1Ms476PENF/?t=2670)

若初始手性在自洽中松弛掉，在 6.5.1 可用 `I_CONSTRAINED_M=4` 约束方向及符号。按 POSCAR 顺序写 3N 个 `M_CONSTR` 分量并检查 `RWIGS`，用配对的正 `LAMBDA` 逐级试算，记录 `OSZICAR` 的残余罚能 `E_p` 与积分磁矩。`I_CONSTRAINED_M=1` 约束轴线，`LAMBDA=0` 对应零罚项。 [组内 06 约束设置，31:40](https://www.bilibili.com/video/BV1Ms476PENF/?t=1900) · [VASP 约束局域磁矩](https://vasp.at/wiki/I_CONSTRAINED_M)

## 5. Wannier90 → TB2J

从零开始或复算见 [TB2J 教程](tb2j.md)，包括三方向、Wannier 权重核验、积分收敛和逐键验收。

1. 用匹配的静态 SCF 生成 Wannier90 接口数据。非共线支要保持 SOC、均匀全 k 网格、spinor 投影顺序、相同的能量零点。保存 `.win/.amn/.mmn/.eig/.wout` 和 `*_hr.dat`，若有 `*_wsvec.dat` 也保留。
2. 验收外/冻结窗态数、实际收敛、Wannier 中心/投影、目标能窗的 DFT/Wannier 能带与自旋轨道顺序。再用本机版本 `wann2J.py --help` 核对参数。
3. `wann2J.py` 的 spinor 入口用 `--spinor --prefix_spinor wannier90 --elements Mn`，再传入已核对的 `--groupby orbital` 或 `--groupby spin`、同一 Hamiltonian 的 `--efermi`（eV）和经收敛的 `--kmesh`。`--groupby` 选择相邻 ↑↓ 还是按自旋分组，按实际基底核对。比较 `exchange.out`、`assigned_basis.txt` 与下游格式，逐壳检查对称等价键、符号、双计数和单位。单轴 spinor 结果仅用可提取的张量分量，完整张量按 TB2J 对多方向数据的合并方法处理。 [TB2J Wannier90 接口](https://tb2j.readthedocs.io/en/latest/src/wannier.html) · [TB2J 哈密顿量约定](https://tb2j.readthedocs.io/en/latest/src/convention.html)

**历史 MnInP₂Te₆。** `TB2J/wannier90.win` 的 `spinors=true`，`num_wann=58`，`num_bands=112`，`mp_grid=9×9×1`，轨道为 Mn:d、Te:p、P:p，外窗口 −7～3.5 eV、冻结窗口 −6.3～2.2 eV。`wannier90.wout` 明报 disentanglement 达到迭代上限且未满足阈值，PBS stderr 留有 Wannier 接口错误，目录里另有 Wannier 与 TB2J 0.9.0.1 的后处理产物。旧 `exchange.out` 的表格与紧跟的 `J_iso:` 项读数不一致（例如同一约 7.022 Å 的键为 0.7056 与 1.7056 meV），部分项带 `[Testing!]`。这批文件可用于追溯试算；采用数值前先重新验证 Wannier，再用同一新输出核对 TB2J 版本、命令、方向、单位与导出数据。
