"""Greenwashing Counsel — 로컬 stdio MCP 서버.

기존 파이썬 기능을 MCP 도구로 노출한다. Claude Code·Claude 데스크톱 등 어느 MCP 클라이언트에서나
`search_decisions`(KR/UK/US/EU 비교법 RAG)·`assess_matter`(추출·트리아지)·corpus 관리 도구를 부를 수 있다.

설계: MCP = 결정론적 배관(추출·검색·문서생성). ② 법적 판단(조문 포섭·오인가능성)은 여전히 에이전트가
korean-law MCP + 웹으로 수행한다. 기밀 사건이 밖으로 나가지 않도록 **로컬 stdio 전용**이다.
실행: `python3 -m greenwashing.mcp_server` (또는 콘솔 스크립트 `greenwashing-mcp`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parents[1]
mcp = FastMCP("greenwashing")


def _cli(args: list[str]) -> dict:
    """자체 CLI를 서브프로세스로 실행하고 JSON stdout을 파싱(사이드이펙트·오케스트레이션 재사용)."""
    proc = subprocess.run([sys.executable, "-m", "greenwashing", *args],
                          cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=1800)
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out)
    except Exception:
        return {"exit_code": proc.returncode, "stdout": out[-4000:], "stderr": (proc.stderr or "")[-2000:]}


@mcp.tool()
def search_decisions(query: str, k: int = 5, jurisdiction: str | None = None,
                     action: str | None = None, since: str | None = None) -> list[dict]:
    """주장/문구로 관련 의결서·재결·지침을 로컬 시맨틱 검색(그린워싱 비교법 RAG).

    KR=공정위 표시광고 의결서(직접 근거), UK=ASA 재결·US=FTC 사건·EU=EUR-Lex 지침(비교법 보강).
    jurisdiction으로 관할 필터(KR/UK/US/EU), action으로 조치(고발/과징금/Upheld), since로 일자(YYYY-MM-DD) 필터.
    결과는 상위 후보일 뿐 — 인용 전 사람이 원문·관련성·확정여부를 확인해야 한다(할루시네이션 금지).
    ※ 사전에 corpus index-decisions로 인덱스가 있어야 한다(sentence-transformers 임베딩, 첫 실행 시 모델 자동 다운로드).
    """
    from .decision_index import search_decisions as _search
    return _search(PROJECT_ROOT / "corpus", query, k=k, jurisdiction=jurisdiction, action=action, since=since)


@mcp.tool()
def assess_matter(matter_path: str, mode: str = "public", with_public_check: bool = False) -> dict:
    """사건 폴더를 추출·트리아지(①)한다. matter_path는 context.yaml·input/이 있는 폴더.

    환경 주장 추출·기계 위험점수·shortlist(정밀평가 대상)·산출물(.md/.xlsx)을 만든다.
    output/2-evaluation.json이 있으면 병합한다. mode=confidential이면 외부 통신 안 함.
    법적 판단이 아니라 기계 트리아지다 — 이후 ② 정밀평가는 에이전트가 수행한다.
    """
    args = ["assess", matter_path, "--mode", mode]
    if with_public_check:
        args.append("--with-public-check")
    return _cli(args)


@mcp.tool()
def get_shortlist(matter_id: str) -> dict:
    """사건의 정밀평가 대상 shortlist(주장 목록)를 반환한다. assess_matter 실행 후 사용."""
    for base in (PROJECT_ROOT / "matters", PROJECT_ROOT / "examples"):
        path = base / matter_id / "output" / "1-shortlist.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {"error": f"shortlist 없음: {matter_id} (먼저 assess_matter 실행)"}


@mcp.tool()
def list_matters() -> list[str]:
    """로컬 사건 폴더 목록."""
    root = PROJECT_ROOT / "matters"
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


@mcp.tool()
def corpus_status() -> dict:
    """규제 DB·coverage·최신성 감사와 의결서 아카이브 현황."""
    return _cli(["corpus", "audit"])


@mcp.tool()
def verify_matter(matter_id: str) -> dict:
    """산출물·인용·승인 무결성 검증."""
    return _cli(["verify", matter_id])


@mcp.tool()
def index_decisions(rebuild: bool = False) -> dict:
    """수집된 의결서·재결·지침을 로컬 시맨틱 인덱스로 구축(증분, sentence-transformers 임베딩). 오래 걸릴 수 있음."""
    return _cli(["corpus", "index-decisions"] + (["--rebuild"] if rebuild else []))


@mcp.tool()
def fetch_decisions(keyword: list[str] | None = None, since: str | None = None, max_pages: int | None = None) -> dict:
    """공정위 표시광고 의결서를 수집(case.ftc.go.kr, 토큰 불요). 인자 없으면 그린워싱 기본세트. 오래 걸릴 수 있음."""
    args = ["corpus", "fetch-decisions"]
    for kw in (keyword or []):
        args += ["--keyword", kw]
    if since:
        args += ["--since", since]
    if max_pages:
        args += ["--max-pages", str(max_pages)]
    return _cli(args)


@mcp.tool()
def fetch_cases(jurisdiction: str) -> dict:
    """해외 그린워싱 비교법 수집(UK=ASA 재결, US=FTC 사건, EU=EUR-Lex 지침). 오래 걸릴 수 있음."""
    return _cli(["corpus", "fetch-cases", "--jurisdiction", jurisdiction])


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
