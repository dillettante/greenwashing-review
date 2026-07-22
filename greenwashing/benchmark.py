"""동종업계 지속가능경영보고서(SR) 횡단 비교 — 집계 엔진.

**분석 단위가 건별 검토와 다르다.** `greenwashing-review`가 "이 문안이 위법인가"를 묻는다면,
여기서는 "이 업계에서 무엇이 관행이고 무엇이 이탈인가"를 묻는다. 그래서 각 사의
`2-evaluation.json`(건별 정밀평가 결과)을 **입력으로 받아** 회사 축으로 다시 세운다.

역할 분리는 건별 스킬과 같다 — **집계는 기계가, 해석은 세션이** 한다.
이 모듈은 "3사 중 3사에 절대적 표현이 있다"까지만 세고, "따라서 업계 관행으로 볼 여지가
있으나 A사는 사법확정 사실과 배치되는 점에서 질적으로 다르다"는 세션이 쓴다.

**과잉 일반화 방지**: 2개사 비교로 "업계 관행"을 단정하면 표본이 부족하다.
`sample_confidence()`가 회사 수에 따라 표현 강도를 제한한다(2사=관찰, 3사 이상=관행 후보).
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
from typing import Any

from .analysis import PATTERN_LABELS

RISK_ORDER = ["매우 높음", "높음", "중간", "낮음"]
STANCE_LABELS = {
    "neutral": "중립 분석 — 업계 실태 파악",
    "offense": "규제 대응 관점 — 신고·조사 요청 준비",
    "defense": "방어 관점 — 자사 위치 진단 및 항변 논거",
}


def _norm_type(raw: str) -> str:
    """유형 표기 정규화 — 원시 키(absolute_claim)와 한글 라벨(절대적 표현)이 섞여 있다."""
    return PATTERN_LABELS.get(raw, raw)


def sample_confidence(n_companies: int) -> dict[str, str]:
    """표본 크기에 따라 허용되는 주장 강도를 정한다(§과잉 일반화 방지)."""
    if n_companies >= 5:
        return {"level": "strong", "label": "업계 관행",
                "caveat": f"{n_companies}개사 표본. 업종 대표성은 표본 선정 기준에 따라 달라집니다."}
    if n_companies >= 3:
        return {"level": "moderate", "label": "업계 관행 후보",
                "caveat": f"{n_companies}개사 표본으로 경향은 보이나, 업계 전체로 일반화하려면 표본 확대가 필요합니다."}
    return {"level": "weak", "label": "공통 패턴 관찰",
            "caveat": (f"{n_companies}개사 비교입니다. **'업계 관행'으로 단정할 표본이 아니며**, "
                       "두 회사에서 같은 패턴이 관찰되었다는 사실만을 의미합니다.")}


def load_matter(matter_dir: Path) -> dict[str, Any] | None:
    """한 사건의 평가 결과를 비교용 레코드로 읽는다. 정밀평가가 없으면 제외."""
    out = matter_dir / "output"
    ev_path, as_path = out / "2-evaluation.json", out / "1-assessment.json"
    if not (ev_path.exists() and as_path.exists()):
        return None
    ev = json.loads(ev_path.read_text(encoding="utf-8"))
    assessment = json.loads(as_path.read_text(encoding="utf-8"))
    claims_ev = ev.get("claims") or {}
    if not claims_ev:
        return None

    by_id = {c["claim_id"]: c for c in assessment["claims"]}
    claims: list[dict[str, Any]] = []
    for cid, e in claims_ev.items():
        base = by_id.get(cid, {})
        claims.append({
            "claim_id": cid,
            "page": base.get("page"),
            "quote": base.get("quote", ""),
            "types": sorted({_norm_type(t) for t in base.get("patterns", [])}),
            "risk": e.get("risk_final") or base.get("risk_band"),
            "applicability": e.get("applicability_final"),
            "verdict": (e.get("verification") or {}).get("verdict"),
            "narrative_axis": base.get("narrative_axis") or "",
            "has_redline": bool((e.get("redline") or {}).get("revised")),
        })
    return {
        "matter_id": ev.get("matter_id") or matter_dir.name,
        "company": assessment.get("context", {}).get("company", matter_dir.name),
        "medium": assessment.get("context", {}).get("medium", ""),
        "published": assessment.get("context", {}).get("published_date", ""),
        "claims": claims,
        "narratives": ev.get("narratives") or [],
        "exec_summary": ev.get("exec_summary") or {},
        "gateway": ev.get("gateway") or {},
        "risk_dist": collections.Counter(c["risk"] for c in claims if c["risk"]),
        "types": collections.Counter(t for c in claims for t in c["types"]),
    }


def cross_tabulate(records: list[dict]) -> dict[str, Any]:
    """유형 × 회사 교차표와 공통/개별 분류.

    '공통'의 기준은 **과반이 아니라 복수 회사 출현**이다 — 2개사 비교에서 과반(2/2)을 요구하면
    사실상 전원 일치만 잡히고, 3개사 이상에서는 과반이 지나치게 느슨해진다. 출현 회사 수를
    그대로 노출해 세션이 판단하게 한다.
    """
    n = len(records)
    all_types = sorted({t for r in records for t in r["types"]})
    matrix: dict[str, dict[str, int]] = {}
    for t in all_types:
        matrix[t] = {r["company"]: r["types"].get(t, 0) for r in records}

    shared, unique = [], []
    for t in all_types:
        present = [c for c, v in matrix[t].items() if v > 0]
        row = {"type": t, "companies": present, "company_count": len(present),
               "total_claims": sum(matrix[t].values()), "per_company": matrix[t]}
        (shared if len(present) >= 2 else unique).append(row)
    shared.sort(key=lambda r: (-r["company_count"], -r["total_claims"]))
    unique.sort(key=lambda r: -r["total_claims"])
    return {"types": all_types, "matrix": matrix, "shared": shared, "unique": unique,
            "company_count": n}


def build_benchmark(matter_dirs: list[Path], stance: str = "neutral") -> dict[str, Any]:
    """여러 사건의 평가 결과를 회사 축으로 재집계한다."""
    records = [r for r in (load_matter(d) for d in matter_dirs) if r]
    if len(records) < 2:
        raise ValueError("비교하려면 정밀평가(2-evaluation.json)가 끝난 사건이 2건 이상이어야 합니다")
    if stance not in STANCE_LABELS:
        raise ValueError(f"stance는 {'/'.join(STANCE_LABELS)} 중 하나여야 합니다")

    cross = cross_tabulate(records)
    conf = sample_confidence(len(records))

    # 위험 분포 — 회사별 절대건수와 '높음 이상' 비중(문안 수가 달라 절대비교가 왜곡될 수 있다)
    positioning = []
    for r in records:
        total = sum(r["risk_dist"].values())
        high = r["risk_dist"].get("매우 높음", 0) + r["risk_dist"].get("높음", 0)
        positioning.append({
            "company": r["company"], "matter_id": r["matter_id"],
            "claims": total,
            "dist": {k: r["risk_dist"].get(k, 0) for k in RISK_ORDER},
            "high_or_above": high,
            "high_ratio": round(high / total * 100, 1) if total else 0.0,
            "axes": [n.get("axis", "") for n in r["narratives"]],
            "redlines": sum(1 for c in r["claims"] if c["has_redline"]),
        })

    return {
        "generated_from": [str(d) for d in matter_dirs],
        "stance": stance,
        "stance_label": STANCE_LABELS[stance],
        "sample_confidence": conf,
        "companies": [r["company"] for r in records],
        "positioning": positioning,
        "cross_tab": cross,
        "records": records,
    }
