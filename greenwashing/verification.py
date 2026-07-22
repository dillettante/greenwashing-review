from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .approval import assessment_hash


REQUIRED_ASSESSMENT_FILES = (
    "1-assessment.json",
    # 납품 3종(같은 내용·형식만 다름) + 작업용 워크북. 구 3-claims-review.md·
    # 3-evidence-list.md는 xlsx와 중복이라 폐지했다.
    "3-legal-review-report.md",
    "3-legal-review-report.docx",
    "3-legal-review-report.html",
    "3-claims-review.xlsx",
    "3-evidence-list.xlsx",
)

# P2-8 판정↔위험 결정표: (verification.verdict, 광고성 최종) → 허용 risk_final 집합.
# 자의적 등급을 막는다. 예: '반증'인데 '중간'은 근거 없이 낮춘 것 → 경고.
VERDICT_RISK_FLOOR = {"반증": "높음", "불일치": "높음", "과장": "중간", "부합": "낮음", "미확인": "낮음"}
RISK_ORDER = {"낮음": 0, "중간": 1, "높음": 2, "매우 높음": 3}
MAX_PRECEDENT_REUSE = 3  # 같은 심결례를 이 건수 초과 주장에 인용하면 템플릿 반죽 경고


def _evaluation_quality_warnings(claims: list[dict[str, Any]]) -> list[str]:
    """P2-7·8: 정밀평가의 최소 품질을 기계적으로 점검한다(내용 판단이 아니라 절차 이행 여부).

    ① 위험 높음 이상인데 웹검증(verification) 없음 → 근거 없는 상향
    ② 판정과 risk_final의 부정합(반증인데 중간 등)
    ③ 동일 심결례를 여러 주장에 복붙(차별화 실패 — 영풍 1차의 핵심 결함)
    """
    warnings: list[str] = []
    evaluated = [c for c in claims if c.get("evaluation")]
    if not evaluated:
        return warnings

    precedent_use: dict[str, list[str]] = {}
    for claim in evaluated:
        ev = claim["evaluation"]
        cid = claim["claim_id"]
        risk = ev.get("risk_final")
        verdict = (ev.get("verification") or {}).get("verdict")

        if risk in {"높음", "매우 높음"} and not ev.get("verification"):
            warnings.append(f"{cid}: 위험 '{risk}'인데 실증·검증(웹) 결과가 없음 — 근거 보강 필요")
        if not ev.get("precedents"):
            warnings.append(f"{cid}: 참조 심결례 없음 — corpus search-decisions로 유사 사건 확인 필요")
        if verdict and risk:
            floor = VERDICT_RISK_FLOOR.get(verdict)
            if floor and RISK_ORDER.get(risk, 0) < RISK_ORDER[floor]:
                warnings.append(
                    f"{cid}: 판정 '{verdict}'인데 위험 '{risk}' — 통상 '{floor}' 이상이어야 함(하향 사유를 assessment에 명시)")
        for prec in ev.get("precedents") or []:
            cite = str(prec.get("cite", "")).strip()
            if cite:
                precedent_use.setdefault(cite, []).append(cid)

    for cite, users in precedent_use.items():
        if len(users) > MAX_PRECEDENT_REUSE:
            warnings.append(
                f"심결례 '{cite[:40]}'가 {len(users)}건 주장에 반복 인용됨(기준 {MAX_PRECEDENT_REUSE}건) "
                "— 주장별 차별 검색 필요")
    return warnings


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

    warnings.extend(_evaluation_quality_warnings(assessment["claims"]))

    # LLM 추출 모드: 인용 원문 앵커가 깨진 주장은 인용 금지 대상 → 오류로 승격
    for claim in assessment["claims"]:
        if (claim.get("anchor") or {}).get("status") == "not_found":
            errors.append(f"{claim['claim_id']}: 인용 원문이 PDF에서 확인되지 않음(할루시네이션 게이트)")

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


def write_verification_log(result: dict[str, Any], output_dir: Path) -> Path:
    """검증 결과를 JSON으로 남긴다(구 .md 사본은 폐지 — verify가 콘솔에 같은 내용을 출력한다)."""
    json_path = output_dir / "9-verification-log.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path
