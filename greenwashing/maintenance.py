from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .database import Database
from .korean_corpus import _get, sync_korean_official_corpus


REGISTRY = Path(__file__).with_name("data") / "maintenance_registry.json"
AD_LAW_RELEVANCE = re.compile(r"표시[ㆍ·]광고의\s*공정화에\s*관한\s*법률|표시광고법|환경성\s*표시[ㆍ·]광고|그린워싱", re.I)


def _case_relevant(plain: str) -> bool:
    if AD_LAW_RELEVANCE.search(plain):
        return True
    for match in re.finditer(r"친환경|환경성", plain):
        context = plain[max(0, match.start() - 250): match.end() + 250]
        if re.search(r"광고|표시|상표|상품|제품|품질|오인|소비자", context):
            return True
    return False


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href: str | None = None
        self.label: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href:
            self.links.append((html.unescape(self.href), re.sub(r"\s+", " ", "".join(self.label)).strip()))
            self.href = None

    def handle_data(self, data: str) -> None:
        if self.href:
            self.label.append(data)


def _links(body: bytes, base_url: str) -> list[tuple[str, str]]:
    parser = _LinkParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return [(urljoin(base_url, href), label) for href, label in parser.links]


def _canonical_watch_url(url: str) -> str:
    parts = urlsplit(html.unescape(url))
    path = re.sub(r";jsessionid=[^/?]+", "", parts.path, flags=re.I)
    keep = {"nttSn", "boardId", "boardMasterId", "precSeq", "admRulSeq", "lsiSeq", "seq", "key", "bordCd"}
    query = urlencode(sorted((key, value) for key, value in parse_qsl(parts.query) if key in keep))
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def _current_authorities(db: Database) -> dict[str, dict]:
    rows = db.conn.execute(
        """SELECT authority_id,version_id,effective_date,full_text_sha256,source_sha256,retrieved_at
           FROM authority_versions WHERE legal_status='primary_verified'"""
    )
    return {row["authority_id"]: dict(row) for row in rows}


def _collect_case_candidates(db: Database, queries: list[str], queue_dir: Path, now: str) -> tuple[list[dict], dict]:
    queue_dir.mkdir(parents=True, exist_ok=True)
    found: dict[str, dict] = {}
    skipped = {"query_errors": 0, "case_fetch_errors": 0}  # 침묵 누락 방지 — 보고서에 노출
    for query in queries:
        search_url = "https://www.law.go.kr/LSW/unSc.do?" + urlencode({"menuId": "10", "query": query})
        try:
            body, final_url, _ = _get(search_url)
        except Exception:
            skipped["query_errors"] += 1  # 검색 페이지 실패 — 이 질의의 후보 전체 누락
            continue
        decoded = body.decode("utf-8", errors="replace")
        sequences = sorted(set(re.findall(r"precInfoP\.do\?[^\"']*precSeq=(\d+)", decoded)))
        for sequence in sequences:
            case_url = f"https://www.law.go.kr/LSW/precInfoP.do?precSeq={sequence}"
            candidate_id = f"KR-PREC-{sequence}"
            if candidate_id in found:
                found[candidate_id]["queries"].add(query)
                continue
            try:
                raw, resolved, _ = _get(case_url)
                digest = hashlib.sha256(raw).hexdigest()
                snapshot = queue_dir / f"{candidate_id}-{digest[:12]}.html"
                snapshot.write_bytes(raw)
                title_match = re.search(r"<title>(.*?)</title>", raw.decode("utf-8", errors="replace"), re.S | re.I)
                title = re.sub(r"<[^>]+>|\s+", " ", html.unescape(title_match.group(1))).strip() if title_match else candidate_id
            except Exception:
                skipped["case_fetch_errors"] += 1  # 원문 수집 실패 — 빈 본문은 관련성 필터에 걸려 후보에서 빠짐
                resolved, digest, snapshot, title = case_url, None, None, candidate_id
                raw = b""
            plain = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="replace"))
            if not _case_relevant(plain):
                db.conn.execute(
                    "UPDATE research_candidates SET status='excluded_auto_irrelevant',notes=COALESCE(notes,'') || ? WHERE id=? AND status='pending_human_review'",
                    ("\n고정 환경표시광고 관련성 필터 불충족", candidate_id),
                )
                continue
            found[candidate_id] = {
                "id": candidate_id, "jurisdiction": "KR", "source_kind": "court_case",
                "title": title or candidate_id, "source_url": resolved, "queries": {query},
                "discovered_at": now, "status": "pending_human_review",
                "notes": f"snapshot={snapshot}; sha256={digest}" if snapshot else "원문 수집 실패",
            }
    inserted = []
    for item in found.values():
        item["search_query"] = " | ".join(sorted(item.pop("queries")))
        existing = db.conn.execute("SELECT status FROM research_candidates WHERE id=?", (item["id"],)).fetchone()
        if existing:
            continue
        db.conn.execute(
            """INSERT INTO research_candidates(id,jurisdiction,source_kind,title,source_url,search_query,discovered_at,status,notes)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            tuple(item[k] for k in ("id", "jurisdiction", "source_kind", "title", "source_url", "search_query", "discovered_at", "status", "notes")),
        )
        inserted.append(item)
    db.conn.commit()
    pending = db.conn.execute(
        "SELECT id,notes FROM research_candidates WHERE status='pending_human_review'"
    ).fetchall()
    for row in pending:
        snapshot_match = re.search(r"snapshot=([^;]+)", row["notes"] or "")
        if not snapshot_match:
            continue
        snapshot = Path(snapshot_match.group(1))
        if not snapshot.exists():
            continue
        plain = re.sub(r"<[^>]+>", " ", snapshot.read_text(encoding="utf-8", errors="replace"))
        if not _case_relevant(plain):
            db.conn.execute(
                "UPDATE research_candidates SET status='excluded_auto_irrelevant',notes=COALESCE(notes,'') || ? WHERE id=?",
                ("\n고정 환경표시광고 관련성 필터 불충족", row["id"]),
            )
    db.conn.commit()
    return inserted, skipped


def _watch_official_sources(db: Database, watches: list[dict], now: str) -> list[dict]:
    results = []
    for watch in watches:
        try:
            body, final_url, _ = _get(watch["url"])
            decoded = body.decode("utf-8", errors="replace")
            collected = {
                _canonical_watch_url(url) for url, label in _links(body, final_url)
                if re.search(r"precInfoP|selectBbsNttView|/board/read\.do|admRulInfoP|lsInfoP", url)
            }
            for match in re.findall(r"(?:precInfoP|selectBbsNttView|/board/read|admRulInfoP|lsInfoP)\.do\?[^\"'<>\s]+", decoded):
                raw_url = html.unescape(match)
                collected.add(_canonical_watch_url(urljoin(final_url, raw_url)))
            link_set = sorted(collected)
            digest = hashlib.sha256(json.dumps(link_set, ensure_ascii=False).encode()).hexdigest()
            status = "ok"
        except Exception as exc:
            digest, status, link_set = None, f"error:{type(exc).__name__}", []
        previous = db.conn.execute("SELECT last_sha256 FROM source_watches WHERE id=?", (watch["id"],)).fetchone()
        changed = bool(previous and digest and previous["last_sha256"] != digest)
        db.upsert_many("source_watches", [{
            "id": watch["id"], "source_name": watch["name"], "source_url": watch["url"],
            "last_sha256": digest, "last_checked": now, "changed": int(changed), "status": status,
            "notes": f"검색결과 링크 {len(link_set)}건",
        }])
        results.append({"id": watch["id"], "status": status, "changed": changed, "result_links": len(link_set), "sha256": digest})
    return results


def monitor_corpus(db: Database, project_root: Path, cadence: str) -> dict:
    if cadence not in {"weekly", "monthly", "pre_filing"}:
        raise ValueError("cadence는 weekly, monthly 또는 pre_filing이어야 합니다")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    before = _current_authorities(db)
    try:
        sync = sync_korean_official_corpus(db, project_root / "corpus")
        sync_error = None
    except Exception as exc:
        sync = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        sync_error = sync["error"]
    after = _current_authorities(db)
    authority_changes = []
    for authority_id, current in after.items():
        prior = before.get(authority_id)
        if not prior or prior["version_id"] != current["version_id"] or prior["full_text_sha256"] != current["full_text_sha256"]:
            authority_changes.append({"authority_id": authority_id, "before": prior, "after": current})
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    candidates, candidate_skips = _collect_case_candidates(
        db, registry["case_queries"], project_root / "corpus" / "research-queue" / "KR" / "cases", now
    )
    watches = _watch_official_sources(db, registry["official_watches"], now) if cadence in {"monthly", "pre_filing"} else []
    status = "REVIEW_REQUIRED" if sync_error or authority_changes or candidates or any(w["changed"] or w["status"] != "ok" for w in watches) else "PASS"
    report = {
        "status": status, "cadence": cadence, "created_at": now, "authority_sync": sync,
        "authority_changes": authority_changes, "new_case_candidates": candidates, "candidate_fetch_skipped": candidate_skips,
        "official_watches": watches, "sync_error": sync_error,
        "promotion_rule": "판례·처분 후보는 pending_human_review로만 저장되며 원문·확정 여부·후속절차를 사람이 확인한 뒤 case_records로 승격한다.",
    }
    update_dir = project_root / "corpus" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    json_path = update_dir / f"{stamp}-{cadence}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = update_dir / f"{stamp}-{cadence}.md"
    lines = [
        "# 규제·판례 최신화 보고", "", f"- 실행: {now}", f"- 주기: {cadence}", f"- 상태: **{status}**",
        f"- 규범 변경: {len(authority_changes)}건", f"- 신규 판례 후보: {len(candidates)}건",
        f"- 후보 수집 실패(검색질의/원문): {candidate_skips['query_errors']}건/{candidate_skips['case_fetch_errors']}건",
        f"- 공식 검색 감시: {len(watches)}개",
        f"- 동기화 오류: {sync_error or '없음'}", "",
        "## 규범 변경", "", *(f"- {x['authority_id']}: {x['before']} → {x['after']}" for x in authority_changes), "",
        "## 신규 판례 후보", "", *(f"- [{x['title']}]({x['source_url']}) — {x['search_query']}" for x in candidates), "",
        f"> {report['promotion_rule']}",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["report_json"] = str(json_path)
    report["report_md"] = str(md_path)
    return report
