"""고객 제공용 단일 HTML 보고서 — .md/.docx와 같은 내용, 읽기 경험만 업그레이드.

설계 원칙
- **파일 하나로 완결**: CSS·JS 인라인, 외부 요청 0(폰트·CDN 없음). 메일 첨부 1개로 전달되고
  망분리 환경에서도 열린다.
- **본문에서 조문 원문을 걷어낸다**: 구 보고서는 지면의 25%가 법령 전문이었다. 여기서는
  `<details>` 부록으로 접어 두고, 판단(요약·서사·관문·주장)이 먼저 보이게 한다.
- **위험도 필터·목차**: 25건 주장을 등급으로 걸러 읽는다. 스크립트는 필터·토글뿐이라
  꺼져도 내용은 모두 보인다(점진적 향상).
- **인쇄=PDF**: `@media print`에서 접힌 블록을 모두 펴고 색을 잉크에 맞춘다.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .analysis import PATTERN_LABELS
from .markdown_docs import ROUTE_LABELS

RISK_ORDER = ["매우 높음", "높음", "중간", "낮음"]
RISK_KEY = {"매우 높음": "critical", "높음": "high", "중간": "moderate", "낮음": "low"}
VERDICT_KEY = {"반증": "adverse", "불일치": "adverse", "과장": "warn", "미확인": "unknown", "부합": "ok"}
STANCE_MARK = {"확인": "확인", "반증": "반증", "중립": "중립"}

CSS = """
:root{--ink:#1a1d21;--muted:#5b6470;--line:#e3e6ea;--bg:#fff;--panel:#f7f8fa;
--critical:#a4133c;--high:#c9600a;--moderate:#8a6d1f;--low:#4a6b4f;--accent:#1f4e79;--adverse:#a4133c;--warn:#b8730d;--ok:#2d6a4f;--unknown:#6b7280}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.75 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
word-break:keep-all;overflow-wrap:break-word}
.wrap{display:grid;grid-template-columns:250px minmax(0,1fr);gap:40px;max-width:1180px;margin:0 auto;padding:0 28px}
nav{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;padding:32px 0;font-size:13.5px}
nav a{display:block;color:var(--muted);text-decoration:none;padding:5px 0;border-left:2px solid transparent;padding-left:11px}
nav a:hover{color:var(--accent);border-left-color:var(--accent)}
nav .nav-sub{padding-left:22px;font-size:12.5px}
main{padding:32px 0 96px;min-width:0}
header.doc{border-bottom:3px solid var(--ink);padding-bottom:20px;margin-bottom:28px}
header.doc h1{font-size:27px;margin:0 0 10px;letter-spacing:-.5px}
.meta{color:var(--muted);font-size:13.5px}
.notice{background:var(--panel);border-left:3px solid var(--muted);padding:11px 15px;margin:16px 0;
font-size:13px;color:var(--muted);border-radius:0 3px 3px 0}
h2{font-size:20px;margin:44px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line);letter-spacing:-.3px}
h3{font-size:16.5px;margin:26px 0 10px}
.summary{background:linear-gradient(180deg,#f4f7fb,#fbfcfe);border:1px solid #d8e2ee;border-radius:7px;padding:24px 26px;margin-bottom:12px}
.summary .headline{font-size:16.5px;font-weight:700;line-height:1.7;margin-bottom:16px;color:var(--accent)}
.summary ol{margin:0;padding-left:21px}
.summary ol li{margin-bottom:9px}
.summary .block{margin-top:16px;padding-top:14px;border-top:1px dashed #c9d6e5}
.summary .block b{color:var(--accent)}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:top}
th{background:var(--panel);font-weight:600}
.axis{border:1px solid var(--line);border-radius:7px;padding:18px 20px;margin:14px 0;background:#fcfdfe}
.axis h3{margin-top:0;color:var(--accent)}
.axis dt{font-weight:600;color:var(--muted);font-size:12.5px;letter-spacing:.3px;margin-top:11px}
.axis dd{margin:3px 0 0}
.chips{margin-top:12px}
.chip{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:11px;
padding:2px 9px;font-size:11.5px;color:var(--muted);margin:2px 4px 2px 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.filters{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);
padding:11px 0;border-bottom:1px solid var(--line);margin-bottom:6px;font-size:13px}
.filters button{border:1px solid var(--line);background:#fff;border-radius:15px;padding:5px 13px;
margin-right:6px;cursor:pointer;font:inherit;color:var(--muted)}
.filters button[aria-pressed=true]{background:var(--ink);color:#fff;border-color:var(--ink)}
.claim{border:1px solid var(--line);border-left-width:4px;border-radius:6px;margin:13px 0;background:#fff}
.claim[data-risk=critical]{border-left-color:var(--critical)}
.claim[data-risk=high]{border-left-color:var(--high)}
.claim[data-risk=moderate]{border-left-color:var(--moderate)}
.claim[data-risk=low]{border-left-color:var(--low)}
.claim>summary{cursor:pointer;padding:14px 18px;list-style:none;display:flex;gap:12px;align-items:flex-start}
.claim>summary::-webkit-details-marker{display:none}
.claim>summary::before{content:"▸";color:var(--muted);flex:none;margin-top:1px}
.claim[open]>summary::before{content:"▾"}
.claim>summary:hover{background:#fbfcfd}
.badge{flex:none;font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:11px;color:#fff}
.badge.critical{background:var(--critical)}.badge.high{background:var(--high)}
.badge.moderate{background:var(--moderate)}.badge.low{background:var(--low)}
.sm-title{flex:1;min-width:0}
.sm-title .q{display:block;color:var(--muted);font-size:13px;margin-top:3px}
.claim .body{padding:4px 18px 18px 42px;border-top:1px solid var(--line);margin-top:-1px}
blockquote.quote{margin:12px 0;padding:11px 16px;background:var(--panel);border-left:3px solid var(--accent);
font-size:14px;border-radius:0 4px 4px 0}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:13.5px;margin:10px 0}
.kv dt{color:var(--muted)}
.kv dd{margin:0}
.sub{margin-top:16px}
.sub>b{display:block;font-size:12.5px;letter-spacing:.4px;color:var(--muted);text-transform:uppercase;margin-bottom:6px}
.verdict{display:inline-block;font-size:12px;font-weight:700;padding:2px 9px;border-radius:4px;color:#fff}
.verdict.adverse{background:var(--adverse)}.verdict.warn{background:var(--warn)}
.verdict.ok{background:var(--ok)}.verdict.unknown{background:var(--unknown)}
ul.tight{margin:6px 0;padding-left:20px}ul.tight li{margin-bottom:4px}
.src{font-size:13px;padding:5px 0;border-bottom:1px dotted var(--line)}
.src .mark{font-weight:700;font-size:11.5px;margin-right:6px}
.src .mark.반증{color:var(--adverse)}.src .mark.확인{color:var(--ok)}.src .mark.중립{color:var(--unknown)}
.src a{color:var(--accent)}
.redline{background:#f2f9f4;border:1px solid #cfe6d6;border-radius:5px;padding:11px 14px;margin-top:12px;font-size:13.5px}
.redline b{color:var(--ok)}
.warnflag{background:#fdf2f4;border:1px solid #f2c6d0;color:var(--critical);border-radius:5px;
padding:9px 13px;margin:10px 0;font-size:13px;font-weight:600}
details.appendix{border:1px solid var(--line);border-radius:6px;margin:10px 0;background:#fcfcfd}
details.appendix>summary{cursor:pointer;padding:11px 16px;font-weight:600;font-size:14px}
details.appendix .body{padding:0 18px 16px}
pre.law{white-space:pre-wrap;font-size:12.5px;line-height:1.8;background:var(--panel);
padding:13px 15px;border-radius:4px;color:#33383e;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
footer{margin-top:60px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}
@media(max-width:900px){.wrap{grid-template-columns:1fr;gap:0}nav{display:none}}
@media print{
 nav,.filters{display:none}.wrap{display:block;max-width:none;padding:0}
 body{font-size:10.5pt;line-height:1.6}
 details{open:true}details>summary{list-style:none}
 .claim,.axis,.summary{break-inside:avoid;page-break-inside:avoid}
 h2{break-after:avoid}
 a{color:inherit;text-decoration:none}
 .claim .body,details.appendix .body{display:block!important}
}
"""

JS = """
(function(){
 var btns=document.querySelectorAll('.filters button[data-f]');
 var claims=document.querySelectorAll('.claim');
 btns.forEach(function(b){b.addEventListener('click',function(){
   btns.forEach(function(x){x.setAttribute('aria-pressed', x===b?'true':'false')});
   var f=b.dataset.f;
   claims.forEach(function(c){
     var show = (f==='all') || (f==='top' ? (c.dataset.risk==='critical'||c.dataset.risk==='high') : c.dataset.risk===f);
     c.style.display = show ? '' : 'none';
   });
 })});
 var ex=document.getElementById('toggle-all');
 if(ex) ex.addEventListener('click',function(){
   var open=ex.dataset.open!=='1'; ex.dataset.open=open?'1':'0';
   ex.textContent=open?'모두 접기':'모두 펼치기';
   document.querySelectorAll('.claim').forEach(function(c){c.open=open});
 });
 window.addEventListener('beforeprint',function(){
   document.querySelectorAll('details').forEach(function(d){d.open=true});
 });
})();
"""


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else "")).replace("\n", "<br>")


def _risk_of(claim: dict) -> str:
    return (claim.get("evaluation") or {}).get("risk_final") or claim.get("risk_band") or "중간"


def create_assessment_report_html(result: dict[str, Any], authorities: dict[str, dict[str, Any]],
                                  output_path: Path) -> None:
    ctx = result["context"]
    claims = result["claims"]
    evaluated = [c for c in claims if c.get("evaluation")]
    detailed = evaluated if evaluated else [c for c in claims if c["applicability"] == "있음"][:12]
    narratives = result.get("narratives") or []
    gateway = result.get("gateway") or {}
    exposure = result.get("exposure") or {}
    es = result.get("exec_summary") or {}

    nav: list[str] = []
    o: list[str] = []
    sec = 0

    def h2(title: str, anchor: str) -> None:
        nav.append(f'<a href="#{anchor}">{_e(title)}</a>')
        o.append(f'<h2 id="{anchor}">{_e(title)}</h2>')

    # ── 경영진 요약
    if es:
        h2("경영진 요약", "exec")
        o.append('<div class="summary">')
        if es.get("headline"):
            o.append(f'<div class="headline">{_e(es["headline"])}</div>')
        if es.get("findings"):
            o.append("<ol>" + "".join(f"<li>{_e(f)}</li>" for f in es["findings"]) + "</ol>")
        if es.get("worst_case"):
            o.append(f'<div class="block"><b>최대 리스크 시나리오</b><br>{_e(es["worst_case"])}</div>')
        if es.get("recommendation"):
            o.append(f'<div class="block"><b>권고</b><br>{_e(es["recommendation"])}</div>')
        o.append("</div>")

    # ── 검토 대상
    sec += 1
    h2(f"{sec}. 검토 대상 및 전제", "scope")
    purpose_label = {"defense": "발간 전 사전진단(방어) — 수정 권고안 중심",
                     "offense": "신고·고발 준비(공격) — 제출문서 중심",
                     "both": "사전진단·신고 준비 겸용"}
    rows = []
    if result.get("purpose"):
        rows.append(("검토 목적", purpose_label.get(result["purpose"], result["purpose"])))
    rows += [("기업", ctx.get("company", "[확인 필요]")), ("제품·서비스", ctx.get("product", "[확인 필요]")),
             ("매체", ctx.get("medium", "[확인 필요]")), ("예상 독자", ctx.get("audience", "[확인 필요]")),
             ("게시일", ctx.get("published_date", "[확인 필요]"))]
    o.append("<table>" + "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in rows) + "</table>")
    if result.get("warnings"):
        o.append("<h3>확인 필요 사항</h3><ul class='tight'>"
                 + "".join(f"<li>{_e(w)}</li>" for w in result["warnings"]) + "</ul>")

    # ── 결론 요약
    sec += 1
    h2(f"{sec}. 결론 요약", "conclusion")
    if narratives:
        axes = " / ".join(f"[{i}] {n.get('axis','')}" for i, n in enumerate(narratives, 1))
        o.append(f"<p><b>핵심 위험 축 {len(narratives)}개</b> — {_e(axes)}</p>")
    if evaluated:
        af = {"있음": 0, "불확실": 0, "없음": 0}
        rf = dict.fromkeys(RISK_ORDER, 0)
        for c in evaluated:
            ev = c["evaluation"]
            key = ev.get("applicability_final", "불확실")
            af[key] = af.get(key, 0) + 1
            if ev.get("risk_final") in rf:
                rf[ev["risk_final"]] += 1
        o.append("<table><tr><th>구분</th>" + "".join(f"<th>{r}</th>" for r in RISK_ORDER) + "</tr>"
                 + "<tr><td>최종 위험</td>" + "".join(f"<td>{rf[r]}건</td>" for r in RISK_ORDER) + "</tr></table>")
        o.append(f"<p>정밀평가 {len(evaluated)}건 — 광고성 있음 {af['있음']} · 불확실 {af['불확실']} · 없음 {af['없음']}.</p>")
        if result.get("claims_source") == "llm":
            bad = sum(1 for c in claims if (c.get("anchor") or {}).get("status") == "not_found")
            note = f"주장 추출: 세션 통독 {len(claims)}건 · 원문 앵커 검증 통과 {len(claims) - bad}건"
            if bad:
                note += f" · <b>미확인 {bad}건(인용 재확인 필요)</b>"
            o.append(f'<p class="meta">{note}.</p>')

    # ── 사건 서사
    if narratives:
        sec += 1
        h2(f"{sec}. 종합 위험 분석 — 사건 서사", "narrative")
        o.append("<p>개별 주장 나열이 아니라, 회사의 대외 서사와 확인된 사실의 구조적 괴리를 축으로 종합한다.</p>")
        for i, n in enumerate(narratives, 1):
            o.append(f'<div class="axis"><h3>축 {i}. {_e(n.get("axis",""))}</h3><dl>')
            for label, key in (("회사의 서사", "company_story"), ("확인된 사실", "confirmed_reality"),
                               ("괴리·법적 의미", "gap"), ("법적 평가", "legal_significance")):
                if n.get(key):
                    o.append(f"<dt>{label}</dt><dd>{_e(n[key])}</dd>")
            o.append("</dl>")
            if n.get("claim_ids"):
                o.append('<div class="chips">'
                         + "".join(f'<span class="chip">{_e(x)}</span>' for x in n["claim_ids"]) + "</div>")
            o.append("</div>")

    # ── 관문 쟁점
    if gateway:
        sec += 1
        h2(f"{sec}. 관문 쟁점 — 광고 해당성·경로 선택", "gateway")
        ad = gateway.get("ad_applicability") or {}
        if ad:
            o.append("<h3>광고 해당성 (전 주장 공통 선결문제)</h3>")
            if ad.get("analysis"):
                o.append(f"<p>{_e(ad['analysis'])}</p>")
            if ad.get("media"):
                o.append("<table><tr><th>매체</th><th>결론</th><th>이유</th></tr>"
                         + "".join(f"<tr><td>{_e(m.get('medium'))}</td><td>{_e(m.get('conclusion'))}</td>"
                                   f"<td>{_e(m.get('reason'))}</td></tr>" for m in ad["media"]) + "</table>")
            if ad.get("precedents"):
                o.append("<ul class='tight'>" + "".join(
                    f"<li><b>{_e(p.get('cite'))}</b>"
                    + (f" <span class='meta'>[{_e(p['status'])}]</span>" if p.get("status") else "")
                    + (f"<br>{_e(p['holding'])}" if p.get("holding") else "") + "</li>"
                    for p in ad["precedents"]) + "</ul>")
            if ad.get("conclusion"):
                o.append(f'<div class="notice"><b>결론</b> — {_e(ad["conclusion"])}</div>')
        if gateway.get("alternative_routes"):
            o.append("<h3>대안 경로 비교</h3><table><tr><th>경로</th><th>요건</th><th>제재·효과</th><th>실익·한계</th></tr>"
                     + "".join(f"<tr><td>{_e(r.get('route'))}</td><td>{_e(r.get('requirements'))}</td>"
                               f"<td>{_e(r.get('sanctions'))}</td><td>{_e(r.get('pros_cons'))}</td></tr>"
                               for r in gateway["alternative_routes"]) + "</table>")

    # ── 정량 리스크
    if exposure:
        sec += 1
        h2(f"{sec}. 정량 리스크·제재 전망", "exposure")
        if exposure.get("sanctions"):
            o.append("<table><tr><th>경로</th><th>근거</th><th>노출(상한·구조)</th><th>유사 사건 벤치마크</th></tr>"
                     + "".join(f"<tr><td>{_e(s.get('route'))}</td><td>{_e(s.get('basis'))}</td>"
                               f"<td>{_e(s.get('exposure'))}</td><td>{_e(s.get('benchmark'))}</td></tr>"
                               for s in exposure["sanctions"]) + "</table>")
        if exposure.get("derivative_risks"):
            o.append("<h3>파생 리스크</h3><ul class='tight'>"
                     + "".join(f"<li>{_e(r)}</li>" for r in exposure["derivative_risks"]) + "</ul>")
        if exposure.get("caveat"):
            o.append(f'<div class="notice">{_e(exposure["caveat"])}</div>')

    # ── 주장별 검토
    sec += 1
    claim_sec = sec
    h2(f"{claim_sec}. 주장별 검토", "claims")
    counts = {k: 0 for k in RISK_KEY.values()}
    for c in detailed:
        counts[RISK_KEY.get(_risk_of(c), "moderate")] += 1
    top = counts["critical"] + counts["high"]
    o.append('<div class="filters">'
             f'<button data-f="all" aria-pressed="true">전체 {len(detailed)}</button>'
             f'<button data-f="top">위험 높음↑ {top}</button>'
             + "".join(f'<button data-f="{RISK_KEY[r]}">{r} {counts[RISK_KEY[r]]}</button>'
                       for r in RISK_ORDER if counts[RISK_KEY[r]])
             + '<button id="toggle-all" data-open="0">모두 펼치기</button></div>')
    if gateway:
        o.append(f"<p>광고 해당성은 §{claim_sec - 1} 관문 쟁점의 결론을 전제로 하고, 여기서는 주장별 차별 쟁점만 다룬다.</p>")

    for idx, c in enumerate(detailed, 1):
        ev = c.get("evaluation") or {}
        risk = _risk_of(c)
        rk = RISK_KEY.get(risk, "moderate")
        nav.append(f'<a class="nav-sub" href="#c{idx}">{claim_sec}-{idx} {_e(c["claim_id"])}</a>')
        o.append(f'<details class="claim" id="c{idx}" data-risk="{rk}">')
        o.append(f'<summary><span class="badge {rk}">{_e(risk)}</span>'
                 f'<span class="sm-title"><b>{claim_sec}-{idx}. {_e(c["claim_id"])}</b>'
                 f'<span class="meta"> · {_e(c["filename"])} {c["page"]}쪽</span>'
                 f'<span class="q">{_e(c["quote"][:130])}{"…" if len(c["quote"]) > 130 else ""}</span>'
                 f'</span></summary><div class="body">')
        o.append(f'<blockquote class="quote">{_e(c["quote"])}</blockquote>')
        if (c.get("anchor") or {}).get("status") == "not_found":
            o.append('<div class="warnflag">⚠️ 인용 원문 미확인 — PDF 해당 쪽에서 확인하지 못했습니다. 인용 재확인 전 사용 금지</div>')
        kv = []
        if ev.get("applicability_final"):
            kv.append(("광고성(최종)", ev["applicability_final"]))
        kv.append(("주장 대상", c["subject_scope"]))
        kv.append(("유형", ", ".join(PATTERN_LABELS.get(p, p) for p in c["patterns"])))
        if c.get("why_flagged"):
            kv.append(("선별 사유", c["why_flagged"]))
        o.append('<dl class="kv">' + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in kv) + "</dl>")

        if ev:
            if ev.get("provisions"):
                o.append('<div class="sub"><b>적용 조문(포섭)</b><ul class="tight">' + "".join(
                    f"<li>{_e(p.get('authority_id'))} {_e(p.get('cite'))}"
                    + (f" — {_e(p['label'])}" if p.get("label") else "") + "</li>"
                    for p in ev["provisions"]) + "</ul></div>")
            if ev.get("assessment"):
                o.append(f'<div class="sub"><b>포섭·판단</b><p>{_e(ev["assessment"])}</p></div>')
            if ev.get("misleading"):
                o.append(f'<div class="sub"><b>오인가능성</b><p>{_e(ev["misleading"])}</p></div>')
            if ev.get("precedents"):
                o.append('<div class="sub"><b>참조 심결례·판례</b><ul class="tight">' + "".join(
                    f"<li><b>{_e(p.get('cite'))}</b>"
                    + (f" <span class='meta'>[{_e(p['status'])}]</span>" if p.get("status") else "")
                    + (f"<br>{_e(p['holding'])}" if p.get("holding") else "") + "</li>"
                    for p in ev["precedents"]) + "</ul></div>")
            ver = ev.get("verification")
            if ver:
                vk = VERDICT_KEY.get(ver.get("verdict", ""), "unknown")
                o.append(f'<div class="sub"><b>실증·검증(웹)</b>'
                         f'<p><span class="verdict {vk}">{_e(ver.get("verdict","미확인"))}</span> '
                         f'{_e(ver.get("summary",""))}</p>')
                for s in ver.get("sources", []):
                    stance = s.get("stance", "중립")
                    title = _e(s.get("title", "출처"))
                    link = f'<a href="{html.escape(s["url"])}" target="_blank" rel="noopener">{title}</a>' if s.get("url") else title
                    pub = " ".join(filter(None, [s.get("publisher"), s.get("date")]))
                    o.append(f'<div class="src"><span class="mark {_e(stance)}">{_e(STANCE_MARK.get(stance, stance))}</span>'
                             f'{link}{f" <span class=meta>({_e(pub)})</span>" if pub else ""}'
                             f'{f"<br>{_e(s['finding'])}" if s.get("finding") else ""}</div>')
                o.append("</div>")
            if ev.get("confirm_needed"):
                o.append('<div class="sub"><b>확인 필요</b><ul class="tight">'
                         + "".join(f"<li>{_e(x)}</li>" for x in ev["confirm_needed"]) + "</ul></div>")
            rl = ev.get("redline")
            if rl and rl.get("revised"):
                o.append(f'<div class="redline"><b>수정 제안</b><br>{_e(rl["revised"])}'
                         + (f'<br><span class="meta">근거: {_e(rl["rationale"])}</span>' if rl.get("rationale") else "")
                         + "</div>")
        else:
            o.append(f'<p class="meta">[미평가] 기계 1차분류(법적 판단 아님): {_e(c["legal_call"])}</p>')
        o.append("</div></details>")

    # ── 제출 경로
    sec += 1
    h2(f"{sec}. 제출 경로 검토", "routes")
    o.append("<table><tr><th>경로</th><th>권고</th><th>이유</th></tr>" + "".join(
        f"<tr><td>{_e(ROUTE_LABELS.get(r['route'], r['route']))}</td><td>{_e(r['recommendation'])}</td>"
        f"<td>{_e(r['reason'])}</td></tr>" for r in result["route_recommendations"]) + "</table>")

    # ── 검증 게이트
    sec += 1
    h2(f"{sec}. 최종 검증 게이트", "gate")
    o.append("<ul class='tight'>" + "".join(f"<li>{g}</li>" for g in [
        "사건 당시 시행 법령과 현행 법령을 구분하여 재확인",
        "판례·심결례의 원문, 절차단계 및 확정 여부 확인",
        "각 주장과 증거의 페이지·파일 해시 대조",
        "회사 환경성과·지표의 실재 여부 웹·원자료 재검증",
        "행위자·게시기간·도달범위·시정 여부 확인",
        "변호사 최종 승인 후 제출문서 확정"]) + "</ul>")

    # ── 부록: 조문 원문(접힘) — 본문 지면을 잡아먹던 25%를 여기로 옮긴다
    cited: dict[tuple[str, str], dict] = {}
    cited_ids: set[str] = set()
    for c in detailed:
        for cit in c.get("legal_citations", []):
            cited[(cit["authority_id"], cit["provision_no"])] = cit
            cited_ids.add(cit["authority_id"])
    if cited:
        sec += 1
        h2(f"{sec}. 부록 — 직접 근거 원문·버전", "appendix")
        o.append('<p class="meta">인용 조문의 원문·시행일·해시입니다. 필요할 때만 펼쳐 보십시오.</p>')
        for aid in sorted(cited_ids):
            a = authorities.get(aid, {})
            o.append(f'<p class="meta">{_e(a.get("title", aid))} {_e(a.get("citation") or "")} — '
                     f'{_e(a.get("source_url", ""))}<br>원문 SHA-256 <code>{_e(a.get("sha256") or "[확인 필요]")}</code></p>')
        for cit in cited.values():
            excerpt = cit["text"][:1200] + (" […이하 로컬 조문 DB]" if len(cit["text"]) > 1200 else "")
            o.append(f'<details class="appendix"><summary>{_e(cit["title"])} {_e(cit["provision_no"])} '
                     f'{_e(cit.get("heading") or "")}</summary><div class="body">'
                     f'<pre class="law">{html.escape(excerpt)}</pre>'
                     f'<p class="meta">시행일 {_e(cit.get("effective_date") or "[확인 필요]")} · '
                     f'조문 SHA-256 <code>{_e(cit["provision_sha256"])}</code></p></div></details>')

    meta = result.get("evaluation_meta") or {}
    notice = ("변호사 검토용 초안입니다. 위험도는 우선순위 판단 도구이며 위법성의 자동 결론이 아닙니다."
              + (f" 법적 평가·실증검증은 {meta.get('evaluated_by')}가 수행한 {meta.get('evaluated_count', 0)}건에 근거합니다."
                 if meta else ""))

    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>그린워싱 법률검토보고서 — {html.escape(str(result['matter_id']))}</title>
<style>{CSS}</style></head><body>
<div class="wrap">
<nav>{''.join(nav)}</nav>
<main>
<header class="doc">
<h1>그린워싱 법률검토보고서</h1>
<div class="meta">{html.escape(str(ctx.get('company', '')))} · 사건 <code>{html.escape(str(result['matter_id']))}</code> · 작성일 {html.escape(str(result['created_at'])[:10])}</div>
</header>
<div class="notice">{html.escape(notice)}</div>
{''.join(o)}
<footer>본 보고서는 그린워싱 검토 파이프라인으로 생성된 초안이며, 인용 법령·판례는 제출 전 현행·확정 여부를 재확인해야 합니다. · Confidential</footer>
</main></div>
<script>{JS}</script>
</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc, encoding="utf-8")
