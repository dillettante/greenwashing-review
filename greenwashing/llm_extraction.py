"""LLM-first 주장 추출 지원 — 세션이 쓴 1-claims.json을 파이프라인 주장으로 변환 + 원문 앵커링.

설계 원칙(P0-1): **추출도 판단처럼 LLM이 한다.** 정규식은 환경 어휘가 없는 위험 문장
("1~2급수 수질 유지")을 놓치고 목차·거버넌스 보일러플레이트를 올린다(영풍 실측).
세션이 보고서 전문을 통독해 주장을 추출하고, CLI는 딱 하나 — **추출문이 실제 PDF 그 쪽에
존재하는지**(할루시네이션 앵커)를 결정론적으로 검증한다.

1-claims.json 스키마(세션 작성):
{
  "matter_id": "...", "extracted_by": "...", "extracted_at": "YYYY-MM-DD",
  "claims": [
    {"claim_id": "YP-p05-water",         # 세션 부여(안정적 슬러그 권장)
     "page": 5, "quote": "…원문 인용(중략은 … 허용)…",
     "subject_scope": "사업장 환경성과",  # 선택
     "claim_types": ["포괄적 환경편익 주장"],  # 선택, PATTERN_LABELS 값 또는 자유 라벨
     "why_flagged": "사법확정 오염과 상충",   # 선택, 트리아지 근거
     "narrative_axis": "수질 서사",           # 선택, ② narratives 축 힌트
     "legal_basis_ids": ["KR-FAIR-LABELING-ACT"]}  # 선택, 미지정 시 기본 4법령
  ]
}
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import Applicability, ClaimFinding, RiskBand, SourcePage

# 기본 직접근거 세트 — 세션이 legal_basis_ids를 안 주면 4개 규범 전부를 붙여 조문 인용을 보장
DEFAULT_LEGAL_BASIS = [
    "KR-FAIR-LABELING-ACT", "KR-ENV-TECH-ACT",
    "KR-ME-ENV-CLAIMS-NOTICE-2025", "KR-KFTC-ENV-AD-GUIDELINE-2023",
]


def load_llm_claims(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / "1-claims.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("claims"), list):
        raise ValueError("1-claims.json: claims는 리스트여야 합니다")
    return data


def _norm(text: str) -> str:
    # PDF 추출 텍스트는 공백·줄바꿈이 임의라 전부 제거하고 비교한다
    return re.sub(r"[\s ]+", "", text)


def anchor_quote(quote: str, pages: dict[int, str], claimed_page: int) -> dict[str, Any]:
    """인용문이 실제 그 쪽에 있는지 검증. 중략(…/...)은 조각별 검사. ±1쪽 보정 허용."""
    fragments = [f for f in re.split(r"…|\.\.\.|\[중략\]", quote) if _norm(f)]
    if not fragments:
        return {"status": "not_found", "page": claimed_page}

    def page_has_all(page_no: int) -> bool:
        text = _norm(pages.get(page_no, ""))
        return bool(text) and all(_norm(f) in text for f in fragments)

    if page_has_all(claimed_page):
        return {"status": "anchored", "page": claimed_page}
    for near in (claimed_page - 1, claimed_page + 1):
        if page_has_all(near):
            return {"status": "page_corrected", "page": near}
    # 전 페이지 탐색(쪽 번호 오류 구제) — 조각 전부가 한 쪽에 있어야 인정
    for page_no in sorted(pages):
        if page_has_all(page_no):
            return {"status": "page_corrected", "page": page_no}
    return {"status": "not_found", "page": claimed_page}


def llm_claims_to_findings(
    data: dict[str, Any], input_pages: list[SourcePage], evidence_pages: list[SourcePage],
) -> tuple[list[ClaimFinding], list[str]]:
    """세션 추출 주장 → ClaimFinding. 앵커 실패는 주장 폐기가 아니라 경고로 남긴다(사람 확인)."""
    from .analysis import match_evidence  # 순환 import 회피(analysis가 이 모듈을 부름)

    pages_by_doc: dict[str, dict[int, str]] = {}
    doc_meta: dict[str, SourcePage] = {}
    for page in input_pages:
        pages_by_doc.setdefault(page.document_id, {})[page.page] = page.text
        doc_meta.setdefault(page.document_id, page)

    findings: list[ClaimFinding] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    for raw in data["claims"]:
        claim_id = str(raw.get("claim_id") or "").strip()
        quote = str(raw.get("quote") or "").strip()
        page_no = int(raw.get("page") or 0)
        if not claim_id or not quote or not page_no:
            warnings.append(f"1-claims.json 항목 무시(claim_id/quote/page 필수): {raw.get('claim_id')}")
            continue
        if claim_id in seen_ids:
            warnings.append(f"중복 claim_id 무시: {claim_id}")
            continue
        seen_ids.add(claim_id)

        # 다문서 입력이면 앵커가 잡히는 문서를 채택, 단일 문서면 그 문서
        anchor, doc_id = {"status": "not_found", "page": page_no}, next(iter(pages_by_doc), "")
        for candidate_doc, pages in pages_by_doc.items():
            result = anchor_quote(quote, pages, page_no)
            if result["status"] != "not_found":
                anchor, doc_id = result, candidate_doc
                break
        if anchor["status"] == "not_found":
            warnings.append(f"{claim_id}: 인용 원문을 {page_no}쪽에서 확인 못함 — 인용 재확인 필요(할루시네이션 게이트)")
        elif anchor["status"] == "page_corrected":
            warnings.append(f"{claim_id}: 인용은 실재하나 쪽 번호 보정 {page_no}→{anchor['page']}")

        meta = doc_meta.get(doc_id)
        legal_ids = list(raw.get("legal_basis_ids") or DEFAULT_LEGAL_BASIS)
        findings.append(ClaimFinding(
            claim_id=claim_id,
            document_id=doc_id,
            filename=meta.filename if meta else "[확인 필요]",
            page=int(anchor["page"]),
            quote=quote,
            patterns=list(raw.get("claim_types") or ["environmental_claim_other"]),
            applicability=Applicability.UNCERTAIN,  # 최종은 ② evaluation·gateway가 정한다
            subject_scope=str(raw.get("subject_scope") or "[확인 필요] 주장 대상"),
            evidence=match_evidence(quote, evidence_pages),
            risk_score=0, risk_band=RiskBand.MODERATE, provisional=True,
            legal_basis_ids=legal_ids,
            legal_call="세션 추출(LLM) — 법적 평가는 ② evaluation에서",
            anchor=anchor,
            why_flagged=str(raw.get("why_flagged") or ""),
            narrative_axis=str(raw.get("narrative_axis") or ""),
        ))
    return findings, warnings
