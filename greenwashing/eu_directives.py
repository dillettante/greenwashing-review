"""EU 그린워싱 비교법 — 지침 전문을 EUR-Lex에서 받아 인덱싱(jurisdiction=EU, 입법).

EU는 깨끗한 그린워싱 '사건' DB가 없다. 비교법의 실질 앵커는 지침이므로, 핵심 지침 전문을
corpus/raw/EU/cases/에 저장해 주장별 검색에서 '관련 EU 조문'을 surface한다(사건이 아닌 입법으로 표시).
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
from urllib.request import Request, urlopen

BASE = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
# 큐레이션된 EU 그린워싱 핵심 규범(CELEX, 제목, 유형, 채택일)
DIRECTIVES = [
    ("32024L0825", "Empowering Consumers for the Green Transition Directive (EU) 2024/825", "지침", "2024-02-28"),
    ("32005L0029", "Unfair Commercial Practices Directive 2005/29/EC", "지침", "2005-05-11"),
    ("52023PC0166", "Green Claims Directive proposal COM(2023) 166", "제안", "2023-03-22"),
]


def _get(url: str) -> str:
    for attempt in range(3):
        try:
            return urlopen(Request(url, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.7 * (attempt + 1))


def _text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def fetch_eu(corpus_dir: Path, delay: float = 1.0) -> dict:
    cases_dir = corpus_dir / "raw" / "EU" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cases_dir / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"decisions": {}}
    seen: dict = manifest["decisions"]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    new_count = errors = 0

    for celex, title, kind, date in DIRECTIVES:
        key = f"EU|{celex}"
        try:
            text = _text(_get(BASE + celex))
            if len(text) < 500:
                errors += 1
                continue
            target = cases_dir / f"{celex}.txt"
            target.write_text(text, encoding="utf-8")
            seen[key] = {"jurisdiction": "EU", "csno": celex, "csname": title, "ttcnts": kind,
                         "apdate": date, "keyword": "EU지침", "type": "legislation",
                         "local_path": str(target), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "source_url": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
                         "retrieved_at": now}
            new_count += 1
        except Exception as exc:
            errors += 1
            seen[key] = {"jurisdiction": "EU", "csno": celex, "fetch_error": str(exc)}
        time.sleep(delay)

    manifest["decisions"] = seen
    manifest["updated_at"] = now
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = sorted((v for v in seen.values() if v.get("local_path")), key=lambda r: r.get("csno", ""))
    with (cases_dir / "_index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["CELEX", "유형", "제목", "채택일", "URL"])
        for r in rows:
            w.writerow([r["csno"], r.get("ttcnts", ""), r.get("csname", ""), r.get("apdate", ""), r.get("source_url", "")])
    return {"status": "COMPLETED", "jurisdiction": "EU", "source": "EUR-Lex", "new_directives": new_count,
            "errors": errors, "total_known": len(seen), "cases_dir": str(cases_dir)}
