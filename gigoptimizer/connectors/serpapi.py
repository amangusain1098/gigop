from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import GigOptimizerConfig
from ..models import ConnectorStatus, MarketplaceGig


class SerpApiSearchConnector:
    name = "serpapi"

    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config

    def fetch_fiverr_marketplace_gigs(
        self,
        search_terms: list[str],
        *,
        gig_page_lookup=None,
        observer=None,
    ) -> tuple[list[MarketplaceGig], ConnectorStatus]:
        if not self.config.serpapi_api_key:
            return [], ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="SERPAPI_API_KEY is not configured, so SerpApi competitor discovery is unavailable.",
            )
        gigs: list[MarketplaceGig] = []
        try:
            for term in search_terms:
                query = f'site:fiverr.com "{term}" Fiverr'
                self._notify(
                    observer,
                    stage="serpapi_started",
                    term=term,
                    message=f"Searching SerpApi for Fiverr competitor pages matching '{term}'.",
                )
                payload = self._search(query)
                organic = payload.get("organic_results", []) or []
                self._notify(
                    observer,
                    stage="serpapi_results",
                    term=term,
                    result_count=len(organic),
                    message=f"SerpApi returned {len(organic)} organic results for '{term}'.",
                )
                for item in organic:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("link", "")).strip()
                    title = str(item.get("title", "")).strip()
                    snippet = str(item.get("snippet", "")).strip()
                    if "fiverr.com" not in url.lower():
                        continue
                    gig = MarketplaceGig(
                        title=title.replace("| Fiverr", "").strip() or url,
                        url=url,
                        seller_name="",
                        starting_price=None,
                        rating=None,
                        reviews_count=None,
                        matched_term=term,
                        snippet=snippet,
                    )
                    if gig_page_lookup is not None:
                        try:
                            overview, _ = gig_page_lookup(url)
                        except Exception:
                            overview = None
                        if overview is not None:
                            gig.title = overview.title or gig.title
                            gig.seller_name = overview.seller_name or gig.seller_name
                            gig.starting_price = overview.starting_price
                            gig.rating = overview.rating
                            gig.reviews_count = overview.reviews_count
                            gig.snippet = overview.description_excerpt or gig.snippet
                    gigs.append(gig)
        except Exception as exc:
            return [], ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"SerpApi competitor discovery failed: {exc}",
            )

        unique = self._dedupe(gigs)[: self.config.fiverr_marketplace_max_results]
        if not unique:
            return [], ConnectorStatus(
                connector=self.name,
                status="warning",
                detail="SerpApi did not return usable Fiverr competitor URLs for the current terms.",
            )
        return unique, ConnectorStatus(
            connector=self.name,
            status="ok",
            detail=f"SerpApi discovered {len(unique)} Fiverr competitor pages across {len(search_terms)} term(s).",
        )

    def _search(self, query: str) -> dict:
        url = "https://serpapi.com/search.json?" + urlencode(
            {
                "engine": self.config.serpapi_engine,
                "q": query,
                "num": max(1, int(self.config.serpapi_num_results)),
                "api_key": self.config.serpapi_api_key,
            }
        )
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _dedupe(self, gigs: list[MarketplaceGig]) -> list[MarketplaceGig]:
        unique: list[MarketplaceGig] = []
        seen: set[str] = set()
        for gig in gigs:
            key = gig.url or gig.title.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(gig)
        return unique

    def _notify(self, observer, **event) -> None:
        if observer is None:
            return
        observer(event)
