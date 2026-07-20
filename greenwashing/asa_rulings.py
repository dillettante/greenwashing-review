"""UK ASA 재결 수집 (asa.org.uk) — 비교법 보강용 해외 그린워싱 사례. 공개·GET·토큰 0.

robots.txt는 /rulings 허용. 리스트 rulings.html?q={kw}&page={N} → /rulings/{slug}.html.
각 재결의 회사·일자·Ref·결과·본문을 corpus/raw/UK/cases/에 저장(KR과 동일 매니페스트 키 + jurisdiction).
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

BASE = "https://www.asa.org.uk"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def _get(url: str) -> str:
    for attempt in range(3):
        try:
            return urlopen(Request(url, headers={"User-Agent": UA}), timeout=30).read().decode("utf-8", "replace")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.7 * (attempt + 1))


def _strip(html: str) -> str:
    html = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", _html.unescape(html)).strip()


def _iso_date(text: str) -> str:
    m = (re.search(r"Ruling on\s+(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})", text)
         or re.search(r"\b(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})\b", text))  # 폴백: 본문 첫 날짜
    if not m:
        return ""
    day, mon, year = m.group(1), _MONTHS.get(m.group(2), 0), m.group(3)
    return f"{year}-{mon:02d}-{int(day):02d}" if mon else ""


def _parse_ruling(html: str, slug: str) -> dict:
    title = re.search(r"<title>([^<|]+)", html)
    company = title.group(1).replace(" - ASA", "").strip() if title else slug
    ref = re.search(r"Ref:\s*</?[^>]*>?\s*([A-Z]?\d{2}-\d{6,7}|[A-Z]\d{6,7})", html)
    outcome = ""
    for cand in ("Upheld", "Not upheld", "Informally resolved"):
        if re.search(rf">\s*{cand}\s*<", html) or f"Complaint {cand.lower()}" in html.lower():
            outcome = cand
            break
    return {"company": company, "ref": (ref.group(1) if ref else slug[:40]),
            "date": _iso_date(html), "outcome": outcome}


def _list_slugs(keyword: str, page: int) -> list[str]:
    html = _get(f"{BASE}/codes-and-rulings/rulings.html?q={quote(keyword)}&page={page}")
    slugs = re.findall(r'/rulings/([a-z0-9][a-z0-9._-]+)\.html', html)
    skip = {"index", "help-getting-it-right"}
    return list(dict.fromkeys(s for s in slugs if s not in skip))


def _write_index(cases_dir: Path, seen: dict) -> None:
    rows = sorted(seen.values(), key=lambda r: r.get("apdate", ""), reverse=True)
    with (cases_dir / "_index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["일자", "Ref", "결과", "회사/사건명", "키워드", "URL", "파일"])
        for r in rows:
            w.writerow([r.get("apdate", ""), r.get("csno", ""), r.get("ttcnts", ""), r.get("csname", ""),
                        r.get("keyword", ""), r.get("source_url", ""), Path(r.get("local_path", "")).name])


def fetch_asa(corpus_dir: Path, keywords: list[str], max_pages: int | None = None, delay: float = 1.0) -> dict:
    cases_dir = corpus_dir / "raw" / "UK" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cases_dir / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"decisions": {}}
    seen: dict = manifest["decisions"]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    new_count = errors = list_errors = 0

    for keyword in keywords:
        page = 1
        while max_pages is None or page <= max_pages:
            try:
                slugs = _list_slugs(keyword, page)
            except Exception:
                list_errors += 1  # 목록 페이지 실패 — 이 키워드의 남은 페이지가 통째로 누락됨(결과에 표시)
                break
            if not slugs:
                break
            fresh = [s for s in slugs if f"UK|{s}" not in seen]
            for slug in fresh:
                key = f"UK|{slug}"
                try:
                    rhtml = _get(f"{BASE}/rulings/{slug}.html")
                    meta = _parse_ruling(rhtml, slug)
                    text = _strip(rhtml)
                    target = cases_dir / f"{re.sub(r'[^a-z0-9._-]', '_', slug)[:80]}.txt"
                    target.write_text(text, encoding="utf-8")
                    seen[key] = {"jurisdiction": "UK", "csno": meta["ref"], "csname": meta["company"],
                                 "ttcnts": meta["outcome"], "apdate": meta["date"], "keyword": keyword,
                                 "local_path": str(target), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                                 "source_url": f"{BASE}/rulings/{slug}.html", "retrieved_at": now}
                    new_count += 1
                except Exception as exc:
                    errors += 1
                    seen[key] = {"jurisdiction": "UK", "csno": slug[:40], "fetch_error": str(exc), "keyword": keyword}
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
    return {"status": "COMPLETED", "jurisdiction": "UK", "source": "ASA", "keywords": keywords,
            "new_rulings": new_count, "errors": errors, "list_errors": list_errors,
            "total_known": len(seen), "cases_dir": str(cases_dir)}
