from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from ..config import GigOptimizerConfig
from ..persistence import BlueprintRepository
from .cache_service import CacheService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ManhwaFeedService:
    DEFAULT_SOURCES = [
        {
            "slug": "anime-news-network",
            "title": "Anime News Network",
            "category": "manga",
            "feed_url": "https://www.animenewsnetwork.com/all/rss.xml?ann-edition=us",
            "site_url": "https://www.animenewsnetwork.com/",
            "language": "en",
            "fetch_interval_minutes": 30,
            "metadata": {"kind": "news", "focus": ["manga", "anime", "industry"]},
        },
        {
            "slug": "myanimelist-news",
            "title": "MyAnimeList News",
            "category": "manga",
            "feed_url": "https://www.myanimelist.net/rss/news.xml",
            "site_url": "https://myanimelist.net/news",
            "language": "en",
            "fetch_interval_minutes": 30,
            "metadata": {"kind": "news", "focus": ["manga", "anime"]},
        },
        {
            "slug": "bleeding-cool-comics",
            "title": "Bleeding Cool Comics",
            "category": "comics",
            "feed_url": "https://bleedingcool.com/comics/feed/",
            "site_url": "https://bleedingcool.com/comics/",
            "language": "en",
            "fetch_interval_minutes": 30,
            "metadata": {"kind": "news", "focus": ["comics", "graphic novels"]},
        },
        {
            "slug": "cbr-main-feed",
            "title": "CBR",
            "category": "comics",
            "feed_url": "https://www.cbr.com/feed/",
            "site_url": "https://www.cbr.com/",
            "language": "en",
            "fetch_interval_minutes": 30,
            "metadata": {"kind": "news", "focus": ["comics", "manga", "manhwa"]},
        },
    ]

    ENTRY_CACHE_TTL_SECONDS = 10 * 60
    OVERVIEW_CACHE_TTL_SECONDS = 5 * 60
    USER_AGENT = "AnimhaBot/1.0 (+https://animha.co.in/manhwa)"
    NS = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "media": "http://search.yahoo.com/mrss/",
        "atom": "http://www.w3.org/2005/Atom",
    }
    CATEGORY_KEYWORDS = {
        "manhwa": {"manhwa", "webtoon", "naver", "kakao", "toon", "solo leveling"},
        "manga": {"manga", "shonen", "shoujo", "kodansha", "jump", "viz", "seinen"},
        "comics": {"comic", "comics", "marvel", "dc", "graphic novel", "batman", "spider-man"},
    }
    CATEGORY_COPY = {
        "manhwa": {
            "title": "Manhwa desk",
            "description": "Fresh headlines, webtoon buzz, and Korean comics coverage aimed at readers hunting what is moving right now.",
        },
        "manga": {
            "title": "Manga desk",
            "description": "New release chatter, industry updates, and manga-focused coverage pulled into one searchable stream.",
        },
        "comics": {
            "title": "Comics desk",
            "description": "Comics headlines, graphic novel coverage, and crossover stories that broaden discovery traffic.",
        },
    }
    TOPIC_STOPWORDS = {
        "news",
        "update",
        "updates",
        "chapter",
        "chapters",
        "episode",
        "episodes",
        "season",
        "movie",
        "film",
        "anime",
        "manga",
        "manhwa",
        "comics",
        "comic",
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "after",
        "about",
        "your",
        "their",
        "this",
        "that",
        "will",
        "gets",
        "more",
        "have",
        "has",
        "new",
    }

    def __init__(
        self,
        config: GigOptimizerConfig,
        repository: BlueprintRepository,
        cache_service: CacheService | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.cache_service = cache_service
        self.ensure_default_sources()

    def ensure_default_sources(self) -> list[dict[str, Any]]:
        return self.repository.ensure_feed_sources(self.DEFAULT_SOURCES)

    def save_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = self._clean_text(payload.get("title", ""))
        feed_url = self._clean_text(payload.get("feed_url", ""))
        if not title:
            raise ValueError("Source title is required.")
        if not feed_url.startswith(("http://", "https://")):
            raise ValueError("Feed URL must start with http:// or https://.")
        slug = self._slugify_source(payload.get("slug") or title)
        source = {
            "slug": slug,
            "title": title,
            "category": self._normalize_category(payload.get("category", "manga")),
            "feed_url": feed_url,
            "site_url": self._clean_text(payload.get("site_url", "")),
            "language": self._clean_text(payload.get("language", "en")) or "en",
            "active": bool(payload.get("active", True)),
            "fetch_interval_minutes": max(5, int(payload.get("fetch_interval_minutes", 30) or 30)),
            "metadata": {
                "kind": self._clean_text(payload.get("kind", "news")) or "news",
                "focus": self._split_focus(payload.get("focus", "")),
                "custom": True,
            },
        }
        self.repository.ensure_feed_sources([source])
        self._clear_cached_views()
        sources = self.repository.list_feed_sources(limit=100)
        return next(item for item in sources if item["slug"] == slug)

    def set_source_active(self, *, slug: str, active: bool) -> dict[str, Any]:
        sources = self.repository.ensure_feed_sources(
            [
                {
                    **item,
                    "active": active,
                    "metadata": item.get("metadata", {}),
                }
                for item in self.repository.list_feed_sources(limit=100)
                if item["slug"] == slug
            ]
        )
        self._clear_cached_views()
        for item in sources:
            if item["slug"] == slug:
                return item
        raise KeyError(slug)

    def sync_all_sources(self, *, force: bool = False) -> dict[str, Any]:
        started_at = utc_now()
        sources = self.repository.list_feed_sources(active_only=True, limit=50)
        total_entries = 0
        total_new_entries = 0
        error_count = 0
        source_results: list[dict[str, Any]] = []

        for source in sources:
            try:
                if not force and self._should_skip_source(source):
                    source_results.append(
                        {
                            "source_slug": source["slug"],
                            "status": "skipped",
                            "title": source["title"],
                            "message": "Still fresh from the previous sync window.",
                            "fetched_entries": 0,
                            "new_entries": 0,
                        }
                    )
                    continue

                items = self._fetch_feed_items(source)
                fetched_entries = len(items)
                new_entries = 0
                for item in items:
                    _, created = self.repository.upsert_feed_entry(**item)
                    if created:
                        new_entries += 1
                total_entries += fetched_entries
                total_new_entries += new_entries
                self.repository.update_feed_source_status(source["slug"], success=True, checked_at=utc_now())
                source_results.append(
                    {
                        "source_slug": source["slug"],
                        "status": "ok",
                        "title": source["title"],
                        "message": f"Fetched {fetched_entries} entries.",
                        "fetched_entries": fetched_entries,
                        "new_entries": new_entries,
                    }
                )
            except Exception as exc:
                error_count += 1
                self.repository.update_feed_source_status(
                    source["slug"],
                    last_error=str(exc),
                    success=False,
                    checked_at=utc_now(),
                )
                source_results.append(
                    {
                        "source_slug": source["slug"],
                        "status": "error",
                        "title": source["title"],
                        "message": str(exc),
                        "fetched_entries": 0,
                        "new_entries": 0,
                    }
                )

        finished_at = utc_now()
        run = self.repository.record_feed_sync_run(
            scope="all",
            status="completed" if error_count == 0 else "partial",
            total_sources=len(sources),
            total_entries=total_entries,
            total_new_entries=total_new_entries,
            error_count=error_count,
            result_json={"sources": source_results},
            started_at=started_at,
            finished_at=finished_at,
        )
        self._clear_cached_views()
        return {
            "status": run["status"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "total_sources": len(sources),
            "total_entries": total_entries,
            "total_new_entries": total_new_entries,
            "error_count": error_count,
            "sources": source_results,
            "run": run,
        }

    def build_overview(self) -> dict[str, Any]:
        cache_key = "gigoptimizer:manhwa:overview"
        if self.cache_service is not None:
            cached = self.cache_service.get_json(cache_key)
            if isinstance(cached, dict):
                return cached

        sources = self.repository.list_feed_sources(limit=50)
        source_title_map = {item["slug"]: item["title"] for item in sources}
        entries = [self._decorate_entry(item, source_title_map) for item in self.repository.list_feed_entries(limit=120)]
        latest_entries = entries[:24]
        counts = {
            "all": len(entries),
            "manhwa": sum(1 for item in entries if item.get("category") == "manhwa"),
            "manga": sum(1 for item in entries if item.get("category") == "manga"),
            "comics": sum(1 for item in entries if item.get("category") == "comics"),
        }
        sync_runs = self.repository.list_feed_sync_runs(limit=8)
        by_source: list[dict[str, Any]] = []
        for source in sources:
            source_entries = [item for item in entries if item.get("source_slug") == source["slug"]]
            by_source.append(
                {
                    **source,
                    "entry_count": len(source_entries),
                    "latest_entry": source_entries[0] if source_entries else None,
                }
            )

        lead_entry = latest_entries[0] if latest_entries else None
        headline_entries = latest_entries[1:6]
        feature_entries = latest_entries[6:12]
        news_briefs = latest_entries[12:20]
        overview = {
            "counts": counts,
            "sources": by_source,
            "latest_entries": latest_entries,
            "featured_entries": latest_entries[:6],
            "lead_entry": lead_entry,
            "headline_entries": headline_entries,
            "feature_entries": feature_entries,
            "news_briefs": news_briefs,
            "source_channels": [item for item in by_source if item.get("latest_entry")][:6],
            "trending_topics": self._build_trending_topics(entries),
            "category_sections": self._build_category_sections(entries),
            "manhwa_entries": [item for item in entries if item.get("category") == "manhwa"][:8],
            "manga_entries": [item for item in entries if item.get("category") == "manga"][:8],
            "comics_entries": [item for item in entries if item.get("category") == "comics"][:8],
            "latest_sync": sync_runs[0] if sync_runs else {},
            "recent_sync_runs": sync_runs,
            "coverage": {
                "interval_minutes": max(5, self.config.manhwa_sync_interval_minutes),
                "last_sync_human": self._relative_timestamp((sync_runs[0] if sync_runs else {}).get("finished_at")),
                "channels": len([item for item in by_source if item.get("active", True)]),
            },
            "seo": {
                "title": "Animha Newsroom | Manhwa, Manga, and Comics Headlines",
                "description": "Read a live newsroom-style stream of manhwa, manga, and comics headlines, updates, and discovery stories published automatically on Animha.",
            },
            "monetization_notes": [
                "Use public landing pages, genre hubs, and source-specific updates to attract organic traffic.",
                "Place ads on category pages, in-feed cards, and reader pages after traffic starts building.",
                "Add affiliate links to official read and buy destinations instead of mirroring copyrighted chapters.",
            ],
        }
        if self.cache_service is not None:
            self.cache_service.set_json(cache_key, overview, ttl_seconds=self.OVERVIEW_CACHE_TTL_SECONDS)
        return overview

    def should_auto_refresh(self, overview: dict[str, Any]) -> bool:
        latest_sync = overview.get("latest_sync") or {}
        finished_at = str(latest_sync.get("finished_at") or latest_sync.get("started_at") or "").strip()
        if not finished_at:
            return not bool(overview.get("latest_entries"))
        try:
            parsed = datetime.fromisoformat(finished_at)
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        refresh_after = timedelta(minutes=max(10, int(self.config.manhwa_sync_interval_minutes or 30)))
        return utc_now() - parsed.astimezone(timezone.utc) >= refresh_after

    def list_entries(self, *, category: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
        source_title_map = {item["slug"]: item["title"] for item in self.repository.list_feed_sources(limit=50)}
        entries = self.repository.list_feed_entries(category=category, limit=limit)
        return [self._decorate_entry(item, source_title_map) for item in entries]

    def get_entry(self, slug: str) -> dict[str, Any] | None:
        entry = self.repository.get_feed_entry(slug)
        if entry is None:
            return None
        source_title_map = {item["slug"]: item["title"] for item in self.repository.list_feed_sources(limit=50)}
        return self._decorate_entry(entry, source_title_map)

    def build_reader_context(self, slug: str) -> dict[str, Any] | None:
        entry = self.get_entry(slug)
        if entry is None:
            return None
        related = [
            item
            for item in self.list_entries(category=entry.get("category"), limit=12)
            if item.get("slug") != slug
        ][:6]
        paragraphs = self._paragraphs(entry.get("content_text") or entry.get("summary_text") or "")
        body_html = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
        return {
            "entry": entry,
            "body_html": body_html,
            "paragraphs": paragraphs,
            "related_entries": related,
            "seo": {
                "title": f"{entry.get('title', 'Read update')} | Animha",
                "description": (entry.get("summary_text") or entry.get("content_text") or "")[:160].strip(),
            },
        }

    def build_sitemap_entries(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return self.repository.list_feed_entries(limit=limit)

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
            raise ValueError("Feed returned an empty response.")
        return self._parse_feed_xml(raw_xml, source)

    def _parse_feed_xml(self, raw_xml: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        root = ET.fromstring(raw_xml)
        tag = self._local_name(root.tag)
        if tag == "rss":
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else []
            return [parsed for item in items if (parsed := self._parse_rss_item(item, source)) is not None]
        if tag == "feed":
            items = [self._parse_atom_entry(item, source) for item in root.findall("atom:entry", self.NS)]
            return [item for item in items if item is not None]
        raise ValueError(f"Unsupported feed format: {tag}")

    def _parse_rss_item(self, item: ET.Element, source: dict[str, Any]) -> dict[str, Any] | None:
        title = self._clean_text(item.findtext("title", ""))
        canonical_url = self._clean_text(item.findtext("link", ""))
        guid = self._clean_text(item.findtext("guid", "")) or canonical_url or title
        if not title or not guid:
            return None
        description_html = self._clean_html(item.findtext("description", ""))
        content_html = self._clean_html(item.findtext("content:encoded", "", self.NS))
        author = self._clean_text(item.findtext("dc:creator", "", self.NS) or item.findtext("author", ""))
        categories = [self._clean_text(child.text or "") for child in item.findall("category") if self._clean_text(child.text or "")]
        image_url = self._image_from_item(item)
        published_at = self._parse_date(item.findtext("pubDate", ""))
        return self._build_entry_payload(
            source=source,
            external_id=guid,
            title=title,
            canonical_url=canonical_url,
            author=author,
            summary_html=description_html,
            content_html=content_html,
            categories=categories,
            image_url=image_url,
            published_at=published_at,
        )

    def _parse_atom_entry(self, item: ET.Element, source: dict[str, Any]) -> dict[str, Any] | None:
        title = self._clean_text(item.findtext("atom:title", "", self.NS))
        link_node = item.find("atom:link", self.NS)
        canonical_url = self._clean_text(link_node.get("href", "")) if link_node is not None else ""
        guid = self._clean_text(item.findtext("atom:id", "", self.NS)) or canonical_url or title
        if not title or not guid:
            return None
        summary_html = self._clean_html(item.findtext("atom:summary", "", self.NS))
        content_html = self._clean_html(item.findtext("atom:content", "", self.NS))
        author = self._clean_text(item.findtext("atom:author/atom:name", "", self.NS))
        categories = [
            self._clean_text(child.get("term", ""))
            for child in item.findall("atom:category", self.NS)
            if self._clean_text(child.get("term", ""))
        ]
        image_url = self._image_from_item(item)
        published_at = self._parse_date(
            item.findtext("atom:updated", "", self.NS) or item.findtext("atom:published", "", self.NS)
        )
        return self._build_entry_payload(
            source=source,
            external_id=guid,
            title=title,
            canonical_url=canonical_url,
            author=author,
            summary_html=summary_html,
            content_html=content_html,
            categories=categories,
            image_url=image_url,
            published_at=published_at,
        )

    def _build_entry_payload(
        self,
        *,
        source: dict[str, Any],
        external_id: str,
        title: str,
        canonical_url: str,
        author: str,
        summary_html: str,
        content_html: str,
        categories: list[str],
        image_url: str,
        published_at: datetime | None,
    ) -> dict[str, Any]:
        summary_text = self._html_to_text(summary_html)
        content_text = self._html_to_text(content_html)
        category = self._classify_category(
            source_category=str(source.get("category", "manga")),
            title=title,
            text=" ".join([summary_text, content_text, " ".join(categories)]),
        )
        slug = self._slugify_entry(title=title, external_id=external_id)
        normalized_tags = self._dedupe_tags(categories)
        return {
            "source_slug": str(source.get("slug", "")).strip(),
            "category": category,
            "external_id": external_id,
            "slug": slug,
            "title": title,
            "canonical_url": canonical_url or source.get("site_url", "") or "",
            "author": author,
            "summary_html": summary_html,
            "summary_text": summary_text,
            "content_html": content_html,
            "content_text": content_text,
            "image_url": image_url,
            "tags": normalized_tags,
            "metadata": {
                "source_title": source.get("title", ""),
                "source_site_url": source.get("site_url", ""),
                "source_feed_url": source.get("feed_url", ""),
                "hostname": urlparse(canonical_url or source.get("site_url", "") or "").hostname or "",
            },
            "published_at": published_at,
        }

    def _image_from_item(self, item: ET.Element) -> str:
        media_thumbnail = item.find("media:thumbnail", self.NS)
        if media_thumbnail is not None and media_thumbnail.get("url"):
            return str(media_thumbnail.get("url", "")).strip()
        media_content = item.find("media:content", self.NS)
        if media_content is not None and media_content.get("url"):
            return str(media_content.get("url", "")).strip()
        enclosure = item.find("enclosure")
        if enclosure is not None and enclosure.get("url"):
            url = str(enclosure.get("url", "")).strip()
            if (enclosure.get("type", "") or "").startswith("image/"):
                return url
        raw_xml = ET.tostring(item, encoding="unicode")
        image_match = re.search(r"""<img[^>]+src=["']([^"']+)["']""", raw_xml, flags=re.IGNORECASE)
        return image_match.group(1).strip() if image_match else ""

    def _classify_category(self, *, source_category: str, title: str, text: str) -> str:
        haystack = f"{title} {text}".lower()
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if any(keyword in haystack for keyword in keywords):
                return category
        normalized_source = source_category.strip().lower() or "manga"
        if normalized_source in {"manhwa", "manga", "comics"}:
            return normalized_source
        return "manga"

    def _parse_date(self, value: str) -> datetime | None:
        cleaned = str(value or "").strip()
        if not cleaned:
            return None
        try:
            parsed = parsedate_to_datetime(cleaned)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _slugify_entry(self, *, title: str, external_id: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", unescape(title).lower()).strip("-") or "entry"
        digest = hashlib.sha1(external_id.encode("utf-8")).hexdigest()[:8]
        return f"{base[:120]}-{digest}"

    def _slugify_source(self, value: str) -> str:
        return (re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "source")[:120]

    def _normalize_category(self, value: str) -> str:
        cleaned = str(value or "manga").strip().lower()
        return cleaned if cleaned in {"manhwa", "manga", "comics"} else "manga"

    def _split_focus(self, value: Any) -> list[str]:
        if isinstance(value, list):
            parts = [self._clean_text(item) for item in value]
        else:
            parts = [self._clean_text(item) for item in str(value or "").split(",")]
        return [item for item in parts if item]

    def _clean_text(self, value: str) -> str:
        text = re.sub(r"\s+", " ", unescape(str(value or ""))).strip()
        return self._fix_mojibake(text)

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
        return self._fix_mojibake(text.strip())

    def _should_skip_source(self, source: dict[str, Any]) -> bool:
        last_success = str(source.get("last_success_at", "")).strip()
        if not last_success:
            return False
        try:
            parsed = datetime.fromisoformat(last_success)
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        minutes_elapsed = (utc_now() - parsed.astimezone(timezone.utc)).total_seconds() / 60
        return minutes_elapsed < max(5, int(source.get("fetch_interval_minutes", 30) or 30))

    def _paragraphs(self, value: str) -> list[str]:
        parts = [part.strip() for part in re.split(r"\n\s*\n", value) if part.strip()]
        if parts:
            return parts
        line = value.strip()
        return [line] if line else []

    def _decorate_entry(self, entry: dict[str, Any], source_title_map: dict[str, str]) -> dict[str, Any]:
        enriched = dict(entry)
        summary = (entry.get("summary_text") or entry.get("content_text") or "").strip()
        enriched["summary_preview"] = summary[:220].strip() + ("..." if len(summary) > 220 else "")
        enriched["source_title"] = source_title_map.get(entry.get("source_slug", ""), entry.get("source_slug", ""))
        enriched["display_time"] = self._relative_timestamp(entry.get("published_at") or entry.get("fetched_at"))
        enriched["published_display"] = self._format_timestamp(entry.get("published_at") or entry.get("fetched_at"))
        enriched["eyebrow"] = self.CATEGORY_COPY.get(entry.get("category", ""), {}).get("title", "News desk")
        return enriched

    def _build_trending_topics(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counter: Counter[str] = Counter()
        for entry in entries[:40]:
            for tag in entry.get("tags", [])[:4]:
                cleaned = self._clean_text(tag).lower()
                if cleaned and cleaned not in self.TOPIC_STOPWORDS:
                    counter[cleaned] += 3
            for token in re.findall(r"[a-z0-9][a-z0-9+'-]{2,}", str(entry.get("title", "")).lower()):
                if token not in self.TOPIC_STOPWORDS and not token.isdigit():
                    counter[token] += 1
        topics = []
        for label, count in counter.most_common(10):
            topics.append({"label": label.title(), "count": count})
        return topics

    def _build_category_sections(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        for slug in ("manhwa", "manga", "comics"):
            section_entries = [item for item in entries if item.get("category") == slug][:5]
            if not section_entries:
                continue
            copy = self.CATEGORY_COPY[slug]
            sections.append(
                {
                    "slug": slug,
                    "title": copy["title"],
                    "description": copy["description"],
                    "lead": section_entries[0],
                    "items": section_entries[1:5],
                }
            )
        return sections

    def _relative_timestamp(self, value: str | None) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return "Just updated"
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return cleaned
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = utc_now() - parsed.astimezone(timezone.utc)
        minutes = int(delta.total_seconds() // 60)
        if minutes < 1:
            return "Just updated"
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 7:
            return f"{days}d ago"
        return parsed.strftime("%d %b %Y")

    def _format_timestamp(self, value: str | None) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return "Recently published"
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return cleaned
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")

    def _dedupe_tags(self, tags: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for tag in tags:
            cleaned = self._clean_text(tag)
            lowered = cleaned.lower()
            if not cleaned or lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(cleaned)
        return ordered[:8]

    def _fix_mojibake(self, value: str) -> str:
        text = str(value or "")
        replacements = {
            "â": "-",
            "â": "-",
            "â": "'",
            "â": "'",
            "â": '"',
            "â": '"',
            "Â": "",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    def _clear_cached_views(self) -> None:
        if self.cache_service is None:
            return
        for key in ["gigoptimizer:manhwa:overview"]:
            self.cache_service.delete(key)

    def _local_name(self, tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag
