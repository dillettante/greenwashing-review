"""Greenwashing 비교법 RAG — 원격 SSE MCP 서버(사내 LAN 전용).

로컬 stdio 서버(mcp_server.py)와 달리 이 서버는 **공개데이터 검색만** 네트워크로 노출한다:
공정위 표시광고 의결서·UK ASA·US FTC·EU 지침의 시맨틱 검색·전문조회. 끝.

기밀 사건을 다루는 도구(assess_matter·get_shortlist·list_matters·verify_matter 등)는 **의도적으로 제외**한다 —
공유 서버에 의뢰인 문건이 올라가면 안 되기 때문. 그 갈래는 각 변호사 로컬(stdio 서버 또는 CLI)에만 둔다.

같은 사내 LAN에서만 접속(외부 노출 안 함). Mac Studio 상시가동 전제.
실행: `greenwashing-mcp-remote`  ·  env: GW_MCP_HOST(0.0.0.0) GW_MCP_PORT(8766)
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS = PROJECT_ROOT / "corpus"

mcp = FastMCP("greenwashing-search",
              host=os.getenv("GW_MCP_HOST", "0.0.0.0"),
              port=int(os.getenv("GW_MCP_PORT", "8766")))


@mcp.tool()
def search_decisions(query: str, k: int = 5, jurisdiction: str | None = None,
                     action: str | None = None, since: str | None = None) -> list[dict]:
    """주장/문구로 관련 의결서·재결·지침을 시맨틱 검색(그린워싱 비교법 RAG, 공개데이터).

    KR=공정위 표시광고 의결서(직접 근거), UK=ASA 재결·US=FTC 사건·EU=EUR-Lex 지침(비교법).
    jurisdiction(KR/UK/US/EU)·action(고발/과징금/Upheld)·since(YYYY-MM-DD) 필터. 전문은 get_decision(csno).
    결과는 상위 후보 — 인용 전 사람이 원문·관련성·확정여부를 확인해야 한다(할루시네이션 금지).
    """
    from .decision_index import search_decisions as _s
    rows = _s(CORPUS, query, k=k, jurisdiction=jurisdiction, action=action, since=since)
    for r in rows:
        r.pop("pdf", None)  # 서버 로컬경로는 원격에 노출하지 않음(csno로 get_decision)
    return rows


@mcp.tool()
def get_decision(csno: str, jurisdiction: str | None = None) -> dict:
    """사건번호(csno)로 의결서·재결·지침 전문을 반환. search_decisions의 excerpt를 넘어 전체 확인용."""
    from .decision_index import get_decision as _g
    return _g(CORPUS, csno, jurisdiction=jurisdiction)


def main() -> None:
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
