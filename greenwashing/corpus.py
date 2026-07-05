from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from .database import Database


DATA_DIR = Path(__file__).with_name("data")
REQUIRED_FIELDS = {
    "authority_records": {"id", "jurisdiction", "issuing_body", "title", "authority_type", "legal_status", "source_url", "verified_on", "summary_ko"},
    "case_records": {"id", "jurisdiction", "institution", "finality", "claim_patterns_json", "legal_basis_ids_json", "holding_ko", "source_url", "source_status", "verified_on"},
    "coverage_registry": {"id", "jurisdiction", "source_name", "source_url", "search_scope", "last_checked", "result_count", "included_count", "excluded_count", "duplicate_count", "completion_status"},
}


def load_seed() -> dict:
    return json.loads((DATA_DIR / "corpus_seed.json").read_text(encoding="utf-8"))


def sync_corpus(
    db: Database,
    jurisdiction: str | None = None,
    fetch: bool = False,
    snapshot_dir: Path | None = None,
) -> dict:
    seed = load_seed()
    authorities = [
        row for row in seed["authority_records"] if not jurisdiction or row["jurisdiction"] == jurisdiction
    ]
    cases = [row for row in seed["case_records"] if not jurisdiction or row["jurisdiction"] == jurisdiction]
    coverage = [
        row for row in seed["coverage_registry"] if not jurisdiction or row["jurisdiction"] == jurisdiction
    ]
    snapshots: list[dict[str, str]] = []
    if fetch:
        if snapshot_dir is None:
            raise ValueError("--fetch에는 snapshot_dir가 필요합니다")
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for row in authorities:
            req = Request(row["source_url"], headers={"User-Agent": "GreenwashingCounsel/0.1"})
            with urlopen(req, timeout=30) as response:
                content = response.read()
            digest = hashlib.sha256(content).hexdigest()
            target = snapshot_dir / f"{row['id']}.bin"
            target.write_bytes(content)
            row["sha256"] = digest
            snapshots.append({"id": row["id"], "path": str(target), "sha256": digest})
    return {
        "authority_records": db.upsert_many("authority_records", authorities),
        "case_records": db.upsert_many("case_records", cases),
        "coverage_registry": db.upsert_many("coverage_registry", coverage),
        "snapshots": snapshots,
    }


def import_verified_json(db: Database, path: Path) -> dict[str, int]:
    """사람이 검증한 corpus 레코드를 명시적으로 가져온다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("corpus JSON 최상위는 객체여야 합니다")
    counts: dict[str, int] = {}
    for table, required in REQUIRED_FIELDS.items():
        rows = data.get(table, [])
        if not isinstance(rows, list):
            raise ValueError(f"{table}은 배열이어야 합니다")
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise ValueError(f"{table} {index}번째 항목은 객체여야 합니다")
            missing = sorted(required - set(row))
            if missing:
                raise ValueError(f"{table} {index}번째 항목 필수 필드 누락: {', '.join(missing)}")
            if row["jurisdiction"] not in {"KR", "US", "EU", "UK"}:
                raise ValueError(f"{table} {index}번째 항목 관할 오류: {row['jurisdiction']}")
            if not str(row["source_url"]).startswith("https://"):
                raise ValueError(f"{table} {index}번째 항목 공식 HTTPS 원문 URL 필요")
        counts[table] = db.upsert_many(table, rows)
    return counts


def audit_corpus(db: Database, stale_days: int = 45) -> dict:
    authorities = db.authorities()
    coverage = db.coverage()
    now = date.today()
    problems: list[str] = []
    by_jurisdiction: dict[str, int] = {}
    for row in authorities:
        by_jurisdiction[row["jurisdiction"]] = by_jurisdiction.get(row["jurisdiction"], 0) + 1
        if not row["source_url"].startswith("https://"):
            problems.append(f"{row['id']}: HTTPS 공식 원문 URL 없음")
        checked = datetime.strptime(row["verified_on"], "%Y-%m-%d").date()
        if (now - checked).days > stale_days:
            problems.append(f"{row['id']}: 검증일 {row['verified_on']} 이후 {stale_days}일 초과")
        if row["legal_status"] == "proposal_pending" and row["jurisdiction"] != "EU":
            problems.append(f"{row['id']}: proposal_pending 상태 관할 확인 필요")
    coverage_incomplete = [row["id"] for row in coverage if row["completion_status"] != "complete"]
    if coverage_incomplete:
        problems.append("coverage 미완료: " + ", ".join(coverage_incomplete))
    for jurisdiction in ("KR", "US", "EU", "UK"):
        if by_jurisdiction.get(jurisdiction, 0) == 0:
            problems.append(f"{jurisdiction}: authority record 없음")
    health = db.corpus_health("KR")
    pending_candidates = db.conn.execute(
        "SELECT COUNT(*) count FROM research_candidates WHERE status='pending_human_review'"
    ).fetchone()["count"]
    watch_issues = db.conn.execute(
        "SELECT COUNT(*) count FROM source_watches WHERE changed=1 OR status<>'ok'"
    ).fetchone()["count"]
    required_fulltext = {
        "KR-FAIR-LABELING-ACT", "KR-FAIR-LABELING-DECREE", "KR-ENV-TECH-ACT",
        "KR-ENV-TECH-DECREE", "KR-ME-ENV-CLAIMS-NOTICE-2025", "KR-KFTC-ENV-AD-GUIDELINE-2023",
    }
    health_by_id = {row["id"]: row for row in health["authorities"]}
    for authority_id in sorted(required_fulltext):
        row = health_by_id.get(authority_id)
        if not row or row["version_count"] < 1 or row["provision_count"] < 1:
            problems.append(f"{authority_id}: 원문 버전·조문 DB 없음")
    return {
        "status": "PASS" if not problems else "REVIEW_REQUIRED",
        "authority_count": len(authorities),
        "coverage_count": len(coverage),
        "by_jurisdiction": by_jurisdiction,
        "problems": problems,
        "fulltext_health": health,
        "pending_research_candidates": pending_candidates,
        "source_watch_issues": watch_issues,
    }
