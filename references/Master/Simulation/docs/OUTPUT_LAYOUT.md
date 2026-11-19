# 完整目录版的程序与结果位置

C++ 源码、头文件和编译后可执行文件统一放在 program/；INI、运行/提交/编译脚本和绘图脚本放在外层。
run.sh 与 wz.pbs 将程序标准输出和错误实时写入外层 配置名_master_作业ID.out，默认结果根目录为外层 result/。

```text
全周期：result/材料/llg或mc/场分类/Nx{长}_Ny{宽}_Xperiodic_Yperiodic/
有开放边界：result/材料/llg或mc/band/场分类/Nx{长}_Ny{宽}_X{边界}_Y{边界}/
```

temperature、magnetic、electric 和各组合分类均采用这一结构，LLG/MC 的规则相同。
尺寸目录保留 x/y 边界，避免同尺寸不同边界混用。场点数据和图片仅按场值命名：

```text
result/MnInP2Te6/llg/band/magnetic_electric/Nx256_Ny64_Xperiodic_Yopen/
    T_0.1K_B_1T_Ez_0.2.txt
    T_0.1K_B_1T_Ez_0.2.png
    summary.csv
    trace.csv
    run_settings.ini
    initial_state.txt
    checkpoint.txt
    checkpoint.info
    final_state.txt
```

同分类、尺寸和边界的运行记录会更新；不同作业的主日志按配置名和作业 ID 分开。
同一配置重复提交仍各有日志；同一作业 ID 重启则在其原日志内追加。
result/ 是默认值；主动修改 output_dir 或 RIBBON_OUTPUT 时按指定路径保存。

程序先查尺寸目录内缓存，再查同一输出根目录下上一版扁平场分类目录内带完整尺寸/边界前缀的构型。
旧数据只读，不自动移动，summary 记录实际来源。
如已有历史 results/，可将 output_dir 保持为 results，以继续使用它。
ground_state_file=auto 优先查温度场尺寸目录中的 final_state.txt，缺失时回退到同尺寸/边界的旧版最终文件。
