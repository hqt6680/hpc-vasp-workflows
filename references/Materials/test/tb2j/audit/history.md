# MnInP₂Te₆ TB2J 历史对照

历史目录为 `Materials/MnInP2Te6/TB2J/TB2J_results`。历史 TB2J 0.9.0.1 的 Mn1 磁矩约 4.3285 μB，偏离 Cartesian +z 约 0.0131°。当前 z 分支使用 TB2J 0.9.22，Mn1 约 4.459 μB，偏角约 0.0019°。

按有向键 `(R, Mn1, Mn1)` 的整数位移精确匹配。Cartesian 键向量为 `R @ cell + r_j - r_i`，从 i 指向 j。两套晶格矢量同向，c 均为 20 Å，面内 a 分别为 7.02246896 Å（历史）和 7.02958685 Å（当前）。Mn1 的分数坐标一致。两组当前 z 设置各匹配 42 条有向键，旧结果另有 38 条。CSV 保留每条匹配键的新旧距离和带符号数值。能量单位均为 meV，沿用 TB2J 的单位自旋和有向键约定。旧 z 支路的横向响应支持 `Dx`、`Dy` 和 `Jani` 的 xy 子块。比较合并结果时，优先用 `Jiso I + Jani` 的 xy 对称块判断对称交换差异，合并后的迹标准化会改变 `Jiso` 和 `Jani` 的拆分。

## 历史数值互证

旧 `exchange.out` 第一壳的 6 条有向键，其 `J_iso:` 明细均比上方键行大 1.0000 meV。以 `R=(-1,0,0)` 为例，键行 0.7056、明细 1.7056、pickle 0.705630712、Multibinit 0.705631 meV。历史对照取 pickle 数值。Multibinit 导出与 pickle 的最大绝对差分别为 4.83×10⁻⁷ meV（Jiso）、4.78×10⁻⁷ meV（DMI）和 4.90×10⁻⁶ meV（Jani）。每条不一致的历史明细和两种导出值均列在 JSON 中。

| 当前 z 设置 | Jiso 最大差 | Dxy 最大分量差 | Jani xy 最大分量差 | (Jiso I + Jani) xy 最大分量差 |
| --- | ---: | ---: | ---: | ---: |
| n180，300 K，35×35×1 | 0.225033 | 0.363875 | 0.330507 | 0.514806 |
| t150k51，150 K，51×51×1 | 0.272990 | 0.355800 | 0.343634 | 0.466672 |

对于 `R=(1,0,0)`，`z/t150k51` 的 Jiso 为 0.825446 meV，历史为 0.705631 meV。Dx 分别为 −0.460762、−0.630078 meV。

两套电子结构条件不同。历史 VASP 6.1.0 的 OUTCAR 记录 Liechtenstein `LDAUTYPE=1`，并将 Mn 的 U/J 显示为 1.9/0.4 eV。当前 VASP 6.5.1 采用 Dudarev `LDAUTYPE=2`、Mn Ueff 1.8736 eV。当前 Wannier 模型为含 In s/p 的 66 spinors，采用已收敛的 disentanglement 和 `num_iter=0` 投影规范。历史目录现存 58-spinor Wannier 文件不含 In s/p，日志记录 disentanglement 达到迭代上限。其文件时间晚于历史交换 pickle，旧 TB2J 积分网格、费米能、数值展宽及当时实际读取的 Wannier Hamiltonian 仍未确认。因此以上差异只量化两套归档结果的差别，无法归因于单个参数。

## 复算比较

进入 `Materials/test/tb2j`，使用本站算例的 TB2J 环境。

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
env/bin/python compare_tb2j_history.py z/n180 \
  --json audit/history_z_n180.json --csv audit/history_z_n180.csv
env/bin/python compare_tb2j_history.py merged/n180 --z-reference z/n180 \
  --json audit/history_merged_n180.json --csv audit/history_merged_n180.csv
```

将标签替换为 `t150k51` 可比较 150 K 设置。合并结果须已通过三轴合并验收，`--z-reference` 指向相同积分设置的 z 分支。

## 三轴合并结果对照

按同一有向键得到 42 条匹配。两组 `merged` 结果采用与各自 z 支路相同的网格和展宽。以下为全键最大绝对分量差，单位 meV。

| 当前合并设置 | Jiso | Dxy | Jani xy 块 | (Jiso I + Jani) xy 块 |
| --- | ---: | ---: | ---: | ---: |
| n180 | 0.254843 | 0.359970 | 0.315536 | 0.524004 |
| t150k51 | 0.344557 | 0.352192 | 0.317011 | 0.477159 |

[n180 逐键对照](history_merged_n180.csv) · [t150k51 逐键对照](history_merged_t150k51.csv)
