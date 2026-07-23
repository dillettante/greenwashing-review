from __future__ import annotations

from pathlib import Path
from typing import Any

from .analysis import PATTERN_LABELS


ROUTE_LABELS = {"kftc": "공정거래위원회", "environment": "기후에너지환경부", "criminal": "수사기관"}
FILING_TITLES = {
    "kftc": "부당한 표시·광고 신고서(초안)",
    "environment": "환경성 표시·광고 조사 요청서(초안)",
    "criminal": "고발장(초안)",
}
STANCE_MARK = {"확인": "✅ 확인", "반증": "⛔ 반증", "중립": "◽ 중립"}


def _cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "／").replace("\n", " ").strip()


def _oneline(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 법률검토보고서 (경로·검증 통합)

def create_assessment_report_md(result: dict[str, Any], authorities: dict[str, dict[str, Any]], output_path: Path) -> None:
    ctx = result["context"]
    claims = result["claims"]
    o: list[str] = [
        f"# 그린워싱 법률검토보고서",
        "",
        f"- 사건: `{result['matter_id']}`",
        f"- 작성일: {result['created_at'][:10]}",
        "",
        "> 변호사 검토용 초안. 위험점수는 우선순위 도구이며 위법성의 자동 결론이 아닙니다.",
    ]
    meta = result.get("evaluation_meta")
    if meta:
        o.append(
            f"> 이 보고서의 ‘법적 평가’·‘실증·검증’은 {meta.get('evaluated_by') or '변호사'}가 "
            f"korean-law MCP·웹 리서치로 정밀평가한 {meta.get('evaluated_count', 0)}건에 근거합니다. "
            "‘기계 1차분류’는 정규식 트리아지 값이며 법적 판단이 아닙니다."
        )
    else:
        o.append(
            "> ※ 정밀 법적 평가(evaluation.json)가 결합되지 않았습니다. ‘기계 1차분류’는 정규식 트리아지 값입니다. "
            "EVALUATION-SOP.md 절차로 korean-law MCP·웹 검증을 결합해야 실전 근거가 됩니다."
        )

    # 경영진 요약 — 세션 작성(evaluation 최상위 exec_summary). 의뢰인/경영진이 첫 화면에서 결론을 본다.
    es = result.get("exec_summary") or {}
    if es:
        o += ["", "## 경영진 요약 (Executive Summary)", ""]
        if es.get("headline"):
            o.append(f"**{es['headline']}**")
        if es.get("findings"):
            o.append("")
            o += [f"{i}. {f}" for i, f in enumerate(es["findings"], 1)]
        if es.get("worst_case"):
            o += ["", f"**최대 리스크 시나리오**: {es['worst_case']}"]
        if es.get("recommendation"):
            o += ["", f"**권고**: {es['recommendation']}"]

    o += ["", "## 1. 검토 대상 및 전제", ""]
    purpose_label = {"defense": "발간 전 사전진단(방어) — 수정 권고안 중심",
                     "offense": "신고·고발 준비(공격) — 제출문서 중심",
                     "both": "사전진단·신고 준비 겸용"}
    if result.get("purpose"):
        o.append(f"- **검토 목적**: {purpose_label.get(result['purpose'], result['purpose'])}")
    for label, key in [("기업", "company"), ("제품·서비스", "product"), ("매체", "medium"),
                       ("예상 독자", "audience"), ("게시일", "published_date")]:
        o.append(f"- **{label}**: {ctx.get(key, '[확인 필요]')}")

    if result.get("warnings"):
        o += ["", "### 확인 필요 사항", ""]
        o += [f"- {w}" for w in result["warnings"]]

    corr = result.get("corroboration")
    if corr:
        o += ["", "### 공개자료 교차확인", "",
              f"회사 홈페이지 스냅숏 {corr.get('company_source_count', 0)}건, 언론 검색 포인터 "
              f"{corr.get('news_pointer_count', 0)}건 수집, 주장-자료 문언 매칭 {len(corr.get('matches', []))}건.",
              corr.get("caveat", "")]

    evaluated = [c for c in claims if c.get("evaluation")]
    narratives = result.get("narratives") or []
    gateway = result.get("gateway") or {}
    section = 2  # 이후 섹션 번호는 존재하는 블록에 따라 동적

    # 결론 요약 — 최종 평가 중심. 기계 분포는 내부값(1-assessment.json)으로만 남긴다.
    o += ["", f"## {section}. 결론 요약", ""]
    if narratives:
        axes = " / ".join(f"[{i}] {n.get('axis','')}" for i, n in enumerate(narratives, 1))
        o.append(f"**핵심 위험 축 {len(narratives)}개** — {axes}. 상세는 '종합 위험 분석'.")
    if evaluated:
        af = {"있음": 0, "불확실": 0, "없음": 0}
        rf = {"매우 높음": 0, "높음": 0, "중간": 0, "낮음": 0}
        for c in evaluated:
            ev = c["evaluation"]
            af[ev.get("applicability_final", "불확실")] = af.get(ev.get("applicability_final", "불확실"), 0) + 1
            if ev.get("risk_final") in rf:
                rf[ev["risk_final"]] += 1
        o.append(
            f"**[정밀평가 최종 분포]** {len(evaluated)}건 — 광고성 있음 {af['있음']} · 불확실 {af['불확실']} · "
            f"없음 {af['없음']} / 위험 매우 높음 {rf['매우 높음']} · 높음 {rf['높음']} · 중간 {rf['중간']} · 낮음 {rf['낮음']}."
        )
        if result.get("claims_source") == "llm":
            bad = sum(1 for c in claims if (c.get("anchor") or {}).get("status") == "not_found")
            o.append(f"주장 추출: 세션 통독(LLM) {len(claims)}건 · 원문 앵커 검증 통과 {len(claims) - bad}건"
                     + (f" · **미확인 {bad}건(인용 재확인 필요)**" if bad else "") + ".")
    else:
        counts = {"매우 높음": 0, "높음": 0, "중간": 0, "낮음": 0}
        for c in claims:
            counts[c["risk_band"]] += 1
        o.append(f"**[기계 트리아지 분포 — 참고용]** 환경 주장 {len(claims)}건 — 매우 높음 {counts['매우 높음']} · "
                 f"높음 {counts['높음']} · 중간 {counts['중간']} · 낮음 {counts['낮음']}. 정규식 값(법적 판단 아님).")

    # 모호한 환경성 표현 사용 빈도 — 문안 단위 검토를 보완하는 노출 규모 지표
    gt = result.get("green_terms") or {}
    if gt.get("total"):
        o += ["", f"**[모호한 환경성 표현 사용 빈도]** 전체 {gt['total']}회 / {gt['page_count']}쪽 "
                  f"— 쪽당 {gt['per_page']}회", "",
              "| 분류 | 횟수 | 주요 표현 |", "|---|---|---|"]
        for grp in gt.get("groups", []):
            top = ", ".join(f"{t['term']} {t['count']}" for t in grp["terms"][:5])
            o.append(f"| {_cell(grp['group'])} | {grp['total']}회 | {_cell(top)} |")
        if gt.get("top_pages"):
            pages_txt = ", ".join(f"{p['page']}쪽({p['count']}회)" for p in gt["top_pages"][:3])
            o.append(f"\n표현이 집중된 지면: {pages_txt}")
        o += ["", f"> {gt.get('caveat', '')}"]

    # 종합 위험 분석(사건 서사) — 회사의 대외 서사 vs 확인된 사실의 구조적 괴리
    if narratives:
        section += 1
        o += ["", f"## {section}. 종합 위험 분석 — 사건 서사", "",
              "개별 주장 나열이 아니라, 회사의 대외 서사와 확인된 사실의 구조적 괴리를 축으로 종합한다. "
              "각 축이 신고서·고발장 '대상 행위' 구성의 뼈대가 된다."]
        for i, n in enumerate(narratives, 1):
            o += ["", f"### 축 {i}. {n.get('axis', '')}"]
            if n.get("company_story"):
                o.append(f"- **회사의 서사**: {n['company_story']}")
            if n.get("confirmed_reality"):
                o.append(f"- **확인된 사실**: {n['confirmed_reality']}")
            if n.get("gap"):
                o.append(f"- **괴리·법적 의미**: {n['gap']}")
            if n.get("legal_significance"):
                o.append(f"- **법적 평가**: {n['legal_significance']}")
            ids = n.get("claim_ids") or []
            if ids:
                o.append(f"- 소속 주장: {', '.join(f'`{x}`' for x in ids)}")

    # 관문 쟁점 — 광고 해당성(전 주장 공통 선결문제) + 대안 경로
    if gateway:
        section += 1
        o += ["", f"## {section}. 관문 쟁점 — 광고 해당성·경로 선택", ""]
        ad = gateway.get("ad_applicability") or {}
        if ad:
            o.append("### 광고 해당성 (전 주장 공통 선결문제)")
            if ad.get("analysis"):
                o += ["", ad["analysis"]]
            for m in ad.get("media") or []:
                o.append(f"- **{m.get('medium','')}**: {m.get('conclusion','')} — {m.get('reason','')}")
            for pr in ad.get("precedents") or []:
                o.append(f"- 근거: {pr.get('cite','')}" + (f" [{pr['status']}]" if pr.get("status") else "")
                         + (f" — {pr['holding']}" if pr.get("holding") else ""))
            if ad.get("conclusion"):
                o += ["", f"**결론**: {ad['conclusion']}"]
        routes_alt = gateway.get("alternative_routes") or []
        if routes_alt:
            o += ["", "### 대안 경로 비교 (광고 해당성이 부정될 경우 포함)", "",
                  "| 경로 | 요건 | 제재·효과 | 실익·한계 |", "|---|---|---|---|"]
            for r in routes_alt:
                o.append(f"| {_cell(r.get('route'))} | {_cell(r.get('requirements'))} | "
                         f"{_cell(r.get('sanctions'))} | {_cell(r.get('pros_cons'))} |")

    # 정량 리스크·제재 전망 — 세션 작성(exposure). "그래서 얼마짜리 리스크인가"에 답한다.
    exposure = result.get("exposure") or {}
    if exposure:
        section += 1
        o += ["", f"## {section}. 정량 리스크·제재 전망", ""]
        sanctions = exposure.get("sanctions") or []
        if sanctions:
            o += ["| 경로 | 근거 | 노출(상한·구조) | 유사 사건 벤치마크 |", "|---|---|---|---|"]
            for s in sanctions:
                o.append(f"| {_cell(s.get('route'))} | {_cell(s.get('basis'))} | "
                         f"{_cell(s.get('exposure'))} | {_cell(s.get('benchmark'))} |")
        if exposure.get("derivative_risks"):
            o += ["", "**파생 리스크**:"]
            o += [f"- {r}" for r in exposure["derivative_risks"]]
        if exposure.get("caveat"):
            o += ["", f"> {exposure['caveat']}"]

    # 주장별 상세 — 정밀평가된 것 우선, 없으면 광고성 상위
    detailed = evaluated if evaluated else [c for c in claims if c["applicability"] == "있음"][:12]
    section += 1
    claim_sec = section
    o += ["", f"## {claim_sec}. 주장별 검토", ""]
    if gateway:
        o.append(f"광고 해당성은 §{claim_sec - 1} 관문 쟁점의 결론을 전제로 하고, 여기서는 주장별 차별 쟁점만 다룬다.")
    for idx, c in enumerate(detailed, 1):
        ev = c.get("evaluation") or {}
        final_risk = ev.get("risk_final") or c["risk_band"]
        o += [f"### {claim_sec}-{idx}. {c['claim_id']} — 최종 위험 {final_risk}", "",
              f"> {c['quote']}", "",
              f"- 위치: {c['filename']} {c['page']}쪽"]
        anchor = c.get("anchor") or {}
        if anchor.get("status") == "not_found":
            o.append("- ⚠️ **인용 원문 미확인** — PDF 해당 쪽에서 인용문을 확인하지 못함. 인용 재확인 전 인용 금지")
        if ev.get("applicability_final"):
            o.append(f"- 광고성(최종): **{ev['applicability_final']}**")
        elif not gateway:
            o.append(f"- 광고성(기계, 참고): {c['applicability']}")
        o += [f"- 주장 대상: {c['subject_scope']}",
              f"- 유형: {', '.join(PATTERN_LABELS.get(p, p) for p in c['patterns'])}"]
        if c.get("why_flagged"):
            o.append(f"- 선별 사유(세션 추출): {c['why_flagged']}")
        if not ev:
            o.append(f"- [미평가] 기계 1차분류(법적 판단 아님): {c['legal_call']}")

        if ev:
            o += ["", "**법적 평가 (변호사·korean-law MCP)**"]
            provs = ev.get("provisions") or []
            if provs:
                o.append("- 적용 조문(포섭):")
                o += [f"    - {p.get('authority_id','')} {p.get('cite','')}" + (f" — {p['label']}" if p.get("label") else "") for p in provs]
            if ev.get("assessment"):
                o.append(f"- 포섭·판단: {ev['assessment']}")
            if ev.get("misleading"):
                o.append(f"- 오인가능성: {ev['misleading']}")
            precs = ev.get("precedents") or []
            if precs:
                o.append("- 참조 심결례·판례:")
                o += [f"    - {pr.get('cite','')}" + (f" [{pr['status']}]" if pr.get("status") else "") + (f" — {pr['holding']}" if pr.get("holding") else "") for pr in precs]
            else:
                o.append("- 참조 심결례·판례: 로컬 의결서 아카이브(`corpus/raw/KR/cases/_index.csv`)에서 유사 표시·광고 의결서 검색·대조")

            ver = ev.get("verification")
            if ver:
                o += ["", "**실증·검증 (웹 리서치)**",
                      f"- 판정: **{ver.get('verdict', '미확인')}**"]
                if ver.get("summary"):
                    o.append(f"- 요약: {ver['summary']}")
                for src in ver.get("sources", []):
                    mark = STANCE_MARK.get(src.get("stance", "중립"), "◽ 중립")
                    title = src.get("title", "출처")
                    url = src.get("url", "")
                    pub = f"{src.get('publisher','')} {src.get('date','')}".strip()
                    link = f"[{title}]({url})" if url else title
                    o.append(f"- {mark} · {link}" + (f" ({pub})" if pub else "") + (f" — {src['finding']}" if src.get("finding") else ""))
            else:
                o += ["", "**실증·검증 (웹 리서치)**: [미실시] 회사 주장 지표의 실재·범위·반증을 웹으로 확인해야 함"]

            if ev.get("confirm_needed"):
                o.append("- [확인 필요]:")
                o += [f"    - {x}" for x in ev["confirm_needed"]]
            rl = ev.get("redline")
            if rl and rl.get("revised"):
                o += ["", f"**수정 제안(발간물 교정 시)**: {rl['revised']}"]
                if rl.get("rationale"):
                    o.append(f"  — 근거: {rl['rationale']}")

        # '추가 확보 필요 자료' 기계 보일러플레이트는 미평가 주장에서만 — 평가된 주장은 confirm_needed가 실질을 담는다
        if c["missing_evidence"] and not ev:
            o += ["", "추가 확보 필요 자료:"]
            o += [f"- {m}" for m in c["missing_evidence"]]
        if c.get("comparative_notes") and not ev:
            o += ["", "비교법적 보강(한국법상 직접 근거 아님):"]
            o += [f"- {n}" for n in c["comparative_notes"]]
        o.append("")

    # 제출 경로 섹션은 두지 않는다 — 관계 기관별 검토는 관문 쟁점의 '대안 경로 비교'(요건·제재·실익)와
    # '정량 리스크·제재 전망'(경로별 근거·노출·벤치마크)이 법적 근거와 함께 이미 다룬다.
    # 다만 경로 선택 시 공통으로 짚어야 할 사항은 아래 검증 게이트로 흡수한다.
    section += 1
    o += ["", f"## {section}. 최종 검증 게이트", "",
          "- 사건 당시 시행 법령과 현행 법령을 구분하여 재확인",
          "- 판례·심결례의 원문, 절차단계 및 확정 여부 확인",
          "- 각 주장과 증거의 페이지·파일 해시 대조",
          "- 회사 환경성과·지표의 실재 여부 웹·원자료 재검증",
          "- 행위자·게시기간·도달범위·시정 여부 확인",
          "- 표시·광고 해당성과 소비자 오인 가능성(경로 공통 선결)",
          "- 환경기술 및 환경산업 지원법상 제품·행위자 범위",
          "- 실증자료 요청·보전 필요성",
          "- 행정조사와 형사절차의 순서 및 중복 위험",
          "- 고발인·피고발인 인적사항, 관할, 시효",
          "- 변호사 최종 승인 후 제출문서 확정"]

    # 직접 근거 원문
    cited_ids: set[str] = set()
    cited_provs: dict[tuple[str, str], dict[str, Any]] = {}
    for c in detailed:
        for cit in c.get("legal_citations", []):
            cited_ids.add(cit["authority_id"])
            cited_provs[(cit["authority_id"], cit["provision_no"])] = cit
    section += 1
    o += ["", f"## {section}. 직접 근거 원문·버전", ""]
    for aid in sorted(cited_ids):
        a = authorities.get(aid, {})
        o.append(f"- {a.get('title', aid)} {a.get('citation') or ''}: {a.get('source_url', '')} "
                 f"(원문 SHA-256 `{a.get('sha256') or '[확인 필요]'}`)")
    for cit in cited_provs.values():
        excerpt = cit["text"][:1200]
        if len(cit["text"]) > len(excerpt):
            excerpt += " […이하 로컬 조문 DB]"
        o += ["", f"### {cit['title']} {cit['provision_no']} {cit.get('heading') or ''}", "",
              excerpt,
              "",
              f"시행일 {cit.get('effective_date') or '[확인 필요]'} · 조문 SHA-256 `{cit['provision_sha256']}`"]

    _write(output_path, o)


# ---------------------------------------------------------------- 레드라인(발간 전 수정 권고안)

def create_redline_md(result: dict[str, Any], output_path: Path) -> bool:
    """redline이 있는 주장으로 '현재 문안 → 위험 → 수정 제안' 표를 만든다(방어 상품의 핵심 산출물).

    반환: 생성 여부(redline 있는 주장이 없으면 False, 파일 미생성).
    """
    rows = [(c, c["evaluation"]["redline"]) for c in result["claims"]
            if (c.get("evaluation") or {}).get("redline", {}).get("revised")]
    if not rows:
        return False
    rows.sort(key=lambda x: x[0]["page"])
    o = [f"# 표시·문안 수정 권고안 (레드라인) — {result['matter_id']}", "",
         f"- 작성일: {result['created_at'][:10]}",
         "- 용도: 보고서·홍보물 **발간 전 사전진단**. 각 문안의 표시광고법·환경광고 심사지침 위험을 낮추는 최소 수정안.",
         "- 수정안은 초안이며 사실관계(실증자료 존부)에 따라 변호사가 확정한다.", "",
         "| 쪽 | 현재 문안 | 위험 | 수정 제안 | 근거 |", "|---|---|---|---|---|"]
    for c, rl in rows:
        risk = (c.get("evaluation") or {}).get("risk_final") or c["risk_band"]
        o.append("| {pg} | {cur} | {rk} | {rev} | {ra} |".format(
            pg=c["page"], cur=_cell(_oneline(c["quote"], 80)), rk=_cell(risk),
            rev=_cell(rl["revised"]), ra=_cell(rl.get("rationale", ""))))
    o += ["", f"총 {len(rows)}건. 수정안 반영 여부와 무관하게 실증자료(제5조) 구비가 선행되어야 한다."]
    _write(output_path, o)
    return True


# ---------------------------------------------------------------- 제출문서 초안(md)

def create_filing_md(result: dict[str, Any], route: str, output_path: Path) -> None:
    ctx = result["context"]
    o = [f"# {FILING_TITLES[route]}", "",
         "> 변호사 승인 후 사실·법령·관할을 최종 확정할 것", "",
         "## 1. 당사자", "",
         f"- 신고인·고발인: {ctx.get('complainant', '[확인 필요]')}",
         f"- 피신고인·피고발인: {ctx.get('company', '[확인 필요]')}",
         f"- 주소·대표자: {ctx.get('respondent_details', '[확인 필요]')}",
         "", "## 2. 대상 행위", ""]
    for c in result["claims"]:
        if c["applicability"] != "없음" and (c.get("evaluation", {}) or {}).get("applicability_final") != "없음":
            o.append(f"- {c['claim_id']} — {c['filename']} {c['page']}쪽: “{_oneline(c['quote'], 90)}”")
    o += ["", "## 3. 사실관계", "",
          "[확인 필요] 게시 주체, 게시일, 게시 매체, 노출기간, 도달범위 및 시정 여부를 증거와 함께 특정합니다."]

    applied: dict[str, str] = {}
    for c in result["claims"]:
        for p in (c.get("evaluation") or {}).get("provisions", []):
            cite = f"{p.get('authority_id', '')} {p.get('cite', '')}".strip()
            if cite:
                applied[cite] = p.get("label", "")
    o += ["", "## 4. 법률상 쟁점", "",
          "각 주장의 진실성·명확성·대상 구체성·환경성 개선의 상당성·자발성·실증가능성과 소비자 오인가능성을 검토합니다."]
    if applied:
        o.append("")
        o.append("정밀평가에서 포섭된 적용 조문:")
        o += [f"- {cite}" + (f" — {label}" if label else "") for cite, label in applied.items()]
    else:
        o += ["", "[확인 필요] 적용 조문은 korean-law MCP 정밀평가 결합 후 확정합니다."]

    o += ["", "## 5. 입증자료", "", "별첨 증거목록과 원문 파일 해시를 참조합니다.", "", "## 6. 요청사항", ""]
    if route == "kftc":
        o.append("표시광고법 위반 여부를 조사하고 필요한 시정조치 등 적절한 조치를 하여 주시기 바랍니다.")
    elif route == "environment":
        o.append("환경성 표시·광고의 실증자료를 확인하고 관련 법령에 따른 조사와 조치를 하여 주시기 바랍니다.")
    else:
        o.append("[확인 필요] 적용 가능한 벌칙조항, 구성요건, 고의, 행위자 및 관할을 확정한 뒤 수사를 요청합니다.")
    _write(output_path, o)
