#!/bin/bash
# 本地与 PBS 共用入口：日志按配置文件名前缀和作业 ID 分开，保存在本脚本目录。
set -euo pipefail
RUN_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$RUN_DIR"
ACTIVE_CONFIG="${RIBBON_CONFIG:-nanoribbon.ini}"
# 与 C++ 的配置选择一致：命令行中最后一个 --config 覆盖 RIBBON_CONFIG。
# 此处只确定文件名，不提前读取 INI 内容；参数仍由 C++ 启动时读取一次。
EXPECT_CONFIG=0
for config_arg in "$@"; do
    if [[ $EXPECT_CONFIG == 1 ]]; then
        ACTIVE_CONFIG="$config_arg"
        EXPECT_CONFIG=0
    elif [[ $config_arg == --config ]]; then
        EXPECT_CONFIG=1
    fi
done
CONFIG_NAME=${ACTIVE_CONFIG##*/}
CONFIG_PREFIX=${CONFIG_NAME%.*}
CONFIG_PREFIX=${CONFIG_PREFIX//[[:cntrl:]]/_}
CONFIG_PREFIX=${CONFIG_PREFIX// /_}
CONFIG_PREFIX=${CONFIG_PREFIX//\\/_}
CONFIG_PREFIX=${CONFIG_PREFIX:-nanoribbon}
# PBS 保留完整作业 ID（包括服务器/数组后缀）；本地用时间和进程 ID 区分每次启动。
JOB_TAG="${PBS_JOBID:-local_$(date +%Y%m%d_%H%M%S)_$$}"
JOB_TAG=${JOB_TAG//[[:cntrl:]]/_}
JOB_TAG=${JOB_TAG// /_}
JOB_TAG=${JOB_TAG//\//_}
JOB_TAG=${JOB_TAG//\\/_}
LOG_FILE="$RUN_DIR/${CONFIG_PREFIX}_master_${JOB_TAG}.out"
exec >> "$LOG_FILE" 2>&1
log_job_exit() {
    local job_exit_status=$?
    printf '[Run] End: %s; job: %s; exit status: %s\n' \
        "$(date -Is)" "${PBS_JOBID:-local}" "$job_exit_status"
}
trap log_job_exit EXIT
printf '[Run] Start: %s; job: %s; host: %s; directory: %s\n' \
    "$(date -Is)" "${PBS_JOBID:-local}" "${HOSTNAME:-unknown}" "$RUN_DIR"

# cpu_threads=0 在 PBS 下由 C++ 读取 ppn；非零配置/命令行仍然生效。
if [[ -n ${PBS_NODEFILE:-} ]]; then
    NP=$(wc -l < "$PBS_NODEFILE")
    NODE_COUNT=$(sort -u "$PBS_NODEFILE" | wc -l)
    if [[ "$NODE_COUNT" -ne 1 ]]; then
        printf '[PBS] This executable needs one CPU node; allocated nodes: %s\n' "$NODE_COUNT" >&2
        exit 1
    fi
    export OMP_NUM_THREADS="$NP"
    printf '[PBS] Allocated CPU slots: %s\n' "$NP"
fi
export OMP_DYNAMIC=FALSE OMP_PROC_BIND=spread OMP_PLACES=cores
export MPLBACKEND=Agg OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
if [[ -x "$HOME/anaconda3/envs/python3.7/bin/python" ]]; then
    export SPIN_PLOT_PYTHON="$HOME/anaconda3/envs/python3.7/bin/python"
fi
export MPLCONFIGDIR="${MPLCONFIGDIR:-${TMPDIR:-/tmp}/mninp2te6-ribbon-mpl-${PBS_JOBID:-$$}}"
mkdir -p -- "$MPLCONFIGDIR"

EXECUTABLE="$RUN_DIR/program/nanoribbon_cpu"
NEEDS_BUILD=0
if [[ ! -x "$EXECUTABLE" ]]; then
    NEEDS_BUILD=1
else
    for source in "$RUN_DIR"/program/*.cpp "$RUN_DIR"/program/*.hpp "$RUN_DIR/build.sh"; do
        if [[ "$source" -nt "$EXECUTABLE" ]]; then
            NEEDS_BUILD=1
            break
        fi
    done
fi
if [[ ${BUILD_ON_NODE:-0} == 1 ]]; then
    BUILD_NATIVE=1 bash "$RUN_DIR/build.sh"
elif [[ "$NEEDS_BUILD" == 1 ]]; then
    bash "$RUN_DIR/build.sh"
fi

RUN_ARGS=(--config "$ACTIVE_CONFIG")
# 环境覆盖转为命令行，优先于 INI；本脚本末尾显式参数继续从左到右覆盖。
if [[ -n ${RIBBON_ENGINE:-} ]]; then
    RUN_ARGS+=(--engine "$RIBBON_ENGINE")
fi
if [[ -n ${RIBBON_THREADS:-} ]]; then
    RUN_ARGS+=(--threads "$RIBBON_THREADS")
fi
if [[ -n ${RIBBON_OUTPUT:-} ]]; then
    RUN_ARGS+=(--output "$RIBBON_OUTPUT")
fi
printf '[Run] Config: %s; executable: %s; log: %s\n' "$ACTIVE_CONFIG" "$EXECUTABLE" "$LOG_FILE"
"$EXECUTABLE" "${RUN_ARGS[@]}" "$@"
