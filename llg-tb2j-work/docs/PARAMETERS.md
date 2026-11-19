# 参数分组与生效优先关系

编辑外层 `nanoribbon.ini`，无需重新编译。它是 `键 = 值` 的纯文本配置，`#` 后为注释；
九个分组由注释划分，不要添加 `[section]`。参数名区分大小写，布尔值写 `true/false` 或 `1/0`。
所有数字都必须可解析且有限；拼错的参数名会报错。

## 1. 设置来源：从低到高

```text
C++ 内置默认值 < --config 指定的配置文件 < 命令行覆盖
```

默认读取当前工作目录的 `nanoribbon.ini`。多次出现 `--config` 时，只加载最后指定的文件。
配置中重复的键按文件顺序后者覆盖前者；命令行也按从左到右覆盖，不受 `--config` 出现位置影响。
初态命令行选项另有互斥规则，见第 4 节。

例如配置里 `engine=llg`、`cpu_threads=8`，执行：

```bash
./program/nanoribbon_cpu --config nanoribbon.ini --engine mc --threads 4 --temperature 10 --field 1
```

实际使用 MC、4 线程、固定 10 K、固定 1 T。`--temperature` 同时设置温度起止值并将点数设为 1；
`--field`、`--electric` 同理。若后面再出现 `--temperature-sweep 20 5 4`，最终采用这 4 个温度点。
实际参数在启动日志和结果目录的 `run_settings.ini` 中记录。

## 2. engine 决定哪些参数参与计算

| 分组 / 参数 | LLG | MC |
| --- | --- | --- |
| 材料、Nx/Ny、边界、初态、seed、线程、缓存与输出 | 使用 | 使用 |
| temperature_*、field_* | 使用；T >= 0 | 使用；T > 0 |
| electric_*、Kxy_meV、Kxz_meV | 使用磁电耦合 | 沿用原 MC：不使用电场耦合 |
| damping、dt_fs、relaxation_ps、llg_steps、llg_kernel、thermal_noise | 使用 | 不参与采样 |
| equilibration_sweeps、measurement_sweeps、proposal_sigma | 不参与积分 | 使用 |

MC 在命令行覆盖完后将 `electric_start/electric_end` 统一设为 0，`electric_count` 设为 1；
非零电场请求会在启动日志中说明，因此不会重复计算不同 Ez 下相同的 MC。
`thermal_noise=false` 只关闭 LLG 热场，不能关闭 MC 接受概率中的温度。
不生效分组的数字仍须语法正确；其算法专用的物理范围检查仅在选中该算法时执行。

LLG 电场项还要求 `Kxy_meV` 或 `Kxz_meV` 非零。默认两者均为零，保持原材料参数，
此时改变 Ez 不会改变动力学。电场取值与单位约定沿用项目原程序，磁场为 z 方向、单位 T。
三个外场都是空间均匀值，扫描改变整片晶格的场值。

## 3. 每个场点的计算量

LLG 步数的优先关系为：

```text
命令行 --steps N > 配置 llg_steps（>0）> relaxation_ps 与 dt_fs 自动换算
```

`llg_steps=0` 表示自动换算：`nearbyint(relaxation_ps*1000/dt_fs)`，最少 1 步。
默认 `50 ps / 0.1 fs = 500000` 步/点。显式步数只替代步数预算；
积分步长仍是 `dt_fs`，实际物理时间为 `步数*dt_fs/1000 ps`。
即使显式给步数，仍须 `dt_fs>0`、`relaxation_ps>=0`、`damping>=0`。
`--steps` 必须 >=1；配置 `llg_steps` 可为 0；实际步数最多 10^12。

MC 每点轮数为 `equilibration_sweeps + measurement_sweeps`，
一轮 sweep 包含 Nx*Ny 次自旋更新尝试。平衡轮数 >=0，测量轮数 >=1，各自最多 10^9；
`proposal_sigma>0`。默认 5000 轮平衡、10 轮测量、提议幅度 60，与原 MC 相同。
接受率只统计测量阶段，输出能量、磁化和 Q 是最终构型的瞬时量，并非测量阶段平均值。
MC 不赋予 sweeps 以 LLG 物理时间，`--steps` 在 MC 下会报错，避免误用。

## 4. 缓存、初态和扫描传递的优先关系

程序启动时会读取并校验所选初态，包括构型文件尺寸。随后每个场点按以下规则运行：

1. `reuse_states=true` 且有匹配的完整场点 TXT/NPY：直接读入该构型，本点不重新积分/采样。
2. 没有完整缓存：使用当前扫描状态运行完整的每点预算。第一点从配置初态开始，后续点沿用扫描前态。
3. `reuse_states=false` 或 `--no-reuse`：跳过缓存查找，每点都计算；初态选择规则保持如下。

初态选择由高到低：

| 优先级 | 条件 | 实际初态 |
| --- | --- | --- |
| 高 | 命令行 `--random` / `--skyrmion` / `--uniform` / `--ground-state FILE` / `--initial-state VALUE` | 指定初态，并关闭配置的 read_ground_state |
| 中 | 没有初态命令行覆盖，且 `read_ground_state=true` | ground_state_file |
| 低 | `read_ground_state=false` | initial_state |

上述初态命令行选项互斥，多次指定也会报错。`--no-reuse` 不等于随机重启；
要从随机态重新计算，应同时使用 `--random --no-reuse`。
`skyrmion_radius_sites`、`skyrmion_wall_sites` 仅在最终选择 skyrmion 初态时起作用，均须 >0。
seed 控制随机初态和采样；读取构型时不会用 seed 覆盖文件。

`ground_state_file=auto` 查找当前材料、engine、长宽和边界对应的温度场最终文件：

```text
全周期：result/材料/engine/temperature/Nx..._Ny..._Xperiodic_Yperiodic/final_state.txt
有开放边界：result/材料/engine/band/temperature/Nx..._Ny..._X..._Y.../final_state.txt
```

这里 `result` 可由 output_dir 改变。跨 LLG/MC 或跨输出根目录读取时，直接指定实际构型路径。
新路径缺失时兼容读取上一版 temperature 目录下带完整尺寸/边界前缀的最终文件；不回退到旧通用别名。
`read_ground_state=true` 时初态文件必须存在，即使后续场点可复用缓存；缺失会在启动校验时报错。

缓存只匹配当前 output_dir 下同材料、engine、Nx/Ny、x/y 边界和精确 T/B/Ez 的完整点；
TXT 优先于同名 NPY。单温与多温的对应分类可互查，如 magnetic 和 temperature_magnetic。
所有新尺寸目录优先，之后再检查上一版扁平目录中带长宽/边界/场分类前缀的场点文件。
旧结果只读，不自动搬迁；summary 的相对 snapshot 路径会指向实际读取的旧文件。
`final_state.txt`、带尺寸的最终文件、checkpoint 均不被自动视为某个完整场点缓存。
模型系数、步数和 seed 不进入缓存文件名，改动这些设置后请换 output_dir 或关闭复用。
缓存损坏会报错。复用不会覆盖原场点数据，summary 中 status=reused_state、steps=0；
MC 复用点的 acceptance 留空，不推算历史接受率。原缓存缺 PNG 时可用重绘脚本补图。

普通扫描和 MC 按 T → B → Ez 的嵌套顺序运行，保留输入方向；MC 实际仅 T/B。
LLG 同时设置非零磁场和电场时，沿用原程序的独立分支逻辑：

1. 每个温度先按 B 升序读入或补算 Ez=0 的纯磁场基底。
2. 每个 B 回到自己的纯磁场基底，按 Ez 升序读入或补算电场点；不同 B 的电场分支不串接。
3. 下一温度接收上一个温度纯磁场阶段的末态。

## 5. 长宽、边界和目录

Nx/Ny 均至少为 3，代表格点数，并非 nm。六角晶格坐标为
`x/a=i+0.5*(j%2)`、`y/a=j*sqrt(3)/2`。
`boundary_x`、`boundary_y` 分别设置 `open` 或 `periodic`，`closed` 为 open 的兼容别名。
旧参数 `boundary` 会同时赋值两个方向；和独立参数混用时按出现顺序赋值。
CLI `--boundary-x/y` 最后覆盖配置。y 周期要求 Ny 为偶数，x 周期允许奇数 Nx。

开放方向不做坐标取模，越界近邻标为 -1，并跳过跨边界的三壳层相互作用；
边缘自旋仍参加 LLG/MC 更新。周期方向按该方向尺寸取模。Q 积分也遵守相同边界。

```text
两方向周期：output_dir/材料名/llg或mc/场分类/Nx{长}_Ny{宽}_Xperiodic_Yperiodic/
任一方向开放：output_dir/材料名/llg或mc/band/场分类/Nx{长}_Ny{宽}_X{边界}_Y{边界}/
```

场分类是 `temperature`、`magnetic`、`electric`、`magnetic_electric`，
以及温度扫描与外场的组合 `temperature_magnetic`、`temperature_electric`、`temperature_magnetic_electric`。
零磁电场时，即使只有一个温度点也归入 temperature；固定温度加磁场归 magnetic。
整组磁场/电场只要包含非零值就参与分类，组内零场点仍留在该组目录。
目录已包含尺寸/边界/场分类，场点文件仅命名为 `T_{温度}K_B_{磁场}T_Ez_{电场}.txt/.png`。

`summary.csv`、`trace.csv`、`run_settings.ini`、`checkpoint` 和 final_state 均放在尺寸/边界目录。
同分类不同尺寸/边界的运行记录相互隔离；同时运行相同分类、尺寸和边界时仍须区分 output_dir。

## 6. 线程、PBS 与路径

线程数先按 `--threads/--cpu-threads` 覆盖配置 `cpu_threads`。
最终值 >0 时使用该值；为 0 时优先取 PBS_NODEFILE 的单节点槽位数，本地则用 OpenMP 默认值
（可由 OMP_NUM_THREADS 设置）。PBS 分配是硬上限，请求超出分配或分到多节点会报错。
程序是单节点 OpenMP 程序，不使用 mpirun。

`wz.pbs` 中的覆盖关系：

| PBS 环境变量 | 用途 |
| --- | --- |
| RIBBON_CONFIG | 选择配置文件，默认 nanoribbon.ini |
| RIBBON_ENGINE | 转为 --engine，覆盖配置方法 |
| RIBBON_THREADS | 转为 --threads，覆盖配置线程数，仍受 ppn 限制 |
| RIBBON_OUTPUT | 转为 --output，覆盖输出根目录 |
| BUILD_ON_NODE=1 | 在计算节点重新编译并使用本机 CPU 优化 |
| RIBBON_HOME | PBS 入口定位外层目录；通常由 PBS_O_WORKDIR 定位，无需设置 |

PBS 默认不强制用 ppn 覆盖非零 cpu_threads；cpu_threads=0 时自动使用 ppn。
run.sh 先切换到自身所在目录，默认读取同层 INI；程序位于 program/nanoribbon_cpu，默认输出到同层 result/。
主日志保存在 run.sh 同层，以实际配置文件名去扩展名为前缀：配置名_master_完整PBS作业ID.out。
本地运行改用 local_时间_进程ID；选择配置时最后一个 --config 优先于 RIBBON_CONFIG。
日志路径与 output_dir/RIBBON_OUTPUT 的自定义值分开设置。
submit.sh 从自身目录提交 wz.pbs，因此 PBS_O_WORKDIR 与外层目录一致；直接 qsub 时应先进入该目录。
配置中的输出/构型/绘图脚本相对路径以配置文件所在目录为起点；
命令行路径和 RIBBON_OUTPUT 以作业工作目录为起点。配置中的 `~/` 路径会展开。
绘图解释器按 `--python` > 配置中明确的解释器 > SPIN_PLOT_PYTHON > PATH 选择；
仅配置值为 python/python3 时才使用 SPIN_PLOT_PYTHON。解释器参数应为可执行文件名或路径，勿附加启动参数。

write_png=false 时不调用 Python。关闭 save_text 仍保留启动初态和检查点，
但不输出每点的持久构型及最终文件，因而不能用这些点做后续缓存或准确重绘。
每点计算结束保存构型/图像；检查点和日志在 LLG 的 64 步或 MC 的 32 轮批次边界响应。
checkpoint 仅保存构型及当前场条件；重新读取会按新预算计算，不恢复随机数和扫描进度。
