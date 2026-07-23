"""모호한 환경성 표현의 사용 빈도 집계 — 문안 단위 검토를 보완하는 '노출 규모' 지표.

**왜 세는가.** 개별 문안 검토는 "이 문장이 위법인가"를 묻지만, 보고서 전체에서 '친환경'이
87회 쓰였다면 그 자체가 노출 규모다. 환경 관련 표시·광고에 관한 심사지침 Ⅳ~Ⅴ는 구체적
근거·범위 없는 **포괄적 환경성 표시**를 문제 삼는데, 그런 표현이 문서 전반에 반복될수록
소비자가 받는 전체적 인상은 강해진다(대법원 2002두6965의 '전체적·궁극적 인상' 기준).

**빈도는 위법성이 아니다.** 근거를 갖춰 한정적으로 쓴 '친환경'은 적법하다. 이 지표는
어디를 먼저 볼지 정하는 **우선순위 도구**이자, 회사 간 비교의 **정규화된 척도**다.
보고서에도 그렇게 표기한다.

**용어 선정 근거.** 임의 선정이 아니라 규범이 겨냥하는 세 갈래를 따른다:
  ① 포괄적 환경성(심사지침 Ⅳ) — 친환경·녹색·그린·에코
  ② 배타적 절대 표현(부당 표시·광고 유형 및 기준 지정고시 15호 나목, 더클라스 건 법리) — 100%·최초·제로
  ③ 지속가능성·탄소 포괄어 — 지속가능·탄소중립·넷제로
"""
from __future__ import annotations

import re
from typing import Any

# 법령·제도의 고유명사는 회사의 주장이 아니라 인용이므로 세기 전에 걷어낸다.
# (예: '탄소중립녹색성장기본법'의 '녹색', '녹색채권' 발행 사실의 '녹색')
EXCLUDE_PHRASES = [
    # 법령·제도명
    "탄소중립녹색성장기본법", "탄소중립·녹색성장 기본법", "저탄소 녹색성장 기본법",
    "녹색성장기본법", "녹색성장 기본법", "녹색분류체계", "한국형 녹색분류체계", "K-Taxonomy",
    "녹색채권", "녹색금융", "녹색기술 인증", "환경친화적산업구조로의전환촉진에관한법률",
    # 문서·조직 고유명사 — 머리글에 반복되는 보고서 제목과 부서명은 환경성 주장이 아니다.
    # (영풍 실측: '지속가능' 197회 중 93회가 페이지 머리글 '영풍 지속가능경영보고서 2025'였다)
    "지속가능경영", "Sustainability Report", "Sustainability Management",
]

# (분류, 표시명, 패턴) — 한글은 부분일치, 영문은 단어경계
TERM_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("포괄적 환경성", [
        ("친환경", r"친환경"),
        ("환경친화", r"환경\s*친화"),
        ("녹색", r"녹색"),
        ("그린", r"그린"),
        ("에코", r"에코|\beco[- ]?friendly\b"),
        ("청정·깨끗", r"청정|깨끗한"),
        ("green(영문)", r"\bgreen\b"),
    ]),
    ("절대·최상급", [
        ("100%", r"100\s*%"),
        ("제로·ZERO", r"제로화?|\bzero\b"),
        ("완전·일절·전혀", r"완전히?|일절|전혀"),
        # '최대'는 뺀다 — 최대주주·최대 1,200톤처럼 수량·지분 표현이 대부분이라 최상급 주장과 구분되지 않는다
        ("최초·최고", r"최초|최고"),
        ("유일·독보", r"유일|독보적?"),
        ("원천·근본 차단", r"원천적?\s*(?:으로)?\s*차단|근본적?\s*(?:으로)?\s*차단"),
        ("무방류·무배출", r"무방류|무배출"),
    ]),
    ("지속가능·탄소 포괄어", [
        ("지속가능", r"지속\s*가능"),
        ("탄소중립", r"탄소\s*중립"),
        ("넷제로", r"넷\s*제로|\bnet[- ]?zero\b"),
        ("carbon neutral(영문)", r"\bcarbon[- ]?neutral\b"),
        ("sustainable(영문)", r"\bsustainable\b"),
    ]),
]


def _scrub(text: str) -> str:
    """법령명 등 고유명사를 지운 뒤 센다 — 인용을 회사의 주장으로 오인하지 않기 위해서다."""
    for phrase in EXCLUDE_PHRASES:
        text = text.replace(phrase, " ")
    return text


def find_boilerplate(texts: list[str], threshold: float = 0.4, min_len: int = 4) -> set[str]:
    """페이지마다 반복되는 머리글·사이드 목차·푸터를 찾아낸다.

    실측 두 건 모두 여기서 수치가 부풀려졌다 — 영풍은 머리글 '영풍 지속가능경영보고서 2025'가
    93회, 고려아연은 사이드 목차 '공급망 지속가능성'이 78회 잡혔다. 둘 다 회사의 환경성 주장이
    아니라 문서 구조물이다. 제외어를 하나씩 추가하는 대신 **반복 자체를 신호로** 삼는다.
    """
    if len(texts) < 5:  # 페이지가 적으면 정상 문장도 반복으로 오인될 수 있다
        return set()
    seen: dict[str, int] = {}
    for text in texts:
        lines = {re.sub(r"\s+", " ", ln).strip() for ln in (text or "").split("\n")}
        for line in lines:
            if len(line) >= min_len:
                seen[line] = seen.get(line, 0) + 1
    cut = max(2, int(len(texts) * threshold))
    return {line for line, n in seen.items() if n >= cut}


def _strip_boilerplate(text: str, boilerplate: set[str]) -> str:
    if not boilerplate:
        return text
    kept = [ln for ln in (text or "").split("\n")
            if re.sub(r"\s+", " ", ln).strip() not in boilerplate]
    return "\n".join(kept)


def count_green_terms(pages: list[Any]) -> dict[str, Any]:
    """페이지 목록(SourcePage)에서 모호한 환경성 표현의 사용 빈도를 센다.

    반환: 분류별·용어별 총계, 쪽당 밀도, 최다 사용 쪽. 밀도는 보고서 분량이 달라
    절대 건수만으로는 회사 간 비교가 왜곡되기 때문에 함께 낸다.
    """
    raw = [(p.page, p.text or "") for p in pages]
    boilerplate = find_boilerplate([t for _, t in raw])
    texts = [(no, _scrub(_strip_boilerplate(t, boilerplate))) for no, t in raw]
    page_count = len(texts)

    groups: list[dict[str, Any]] = []
    per_page_total: dict[int, int] = {}
    grand_total = 0

    for group_name, terms in TERM_GROUPS:
        rows, group_total = [], 0
        for label, pattern in terms:
            regex = re.compile(pattern, re.I)
            count = 0
            for page_no, text in texts:
                hits = len(regex.findall(text))
                if hits:
                    count += hits
                    per_page_total[page_no] = per_page_total.get(page_no, 0) + hits
            if count:
                rows.append({"term": label, "count": count})
                group_total += count
        rows.sort(key=lambda r: -r["count"])
        groups.append({"group": group_name, "total": group_total, "terms": rows})
        grand_total += group_total

    top_pages = sorted(per_page_total.items(), key=lambda kv: -kv[1])[:5]
    return {
        "total": grand_total,
        "page_count": page_count,
        "per_page": round(grand_total / page_count, 1) if page_count else 0.0,
        "groups": groups,
        "top_pages": [{"page": p, "count": c} for p, c in top_pages],
        "caveat": ("표현의 사용 빈도는 노출 규모를 보여주는 참고 지표이며 그 자체로 위법성을 뜻하지 "
                   "않습니다. 구체적 근거와 범위를 밝혀 사용한 표현은 적법합니다. 목차·제목·도표 "
                   "문구가 함께 집계되며, 법령명 등 고유명사는 집계에서 제외하였습니다."),
    }
