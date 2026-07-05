from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS authority_records (
  id TEXT PRIMARY KEY,
  jurisdiction TEXT NOT NULL,
  issuing_body TEXT NOT NULL,
  title TEXT NOT NULL,
  authority_type TEXT NOT NULL,
  legal_status TEXT NOT NULL,
  effective_date TEXT,
  end_date TEXT,
  citation TEXT,
  source_url TEXT NOT NULL,
  sha256 TEXT,
  verified_on TEXT NOT NULL,
  summary_ko TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_records (
  id TEXT PRIMARY KEY,
  jurisdiction TEXT NOT NULL,
  institution TEXT NOT NULL,
  case_number TEXT,
  decision_date TEXT,
  finality TEXT NOT NULL,
  claim_patterns_json TEXT NOT NULL,
  legal_basis_ids_json TEXT NOT NULL,
  holding_ko TEXT NOT NULL,
  remedy_ko TEXT,
  source_url TEXT NOT NULL,
  source_status TEXT NOT NULL,
  verified_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coverage_registry (
  id TEXT PRIMARY KEY,
  jurisdiction TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL,
  search_scope TEXT NOT NULL,
  last_checked TEXT NOT NULL,
  result_count INTEGER NOT NULL,
  included_count INTEGER NOT NULL,
  excluded_count INTEGER NOT NULL,
  duplicate_count INTEGER NOT NULL,
  completion_status TEXT NOT NULL,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS source_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  authority_id TEXT NOT NULL,
  version_id TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  source_url TEXT NOT NULL,
  content_type TEXT NOT NULL,
  local_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  UNIQUE(authority_id, sha256)
);
CREATE TABLE IF NOT EXISTS authority_versions (
  version_id TEXT PRIMARY KEY,
  authority_id TEXT NOT NULL,
  title TEXT NOT NULL,
  promulgation TEXT,
  effective_date TEXT,
  legal_status TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  full_text TEXT NOT NULL,
  full_text_sha256 TEXT NOT NULL,
  FOREIGN KEY(authority_id) REFERENCES authority_records(id)
);
CREATE TABLE IF NOT EXISTS provisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id TEXT NOT NULL,
  authority_id TEXT NOT NULL,
  provision_no TEXT NOT NULL,
  heading TEXT,
  text TEXT NOT NULL,
  text_sha256 TEXT NOT NULL,
  UNIQUE(version_id, provision_no),
  FOREIGN KEY(version_id) REFERENCES authority_versions(version_id),
  FOREIGN KEY(authority_id) REFERENCES authority_records(id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS provisions_fts USING fts5(
  authority_id UNINDEXED, version_id UNINDEXED, provision_no UNINDEXED,
  heading, text, tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS research_candidates (
  id TEXT PRIMARY KEY,
  jurisdiction TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  title TEXT NOT NULL,
  source_url TEXT NOT NULL,
  search_query TEXT NOT NULL,
  discovered_at TEXT NOT NULL,
  status TEXT NOT NULL,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS source_watches (
  id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL,
  last_sha256 TEXT,
  last_checked TEXT NOT NULL,
  changed INTEGER NOT NULL,
  status TEXT NOT NULL,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS matters (
  id TEXT PRIMARY KEY,
  matter_path TEXT NOT NULL,
  mode TEXT NOT NULL,
  context_json TEXT NOT NULL,
  assessment_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def upsert_many(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        allowed = {"authority_records", "case_records", "coverage_registry", "source_snapshots", "authority_versions", "provisions", "research_candidates", "source_watches"}
        if table not in allowed:
            raise ValueError(f"허용되지 않은 테이블: {table}")
        columns = list(rows[0].keys())
        placeholders = ",".join("?" for _ in columns)
        assignments = ",".join(f"{c}=excluded.{c}" for c in columns if c != "id")
        sql = (
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {assignments}"
        )
        self.conn.executemany(sql, [[row.get(c) for c in columns] for row in rows])
        self.conn.commit()
        return len(rows)

    def authorities(self, jurisdiction: str | None = None) -> list[dict[str, Any]]:
        if jurisdiction:
            rows = self.conn.execute(
                "SELECT * FROM authority_records WHERE jurisdiction=? ORDER BY id", (jurisdiction,)
            )
        else:
            rows = self.conn.execute("SELECT * FROM authority_records ORDER BY jurisdiction,id")
        return [dict(row) for row in rows]

    def coverage(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM coverage_registry ORDER BY jurisdiction,id")]

    def save_authority_version(
        self,
        authority: dict[str, Any],
        version: dict[str, Any],
        snapshot: dict[str, Any],
        provisions: list[dict[str, Any]],
    ) -> None:
        self.upsert_many("authority_records", [authority])
        self.conn.execute(
            "UPDATE authority_versions SET legal_status='superseded' WHERE authority_id=? AND version_id<>? AND legal_status='primary_verified'",
            (version["authority_id"], version["version_id"]),
        )
        self.conn.execute(
            """INSERT INTO source_snapshots(authority_id,version_id,retrieved_at,source_url,content_type,local_path,sha256)
               VALUES(?,?,?,?,?,?,?) ON CONFLICT(authority_id,sha256) DO UPDATE SET
               version_id=excluded.version_id,retrieved_at=excluded.retrieved_at,local_path=excluded.local_path""",
            tuple(snapshot[k] for k in ("authority_id","version_id","retrieved_at","source_url","content_type","local_path","sha256")),
        )
        self.conn.execute(
            """INSERT INTO authority_versions(version_id,authority_id,title,promulgation,effective_date,legal_status,
               retrieved_at,source_url,source_sha256,full_text,full_text_sha256)
               VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(version_id) DO UPDATE SET
               title=excluded.title,promulgation=excluded.promulgation,effective_date=excluded.effective_date,
               legal_status=excluded.legal_status,retrieved_at=excluded.retrieved_at,source_url=excluded.source_url,
               source_sha256=excluded.source_sha256,full_text=excluded.full_text,full_text_sha256=excluded.full_text_sha256""",
            tuple(version[k] for k in ("version_id","authority_id","title","promulgation","effective_date","legal_status",
                                       "retrieved_at","source_url","source_sha256","full_text","full_text_sha256")),
        )
        self.conn.execute("DELETE FROM provisions WHERE version_id=?", (version["version_id"],))
        self.conn.execute("DELETE FROM provisions_fts WHERE version_id=?", (version["version_id"],))
        for provision in provisions:
            self.conn.execute(
                "INSERT INTO provisions(version_id,authority_id,provision_no,heading,text,text_sha256) VALUES(?,?,?,?,?,?)",
                (version["version_id"], version["authority_id"], provision["provision_no"], provision.get("heading"),
                 provision["text"], provision["text_sha256"]),
            )
            self.conn.execute(
                "INSERT INTO provisions_fts(authority_id,version_id,provision_no,heading,text) VALUES(?,?,?,?,?)",
                (version["authority_id"], version["version_id"], provision["provision_no"], provision.get("heading", ""), provision["text"]),
            )
        self.conn.commit()

    def current_provision(self, authority_id: str, provision_no: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT p.*,v.effective_date,v.source_url,v.source_sha256,v.full_text_sha256,v.retrieved_at,a.title
               FROM provisions p JOIN authority_versions v ON v.version_id=p.version_id
               JOIN authority_records a ON a.id=p.authority_id
               WHERE p.authority_id=? AND p.provision_no=? AND v.legal_status='primary_verified'
               ORDER BY COALESCE(v.effective_date,'') DESC,v.retrieved_at DESC LIMIT 1""",
            (authority_id, provision_no),
        ).fetchone()
        return dict(row) if row else None

    def corpus_health(self, jurisdiction: str = "KR") -> dict[str, Any]:
        rows = self.conn.execute(
            """SELECT a.id,a.title,a.legal_status,a.verified_on,
               COUNT(DISTINCT CASE WHEN v.legal_status='primary_verified' THEN v.version_id END) version_count,
               COUNT(DISTINCT CASE WHEN v.legal_status='primary_verified' THEN p.id END) provision_count,
               MAX(CASE WHEN v.legal_status='primary_verified' THEN v.retrieved_at END) retrieved_at
               FROM authority_records a LEFT JOIN authority_versions v ON v.authority_id=a.id
               LEFT JOIN provisions p ON p.version_id=v.version_id
               WHERE a.jurisdiction=? GROUP BY a.id ORDER BY a.id""", (jurisdiction,)
        )
        return {"jurisdiction": jurisdiction, "authorities": [dict(row) for row in rows]}

    def save_matter(
        self,
        matter_id: str,
        matter_path: str,
        mode: str,
        context: dict[str, Any],
        assessment: dict[str, Any],
        created_at: str,
    ) -> None:
        self.conn.execute(
            """INSERT INTO matters(id,matter_path,mode,context_json,assessment_json,created_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET matter_path=excluded.matter_path,
               mode=excluded.mode,context_json=excluded.context_json,
               assessment_json=excluded.assessment_json,created_at=excluded.created_at""",
            (
                matter_id,
                matter_path,
                mode,
                json.dumps(context, ensure_ascii=False),
                json.dumps(assessment, ensure_ascii=False),
                created_at,
            ),
        )
        self.conn.commit()

    def load_matter(self, matter_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matters WHERE id=?", (matter_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["context"] = json.loads(data.pop("context_json"))
        data["assessment"] = json.loads(data.pop("assessment_json"))
        return data
