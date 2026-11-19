# 按配置和任务分开的日志

将新版 run.sh 替换到 nanoribbon.ini、wz.pbs 所在的外层目录即可，不需要重新编译 C++。
原 wz.pbs 已调用 run.sh，因此无需替换你修改过节点、ppn、队列的 PBS 脚本。

```bash
qsub -v RIBBON_CONFIG=scan_A.ini wz.pbs
qsub -v RIBBON_CONFIG=scan_B.ini wz.pbs
```

例如 PBS 返回 12345.server 和 12346.server，对应日志为：

```text
scan_A_master_12345.server.out
scan_B_master_12346.server.out
```

命名规则为 `配置文件名去扩展名_master_完整PBS作业ID.out`。
配置路径只取最后的文件名，空白改为下划线，中文保留。
同一配置重复提交时按不同作业 ID 分开；本地运行使用 `配置名_master_local_时间_进程ID.out`。
日志始终放在 run.sh 同层，不随结果目录 RIBBON_OUTPUT 改变。

本地指定配置也支持：

```bash
bash run.sh --config scan_B.ini
```

命令行最后一个 --config 覆盖 RIBBON_CONFIG，日志前缀跟随实际配置。
INI 内容仍由 C++ 启动时读取一次；本次替换不改变参数优先关系或计算方法。
旧 master.out 保留，新启动的任务使用新名称；同一 PBS 作业 ID 重启会追加到其原日志。
