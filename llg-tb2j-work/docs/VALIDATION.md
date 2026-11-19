# Simulation 模板验证

2026-11-13 在 zjt 的独立副本编译和验证 `Master/Simulation`。GCC 4.8.5、Python 3.7.13、NumPy 1.21.6、Matplotlib 3.5.3。记录位于 `hqt/.codex_reports/vasp_audits/master_library_20261113/simulation-check/`。

| 命令 | 观察到的结果 |
| --- | --- |
| `bash build.sh` | C++/OpenMP 编译成功，生成 `program/nanoribbon_cpu`。 |
| `python validation/validate_deployment.py` | 独立工作目录、真实小规模 LLG/MC、LLG 图片、PBS spool 模拟、输出参数覆盖及构建失败恢复通过。 |
| `python validation/validate_layout.py` | 40 个计算引擎、场类别、边界与输出目录用例通过，兼容旧 TXT/NPY 缓存。 |
| `python validation/validate_logs.py` | 并发任务日志、配置、路径和 PBS 数组 ID 通过。 |

此处 PBS 用脚本环境和替身命令模拟。材料实际生产结果和物理收敛条件见 [自旋模拟入口](../../spin_simulation.md)。
