from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from greenwashing.approval import create_approval, require_approval
from greenwashing.corpus import audit_corpus, import_verified_json, sync_corpus
from greenwashing.database import Database
from greenwashing.korean_corpus import split_provisions
from greenwashing.maintenance import _canonical_watch_url


class CorpusAndApprovalTests(unittest.TestCase):
    def test_watch_url_removes_session_noise(self) -> None:
        first = _canonical_watch_url(
            "https://www.mcee.go.kr/home/web/board/read.do;jsessionid=ABC?boardId=10&boardMasterId=939&pagerOffset=20"
        )
        second = _canonical_watch_url(
            "https://www.mcee.go.kr/home/web/board/read.do;jsessionid=XYZ?boardMasterId=939&boardId=10&pagerOffset=40"
        )
        self.assertEqual(first, second)

    def test_korean_fulltext_is_split_into_exact_provisions(self) -> None:
        text = "제2조(정의) 정의 본문입니다.\n제3조(금지) 금지 본문입니다."
        provisions = split_provisions(text)
        self.assertEqual([row["provision_no"] for row in provisions], ["제2조", "제3조"])
        self.assertTrue(all(row["text_sha256"] for row in provisions))

    def test_current_provision_returns_version_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "state.sqlite3")
            authority = {
                "id": "KR-TEST", "jurisdiction": "KR", "issuing_body": "법제처", "title": "시험법",
                "authority_type": "statute", "legal_status": "primary_verified", "effective_date": "2026-01-01",
                "end_date": None, "citation": "제1조", "source_url": "https://www.law.go.kr/test",
                "sha256": "a" * 64, "verified_on": "2026-07-05", "summary_ko": "시험",
            }
            version = {
                "version_id": "KR-TEST@2026-01-01", "authority_id": "KR-TEST", "title": "시험법",
                "promulgation": "법률 제1호", "effective_date": "2026-01-01", "legal_status": "primary_verified",
                "retrieved_at": "2026-07-05T00:00:00+09:00", "source_url": authority["source_url"],
                "source_sha256": "a" * 64, "full_text": "제1조(목적) 시험", "full_text_sha256": "b" * 64,
            }
            snapshot = {
                "authority_id": "KR-TEST", "version_id": version["version_id"], "retrieved_at": version["retrieved_at"],
                "source_url": authority["source_url"], "content_type": "application/pdf", "local_path": "/tmp/test.pdf",
                "sha256": "a" * 64,
            }
            provisions = [{"provision_no": "제1조", "heading": "목적", "text": "제1조(목적) 시험", "text_sha256": "c" * 64}]
            try:
                db.save_authority_version(authority, version, snapshot, provisions)
                row = db.current_provision("KR-TEST", "제1조")
                self.assertEqual(row["text"], "제1조(목적) 시험")
                self.assertEqual(row["source_sha256"], "a" * 64)
            finally:
                db.close()

    def test_corpus_sync_separates_pending_eu_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "state.sqlite3")
            try:
                sync_corpus(db)
                authorities = db.authorities()
                proposal = next(row for row in authorities if row["id"] == "EU-GREEN-CLAIMS-PROPOSAL-2023-0085")
                self.assertEqual(proposal["legal_status"], "proposal_pending")
                audit = audit_corpus(db)
                self.assertEqual(audit["status"], "REVIEW_REQUIRED")
                self.assertEqual(audit["by_jurisdiction"]["KR"], 5)
            finally:
                db.close()

    def test_approval_invalidates_when_assessment_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            assessment = output / "1-assessment.json"
            assessment.write_text(json.dumps({"matter_id": "a"}), encoding="utf-8")
            create_approval(output, "홍길동", "all")
            require_approval(output, "all")
            assessment.write_text(json.dumps({"matter_id": "b"}), encoding="utf-8")
            with self.assertRaises(PermissionError):
                require_approval(output, "all")

    def test_corpus_import_rejects_non_https_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "bad.json"
            payload.write_text(
                json.dumps({
                    "authority_records": [{
                        "id": "X", "jurisdiction": "KR", "issuing_body": "기관", "title": "자료",
                        "authority_type": "guideline", "legal_status": "primary_verified",
                        "source_url": "http://example.com", "verified_on": "2026-07-04", "summary_ko": "요약"
                    }]
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            db = Database(root / "state.sqlite3")
            try:
                with self.assertRaises(ValueError):
                    import_verified_json(db, payload)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
