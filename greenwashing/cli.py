from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import assess_matter, recommend_routes_final, select_shortlist
from .approval import create_approval, require_approval
from .corpus import audit_corpus, import_verified_json, sync_corpus
from .corroboration import corroborate_matter
from .database import Database
from .docx_report import create_assessment_report_docx
from .markdown_docs import (
    create_assessment_report_md,
    create_claims_table_md,
    create_evidence_table_md,
    create_filing_md,
)
from .korean_corpus import sync_korean_official_corpus
from .maintenance import monitor_corpus
from .verification import verify_matter, write_verification_log
from .workbooks import create_workbooks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / ".gw" / "state.sqlite3"


def _db(path: str | None) -> Database:
    return Database(Path(path) if path else DEFAULT_DB)


def _output_dir(matter_path: Path) -> Path:
    return matter_path / "output"


def command_corpus_sync(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        if args.jurisdiction == "KR":
            result = sync_korean_official_corpus(db, PROJECT_ROOT / "corpus")
        else:
            result = sync_corpus(
                db,
                jurisdiction=args.jurisdiction,
                fetch=args.fetch,
                snapshot_dir=PROJECT_ROOT / ".gw" / "snapshots",
            )
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_corpus_audit(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        result = audit_corpus(db, stale_days=args.stale_days)
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


def command_corpus_import(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        result = import_verified_json(db, Path(args.path).expanduser().resolve())
    finally:
        db.close()
    print(json.dumps({"status": "IMPORTED", **result}, ensure_ascii=False, indent=2))
    return 0


def command_corpus_monitor(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        result = monitor_corpus(db, PROJECT_ROOT, args.cadence)
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


def command_corpus_candidates(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        rows = db.conn.execute(
            "SELECT * FROM research_candidates WHERE (? IS NULL OR status=?) ORDER BY discovered_at DESC,id",
            (args.status, args.status),
        )
        result = [dict(row) for row in rows]
    finally:
        db.close()
    print(json.dumps({"count": len(result), "candidates": result}, ensure_ascii=False, indent=2))
    return 0


def command_corpus_candidate_review(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        row = db.conn.execute("SELECT id FROM research_candidates WHERE id=?", (args.candidate_id,)).fetchone()
        if not row:
            raise ValueError(f"후보를 찾을 수 없습니다: {args.candidate_id}")
        db.conn.execute(
            "UPDATE research_candidates SET status=?,notes=COALESCE(notes,'') || ? WHERE id=?",
            (args.status, f"\nreview:{args.notes or ''}", args.candidate_id),
        )
        db.conn.commit()
    finally:
        db.close()
    print(json.dumps({"status": "UPDATED", "candidate_id": args.candidate_id, "review_status": args.status}, ensure_ascii=False, indent=2))
    return 0


def command_corpus_fetch_decisions(args: argparse.Namespace) -> int:
    from .ftc_decisions import fetch_decisions

    keywords, violation, title = args.keyword, args.violation_type, args.title
    if not keywords and not violation and not title:
        # 기본 = 그린워싱 관련: 부당한 표시광고 위반(0609*) + 본문 환경 키워드
        violation = "0609*"
        keywords = ["환경", "친환경", "탄소", "그린", "재활용", "넷제로", "온실가스"]
    result = fetch_decisions(
        PROJECT_ROOT / "corpus",
        keywords=keywords or [],
        since=args.since,
        max_pages=args.max_pages,
        download=not args.no_download,
        delay=args.delay,
        title=title,
        violation_type=violation,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_corpus_index_decisions(args: argparse.Namespace) -> int:
    from .decision_index import index_decisions

    result = index_decisions(PROJECT_ROOT / "corpus", rebuild=args.rebuild)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_corpus_fetch_cases(args: argparse.Namespace) -> int:
    if args.jurisdiction == "UK":
        from .asa_rulings import fetch_asa
        keywords = args.keyword or ["environmental", "green", "carbon", "sustainable", "climate", "recyclable"]
        result = fetch_asa(PROJECT_ROOT / "corpus", keywords=keywords, max_pages=args.max_pages, delay=args.delay)
    elif args.jurisdiction == "US":
        from .ftc_us_cases import fetch_ftc_us
        keywords = args.keyword or ["environmental", "recyclable", "biodegradable", "sustainable", "green guides"]
        result = fetch_ftc_us(PROJECT_ROOT / "corpus", keywords=keywords, max_pages=args.max_pages, delay=args.delay)
    elif args.jurisdiction == "EU":
        from .eu_directives import fetch_eu  # EU는 사건 DB 없음 → 핵심 지침 전문을 EUR-Lex에서 인덱싱
        result = fetch_eu(PROJECT_ROOT / "corpus", delay=args.delay)
    else:
        raise ValueError(f"미지원 관할: {args.jurisdiction}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_corpus_search_decisions(args: argparse.Namespace) -> int:
    from .decision_index import search_decisions

    results = search_decisions(PROJECT_ROOT / "corpus", args.query, k=args.k, action=args.action,
                               since=args.since, jurisdiction=args.jurisdiction)
    print(json.dumps({"query": args.query, "count": len(results), "results": results},
                     ensure_ascii=False, indent=2))
    return 0


def command_assess(args: argparse.Namespace) -> int:
    matter_dir = Path(args.matter_folder).expanduser().resolve()
    result = assess_matter(matter_dir, args.mode)
    if args.with_public_check:
        corroborate_matter(
            matter_dir, result.to_dict(), max_company_pages=args.max_company_pages,
            max_news_results=args.max_news_results,
        )
        result = assess_matter(matter_dir, args.mode)
    output_dir = _output_dir(matter_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    db = _db(args.db)
    try:
        health = db.corpus_health("KR")
        required = {"KR-FAIR-LABELING-ACT", "KR-ENV-TECH-ACT", "KR-ME-ENV-CLAIMS-NOTICE-2025", "KR-KFTC-ENV-AD-GUIDELINE-2023"}
        healthy = {row["id"] for row in health["authorities"] if row["provision_count"] > 0}
        missing = sorted(required - healthy)
        if missing:
            raise RuntimeError("국내 원문 조문 DB가 준비되지 않았습니다. 먼저 `gw corpus sync --jurisdiction KR`을 실행하십시오: " + ", ".join(missing))
        result_dict = result.to_dict()
        corroboration_path = output_dir / "1-corroboration.json"
        if corroboration_path.exists():
            result_dict["corroboration"] = json.loads(corroboration_path.read_text(encoding="utf-8"))
        _attach_legal_citations(result_dict, db)
        evaluated = _attach_evaluation(result_dict, output_dir)
        if evaluated:
            # 경로 메모는 기계점수가 아니라 최종 평가 기준으로(구 자기모순 버그 수정)
            result_dict["route_recommendations"] = recommend_routes_final(result_dict["claims"])
        result_dict["corpus_health"] = health
        _write_shortlist(result, result_dict, output_dir, evaluated)
        assessment_path = output_dir / "1-assessment.json"
        assessment_path.write_text(json.dumps(result_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        authorities = db.authorities()
        authority_map = {row["id"]: row for row in authorities}
        create_assessment_report_md(result_dict, authority_map, output_dir / "3-legal-review-report.md")
        create_assessment_report_docx(result_dict, authority_map, output_dir / "3-legal-review-report.docx")
        create_claims_table_md(result_dict, output_dir / "3-claims-review.md")
        create_evidence_table_md(result_dict, output_dir / "3-evidence-list.md")
        create_workbooks(result_dict, authorities, output_dir)
        db.save_matter(result.matter_id, str(matter_dir), args.mode, result.context, result_dict, result.created_at)
    finally:
        db.close()
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "matter_id": result.matter_id,
                "claims": len(result.claims),
                "claims_source": result.claims_source,
                "output_dir": str(output_dir),
                "warnings": result.warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_corroborate(args: argparse.Namespace) -> int:
    matter_dir = Path(args.matter_folder).expanduser().resolve()
    assessment_path = matter_dir / "output" / "1-assessment.json"
    if assessment_path.exists():
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    else:
        assessment = assess_matter(matter_dir, "public").to_dict()
    result = corroborate_matter(
        matter_dir, assessment, max_company_pages=args.max_company_pages,
        max_news_results=args.max_news_results,
        include_company=not args.no_company, include_news=not args.no_news,
    )
    print(json.dumps({
        "status": "COMPLETED", "matter_id": result["matter_id"], "sources": result["source_count"],
        "matches": len(result["matches"]), "output": str(matter_dir / "output" / "1-corroboration.md"),
        "next_step": f"gw assess {matter_dir} --mode public",
    }, ensure_ascii=False, indent=2))
    return 0


LEGAL_PROVISION_MAP = {
    "KR-FAIR-LABELING-ACT": ["제2조", "제3조", "제5조"],
    "KR-ENV-TECH-ACT": ["제2조", "제16조의10", "제16조의11", "제16조의12"],
    "KR-ME-ENV-CLAIMS-NOTICE-2025": ["제2조", "제5조", "제6조", "제7조"],
    "KR-KFTC-ENV-AD-GUIDELINE-2023": ["Ⅳ", "Ⅴ"],
}


def _attach_legal_citations(result: dict, db: Database) -> None:
    for claim in result["claims"]:
        citations = []
        for authority_id in claim["legal_basis_ids"]:
            for provision_no in LEGAL_PROVISION_MAP.get(authority_id, []):
                row = db.current_provision(authority_id, provision_no)
                if not row:
                    continue
                citations.append({
                    "authority_id": authority_id,
                    "title": row["title"],
                    "provision_no": row["provision_no"],
                    "heading": row.get("heading") or "",
                    "text": row["text"],
                    "effective_date": row["effective_date"],
                    "source_url": row["source_url"],
                    "source_sha256": row["source_sha256"],
                    "full_text_sha256": row["full_text_sha256"],
                    "provision_sha256": row["text_sha256"],
                    "retrieved_at": row["retrieved_at"],
                })
        claim["legal_citations"] = citations
        if not citations:
            raise RuntimeError(f"{claim['claim_id']}: 로컬 조문 DB에서 직접 근거를 찾지 못했습니다")


def _attach_evaluation(result: dict, output_dir: Path) -> int:
    """세션(Claude+korean-law MCP)이 작성한 evaluation.json을 주장별로 병합한다.

    파일이 없으면 기계 트리아지 상태로 남는다(정상). 있으면 각 주장의 실제
    법적 평가(조·항·호, 심결례·판례, 포섭, 오인가능성)를 claim["evaluation"]에 붙인다.
    """
    path = output_dir / "2-evaluation.json"
    if not path.exists():
        result["evaluation_meta"] = None
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    claims_map = data.get("claims", {})
    evaluated = 0
    for claim in result["claims"]:
        payload = claims_map.get(claim["claim_id"])
        if payload:
            claim["evaluation"] = payload
            evaluated += 1
    result["evaluation_meta"] = {
        "evaluated_by": data.get("evaluated_by"),
        "evaluated_at": data.get("evaluated_at"),
        "evaluated_count": evaluated,
    }
    # 사건 수준 평가(P0-2·3): 관문 쟁점(광고 해당성·대안 경로) + 사건 서사 축
    result["gateway"] = data.get("gateway")
    result["narratives"] = data.get("narratives")
    orphans = sorted(set(claims_map) - {c["claim_id"] for c in result["claims"]})
    if orphans:
        result.setdefault("warnings", []).append(
            f"evaluation.json의 주장 {len(orphans)}건이 주장 목록에 없어 병합 누락: {', '.join(orphans[:5])}"
            + (" 외" if len(orphans) > 5 else "") + " — 1-claims.json에 추가하십시오")
    return evaluated


def _write_shortlist(result, result_dict: dict, output_dir: Path, evaluated: int) -> None:
    """세션 정밀평가로 넘길 주장을 shortlist.json과 작업지시로 고정한다.

    LLM 모드(1-claims.json 존재): 세션이 이미 통독·선별했으므로 전량이 대상, 앵커 상태를 표시.
    regex 폴백: 기계 트리아지 상위 20건.
    """
    llm_mode = getattr(result, "claims_source", "regex") == "llm"
    dict_by_id = {c["claim_id"]: c for c in result_dict["claims"]}
    if llm_mode:
        rows = list(result_dict["claims"])
    else:
        shortlist = select_shortlist(result.claims)
        rows = [dict_by_id[c.claim_id] for c in shortlist if c.claim_id in dict_by_id]
    payload = {
        "matter_id": result.matter_id,
        "generated_at": result.created_at,
        "claims_source": getattr(result, "claims_source", "regex"),
        "note": "이 목록은 korean-law MCP 정밀평가 대상이다. EVALUATION-SOP.md 절차로 evaluation.json을 작성하라.",
        "claims": [
            {
                "claim_id": c["claim_id"],
                "page": c["page"],
                "filename": c["filename"],
                "quote": c["quote"],
                "patterns": c["patterns"],
                "subject_scope": c["subject_scope"],
                "anchor": c.get("anchor"),
                "why_flagged": c.get("why_flagged") or "",
                "narrative_axis": c.get("narrative_axis") or "",
                "applicability_mechanical": c["applicability"],
                "risk_score_mechanical": c["risk_score"],
                "legal_basis_ids_mechanical": c["legal_basis_ids"],
                "missing_evidence": c["missing_evidence"],
                "evaluated": bool(c.get("evaluation")),
            }
            for c in rows
        ],
    }
    (output_dir / "1-shortlist.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    anchor_mark = {"anchored": "🔗", "page_corrected": "🔁", "not_found": "⚠️미확인"}
    lines = [f"# 정밀평가 작업지시 — {result.matter_id}", ""]
    if llm_mode:
        bad = sum(1 for c in rows if (c.get("anchor") or {}).get("status") == "not_found")
        lines += [
            f"세션 통독 추출(LLM) {len(rows)}건 전량이 정밀평가 대상입니다. 원문 앵커 미확인 {bad}건은 인용을 재확인하십시오.",
            f"정밀평가 완료: {evaluated}건. 절차는 EVALUATION-SOP.md, 산출물은 output/2-evaluation.json.",
            "",
            "| # | claim_id | 쪽 | 앵커 | 서사 축 | 평가완료 | 주장 요약 |",
            "|---|---|---|---|---|---|---|",
        ]
        for index, c in enumerate(rows, 1):
            summary = c["quote"][:50].replace("|", "/").replace("\n", " ")
            done = "✅" if c.get("evaluation") else "⬜"
            mark = anchor_mark.get((c.get("anchor") or {}).get("status", ""), "?")
            lines.append(f"| {index} | {c['claim_id']} | {c['page']} | {mark} | "
                         f"{(c.get('narrative_axis') or '-')[:14]} | {done} | {summary}… |")
    else:
        lines += [
            f"기계 트리아지가 {len(result.claims)}건 중 {len(rows)}건을 정밀평가 대상으로 추렸습니다.",
            "※ 정규식 폴백 모드 — 어휘 없는 위험 주장을 놓칠 수 있으니 세션 통독 추출(1-claims.json)을 권장합니다.",
            f"정밀평가 완료: {evaluated}건. 절차는 EVALUATION-SOP.md, 산출물은 output/2-evaluation.json.",
            "",
            "| # | claim_id | 쪽 | 기계분류 | 기계점수 | 평가완료 | 주장 요약 |",
            "|---|---|---|---|---|---|---|",
        ]
        for index, c in enumerate(rows, 1):
            summary = c["quote"][:50].replace("|", "/").replace("\n", " ")
            done = "✅" if c.get("evaluation") else "⬜"
            lines.append(
                f"| {index} | {c['claim_id']} | {c['page']} | {c['applicability']} | "
                f"{c['risk_score']} | {done} | {summary}… |"
            )
    (output_dir / "1-worklist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _matter_from_db(db: Database, matter_id: str) -> dict:
    matter = db.load_matter(matter_id)
    if not matter:
        raise ValueError(f"등록되지 않은 matter_id: {matter_id}")
    return matter


def command_approve(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        matter = _matter_from_db(db, args.matter_id)
    finally:
        db.close()
    output_dir = _output_dir(Path(matter["matter_path"]))
    path = create_approval(output_dir, args.reviewer, args.scope)
    print(json.dumps({"status": "APPROVED", "path": str(path), "scope": args.scope}, ensure_ascii=False, indent=2))
    return 0


def command_draft(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        matter = _matter_from_db(db, args.matter_id)
    finally:
        db.close()
    output_dir = _output_dir(Path(matter["matter_path"]))
    routes = ["kftc", "environment", "criminal"] if args.route == "all" else [args.route]
    created: list[str] = []
    filenames = {
        "kftc": "4-filing-kftc-draft.md",
        "environment": "4-filing-environment-draft.md",
        "criminal": "4-filing-criminal-draft.md",
    }
    for route in routes:
        require_approval(output_dir, route if args.route != "all" else "all")
        target = output_dir / filenames[route]
        create_filing_md(matter["assessment"], route, target)
        created.append(str(target))
    print(json.dumps({"status": "COMPLETED", "created": created}, ensure_ascii=False, indent=2))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    db = _db(args.db)
    try:
        matter = _matter_from_db(db, args.matter_id)
        authorities = db.authorities()
    finally:
        db.close()
    output_dir = _output_dir(Path(matter["matter_path"]))
    result = verify_matter(matter, authorities, output_dir)
    write_verification_log(result, output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gw", description="한국법 중심 그린워싱 검토 자동화")
    parser.add_argument("--db", help="SQLite DB 경로")
    sub = parser.add_subparsers(dest="command", required=True)

    corpus = sub.add_parser("corpus", help="규제·사례 DB 관리")
    corpus_sub = corpus.add_subparsers(dest="corpus_command", required=True)
    sync = corpus_sub.add_parser("sync", help="검증된 시드 DB 동기화")
    sync.add_argument("--jurisdiction", choices=["KR", "US", "EU", "UK"])
    sync.add_argument("--fetch", action="store_true", help="공식 원문 스냅숏 다운로드")
    sync.set_defaults(func=command_corpus_sync)
    audit = corpus_sub.add_parser("audit", help="coverage·효력상태·최신성 감사")
    audit.add_argument("--stale-days", type=int, default=45)
    audit.set_defaults(func=command_corpus_audit)
    import_json = corpus_sub.add_parser("import-json", help="사람이 검증한 규제·사례·coverage 레코드 가져오기")
    import_json.add_argument("path")
    import_json.set_defaults(func=command_corpus_import)
    monitor = corpus_sub.add_parser("monitor", help="공식 원문 변경·판례 후보·처분 검색 감시")
    monitor.add_argument("--cadence", choices=["weekly", "monthly", "pre_filing"], default="weekly")
    monitor.set_defaults(func=command_corpus_monitor)
    candidates = corpus_sub.add_parser("candidates", help="판례·처분 검증 대기열 조회")
    candidates.add_argument("--status")
    candidates.set_defaults(func=command_corpus_candidates)
    candidate_review = corpus_sub.add_parser("candidate-review", help="검증 대기 후보 상태 기록")
    candidate_review.add_argument("candidate_id")
    candidate_review.add_argument("--status", choices=["approved_for_import", "excluded", "duplicate", "needs_update"], required=True)
    candidate_review.add_argument("--notes")
    candidate_review.set_defaults(func=command_corpus_candidate_review)
    fetch_dec = corpus_sub.add_parser("fetch-decisions", help="공정위 의결서 자동 수집(case.ftc.go.kr, 토큰 불요)")
    fetch_dec.add_argument("--keyword", action="append", help="본문 검색어(반복 가능). 미지정 시 그린워싱 기본세트")
    fetch_dec.add_argument("--title", help="사건명(caseNm) 검색어")
    fetch_dec.add_argument("--violation-type", help="위반유형 코드. 예 '0609*'=부당한 표시광고")
    fetch_dec.add_argument("--since", help="의결일 YYYY-MM-DD 이상만")
    fetch_dec.add_argument("--max-pages", type=int, help="키워드당 최대 페이지(미지정 시 전체)")
    fetch_dec.add_argument("--no-download", action="store_true", help="메타데이터만 수집, PDF 미다운로드")
    fetch_dec.add_argument("--delay", type=float, default=1.0, help="요청 간 지연(초)")
    fetch_dec.set_defaults(func=command_corpus_fetch_decisions)
    index_dec = corpus_sub.add_parser("index-decisions", help="의결서 로컬 시맨틱 인덱스 구축(LM Studio 임베딩, 증분)")
    index_dec.add_argument("--rebuild", action="store_true", help="전체 재인덱싱")
    index_dec.set_defaults(func=command_corpus_index_decisions)
    search_dec = corpus_sub.add_parser("search-decisions", help="주장으로 관련 의결서·재결 시맨틱 검색")
    search_dec.add_argument("query", help="검색 주장·문구")
    search_dec.add_argument("-k", type=int, default=5, help="반환 건수")
    search_dec.add_argument("--action", help="조치 필터(예: 고발, 과징금, Upheld)")
    search_dec.add_argument("--since", help="의결일 YYYY-MM-DD 이상")
    search_dec.add_argument("--jurisdiction", choices=["KR", "UK", "US", "EU"], help="관할 필터")
    search_dec.set_defaults(func=command_corpus_search_decisions)
    fetch_cases = corpus_sub.add_parser("fetch-cases", help="해외 그린워싱 사례 수집(비교법 보강). 현재 UK=ASA")
    fetch_cases.add_argument("--jurisdiction", choices=["UK", "US", "EU"], required=True)
    fetch_cases.add_argument("--keyword", action="append", help="검색어(반복). 기본 환경 키워드세트")
    fetch_cases.add_argument("--max-pages", type=int, help="키워드당 최대 페이지")
    fetch_cases.add_argument("--delay", type=float, default=1.0)
    fetch_cases.set_defaults(func=command_corpus_fetch_cases)

    assess = sub.add_parser("assess", help="사건 폴더 평가")
    assess.add_argument("matter_folder")
    assess.add_argument("--mode", choices=["public", "confidential"], required=True)
    assess.add_argument("--with-public-check", action="store_true", help="회사 홈페이지·언론 공개자료 수집 후 재평가")
    assess.add_argument("--max-company-pages", type=int, default=20)
    assess.add_argument("--max-news-results", type=int, default=5)
    assess.set_defaults(func=command_assess)

    corroborate = sub.add_parser("corroborate", help="회사 홈페이지·언론보도로 환경주장 교차확인")
    corroborate.add_argument("matter_folder")
    corroborate.add_argument("--max-company-pages", type=int, default=20)
    corroborate.add_argument("--max-news-results", type=int, default=5)
    corroborate.add_argument("--no-company", action="store_true")
    corroborate.add_argument("--no-news", action="store_true")
    corroborate.set_defaults(func=command_corroborate)

    approve = sub.add_parser("approve", help="제출문서 초안 생성 승인")
    approve.add_argument("matter_id")
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--scope", choices=["all", "kftc", "environment", "criminal"], default="all")
    approve.set_defaults(func=command_approve)

    draft = sub.add_parser("draft", help="승인된 제출문서 초안 생성")
    draft.add_argument("matter_id")
    draft.add_argument("--route", choices=["all", "kftc", "environment", "criminal"], required=True)
    draft.set_defaults(func=command_draft)

    verify = sub.add_parser("verify", help="산출물·인용·승인 무결성 검증")
    verify.add_argument("matter_id")
    verify.set_defaults(func=command_verify)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(args.func(args))
    except (ValueError, PermissionError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
