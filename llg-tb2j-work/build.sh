#!/bin/bash
# Linux 离线编译：使用集群已有的 C++/OpenMP 编译器，不下载任何依赖。
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PROGRAM_DIR="$PWD/program"
CXX="${CXX:-g++}"
if ! command -v "$CXX" >/dev/null 2>&1; then
    printf 'C++ compiler not found: %s. Load the cluster compiler module first.\n' "$CXX" >&2
    exit 1
fi
flags=(-O3 -std=c++11 -fopenmp -ffp-contract=off -Wall -Wextra -pedantic)
# 保持双精度和严格浮点语义，不使用 -ffast-math。
# 仅在实际运行的计算节点编译时启用本机指令集优化。
if [[ ${BUILD_NATIVE:-0} == 1 ]]; then
    flags+=(-march=native)
fi
# 独立临时文件编译成功后再替换程序，已有运行进程继续使用其原可执行文件。
TEMP_BINARY=$(mktemp "$PROGRAM_DIR/.nanoribbon_cpu.XXXXXX")
trap 'rm -f -- "$TEMP_BINARY"' EXIT
"$CXX" --version | sed -n '1p'
"$CXX" "${flags[@]}" "$PROGRAM_DIR/nanoribbon.cpp" -o "$TEMP_BINARY"
chmod 755 "$TEMP_BINARY"
mv -f -- "$TEMP_BINARY" "$PROGRAM_DIR/nanoribbon_cpu"
trap - EXIT
printf 'Built: %s/nanoribbon_cpu\n' "$PROGRAM_DIR"
