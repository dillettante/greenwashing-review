from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pypdf import PdfReader

from .database import Database


DATA_FILE = Path(__file__).with_name("data") / "kr_official_sources.json"
UA = "GreenwashingCounsel/1.0 (official-source archival client)"


class _ParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.current: list[str] = []
        self.paragraphs: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style"}:
            self.skip += 1
        if tag == "p" and not self.skip:
            self.depth += 1
            if self.depth == 1:
                self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1
        if tag == "p" and self.depth:
            if self.depth == 1:
                text = re.sub(r"\s+", " ", html.unescape("".join(self.current))).strip()
                if text:
                    self.paragraphs.append(text)
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth and not self.skip:
            self.current.append(data)


def _get(url: str, data: bytes | None = None, referer: str | None = None) -> tuple[bytes, str, str]:
    parts = urlsplit(url)
    url = urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe="/%"), quote(parts.query, safe="=&%+"), parts.fragment))
    headers = {"User-Agent": UA}
    if referer:
        ref = urlsplit(referer)
        headers["Referer"] = urlunsplit((ref.scheme, ref.netloc, quote(ref.path, safe="/%"), quote(ref.query, safe="=&%+"), ref.fragment))
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = urlopen(Request(url, data=data, headers=headers), timeout=30)
            return response.read(), response.geturl(), response.headers.get_content_type()
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _resolve_frame(url: str) -> tuple[bytes, str]:
    body, final_url, _ = _get(url)
    decoded = body.decode("utf-8", errors="replace")
    frame = re.search(r'<iframe[^>]+src="([^"]+)"', decoded, re.I)
    if frame:
        framed_url = urljoin(final_url, html.unescape(frame.group(1)))
        body, final_url, _ = _get(framed_url, referer=url)
    return body, final_url


def _law_pdf(canonical_url: str) -> tuple[bytes, str, str]:
    landing, landing_url = _resolve_frame(canonical_url)
    decoded = landing.decode("utf-8", errors="replace")
    seq = re.search(r'id="lsiSeq"\s+value="(\d+)"', decoded)
    if not seq:
        raise RuntimeError(f"현행 법령 일련번호를 찾지 못했습니다: {canonical_url}")
    effective_value = parse_qs(urlsplit(landing_url).query).get("efYd", [None])[0]
    params = f"lsiSeq={seq.group(1)}&joAllCheck=Y&joEfOutPutYn=on&efGubun=Y"
    if effective_value:
        params += f"&efYd={effective_value}"
    pdf_url = "https://www.law.go.kr/LSW/lsPdfPrint.do?" + params
    pdf, final_url, content_type = _get(pdf_url, referer=landing_url)
    if not pdf.startswith(b"%PDF"):
        raise RuntimeError(f"법령 원문 PDF 수집 실패: {canonical_url}")
    text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(pdf)).pages)
    return pdf, final_url, _clean_pdf_text(text)


def _administrative_rule(canonical_url: str) -> tuple[bytes, str, str]:
    landing, landing_url = _resolve_frame(canonical_url)
    decoded = landing.decode("utf-8", errors="replace")
    seq = re.search(r'admRulSeq[:=]"?(\d+)', decoded) or re.search(r'id="admRulSeqA?"\s+value="(\d+)"', decoded)
    rule_id = re.search(r'admRulId[:=]"?(\d+)', decoded)
    if not seq:
        raise RuntimeError(f"현행 행정규칙 일련번호를 찾지 못했습니다: {canonical_url}")
    params = {"admRulSeq": seq.group(1), "joTpYn": "Y", "languageType": "KO", "chrClsCd": "010201"}
    if rule_id:
        params["admRulId"] = rule_id.group(1)
    from urllib.parse import urlencode
    endpoint = "https://www.law.go.kr/LSW/admRulLsInfoR.do?" + urlencode(params)
    body, final_url, _ = _get(endpoint, referer=landing_url)
    parser = _ParagraphParser()
    body_decoded = body.decode("utf-8", errors="replace")
    parser.feed(body_decoded)
    text = "\n".join(parser.paragraphs)
    header = re.search(r'<span class="tx2">(.*?)</span>', decoded, re.S)
    header_text = ""
    if header:
        header_text = re.sub(r"<[^>]+>", "", html.unescape(header.group(1))).strip()
    if not header_text:
        plain_header = re.search(r"\[시행\s+\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\]\s*\[[^\]]+\]", body_decoded)
        if plain_header:
            header_text = plain_header.group(0)
    if header_text:
        text = header_text + "\n" + text
    if len(text) < 500:
        raise RuntimeError(f"행정규칙 본문 수집 실패: {canonical_url}")
    return body, final_url, text


def _clean_pdf_text(text: str) -> str:
    text = re.sub(r"법제처\s+\d+\s+국가법령정보센\s*터", "", text)
    text = re.sub(r"\n(?=[가-힣A-Za-z0-9ㆍ·])", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+(?=제\d+조(?:의\d+)?\()", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _metadata(text: str, fallback_title: str, digest: str) -> dict[str, str | None]:
    header = re.search(r"\[시행\s+(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.)\]\s*\[([^\]]+)\]", text)
    effective_date = None
    promulgation = None
    if header:
        nums = re.findall(r"\d+", header.group(1))
        effective_date = f"{int(nums[0]):04d}-{int(nums[1]):02d}-{int(nums[2]):02d}"
        promulgation = header.group(2).strip()
    version_key = effective_date or digest[:12]
    return {"title": fallback_title, "effective_date": effective_date, "promulgation": promulgation, "version_key": version_key}


def split_provisions(text: str) -> list[dict[str, str]]:
    article_matches = list(re.finditer(r"(?m)^(제\d+조(?:의\d+)?)(?:\(([^\n)]+)\)|\s+삭제)", text))
    roman_matches = list(re.finditer(r"(?m)^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\.\s*([^\n]+)", text))
    matches = roman_matches if len(roman_matches) >= 2 else article_matches
    if not matches:
        return [{"provision_no": "전문", "heading": "전문", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}]
    result: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start():end].strip()
        result.append({
            "provision_no": match.group(1),
            "heading": (match.group(2) or "").strip(),
            "text": body,
            "text_sha256": hashlib.sha256(body.encode()).hexdigest(),
        })
    return result


def sync_korean_official_corpus(db: Database, corpus_dir: Path) -> dict:
    sources = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    retrieved_at = datetime.now().astimezone().isoformat(timespec="seconds")
    raw_dir = corpus_dir / "raw" / "KR"
    parsed_dir = corpus_dir / "verified" / "KR"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for source in sources:
        if source["method"] == "law_pdf":
            raw, resolved_url, text = _law_pdf(source["canonical_url"])
            extension, content_type = ".pdf", "application/pdf"
        else:
            raw, resolved_url, text = _administrative_rule(source["canonical_url"])
            extension, content_type = ".html", "text/html"
        source_hash = hashlib.sha256(raw).hexdigest()
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        meta = _metadata(text, source["title"], source_hash)
        version_id = f"{source['id']}@{meta['version_key']}"
        raw_path = raw_dir / f"{version_id}-{source_hash[:12]}{extension}"
        raw_path.write_bytes(raw)
        provisions = split_provisions(text)
        parsed = {
            "authority_id": source["id"], "version_id": version_id, "title": source["title"],
            "effective_date": meta["effective_date"], "promulgation": meta["promulgation"],
            "retrieved_at": retrieved_at, "source_url": source["canonical_url"],
            "resolved_url": resolved_url, "source_sha256": source_hash, "full_text_sha256": text_hash,
            "provisions": provisions,
        }
        parsed_path = parsed_dir / f"{version_id}.json"
        parsed_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        authority = {
            "id": source["id"], "jurisdiction": "KR", "issuing_body": source["issuing_body"],
            "title": source["title"], "authority_type": source["authority_type"],
            "legal_status": "primary_verified", "effective_date": meta["effective_date"], "end_date": None,
            "citation": source["citation"], "source_url": source["canonical_url"], "sha256": source_hash,
            "verified_on": retrieved_at[:10], "summary_ko": "국가법령정보센터 공식 원문을 로컬 조문 DB로 보존한 현행 규범.",
        }
        version = {
            "version_id": version_id, "authority_id": source["id"], "title": source["title"],
            "promulgation": meta["promulgation"], "effective_date": meta["effective_date"],
            "legal_status": "primary_verified", "retrieved_at": retrieved_at,
            "source_url": source["canonical_url"], "source_sha256": source_hash,
            "full_text": text, "full_text_sha256": text_hash,
        }
        snapshot = {
            "authority_id": source["id"], "version_id": version_id, "retrieved_at": retrieved_at,
            "source_url": resolved_url, "content_type": content_type,
            "local_path": str(raw_path), "sha256": source_hash,
        }
        db.save_authority_version(authority, version, snapshot, provisions)
        results.append({"id": source["id"], "version_id": version_id, "provisions": len(provisions), "sha256": source_hash})
    manifest = {"retrieved_at": retrieved_at, "jurisdiction": "KR", "sources": results}
    (parsed_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
