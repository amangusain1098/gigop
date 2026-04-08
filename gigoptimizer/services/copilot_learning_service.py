from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import httpx

from ..config import GigOptimizerConfig
from ..persistence import BlueprintRepository
from .cache_service import CacheService
from .knowledge_service import KnowledgeService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CopilotLearningService:
    GLOBAL_GIG_ID = "copilot-global-knowledge"
    STATUS_CACHE_KEY = "gigoptimizer:copilot-learning:status"
    STATUS_CACHE_TTL_SECONDS = 10 * 60
    QUERY_CACHE_TTL_SECONDS = 20 * 60
    USER_AGENT = "GigOptimizerCopilot/1.0 (+https://animha.co.in/dashboard)"
    GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    NS = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "atom": "http://www.w3.org/2005/Atom",
    }
    DEFAULT_SOURCES = [
        {
            "slug": "mdn-blog",
            "title": "MDN Blog",
            "feed_url": "https://developer.mozilla.org/en-US/blog/rss.xml",
            "focus": ["web", "javascript", "frontend", "performance"],
        },
        {
            "slug": "python-insider",
            "title": "Python Insider",
            "feed_url": "https://pythoninsider.blogspot.com/feeds/posts/default?alt=rss",
            "focus": ["python", "backend", "release notes"],
        },
        {
            "slug": "cloudflare-blog",
            "title": "Cloudflare Blog",
            "feed_url": "https://blog.cloudflare.com/rss/",
            "focus": ["security", "networking", "firewalls", "performance"],
        },
        {
            "slug": "github-blog",
            "title": "GitHub Blog",
            "feed_url": "https://github.blog/feed/",
            "focus": ["developer tools", "ai", "automation", "platform"],
        },
        {
            "slug": "stack-overflow-blog",
            "title": "Stack Overflow Blog",
            "feed_url": "https://stackoverflow.blog/feed/",
            "focus": ["engineering", "software", "ai", "career"],
        },
    ]
    DEFAULT_QUERY_TOPICS = [
        "agentic AI coding",
        "programming languages software engineering",
        "python fastapi backend",
        "javascript typescript react",
        "docker redis postgres devops",
        "linux firewall security",
    ]
    QUERY_TOPIC_MAP = {
        "python": ["python backend tutorial", "python fastapi api"],
        "fastapi": ["fastapi python api", "python backend tutorial"],
        "javascript": ["javascript web development", "typescript react frontend"],
        "typescript": ["typescript react frontend", "javascript web development"],
        "react": ["react frontend development", "typescript react frontend"],
        "node": ["node.js backend development", "javascript backend api"],
        "docker": ["docker devops containers", "docker compose deployment"],
        "redis": ["redis caching backend", "redis worker queue"],
        "postgres": ["postgres backend engineering", "postgres performance tuning"],
        "firewall": ["linux firewall ufw", "cloudflare firewall security"],
        "security": ["application security engineering", "linux firewall ufw"],
        "agentic": ["agentic AI coding", "AI agents software engineering"],
        "ai": ["agentic AI coding", "AI software engineering"],
        "ml": ["machine learning engineering", "AI model deployment"],
        "golang": ["golang backend engineering"],
        "go": ["golang backend engineering"],
        "rust": ["rust systems programming"],
        "java": ["java backend engineering"],
        "kubernetes": ["kubernetes devops platform"],
        "nginx": ["nginx reverse proxy security"],
    }

    def __init__(
        self,
        config: GigOptimizerConfig,
        repository: BlueprintRepository,
        knowledge_service: KnowledgeService,
        cache_service: CacheService | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.knowledge_service = knowledge_service
        self.cache_service = cache_service
        self.learning_dir = (self.config.data_dir / "copilot_learning").resolve()
        self.snapshot_dir = self.learning_dir / "snapshots"
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def sync_sources(self, *, force: bool = False) -> dict[str, Any]:
        started_at = utc_now()
        source_results: list[dict[str, Any]] = []
        total_new_documents = 0
        total_documents_seen = 0
        error_count = 0

        all_sources = self._iter_continuous_sources()
        for source in all_sources:
            try:
                items = self._fetch_feed_items(source)
                inserted = 0
                reused = 0
                for item in items[:6]:
                    payload = self._item_to_document(source, item)
                    raw_bytes = payload["content"].encode("utf-8")
                    checksum = hashlib.sha256(raw_bytes).hexdigest()
                    existing = self.repository.find_knowledge_document_by_checksum(
                        gig_id=self.GLOBAL_GIG_ID,
                        checksum=checksum,
                    )
                    self.knowledge_service.ingest_document(
                        gig_id=self.GLOBAL_GIG_ID,
                        filename=payload["filename"],
                        content_type="text/plain",
                        raw_bytes=raw_bytes,
                        source="copilot_feed",
                    )
                    total_documents_seen += 1
                    if existing is None:
                        inserted += 1
                        total_new_documents += 1
                    else:
                        reused += 1
                source_results.append(
                    {
                        "slug": source["slug"],
                        "title": source["title"],
                        "status": "ok",
                        "fetched_items": len(items[:6]),
                        "new_documents": inserted,
                        "reused_documents": reused,
                        "focus": source.get("focus", []),
                    }
                )
            except Exception as exc:
                error_count += 1
                source_results.append(
                    {
                        "slug": source["slug"],
                        "title": source["title"],
                        "status": "error",
                        "message": str(exc),
                        "focus": source.get("focus", []),
                    }
                )

        latest_documents = self.knowledge_service.summarize_documents(gig_id=self.GLOBAL_GIG_ID, limit=8)
        status = {
            "enabled": self.config.copilot_learning_enabled,
            "sync_interval_minutes": max(5, int(self.config.copilot_learning_interval_minutes or 30)),
            "last_synced_at": started_at.isoformat(),
            "last_query_sync_at": "",
            "recent_queries": [],
            "total_sources": len(all_sources),
            "total_documents_seen": total_documents_seen,
            "new_documents": total_new_documents,
            "error_count": error_count,
            "latest_topics": [item.get("filename", "") for item in latest_documents[:5] if item.get("filename")],
            "documents_available": len(self.knowledge_service.list_documents(gig_id=self.GLOBAL_GIG_ID, limit=200)),
            "sources": source_results,
        }
        self._set_status(status)
        return status

    def status(self) -> dict[str, Any]:
        cached = self._get_status()
        if cached is not None:
            return cached
        latest_documents = self.knowledge_service.summarize_documents(gig_id=self.GLOBAL_GIG_ID, limit=8)
        status = {
            "enabled": self.config.copilot_learning_enabled,
            "sync_interval_minutes": max(5, int(self.config.copilot_learning_interval_minutes or 30)),
            "last_synced_at": "",
            "last_query_sync_at": "",
            "recent_queries": [],
            "total_sources": len(self._iter_continuous_sources()),
            "total_documents_seen": 0,
            "new_documents": 0,
            "error_count": 0,
            "latest_topics": [item.get("filename", "") for item in latest_documents[:5] if item.get("filename")],
            "documents_available": len(self.knowledge_service.list_documents(gig_id=self.GLOBAL_GIG_ID, limit=200)),
            "sources": [],
        }
        self._set_status(status)
        return status

    def sync_query_context(self, query: str, *, force: bool = False) -> dict[str, Any]:
        cleaned_query = str(query or "").strip()
        if not self.config.copilot_learning_enabled:
            return self.status()
        if not cleaned_query or self._is_low_signal_query(cleaned_query):
            return self.status()

        queries = self._extract_relevant_queries(cleaned_query)
        if not queries:
            return self.status()

        query_hash = hashlib.sha256("|".join(sorted(queries)).encode("utf-8")).hexdigest()
        cache_key = f"gigoptimizer:copilot-learning:query:{query_hash}"
        if not force and self.cache_service is not None:
            cached = self.cache_service.get_json(cache_key)
            if isinstance(cached, dict):
                return cached

        started_at = utc_now()
        query_results: list[dict[str, Any]] = []
        total_documents_seen = 0
        total_new_documents = 0
        error_count = 0
        for query_source in self._build_query_sources(queries):
            try:
                items = self._fetch_feed_items(query_source)
                inserted = 0
                reused = 0
                for item in items[:4]:
                    payload = self._item_to_document(query_source, item)
                    raw_bytes = payload["content"].encode("utf-8")
                    checksum = hashlib.sha256(raw_bytes).hexdigest()
                    existing = self.repository.find_knowledge_document_by_checksum(
                        gig_id=self.GLOBAL_GIG_ID,
                        checksum=checksum,
                    )
                    self.knowledge_service.ingest_document(
                        gig_id=self.GLOBAL_GIG_ID,
                        filename=payload["filename"],
                        content_type="text/plain",
                        raw_bytes=raw_bytes,
                        source="copilot_query_feed",
                    )
                    total_documents_seen += 1
                    if existing is None:
                        inserted += 1
                        total_new_documents += 1
                    else:
                        reused += 1
                query_results.append(
                    {
                        "slug": query_source["slug"],
                        "title": query_source["title"],
                        "query": query_source.get("query", ""),
                        "status": "ok",
                        "fetched_items": len(items[:4]),
                        "new_documents": inserted,
                        "reused_documents": reused,
                    }
                )
            except Exception as exc:
                error_count += 1
                query_results.append(
                    {
                        "slug": query_source["slug"],
                        "title": query_source["title"],
                        "query": query_source.get("query", ""),
                        "status": "error",
                        "message": str(exc),
                    }
                )

        status = self.status()
        recent_queries = [result.get("query", "") for result in query_results if result.get("query")]
        updated_status = {
            **status,
            "last_query_sync_at": started_at.isoformat(),
            "recent_queries": recent_queries[:6],
            "total_documents_seen": max(int(status.get("total_documents_seen", 0)), 0) + total_documents_seen,
            "new_documents": total_new_documents,
            "error_count": error_count,
            "latest_topics": [item.get("filename", "") for item in self.summarize_documents(limit=5) if item.get("filename")],
            "documents_available": len(self.knowledge_service.list_documents(gig_id=self.GLOBAL_GIG_ID, limit=300)),
        }
        self._set_status(updated_status)
        result = {
            "status": "ok",
            "query": cleaned_query,
            "queries": queries,
            "last_query_sync_at": started_at.isoformat(),
            "documents_seen": total_documents_seen,
            "new_documents": total_new_documents,
            "error_count": error_count,
            "sources": query_results,
        }
        if self.cache_service is not None:
            self.cache_service.set_json(cache_key, result, ttl_seconds=self.QUERY_CACHE_TTL_SECONDS)
        self._write_snapshot(result, prefix="query")
        return result

    def retrieve_context(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.knowledge_service.retrieve_context(
            gig_id=self.GLOBAL_GIG_ID,
            query=query,
            limit=limit,
        )

    def summarize_documents(self, *, limit: int = 8) -> list[dict[str, Any]]:
        return self.knowledge_service.summarize_documents(gig_id=self.GLOBAL_GIG_ID, limit=limit)

    def _iter_continuous_sources(self) -> list[dict[str, Any]]:
        sources = [dict(item) for item in self.DEFAULT_SOURCES]
        sources.extend(self._build_query_sources(self.DEFAULT_QUERY_TOPICS))
        return sources

    def _build_query_sources(self, queries: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index, query in enumerate(queries, start=1):
            cleaned = str(query or "").strip()
            if not cleaned:
                continue
            slug_seed = re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-")[:48] or f"query-{index}"
            results.append(
                {
                    "slug": f"google-news-{slug_seed}",
                    "title": f"Google News: {cleaned}",
                    "feed_url": self.GOOGLE_NEWS_RSS.format(query=quote_plus(cleaned)),
                    "focus": sorted(self._query_tokens(cleaned))[:8],
                    "query": cleaned,
                    "source_type": "google_news",
                }
            )
        return results

    def _extract_relevant_queries(self, query: str) -> list[str]:
        lower_query = str(query or "").lower()
        queries: list[str] = []
        for key, variants in self.QUERY_TOPIC_MAP.items():
            if key in lower_query:
                queries.extend(variants)
        if not queries:
            tokens = [token for token in self._query_tokens(query) if token not in {"write", "build", "code", "hello", "there"}]
            if tokens:
                seed = " ".join(tokens[:4])
                queries.extend(
                    [
                        f"{seed} programming",
                        f"{seed} software engineering",
                    ]
                )
        deduped: list[str] = []
        seen: set[str] = set()
        for item in queries:
            cleaned = re.sub(r"\s+", " ", item).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
            if len(deduped) >= 3:
                break
        return deduped

    def _is_low_signal_query(self, query: str) -> bool:
        normalized = re.sub(r"[^a-z\s]", " ", str(query or "").lower()).strip()
        if not normalized:
            return True
        greeting_tokens = {"hi", "hello", "hey", "yo", "hola", "namaste", "how", "are", "you", "doing", "there"}
        tokens = [token for token in normalized.split() if token]
        return bool(tokens) and len(tokens) <= 5 and all(token in greeting_tokens for token in tokens)

    def _fetch_feed_items(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        response = httpx.get(
            source["feed_url"],
            follow_redirects=True,
            timeout=20.0,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"},
        )
        response.raise_for_status()
        raw_xml = response.text.strip()
        if not raw_xml:
            raise ValueError("Educational feed returned an empty response.")
        root = ET.fromstring(raw_xml)
        tag = self._local_name(root.tag)
        if tag == "rss":
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else []
            return [parsed for item in items if (parsed := self._parse_rss_item(item)) is not None]
        if tag == "feed":
            entries = root.findall("atom:entry", self.NS)
            return [parsed for item in entries if (parsed := self._parse_atom_entry(item)) is not None]
        raise ValueError(f"Unsupported educational feed format: {tag}")

    def _parse_rss_item(self, item: ET.Element) -> dict[str, Any] | None:
        title = self._clean_text(item.findtext("title", ""))
        link = self._clean_text(item.findtext("link", ""))
        guid = self._clean_text(item.findtext("guid", "")) or link or title
        if not title or not guid:
            return None
        summary_html = self._clean_html(item.findtext("description", ""))
        content_html = self._clean_html(item.findtext("content:encoded", "", self.NS))
        published_at = self._parse_date(item.findtext("pubDate", ""))
        tags = [self._clean_text(child.text or "") for child in item.findall("category") if self._clean_text(child.text or "")]
        if published_at and published_at < utc_now() - timedelta(days=14):
            return None
        return {
            "id": guid,
            "title": title,
            "url": link,
            "summary_text": self._html_to_text(summary_html),
            "content_text": self._html_to_text(content_html) or self._html_to_text(summary_html),
            "published_at": published_at,
            "tags": tags,
        }

    def _parse_atom_entry(self, item: ET.Element) -> dict[str, Any] | None:
        title = self._clean_text(item.findtext("atom:title", "", self.NS))
        guid = self._clean_text(item.findtext("atom:id", "", self.NS)) or title
        link_node = item.find("atom:link", self.NS)
        link = self._clean_text(link_node.get("href", "")) if link_node is not None else ""
        if not title or not guid:
            return None
        summary_html = self._clean_html(item.findtext("atom:summary", "", self.NS))
        content_html = self._clean_html(item.findtext("atom:content", "", self.NS))
        published_at = self._parse_date(
            item.findtext("atom:updated", "", self.NS) or item.findtext("atom:published", "", self.NS)
        )
        tags = [
            self._clean_text(child.get("term", ""))
            for child in item.findall("atom:category", self.NS)
            if self._clean_text(child.get("term", ""))
        ]
        if published_at and published_at < utc_now() - timedelta(days=14):
            return None
        return {
            "id": guid,
            "title": title,
            "url": link,
            "summary_text": self._html_to_text(summary_html),
            "content_text": self._html_to_text(content_html) or self._html_to_text(summary_html),
            "published_at": published_at,
            "tags": tags,
        }

    def _item_to_document(self, source: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
        slug = str(source.get("slug", "feed")).strip() or "feed"
        title = str(item.get("title", "")).strip() or "Untitled"
        clean_title = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-.")[:80] or "entry"
        published = item.get("published_at")
        published_text = published.isoformat() if isinstance(published, datetime) else ""
        tags = ", ".join(item.get("tags", [])[:8])
        content = "\n".join(
            part
            for part in [
                f"Source: {source.get('title', slug)}",
                f"Feed URL: {source.get('feed_url', '')}",
                f"Original URL: {item.get('url', '')}",
                f"Published at: {published_text}",
                f"Focus: {', '.join(source.get('focus', []))}",
                f"Tags: {tags}",
                f"Title: {title}",
                f"Summary: {item.get('summary_text', '')}",
                f"Content: {item.get('content_text', '')}",
            ]
            if str(part).strip()
        ).strip()
        return {
            "filename": f"{slug}-{clean_title}.txt",
            "content": content,
        }

    def _query_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in (
                piece.strip(".,!?()[]{}:\"'").lower()
                for piece in str(value or "").replace("/", " ").replace("-", " ").split()
            )
            if len(token) >= 3
        }

    def _clean_text(self, value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"\s+", " ", text)
        return unescape(text).strip()

    def _clean_html(self, value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
        return text.strip()

    def _html_to_text(self, value: str) -> str:
        text = self._clean_html(value)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _parse_date(self, value: str) -> datetime | None:
        raw = self._clean_text(value)
        if not raw:
            return None
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _local_name(self, tag: str) -> str:
        if "}" in tag:
            return tag.rsplit("}", 1)[-1]
        return tag

    def _get_status(self) -> dict[str, Any] | None:
        if self.cache_service is None:
            return self._read_status_snapshot()
        value = self.cache_service.get_json(self.STATUS_CACHE_KEY)
        if isinstance(value, dict):
            return value
        return self._read_status_snapshot()

    def _set_status(self, value: dict[str, Any]) -> None:
        self._write_snapshot(value, prefix="status", latest_name="status.json")
        if self.cache_service is None:
            return
        self.cache_service.set_json(
            self.STATUS_CACHE_KEY,
            value,
            ttl_seconds=self.STATUS_CACHE_TTL_SECONDS,
        )

    def _read_status_snapshot(self) -> dict[str, Any] | None:
        path = self.learning_dir / "status.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_snapshot(self, payload: dict[str, Any], *, prefix: str, latest_name: str | None = None) -> None:
        timestamp = utc_now().strftime("%Y%m%d-%H%M%S")
        snapshot_path = self.snapshot_dir / f"{prefix}-{timestamp}.json"
        try:
            snapshot_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
            if latest_name:
                latest_path = self.learning_dir / latest_name
                latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        except OSError:
            return
