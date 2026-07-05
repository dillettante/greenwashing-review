from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


def assessment_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_approval(output_dir: Path, reviewer: str, scope: str = "all") -> Path:
    assessment_path = output_dir / "1-assessment.json"
    if not assessment_path.exists():
        raise ValueError("assessment.json이 없습니다. 먼저 gw assess를 실행하십시오")
    approval = {
        "reviewer": reviewer,
        "approved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": scope,
        "assessment_sha256": assessment_hash(assessment_path),
        "statement": "평가 결과를 검토했으며 선택한 범위의 제출문서 초안 생성을 승인함",
    }
    path = output_dir / "attorney-approval.json"
    path.write_text(json.dumps(approval, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def require_approval(output_dir: Path, route: str) -> dict:
    approval_path = output_dir / "attorney-approval.json"
    assessment_path = output_dir / "1-assessment.json"
    if not approval_path.exists():
        raise PermissionError("변호사 승인 게이트: gw approve <matter-id> --reviewer <이름>을 먼저 실행하십시오")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("assessment_sha256") != assessment_hash(assessment_path):
        raise PermissionError("승인 후 평가 결과가 변경되었습니다. 재검토·재승인이 필요합니다")
    scope = approval.get("scope", "all")
    if scope not in {"all", route}:
        raise PermissionError(f"승인 범위({scope})에 {route}가 포함되지 않습니다")
    return approval

