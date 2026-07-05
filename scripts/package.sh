#!/usr/bin/env bash
# 배포용 클린 zip 생성. 기밀(matters/)·임시·캐시는 제외한다.
# 사용: scripts/package.sh [스탬프]   (스탬프 예: 20260705, 미지정 시 dist)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="${1:-dist}"
OUT="${TMPDIR:-/tmp}/greenwashing-counsel-${STAMP}.zip"
cd "$ROOT"
rm -f "$OUT"
zip -rq "$OUT" . \
  -x '*/__pycache__/*' -x '*.pyc' -x '.DS_Store' -x '*/.DS_Store' \
  -x 'matters/*' -x 'tmp/*' -x 'node_modules' -x 'node_modules/*' \
  -x '.git/*' -x '.gw/snapshots/*'
echo "생성: $OUT"
echo "포함: greenwashing/·corpus/·.gw/state.sqlite3·docs·skills/·tests/"
echo "제외: matters/(기밀 사건)·tmp/·__pycache__·node_modules"
