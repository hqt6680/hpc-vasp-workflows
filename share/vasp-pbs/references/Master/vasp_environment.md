# VASP 与 PBS 环境示例

用自己的 SSH 别名登录，核对 `id -un`、`hostname`、`pwd -P` 后阅读项目和站点规则。以下版本、构建特性及资源配置记录原站点实测条件。接收者按实际集群配置调整程序路径、MPI 和 PBS 请求。

| 任务 | 原站点的 VASP 入口 | PBS 模板 |
| --- | --- | --- |
| 共线结构优化、SCF、能带、DOS、通常的无 SOC 声子 | `vasp6.5-wannier`（std） | `software/vasp-6.5.1/examples/std.pbs` |
| SOC、非共线、需要复现 ncl 的历史算例 | `vasp6.5so-wannier`（ncl） | `software/vasp-6.5.1/examples/ncl.pbs` |

两个原站点入口都是 VASP 6.5.1，均链接串行 Wannier90 3.1.0，整个 VASP 仍用 MPI。入口名字只表示编译能力。Wannier90 按对应 `ALGO` 或 `LWANNIER90*` 标签调用，SOC 由 `LSORBIT` 启用。原站点构建包含 HDF5 1.14.6、本地 `OPTCELL` 兼容层和 WANPROJ 并行写入补丁，未合入 VTST。接收者按本机或集群的编译记录核对这些特性。

## 提交

从包内复制 [std](../software/vasp-6.5.1/examples/std.pbs) 或 [ncl](../software/vasp-6.5.1/examples/ncl.pbs) 模板，填写实际程序和 MPI 启动器的绝对路径，按需配置 `VASP_ENV_FILE`。在独立算例目录准备 `INCAR/POSCAR/POTCAR/KPOINTS`，文本用 UTF-8/LF。按计算类型选择模板，先编辑 `#PBS -N`、CPU 数和 walltime。下面演示 std，SOC 或非共线改用 `ncl.pbs`。

```bash
cp -n /path/to/vasp-pbs/references/software/vasp-6.5.1/examples/std.pbs run.pbs
bash -n run.pbs
/opt/pbs/bin/qstat -Q workq
```

模板从 `PBS_NODEFILE` 取 MPI 数与主机，使用接收者配置的环境和 MPI 启动器。原站点加载自编译环境并使用 Intel MPI 2021.11。若站点的 MPI 不接受 `-machinefile`，将启动行改为本站命令。示例固定 `OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`。DFT+U 保持单线程，见 VASP 已知问题 #71。`NCORE`、`KPAR` 应与实际 rank 布局匹配，电子结构示例的 28 ranks、`NCORE=4` 只是已用组合。节点按本次资源选取。cRPA 的内存和 rank 见 [测 U](U_cal.md)。[VASP Known issues](https://vasp.at/wiki/Known_issues) · [NCORE](https://vasp.at/wiki/NCORE)

**大节点预留。** 常规作业提交前用 `/opt/pbs/bin/pbsnodes -aS` 查看规格，再用 `/opt/pbs/bin/pbsnodes NODE` 核对 `jobs` 和 `resources_assigned`，将 PBS 模板改为明确的小节点。`free` 状态也可能已有作业。PBS 作业名用简短的计算名，例如 `scf`、`socx`、`tb2j`。 多阶段算例等前置计算验收后再提交下一步，避免预提交整条依赖链。同一算例并行占用最多两个小节点。确认小节点内存不足等资源限制后再考虑大内存节点，提交前及排队期间确认仍有至少一台大内存节点留给师兄。2026-11-13 的 PBS 配置中 `node01` 和 `master` 均约 502 GiB，实际使用以本站分配和当时占用为准。

## 预检与验收

```bash
HQT=/path/to/your/workspace
PY=/path/to/python3
AICC="$HQT/.auto-computational-chemist/tools/vasp/scripts"
"$PY" "$AICC/check_inputs.py" .
```

- 核对 POSCAR 元素顺序、POTCAR 的 `TITEL`、泛函、`ENCUT`、k 网格、磁矩与 U 数组。赝势原文件留在服务器。非共线时按本站指南手工复核 `MAGMOM` 为 `3×原子数`，通用检查器按标量计数。二维限晶格等方法相关警告结合具体输入判断。
- 检查通过后用 `/opt/pbs/bin/qsub run.pbs` 并记录返回 ID。用 `/opt/pbs/bin/qstat -f JOB_ID` 查看状态。若作业已离队，结合模板日志、`OUTCAR` 和输出文件判断结果。
- 普通 relax/SCF 用 `"$PY" "$AICC/parse_vasp.py" .`，再按对应教程验收物理量。固定电荷能带、声子、Wannier/cRPA 使用各自的验收项。`--dry-run` 只检输入和启动，`exit code=0` 只表示程序正常退出。
- 每次记录实际 VASP 版本/入口、job ID、工作目录、MPI 数、输入来源、结果文件和收敛状态。记录材料专用参数与单胞归一化。出错保留原目录，在新目录续算或重跑。

对应视频 [01 安装软件](https://www.bilibili.com/video/BV1yTHS6TE3y/)；本站入口和版本以本页及安装目录为准。
