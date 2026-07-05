from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .approval import assessment_hash


REQUIRED_ASSESSMENT_FILES = (
    "1-assessment.json",
    "3-legal-review-report.md",
    "3-legal-review-report.docx",
    "3-claims-review.md",
    "3-evidence-list.md",
    "3-claims-review.xlsx",
    "3-evidence-list.xlsx",
)


def verify_matter(
    matter: dict[str, Any], authorities: list[dict[str, Any]], output_dir: Path
) -> dict[str, Any]:
    assessment = matter["assessment"]
    authority_map = {row["id"]: row for row in authorities}
    errors: list[str] = []
    warnings: list[str] = list(assessment.get("warnings", []))

    for filename in REQUIRED_ASSESSMENT_FILES:
        path = output_dir / filename
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"필수 산출물 없음 또는 비어 있음: {filename}")

    input_pages = {(p["document_id"], p["page"]) for p in assessment["input_documents"]}
    for claim in assessment["claims"]:
        if (claim["document_id"], claim["page"]) not in input_pages:
            errors.append(f"{claim['claim_id']}: 원문 페이지 연결 없음")
        for basis_id in claim["legal_basis_ids"]:
            authority = authority_map.get(basis_id)
            if not authority:
                errors.append(f"{claim['claim_id']}: 규제 DB에 없는 근거 {basis_id}")
            elif authority["jurisdiction"] != "KR":
                errors.append(f"{claim['claim_id']}: 외국 규범이 직접 근거로 연결됨 {basis_id}")
            elif authority["legal_status"] in {"proposal_pending", "superseded"}:
                errors.append(f"{claim['claim_id']}: 직접 근거의 효력 상태 부적절 {basis_id}")
        citations = claim.get("legal_citations", [])
        if not citations:
            errors.append(f"{claim['claim_id']}: 조문 원문 인용 없음")
        for citation in citations:
            if citation["authority_id"] not in claim["legal_basis_ids"]:
                errors.append(f"{claim['claim_id']}: 근거 ID와 조문 인용 불일치")
            if not citation.get("text") or not citation.get("source_sha256") or not citation.get("full_text_sha256") or not citation.get("provision_sha256"):
                errors.append(f"{claim['claim_id']}: 조문 본문 또는 원문·본문·조문 해시 누락")
        if claim["provisional"]:
            warnings.append(f"{claim['claim_id']}: 잠정평가")

    approval_path = output_dir / "attorney-approval.json"
    filing_files = list(output_dir.glob("4-filing-*-draft.md"))
    if filing_files:
        if not approval_path.exists():
            errors.append("제출문서 초안이 있으나 변호사 승인 파일이 없음")
        else:
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            if approval.get("assessment_sha256") != assessment_hash(output_dir / "1-assessment.json"):
                errors.append("변호사 승인 이후 assessment.json 변경")

    unresolved = 0
    for path in output_dir.glob("*.md"):
        try:
            unresolved += path.read_text(encoding="utf-8").count("[확인 필요]")
        except Exception as exc:
            errors.append(f"MD 확인 실패 {path.name}: {exc}")
    if unresolved:
        warnings.append(f"최종 확정 전 해결할 [확인 필요] 표시 {unresolved}건")

    corroboration = assessment.get("corroboration")
    if corroboration:
        for source in corroboration.get("sources", []):
            local_path = Path(source.get("local_path", ""))
            if not local_path.exists():
                errors.append(f"공개자료 스냅숏 없음: {source.get('url')}")
                continue
            digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
            if digest != source.get("sha256"):
                errors.append(f"공개자료 스냅숏 해시 불일치: {source.get('url')}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "matter_id": assessment["matter_id"],
        "claim_count": len(assessment["claims"]),
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "unresolved_count": unresolved,
    }


def write_verification_log(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    json_path = output_dir / "9-verification-log.json"
    md_path = output_dir / "9-verification-log.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 검증 로그",
        "",
        f"- 상태: **{result['status']}**",
        f"- 사건: `{result['matter_id']}`",
        f"- 주장 수: {result['claim_count']}",
        f"- 미해결 표시: {result['unresolved_count']}",
        "",
        "## 오류",
        *(f"- {item}" for item in result["errors"]),
        "",
        "## 경고·확인 필요",
        *(f"- {item}" for item in result["warnings"]),
        "",
        "> PASS는 기계적 무결성 통과를 뜻하며 법률적 최종 승인이나 제출 가능 상태를 뜻하지 않습니다.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
