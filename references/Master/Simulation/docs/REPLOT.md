# 已计算构型批量重绘

将 `replot_existing.py` 和新版 `render_snapshot.py` 放在同一目录。
使用已有 Python 3.7、NumPy、Matplotlib 即可，无需 C++ 可执行文件，也不会运行 LLG/MC。

递归扫描整个结果目录，新图另存到该目录下的 `replotted/`：

```bash
python replot_existing.py /你的结果目录
```

把已有同名 PNG 直接替换为新规范：

```bash
python replot_existing.py /你的结果目录 --in-place
```

指定输出目录，或先检查转换计划：

```bash
python replot_existing.py /你的结果目录 --output-dir /新版图片目录
python replot_existing.py /你的结果目录 --dry-run
```

在原集群环境中，可将上面的 `python` 换成 `~/anaconda3/envs/python3.7/bin/python`。

脚本自动读取结果 CSV、运行配置和新旧文件名，识别 Nx/Ny、engine、温度、磁场和电场。
支持 `result/材料/engine/[band/]场分类/尺寸与边界/` 及旧目录层级。
新场点文件只含 T/B/Ez 时，从尺寸目录读取 Nx/Ny 和 x/y 边界，从上层识别 LLG/MC。
原始 TXT/NPY 保持不变。新图采用原 LLG Python 程序的彩色箭头，色标固定 [-1,1]，默认 150 dpi。
目录中新图已存在时默认跳过；用 `--overwrite` 可覆盖另存目录中的图。
转换清单为 `replot_manifest.csv`；单文件失败会记录错误，并继续其余构型。

若历史数据没有尺寸或场值，可直接补充：

```bash
python replot_existing.py /你的结果目录 --length 256 --width 64 --temperature 0.1 --field 1 --electric 0
```

这些命令行参数会覆盖自动识别值，只应对相同条件的数据使用。
三列 TXT 无法仅按总行数区分 128×128 和 256×64；缺少尺寸时须指定正确长宽。
需要原始自旋 TXT/NPY 才能准确重绘；只有旧 PNG 时无法恢复完整的自旋数据。
