from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from greenwashing.analysis import assess_matter, risk_band, weighted_score
from greenwashing.models import RiskBand


class AnalysisTests(unittest.TestCase):
    def test_weighted_score_boundaries(self) -> None:
        zeros = {
            "misleading_likelihood": 0,
            "substantiation_gap": 0,
            "scope_or_lifecycle": 0,
            "consumer_materiality": 0,
            "absolute_or_broad": 0,
            "comparison_defect": 0,
            "special_aggravator": 0,
            "dissemination_or_remediation": 0,
        }
        fours = {key: 4 for key in zeros}
        self.assertEqual(weighted_score(zeros), 0)
        self.assertEqual(weighted_score(fours), 100)
        self.assertEqual(risk_band(29), RiskBand.LOW)
        self.assertEqual(risk_band(30), RiskBand.MODERATE)
        self.assertEqual(risk_band(55), RiskBand.HIGH)
        self.assertEqual(risk_band(75), RiskBand.VERY_HIGH)

    def test_assessment_extracts_claims_and_links_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input").mkdir()
            (root / "evidence").mkdir()
            (root / "context.yaml").write_text(
                "matter_id: t-001\ncompany: 예시\nproduct: 병\npublished_date: 2026-01-01\n"
                "medium: 웹사이트 광고\naudience: 일반 소비자\n",
                encoding="utf-8",
            )
            (root / "input" / "ad.txt").write_text(
                "이 제품은 100% 친환경이며 기존 제품보다 탄소배출을 50% 감축했습니다.", encoding="utf-8"
            )
            (root / "evidence" / "test.txt").write_text(
                "제품 탄소배출 감축 비교 대상과 기준연도는 2024년이다.", encoding="utf-8"
            )
            result = assess_matter(root, "confidential")
            self.assertEqual(result.matter_id, "t-001")
            self.assertGreaterEqual(len(result.claims), 1)
            claim = result.claims[0]
            self.assertIn("absolute_claim", claim.patterns)
            self.assertIn("comparison_without_baseline", claim.patterns)
            self.assertTrue(claim.legal_basis_ids)
            self.assertLessEqual(claim.risk_score, 100)

    def test_non_advertising_mandatory_disclosure_is_separated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input").mkdir()
            (root / "context.yaml").write_text(
                "matter_id: t-002\ncompany: 예시\nproduct: 없음\npublished_date: 2026-01-01\n"
                "medium: 지속가능보고서\naudience: 투자자\npurpose: mandatory_disclosure\n",
                encoding="utf-8",
            )
            (root / "input" / "report.txt").write_text(
                "회사는 2030년까지 탄소중립을 달성할 목표를 수립하였다.", encoding="utf-8"
            )
            result = assess_matter(root, "confidential")
            self.assertEqual(result.claims[0].applicability.value, "없음")

    def test_certification_claim_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input").mkdir()
            (root / "context.yaml").write_text(
                "matter_id: t-003\ncompany: 예시\nproduct: 포장\npublished_date: 2026-01-01\n"
                "medium: 포장 광고\naudience: 일반 소비자\n",
                encoding="utf-8",
            )
            (root / "input" / "label.txt").write_text("이 포장에는 환경 인증 마크가 있습니다.", encoding="utf-8")
            result = assess_matter(root, "public")
            self.assertIn("certification_or_label", result.claims[0].patterns)

    def test_public_mentions_do_not_replace_substantiation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input").mkdir()
            (root / "public-evidence").mkdir()
            (root / "context.yaml").write_text(
                "matter_id: t-004\ncompany: 예시\nproduct: 금속\npublished_date: 2026-01-01\n"
                "medium: 지속가능경영보고서\naudience: 일반 소비자\n",
                encoding="utf-8",
            )
            claim = "이 제품은 100% 재활용 원료를 사용한 친환경 제품입니다."
            (root / "input" / "report.txt").write_text(claim, encoding="utf-8")
            (root / "public-evidence" / "news.txt").write_text(claim, encoding="utf-8")
            result = assess_matter(root, "public")
            finding = result.claims[0]
            self.assertEqual(finding.component_scores["substantiation_gap"], 4)
            self.assertTrue(finding.provisional)
            self.assertEqual(finding.evidence[0].source_type, "public_evidence")


if __name__ == "__main__":
    unittest.main()
