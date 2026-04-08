from __future__ import annotations

from typing import Protocol

from ..models import ConnectorStatus, GigPageOverview, MarketplaceGig


class MarketplaceConnector(Protocol):
    name: str

    def fetch_competitor_gigs(
        self,
        search_terms: list[str],
        observer=None,
    ) -> tuple[list[MarketplaceGig], ConnectorStatus]:
        ...

    def fetch_gig_page_overview(
        self,
        gig_url: str,
        observer=None,
    ) -> tuple[GigPageOverview | None, ConnectorStatus]:
        ...
