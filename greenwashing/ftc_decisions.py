"""공정위 의결서 자동 수집 (case.ftc.go.kr) — API·토큰 없이 공개 폼 스크래핑.

흐름(검증됨):
  1) GET  /ocp/co/ltfr.do          → TMOSHCooKie 세션 확보
  2) POST /ocp/co/ltfr.do          → searchKrwd·pageIndex로 서버렌더 결과행
     각 행 hidden: csno·blno·csname·ttcnts·apdate·fileId·fileSn·fileNm (메타데이터)
  3) POST /ocp/co/ltfrView.do      → 상세 세션 컨텍스트 설정
  4) POST /ocp/co/getFileList.do   → docId=fileId·docSn=fileSn 로 의결서 PDF 다운로드

raw는 corpus/raw/KR/cases/ 에 저장(gitignore). _manifest.json 이 증분 체크포인트 겸
case_records 초안(사건번호·사건명·조치·의결일). 구조화·검증·편입은 사람이 import-json.
"""
from __future__ import annotations

import csv
import hashlib
import http.cookiejar
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE = "https://case.ftc.go.kr"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
_ROW_FIELDS = ("csno", "blno", "csname", "ttcnts", "apdate", "fileId", "fileSn", "fileNm")


def _opener():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _request(opener, path, data=None, referer=None):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = BASE + referer
    body = urlencode(data, encoding="utf-8").encode() if data is not None else None
    for attempt in range(3):
        try:
            return opener.open(Request(BASE + path, data=body, headers=headers), timeout=30).read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.7 * (attempt + 1))


def _row_fields(tr: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", tr):
        mid = re.search(r'\bid="([^"]+)"', tag)
        mv = re.search(r'\bvalue="([^"]*)"', tag)
        if mid and mv and mid.group(1) in _ROW_FIELDS:
            fields[mid.group(1)] = mv.group(1)
    if len(fields) < len(_ROW_FIELDS):  # id 누락 시 위치 기반 폴백
        vals = [re.search(r'\bvalue="([^"]*)"', t).group(1)
                for t in re.findall(r"<input\b[^>]*>", tr)
                if 'type="hidden"' in t and re.search(r'\bvalue="', t)]
        if len(vals) >= len(_ROW_FIELDS):
            fields = dict(zip(_ROW_FIELDS, vals))
    return fields


def _parse_rows(html: str) -> list[dict[str, str]]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S):
        if "fn_ltfrView" not in tr:
            continue
        fields = _row_fields(tr)
        if fields.get("csno") and fields.get("fileId"):
            rows.append(fields)
    return rows


def _total_count(html: str) -> int | None:
    m = re.search(r"([0-9,]+)\s*건", html)
    return int(m.group(1).replace(",", "")) if m else None


def _download_pdf(opener, row: dict[str, str]) -> bytes:
    _request(opener, "/ocp/co/ltfrView.do", {k: row.get(k, "") for k in _ROW_FIELDS}, referer="/ocp/co/ltfr.do")
    return _request(opener, "/ocp/co/getFileList.do",
                    {"docId": row["fileId"], "docSn": row["fileSn"]}, referer="/ocp/co/ltfrView.do")


def _write_index(cases_dir: Path, seen: dict) -> None:
    """의결일 내림차순 CSV 인덱스 — 사람이 언제든 검색·정렬해 활용(Excel/grep)."""
    rows = sorted(seen.values(), key=lambda r: r.get("apdate", ""), reverse=True)
    with (cases_dir / "_index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["의결일", "사건번호", "의결번호", "조치", "사건명", "키워드", "PDF파일", "다운로드"])
        for r in rows:
            local = Path(r["local_path"]).name if r.get("local_path") else ""
            status = "다운로드완료" if r.get("local_path") else ("실패:" + r.get("download_error", "") if r.get("download_error") else "메타만")
            writer.writerow([r.get("apdate", ""), r.get("csno", ""), r.get("blno", ""), r.get("ttcnts", ""),
                             r.get("csname", ""), r.get("keyword", ""), local, status])


def fetch_decisions(corpus_dir: Path, keywords: list[str], since: str | None = None,
                    max_pages: int | None = None, download: bool = True, delay: float = 1.0) -> dict:
    cases_dir = corpus_dir / "raw" / "KR" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cases_dir / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"decisions": {}}
    seen: dict = manifest["decisions"]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    new_count = downloaded = errors = 0

    for keyword in keywords:
        opener = _opener()
        _request(opener, "/ocp/co/ltfr.do")  # 세션 확보
        page = 1
        while max_pages is None or page <= max_pages:
            html = _request(opener, "/ocp/co/ltfr.do",
                            {"searchKrwd": keyword, "pageIndex": page}, referer="/ocp/co/ltfr.do").decode("utf-8", "replace")
            rows = _parse_rows(html)
            if not rows:
                break
            for row in rows:
                if since and row.get("apdate", "") and row["apdate"] < since:
                    continue
                key = f"{row['csno']}|{row.get('blno', '')}"
                if key in seen:
                    continue
                record = {**row, "keyword": keyword, "retrieved_at": now,
                          "source_url": f"{BASE}/ocp/co/ltfr.do?searchKrwd={keyword}"}
                safe = re.sub(r"[^0-9A-Za-z가-힣]", "_", row["csno"])
                target = cases_dir / f"{safe}__{row.get('fileId', '')}.pdf"
                if target.exists() and target.stat().st_size > 0:  # 재개: 디스크에 이미 있으면 재다운로드 안 함
                    record["local_path"] = str(target)
                    record["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
                    downloaded += 1
                elif download and row.get("fileId"):
                    try:
                        pdf = _download_pdf(opener, row)
                        if pdf and pdf[:4] == b"%PDF":
                            target.write_bytes(pdf)
                            record["local_path"] = str(target)
                            record["sha256"] = hashlib.sha256(pdf).hexdigest()
                            downloaded += 1
                        else:
                            record["download_error"] = "PDF 아님 또는 빈 응답"
                            errors += 1
                    except Exception as exc:  # 개별 실패 격리
                        record["download_error"] = str(exc)
                        errors += 1
                    time.sleep(delay)
                seen[key] = record
                new_count += 1
                if new_count % 25 == 0:  # 주기적 체크포인트(중단 대비 진행 보존)
                    manifest["decisions"] = seen
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    _write_index(cases_dir, seen)
            page += 1
            time.sleep(delay)

    manifest["decisions"] = seen
    manifest["updated_at"] = now
    manifest["keywords"] = sorted(set(manifest.get("keywords", []) + keywords))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_index(cases_dir, seen)
    return {"status": "COMPLETED", "keywords": keywords, "new_decisions": new_count,
            "downloaded_pdfs": downloaded, "download_errors": errors,
            "total_known": len(seen), "cases_dir": str(cases_dir), "manifest": str(manifest_path)}
