#!/bin/zsh
set -eu

# 스크립트 위치 기준으로 프로젝트 루트를 자동 산출한다(경로 하드코딩 없음).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${GW_PYTHON:-python3}"
CADENCE="${1:-weekly}"

mkdir -p "$ROOT/.gw/logs"
cd "$ROOT"
"$PYTHON" -m greenwashing corpus monitor --cadence "$CADENCE"
