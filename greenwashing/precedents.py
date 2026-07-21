"""법제처 판례 수집기 — 국가법령정보 DRF API(토큰 불요, OC 계정만).

**핵심**: `search=2`(본문검색)를 써야 한다. 기본값(search=1)은 사건명만 뒤져서
'표시광고' 검색 시 12건뿐이지만, search=2면 1,289건이 나온다(107배). 공정위 의결서
스크래퍼의 searchKrwd/caseNm 구분과 같은 함정이다.

수집 결과는 `corpus/raw/KR-PREC/cases/`에 텍스트+매니페스트로 저장되어
decision_index가 공정위 의결서·UK/US/EU와 동일하게 시맨틱 색인한다.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"
DEFAULT_OC = "mylove00"  # korean-law MCP와 동일한 공개 조회 계정
PAGE_SIZE = 100

# 그린워싱 검토에 반복 쓰이는 기본 검색어(본문검색). 인자 미지정 시 사용.
DEFAULT_KEYWORDS = [
    "표시광고", "부당한 표시", "기만적인 광고", "거짓 과장 광고",
    "소비자 오인", "전체적 인상", "실증책임", "친환경", "환경성 표시",
]


def _get(url: str, params: dict, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            with urlopen(f"{url}?{urlencode(params)}", timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    return ""


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _iso(date_raw: str) -> str:
    """선고일자 '20260416' 또는 '2026.04.16' → '2026-04-16'."""
    digits = re.sub(r"\D", "", str(date_raw or ""))
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) >= 8 else ""


def search_precedents(keyword: str, oc: str = DEFAULT_OC, max_pages: int | None = None,
                      delay: float = 0.4) -> list[dict]:
    """본문검색(search=2)으로 판례 메타를 페이지 순회 수집한다."""
    results, page = [], 1
    while True:
        raw = _get(SEARCH_URL, {"OC": oc, "target": "prec", "type": "JSON", "search": 2,
                                "query": keyword, "display": PAGE_SIZE, "page": page})
        try:
            payload = json.loads(raw).get("PrecSearch", {})
        except json.JSONDecodeError:
            break
        rows = _as_list(payload.get("prec"))
        if not rows:
            break
        results.extend(rows)
        total = int(payload.get("totalCnt") or 0)
        if page * PAGE_SIZE >= total or (max_pages and page >= max_pages):
            break
        page += 1
        time.sleep(delay)
    return results


def fetch_precedent_text(serial: str, oc: str = DEFAULT_OC) -> dict:
    """판례일련번호로 전문(판시사항·판결요지·참조조문·판례내용)을 가져온다."""
    raw = _get(SERVICE_URL, {"OC": oc, "target": "prec", "ID": serial, "type": "JSON"})
    try:
        return json.loads(raw).get("PrecService", {}) or {}
    except json.JSONDecodeError:
        return {}


def _plain(value) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def fetch_precedents(corpus_dir: Path, keywords: list[str] | None = None,
                     since: str | None = None, max_pages: int | None = None,
                     oc: str = DEFAULT_OC, delay: float = 0.4) -> dict:
    """검색어별로 판례를 수집해 corpus/raw/KR-PREC/cases/에 저장(증분: 기존 파일 스킵)."""
    keywords = keywords or DEFAULT_KEYWORDS
    out_dir = corpus_dir / "raw" / "KR-PREC" / "cases"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "_manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {"decisions": {}})
    decisions = manifest["decisions"]

    found = downloaded = skipped = errors = 0
    for keyword in keywords:
        try:
            rows = search_precedents(keyword, oc=oc, max_pages=max_pages, delay=delay)
        except Exception:
            errors += 1
            continue
        for row in rows:
            found += 1
            serial = str(row.get("판례일련번호") or "").strip()
            case_no = str(row.get("사건번호") or "").strip()
            date_iso = _iso(row.get("선고일자"))
            if not serial or not case_no:
                continue
            if since and date_iso and date_iso < since:
                continue
            path = out_dir / f"{serial}.txt"
            if serial in decisions and path.exists():
                skipped += 1
                continue
            body = fetch_precedent_text(serial, oc=oc)
            if not body:
                errors += 1
                continue
            text = "\n\n".join(filter(None, [
                f"[{row.get('법원명','')}] {case_no} {row.get('사건명','')}",
                f"판시사항\n{_plain(body.get('판시사항'))}",
                f"판결요지\n{_plain(body.get('판결요지'))}",
                f"참조조문\n{_plain(body.get('참조조문'))}",
                f"참조판례\n{_plain(body.get('참조판례'))}",
                f"판례내용\n{_plain(body.get('판례내용'))}",
            ]))
            path.write_text(text, encoding="utf-8")
            decisions[serial] = {
                "csno": case_no,                       # 사건번호
                "blno": serial,                        # 판례일련번호
                "csname": str(row.get("사건명") or ""),
                "ttcnts": f"{row.get('법원명','')} {row.get('판결유형','')}".strip(),
                "apdate": date_iso,
                "keyword": keyword,
                "local_path": str(path.resolve()),
                "jurisdiction": "KR-PREC",
            }
            downloaded += 1
            time.sleep(delay)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "COMPLETED", "keywords": len(keywords), "found": found,
            "downloaded": downloaded, "skipped_existing": skipped, "errors": errors,
            "total_in_manifest": len(decisions), "dir": str(out_dir)}
