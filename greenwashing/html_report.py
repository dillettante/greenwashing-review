"""고객 제공용 단일 HTML 보고서 — .md/.docx와 같은 내용, 대고객 표현·형식으로 다듬은 판.

설계 원칙
- **파일 하나로 완결**: CSS·JS·로고를 인라인(base64)한다. 외부 요청이 0이라 메일 첨부 하나로
  전달되고 망분리 환경에서도 열린다.
- **본문에서 조문 원문을 걷어낸다**: 구 보고서는 지면의 25%가 법령 전문이었다. 부록으로 접어
  판단(요약·서사·관문·주장)이 먼저 보이게 한다.
- **대고객 문체**: 합쇼체를 쓰고 내부 도구명(정규식·세션·MCP·앵커 등)을 노출하지 않는다.
  같은 사실을 의뢰인의 언어로 바꿔 쓸 뿐, 내용을 덜어내지 않는다.
- **브랜딩은 로컬 자산**: `brand/brand.json`(gitignore)이 있으면 로고·CI 색을 입히고,
  없으면 중립 색으로 렌더한다. 법인 로고는 공개 저장소에 두지 않는다.
"""
from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from .analysis import PATTERN_LABELS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RISK_ORDER = ["매우 높음", "높음", "중간", "낮음"]
RISK_KEY = {"매우 높음": "critical", "높음": "high", "중간": "moderate", "낮음": "low"}
VERDICT_KEY = {"반증": "adverse", "불일치": "adverse", "과장": "warn", "미확인": "unknown", "부합": "ok"}
# 고객용 표현 — 내부 판정어를 의뢰인이 읽는 말로 바꾼다(내용은 동일)
VERDICT_LABEL = {"반증": "상반된 사실 확인", "불일치": "자료 간 불일치", "과장": "표현 과장 소지",
                 "미확인": "추가 확인 필요", "부합": "사실 부합"}
STANCE_LABEL = {"확인": "뒷받침", "반증": "상반", "중립": "참고"}
DEFAULT_BRAND = {"firm": "", "logo": "", "primary": "#1f4e79", "primary_dark": "#17395a", "footer": ""}


def _load_brand() -> dict:
    """brand/brand.json이 있으면 로고·CI 색을 읽는다(법인 자산이라 저장소에는 두지 않는다)."""
    brand = dict(DEFAULT_BRAND)
    path = PROJECT_ROOT / "brand" / "brand.json"
    if path.exists():
        try:
            brand.update(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return brand


def _logo_tag(brand: dict) -> str:
    """로고를 base64로 인라인한다. 파일이 없으면 법인명 텍스트로, 그것도 없으면 빈 자리로 둔다."""
    rel = brand.get("logo") or ""
    if rel:
        path = (PROJECT_ROOT / rel) if not Path(rel).is_absolute() else Path(rel)
        if path.exists():
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            data = base64.b64encode(path.read_bytes()).decode()
            return f'<img class="logo" src="data:{mime};base64,{data}" alt="{html.escape(brand.get("firm",""))}">'
    if brand.get("firm"):
        return f'<div class="logo-text">{html.escape(brand["firm"])}</div>'
    return ""


CSS_TMPL = """
:root{{--ink:#1a1d21;--muted:#5b6470;--line:#e3e6ea;--bg:#fff;--panel:#f7f8fa;
--brand:{primary};--brand-dark:{primary_dark};
--critical:{primary};--high:#c9600a;--moderate:#8a6d1f;--low:#4a6b4f;
--adverse:{primary};--warn:#b8730d;--ok:#2d6a4f;--unknown:#6b7280}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.78 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
word-break:keep-all;overflow-wrap:break-word}}
.wrap{{display:grid;grid-template-columns:250px minmax(0,1fr);gap:40px;max-width:1180px;margin:0 auto;padding:0 28px}}
nav{{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;padding:30px 0;font-size:13.5px}}
nav .brandmark{{margin-bottom:20px;padding-bottom:16px;border-bottom:2px solid var(--brand)}}
nav a{{display:block;color:var(--muted);text-decoration:none;padding:5px 0;border-left:2px solid transparent;padding-left:11px}}
nav a:hover{{color:var(--brand);border-left-color:var(--brand)}}
nav .nav-sub{{padding-left:22px;font-size:12.5px}}
main{{padding:30px 0 96px;min-width:0}}
.logo{{max-width:190px;height:auto;display:block}}
.logo-text{{font-size:15px;font-weight:700;color:var(--brand);letter-spacing:-.3px}}
header.doc{{border-bottom:3px solid var(--brand);padding-bottom:20px;margin-bottom:26px}}
header.doc .eyebrow{{color:var(--brand);font-size:12.5px;font-weight:700;letter-spacing:1.4px;margin-bottom:9px}}
header.doc h1{{font-size:27px;margin:0 0 11px;letter-spacing:-.6px}}
.meta{{color:var(--muted);font-size:13.5px}}
.notice{{background:var(--panel);border-left:3px solid var(--muted);padding:12px 16px;margin:16px 0;
font-size:13px;color:var(--muted);border-radius:0 3px 3px 0}}
h2{{font-size:20px;margin:44px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line);letter-spacing:-.3px}}
h3{{font-size:16.5px;margin:26px 0 10px}}
.summary{{background:linear-gradient(180deg,#fbf5f6,#fdfbfb);border:1px solid #ecd9db;border-radius:7px;padding:24px 26px}}
.summary .headline{{font-size:16.5px;font-weight:700;line-height:1.75;margin-bottom:16px;color:var(--brand-dark)}}
.summary ol{{margin:0;padding-left:21px}}
.summary ol li{{margin-bottom:9px}}
.summary .block{{margin-top:16px;padding-top:14px;border-top:1px dashed #e0c9cc}}
.summary .block b{{color:var(--brand-dark)}}
table{{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px}}
th,td{{border:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:top}}
th{{background:var(--panel);font-weight:600}}
.axis{{border:1px solid var(--line);border-top:3px solid var(--brand);border-radius:5px;padding:18px 20px;margin:14px 0;background:#fcfdfe}}
.axis h3{{margin-top:0;color:var(--brand-dark)}}
.axis dt{{font-weight:600;color:var(--muted);font-size:12.5px;letter-spacing:.3px;margin-top:11px}}
.axis dd{{margin:3px 0 0}}
.chips{{margin-top:12px}}
.chip{{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:11px;
padding:2px 9px;font-size:11.5px;color:var(--muted);margin:2px 4px 2px 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
.filters{{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);
padding:11px 0;border-bottom:1px solid var(--line);margin-bottom:6px;font-size:13px}}
.filters button{{border:1px solid var(--line);background:#fff;border-radius:15px;padding:5px 13px;
margin:0 6px 4px 0;cursor:pointer;font:inherit;color:var(--muted)}}
.filters button[aria-pressed=true]{{background:var(--brand);color:#fff;border-color:var(--brand)}}
.claim{{border:1px solid var(--line);border-left-width:4px;border-radius:6px;margin:13px 0;background:#fff}}
.claim[data-risk=critical]{{border-left-color:var(--critical)}}
.claim[data-risk=high]{{border-left-color:var(--high)}}
.claim[data-risk=moderate]{{border-left-color:var(--moderate)}}
.claim[data-risk=low]{{border-left-color:var(--low)}}
.claim>summary{{cursor:pointer;padding:14px 18px;list-style:none;display:flex;gap:12px;align-items:flex-start}}
.claim>summary::-webkit-details-marker{{display:none}}
.claim>summary::before{{content:"▸";color:var(--muted);flex:none;margin-top:1px}}
.claim[open]>summary::before{{content:"▾"}}
.claim>summary:hover{{background:#fbfcfd}}
.badge{{flex:none;font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:11px;color:#fff}}
.badge.critical{{background:var(--critical)}}.badge.high{{background:var(--high)}}
.badge.moderate{{background:var(--moderate)}}.badge.low{{background:var(--low)}}
.sm-title{{flex:1;min-width:0}}
.sm-title .q{{display:block;color:var(--muted);font-size:13px;margin-top:3px}}
.claim .body{{padding:4px 18px 18px 42px;border-top:1px solid var(--line);margin-top:-1px}}
blockquote.quote{{margin:12px 0;padding:11px 16px;background:var(--panel);border-left:3px solid var(--brand);
font-size:14px;border-radius:0 4px 4px 0}}
.kv{{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:13.5px;margin:10px 0}}
.kv dt{{color:var(--muted)}}
.kv dd{{margin:0}}
.sub{{margin-top:16px}}
.sub>b{{display:block;font-size:12.5px;letter-spacing:.4px;color:var(--muted);margin-bottom:6px}}
.verdict{{display:inline-block;font-size:12px;font-weight:700;padding:2px 9px;border-radius:4px;color:#fff}}
.verdict.adverse{{background:var(--adverse)}}.verdict.warn{{background:var(--warn)}}
.verdict.ok{{background:var(--ok)}}.verdict.unknown{{background:var(--unknown)}}
ul.tight{{margin:6px 0;padding-left:20px}}ul.tight li{{margin-bottom:4px}}
.src{{font-size:13px;padding:5px 0;border-bottom:1px dotted var(--line)}}
.src .mark{{font-weight:700;font-size:11.5px;margin-right:6px}}
.src .mark.상반{{color:var(--adverse)}}.src .mark.뒷받침{{color:var(--ok)}}.src .mark.참고{{color:var(--unknown)}}
.src a{{color:var(--brand-dark)}}
.redline{{background:#f2f9f4;border:1px solid #cfe6d6;border-radius:5px;padding:11px 14px;margin-top:12px;font-size:13.5px}}
.redline b{{color:var(--ok)}}
.warnflag{{background:#fdf2f4;border:1px solid #f2c6d0;color:var(--brand-dark);border-radius:5px;
padding:9px 13px;margin:10px 0;font-size:13px;font-weight:600}}
details.appendix{{border:1px solid var(--line);border-radius:6px;margin:10px 0;background:#fcfcfd}}
details.appendix>summary{{cursor:pointer;padding:11px 16px;font-weight:600;font-size:14px}}
details.appendix .body{{padding:0 18px 16px}}
pre.law{{white-space:pre-wrap;font-size:12.5px;line-height:1.8;background:var(--panel);
padding:13px 15px;border-radius:4px;color:#33383e;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
footer{{margin-top:60px;padding-top:18px;border-top:2px solid var(--brand);color:var(--muted);font-size:12.5px}}
@media(max-width:900px){{.wrap{{grid-template-columns:1fr;gap:0}}nav{{display:none}}}}
@media print{{
 nav,.filters{{display:none}}.wrap{{display:block;max-width:none;padding:0}}
 body{{font-size:10.5pt;line-height:1.62}}
 .claim,.axis,.summary{{break-inside:avoid;page-break-inside:avoid}}
 h2{{break-after:avoid}}
 a{{color:inherit;text-decoration:none}}
 .claim .body,details.appendix .body{{display:block!important}}
}}
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


# 내부 검증 이력을 뜻하는 표지 — 의뢰인 문서에 나가면 안 된다(작업 지시·도구명·수집 경로)
_INTERNAL_MARK = ("변호사 확인", "국가법령정보", "korean-law", "아카이브", "MCP", "원문 확인",
                  "전문 확인", "확인 필요", "로컬")


def _public_status(status: str) -> str:
    """판례·심결례의 `status`에서 **법적 절차 단계만** 남긴다.

    이 필드에는 두 성격이 섞여 있다 — 절차 단계(확정·공정위 의결·ASA 재결)는 인용 가치에
    직결되어 의뢰인에게 필요하지만, 검증 이력("국가법령정보 원문 확인", "확정 여부 변호사 확인")은
    내부 작업 기록이다. 후자는 지우되, 확정 여부가 확인되지 않았다는 **사실 자체는**
    중립적으로 남긴다([[CLAUDE]] §2-1 — 확정 여부 미확인은 표시해야 한다).
    """
    raw = str(status or "").strip()
    if not raw:
        return ""
    parts: list[str] = []
    # 절차 단계 추출(있는 것만)
    if re.search(r"(?<!여부 )확정(?!\s*여부)", raw) and "여부" not in raw.split("확정")[0][-6:]:
        parts.append("확정")
    m = re.search(r"공정위 의결(?:\(([^)]+)\))?", raw)
    if m:
        parts.append(f"공정위 의결({m.group(1)})" if m.group(1) else "공정위 의결")
    if "피심인 위법성 수락" in raw:
        parts.append("피심인 위법성 수락")
    if "ASA" in raw or "재결" in raw:
        parts.append("영국 ASA 재결 — 국내법상 직접 근거는 아닌 참고 자료")
    if "헌법재판소" in raw or "헌재" in raw:
        parts.append("헌법재판소 결정")
    # 확정 여부가 미확인이면 중립 표기로 남긴다(작업 지시 어투는 제거)
    if not any(p == "확정" for p in parts) and re.search(r"확정\s*여부", raw):
        parts.append("사법 확정 여부 미확인")
    if not parts:
        # 절차 단계가 없고 내부 기록뿐이면 표시하지 않는다
        return "" if any(k in raw for k in _INTERNAL_MARK) else raw
    return " · ".join(parts)


def _risk_of(claim: dict) -> str:
    return (claim.get("evaluation") or {}).get("risk_final") or claim.get("risk_band") or "중간"


def create_assessment_report_html(result: dict[str, Any], authorities: dict[str, dict[str, Any]],
                                  output_path: Path) -> None:
    brand = _load_brand()
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

    # ── 검토 요약
    if es:
        h2("검토 요약", "exec")
        o.append('<div class="summary">')
        if es.get("headline"):
            o.append(f'<div class="headline">{_e(es["headline"])}</div>')
        if es.get("findings"):
            o.append("<ol>" + "".join(f"<li>{_e(f)}</li>" for f in es["findings"]) + "</ol>")
        if es.get("worst_case"):
            o.append(f'<div class="block"><b>최대 리스크 시나리오</b><br>{_e(es["worst_case"])}</div>')
        if es.get("recommendation"):
            o.append(f'<div class="block"><b>권고 사항</b><br>{_e(es["recommendation"])}</div>')
        o.append("</div>")

    # ── 검토 대상
    sec += 1
    h2(f"{sec}. 검토 대상 및 전제", "scope")
    purpose_label = {"defense": "발간 전 사전 진단 — 문안 수정 권고 중심",
                     "offense": "신고·고발 준비 — 제출문서 중심",
                     "both": "사전 진단 및 신고 준비 겸용"}
    rows = []
    if result.get("purpose"):
        rows.append(("검토 목적", purpose_label.get(result["purpose"], result["purpose"])))
    rows += [("대상 기업", ctx.get("company", "[확인 필요]")), ("제품·서비스", ctx.get("product", "[확인 필요]")),
             ("검토 매체", ctx.get("medium", "[확인 필요]")), ("예상 독자", ctx.get("audience", "[확인 필요]")),
             ("게시일", ctx.get("published_date", "[확인 필요]"))]
    o.append("<table>" + "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in rows) + "</table>")
    if result.get("warnings"):
        o.append("<h3>확인이 필요한 사항</h3><ul class='tight'>"
                 + "".join(f"<li>{_e(w)}</li>" for w in result["warnings"]) + "</ul>")

    # ── 검토 결과 개요
    sec += 1
    h2(f"{sec}. 검토 결과 개요", "conclusion")
    if narratives:
        axes = " / ".join(f"[{i}] {n.get('axis','')}" for i, n in enumerate(narratives, 1))
        o.append(f"<p>이번 검토에서 확인된 <b>핵심 위험 축은 {len(narratives)}개</b>입니다 — {_e(axes)}. "
                 "각 축의 상세 내용은 다음 장에서 설명드립니다.</p>")
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
                 + "<tr><td>위험도별 문안 수</td>" + "".join(f"<td>{rf[r]}건</td>" for r in RISK_ORDER) + "</tr></table>")
        o.append(f"<p>검토 대상 문안은 모두 {len(evaluated)}건이며, 표시·광고 해당 여부는 "
                 f"인정 {af['있음']}건 · 다툼의 여지 있음 {af['불확실']}건 · 해당 없음 {af['없음']}건으로 판단하였습니다.</p>")
        if result.get("claims_source") == "llm":
            bad = sum(1 for c in claims if (c.get("anchor") or {}).get("status") == "not_found")
            note = (f"검토 대상 문안 {len(claims)}건은 보고서 원문과 대조하여 "
                    f"{len(claims) - bad}건의 인용 정확성을 확인하였습니다")
            if bad:
                note += f". <b>다만 {bad}건은 원문에서 확인되지 않아 재확인이 필요합니다</b>"
            o.append(f'<p class="meta">{note}.</p>')

    # ── 종합 위험 분석
    if narratives:
        sec += 1
        h2(f"{sec}. 종합 위험 분석", "narrative")
        o.append("<p>개별 문안을 나열하는 대신, 보고서가 제시하는 서술과 확인된 사실 사이의 "
                 "구조적 괴리를 축으로 정리하였습니다. 각 축은 향후 규제 대응이나 문안 수정의 단위가 됩니다.</p>")
        for i, n in enumerate(narratives, 1):
            o.append(f'<div class="axis"><h3>축 {i}. {_e(n.get("axis",""))}</h3><dl>')
            for label, key in (("보고서의 서술", "company_story"), ("확인된 사실", "confirmed_reality"),
                               ("괴리의 내용", "gap"), ("법적 평가", "legal_significance")):
                if n.get(key):
                    o.append(f"<dt>{label}</dt><dd>{_e(n[key])}</dd>")
            o.append("</dl>")
            if n.get("claim_ids"):
                o.append('<div class="chips">'
                         + "".join(f'<span class="chip">{_e(x)}</span>' for x in n["claim_ids"]) + "</div>")
            o.append("</div>")

    # ── 선결 쟁점
    if gateway:
        sec += 1
        h2(f"{sec}. 선결 쟁점 — 표시·광고 해당성", "gateway")
        ad = gateway.get("ad_applicability") or {}
        if ad:
            o.append("<p>아래 쟁점은 개별 문안에 앞서 판단되어야 하는 공통 전제입니다.</p>")
            if ad.get("analysis"):
                o.append(f"<p>{_e(ad['analysis'])}</p>")
            if ad.get("media"):
                o.append("<table><tr><th>매체</th><th>판단</th><th>이유</th></tr>"
                         + "".join(f"<tr><td>{_e(m.get('medium'))}</td><td>{_e(m.get('conclusion'))}</td>"
                                   f"<td>{_e(m.get('reason'))}</td></tr>" for m in ad["media"]) + "</table>")
            if ad.get("precedents"):
                o.append("<h3>참고 판례·심결례</h3><ul class='tight'>" + "".join(
                    f"<li><b>{_e(p.get('cite'))}</b>"
                    + (f" <span class='meta'>[{_e(_public_status(p['status']))}]</span>" if _public_status(p.get("status","")) else "")
                    + (f"<br>{_e(p['holding'])}" if p.get("holding") else "") + "</li>"
                    for p in ad["precedents"]) + "</ul>")
            if ad.get("conclusion"):
                o.append(f'<div class="notice"><b>결론</b> — {_e(ad["conclusion"])}</div>')
        if gateway.get("alternative_routes"):
            o.append("<h3>대안 경로 비교</h3>"
                     "<p>표시·광고 해당성이 부정될 경우를 대비한 검토입니다.</p>"
                     "<table><tr><th>경로</th><th>요건</th><th>제재·효과</th><th>실익과 한계</th></tr>"
                     + "".join(f"<tr><td>{_e(r.get('route'))}</td><td>{_e(r.get('requirements'))}</td>"
                               f"<td>{_e(r.get('sanctions'))}</td><td>{_e(r.get('pros_cons'))}</td></tr>"
                               for r in gateway["alternative_routes"]) + "</table>")

    # ── 제재 전망
    if exposure:
        sec += 1
        h2(f"{sec}. 제재 전망 및 파생 리스크", "exposure")
        if exposure.get("sanctions"):
            o.append("<table><tr><th>경로</th><th>근거</th><th>노출 범위</th><th>유사 사건 사례</th></tr>"
                     + "".join(f"<tr><td>{_e(s.get('route'))}</td><td>{_e(s.get('basis'))}</td>"
                               f"<td>{_e(s.get('exposure'))}</td><td>{_e(s.get('benchmark'))}</td></tr>"
                               for s in exposure["sanctions"]) + "</table>")
        if exposure.get("derivative_risks"):
            o.append("<h3>파생 리스크</h3><ul class='tight'>"
                     + "".join(f"<li>{_e(r)}</li>" for r in exposure["derivative_risks"]) + "</ul>")
        if exposure.get("caveat"):
            o.append(f'<div class="notice">{_e(exposure["caveat"])}</div>')

    # ── 문안별 검토
    sec += 1
    claim_sec = sec
    h2(f"{claim_sec}. 문안별 검토", "claims")
    counts = {k: 0 for k in RISK_KEY.values()}
    for c in detailed:
        counts[RISK_KEY.get(_risk_of(c), "moderate")] += 1
    top = counts["critical"] + counts["high"]
    o.append('<div class="filters">'
             f'<button data-f="all" aria-pressed="true">전체 {len(detailed)}</button>'
             f'<button data-f="top">위험 높음 이상 {top}</button>'
             + "".join(f'<button data-f="{RISK_KEY[r]}">{r} {counts[RISK_KEY[r]]}</button>'
                       for r in RISK_ORDER if counts[RISK_KEY[r]])
             + '<button id="toggle-all" data-open="0">모두 펼치기</button></div>')
    o.append("<p>각 항목을 누르시면 적용 조문, 참고 사례, 사실 확인 결과와 수정 제안을 보실 수 있습니다."
             + (f" 표시·광고 해당성은 앞의 선결 쟁점에서 검토한 결론을 전제로 합니다." if gateway else "") + "</p>")

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
            o.append('<div class="warnflag">이 인용문은 해당 쪽 원문에서 확인되지 않았습니다. '
                     '원문을 재확인하시기 전까지는 인용을 보류하시기 바랍니다.</div>')
        kv = []
        if ev.get("applicability_final"):
            kv.append(("표시·광고 해당성", ev["applicability_final"]))
        kv.append(("주장 대상", c["subject_scope"]))
        kv.append(("문안 유형", ", ".join(PATTERN_LABELS.get(p, p) for p in c["patterns"])))
        if c.get("why_flagged"):
            kv.append(("선별 사유", c["why_flagged"]))
        o.append('<dl class="kv">' + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in kv) + "</dl>")

        if ev:
            if ev.get("provisions"):
                o.append('<div class="sub"><b>적용 조문</b><ul class="tight">' + "".join(
                    f"<li>{_e(p.get('authority_id'))} {_e(p.get('cite'))}"
                    + (f" — {_e(p['label'])}" if p.get("label") else "") + "</li>"
                    for p in ev["provisions"]) + "</ul></div>")
            if ev.get("assessment"):
                o.append(f'<div class="sub"><b>검토 의견</b><p>{_e(ev["assessment"])}</p></div>')
            if ev.get("misleading"):
                o.append(f'<div class="sub"><b>오인 가능성</b><p>{_e(ev["misleading"])}</p></div>')
            if ev.get("precedents"):
                o.append('<div class="sub"><b>참고 판례·심결례</b><ul class="tight">' + "".join(
                    f"<li><b>{_e(p.get('cite'))}</b>"
                    + (f" <span class='meta'>[{_e(_public_status(p['status']))}]</span>" if _public_status(p.get("status","")) else "")
                    + (f"<br>{_e(p['holding'])}" if p.get("holding") else "") + "</li>"
                    for p in ev["precedents"]) + "</ul></div>")
            ver = ev.get("verification")
            if ver:
                verdict = ver.get("verdict", "미확인")
                vk = VERDICT_KEY.get(verdict, "unknown")
                o.append(f'<div class="sub"><b>사실 확인 결과</b>'
                         f'<p><span class="verdict {vk}">{_e(VERDICT_LABEL.get(verdict, verdict))}</span> '
                         f'{_e(ver.get("summary",""))}</p>')
                for s in ver.get("sources", []):
                    label = STANCE_LABEL.get(s.get("stance", "중립"), "참고")
                    title = _e(s.get("title", "출처"))
                    link = (f'<a href="{html.escape(s["url"])}" target="_blank" rel="noopener">{title}</a>'
                            if s.get("url") else title)
                    pub = " ".join(filter(None, [s.get("publisher"), s.get("date")]))
                    finding = f"<br>{_e(s['finding'])}" if s.get("finding") else ""
                    o.append(f'<div class="src"><span class="mark {label}">{label}</span>'
                             f'{link}{f" <span class=meta>({_e(pub)})</span>" if pub else ""}{finding}</div>')
                o.append("</div>")
            if ev.get("confirm_needed"):
                o.append('<div class="sub"><b>추가 확인이 필요한 사항</b><ul class="tight">'
                         + "".join(f"<li>{_e(x)}</li>" for x in ev["confirm_needed"]) + "</ul></div>")
            rl = ev.get("redline")
            if rl and rl.get("revised"):
                o.append(f'<div class="redline"><b>문안 수정 제안</b><br>{_e(rl["revised"])}'
                         + (f'<br><span class="meta">제안 이유: {_e(rl["rationale"])}</span>'
                            if rl.get("rationale") else "") + "</div>")
        else:
            o.append('<p class="meta">이 문안은 아직 정밀 검토가 완료되지 않았습니다.</p>')
        o.append("</div></details>")

    # ── 대응 경로 섹션은 두지 않는다.
    # 관계 기관별 검토는 §선결 쟁점의 '대안 경로 비교'(요건·제재·실익)와 §제재 전망(경로별 노출·
    # 벤치마크)이 이미 법적 근거와 함께 다룬다. 여기에 건수 기반 권고 라벨을 한 번 더 넣으면
    # 같은 내용이 세 번 반복되고, 그 라벨은 법적 분석을 더하지 않는다.

    # ── 확인 사항
    sec += 1
    h2(f"{sec}. 제출 전 확인 사항", "gate")
    o.append("<p>본 보고서를 근거로 대외 절차를 진행하시기 전에 아래 사항을 확인하시기 바랍니다.</p>")
    o.append("<ul class='tight'>" + "".join(f"<li>{g}</li>" for g in [
        "사건 당시 시행 법령과 현행 법령의 구분",
        "인용 판례·심결례의 원문, 절차 단계 및 확정 여부",
        "각 문안과 증거의 쪽수·파일 대조",
        "회사 환경성과·지표의 실재 여부 재확인",
        "게시 주체·게시 기간·도달 범위 및 시정 여부",
        "담당 변호사의 최종 승인"]) + "</ul>")

    # ── 부록: 조문 원문
    cited: dict[tuple[str, str], dict] = {}
    cited_ids: set[str] = set()
    for c in detailed:
        for cit in c.get("legal_citations", []):
            cited[(cit["authority_id"], cit["provision_no"])] = cit
            cited_ids.add(cit["authority_id"])
    if cited:
        sec += 1
        h2(f"{sec}. 부록 — 인용 조문 원문", "appendix")
        o.append('<p class="meta">인용한 조문의 원문과 시행일입니다. 필요하실 때 펼쳐 보시기 바랍니다.</p>')
        for aid in sorted(cited_ids):
            a = authorities.get(aid, {})
            o.append(f'<p class="meta">{_e(a.get("title", aid))} {_e(a.get("citation") or "")} — '
                     f'{_e(a.get("source_url", ""))}</p>')
        for cit in cited.values():
            excerpt = cit["text"][:1200] + (" […이하 생략]" if len(cit["text"]) > 1200 else "")
            o.append(f'<details class="appendix"><summary>{_e(cit["title"])} {_e(cit["provision_no"])} '
                     f'{_e(cit.get("heading") or "")}</summary><div class="body">'
                     f'<pre class="law">{html.escape(excerpt)}</pre>'
                     f'<p class="meta">시행일 {_e(cit.get("effective_date") or "[확인 필요]")}</p></div></details>')

    logo = _logo_tag(brand)
    firm = brand.get("firm", "")
    footer_note = brand.get("footer") or firm
    css = CSS_TMPL.format(primary=brand.get("primary", DEFAULT_BRAND["primary"]),
                          primary_dark=brand.get("primary_dark", DEFAULT_BRAND["primary_dark"]))

    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Greenwashing Review — {html.escape(str(ctx.get('company', result['matter_id'])))}</title>
<style>{css}</style></head><body>
<div class="wrap">
<nav>{f'<div class="brandmark">{logo}</div>' if logo else ''}{''.join(nav)}</nav>
<main>
<header class="doc">
{f'<div class="eyebrow">{html.escape(firm)}</div>' if firm else ''}
<h1>Greenwashing Review</h1>
<div class="meta">{html.escape(str(ctx.get('company', '')))} · 작성일 {html.escape(str(result['created_at'])[:10])}</div>
</header>
<div class="notice">본 보고서는 검토 대상 문안의 표시·광고 관련 법적 위험을 정리한 것으로, 담당 변호사의 최종 검토를 거쳐 확정됩니다.
위험도 표시는 대응의 우선순위를 가늠하기 위한 것이며 위법성에 대한 결론이 아닙니다.
인용한 법령과 판례는 대외 절차 진행 전 현행 여부와 확정 여부를 다시 확인하시기 바랍니다.</div>
{''.join(o)}
<footer>{html.escape(footer_note)}{' · ' if footer_note else ''}본 문서는 의뢰인 제공용으로 작성되었으며 외부 배포를 제한합니다. Confidential</footer>
</main></div>
<script>{JS}</script>
</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc, encoding="utf-8")
