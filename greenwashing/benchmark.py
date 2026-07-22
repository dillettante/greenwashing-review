"""동종업계 지속가능경영보고서(SR) 횡단 비교 — 집계 엔진.

**분석 단위가 건별 검토와 다르다.** `greenwashing-review`가 "이 문안이 위법인가"를 묻는다면,
여기서는 "이 업계에서 무엇이 관행이고 무엇이 이탈인가"를 묻는다. 그래서 각 사의
`2-evaluation.json`(건별 정밀평가 결과)을 **입력으로 받아** 회사 축으로 다시 세운다.

역할 분리는 건별 스킬과 같다 — **집계는 기계가, 해석은 세션이** 한다.
이 모듈은 "3사 중 3사에 절대적 표현이 있다"까지만 세고, "따라서 업계 관행으로 볼 여지가
있으나 A사는 사법확정 사실과 배치되는 점에서 질적으로 다르다"는 세션이 쓴다.

**과잉 일반화 방지**: 2개사 비교로 "업계 관행"을 단정하면 표본이 부족하다.
`sample_confidence()`가 회사 수에 따라 표현 강도를 제한한다(2사=관찰, 3사 이상=관행 후보).

**축이 둘이다 — 보고서와 회사.** 같은 회사의 다른 연도 보고서를 함께 넣는 연도별 추이 비교를
지원하므로, 표는 보고서 단위로 벌리되(열이 따로 서야 추이가 보인다) 표본 강도와 공통/개별
분류는 **회사 단위**로 센다. 한 회사의 2개 연도를 '2개사'로 세면 위 가드가 그대로 뚫린다.
"""
from __future__ import annotations

import collections
import json
import re
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


def sample_confidence(n_companies: int, n_reports: int | None = None) -> dict[str, str]:
    """표본 크기에 따라 허용되는 주장 강도를 정한다(§과잉 일반화 방지).

    **기준은 보고서 수가 아니라 회사 수다.** 같은 회사의 보고서를 여러 해 넣어도 업계 표본이
    늘어난 것이 아니기 때문이다 — 보고서로 세면 1개사 3개년이 '업계 관행 후보'가 되어버린다.
    """
    n_reports = n_reports if n_reports is not None else n_companies
    span = f"{n_companies}개사" + (f"(보고서 {n_reports}건)" if n_reports != n_companies else "")
    if n_companies <= 1:
        return {"level": "single", "label": "동일 회사 연도별 추이",
                "caveat": (f"한 회사의 보고서 {n_reports}건을 비교한 것입니다. **업계 비교가 아니며**, "
                           "같은 회사 안에서의 시점 간 변화만을 의미합니다.")}
    if n_companies >= 5:
        return {"level": "strong", "label": "업계 관행",
                "caveat": f"{span} 표본. 업종 대표성은 표본 선정 기준에 따라 달라집니다."}
    if n_companies >= 3:
        return {"level": "moderate", "label": "업계 관행 후보",
                "caveat": f"{span} 표본으로 경향은 보이나, 업계 전체로 일반화하려면 표본 확대가 필요합니다."}
    return {"level": "weak", "label": "공통 패턴 관찰",
            "caveat": (f"{span} 비교입니다. **'업계 관행'으로 단정할 표본이 아니며**, "
                       f"{n_companies}개사에서 같은 패턴이 관찰되었다는 사실만을 의미합니다.")}


def _report_year(published: Any) -> str:
    """게시연도만 뽑는다. published_date가 '2026-06-01'일 수도 2024(정수)일 수도 있다."""
    m = re.search(r"(\d{4})", str(published or ""))
    return m.group(1) if m else ""


def assign_labels(records: list[dict]) -> None:
    """보고서 표시명을 정한다 — 같은 회사가 둘 이상일 때만 게시연도를 붙인다.

    회사가 한 번만 나오면 회사명 그대로 쓴다(단일 연도 비교의 표를 어지럽히지 않기 위해서다).
    연도까지 겹치면 사건 폴더명으로 떨어뜨린다 — 무슨 수를 써서라도 열은 구분되어야 한다.
    """
    dupes = {c for c, n in collections.Counter(r["company"] for r in records).items() if n > 1}
    used: set[str] = set()
    for r in records:
        label = r["company"]
        if r["company"] in dupes:
            year = _report_year(r["published"])
            label = f"{r['company']} ({year})" if year else r["company"]
            if label in used:
                label = f"{r['company']} ({r['matter_id']})"
        used.add(label)
        r["label"] = label


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
    """유형 × 보고서 교차표와 공통/개별 분류.

    '공통'의 기준은 **과반이 아니라 복수 회사 출현**이다 — 2개사 비교에서 과반(2/2)을 요구하면
    사실상 전원 일치만 잡히고, 3개사 이상에서는 과반이 지나치게 느슨해진다. 출현 회사 수를
    그대로 노출해 세션이 판단하게 한다.

    **표는 보고서별로 벌리되 공통/개별은 회사로 센다.** 한 회사의 2개 연도에서 같은 유형이
    나온 것을 '복수 회사 공통'이라 부르면 없는 업계 관행을 만들어내게 된다.
    """
    all_types = sorted({t for r in records for t in r["types"]})
    matrix = {t: {r["label"]: r["types"].get(t, 0) for r in records} for t in all_types}

    shared, unique = [], []
    for t in all_types:
        hit = [r for r in records if r["types"].get(t, 0) > 0]
        firms = list(dict.fromkeys(r["company"] for r in hit))
        row = {"type": t, "companies": firms, "company_count": len(firms),
               "reports": [r["label"] for r in hit],
               "total_claims": sum(matrix[t].values()), "per_report": matrix[t]}
        (shared if len(firms) >= 2 else unique).append(row)
    shared.sort(key=lambda r: (-r["company_count"], -r["total_claims"]))
    unique.sort(key=lambda r: -r["total_claims"])
    return {"types": all_types, "matrix": matrix, "shared": shared, "unique": unique,
            "company_count": len({r["company"] for r in records}),
            "report_count": len(records)}


def build_benchmark(matter_dirs: list[Path], stance: str = "neutral") -> dict[str, Any]:
    """여러 사건의 평가 결과를 보고서 축으로 재집계한다(표본 강도는 회사 축)."""
    records = [r for r in (load_matter(d) for d in matter_dirs) if r]
    if len(records) < 2:
        raise ValueError("비교하려면 정밀평가(2-evaluation.json)가 끝난 사건이 2건 이상이어야 합니다")
    if stance not in STANCE_LABELS:
        raise ValueError(f"stance는 {'/'.join(STANCE_LABELS)} 중 하나여야 합니다")

    assign_labels(records)
    companies = list(dict.fromkeys(r["company"] for r in records))
    cross = cross_tabulate(records)
    conf = sample_confidence(len(companies), len(records))

    # 위험 분포 — 보고서별 절대건수와 '높음 이상' 비중(문안 수가 달라 절대비교가 왜곡될 수 있다)
    positioning = []
    for r in records:
        total = sum(r["risk_dist"].values())
        high = r["risk_dist"].get("매우 높음", 0) + r["risk_dist"].get("높음", 0)
        positioning.append({
            "company": r["company"], "label": r["label"], "matter_id": r["matter_id"],
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
        "companies": companies,                       # 고유 회사 — 표제·표본 서술용
        "labels": [r["label"] for r in records],      # 보고서 — 표의 열 순서
        "positioning": positioning,
        "cross_tab": cross,
        "records": records,
    }
