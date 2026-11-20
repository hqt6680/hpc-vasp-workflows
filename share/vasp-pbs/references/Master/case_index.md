# 其他材料的计算归档

下列路径相对 `<原站点工作根>/Materials`。本页用于查找已计算的分支及原始输入。除表中注明 6.5.1 的分支外，历史 VASP 任务主要用 6.1.0。K₂CrF₄ 详见 [完整算例](K2CrF4.md)。

| 材料或分支 | 已归档 | 调用入口与限制 |
| --- | --- | --- |
| `MnInP2Te6/relax`、`scf/{nosoc,soc}`、`band/{nosoc,soc}` | relax 主动停止，SCF 和能带完成。历史 `relax` 与电子结构分支的 `LDAUTYPE=1` 参数不同。 | [relax/SCF](relax+scf.md)、[能带](band_dos.md)。对照各自 `INCAR/OUTCAR`，重新确认结构和电荷来源。 |
| `MnInP2Te6/scf/new/u` | 单独较大 U 的 SCF 完成，`LDAUTYPE=1`、Mn `U=3.9262 eV`、`J=0.4384 eV`。 | 原 `scf/nosoc` 为 `U=1.9262 eV`、`J=0.4384 eV`。按独立方法保存。 |
| `MnInP2Te6/J/{AFM,FM,ds,neel}`、`J/soc/{xafm,xfm,zafm,zfm}` | 都有正常结束和电子收敛。无 SOC 的 `AFM` 为 4 Mn，其余三支为 9 Mn。SOC 四支为 2 Mn。 | [磁性](magnetism.md)。跨胞先重建同口径键计数和结构。SOC 四支可按同一晶胞与输入复核方向、FM/AFM 能差，检查是否足以分离交换各向异性和单离子项。 |
| `MnInP2Te6/aniso`、`D/{CW,CCW}`、`sp/double/{ac,bc,bcnew}` | 单胞 MAE、四 Mn 手性总能、双 Mn 的 ac/bc 各 19 份输出。历史 `bc` 的实际方向过 90° 后折返，`bcnew` 只见输入。 | [磁性](magnetism.md)、[自旋转角与偶极矩](spin_dipole.md)。 |
| `MnInP2Te6/phonopy` | 90 原子超胞，`IBRION=6`，已有力常数和声子谱。 | [声子](phonopy.md)。后处理已逐字节复核，Γ 附近虚频仍需物理判断。 |
| `MnInP2Te6/TB2J`、`U_test` | TB2J 归档为探索数据；`U_test` 三段 6.5.1 完成，最终 `03_crpa`。 | [磁性](magnetism.md)、[测 U](U_cal.md)。两套 Wannier 的目的、输入和验收条件不同。 |
| `MnInP2Te6/simulation` | 已有 LLG 周期体系温度/磁场/磁电场和开放纳米带温度/电场结果。 | [自旋模拟](spin_simulation.md)。配置目录与 `Master/Simulation` 版本分别记录。 |
| `test/{relax,scf,band}` | MnInP₂Te₆ 自编译 6.5.1 std 实跑 `52043/52045/52184.master`；三步退出 0。 | PBE、`IVDW=11`、Dudarev Mn `Ueff=1.8736 eV`。relax 14 步、最大力 `0.0006 eV/Å`、官方 110 约束。SHA-256 核对 `relax/CONTCAR=scf/POSCAR=band/POSCAR`、`scf/CHGCAR=band/CHGCAR`。 |
| `CoI2/{relax,scf/nosoc,scf/soc}` | `41419–41421.master` 正常结束。PBE、`IVDW=11`、Dudarev Co `Ueff=2.0590 eV`。 | [relax/SCF](relax+scf.md)、[SOC](magnetism.md)。视频中的 CoI₂ DMI 在另一目录，本站该材料归档只验收这三步。 |
| `Cr2WS4/relax`、`J/{FM,CAFM,1}`、`master`、`scf` | `33343.master` relax 和 `33349–33351.master` 磁态测试结束。`master` 是输入模板，`scf` 为空。 | Dudarev Cr `Ueff=2 eV`。`J/1` 与 `FM` 不同初始化后总能仅差约 `1.3×10⁻⁷ eV`。拟合前须核对最终 Cr 磁矩及独立磁构型。 |
| `RuI2/relax` | `34991.master` 达到离子停止条件，归档有 19 步。 | PBE、`IVDW=11`、Dudarev Ru `Ueff=2.1 eV`。后续按 [relax/SCF](relax+scf.md) 验收并续算。 |
| `Si/relax`、`Si/phonopy` | relax `43362.master` 有历史输出，但当前 INCAR 留有其他材料的 `MAGMOM`、DFT+U 与 vdW 设置。`phonopy` 只见 POSCAR/POTCAR。 | 使用干净的 Si 输入，先核对磁性和赝势。此分支没有可验收的 Si 声子结果。 |

同名目录代表历史尝试，实际关系以 POSCAR、POTCAR、CHGCAR、输入参数和输出证据为准。不同 U 方法、磁态或胞大小的能量比较需先建立同一个可拟合模型与能量零点。
