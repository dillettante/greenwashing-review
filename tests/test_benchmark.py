"""비교분석 집계의 회귀 테스트.

주안점은 **과잉 일반화 차단**이다 — 같은 회사의 여러 해 보고서를 넣었을 때 표본이 부풀려지거나
한 회사의 반복이 '업계 공통'으로 둔갑하지 않아야 한다. 신고서·조사요청서에 실리는 수치라
조용히 틀리면 안 되는 자리다.

실제 사건 폴더(`matters/`)는 기밀이라 저장소에 없으므로, 최소 구조만 갖춘 임시 사건을 만들어 쓴다.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from greenwashing.benchmark import build_benchmark, sample_confidence
from greenwashing.benchmark_docs import create_benchmark_md


def _make_matter(root: Path, matter_id: str, company: str, published: Any,
                 patterns: list[list[str]], risk: str = "높음") -> Path:
    """비교에 필요한 최소 구조만 갖춘 사건 폴더. patterns 한 칸이 문안 하나가 된다."""
    d = root / matter_id
    (d / "output").mkdir(parents=True)
    claims = [{"claim_id": f"C{i}", "page": i, "quote": f"문안 {i}", "patterns": p,
               "risk_band": risk, "narrative_axis": "축"}
              for i, p in enumerate(patterns, 1)]
    (d / "output" / "1-assessment.json").write_text(json.dumps(
        {"context": {"company": company, "medium": "지속가능경영보고서", "published_date": published},
         "claims": claims}, ensure_ascii=False), encoding="utf-8")
    (d / "output" / "2-evaluation.json").write_text(json.dumps(
        {"matter_id": matter_id,
         "claims": {c["claim_id"]: {"risk_final": risk, "applicability_final": "적용",
                                    "verification": {"verdict": "확인"},
                                    "redline": {"revised": ""}} for c in claims},
         "narratives": [{"axis": "축"}], "exec_summary": {}, "gateway": {}},
        ensure_ascii=False), encoding="utf-8")
    return d


class SampleConfidenceTests(unittest.TestCase):
    def test_thresholds_follow_company_count(self) -> None:
        self.assertEqual(sample_confidence(2)["level"], "weak")
        self.assertEqual(sample_confidence(3)["level"], "moderate")
        self.assertEqual(sample_confidence(5)["level"], "strong")

    def test_extra_reports_of_same_company_do_not_raise_confidence(self) -> None:
        """보고서를 더 넣는다고 업계 표본이 늘지 않는다 — 여기가 뚫리면 가드 전체가 무의미해진다."""
        self.assertEqual(sample_confidence(2, 3)["level"], "weak")
        self.assertEqual(sample_confidence(2, 9)["level"], "weak")
        self.assertIn("보고서 3건", sample_confidence(2, 3)["caveat"])

    def test_single_company_is_labelled_as_trend_not_industry(self) -> None:
        conf = sample_confidence(1, 2)
        self.assertEqual(conf["level"], "single")
        self.assertIn("업계 비교가 아니며", conf["caveat"])


class BenchmarkAxisTests(unittest.TestCase):
    def test_two_distinct_companies_keep_plain_labels(self) -> None:
        """중복이 없으면 연도를 붙이지 않는다(단일 연도 비교의 표를 어지럽히지 않기 위해서다)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _make_matter(root, "a-2025", "가나 주식회사", "2026-01-01", [["절대적 표현"]])
            b = _make_matter(root, "b-2025", "다라 주식회사", "2026-02-01", [["절대적 표현"]])
            bm = build_benchmark([a, b])
        self.assertEqual(bm["labels"], bm["companies"])
        self.assertEqual(bm["sample_confidence"]["level"], "weak")

    def test_same_company_two_years_get_separate_columns(self) -> None:
        """같은 회사 두 해가 한 열로 합쳐지면 앞 연도 수치가 조용히 사라진다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _make_matter(root, "a-2025", "가나 주식회사", "2026-01-01", [["절대적 표현"]])
            b24 = _make_matter(root, "b-2024", "다라 주식회사", 2024,
                               [["절대적 표현"], ["절대적 표현"], ["절대적 표현"]])
            b26 = _make_matter(root, "b-2026", "다라 주식회사", "2026-02-01", [["절대적 표현"]])
            bm = build_benchmark([a, b24, b26])

        self.assertEqual(bm["companies"], ["가나 주식회사", "다라 주식회사"])
        self.assertEqual(bm["labels"],
                         ["가나 주식회사", "다라 주식회사 (2024)", "다라 주식회사 (2026)"])
        per = bm["cross_tab"]["shared"][0]["per_report"]
        self.assertEqual(len(per), 3, "보고서 3건이 각자 열을 가져야 한다")
        self.assertEqual(per["다라 주식회사 (2024)"], 3)
        self.assertEqual(per["다라 주식회사 (2026)"], 1)
        # 표본은 여전히 2개사다
        self.assertEqual(bm["sample_confidence"]["level"], "weak")
        self.assertEqual(bm["cross_tab"]["company_count"], 2)
        self.assertEqual(bm["cross_tab"]["report_count"], 3)

    def test_repeat_within_one_company_is_not_a_shared_pattern(self) -> None:
        """한 회사가 두 해에 걸쳐 반복한 것을 '복수 회사 공통'이라 부르면 없는 관행을 만들어낸다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _make_matter(root, "a-2025", "가나 주식회사", "2026-01-01", [["절대적 표현"]])
            b24 = _make_matter(root, "b-2024", "다라 주식회사", 2024,
                               [["절대적 표현"], ["재활용 주장"]])
            b26 = _make_matter(root, "b-2026", "다라 주식회사", "2026-02-01",
                               [["절대적 표현"], ["재활용 주장"]])
            bm = build_benchmark([a, b24, b26])

        shared = {r["type"] for r in bm["cross_tab"]["shared"]}
        unique = {r["type"] for r in bm["cross_tab"]["unique"]}
        self.assertIn("절대적 표현", shared)       # 두 회사에 모두 있다
        self.assertIn("재활용 주장", unique)        # 다라의 두 해에만 있다 → 개별
        self.assertNotIn("재활용 주장", shared)

    def test_year_falls_back_to_matter_id_when_indistinguishable(self) -> None:
        """게시연도까지 같으면 사건 폴더명으로라도 열을 갈라야 한다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _make_matter(root, "a-1", "가나 주식회사", "2026-01-01", [["절대적 표현"]])
            b = _make_matter(root, "a-2", "가나 주식회사", "2026-06-01", [["절대적 표현"]])
            bm = build_benchmark([a, b])
        self.assertEqual(len(set(bm["labels"])), 2)
        self.assertIn("가나 주식회사 (a-2)", bm["labels"])


class BenchmarkRenderTests(unittest.TestCase):
    def _render(self, matters: list[Path], out: Path, analysis: dict | None = None) -> list[str]:
        bm = build_benchmark(matters)
        create_benchmark_md(bm, analysis or {}, out)
        return [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.startswith("## ")]

    def test_section_numbers_stay_contiguous_when_a_section_drops(self) -> None:
        """'개별 이탈'은 없으면 통째로 빠진다 — 번호를 하드코딩하면 3 다음이 5가 된다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _make_matter(root, "a", "가나 주식회사", "2026-01-01", [["절대적 표현"]])
            b = _make_matter(root, "b", "다라 주식회사", "2026-02-01", [["절대적 표현"]])
            heads = self._render([a, b], root / "out.md")

        numbers = [int(h.split(".")[0].removeprefix("## ")) for h in heads]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_created_at_line_is_omitted_without_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _make_matter(root, "a", "가나 주식회사", "2026-01-01", [["절대적 표현"]])
            b = _make_matter(root, "b", "다라 주식회사", "2026-02-01", [["절대적 표현"]])
            out = root / "out.md"
            self._render([a, b], out)
            self.assertNotIn("작성일:", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
