# Wannier90 与 TB2J

用 VASP 和 Wannier90 构造 Hamiltonian，再用 TB2J 提取逐键磁交换。只算无 SOC 的各向同性交换时，准备共线 ↑/↓ 两套 Wannier 前缀。需要 DMI 和对称交换张量时，做同一结构的三支 SOC 自洽，参考磁矩分别沿 Cartesian x、y、z。单离子各向异性见 [磁性计算](magnetism.md)。

## 1. SOC 自洽与接口导出

沿用已验收结构和 SCF 的泛函、赝势及 DFT+U 设置。用 [本站 ncl 模板](vasp_environment.md) 在均匀网格上计算，`ISYM=-1` 保留全网格。固定 `SAXIS=0 0 1`，按 POSCAR 顺序给每个原子设置三个 `MAGMOM` 分量。检查最终磁矩方向、电子收敛和正常退出。

```ini
LWANNIER90 = .TRUE.
LWANNIER90_RUN = .FALSE.
LWRITE_MMN_AMN = .TRUE.
NUM_WANN = 66  # 本例，按投影数调整
```

在 INCAR 的 `WANNIER90_WIN` 写投影和 `spinors=true`。本站 VASP 6.5.1 用 INCAR 的 `NUM_WANN` 确定接口投影维数。选 `NBANDS` 覆盖 Wannier 外窗，核对输出 `.eig/.amn/.mmn` 的 k 点、能带和投影数。保留同轴 `CHGCAR`，用 `ICHARG=11` 算一条参考能带。TB2J 使用**均匀网格自洽**的费米能。 [VASP Wannier 接口](https://vasp.at/wiki/LWANNIER90)

## 2. Wannier 拟合与 TB2J 输入

1. 按费米能附近的磁性轨道和杂化选投影与能窗。Wannier 能窗用绝对 eV，逐 k 点核对外窗态数 ≥ `num_wann`、冻结窗态数 ≤ `num_wann`，并检查目标能带覆盖。
2. 依次运行 `wannier90.x -pp wannier90`、`wannier90.x wannier90`。开启 `write_hr=true`、`write_xyz=true`。检查解缠收敛、轨道中心、spinor 配对和同 k 点参考能带。局域化导致成对中心漂移时，可在收敛解缠后用 `num_iter=0`，并用 `check_wannier_bands.py --gauge projected` 验收。
3. 本站 Wannier90 3.1.0 的裸轨道投影按轨道交替 ↑↓，本例用 `--groupby orbital`。按自旋分块时用 `--groupby spin`。本例的 HamiltonIO 0.3.8 会漏读原始 HR 的简并权重和 `_wsvec.dat`。用 `prepare_tb2j_hr.py` 显式写入权重及最短像平移，再验收实际读入的谱。`use_ws_distance=true` 用 `--scheme pair`，并保留 `_wsvec.dat`。关闭时用 `--scheme global`。

```bash
env/bin/python prepare_tb2j_hr.py --seed z/proj/wannier90 \
  --output z/proj/weighted --scheme pair --groupby orbital --vasprun z/band/vasprun.xml
```

输出目录应为新目录。`weighted/` 提供 POSCAR、`.win`、加权 `_hr.dat`、`_centres.xyz` 和验证记录 `hr_preparation.json`。 [Wannier90 参数](https://wannier90.readthedocs.io/en/stable/user_guide/wannier90/parameters/)

## 3. 逐轴积分与合并

本站算例使用 TB2J 0.9.22 和 HamiltonIO 0.3.8。新建环境用 `uv venv --python 3.12 env` 和 `uv pip install --python env/bin/python -r tb2j-requirements.txt`。`run_tb2j.py` 调用 TB2J 的交换接口，并显式传入 CFR 展宽。固定实空间截断 `rcut`，按实际材料检查积分网格、极点数、展宽和替代能窗。二维用奇数 `N×N×1`。积分网格和 VASP/Wannier 源网格分别验收。

以下是 MnInP₂Te₆ 主设置。复制到新算例后，x、y、z 各用本支的 `source.json` 中的费米能和对应加权 HR。按接收者集群的模板适配 PBS 资源和程序入口。积分命令在 PBS 作业内执行，按 [分享包的项目规则示例](../../assets/project/AGENTS.md) 逐步提交。

```bash
set -e
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg
for axis in x y z; do
  ef=$(env/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1]))["fermi_energy_ev"])' "$axis/source.json")
  env/bin/python run_tb2j.py --axis "$axis" --input "$axis/proj/weighted" --output "$axis/n180" \
    --element Mn --groupby orbital --efermi "$ef" --kmesh 35 35 1 --temperature 300 --nz 180 --rcut 24.5 --np 6
done
```

三支全部通过后合并。`--main_path z/n180` 已包含 z 支，命令的位置参数只列 x、y。

```bash
env/bin/TB2J_merge.py x/n180 y/n180 --main_path z/n180 --output_path merged/n180
env/bin/python check_tb2j_exchange.py merged/n180 --branches x/n180 y/n180 z/n180 \
  --triangular-c3 --report merged/n180/validation.json --csv merged/n180/bonds.csv
```

核对三支磁矩、原子及键索引、张量重建秩和回投影残差。反向键的 J 相等、D 反号、对称交换张量互为转置。`--triangular-c3` 用于本例的单 Mn 三角子晶格。 [TB2J 多方向合并](https://tb2j.readthedocs.io/en/latest/src/rotate_and_merge.html)

## 4. 结果与复算参考

逐键参数从 `bonds.csv` 读取，保留 `exchange.out`、`TB2J.pickle`、验收结果和日志。TB2J 用单位自旋、有向键双计数，正 J 偏好平行。下游若每条物理键只计一次，原始 J、D 和对称交换张量均乘 2，并核对 DMI 符号和叉乘顺序。组内新版 LLG 的 `tb2j_bonds` 导入已处理倍数。 [TB2J 哈密顿量约定](https://tb2j.readthedocs.io/en/latest/src/convention.html)

| MnInP₂Te₆ | 实算参考 |
| --- | --- |
| SOC 源输入 | VASP 6.5.1，PBE，PAW Te/Mn_pv/In_d/P，Dudarev Mn Ueff = 1.8736 eV，ENCUT = 600 eV，Γ `9×9×1`，112 条 spinor 能带 |
| Wannier | Mn d、Te p、P p、In s/p，66 个 spinor。外窗 [−7.5, 5.0]，冻结窗 [−7.0, 1.6] eV，`num_iter=0`。近费米能最大插值误差约 1.3 meV |
| [主结果](../Materials/test/tb2j/merged/n180/bonds.csv) | CFR 300 K，`35×35×1`，180 极点，`rcut=24.5 Å`。第一壳平均 J = +0.9175 meV |
| [展宽对照](../Materials/test/tb2j/merged/t150k51/bonds.csv) | CFR 150 K，`51×51×1`，180 极点，同一截断。第一壳平均 J = +0.8695 meV |

300 K、150 K 是积分展宽。两组 DMI 的最大分量差为 0.073 meV，引用时注明展宽。三轴合并还应参考验收中的回投影残差。源网格和零展宽极限仍待验证。

[算例输入与脚本](../Materials/test/tb2j/) · [流程及作业表](../Materials/test/tb2j/workflow.md) · [验收](../Materials/test/tb2j/audit/summary.md) · [历史对照](../Materials/test/tb2j/audit/history.md)
