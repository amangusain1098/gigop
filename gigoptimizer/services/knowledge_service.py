from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
import zipfile
from html import unescape
from io import StringIO
from pathlib import Path
from typing import Any

from ..config import GigOptimizerConfig
from ..persistence import BlueprintRepository
from ..utils import build_gig_key
from .cache_service import CacheService


class KnowledgeService:
    RETRIEVAL_CACHE_TTL_SECONDS = 20 * 60
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv", ".html", ".htm", ".docx"}

    def __init__(
        self,
        config: GigOptimizerConfig,
        repository: BlueprintRepository,
        cache_service: CacheService | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.cache_service = cache_service
        self.config.uploads_dir.mkdir(parents=True, exist_ok=True)

    def ingest_document(
        self,
        *,
        gig_id: str,
        filename: str,
        content_type: str,
        raw_bytes: bytes,
        source: str = "upload",
    ) -> dict[str, Any]:
        cleaned_name = self._clean_filename(filename)
        if not cleaned_name:
            raise ValueError("A filename is required for uploaded knowledge.")
        if len(raw_bytes) > self.config.knowledge_max_upload_bytes:
            raise ValueError(
                f"Dataset is too large. Keep uploads under {self.config.knowledge_max_upload_bytes // (1024 * 1024)} MB."
            )
        extension = Path(cleaned_name).suffix.lower()
        if extension and extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                "Unsupported dataset type. Upload txt, md, json, csv, html, or docx files."
            )

        normalized_gig_id = build_gig_key(gig_id)
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        existing = self.repository.find_knowledge_document_by_checksum(
            gig_id=normalized_gig_id,
            checksum=checksum,
        )
        if existing is not None:
            return existing

        extracted_text = self._extract_text(
            raw_bytes=raw_bytes,
            filename=cleaned_name,
            content_type=content_type,
        )
        normalized_text = self._normalize_text(extracted_text)
        if not normalized_text:
            raise ValueError("The uploaded dataset did not contain readable text.")

        chunks = self._chunk_text(normalized_text)
        document_id = uuid.uuid4().hex
        target_dir = self.config.uploads_dir / self._clean_path_segment(normalized_gig_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_path = target_dir / f"{document_id}-{cleaned_name}"
        stored_path.write_bytes(raw_bytes)

        metadata = {
            "chunk_count": len(chunks),
            "char_count": len(normalized_text),
            "extension": extension or "unknown",
            "source": source,
        }
        preview = normalized_text[:320]
        document = self.repository.upsert_knowledge_document(
            document_id=document_id,
            gig_id=normalized_gig_id,
            filename=cleaned_name,
            stored_path=str(stored_path),
            content_type=content_type or "application/octet-stream",
            size_bytes=len(raw_bytes),
            checksum=checksum,
            preview=preview,
            metadata=metadata,
            source=source,
            status="ready",
        )
        self.repository.replace_knowledge_chunks(
            document_id=document_id,
            gig_id=normalized_gig_id,
            chunks=[
                {
                    "chunk_index": item["chunk_index"],
                    "content": item["content"],
                    "char_count": item["char_count"],
                    "metadata": {
                        "filename": cleaned_name,
                        "source": source,
                    },
                }
                for item in chunks
            ],
        )
        return self.repository.get_knowledge_document(document_id) or document

    def list_documents(self, *, gig_id: str, limit: int = 20) -> list[dict[str, Any]]:
        normalized_gig_id = build_gig_key(gig_id)
        return self.repository.list_knowledge_documents(gig_id=normalized_gig_id, limit=limit)

    def delete_document(self, *, gig_id: str, document_id: str) -> dict[str, Any]:
        normalized_gig_id = build_gig_key(gig_id)
        document = self.repository.get_knowledge_document(document_id)
        if document is None or document.get("gig_id") != normalized_gig_id:
            raise KeyError(document_id)
        deleted = self.repository.delete_knowledge_document(document_id)
        if deleted is None:
            raise KeyError(document_id)
        stored_path = Path(str(deleted.get("stored_path", "")))
        if stored_path.exists():
            try:
                stored_path.unlink()
            except OSError:
                pass
        return deleted

    def retrieve_context(
        self,
        *,
        gig_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        normalized_gig_id = build_gig_key(gig_id)
        cleaned_query = str(query or "").strip()
        if not cleaned_query:
            return []
        documents = self.repository.list_knowledge_documents(gig_id=normalized_gig_id, limit=50)
        version_bits = [str(item.get("checksum", "")) for item in documents]
        cache_key = self._retrieval_cache_key(normalized_gig_id, cleaned_query, limit, version_bits)
        if self.cache_service is not None:
            cached = self.cache_service.get_json(cache_key)
            if isinstance(cached, list):
                return cached

        tokens = self._query_tokens(cleaned_query)
        if not tokens:
            return []
        documents_by_id = {
            item["id"]: item
            for item in documents
        }
        chunks = self.repository.list_knowledge_chunks(gig_id=normalized_gig_id, limit=500)
        ranked: list[tuple[int, dict[str, Any]]] = []
        for chunk in chunks:
            content = str(chunk.get("content", "")).strip()
            if not content:
                continue
            score = self._score_chunk(tokens, cleaned_query, content)
            if score <= 0:
                continue
            document = documents_by_id.get(str(chunk.get("document_id", "")), {})
            ranked.append(
                (
                    score,
                    {
                        "document_id": chunk.get("document_id"),
                        "filename": document.get("filename", ""),
                        "score": score,
                        "snippet": self._snippet_from_text(content, tokens),
                        "content": content,
                        "metadata": chunk.get("metadata", {}),
                        "created_at": chunk.get("created_at"),
                    },
                )
            )

        ranked.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for _, item in ranked:
            key = (str(item.get("document_id", "")), str(item.get("snippet", "")))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            results.append(item)
            if len(results) >= limit:
                break

        if self.cache_service is not None:
            self.cache_service.set_json(cache_key, results, ttl_seconds=self.RETRIEVAL_CACHE_TTL_SECONDS)
        return results

    def summarize_documents(self, *, gig_id: str, limit: int = 6) -> list[dict[str, Any]]:
        documents = self.list_documents(gig_id=gig_id, limit=limit)
        return [
            {
                "id": item["id"],
                "filename": item["filename"],
                "preview": item.get("preview", ""),
                "chunk_count": (item.get("metadata") or {}).get("chunk_count", 0),
                "char_count": (item.get("metadata") or {}).get("char_count", 0),
                "created_at": item.get("created_at"),
            }
            for item in documents
        ]

    def _extract_text(self, *, raw_bytes: bytes, filename: str, content_type: str) -> str:
        extension = Path(filename).suffix.lower()
        if extension in {".txt", ".md", ".markdown"}:
            return raw_bytes.decode("utf-8", errors="ignore")
        if extension == ".json" or "json" in content_type.lower():
            return self._json_to_text(raw_bytes.decode("utf-8", errors="ignore"))
        if extension == ".csv" or "csv" in content_type.lower():
            return self._csv_to_text(raw_bytes.decode("utf-8", errors="ignore"))
        if extension in {".html", ".htm"} or "html" in content_type.lower():
            return self._html_to_text(raw_bytes.decode("utf-8", errors="ignore"))
        if extension == ".docx":
            return self._docx_to_text(raw_bytes)
        return raw_bytes.decode("utf-8", errors="ignore")

    def _json_to_text(self, payload: str) -> str:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        lines: list[str] = []

        def walk(value: Any, prefix: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    next_prefix = f"{prefix}.{key}" if prefix else str(key)
                    walk(child, next_prefix)
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{prefix}[{index}]")
                return
            lines.append(f"{prefix}: {value}")

        walk(data)
        return "\n".join(lines) or json.dumps(data, indent=2)

    def _csv_to_text(self, payload: str) -> str:
        reader = csv.DictReader(StringIO(payload))
        if not reader.fieldnames:
            return payload
        lines: list[str] = []
        for index, row in enumerate(reader, start=1):
            values = [f"{key}: {value}" for key, value in row.items() if str(value or "").strip()]
            if values:
                lines.append(f"Row {index} | " + " | ".join(values))
            if index >= 500:
                break
        return "\n".join(lines) or payload

    def _html_to_text(self, payload: str) -> str:
        text = re.sub(r"<script[\s\S]*?</script>", " ", payload, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return unescape(text)

    def _docx_to_text(self, raw_bytes: bytes) -> str:
        try:
            from io import BytesIO

            with zipfile.ZipFile(BytesIO(raw_bytes)) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
        except Exception as exc:
            raise ValueError(f"Unable to read the DOCX dataset. {exc}") from exc
        matches = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml)
        return unescape(" ".join(matches))

    def _chunk_text(self, text: str) -> list[dict[str, Any]]:
        chunk_size = max(250, self.config.knowledge_chunk_chars)
        overlap = max(0, min(self.config.knowledge_chunk_overlap_chars, chunk_size // 2))
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[dict[str, Any]] = []
        current = ""
        for paragraph in paragraphs or [text]:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= chunk_size:
                current = candidate
                continue
            if current:
                chunks.append({"chunk_index": len(chunks), "content": current, "char_count": len(current)})
            if len(paragraph) <= chunk_size:
                current = paragraph
                continue
            start = 0
            while start < len(paragraph):
                end = min(len(paragraph), start + chunk_size)
                piece = paragraph[start:end].strip()
                if piece:
                    chunks.append({"chunk_index": len(chunks), "content": piece, "char_count": len(piece)})
                if end >= len(paragraph):
                    break
                start = max(start + 1, end - overlap)
            current = ""
        if current:
            chunks.append({"chunk_index": len(chunks), "content": current, "char_count": len(current)})
        return chunks

    def _normalize_text(self, value: str) -> str:
        text = value.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _query_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in (
                piece.strip(".,!?()[]{}:\"'").lower()
                for piece in str(value or "").replace("/", " ").replace("-", " ").split()
            )
            if len(token) >= 3
        }

    def _score_chunk(self, tokens: set[str], query: str, content: str) -> int:
        haystack = content.lower()
        score = sum(4 for token in tokens if token in haystack)
        phrase = query.lower().strip()
        if phrase and phrase in haystack:
            score += 8
        return score

    def _snippet_from_text(self, text: str, tokens: set[str]) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        best_sentence = ""
        best_score = -1
        for sentence in sentences[:12]:
            score = self._score_chunk(tokens, " ".join(tokens), sentence)
            if score > best_score:
                best_sentence = sentence.strip()
                best_score = score
        snippet = best_sentence or text[:260]
        return snippet[:260].strip()

    def _clean_filename(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(str(value or "dataset")).name).strip("-.")
        return cleaned[:120] or "dataset.txt"

    def _clean_path_segment(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "primary")).strip("-.")
        return cleaned[:120] or "primary"

    def _retrieval_cache_key(self, gig_id: str, query: str, limit: int, version_bits: list[str]) -> str:
        digest = hashlib.sha256(
            f"{gig_id}|{query}|{limit}|{'|'.join(sorted(version_bits))}".encode("utf-8")
        ).hexdigest()
        return f"gigoptimizer:knowledge:{digest}"
