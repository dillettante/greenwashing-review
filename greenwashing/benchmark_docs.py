"""SR 비교분석 보고서 렌더 — .md(기본)·.html(고객용). 건별 보고서와 같은 3종 원칙을 따른다.

집계(`benchmark.py`)와 해석(세션이 쓰는 `benchmark-analysis.json`)을 병합해 렌더한다.
해석이 없으면 집계만 렌더하되, **집계만으로는 결론이 아님**을 문서 안에 명시한다 —
"3사 중 3사에 절대적 표현이 있다"는 사실이고, 그것이 관행인지 이탈인지는 법적 판단이다.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .benchmark import RISK_ORDER
from .html_report import CSS_TMPL, DEFAULT_BRAND, JS, _load_brand, _logo_tag

STANCE_INTRO = {
    "neutral": "업계 실태를 중립적으로 파악하기 위한 비교입니다. 특정 회사의 책임을 묻거나 방어하기 위한 것이 아닙니다.",
    "offense": "규제 대응(신고·조사 요청)을 검토하기 위한 비교입니다. 개별 회사의 이탈과 업계 공통 구조를 구분해 제시합니다.",
    "defense": "자사의 상대적 위치를 진단하기 위한 비교입니다. 업계 공통 관행과 자사 고유 위험을 구분해 대응 우선순위를 제시합니다.",
}


def _cell(v: Any) -> str:
    return str(v if v is not None else "").replace("|", "／").replace("\n", " ").strip()


def _e(v: Any) -> str:
    return html.escape(str(v if v is not None else "")).replace("\n", "<br>")


def _sections(bm: dict, analysis: dict) -> list[tuple[str, str, list]]:
    """(제목, 앵커, 블록) 목록 — md·html이 같은 순서를 공유한다."""
    conf = bm["sample_confidence"]
    cross = bm["cross_tab"]
    out: list[tuple[str, str, list]] = []

    if analysis.get("headline") or analysis.get("findings"):
        out.append(("비교 요약", "summary", [("summary", analysis)]))
    out.append(("1. 비교 대상 및 방법", "scope", [("scope", {"bm": bm, "conf": conf})]))
    out.append(("2. 회사별 위험 포지셔닝", "positioning", [("positioning", bm["positioning"])]))
    out.append(("3. 공통 패턴", "shared", [("shared", {"rows": cross["shared"], "conf": conf,
                                                       "notes": analysis.get("shared_notes") or []})]))
    if cross["unique"]:
        out.append(("4. 개별 이탈", "unique", [("unique", {"rows": cross["unique"],
                                                          "notes": analysis.get("unique_notes") or []})]))
    out.append(("5. 회사별 위험 축", "axes", [("axes", bm["positioning"])]))
    if analysis.get("implications"):
        out.append(("6. 규제·대응 시사점", "implications", [("implications", analysis["implications"])]))
    return out


def create_benchmark_md(bm: dict, analysis: dict, output_path: Path) -> None:
    conf, cross = bm["sample_confidence"], bm["cross_tab"]
    labels, companies = bm["labels"], bm["companies"]
    multi_year = len(labels) != len(companies)
    scope = f"{len(companies)}개사" + (f" · 보고서 {len(labels)}건" if multi_year else "")

    o = ["# 지속가능경영보고서 비교분석", "",
         f"- 대상: {', '.join(companies)} ({scope})",
         f"- 관점: {bm['stance_label']}"]
    if analysis.get("created_at"):
        o.append(f"- 작성일: {analysis['created_at']}")
    o += ["", f"> **표본 한계** — {conf['caveat']}", "",
          f"> {STANCE_INTRO[bm['stance']]}", ""]

    # 절 번호는 세어서 붙인다 — '개별 이탈'은 없으면 통째로 빠지므로 하드코딩하면 번호가 튄다
    n = 0

    def head(title: str) -> str:
        nonlocal n
        n += 1
        return f"## {n}. {title}"

    if analysis.get("headline"):
        o += ["## 비교 요약", "", f"**{analysis['headline']}**", ""]
        o += [f"{i}. {f}" for i, f in enumerate(analysis.get("findings", []), 1)]
        o.append("")

    o += [head("비교 대상 및 방법"), "",
          "각 사의 지속가능경영보고서를 동일한 기준(표시광고법·환경기술산업법·환경광고 심사지침)으로 "
          "개별 검토한 결과를 보고서 축으로 재집계하였습니다. 문안 수가 보고서마다 달라 절대 건수보다 "
          "**비중과 유형 구성**을 함께 보아야 합니다.", ""]
    if multi_year:
        o += ["> 같은 회사의 보고서가 둘 이상이어서 표에는 **게시연도**를 붙여 구분하였습니다. "
              "표본 강도는 보고서 수가 아니라 **회사 수**를 기준으로 판단합니다.", ""]
    o += ["| 보고서 | 매체 | 게시 | 검토 문안 |", "|---|---|---|---|"]
    for r in bm["records"]:
        o.append(f"| {_cell(r['label'])} | {_cell(r['medium'])} | {_cell(r['published'])} | {len(r['claims'])}건 |")

    o += ["", head("보고서별 위험 포지셔닝"), "",
          "| 보고서 | 문안 | " + " | ".join(RISK_ORDER) + " | 높음 이상 비중 | 수정 권고 |",
          "|---|---|" + "---|" * (len(RISK_ORDER) + 2)]
    for p in bm["positioning"]:
        dist = " | ".join(str(p["dist"][k]) for k in RISK_ORDER)
        o.append(f"| {_cell(p['label'])} | {p['claims']} | {dist} | {p['high_ratio']}% | {p['redlines']}건 |")

    o += ["", head("공통 패턴"), "",
          f"복수 회사에서 반복 관찰된 문안 유형입니다. **{conf['label']}** 수준으로 읽어야 합니다.", "",
          "| 문안 유형 | 출현 회사 | " + " | ".join(labels) + " |",
          "|---|---|" + "---|" * len(labels)]
    for r in cross["shared"]:
        per = " | ".join(str(r["per_report"].get(c, 0)) for c in labels)
        o.append(f"| {_cell(r['type'])} | {r['company_count']}개사 | {per} |")
    for note in analysis.get("shared_notes", []):
        o += ["", f"**{note.get('type','')}** — {note.get('interpretation','')}"]

    if cross["unique"]:
        o += ["", head("개별 이탈"), "",
              "한 회사에서만 관찰된 유형입니다. 업계 공통 사정으로 설명하기 어려운 부분입니다.", "",
              "| 문안 유형 | 회사 | 건수 |", "|---|---|---|"]
        for r in cross["unique"]:
            o.append(f"| {_cell(r['type'])} | {_cell(r['companies'][0])} | {r['total_claims']} |")
        for note in analysis.get("unique_notes", []):
            o += ["", f"**{note.get('company','')} — {note.get('type','')}**: {note.get('interpretation','')}"]

    o += ["", head("보고서별 위험 축"), ""]
    for p in bm["positioning"]:
        o += [f"### {p['label']}", ""]
        o += [f"- {a}" for a in p["axes"]] or ["- (축 미설정)"]
        o.append("")

    if analysis.get("implications"):
        o += [head("규제·대응 시사점"), ""]
        for item in analysis["implications"]:
            o += [f"### {item.get('title','')}", "", item.get("body", ""), ""]

    o += ["---", "",
          "본 비교분석은 각 사가 공개한 보고서만을 대상으로 하며, 공개되지 않은 실증자료·내부 정황은 "
          "반영되지 않았습니다. 개별 회사에 대한 법적 결론은 해당 회사의 개별 검토보고서를 따릅니다."]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(o).rstrip() + "\n", encoding="utf-8")


def create_benchmark_html(bm: dict, analysis: dict, output_path: Path) -> None:
    brand = _load_brand()
    conf, cross = bm["sample_confidence"], bm["cross_tab"]
    labels, companies = bm["labels"], bm["companies"]
    multi_year = len(labels) != len(companies)
    nav, o = [], []
    sec = 0

    def h2(title: str, anchor: str, num: bool = True) -> None:
        """번호는 세어서 붙인다 — 빠질 수 있는 절이 있어 하드코딩하면 번호가 튄다."""
        nonlocal sec
        if num:
            sec += 1
            title = f"{sec}. {title}"
        nav.append(f'<a href="#{anchor}">{_e(title)}</a>')
        o.append(f'<h2 id="{anchor}">{_e(title)}</h2>')

    if analysis.get("headline"):
        h2("비교 요약", "summary", num=False)
        o.append('<div class="summary">')
        o.append(f'<div class="headline">{_e(analysis["headline"])}</div>')
        if analysis.get("findings"):
            o.append("<ol>" + "".join(f"<li>{_e(f)}</li>" for f in analysis["findings"]) + "</ol>")
        o.append("</div>")

    h2("비교 대상 및 방법", "scope")
    o.append("<p>각 사의 지속가능경영보고서를 동일한 기준(표시광고법·환경기술산업법·환경광고 심사지침)으로 "
             "개별 검토한 결과를 보고서 축으로 재집계하였습니다. 문안 수가 보고서마다 달라 절대 건수보다 "
             "비중과 유형 구성을 함께 보아야 합니다.</p>")
    if multi_year:
        o.append('<div class="notice">같은 회사의 보고서가 둘 이상이어서 표에는 <b>게시연도</b>를 붙여 '
                 "구분하였습니다. 표본 강도는 보고서 수가 아니라 <b>회사 수</b>를 기준으로 판단합니다.</div>")
    o.append("<table><tr><th>보고서</th><th>매체</th><th>게시</th><th>검토 문안</th></tr>" + "".join(
        f"<tr><td>{_e(r['label'])}</td><td>{_e(r['medium'])}</td><td>{_e(r['published'])}</td>"
        f"<td>{len(r['claims'])}건</td></tr>" for r in bm["records"]) + "</table>")

    h2("보고서별 위험 포지셔닝", "positioning")
    o.append("<table><tr><th>보고서</th><th>문안</th>" + "".join(f"<th>{r}</th>" for r in RISK_ORDER)
             + "<th>높음 이상</th><th>수정 권고</th></tr>" + "".join(
        f"<tr><td>{_e(p['label'])}</td><td>{p['claims']}</td>"
        + "".join(f"<td>{p['dist'][k]}</td>" for k in RISK_ORDER)
        + f"<td><b>{p['high_ratio']}%</b></td><td>{p['redlines']}건</td></tr>"
        for p in bm["positioning"]) + "</table>")

    h2("공통 패턴", "shared")
    o.append(f'<p>복수 회사에서 반복 관찰된 문안 유형입니다. <b>{_e(conf["label"])}</b> 수준으로 읽어야 합니다.</p>')
    o.append("<table><tr><th>문안 유형</th><th>출현 회사</th>"
             + "".join(f"<th>{_e(c)}</th>" for c in labels) + "</tr>" + "".join(
        f"<tr><td>{_e(r['type'])}</td><td>{r['company_count']}개사</td>"
        + "".join(f"<td>{r['per_report'].get(c, 0)}</td>" for c in labels) + "</tr>"
        for r in cross["shared"]) + "</table>")
    for note in analysis.get("shared_notes", []):
        o.append(f'<div class="axis"><h3>{_e(note.get("type",""))}</h3>'
                 f'<p>{_e(note.get("interpretation",""))}</p></div>')

    if cross["unique"]:
        h2("개별 이탈", "unique")
        o.append("<p>한 회사에서만 관찰된 유형입니다. 업계 공통 사정으로 설명하기 어려운 부분입니다.</p>")
        o.append("<table><tr><th>문안 유형</th><th>회사</th><th>건수</th></tr>" + "".join(
            f"<tr><td>{_e(r['type'])}</td><td>{_e(r['companies'][0])}</td><td>{r['total_claims']}</td></tr>"
            for r in cross["unique"]) + "</table>")
        for note in analysis.get("unique_notes", []):
            o.append(f'<div class="axis"><h3>{_e(note.get("company",""))} — {_e(note.get("type",""))}</h3>'
                     f'<p>{_e(note.get("interpretation",""))}</p></div>')

    h2("보고서별 위험 축", "axes")
    for p in bm["positioning"]:
        o.append(f'<div class="axis"><h3>{_e(p["label"])}</h3><ul class="tight">'
                 + "".join(f"<li>{_e(a)}</li>" for a in p["axes"]) + "</ul></div>")

    if analysis.get("implications"):
        h2("규제·대응 시사점", "implications")
        for item in analysis["implications"]:
            o.append(f'<div class="axis"><h3>{_e(item.get("title",""))}</h3>'
                     f'<p>{_e(item.get("body",""))}</p></div>')

    logo, firm = _logo_tag(brand), brand.get("firm", "")
    css = CSS_TMPL.format(primary=brand.get("primary", DEFAULT_BRAND["primary"]),
                          primary_dark=brand.get("primary_dark", DEFAULT_BRAND["primary_dark"]))
    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SR Benchmark — {html.escape(', '.join(companies))}</title>
<style>{css}</style></head><body>
<div class="wrap">
<nav>{f'<div class="brandmark">{logo}</div>' if logo else ''}{''.join(nav)}</nav>
<main>
<header class="doc">
{f'<div class="eyebrow">{html.escape(firm)}</div>' if firm else ''}
<h1>SR Benchmark</h1>
<div class="meta">지속가능경영보고서 비교분석 · {html.escape(', '.join(companies))} · {len(companies)}개사{f' · 보고서 {len(labels)}건' if multi_year else ''}</div>
</header>
<div class="notice"><b>표본 한계</b> — {_e(conf['caveat'])}<br>{_e(STANCE_INTRO[bm['stance']])}</div>
{''.join(o)}
<footer>본 비교분석은 각 사가 공개한 보고서만을 대상으로 하며, 공개되지 않은 실증자료·내부 정황은 반영되지 않았습니다.
개별 회사에 대한 법적 결론은 해당 회사의 개별 검토보고서를 따릅니다. · Confidential</footer>
</main></div>
<script>{JS}</script>
</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc, encoding="utf-8")
