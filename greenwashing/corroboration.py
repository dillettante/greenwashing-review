from __future__ import annotations

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

from .analysis import ENVIRONMENT_TERMS, _tokens
from .context import load_context
from .korean_corpus import _get


RELEVANT_LINK = re.compile(
    r"환경|지속가능|친환경|탄소|기후|재활용|자원순환|ESG|sustain|environment|climate|carbon|recycl|news|press|홍보|보도",
    re.I,
)
ADVERSE_TERMS = re.compile(
    r"그린워싱|과장|허위|거짓|기만|논란|위반|제재|취소|철회|미달|실패|반박|오염|사고|수사|고발|소송",
    re.I,
)


class _WebPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip = 0
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.link_href: str | None = None
        self.link_text: list[str] = []
        self.title: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag == "a" and not self.skip:
            self.link_href = attrs.get("href")
            self.link_text = []
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag == "a" and self.link_href:
            self.links.append((self.link_href, re.sub(r"\s+", " ", "".join(self.link_text)).strip()))
            self.link_href = None
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        self.text.append(data)
        if self.link_href:
            self.link_text.append(data)
        if self.in_title:
            self.title.append(data)


def _page(body: bytes, url: str) -> tuple[str, str, list[tuple[str, str]]]:
    parser = _WebPageParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    text = re.sub(r"\s+", " ", html.unescape(" ".join(parser.text))).strip()
    title = re.sub(r"\s+", " ", " ".join(parser.title)).strip() or url
    return title, text, parser.links


def _queries(assessment: dict, company: str) -> list[str]:
    company = re.sub(r"\s*(주식회사|㈜|유한회사)\s*", " ", company).strip()
    queries = [
        f'"{company}" 친환경 제품',
        f'"{company}" 탄소중립 그린메탈',
        f'"{company}" 재활용 SGS 인증',
        f'"{company}" 탄소발자국 Carbon Trust',
        f'"{company}" 그린워싱 OR 환경 논란',
    ]
    patterns = {p for claim in assessment.get("claims", [])[:30] for p in claim.get("patterns", [])}
    if "renewable_energy_or_material" in patterns:
        queries.append(f'"{company}" 재생에너지 그린수소')
    return queries


def _save_text(root: Path, record: dict, text: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(record["url"].encode()).hexdigest()[:16]
    target = root / f"{record['kind']}-{key}.txt"
    header = {
        key_name: record.get(key_name)
        for key_name in ("title", "url", "publisher_url", "published_at", "retrieved_at", "kind", "search_query", "status")
        if record.get(key_name) is not None
    }
    target.write_text(json.dumps(header, ensure_ascii=False, indent=2) + "\n\n" + text, encoding="utf-8")
    record["local_path"] = str(target)
    record["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()


def _company_crawl(homepage: str, out_dir: Path, max_pages: int) -> tuple[list[dict], int]:
    origin = urlsplit(homepage).netloc.lower()
    queue: deque[tuple[str, int]] = deque([(homepage, 0)])
    seen: set[str] = set()
    records: list[dict] = []
    fetch_errors = 0
    while queue and len(seen) < max_pages:
        url, depth = queue.popleft()
        clean = url.split("#", 1)[0]
        if clean in seen or urlsplit(clean).netloc.lower() != origin:
            continue
        seen.add(clean)
        try:
            body, final_url, content_type = _get(clean)
        except Exception:
            fetch_errors += 1  # 페이지 수집 실패 — 스냅숏 누락(결과에 표시)
            continue
        if content_type not in {"text/html", "application/xhtml+xml"}:
            continue
        title, text, links = _page(body, final_url)
        if depth == 0 or ENVIRONMENT_TERMS.search(text):
            record = {
                "kind": "company", "title": title, "url": final_url, "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": "fulltext_snapshot", "content_sha256": hashlib.sha256(body).hexdigest(),
            }
            _save_text(out_dir, record, text[:200_000])
            records.append(record)
        if depth >= 2:
            continue
        ranked = []
        for href, anchor in links:
            absolute = urljoin(final_url, href).split("#", 1)[0]
            if urlsplit(absolute).netloc.lower() != origin:
                continue
            if RELEVANT_LINK.search(anchor + " " + absolute):
                ranked.append((absolute, depth + 1))
        for item in ranked[: max_pages * 2]:
            if item[0] not in seen:
                queue.append(item)
    return records, fetch_errors


def _news_search(queries: list[str], out_dir: Path, max_results: int) -> tuple[list[dict], int]:
    records: list[dict] = []
    seen: set[str] = set()
    fetch_errors = 0
    retrieved_at = datetime.now().astimezone().isoformat(timespec="seconds")
    for query in queries:
        url = "https://news.google.com/rss/search?" + urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        try:
            body, _, _ = _get(url)
            root = ET.fromstring(body)
        except Exception:
            fetch_errors += 1  # 검색 질의 실패 — 이 질의의 기사 포인터 전체 누락(결과에 표시)
            continue
        for item in root.findall(".//item")[:max_results]:
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            source = item.find("source")
            publisher_url = source.attrib.get("url") if source is not None else None
            dedupe = publisher_url + title if publisher_url else link
            if not link or dedupe in seen:
                continue
            seen.add(dedupe)
            description = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
            text = re.sub(r"\s+", " ", html.unescape(f"{title} {description}")).strip()
            record = {
                "kind": "news", "title": title, "url": link, "publisher_url": publisher_url,
                "published_at": item.findtext("pubDate"), "retrieved_at": retrieved_at,
                "search_query": query, "status": "search_pointer_only",
            }
            _save_text(out_dir, record, text)
            records.append(record)
    return records, fetch_errors


def _direct_urls(urls: list[str], out_dir: Path) -> tuple[list[dict], int]:
    records = []
    fetch_errors = 0
    for url in urls:
        try:
            body, final_url, content_type = _get(url)
            if content_type not in {"text/html", "application/xhtml+xml"}:
                continue
            title, text, _ = _page(body, final_url)
        except Exception:
            fetch_errors += 1  # 지정 URL 수집 실패 — 스냅숏 누락(결과에 표시)
            continue
        record = {
            "kind": "direct", "title": title, "url": final_url,
            "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "fulltext_snapshot", "content_sha256": hashlib.sha256(body).hexdigest(),
        }
        _save_text(out_dir, record, text[:200_000])
        records.append(record)
    return records, fetch_errors


def _match(assessment: dict, records: list[dict]) -> list[dict]:
    matches = []
    source_texts = []
    for record in records:
        path = Path(record["local_path"])
        text = path.read_text(encoding="utf-8", errors="replace")
        source_texts.append((record, text, _tokens(text)))
    for claim in assessment.get("claims", []):
        claim_tokens = _tokens(claim["quote"])
        if not claim_tokens:
            continue
        for record, text, source_tokens in source_texts:
            score = len(claim_tokens & source_tokens) / max(1, len(claim_tokens))
            if score < 0.14:
                continue
            adverse_haystack = record["title"] if record["kind"] == "company" else (record["title"] + " " + text[:1000])
            matches.append({
                "claim_id": claim["claim_id"], "source_url": record["url"], "source_title": record["title"],
                "source_kind": record["kind"], "match_score": round(score, 3),
                "signal": "potential_adverse_or_contradictory" if ADVERSE_TERMS.search(adverse_haystack) else "corroborating_mention",
                "status": record["status"],
            })
    return sorted(matches, key=lambda item: (-item["match_score"], item["claim_id"]))


def corroborate_matter(
    matter_dir: Path,
    assessment: dict,
    max_company_pages: int = 20,
    max_news_results: int = 5,
    include_company: bool = True,
    include_news: bool = True,
) -> dict:
    context = load_context(matter_dir / "context.yaml")
    company = str(context.get("company") or "").strip()
    if not company:
        raise ValueError("공개자료 검색에는 context.yaml의 company가 필요합니다")
    out_dir = matter_dir / "public-evidence" / "web"
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    fetch_errors = {"company_pages": 0, "news_queries": 0, "direct_urls": 0}  # 침묵 누락 방지 — 결과에 노출
    homepage = str(context.get("company_homepage") or "").strip()
    if include_company and homepage:
        crawled, fetch_errors["company_pages"] = _company_crawl(homepage, out_dir, max_company_pages)
        records.extend(crawled)
    public_urls = context.get("public_urls") or []
    if isinstance(public_urls, str):
        public_urls = [public_urls]
    direct, fetch_errors["direct_urls"] = _direct_urls([str(url) for url in public_urls], out_dir)
    records.extend(direct)
    queries = _queries(assessment, company)
    if include_news:
        news, fetch_errors["news_queries"] = _news_search(queries, out_dir, max_news_results)
        records.extend(news)
    records = list({record["url"]: record for record in records}.values())
    matches = _match(assessment, records)
    result = {
        "matter_id": assessment["matter_id"], "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "queries": queries, "source_count": len(records), "company_source_count": sum(r["kind"] == "company" for r in records),
        "news_pointer_count": sum(r["kind"] == "news" for r in records), "fetch_errors": fetch_errors,
        "matches": matches, "sources": records,
        "caveat": "언론 검색 결과는 기사 원문이 아닌 검색 포인터일 수 있으며, 반복 보도는 독립적 실증이 아니다. 공개자료 일치는 진실성을 자동 확정하거나 위험점수를 낮추지 않는다.",
    }
    output_dir = matter_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "1-corroboration.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 공개자료 교차확인 로그", "", f"- 사건: `{assessment['matter_id']}`", f"- 회사 홈페이지 스냅숏: {result['company_source_count']}건",
        f"- 언론 검색 포인터: {result['news_pointer_count']}건", f"- 주장-자료 문언 매칭: {len(matches)}건",
        f"- 수집 실패(회사페이지/뉴스질의/직접URL): {fetch_errors['company_pages']}/{fetch_errors['news_queries']}/{fetch_errors['direct_urls']}건",
        "", f"> {result['caveat']}", "",
        "## 상충·부정 신호 후보", "",
    ]
    adverse = [m for m in matches if m["signal"] == "potential_adverse_or_contradictory"]
    lines.extend(f"- {m['claim_id']} — [{m['source_title']}]({m['source_url']}) (문언 일치 {m['match_score']:.0%})" for m in adverse[:50])
    lines.extend(["", "## 높은 문언 일치 후보", ""])
    lines.extend(f"- {m['claim_id']} — [{m['source_title']}]({m['source_url']}) ({m['source_kind']}, {m['match_score']:.0%})" for m in matches[:50])
    (output_dir / "1-corroboration.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
