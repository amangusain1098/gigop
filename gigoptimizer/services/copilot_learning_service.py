from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
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
    USER_AGENT = "GigOptimizerCopilot/1.0 (+https://animha.co.in/dashboard)"
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
            "feed_url": "https://feeds.feedburner.com/PythonInsider",
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

    def sync_sources(self, *, force: bool = False) -> dict[str, Any]:
        started_at = utc_now()
        source_results: list[dict[str, Any]] = []
        total_new_documents = 0
        total_documents_seen = 0
        error_count = 0

        for source in self.DEFAULT_SOURCES:
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
            "total_sources": len(self.DEFAULT_SOURCES),
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
            "total_sources": len(self.DEFAULT_SOURCES),
            "total_documents_seen": 0,
            "new_documents": 0,
            "error_count": 0,
            "latest_topics": [item.get("filename", "") for item in latest_documents[:5] if item.get("filename")],
            "documents_available": len(self.knowledge_service.list_documents(gig_id=self.GLOBAL_GIG_ID, limit=200)),
            "sources": [],
        }
        self._set_status(status)
        return status

    def retrieve_context(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.knowledge_service.retrieve_context(
            gig_id=self.GLOBAL_GIG_ID,
            query=query,
            limit=limit,
        )

    def summarize_documents(self, *, limit: int = 8) -> list[dict[str, Any]]:
        return self.knowledge_service.summarize_documents(gig_id=self.GLOBAL_GIG_ID, limit=limit)

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
            return None
        value = self.cache_service.get_json(self.STATUS_CACHE_KEY)
        return value if isinstance(value, dict) else None

    def _set_status(self, value: dict[str, Any]) -> None:
        if self.cache_service is None:
            return
        self.cache_service.set_json(
            self.STATUS_CACHE_KEY,
            value,
            ttl_seconds=self.STATUS_CACHE_TTL_SECONDS,
        )
