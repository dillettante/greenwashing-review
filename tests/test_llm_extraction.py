"""LLM-first 추출·앵커링 검증 — 인용 실재(할루시네이션 게이트)가 핵심."""
from greenwashing.llm_extraction import anchor_quote, llm_claims_to_findings
from greenwashing.models import SourcePage


PAGES = {
    5: "이러한 노력의 결과, 영풍 사업장 인근 지점에서\n최근 수년간 1~2급수 수준의 수질을 유지하고 있으며, 낙동강 일대에서 생태계 회복의 징후가 관찰되고 있습니다.",
    37: "주요 중금속 항목은 최근 수년간 전 항목에서 검출한계 미만 수준으로 유지되고 있습니다.",
}


def test_anchor_exact_page():
    r = anchor_quote("최근 수년간 1~2급수 수준의 수질을 유지", PAGES, 5)
    assert r == {"status": "anchored", "page": 5}


def test_anchor_whitespace_insensitive():
    # PDF 추출 텍스트의 임의 줄바꿈·공백과 무관하게 매칭돼야 한다
    r = anchor_quote("사업장 인근 지점에서 최근 수년간 1~2급수", PAGES, 5)
    assert r["status"] == "anchored"


def test_anchor_ellipsis_fragments():
    r = anchor_quote("1~2급수 수준의 수질을 유지 … 생태계 회복의 징후", PAGES, 5)
    assert r["status"] == "anchored"


def test_anchor_page_corrected():
    r = anchor_quote("검출한계 미만 수준으로 유지", PAGES, 36)  # 실제는 37쪽
    assert r == {"status": "page_corrected", "page": 37}


def test_anchor_hallucination_caught():
    r = anchor_quote("폐수를 완전히 정화하여 식수 수준으로 방류", PAGES, 5)
    assert r["status"] == "not_found"


def test_findings_conversion_and_warnings():
    pages = [SourcePage("doc1", "report.pdf", n, t, "x", "target") for n, t in PAGES.items()]
    data = {"claims": [
        {"claim_id": "YP-p05-water", "page": 5, "quote": "1~2급수 수준의 수질을 유지",
         "narrative_axis": "수질 서사", "why_flagged": "확정 처분과 상충"},
        {"claim_id": "YP-fake", "page": 5, "quote": "존재하지 않는 인용문입니다 절대로"},
    ]}
    findings, warnings = llm_claims_to_findings(data, pages, [])
    assert len(findings) == 2
    ok = next(f for f in findings if f.claim_id == "YP-p05-water")
    assert ok.anchor["status"] == "anchored" and ok.narrative_axis == "수질 서사"
    bad = next(f for f in findings if f.claim_id == "YP-fake")
    assert bad.anchor["status"] == "not_found"
    assert any("YP-fake" in w for w in warnings)  # 경고로 표면화(조용히 통과 금지)
    assert ok.legal_basis_ids  # 기본 직접근거 세트 보장(조문 인용 게이트 통과용)
