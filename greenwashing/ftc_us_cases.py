"""US FTC 사건 수집 (ftc.gov legal-library) — 비교법 보강용 해외 그린워싱 집행사례. 공개·GET·토큰 0.

robots.txt는 /legal-library 허용. 브라우즈 ?search={kw}&page={N} → /legal-library/browse/cases-proceedings/{slug}.
각 사건의 회사·요약(field--name-body)·일자를 corpus/raw/US/cases/에 저장(KR/UK와 동일 매니페스트 키 + jurisdiction).
"""
from __future__ import annotations

import csv
import hashlib
import html as _html
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://www.ftc.gov"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
# 사건이 아닌 브라우즈 카테고리 슬러그(제외)
_SKIP = {"adjudicative-proceedings", "banned-debt-collectors", "closing-letters", "commissioner-statements",
         "public-statements", "warning-letters", "refunds", "advisory-opinions", "petitions"}


def _get(url: str) -> str:
    for attempt in range(3):
        try:
            return urlopen(Request(url, headers={"User-Agent": UA}), timeout=30).read().decode("utf-8", "replace")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.7 * (attempt + 1))


def _text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _iso_after(html: str, label: str) -> str:
    seg = html[html.find(label):html.find(label) + 400] if label in html else ""
    m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", seg)
    return f"{m.group(3)}-{_MONTHS.get(m.group(1),0):02d}-{int(m.group(2)):02d}" if m and _MONTHS.get(m.group(1)) else ""


def _parse_case(html: str, slug: str) -> dict:
    title = re.search(r"<title>([^<|]+)", html)
    company = title.group(1).strip() if title else slug
    body = re.search(r'field--name-body.*?<div[^>]*>(.*?)</div>\s*</div>', html, re.S)
    summary = _text(body.group(1)) if body else ""
    if not summary:
        og = re.search(r'property="og:description"[^>]*content="([^"]*)"', html)
        summary = _html.unescape(og.group(1)) if og else ""
    docket = re.search(r'(Docket Number|FTC Matter/File Number)\s*</[^>]+>\s*<[^>]+>\s*([0-9A-Za-z-]{3,30})', html)
    return {"company": company, "summary": summary, "date": _iso_after(html, "Last Updated"),
            "docket": (docket.group(2) if docket else slug[:20])}


def _list_slugs(keyword: str, page: int) -> list[str]:
    html = _get(f"{BASE}/legal-library/browse/cases-proceedings?search={quote(keyword)}&page={page}")
    slugs = re.findall(r'/legal-library/browse/cases-proceedings/([a-z0-9][a-z0-9-]+)', html)
    return list(dict.fromkeys(s for s in slugs if s not in _SKIP))


def _write_index(cases_dir: Path, seen: dict) -> None:
    rows = sorted(seen.values(), key=lambda r: r.get("apdate", ""), reverse=True)
    with (cases_dir / "_index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["date", "docket", "company/case", "keyword", "url", "file"])
        for r in rows:
            w.writerow([r.get("apdate", ""), r.get("csno", ""), r.get("csname", ""),
                        r.get("keyword", ""), r.get("source_url", ""), Path(r.get("local_path", "")).name])


def fetch_ftc_us(corpus_dir: Path, keywords: list[str], max_pages: int | None = None, delay: float = 1.0) -> dict:
    cases_dir = corpus_dir / "raw" / "US" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cases_dir / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"decisions": {}}
    seen: dict = manifest["decisions"]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    new_count = errors = list_errors = 0

    for keyword in keywords:
        page = 0
        while max_pages is None or page < max_pages:
            try:
                slugs = _list_slugs(keyword, page)
            except Exception:
                list_errors += 1  # 목록 페이지 실패 — 이 키워드의 남은 페이지가 통째로 누락됨(결과에 표시)
                break
            fresh = [s for s in slugs if f"US|{s}" not in seen]
            if not slugs or not fresh:  # 새 사건이 없으면 이 키워드 종료
                break
            for slug in fresh:
                key = f"US|{slug}"
                try:
                    chtml = _get(f"{BASE}/legal-library/browse/cases-proceedings/{slug}")
                    meta = _parse_case(chtml, slug)
                    text = f"{meta['company']}. {meta['summary']}".strip()
                    if len(text) < 40:
                        seen[key] = {"jurisdiction": "US", "csno": meta["docket"], "skipped": "본문 없음", "keyword": keyword}
                        continue
                    target = cases_dir / f"{re.sub(r'[^a-z0-9-]', '_', slug)[:80]}.txt"
                    target.write_text(text, encoding="utf-8")
                    seen[key] = {"jurisdiction": "US", "csno": meta["docket"], "csname": meta["company"],
                                 "ttcnts": "", "apdate": meta["date"], "keyword": keyword,
                                 "local_path": str(target), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                                 "source_url": f"{BASE}/legal-library/browse/cases-proceedings/{slug}", "retrieved_at": now}
                    new_count += 1
                except Exception as exc:
                    errors += 1
                    seen[key] = {"jurisdiction": "US", "csno": slug[:20], "fetch_error": str(exc), "keyword": keyword}
                time.sleep(delay)
                if new_count % 25 == 0:
                    manifest["decisions"] = seen
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            page += 1
            time.sleep(delay)

    manifest["decisions"] = seen
    manifest["updated_at"] = now
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_index(cases_dir, {k: v for k, v in seen.items() if v.get("local_path")})
    return {"status": "COMPLETED", "jurisdiction": "US", "source": "FTC", "keywords": keywords,
            "new_cases": new_count, "errors": errors, "list_errors": list_errors,
            "total_known": len(seen), "cases_dir": str(cases_dir)}
