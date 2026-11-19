# C++ / OpenMP 自旋模拟最终版：LLG、MC 与独立边界

将整个 `server_nanoribbon_cpp` 文件夹上传到 Linux 集群即可使用。
`nanoribbon.ini` 用 `engine = llg` 或 `engine = mc` 切换方法，分为九组并附中文注释。
两种方法共用矩形晶格和 x/y 独立边界，支持有限纳米带、单方向周期以及两方向全周期。
LLG 保留已有温度、磁场、电场扫描和磁电独立分支逻辑；MC 沿用原项目的温度/磁场 Metropolis 算法。
核心计算与统计均为 C++，仅绘图调用已有 Python 3.7+、NumPy、Matplotlib，无需 Numba/CUDA 或联网安装。

完整参数作用与优先关系见 [PARAMETERS.md](docs/PARAMETERS.md)，验证记录见 [VALIDATION.md](docs/VALIDATION.md)。

## 文件组织

```text
server_nanoribbon_cpp/
├── program/                  # C++ 源码、头文件和编译后的可执行文件
│   ├── nanoribbon.cpp
│   ├── *.hpp
│   └── nanoribbon_cpu         # bash build.sh 后生成
├── nanoribbon.ini             # 参数设置
├── build.sh                   # 编译
├── run.sh                     # 统一运行入口，按配置名和作业 ID 分开日志
├── wz.pbs                     # PBS 作业脚本
├── submit.sh                  # 可从任意目录调用的提交入口
├── render_snapshot.py         # 保存单张图片
├── replot_existing.py         # 批量重绘历史构型
├── plot_results.py            # 兼容旧补图命令
├── docs/                      # 参数、输出及验证说明
├── validation/                # 开发验证脚本，不参与生产计算
├── result/                    # 结果根目录，与 INI/脚本同层
└── 配置名_master_作业ID.out    # 运行后生成，与脚本同层
```

主日志按配置文件名（去掉扩展名）和完整 PBS 作业 ID 分开，例如 `scan_B_master_12345.server.out`。
同一配置重复提交也会因作业 ID 不同而分开。本地运行使用时间和进程 ID。
查看实时进度：`tail -f scan_B_master_12345.server.out`；规则和替换方法见 [LOG_FILES.md](docs/LOG_FILES.md)。
直接执行 C++ 可执行文件时输出到终端；使用 run.sh 或 wz.pbs 时写入各自的任务日志。
默认 result/ 相对外层 nanoribbon.ini 解析，内部仍按材料、engine、band、场类型、尺寸/边界分类。

## 编译与提交

```bash
cd /你的服务器路径/server_nanoribbon_cpp
bash build.sh
./program/nanoribbon_cpu --config nanoribbon.ini --dry-run
qsub wz.pbs
```

直接 qsub 时请先进入 wz.pbs 所在目录。也可以从任意目录调用：

```bash
bash /你的服务器路径/server_nanoribbon_cpp/submit.sh
bash /你的服务器路径/server_nanoribbon_cpp/submit.sh -v RIBBON_ENGINE=mc,RIBBON_OUTPUT=result_mc
```

本地或交互节点运行同样使用外层入口：

```bash
bash run.sh --dry-run
bash run.sh --engine mc --length 32 --width 16 --temperature 10 --field 1 --equilibration-sweeps 10 --measurement-sweeps 5
```

run.sh 总是切换到自身所在目录；submit.sh 在该目录调用 qsub，使 PBS_O_WORKDIR 与脚本目录一致。
除非主动更改 output_dir/RIBBON_OUTPUT，默认结果均写到外层 result/。
从其他目录提供自定义 INI 时，INI 内相对路径仍以该 INI 的目录为基准。

使用 C++11 / OpenMP 编译器，如 GCC 4.8 及以上；默认 `g++`，可用 CXX 指定。
保留双精度，不使用 `-ffast-math`。若服务器需要加载编译器模块，先按现有集群方式加载。
修改 INI 不必重编译，源码或头文件更新后 PBS 会重新编译。

`wz.pbs` 参考项目最新的 `server_cpp/wz.pbs`，保留 node10、ppn=28、workq、单节点单进程和 OpenMP 绑核设置，
作业名为 SPIN_RIBBON；按实际资源修改其顶部的节点、ppn 和队列。
程序标准输出和错误通过 run.sh 实时写入外层的独立任务日志；每次运行记录配置、作业 ID、开始/结束及退出码。
默认尊重配置的 cpu_threads，0 自动使用 PBS ppn；不会强制覆盖为 28。
有 `~/anaconda3/envs/python3.7/bin/python` 时优先供默认绘图配置使用。

可复制 INI 在同一目录保存不同任务配置：

```bash
qsub -v RIBBON_CONFIG=scan_B.ini,RIBBON_OUTPUT=results_scan_B wz.pbs
qsub -v RIBBON_ENGINE=mc,RIBBON_THREADS=14,RIBBON_OUTPUT=results_mc wz.pbs
```

环境覆盖会转为命令行，优先于 INI。同一目录的不同作业使用不同日志文件；相同分类/尺寸/边界的并发任务仍须区分结果目录。
程序只用单节点共享内存；不使用 mpirun，也不申请多个节点。
已在登录节点编译时可直接提交；需要在计算节点针对其 CPU 重新编译时用 `qsub -v BUILD_ON_NODE=1 wz.pbs`。

## 设置方法、长宽和边界

```ini
engine = llg
Nx = 256
Ny = 64
boundary_x = open
boundary_y = open
```

Nx 为 x 格点数，Ny 为 y 行数，均 >=3。坐标延续原三角晶格：
`x/a=i+0.5*(j%2)`、`y/a=j*sqrt(3)/2`。输入尺寸单位为格点数；实际 y 格点中心跨度为 `(Ny-1)*sqrt(3)*a/2`。
两边界独立选 open/periodic，closed 是 open 的兼容别名。
y 周期时 Ny 必须为偶数，保证错位晶格连接互反；x 周期允许奇数 Nx。

| 边界设置 | 几何 |
| --- | --- |
| x=open，y=open | 四边自由开放的有限纳米带，默认 |
| x=periodic，y=open | 长度方向首尾连接、宽度方向自由 |
| x=open，y=periodic | 长度方向自由、宽度方向首尾连接 |
| x=periodic，y=periodic | 全周期矩形；Nx=Ny 时对应原方形全周期模拟 |

“封闭”按前面约定表示没有跨边界连接的自由边界。实现时先生成原三壳层的候选近邻：
周期方向把坐标映射为 `(坐标%尺寸+尺寸)%尺寸`；开放方向不取模。
仍越界的近邻记为 -1，计算交换、DMI、交换各向异性和电场耦合时跳过该键。
边缘自旋照常更新，受实际存在的近邻、局部各向异性、磁场及 LLG 热场作用，不固定边缘。
拓扑荷的三角形积分也按方向连接或截断，开放边界下 Q 不要求为整数。
MC 根据包含三壳层作用的实际邻接图分组，只并行更新互不耦合的格点，避免跨周期边界的更新冲突。

## 算法和默认参数

| 参数 | 默认值 |
| --- | --- |
| 材料 / 晶格常数 / 磁矩 | MnInP2Te6 / 1 Å / 4.2 μB |
| J1 / J2 / J3 | 1.71 / -0.11 / -0.09 meV |
| lambda / K | 0 / -0.5125 meV，单离子能量 -K*Sz² |
| DMI | Bloch，D=0.63 meV；也支持 Neel |
| Kxy / Kxz | 0 / 0 meV |
| LLG | 阻尼 0.5，dt=0.1 fs，每点 50 ps，即 500000 步 |
| MC | 平衡 5000 sweeps，测量 10 sweeps，proposal_sigma=60 |
| 温度扫描 | 200 → 0.1 K，共 50 点 |
| 磁场 / 电场 | 0 / 0 |

LLG 使用原有归一化随机 Heun 法，预测/校正阶段共用同一步热场；
有效场、能量、热噪声单位和原 C++ 实现保持一致，保留 optimized/reference 两种内核。
MC 使用原来的归一化高斯提议与 Metropolis 接受概率，一轮每格点尝试一次，
只在测量轮统计接受率。输出能量、磁化与 Q 为最终构型瞬时值。
MC 温度必须 >0；电场和 LLG 时间/阻尼/热噪声开关不参与 MC，日志会说明被忽略的电场请求。
LLG 支持 T=0。默认 Kxy=Kxz=0 时电场不改变动力学；产生电场响应须按材料数据设置非零耦合。

切换到 MC 只需更改：

```ini
engine = mc
```

需要不同采样量时修改第 7 组的 equilibration_sweeps、measurement_sweeps、proposal_sigma。
两种方法使用同一温度/磁场配置；MC 的实际 Ez 归零、点数归一。
同 seed 在固定编译环境和线程数下可重复；跨语言或更改线程数不保证随机轨迹逐位一致。

## 初态、扫场和先读后算

初态支持 random、skyrmion、uniform 和 TXT/NPY 路径。
skyrmion 为背景 +z、核心 -z 的中心种子，半径/畴壁宽由配置控制，Bloch/Neel 跟随 DMI 类型；
演化中不固定核心，种子是否稳定取决于物理参数。
`read_ground_state=true` 时用 ground_state_file 覆盖 initial_state；
auto 指向当前 engine/边界分支内温度场尺寸目录的 final_state.txt，详细路径见 docs/PARAMETERS.md。
初态命令行选项优先于此开关，且彼此互斥。

TXT 为 Nx*Ny 行、Sx/Sy/Sz 三列，按 site=i*Ny+j 展开。
NPY 支持 `(Nx,Ny,3)` 或 `(Nx*Ny,3)`，C/Fortran 排列、大小端、f32/f64。
读入后归一化；尺寸不匹配、NaN/Inf 或零向量会报错。
纯三列 TXT 不含原始长宽，总行数相同时须自行确认它与当前 Nx/Ny 一致。

温度、磁场、电场设置起止值与点数：固定值取相同起止、count=1；扫描取多个点。
默认 reuse_states=true，每个完整 T/B/Ez 场点先查同材料、engine、尺寸和边界的 TXT/NPY，存在就读，缺失才计算。
单温/多温对应分类互查，纯磁场结果可以直接用于后续 LLG 磁电联合扫描。
只查完整场点，不把 final_state 或 checkpoint 当作该点缓存；复用不覆盖原场点数据。
修改材料系数或每点预算后如需重新计算，用另一 output_dir 或 `--no-reuse`。

普通扫描/MC 按输入方向连续演化。LLG 磁电联合扫描按原逻辑：
每个温度先按 B 升序准备全部 Ez=0 磁场基底，再分别回到各 B 自己的基底按 Ez 升序扫电场。
每个点依然先读后算，不同 B 的电场分支不串接；下一温度接收纯磁场阶段的末态。

```bash
bash run.sh --temperature 0.1 --field-sweep 0 6 61
bash run.sh --temperature 0.1 --field-sweep 0 6 61 --electric-sweep 0 1 11
bash run.sh --engine mc --temperature 10 --field-sweep 0 6 61
```

参数总体优先级为内置默认 < INI < CLI；LLG 每点步数为 --steps > 非零 llg_steps > relaxation_ps/dt_fs。
MC 使用平衡+测量轮数，不能用 --steps。路径、PBS、缓存和初态的具体优先关系见 docs/PARAMETERS.md。

## 输出目录与文件

默认 output_dir=result，分类延续原项目命名：

```text
全周期：result/材料名/llg或mc/场分类/Nx{长}_Ny{宽}_Xperiodic_Yperiodic/
有开放边界：result/材料名/llg或mc/band/场分类/Nx{长}_Ny{宽}_X{边界}_Y{边界}/
```

上述展示可选分类，并非每次都会创建。温度扫描叠加磁场/电场时分类为 temperature_magnetic、
temperature_electric、temperature_magnetic_electric；固定温度加磁场归 magnetic，零磁电场归 temperature。
每种方法、每种场类型均在分类后加入尺寸目录，边界一并写在目录名中以避免同尺寸不同边界混用。
构型和图片只按 T/B/Ez 命名，不重复尺寸、边界或场分类。例如：

```text
result/MnInP2Te6/llg/band/magnetic_electric/Nx256_Ny64_Xperiodic_Yopen/
    T_0.1K_B_1T_Ez_0.2.txt
    T_0.1K_B_1T_Ez_0.2.png
    run_settings.ini
    initial_state.txt
    summary.csv
    trace.csv
    checkpoint.txt
    checkpoint.info
    final_state.txt
```

summary 记录条件、迭代量、能量/每自旋能量、磁化、Q、最大力矩及构型路径。
unit 区分 steps/sweeps，phase 区分磁场基底和电场分支；
status=reused_state、steps=0 表示复用，MC 新算点额外记录测量接受率 acceptance。
浮点条件使用可往返双精度的标签，避免按少数小数位舍入后覆盖不同场点。
运行记录保存在各尺寸与边界目录，仅相同分类、相同尺寸/边界的再次运行会更新它们。
同时运行相同分类/尺寸/边界的作业需用不同 output_dir。
新目录优先查缓存，也兼容上一版分类目录下带长宽前缀的 TXT/NPY；旧文件只读，不自动移动。
auto 初态优先读新尺寸目录的 final_state.txt，缺失时回退同尺寸/边界的旧版温度场最终文件。

PNG 与原 `spin_simulation.py` 相同：全部格点彩色箭头表示 Sx/Sy，箭头颜色表示 Sz，
bwr 固定 [-1,1]，原箭头参数、scale=30、150 dpi。矩形调整画布与坐标范围，保持实际晶格比例。

默认每 30 秒记录进度，每 300 秒保存中间构型，点结束更新检查点。
SIGTERM/SIGINT 在 LLG 最多 64 步、MC 最多 32 轮的批次边界响应；中断点不保存为完整场点。
checkpoint 可作为 --ground-state 初态使用，但不保存随机数/全扫描状态，不是精确续算恢复。

## 小规模试跑与历史构型重绘

以下只检查编译与工作流，不代表充分弛豫：

```bash
bash run.sh --length 64 --width 32 --skyrmion --radius 6 --wall 1.5 --temperature 0.1 --field 1 --threads 4 --steps 100 --output smoke_llg
bash run.sh --engine mc --length 32 --width 16 --temperature 10 --field 1 --threads 4 --equilibration-sweeps 10 --measurement-sweeps 5 --output smoke_mc
```

生产计算关闭 write_png 时完全不依赖 Python。保留 TXT/NPY 后可批量补图，无需重算 LLG/MC：

```bash
python replot_existing.py result --dry-run
python replot_existing.py result
python replot_existing.py result --in-place
```

默认另存 result/replotted，保留层级和原图；--in-place 原地替换同名图，原始自旋数据不变。
支持新旧 C++/Python 结果，自动读 CSV、配置和文件名；缺少尺寸时须明确提供，详见 [REPLOT.md](docs/REPLOT.md)。
仅有 PNG 无法恢复自旋构型。完整选项用 `./program/nanoribbon_cpu --help` 查看。

这是完整整理版，已包含尺寸分类功能，不需要另打旧版补丁。输出结构见 [OUTPUT_LAYOUT.md](docs/OUTPUT_LAYOUT.md)。
# TB2J 逐键导入

在 LLG 配置里设置 `tb2j_bonds = bonds.csv`，同时把 `lattice_constant_angstrom` 改为计算结构的面内晶格常数。INI 内的路径相对于该 INI。也可使用 `--tb2j-bonds FILE.csv`，命令行路径相对于当前工作目录。

读取 `check_tb2j_exchange.py` 生成的原始有向键 CSV。本模式适用于单磁性子晶格、二维三角晶格，要求 TB2J 的面内原胞矢量分别沿 Cartesian +x 和逆时针 120°。程序核对键长和反向键，并把每条键的 J、DMI 和对称交换张量乘 2，以匹配本程序的每键一次能量约定。CSV 覆盖 `J1/J2/J3`、`lambda` 和标量 DMI，单离子 `K_meV`、磁场及原程序的电场项仍独立生效。MC 使用原参数模式。

导入模式使用通用 LLG 内核，输出放在 `llg/tb2j/` 子树，关闭自动构型复用。换 CSV 时使用独立输出目录。运行后用 `python plot_spin_texture.py FINAL_STATE --output PREFIX` 输出面内自旋及 Sz 图。

