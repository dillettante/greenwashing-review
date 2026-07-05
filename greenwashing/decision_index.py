"""공정위 의결서 로컬 시맨틱 인덱스 — LM Studio 로컬 임베딩 + numpy 코사인(기밀 안전).

인덱스는 `.gw/decision_index/`(gitignore)에 vectors.npy + chunks.jsonl로 저장한다.
임베딩은 LM Studio(OpenAI 호환 /v1/embeddings)로 로컬 생성 — 외부 API·토큰 0, 주장 문구가 기기 밖으로 안 나감.
규모가 커지면 동일 인터페이스로 Qdrant 백엔드로 교체 가능(payload=메타).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

EMBED_URL = os.getenv("GW_EMBED_URL", "http://localhost:1234/v1/embeddings")
EMBED_MODEL = os.getenv("GW_EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")
_META = ("csno", "blno", "csname", "ttcnts", "apdate", "keyword", "local_path")


def _embed_call(inputs: list[str]) -> list[list[float]]:
    body = json.dumps({"model": EMBED_MODEL, "input": inputs}).encode()
    req = Request(EMBED_URL, data=body, headers={"Content-Type": "application/json"})
    return [item["embedding"] for item in json.loads(urlopen(req, timeout=120).read())["data"]]


def _embed(texts: list[str], prefix: str, batch: int = 16, dim: int = 768) -> np.ndarray:
    """LM Studio 임베딩(nomic 프리픽스). 배치 실패 시 개별 재시도, 개별 실패는 영벡터로 격리(정렬 유지)."""
    try:
        _embed_call([f"{prefix}healthcheck"])  # LM Studio 연결 확인
    except Exception as exc:
        raise RuntimeError(f"LM Studio 임베딩 연결 실패({EMBED_URL}, model={EMBED_MODEL}): {exc}. "
                           "LM Studio에 임베딩 모델이 로드돼 있는지 확인하십시오.") from exc
    out: list[list[float]] = []
    failed = 0
    for start in range(0, len(texts), batch):
        group = [f"{prefix}{t}" for t in texts[start:start + batch]]
        try:
            out.extend(_embed_call(group))
        except Exception:  # 배치 실패 → 개별 재시도로 원인 청크만 격리
            for one in group:
                try:
                    out.extend(_embed_call([one]))
                except Exception:
                    out.append([0.0] * dim)
                    failed += 1
    if failed:
        print(f"[warn] 임베딩 실패 {failed}건은 영벡터로 격리(검색 미노출)", file=sys.stderr)
    arr = np.asarray(out, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-9, None)  # 정규화 → 내적=코사인


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception:
        return ""


def _doc_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return _pdf_text(path)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _iter_decisions(corpus_dir: Path):
    """모든 관할(KR PDF·UK/US/EU 텍스트)의 다운로드된 결정을 jurisdiction 태그와 함께 순회."""
    for jx in ("KR", "UK", "US", "EU"):
        mp = corpus_dir / "raw" / jx / "cases" / "_manifest.json"
        if not mp.exists():
            continue
        for rec in json.loads(mp.read_text(encoding="utf-8"))["decisions"].values():
            if rec.get("local_path"):
                yield {**rec, "jurisdiction": rec.get("jurisdiction", jx)}


def _chunks(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    paras = [p.strip() for p in re.split(r"\n{2,}|\r\n\r\n", text) if p.strip()]
    chunks, buf = [], ""
    for para in paras:
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf} {para}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = (buf[-overlap:] + " " + para).strip() if buf else para
            while len(buf) > size:  # 긴 단락 강제 분할
                chunks.append(buf[:size])
                buf = buf[size - overlap:]
    if buf:
        chunks.append(buf)
    return [c for c in chunks if len(c) >= 30]


def _index_dir(corpus_dir: Path) -> Path:
    return corpus_dir.parent / ".gw" / "decision_index"


def index_decisions(corpus_dir: Path, rebuild: bool = False, max_chunks_per_doc: int = 40) -> dict:
    idir = _index_dir(corpus_dir)
    idir.mkdir(parents=True, exist_ok=True)
    vec_path, meta_path = idir / "vectors.npy", idir / "chunks.jsonl"

    if rebuild:
        vec_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    existing_meta = [json.loads(l) for l in meta_path.read_text(encoding="utf-8").splitlines()] if meta_path.exists() else []
    indexed = {(m.get("jurisdiction", "KR"), m["csno"]) for m in existing_meta}
    vectors = [np.load(vec_path)] if vec_path.exists() and existing_meta else []

    new_meta, new_texts, indexed_docs, skipped = [], [], 0, 0
    for rec in _iter_decisions(corpus_dir):
        if (rec["jurisdiction"], rec.get("csno", "")) in indexed:
            continue
        text = _doc_text(Path(rec["local_path"]))
        cs = _chunks(text)[:max_chunks_per_doc]
        if not cs:
            skipped += 1
            continue
        base = {k: rec.get(k, "") for k in _META}
        base["jurisdiction"] = rec["jurisdiction"]
        header = f"[{rec['jurisdiction']}] {base['csname']} · {base['ttcnts']}"  # 관할·사건명·조치 앵커링
        for i, c in enumerate(cs):
            if len(re.findall(r"[가-힣A-Za-z]", c)) < 40:  # 절차·여백 보일러플레이트 제외(한/영 모두)
                continue
            new_meta.append({**base, "chunk": i, "text": c})
            new_texts.append(f"{header}: {c}")
        indexed_docs += 1

    if new_texts:
        vectors.append(_embed(new_texts, "search_document: "))
        all_vecs = np.vstack(vectors)
        np.save(vec_path, all_vecs)
        with meta_path.open("a", encoding="utf-8") as handle:
            for m in new_meta:
                handle.write(json.dumps(m, ensure_ascii=False) + "\n")
    return {"status": "COMPLETED", "indexed_docs": indexed_docs, "new_chunks": len(new_texts),
            "skipped_no_text": skipped, "total_chunks": len(existing_meta) + len(new_meta),
            "index_dir": str(idir)}


def search_decisions(corpus_dir: Path, query: str, k: int = 5, action: str | None = None,
                     since: str | None = None, jurisdiction: str | None = None) -> list[dict]:
    idir = _index_dir(corpus_dir)
    vec_path, meta_path = idir / "vectors.npy", idir / "chunks.jsonl"
    if not vec_path.exists():
        raise RuntimeError("인덱스가 없습니다. 먼저 `corpus index-decisions`를 실행하십시오.")
    vectors = np.load(vec_path)
    meta = [json.loads(l) for l in meta_path.read_text(encoding="utf-8").splitlines()]
    qv = _embed([query], "search_query: ")[0]
    scores = vectors @ qv
    order = np.argsort(-scores)
    results, seen = [], set()
    for idx in order:
        m = meta[idx]
        jx = m.get("jurisdiction", "KR")
        if jurisdiction and jx != jurisdiction:
            continue
        if action and action not in m.get("ttcnts", ""):
            continue
        if since and m.get("apdate", "") and m["apdate"] < since:
            continue
        if (jx, m["csno"]) in seen:  # 결정당 최고 청크 1개
            continue
        seen.add((jx, m["csno"]))
        results.append({"score": round(float(scores[idx]), 4), "jurisdiction": jx, "csno": m["csno"],
                        "csname": m["csname"], "ttcnts": m["ttcnts"], "apdate": m["apdate"],
                        "keyword": m["keyword"], "excerpt": m["text"][:300], "pdf": m["local_path"]})
        if len(results) >= k:
            break
    return results
