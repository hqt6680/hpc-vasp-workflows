# 声子谱、虚频和结构重构

适用范围为 VASP 谐波声子和 Phonopy 后处理。新算使用本站自编译 VASP 6.5.1 的共线 `std` 入口，见 [运行环境](vasp_environment.md)。组内已复跑后处理的版本为 Phonopy 2.19.1，使用原站点的 Conda 环境。实例见 [K₂CrF₄](K2CrF4.md)。

## 1. 结构和计算方法

从与目标磁态、泛函、赝势、U 和 vdW 设置一致的 [弛豫](relax+scf.md) 结构开始。新算声子前宜将残余力收紧到约 `0.001 eV/Å`，检查面内应力，并固定二维体系的真空方向。先根据结构和磁序确定母胞，再生成整倍数超胞。AFM 等磁态需保留磁周期并核对对称性和超胞 `MAGMOM`。

在新目录放入该母胞，命名为 `POSCAR-unitcell`。以下以二维 `2×2×1` 为例，超胞尺寸和相应电子 k 网格应做收敛检查。

```bash
PHONOPY="$(command -v phonopy)"
"$PHONOPY" -d --dim='2 2 1' -c POSCAR-unitcell
cp SPOSCAR POSCAR
```

单次 VASP 任务对**未位移的 `SPOSCAR`** 求 Hessian。以对应的静态 INCAR 为底稿，保留与弛豫一致的物理设置，移除弛豫参数，按下列有限差分设置起步。

```ini
ISTART = 0
ICHARG = 2
IBRION = 6
NSW = 1
ISIF = 2
NFREE = 2
POTIM = 0.015
PREC = Accurate
LREAL = .FALSE.
EDIFF = 1E-8
LWAVE = .FALSE.
LCHARG = .FALSE.
```

`IBRION=6` 是带对称性的有限差分，`POTIM` 为位移幅度（Å）。K₂CrF₄ 历史算例用的是 `IBRION=8`（带对称性的 DFPT），只在计算超胞的 Γ 点构造响应，随后由 Phonopy 插值得到母胞的声子色散。DFPT 适用性需按具体方法核对。对 DFT+U 新算优先用有限差分，并复查每个位移的电子收敛及磁态。两条路线都是单个 VASP Hessian 任务，此时 `POSCAR-*` 和 `phonopy_disp.yaml` 不参与后处理。若改用 Phonopy 独立分发位移，则每个 `POSCAR-xxx` 对应一次 `IBRION=-1, NSW=0` 的静态力计算，按位移序号将 `vasprun.xml` 交给 `phonopy -f` 生成 `FORCE_SETS`。两条后处理入口分别用 `FORCE_CONSTANTS` 和 `FORCE_SETS`。 [VASP 有限差分](https://vasp.at/wiki/Phonons_from_finite_differences) · [VASP DFPT](https://vasp.at/wiki/Phonons_from_density-functional-perturbation_theory) · [Phonopy 2.19.1 的 VASP 接口](https://github.com/phonopy/phonopy/blob/v2.19.1/doc/vasp-dfpt.rst)

## 2. 提取力常数并出谱

检查 `OUTCAR` 正常结束、电子步达标、`vasprun.xml` 含 `<dynmat>` 和 `name="hessian"`，再在独立后处理目录放入原始母胞、XML 和 `band.conf`。下面是 K₂CrF₄ 方形母胞的 Γ–X–M–Γ 示例。其他结构重选倒空间路径。

```text
DIM = 2 2 1
FORCE_CONSTANTS = READ
BAND = 0 0 0   0.5 0 0   0.5 0.5 0   0 0 0
BAND_LABELS = $\Gamma$ X M $\Gamma$
```

```bash
"$PHONOPY" --fc vasprun.xml
MPLBACKEND=Agg "$PHONOPY" -c POSCAR-unitcell -p -s band.conf
```

保留 `FORCE_CONSTANTS`、`band.yaml` 和 `band.pdf`。母胞、超胞矩阵和原子顺序必须与 VASP Hessian 对应，频率单位为 THz，负值表示虚频。使用超胞检查、声学支在 Γ 的行为、q 网格和本征矢判断软模。二维体系近 Γ 的弯曲声学支对力精度、超胞和力常数约束敏感。极性材料如需解释 Γ 附近长程库仑效应，另行核对 Born 有效电荷、介电张量和适合二维模型的处理。虚频保留在原始数据中，使用声学和则并存施加前后的结果。

## 3. 沿虚频模生成新结构

旧 K₂CrF₄ 用 M 点最低支生成过候选结构。将 `DIM` 和 `FORCE_CONSTANTS` 设置写入独立 `mode.conf`，再加入下列设置。输出 `MPOSCAR`、`MPOSCAR-001`、`MPOSCAR-orig` 和 `modulation.yaml`。

```text
MODULATION = 2 2 1, 0.5 0.5 0 1 3
```

```bash
"$PHONOPY" -c POSCAR-unitcell mode.conf
```

逗号后的三项坐标是 q 点，其后为从 1 开始的支编号和 Phonopy 幅度参数。`3` 复现历史构型，`MPOSCAR` 相对 `MPOSCAR-orig` 的最大原子位移实测 `0.0920 Å`。动画使用独立配置，加入 `ANIME = 0.5 0.5 0` 得到 `anime.ascii`。Phonopy 2.19.1 里启用 `ANIME` 会进入动画模式，出谱配置仅保留 `BAND`。将调制结构送入新目录弛豫。随后在结构分析目录执行 `"$PHONOPY" --symmetry -c CONTCAR` 可生成 `PPOSCAR`，核对对称性容差、原子顺序、结构畸变和磁周期，再选新母胞计算声子。 [Phonopy 模式设置](https://phonopy.github.io/phonopy/setting-tags.html) · [Phonopy 结构对称性](https://phonopy.github.io/phonopy/command-options.html#symmetry)

视频中的扩胞、Hessian 和动画操作见 [03 声子谱 14:10–20:00、25:50–30:30](https://www.bilibili.com/video/BV1cxJa65Ebi/?t=850)。软模位移、重优化与提取原胞见 [04 重优化+投影能带态及密度 01:25–04:00、06:50–10:50](https://www.bilibili.com/video/BV1JxHg6QE5K/?t=85)。

## 4. 已验证的组内结果

2026-11-13 在原站点用 Phonopy 2.19.1 从历史 XML 重新提取力常数并重出声子谱，以下三套 `FORCE_CONSTANTS` 和 `band.yaml` 与归档逐字节一致。旧 K₂CrF₄ 的 `anime.ascii`、`modulation.yaml`、`MPOSCAR`、`MPOSCAR-001`、`MPOSCAR-orig` 也逐字节复现。对 `relax-new/CONTCAR` 执行 `--symmetry` 得到的 14 原子 `PPOSCAR` 与归档一致，几何空间群随容差由 `P4bm` 变为 `P4/mbm`。VASP 力常数来自历史 6.1.0 运行，复验范围为后处理。证据目录为 `.codex_reports/vasp_audits/master_library_20261113/phonopy-replay/`（相对 hqt）。

| 归档路径（相对 `Materials/`） | VASP / 超胞 | 最低频率与位置 |
|---|---|---|
| `K2CrF4/phonopy` | `IBRION=8`，7 原子母胞 → 28 原子 | −24.981334147 THz，M |
| `K2CrF4/phonopy-new` | `IBRION=8`，14 原子重构母胞 → 56 原子 | −0.299765744 THz，Γ |
| `MnInP2Te6/phonopy` | `IBRION=6`，10 原子母胞 → 90 原子 | −0.357426953 THz，Γ |

对 K₂CrF₄ 两套旧力常数做 `FC_SYMMETRY=.TRUE.` 敏感性检查，并对同一力常数分别插值到未约化的 Gamma `40×40×1` q 网格。旧 M 点最低频率保持 −24.981334147 THz。重构谱的最低频率由 −0.299765744 变为 −0.000120541 THz（均在 Γ），网格中低于 −0.01 THz 的 q–分支组合由 19 个降为 0。结果支持重构谱近 Γ 的负频率主要受力常数对称性残差影响。两套谱对应不同母胞，动力学稳定性仍需在同一重构母胞上做电子 k 网格、超胞尺寸和力精度收敛。检查结果见 `q-mesh-40/summary.txt`。

MnInP₂Te₆ 的原配置已启用 `FC_SYMMETRY`。网格最低仍为 Γ 的 −0.357427 THz，共 361 个 q–分支组合低于 −0.01 THz，需看本征矢和收敛结果再判定性质。
