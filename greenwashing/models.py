from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class SourceStatus(StrEnum):
    PRIMARY_VERIFIED = "primary_verified"
    GOOD_LAW_VERIFIED = "good_law_verified"
    NEEDS_UPDATE = "needs_update"
    SUPERSEDED = "superseded"
    PROPOSAL_PENDING = "proposal_pending"


class Applicability(StrEnum):
    YES = "있음"
    NO = "없음"
    UNCERTAIN = "불확실"


class RiskBand(StrEnum):
    LOW = "낮음"
    MODERATE = "중간"
    HIGH = "높음"
    VERY_HIGH = "매우 높음"


@dataclass(slots=True)
class SourcePage:
    document_id: str
    filename: str
    page: int
    text: str
    sha256: str
    source_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceMatch:
    evidence_id: str
    filename: str
    page: int
    excerpt: str
    match_score: float
    source_type: str = "evidence"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ClaimFinding:
    claim_id: str
    document_id: str
    filename: str
    page: int
    quote: str
    patterns: list[str]
    applicability: Applicability
    subject_scope: str
    evidence: list[EvidenceMatch] = field(default_factory=list)
    component_scores: dict[str, int] = field(default_factory=dict)
    risk_score: int = 0
    risk_band: RiskBand = RiskBand.LOW
    provisional: bool = True
    legal_basis_ids: list[str] = field(default_factory=list)
    legal_call: str = ""
    missing_evidence: list[str] = field(default_factory=list)
    comparative_notes: list[str] = field(default_factory=list)
    # LLM-first 추출 시 원문 대조 결과: {"status": "anchored|page_corrected|not_found", "page": N}
    anchor: dict[str, Any] | None = None
    why_flagged: str = ""          # LLM 추출 시 세션이 남긴 위험 가설(트리아지 근거)
    narrative_axis: str = ""       # 사건 서사 축 힌트(②에서 narratives로 확정)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["applicability"] = self.applicability.value
        data["risk_band"] = self.risk_band.value
        return data


@dataclass(slots=True)
class AssessmentResult:
    matter_id: str
    context: dict[str, Any]
    created_at: str
    input_documents: list[SourcePage]
    evidence_documents: list[SourcePage]
    claims: list[ClaimFinding]
    route_recommendations: list[dict[str, str]]
    warnings: list[str]
    claims_source: str = "regex"  # "llm"(1-claims.json 통독 추출) | "regex"(폴백)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matter_id": self.matter_id,
            "context": self.context,
            "created_at": self.created_at,
            "input_documents": [p.to_dict() for p in self.input_documents],
            "evidence_documents": [p.to_dict() for p in self.evidence_documents],
            "claims": [c.to_dict() for c in self.claims],
            "route_recommendations": self.route_recommendations,
            "warnings": self.warnings,
            "claims_source": self.claims_source,
        }
