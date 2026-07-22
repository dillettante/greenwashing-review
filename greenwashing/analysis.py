from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .context import context_warnings, load_context
from .extractors import extract_directory
from .models import Applicability, AssessmentResult, ClaimFinding, EvidenceMatch, RiskBand, SourcePage


ENVIRONMENT_TERMS = re.compile(
    r"친환경|환경친화|지속가능|녹색|그린|탄소|온실가스|넷제로|net[ -]?zero|carbon|climate|"
    r"재활용|재생|순환경제|생분해|퇴비화|무독성|무공해|오염|에너지|태양광|풍력|renewable|"
    r"환경\s*(인증|표지|마크)|eco[- ]?friendly|environmentally friendly|sustainable|recycl|biodegrad|compost|offset|ESG",
    re.I,
)

CLAIM_ASSERTION_TERMS = re.compile(
    r"친환경|환경친화|그린메탈|탄소\s*(중립|감축|저감|상쇄)|넷제로|온실가스.*(감축|저감|감소)|"
    r"재활용.*(사용|생산|확대|향상|인증)|재생에너지.*(사용|전환|확대)|환경.*(개선|최소화|인증)|"
    r"(감축|절감|감소|개선|최소화|달성|획득|인증|전환|확대|구축|생산|분류|집계|목표|계획)(하|되|했|했습|하고|할|한|된|받)|"
    r"\bnet[ -]?zero\b|carbon[ -]?(neutral|free|negative)|100\s*%\s*(재활용|renewable|recycled)",
    re.I,
)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("general_environmental_benefit", re.compile(r"친환경|환경친화|녹색|그린|무공해|eco[- ]?friendly|environmentally friendly|sustainable", re.I)),
    ("carbon_neutral_or_offset", re.compile(r"탄소\s*(중립|상쇄|제로)|넷제로|net[ -]?zero|carbon[ -]?(neutral|positive|offset)|climate[ -]?neutral", re.I)),
    ("future_target", re.compile(r"\b20\d{2}\b.*(목표|달성|전환)|향후.*(목표|감축)|will.*(neutral|reduce|zero)", re.I)),
    ("partial_as_whole", re.compile(r"포장.*친환경|원료.*친환경|일부.*(전체|제품)|packaging.*(green|recycl)|made with.*recycled", re.I)),
    ("comparison_without_baseline", re.compile(r"더\s*(친환경|적은|낮은)|감축|절감|감소|개선|greener|less carbon|reduc", re.I)),
    ("mandatory_as_voluntary", re.compile(r"법정|법적\s*기준|의무.*(준수|감축)|규제.*준수", re.I)),
    ("certification_or_label", re.compile(r"인증|환경표지|에코라벨|certif|eco[ -]?label|seal of approval", re.I)),
    ("recycled_or_recyclable", re.compile(r"재활용|재생원료|재사용|재충전|recycl|refill|reus", re.I)),
    ("degradable_or_compostable", re.compile(r"생분해|분해성|퇴비화|biodegrad|degrad|compost", re.I)),
    ("renewable_energy_or_material", re.compile(r"재생에너지|신재생|태양광|풍력|renewable", re.I)),
    ("absolute_claim", re.compile(r"100\s*%|완전|전혀|유일|최초|최고|항상|모든|zero impact|only|never|all\b", re.I)),
]

WEIGHTS = {
    "misleading_likelihood": 25,
    "substantiation_gap": 20,
    "scope_or_lifecycle": 15,
    "consumer_materiality": 15,
    "absolute_or_broad": 10,
    "comparison_defect": 5,
    "special_aggravator": 5,
    "dissemination_or_remediation": 5,
}

LEGAL_BASE_MAP = {
    "general_environmental_benefit": ["KR-FAIR-LABELING-ACT", "KR-ME-ENV-CLAIMS-NOTICE-2025", "KR-KFTC-ENV-AD-GUIDELINE-2023"],
    "carbon_neutral_or_offset": ["KR-ENV-TECH-ACT", "KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "future_target": ["KR-FAIR-LABELING-ACT", "KR-KFTC-ENV-AD-GUIDELINE-2023"],
    "partial_as_whole": ["KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "comparison_without_baseline": ["KR-FAIR-LABELING-ACT", "KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "mandatory_as_voluntary": ["KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "certification_or_label": ["KR-ENV-TECH-ACT", "KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "recycled_or_recyclable": ["KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "degradable_or_compostable": ["KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "renewable_energy_or_material": ["KR-ME-ENV-CLAIMS-NOTICE-2025"],
    "absolute_claim": ["KR-FAIR-LABELING-ACT", "KR-KFTC-ENV-AD-GUIDELINE-2023"],
}

PATTERN_LABELS = {
    "general_environmental_benefit": "포괄적 환경편익 주장",
    "carbon_neutral_or_offset": "탄소중립·상쇄 주장",
    "future_target": "미래 환경성과 목표",
    "partial_as_whole": "일부 속성의 전체 확대",
    "comparison_without_baseline": "비교기준 불명확",
    "mandatory_as_voluntary": "법정의무의 자발적 성과화",
    "certification_or_label": "인증·환경표지 주장",
    "recycled_or_recyclable": "재활용·재사용 주장",
    "degradable_or_compostable": "분해성·퇴비화 주장",
    "renewable_energy_or_material": "재생에너지·재생원료 주장",
    "absolute_claim": "절대적 표현",
    "environmental_claim_other": "기타 환경 주장",
}


def split_statements(text: str) -> list[str]:
    # PDF의 시각적 줄바꿈을 문장 경계로 취급하면 한 주장이 여러 조각으로 분해된다.
    # 먼저 줄바꿈을 복원한 뒤 실제 종결부호를 기준으로 나눈다.
    normalized = re.sub(r"\s+", " ", text).strip()
    chunks = re.split(r"(?<=[.!?。])\s+|(?<=다\.)|(?<=함\.)|(?<=음\.)", normalized)
    results = []
    for chunk in chunks:
        statement = chunk.strip(" -•\t")
        if not 15 <= len(statement) <= 600:
            continue
        if len(_tokens(statement)) < 4:
            continue
        if sum(statement.count(mark) for mark in ("•", "・", "●")) >= 4:
            continue
        results.append(statement)
    return results


def detect_patterns(statement: str) -> list[str]:
    return [name for name, regex in PATTERNS if regex.search(statement)]


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[가-힣A-Za-z0-9%]+", text)
        if len(token) >= 2 and token.lower() not in {"그리고", "또한", "대한", "위한", "the", "and", "with"}
    }


def match_evidence(statement: str, evidence_pages: list[SourcePage], limit: int = 3) -> list[EvidenceMatch]:
    claim_tokens = _tokens(statement)
    if not claim_tokens:
        return []
    matches: list[EvidenceMatch] = []
    for page in evidence_pages:
        evidence_tokens = _tokens(page.text)
        overlap = claim_tokens & evidence_tokens
        score = len(overlap) / max(1, len(claim_tokens))
        if score >= 0.18:
            excerpt = page.text[:400].replace("\n", " ")
            matches.append(EvidenceMatch(page.document_id, page.filename, page.page, excerpt, round(score, 3), page.source_type))
    return sorted(matches, key=lambda item: item.match_score, reverse=True)[:limit]


def determine_applicability(statement: str, context: dict[str, Any]) -> Applicability:
    medium = str(context.get("medium", "")).lower()
    audience = str(context.get("audience", "")).lower()
    purpose = str(context.get("purpose", "")).lower()
    if purpose in {"mandatory_disclosure", "법정공시"} and not re.search(r"제품|상품|서비스|구매|고객|소비자|product|service|customer", statement, re.I):
        return Applicability.NO
    if any(term in medium for term in ("지속가능", "보고서", "sustainability", "esg")):
        if re.search(r"제품|상품|서비스|매출|판매|구매|고객|소비자|product|service|customer|sales", statement, re.I):
            return Applicability.YES
        return Applicability.UNCERTAIN
    if any(term in medium for term in ("광고", "홍보", "웹", "포장", "advert", "marketing", "website")):
        return Applicability.YES
    if re.search(r"제품|상품|서비스|구매|고객|소비자|product|service|customer", statement, re.I):
        return Applicability.YES
    if "consumer" in audience or "소비자" in audience:
        return Applicability.YES
    return Applicability.UNCERTAIN


def subject_scope(statement: str) -> str:
    if re.search(r"포장|용기|packag", statement, re.I):
        return "포장·용기"
    if re.search(r"원료|소재|material|ingredient", statement, re.I):
        return "원료·소재"
    if re.search(r"제품|상품|product", statement, re.I):
        return "제품"
    if re.search(r"회사|기업|사업|전사|company|business|we\b|our\b", statement, re.I):
        return "기업·사업 전체"
    return "[확인 필요] 주장 대상"


def component_scores(
    statement: str,
    patterns: list[str],
    evidence: list[EvidenceMatch],
    context: dict[str, Any],
) -> dict[str, int]:
    substantiation = [item for item in evidence if item.source_type == "evidence"]
    unsupported = not substantiation
    broad = "general_environmental_benefit" in patterns or "absolute_claim" in patterns
    scores = {
        # 오인가능성은 표현의 포괄성·절대성에서 본다. 단순 실증 부재는 substantiation_gap이 별도로 반영하므로
        # 여기서 다시 가중하지 않는다(모든 미실증 주장을 높음으로 밀어올리던 편향 제거).
        "misleading_likelihood": 3 if broad else 1,
        "substantiation_gap": 4 if unsupported else (2 if substantiation[0].match_score < 0.35 else 1),
        "scope_or_lifecycle": 4 if "partial_as_whole" in patterns else (3 if broad else 1),
        "consumer_materiality": 3 if re.search(r"제품|상품|서비스|구매|product|service", statement, re.I) else 2,
        "absolute_or_broad": 4 if "absolute_claim" in patterns else (3 if "general_environmental_benefit" in patterns else 1),
        "comparison_defect": 4 if "comparison_without_baseline" in patterns and not re.search(r"대비|비교|기준|baseline|compared with|since\s+20\d{2}", statement, re.I) else 0,
        "special_aggravator": 4 if any(p in patterns for p in ("carbon_neutral_or_offset", "certification_or_label", "future_target")) else 0,
        "dissemination_or_remediation": 3 if str(context.get("medium", "")).lower() in {"광고", "웹사이트", "advertisement", "website"} else 2,
    }
    return scores


def weighted_score(scores: dict[str, int]) -> int:
    return round(sum(WEIGHTS[key] * min(4, max(0, value)) / 4 for key, value in scores.items()))


def risk_band(score: int) -> RiskBand:
    if score >= 75:
        return RiskBand.VERY_HIGH
    if score >= 55:
        return RiskBand.HIGH
    if score >= 30:
        return RiskBand.MODERATE
    return RiskBand.LOW


def comparative_notes(patterns: list[str]) -> list[str]:
    notes: list[str] = []
    if "general_environmental_benefit" in patterns:
        notes.append("미국 FTC Green Guides와 EU 2024/825는 포괄적·무조건부 환경주장을 엄격히 다룬다.")
    if "carbon_neutral_or_offset" in patterns:
        notes.append("EU 2024/825는 상쇄에 기초한 제품 단위 탄소중립 표현을 특별히 제한한다.")
    if "comparison_without_baseline" in patterns:
        notes.append("영국 CMA·ASA/CAP는 비교 대상과 기준을 명확히 밝힐 것을 요구한다.")
    if "future_target" in patterns:
        notes.append("EU 2024/825는 검증 가능한 이행계획 없는 미래 환경성과 주장을 문제 삼는다.")
    return notes


def legal_call(score: int, applicability: Applicability, provisional: bool) -> str:
    if applicability is Applicability.NO:
        return "표시·광고 해당성이 낮아 별도 공시·공법상 쟁점으로 분리 검토"
    prefix = "잠정: " if provisional else ""
    if score >= 75:
        return prefix + "부당한 환경성 표시·광고 가능성이 매우 높아 집중 조사 필요"
    if score >= 55:
        return prefix + "부당 표시·광고 가능성이 높아 실증·표현 범위 추가 확인 필요"
    if score >= 30:
        return prefix + "오인 가능성이 있어 한정표현·실증자료 검토 필요"
    return prefix + "현재 자료상 위험이 낮으나 최종 법률검증 필요"


def extract_claims(
    input_pages: list[SourcePage], evidence_pages: list[SourcePage], context: dict[str, Any]
) -> list[ClaimFinding]:
    claims: list[ClaimFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for page in input_pages:
        for statement in split_statements(page.text):
            if not ENVIRONMENT_TERMS.search(statement):
                continue
            if not CLAIM_ASSERTION_TERMS.search(statement):
                continue
            key = (page.document_id, page.page, statement)
            if key in seen:
                continue
            seen.add(key)
            patterns = detect_patterns(statement)
            evidence = match_evidence(statement, evidence_pages)
            applicability = determine_applicability(statement, context)
            scores = component_scores(statement, patterns, evidence, context)
            score = weighted_score(scores)
            substantiation = [item for item in evidence if item.source_type == "evidence"]
            provisional = not substantiation or applicability is Applicability.UNCERTAIN
            legal_ids = sorted({basis for pattern in patterns for basis in LEGAL_BASE_MAP.get(pattern, [])})
            if not legal_ids:
                legal_ids = ["KR-FAIR-LABELING-ACT", "KR-KFTC-ENV-AD-GUIDELINE-2023"]
            missing = []
            if not substantiation:
                missing.append("주장을 직접 뒷받침하는 객관적·과학적 실증자료")
            if "comparison_without_baseline" in patterns:
                missing.append("비교 대상·기준연도·측정방법과 통계적 유의성")
            if "future_target" in patterns:
                missing.append("측정 가능한 중간목표·예산·이행계획·독립 검증")
            claim_hash = hashlib.sha256(f"{page.document_id}:{page.page}:{statement}".encode()).hexdigest()[:10]
            claims.append(
                ClaimFinding(
                    claim_id=f"CLM-{claim_hash}",
                    document_id=page.document_id,
                    filename=page.filename,
                    page=page.page,
                    quote=statement,
                    patterns=patterns or ["environmental_claim_other"],
                    applicability=applicability,
                    subject_scope=subject_scope(statement),
                    evidence=evidence,
                    component_scores=scores,
                    risk_score=score,
                    risk_band=risk_band(score),
                    provisional=provisional,
                    legal_basis_ids=legal_ids,
                    legal_call=legal_call(score, applicability, provisional),
                    missing_evidence=missing,
                    comparative_notes=comparative_notes(patterns),
                )
            )
    return sorted(claims, key=lambda claim: (-claim.risk_score, claim.filename, claim.page))


def select_shortlist(claims: list[ClaimFinding], limit: int = 20) -> list[ClaimFinding]:
    # 기계 트리아지의 출력 중 사람+MCP 정밀평가로 넘길 주장만 추린다.
    # 광고성 '있음'을 우선하고, 그 안에서 위험점수 순. 전량을 세션에 넣지 않기 위한 경계.
    actionable = [c for c in claims if c.applicability is not Applicability.NO]
    ranked = sorted(actionable, key=lambda c: (c.applicability is not Applicability.YES, -c.risk_score))
    return ranked[:limit]


def recommend_routes(claims: list[ClaimFinding], context: dict[str, Any]) -> list[dict[str, str]]:
    actionable = [c for c in claims if c.applicability is not Applicability.NO]
    product_claims = [c for c in actionable if c.subject_scope in {"제품", "포장·용기", "원료·소재"}]
    very_high = [c for c in actionable if c.risk_score >= 75]
    routes = [
        {
            "route": "kftc",
            "recommendation": "검토 필요" if actionable else "실익 낮음",
            "reason": f"표시·광고 해당 가능 주장 {len(actionable)}건. 표시광고법상 소비자 오인성과 실증 여부를 중심으로 검토.",
        },
        {
            "route": "environment",
            "recommendation": "우선 검토" if product_claims else "보충 검토",
            "reason": f"제품·포장·원료 환경성 주장 {len(product_claims)}건. 환경기술 및 환경산업 지원법 적용대상 확인 필요.",
        },
        {
            "route": "criminal",
            "recommendation": "신중 검토" if very_high else "현 단계 실익 낮음",
            "reason": f"매우 높은 위험 주장 {len(very_high)}건. 구성요건·고의·행위자·시효와 행정조사 선행 필요성을 별도 확인.",
        },
    ]
    return routes


def assess_matter(matter_dir: Path, mode: str) -> AssessmentResult:
    if mode not in {"public", "confidential"}:
        raise ValueError("mode는 public 또는 confidential이어야 합니다")
    context = load_context(matter_dir / "context.yaml")
    warnings = context_warnings(context)
    input_pages, input_warnings = extract_directory(matter_dir / "input", "target")
    evidence_pages, evidence_warnings = extract_directory(matter_dir / "evidence", "evidence")
    public_pages, public_warnings = extract_directory(matter_dir / "public-evidence", "public_evidence")
    evidence_pages.extend(public_pages)
    warnings.extend(input_warnings)
    warnings.extend(evidence_warnings)
    warnings.extend(public_warnings)
    if not input_pages:
        raise ValueError("matter/input에 지원되는 검토 대상 파일이 없습니다")
    text_pages = [page for page in input_pages if page.text.strip()]
    if not text_pages:
        raise ValueError("검토 대상에서 텍스트를 추출하지 못했습니다. OCR 상태를 확인하십시오")
    clean_evidence = [p for p in evidence_pages if p.text.strip()]
    # LLM-first: 세션이 통독 추출한 1-claims.json이 있으면 그것이 주장 목록이다(P0-1).
    # CLI는 원문 앵커링(할루시네이션 게이트)만 결정론적으로 수행. 정규식 추출은 폴백.
    from .llm_extraction import llm_claims_to_findings, load_llm_claims
    llm_data = load_llm_claims(matter_dir / "output")
    if llm_data:
        claims, llm_warnings = llm_claims_to_findings(llm_data, text_pages, clean_evidence)
        warnings.extend(llm_warnings)
        claims_source = "llm"
        if not claims:
            raise ValueError("1-claims.json에 유효한 주장이 없습니다")
    else:
        claims = extract_claims(text_pages, clean_evidence, context)
        claims_source = "regex"
        if not claims:
            warnings.append("환경 관련 주장을 탐지하지 못했습니다. 이미지·표에만 존재하는지 사람이 확인해야 합니다.")
    matter_id = str(context.get("matter_id") or matter_dir.name)
    return AssessmentResult(
        matter_id=matter_id,
        context=context,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        input_documents=input_pages,
        evidence_documents=evidence_pages,
        claims=claims,
        route_recommendations=recommend_routes(claims, context),
        warnings=warnings,
        claims_source=claims_source,
    )


def recommend_routes_final(claim_dicts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """정밀평가(②) 결합 후 경로 재계산 — 기계점수가 아니라 **최종** 광고성·위험 기준.

    구 버그: 경로 메모가 기계 분포('매우 높음 2건')를 인용해 최종 분포(0건)와 모순됐다.
    """
    evaluated = [c for c in claim_dicts if c.get("evaluation")]
    actionable = [c for c in evaluated if (c["evaluation"].get("applicability_final") or "불확실") != "없음"]
    product = [c for c in actionable if c.get("subject_scope") in {"제품", "포장·용기", "원료·소재"}]
    very_high = [c for c in actionable if c["evaluation"].get("risk_final") == "매우 높음"]
    high_or_above = [c for c in actionable if c["evaluation"].get("risk_final") in {"매우 높음", "높음"}]
    return [
        {"route": "kftc",
         "recommendation": "검토 필요" if actionable else "실익 낮음",
         "reason": f"정밀평가에서 광고 해당 가능(최종 있음·불확실) {len(actionable)}건, 그중 위험 높음 이상 {len(high_or_above)}건. "
                   "관문 쟁점(광고 해당성) 결론을 전제로 소비자 오인성·실증 여부 중심 검토."},
        {"route": "environment",
         "recommendation": "우선 검토" if product else "보충 검토",
         "reason": f"제품·포장·원료 환경성 주장 {len(product)}건(최종 기준). 환경기술 및 환경산업 지원법 적용대상 확인 필요."},
        {"route": "criminal",
         "recommendation": "신중 검토" if very_high else "현 단계 실익 낮음",
         "reason": f"위험도 '매우 높음' {len(very_high)}건. 고의 입증·행위자 특정이 선행되어야 하며, 실무상 행정조사가 먼저 진행되는 것이 통례입니다."},
    ]
