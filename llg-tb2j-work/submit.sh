#!/bin/bash
# 可从任意目录调用，确保 PBS_O_WORKDIR 是本程序外层目录。
set -euo pipefail
SUBMIT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$SUBMIT_DIR"
exec qsub "$@" wz.pbs
