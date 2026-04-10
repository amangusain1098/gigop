"""Retrieval-Augmented Generation (RAG) helper for the GigOptimizer assistant.

The :class:`AssistantTrainer` writes two files:

    data/assistant/rag_index.json    - vocabulary + tf-idf weights + postings
    data/assistant/rag_chunks.jsonl  - the raw chunk text

:class:`RAGIndex` loads both and provides a zero-dependency cosine-style
retriever that returns the top-k chunks for a query. The assistant uses it to
ground answers in the user's own knowledge base without leaving the machine.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


@dataclass(slots=True)
class RAGHit:
    """A single retrieval hit."""

    chunk_id: str
    title: str
    text: str
    score: float
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "title": self.title,
            "text": self.text,
            "score": round(self.score, 5),
            "rank": self.rank,
        }


@dataclass(slots=True)
class RAGIndex:
    """In-memory retriever over the trainer's RAG artifacts.

    The index is intentionally minimal: tokens -> tf-idf weights per chunk,
    plus an inverted posting list keyed by term id. At query time we compute
    dot(query_weights, chunk_weights) over the chunks that share at least
    one term and return the top-k.
    """

    vocabulary: list[str]
    term_to_id: dict[str, int]
    idf: dict[int, float]
    doc_weights: list[dict[int, float]]
    postings: dict[int, list[int]]
    chunk_texts: list[str]
    chunk_meta: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @classmethod
    def load(
        cls,
        *,
        index_path: str | Path,
        chunks_path: str | Path,
    ) -> "RAGIndex":
        index_path = Path(index_path)
        chunks_path = Path(chunks_path)
        with index_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        vocabulary: list[str] = list(data.get("vocabulary", []))
        term_to_id = {term: i for i, term in enumerate(vocabulary)}
        idf = {int(k): float(v) for k, v in data.get("idf", {}).items()}
        doc_weights_raw: list[dict[str, float]] = data.get("doc_weights", [])
        doc_weights = [
            {int(term_id): float(weight) for term_id, weight in row.items()}
            for row in doc_weights_raw
        ]
        postings_raw: dict[str, list[int]] = data.get("postings", {})
        postings = {int(k): list(v) for k, v in postings_raw.items()}
        chunk_meta: list[dict[str, Any]] = list(data.get("chunks", []))

        chunk_texts: list[str] = []
        if chunks_path.exists():
            with chunks_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk_texts.append(str(row.get("text") or ""))

        if chunk_texts and len(chunk_texts) != len(doc_weights):
            # Be lenient - chunks file can be truncated
            chunk_texts = chunk_texts[: len(doc_weights)]
            while len(chunk_texts) < len(doc_weights):
                chunk_texts.append("")

        return cls(
            vocabulary=vocabulary,
            term_to_id=term_to_id,
            idf=idf,
            doc_weights=doc_weights,
            postings=postings,
            chunk_texts=chunk_texts,
            chunk_meta=chunk_meta,
        )

    @classmethod
    def empty(cls) -> "RAGIndex":
        return cls(
            vocabulary=[],
            term_to_id={},
            idf={},
            doc_weights=[],
            postings={},
            chunk_texts=[],
            chunk_meta=[],
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    @property
    def n_chunks(self) -> int:
        return len(self.doc_weights)

    def is_empty(self) -> bool:
        return self.n_chunks == 0

    def search(self, query: str, *, k: int = 3) -> list[RAGHit]:
        if not query or self.is_empty():
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        tf = Counter(tokens)
        max_tf = max(tf.values())
        # Build query weight vector (only for known terms).
        query_weights: dict[int, float] = {}
        for term, count in tf.items():
            term_id = self.term_to_id.get(term)
            if term_id is None:
                continue
            idf_weight = self.idf.get(term_id, 1.0)
            query_weights[term_id] = (count / max_tf) * idf_weight
        if not query_weights:
            return []

        # Collect candidate chunk ids via the inverted postings.
        candidates: set[int] = set()
        for term_id in query_weights:
            candidates.update(self.postings.get(term_id, ()))
        if not candidates:
            return []

        scored: list[tuple[float, int]] = []
        q_norm = math.sqrt(sum(w * w for w in query_weights.values())) or 1.0
        for doc_id in candidates:
            doc = self.doc_weights[doc_id]
            dot = 0.0
            for term_id, q_weight in query_weights.items():
                dot += q_weight * doc.get(term_id, 0.0)
            if dot <= 0:
                continue
            doc_norm = math.sqrt(sum(w * w for w in doc.values())) or 1.0
            score = dot / (q_norm * doc_norm)
            scored.append((score, doc_id))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:k]

        hits: list[RAGHit] = []
        for rank, (score, doc_id) in enumerate(top, start=1):
            meta = self.chunk_meta[doc_id] if doc_id < len(self.chunk_meta) else {}
            text = self.chunk_texts[doc_id] if doc_id < len(self.chunk_texts) else ""
            hits.append(
                RAGHit(
                    chunk_id=str(meta.get("id") or f"chunk-{doc_id}"),
                    title=str(meta.get("title") or ""),
                    text=text,
                    score=score,
                    rank=rank,
                )
            )
        return hits

    def render_context(self, query: str, *, k: int = 3, max_chars: int = 1600) -> str:
        """Format the top-k hits as a plain-text block for the LLM prompt."""
        hits = self.search(query, k=k)
        if not hits:
            return ""
        lines: list[str] = ["Knowledge base excerpts:"]
        for hit in hits:
            snippet = (hit.text or "").strip()
            if len(snippet) > max_chars:
                snippet = snippet[:max_chars].rsplit(" ", 1)[0] + "..."
            lines.append(f"[{hit.rank}] {hit.title}: {snippet}")
        return "\n".join(lines)


__all__ = ["RAGIndex", "RAGHit"]
