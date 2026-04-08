from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

from ..config import GigOptimizerConfig
from ..models import ConnectorStatus, GigPageOverview, MarketplaceGig


class FiverrMarketplaceConnector:
    name = "fiverr_marketplace"

    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config

    def fetch_competitor_gigs(self, search_terms: list[str], observer=None) -> tuple[list[MarketplaceGig], ConnectorStatus]:
        if self.config.marketplace_reader_enabled:
            reader_gigs, reader_status = self.fetch_competitor_gigs_reader(search_terms, observer=observer)
            if reader_gigs:
                return reader_gigs, reader_status

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        except ImportError:
            self._notify(
                observer,
                stage="scraper_unavailable",
                level="warning",
                message="Playwright is not installed, so live marketplace scraping is unavailable.",
            )
            return [], ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="Install the optional 'live' dependencies to enable public Fiverr marketplace scraping.",
            )

        if not search_terms:
            self._notify(
                observer,
                stage="scraper_skipped",
                level="warning",
                message="No marketplace search terms were provided for competitor scraping.",
            )
            return [], ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="No marketplace search terms were provided for competitor scraping.",
            )

        gigs: list[MarketplaceGig] = []
        try:
            self._notify(
                observer,
                stage="run_started",
                message=f"Starting public Fiverr marketplace scrape across {len(search_terms)} search terms.",
            )
            with self._open_browser(headless=self.config.fiverr_marketplace_headless, observer=observer) as page:
                gigs, early_status = self._scrape_terms_in_page(page, search_terms, observer=observer)
                if early_status is not None:
                    return [], early_status
        except PlaywrightTimeoutError as exc:
            self._notify(
                observer,
                stage="scraper_error",
                level="error",
                message=f"Fiverr marketplace scraping timed out: {exc}",
            )
            return [], ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Fiverr marketplace scraping timed out: {exc}",
            )
        except Exception as exc:
            self._notify(
                observer,
                stage="scraper_error",
                level="error",
                message=f"Fiverr marketplace scraping failed: {exc}",
            )
            return [], ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Fiverr marketplace scraping failed: {exc}",
            )

        unique = self._dedupe(gigs)[: self.config.fiverr_marketplace_max_results]
        if not unique:
            self._notify(
                observer,
                stage="run_completed",
                level="warning",
                result_count=0,
                message="Marketplace scraper did not find competitor cards. Tune the public search selectors in .env.",
            )
            return [], ConnectorStatus(
                connector=self.name,
                status="warning",
                detail="Marketplace scraper did not find competitor cards. Tune the public search selectors in .env.",
            )
        self._notify(
            observer,
            stage="run_completed",
            result_count=len(unique),
            message=f"Marketplace scrape finished with {len(unique)} unique gigs collected.",
        )
        return unique, ConnectorStatus(
            connector=self.name,
            status="ok",
            detail=f"Collected {len(unique)} public Fiverr marketplace gigs across {len(search_terms)} search terms.",
        )

    def fetch_gig_page_overview(self, gig_url: str, observer=None) -> tuple[GigPageOverview | None, ConnectorStatus]:
        if not gig_url.strip():
            return None, ConnectorStatus(
                connector=self.name,
                status="warning",
                detail="Provide a Fiverr gig URL before running a market comparison.",
            )

        http_overview, http_status = self.fetch_gig_page_overview_http(gig_url, observer=observer)
        if http_overview is not None:
            return http_overview, http_status
        if self.config.marketplace_reader_enabled:
            reader_overview, reader_status = self.fetch_gig_page_overview_reader(gig_url, observer=observer)
            if reader_overview is not None:
                return reader_overview, reader_status

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        except ImportError:
            return None, ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="Install the optional 'live' dependencies to enable live gig URL comparison.",
            )

        try:
            with self._open_browser(headless=self.config.fiverr_marketplace_headless, observer=observer) as page:
                self._notify(
                    observer,
                    stage="my_gig_started",
                    url=gig_url,
                    message="Opening your Fiverr gig URL for live market comparison.",
                )
                page.goto(gig_url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle")
                challenge_paths = self._capture_challenge_if_present(page, "my-gig")
                if challenge_paths is not None:
                    html_path, screenshot_path = challenge_paths
                    self._notify(
                        observer,
                        stage="challenge_detected",
                        level="warning",
                        url=page.url,
                        message="Fiverr returned an anti-bot challenge page when loading your gig URL.",
                        debug_html_path=str(html_path),
                        debug_screenshot_path=str(screenshot_path),
                    )
                    return None, ConnectorStatus(
                        connector=self.name,
                        status="warning",
                        detail="Fiverr returned an anti-bot challenge page for your gig URL. Start verification and retry the comparison.",
                    )

                html = page.content()
                overview = self._extract_gig_page_overview(page, html, gig_url)
                if not overview.title:
                    return None, ConnectorStatus(
                        connector=self.name,
                        status="warning",
                        detail="The gig page loaded, but the app could not detect a title from it.",
                    )
                self._notify(
                    observer,
                    stage="my_gig_loaded",
                    url=overview.url,
                    gig_title=overview.title,
                    seller_name=overview.seller_name,
                    starting_price=overview.starting_price,
                    rating=overview.rating,
                    message=f"Loaded your gig page '{overview.title}'.",
                )
                return overview, ConnectorStatus(
                    connector=self.name,
                    status="ok",
                    detail=f"Loaded your gig page '{overview.title}' for comparison.",
                )
        except PlaywrightTimeoutError as exc:
            return None, ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Loading your gig URL timed out: {exc}",
            )
        except Exception as exc:
            return None, ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Loading your gig URL failed: {exc}",
            )

    def fetch_gig_page_overview_http(self, gig_url: str, observer=None) -> tuple[GigPageOverview | None, ConnectorStatus]:
        try:
            html = self._http_get_html(gig_url)
            if self._looks_like_challenge_html(html):
                return None, ConnectorStatus(
                    connector=self.name,
                    status="warning",
                    detail="Fiverr returned a challenge page for your gig URL during direct HTTP fetch.",
                )
            overview = self._extract_gig_page_overview_from_html(html, gig_url)
            if not overview.title:
                return None, ConnectorStatus(
                    connector=self.name,
                    status="warning",
                    detail="The gig page loaded over HTTP, but the app could not detect a title from it.",
                )
            self._notify(
                observer,
                stage="my_gig_loaded",
                url=overview.url,
                gig_title=overview.title,
                seller_name=overview.seller_name,
                starting_price=overview.starting_price,
                rating=overview.rating,
                message=f"Loaded your gig page '{overview.title}' via direct HTTP fetch.",
            )
            return overview, ConnectorStatus(
                connector=self.name,
                status="ok",
                detail=f"Loaded your gig page '{overview.title}' via direct HTTP fetch.",
            )
        except Exception as exc:
            return None, ConnectorStatus(
                connector=self.name,
                status="warning",
                detail=f"Direct HTTP fetch for your gig URL failed: {exc}",
            )

    def fetch_gig_page_overview_reader(self, gig_url: str, observer=None) -> tuple[GigPageOverview | None, ConnectorStatus]:
        if not self.config.marketplace_reader_enabled or not self.config.marketplace_reader_base_url:
            return None, ConnectorStatus(
                connector="marketplace_reader",
                status="skipped",
                detail="Marketplace reader fallback is disabled.",
            )
        try:
            markdown = self._reader_get_markdown(gig_url)
            overview = self._extract_gig_page_overview_from_markdown(markdown, gig_url)
            if not overview.title:
                return None, ConnectorStatus(
                    connector="marketplace_reader",
                    status="warning",
                    detail="Marketplace reader loaded the gig page but could not detect a title.",
                )
            self._notify(
                observer,
                stage="my_gig_loaded",
                url=overview.url,
                gig_title=overview.title,
                seller_name=overview.seller_name,
                starting_price=overview.starting_price,
                rating=overview.rating,
                message=f"Loaded your gig page '{overview.title}' via the free marketplace reader fallback.",
            )
            return overview, ConnectorStatus(
                connector="marketplace_reader",
                status="ok",
                detail=f"Loaded your gig page '{overview.title}' via the free marketplace reader fallback.",
            )
        except Exception as exc:
            return None, ConnectorStatus(
                connector="marketplace_reader",
                status="warning",
                detail=f"Marketplace reader fallback for your gig URL failed: {exc}",
            )

    def fetch_competitor_gigs_reader(self, search_terms: list[str], observer=None) -> tuple[list[MarketplaceGig], ConnectorStatus]:
        if not self.config.marketplace_reader_enabled or not self.config.marketplace_reader_base_url:
            return [], ConnectorStatus(
                connector="marketplace_reader",
                status="skipped",
                detail="Marketplace reader fallback is disabled.",
            )
        if not search_terms:
            return [], ConnectorStatus(
                connector="marketplace_reader",
                status="skipped",
                detail="No marketplace search terms were provided for reader-based competitor discovery.",
            )

        gigs: list[MarketplaceGig] = []
        try:
            for term in search_terms:
                url = self._search_url(term)
                self._notify(
                    observer,
                    stage="term_started",
                    term=term,
                    url=url,
                    message=f"Running free marketplace reader discovery for '{term}'.",
                )
                markdown = self._reader_get_markdown(url)
                parsed = self._extract_search_gigs_from_markdown(markdown, term, search_url=url)
                gigs.extend(parsed)
                self._notify(
                    observer,
                    stage="term_completed",
                    term=term,
                    url=url,
                    result_count=len(parsed),
                    message=f"Marketplace reader found {len(parsed)} gigs for '{term}'.",
                )
        except Exception as exc:
            return [], ConnectorStatus(
                connector="marketplace_reader",
                status="warning",
                detail=f"Marketplace reader competitor discovery failed: {exc}",
            )

        unique = self._dedupe(gigs)[: self.config.fiverr_marketplace_max_results]
        if not unique:
            return [], ConnectorStatus(
                connector="marketplace_reader",
                status="warning",
                detail="Marketplace reader did not extract any competitor gigs from the current Fiverr search pages.",
            )
        self._notify(
            observer,
            stage="run_completed",
            result_count=len(unique),
            message=f"Marketplace reader finished with {len(unique)} unique competitor gigs.",
        )
        return unique, ConnectorStatus(
            connector="marketplace_reader",
            status="ok",
            detail=f"Collected {len(unique)} public Fiverr marketplace gigs via the free marketplace reader fallback.",
        )

    def _search_url(self, term: str) -> str:
        return self.config.fiverr_marketplace_search_url_template.format(query=quote_plus(term))

    @contextmanager
    def _open_browser(self, *, headless: bool, observer=None):
        from playwright.sync_api import sync_playwright

        profile_dir = Path(self.config.fiverr_marketplace_profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            if self.config.browserless_enabled and self.config.browserless_ws_url:
                endpoint = self._browserless_endpoint()
                try:
                    browser = playwright.chromium.connect_over_cdp(endpoint)
                    context = browser.contexts[0] if browser.contexts else browser.new_context(
                        viewport={"width": 1440, "height": 960},
                        locale="en-US",
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    self._apply_stealth(page)
                    self._notify(
                        observer,
                        stage="browser_opened",
                        message="Opened the Fiverr scrape session through Browserless.",
                    )
                    try:
                        yield page
                    finally:
                        browser.close()
                    return
                except Exception as exc:
                    self._notify(
                        observer,
                        stage="browserless_fallback",
                        level="warning",
                        message=f"Browserless connection failed, falling back to local Chromium: {exc}",
                    )
            channel = self._resolve_browser_channel(playwright)
            launch_kwargs = {
                "user_data_dir": str(profile_dir),
                "headless": headless,
                "slow_mo": max(0, int(self.config.fiverr_marketplace_slow_mo_ms)),
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
                "viewport": {"width": 1440, "height": 960},
                "locale": "en-US",
            }
            if channel:
                launch_kwargs["channel"] = channel
            try:
                context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            except Exception:
                launch_kwargs.pop("channel", None)
                context = playwright.chromium.launch_persistent_context(**launch_kwargs)
                channel = None
            self._apply_stealth_context(context)
            context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = window.chrome || { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4] });
                """
            )
            page = context.pages[0] if context.pages else context.new_page()
            self._notify(
                observer,
                stage="browser_opened",
                message=(
                    f"Opened the Fiverr verification/scrape session in "
                    f"{channel if channel else 'bundled Chromium'} with a persistent profile."
                ),
            )
            try:
                yield page
            finally:
                context.close()

    def _browserless_endpoint(self) -> str:
        endpoint = self.config.browserless_ws_url.strip()
        token = self.config.browserless_api_token.strip()
        if token and "token=" not in endpoint:
            separator = "&" if "?" in endpoint else "?"
            endpoint = f"{endpoint}{separator}token={token}"
        return endpoint

    def _apply_stealth_context(self, context) -> None:
        try:
            from playwright_stealth import stealth_sync
        except Exception:
            return
        for page in context.pages:
            self._apply_stealth(page, stealth_sync=stealth_sync)

    def _apply_stealth(self, page, stealth_sync=None) -> None:
        resolver = stealth_sync
        if resolver is None:
            try:
                from playwright_stealth import stealth_sync as resolver
            except Exception:
                resolver = None
        if resolver is None:
            return
        try:
            resolver(page)
        except Exception:
            return

    def start_manual_verification(self, search_term: str, observer=None) -> tuple[bool, ConnectorStatus]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False, ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="Install the optional 'live' dependencies to enable manual verification mode.",
            )

        if not search_term.strip():
            return False, ConnectorStatus(
                connector=self.name,
                status="warning",
                detail="A verification search term is required before opening the manual browser.",
            )

        verification_url = self._search_url(search_term)
        profile_dir = Path(self.config.fiverr_marketplace_profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        timeout_seconds = max(60, int(self.config.fiverr_marketplace_verification_timeout_seconds))
        deadline = monotonic() + timeout_seconds

        self._notify(
            observer,
            stage="verification_started",
            term=search_term,
            url=verification_url,
            message="Opening a persistent Fiverr verification browser. Solve the challenge there and keep that window open until the scraper resumes.",
        )

        try:
            with self._open_browser(headless=False, observer=observer) as page:
                page.goto(verification_url, wait_until="domcontentloaded")
                while monotonic() < deadline:
                    if page.is_closed():
                        break
                    page.wait_for_timeout(2000)
                    if not self._is_challenge_page(page):
                        visible_cards = page.locator(self.config.fiverr_marketplace_card_selector).count()
                        self._notify(
                            observer,
                            stage="verification_completed",
                            term=search_term,
                            url=page.url,
                            result_count=visible_cards,
                            message="Manual verification completed. The scraper can now continue from the same visible browser session.",
                        )
                        return True, ConnectorStatus(
                            connector=self.name,
                            status="ok",
                            detail="Manual verification completed in the visible persistent browser session.",
                        )
                if not page.is_closed():
                    self._notify(
                        observer,
                        stage="verification_timeout",
                        level="warning",
                        term=search_term,
                        url=page.url,
                        message="Verification browser timed out before the challenge was cleared.",
                    )
                return False, ConnectorStatus(
                    connector=self.name,
                    status="warning",
                    detail="Manual verification timed out before Fiverr cleared the challenge.",
                )
        except Exception as exc:
            self._notify(
                observer,
                stage="verification_error",
                level="error",
                term=search_term,
                url=verification_url,
                message=f"Manual verification failed: {exc}",
            )
            return False, ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Manual verification failed: {exc}",
            )

    def verify_and_fetch_competitor_gigs(
        self,
        search_terms: list[str],
        observer=None,
    ) -> tuple[list[MarketplaceGig], ConnectorStatus]:
        if not search_terms:
            return [], ConnectorStatus(
                connector=self.name,
                status="warning",
                detail="A verification search term is required before opening the manual browser.",
            )

        verification_url = self._search_url(search_terms[0])
        timeout_seconds = max(60, int(self.config.fiverr_marketplace_verification_timeout_seconds))
        deadline = monotonic() + timeout_seconds
        self._notify(
            observer,
            stage="verification_started",
            term=search_terms[0],
            url=verification_url,
            message="Opening the manual verification browser. After the challenge clears, the scraper will continue in that same session.",
        )
        try:
            with self._open_browser(headless=False, observer=observer) as page:
                page.goto(verification_url, wait_until="domcontentloaded")
                while monotonic() < deadline:
                    if page.is_closed():
                        break
                    page.wait_for_timeout(2000)
                    if not self._is_challenge_page(page):
                        self._notify(
                            observer,
                            stage="verification_completed",
                            term=search_terms[0],
                            url=page.url,
                            message="Manual verification completed. Continuing the scrape in the same visible browser session now.",
                        )
                        gigs, early_status = self._scrape_terms_in_page(page, search_terms, observer=observer)
                        if early_status is not None:
                            return [], early_status
                        unique = self._dedupe(gigs)[: self.config.fiverr_marketplace_max_results]
                        if not unique:
                            return [], ConnectorStatus(
                                connector=self.name,
                                status="warning",
                                detail="Verification succeeded, but no marketplace gig cards were found after the challenge cleared.",
                            )
                        return unique, ConnectorStatus(
                            connector=self.name,
                            status="ok",
                            detail=f"Verification succeeded and collected {len(unique)} public Fiverr gigs in the same session.",
                        )
                return [], ConnectorStatus(
                    connector=self.name,
                    status="warning",
                    detail="Manual verification timed out before Fiverr cleared the challenge.",
                )
        except Exception as exc:
            self._notify(
                observer,
                stage="verification_error",
                level="error",
                term=search_terms[0],
                url=verification_url,
                message=f"Manual verification failed: {exc}",
            )
            return [], ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Manual verification failed: {exc}",
            )

    def _scrape_terms_in_page(self, page, search_terms: list[str], observer=None) -> tuple[list[MarketplaceGig], ConnectorStatus | None]:
        gigs: list[MarketplaceGig] = []
        for term in search_terms:
            search_url = self._search_url(term)
            self._notify(
                observer,
                stage="term_started",
                term=term,
                url=search_url,
                message=f"Searching Fiverr marketplace for '{term}'.",
            )
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            challenge_paths = self._capture_challenge_if_present(page, term)
            if challenge_paths is not None:
                html_path, screenshot_path = challenge_paths
                self._notify(
                    observer,
                    stage="challenge_detected",
                    level="warning",
                    term=term,
                    url=page.url,
                    message="Fiverr returned an anti-bot challenge page instead of public gig results.",
                    debug_html_path=str(html_path),
                    debug_screenshot_path=str(screenshot_path),
                )
                return [], ConnectorStatus(
                    connector=self.name,
                    status="warning",
                    detail="Fiverr returned an anti-bot challenge page. Open the saved debug screenshot or HTML artifact to inspect it.",
                )
            raw_cards = page.locator(self.config.fiverr_marketplace_card_selector).count()
            self._notify(
                observer,
                stage="page_loaded",
                term=term,
                url=page.url,
                result_count=raw_cards,
                message=f"Loaded marketplace page for '{term}' with {raw_cards} visible cards before filtering.",
            )
            term_gigs = self._extract_page_gigs(page, term, search_url=page.url, observer=observer)
            gigs.extend(term_gigs)
            self._notify(
                observer,
                stage="term_completed",
                term=term,
                url=page.url,
                result_count=len(term_gigs),
                message=f"Captured {len(term_gigs)} parsed gig cards for '{term}'.",
            )
        return gigs, None

    def _resolve_browser_channel(self, playwright) -> str | None:
        preferred = self.config.fiverr_marketplace_browser_channel
        if preferred not in {"auto", "msedge", "chrome", "chromium"}:
            preferred = "auto"
        if preferred == "chromium":
            return None
        if preferred != "auto":
            return preferred
        for candidate in ("msedge", "chrome"):
            try:
                browser_type = getattr(playwright, "chromium", None)
                if browser_type is None:
                    continue
                # Channel availability is checked lazily by launch_persistent_context.
                return candidate
            except Exception:
                continue
        return None

    def _extract_page_gigs(self, page, term: str, *, search_url: str, observer=None) -> list[MarketplaceGig]:
        cards = page.locator(self.config.fiverr_marketplace_card_selector)
        count = min(cards.count(), self.config.fiverr_marketplace_max_results)
        gigs: list[MarketplaceGig] = []
        for index in range(count):
            card = cards.nth(index)
            title = self._safe_text(card, self.config.fiverr_marketplace_title_selector)
            if not title:
                continue
            url = self._safe_href(card, self.config.fiverr_marketplace_link_selector, page.url)
            rank_position, page_number, is_first_page = self._extract_rank_metadata(url, fallback_position=index + 1)
            gig = MarketplaceGig(
                title=title,
                url=url,
                seller_name=self._safe_text(card, self.config.fiverr_marketplace_seller_selector),
                starting_price=self._safe_price(card, self.config.fiverr_marketplace_price_selector),
                rating=self._safe_float(card, self.config.fiverr_marketplace_rating_selector),
                reviews_count=self._safe_int(card, self.config.fiverr_marketplace_reviews_selector),
                delivery_days=self._safe_delivery_days(card, self.config.fiverr_marketplace_delivery_selector),
                badges=self._safe_multi_text(card, self.config.fiverr_marketplace_badge_selector),
                snippet=self._safe_text(card, self.config.fiverr_marketplace_snippet_selector),
                matched_term=term,
                rank_position=rank_position,
                page_number=page_number,
                is_first_page=is_first_page,
                search_url=search_url,
            )
            gigs.append(gig)
            self._notify(
                observer,
                stage="gig_found",
                term=term,
                url=gig.url,
                message=f"Parsed competitor gig '{gig.title}'.",
                gig_title=gig.title,
                seller_name=gig.seller_name,
                starting_price=gig.starting_price,
                rating=gig.rating,
            )
        return gigs

    def _safe_text(self, card, selector: str) -> str:
        for piece in self._selector_parts(selector):
            locator = card.locator(piece)
            if locator.count():
                try:
                    text = (locator.first.inner_text(timeout=3000) or "").strip()
                except Exception:
                    text = ""
                if text:
                    return text
        return ""

    def _safe_multi_text(self, card, selector: str) -> list[str]:
        values: list[str] = []
        for piece in self._selector_parts(selector):
            locator = card.locator(piece)
            try:
                count = min(locator.count(), 5)
            except Exception:
                count = 0
            for index in range(count):
                try:
                    text = (locator.nth(index).inner_text(timeout=2000) or "").strip()
                except Exception:
                    text = ""
                if text and text not in values:
                    values.append(text)
        return values

    def _safe_href(self, card, selector: str, base_url: str) -> str:
        for piece in self._selector_parts(selector):
            locator = card.locator(piece)
            if locator.count():
                try:
                    href = locator.first.get_attribute("href", timeout=3000) or ""
                except Exception:
                    href = ""
                if href:
                    return urljoin(base_url, href)
        return ""

    def _safe_price(self, card, selector: str) -> float | None:
        return self._extract_number(self._safe_text(card, selector))

    def _safe_float(self, card, selector: str) -> float | None:
        return self._extract_number(self._safe_text(card, selector))

    def _safe_int(self, card, selector: str) -> int | None:
        number = self._extract_number(self._safe_text(card, selector))
        return int(number) if number is not None else None

    def _safe_delivery_days(self, card, selector: str) -> int | None:
        text = self._safe_text(card, selector)
        return self._extract_delivery_days(text)

    def _extract_delivery_days(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*(?:day|days)", text.lower())
        if match:
            return int(match.group(1))
        return None

    def _extract_number(self, text: str) -> float | None:
        cleaned = text.replace(",", "")
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if not match:
            return None
        return float(match.group(1))

    def _extract_gig_page_overview(self, page, html: str, gig_url: str) -> GigPageOverview:
        json_ld = self._extract_json_ld_data(html)
        title = self._extract_json_ld_value(json_ld, "name") or self._safe_page_text(page, "h1")
        description = (
            self._extract_json_ld_value(json_ld, "description")
            or self._safe_meta_content(page, 'meta[name="description"]')
            or self._safe_meta_content(page, 'meta[property="og:description"]')
        )
        seller_name = (
            self._extract_json_ld_nested_value(json_ld, ["brand", "name"])
            or self._extract_json_ld_nested_value(json_ld, ["provider", "name"])
            or self._safe_page_text(page, '[data-testid="seller-name"], [class*="seller"]')
        )
        price = self._extract_json_ld_nested_value(json_ld, ["offers", "price"])
        rating = self._extract_json_ld_nested_value(json_ld, ["aggregateRating", "ratingValue"])
        reviews_count = self._extract_json_ld_nested_value(json_ld, ["aggregateRating", "reviewCount"])
        clean_title = self._clean_title(title or page.title())
        seller_text = str(seller_name or "").strip()
        if seller_text.lower() == "fiverr":
            seller_text = self._fallback_seller_name_from_url(gig_url)
        return GigPageOverview(
            url=page.url or gig_url,
            title=clean_title,
            seller_name=seller_text,
            description_excerpt=str(description or "").strip(),
            starting_price=float(price) if price not in {None, ""} else self._extract_price_from_html(html),
            rating=float(rating) if rating not in {None, ""} else self._extract_rating_from_html(html),
            reviews_count=int(float(reviews_count)) if reviews_count not in {None, ""} else self._extract_reviews_from_html(html),
            tags=self._extract_keywords_from_text(f"{clean_title} {description or ''}")[:8],
        )

    def _extract_gig_page_overview_from_html(self, html: str, gig_url: str) -> GigPageOverview:
        json_ld = self._extract_json_ld_data(html)
        title = self._extract_json_ld_value(json_ld, "name") or self._extract_title_from_html(html)
        description = (
            self._extract_json_ld_value(json_ld, "description")
            or self._extract_meta_content_from_html(html, "description")
            or self._extract_meta_property_content_from_html(html, "og:description")
        )
        seller_name = (
            self._extract_json_ld_nested_value(json_ld, ["brand", "name"])
            or self._extract_json_ld_nested_value(json_ld, ["provider", "name"])
        )
        price = self._extract_json_ld_nested_value(json_ld, ["offers", "price"])
        rating = self._extract_json_ld_nested_value(json_ld, ["aggregateRating", "ratingValue"])
        reviews_count = self._extract_json_ld_nested_value(json_ld, ["aggregateRating", "reviewCount"])
        clean_title = self._clean_title(title or "")
        seller_text = str(seller_name or "").strip()
        if seller_text.lower() == "fiverr":
            seller_text = self._fallback_seller_name_from_url(gig_url)
        return GigPageOverview(
            url=gig_url,
            title=clean_title,
            seller_name=seller_text,
            description_excerpt=str(description or "").strip(),
            starting_price=float(price) if price not in {None, ""} else self._extract_price_from_html(html),
            rating=float(rating) if rating not in {None, ""} else self._extract_rating_from_html(html),
            reviews_count=int(float(reviews_count)) if reviews_count not in {None, ""} else self._extract_reviews_from_html(html),
            tags=self._extract_keywords_from_text(f"{clean_title} {description or ''}")[:8],
        )

    def _selector_parts(self, selector: str) -> list[str]:
        return [part.strip() for part in selector.split(",") if part.strip()]

    def _dedupe(self, gigs: list[MarketplaceGig]) -> list[MarketplaceGig]:
        seen: set[str] = set()
        unique: list[MarketplaceGig] = []
        for gig in gigs:
            key = gig.url or gig.title.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(gig)
        return unique

    def _capture_challenge_if_present(self, page, term: str) -> tuple[Path, Path] | None:
        if not self._is_challenge_page(page):
            return None

        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        safe_term = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-") or "search"
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        html_path = artifacts_dir / f"marketplace-challenge-{safe_term}-{stamp}.html"
        screenshot_path = artifacts_dir / f"marketplace-challenge-{safe_term}-{stamp}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(screenshot_path), full_page=True)
        return html_path, screenshot_path

    def _is_challenge_page(self, page) -> bool:
        try:
            body_text = (page.locator("body").inner_text(timeout=3000) or "").lower()
        except Exception:
            return False
        return "it needs a human touch" in body_text or "pxcr" in body_text

    def _safe_page_text(self, page, selector: str) -> str:
        for piece in self._selector_parts(selector):
            locator = page.locator(piece)
            if locator.count():
                try:
                    text = (locator.first.inner_text(timeout=3000) or "").strip()
                except Exception:
                    text = ""
                if text:
                    return text
        return ""

    def _safe_meta_content(self, page, selector: str) -> str:
        locator = page.locator(selector)
        if not locator.count():
            return ""
        try:
            value = locator.first.get_attribute("content", timeout=3000) or ""
        except Exception:
            value = ""
        return value.strip()

    def _extract_json_ld_data(self, html: str) -> list[dict]:
        blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        data: list[dict] = []
        for block in blocks:
            try:
                parsed = json.loads(block.strip())
            except Exception:
                continue
            if isinstance(parsed, list):
                data.extend(item for item in parsed if isinstance(item, dict))
            elif isinstance(parsed, dict):
                data.append(parsed)
        return data

    def _extract_json_ld_value(self, items: list[dict], key: str):
        for item in items:
            if key in item and isinstance(item[key], (str, int, float)):
                return item[key]
        return None

    def _extract_json_ld_nested_value(self, items: list[dict], path: list[str]):
        for item in items:
            current = item
            for key in path:
                if isinstance(current, list):
                    current = current[0] if current else None
                if not isinstance(current, dict) or key not in current:
                    current = None
                    break
                current = current[key]
            if isinstance(current, (str, int, float)):
                return current
        return None

    def _clean_title(self, title: str) -> str:
        cleaned = (title or "").strip()
        cleaned = re.sub(r"\s*\|\s*Fiverr.*$", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _extract_price_from_html(self, html: str) -> float | None:
        match = re.search(r'"price"\s*:\s*"?(?P<value>\d+(?:\.\d+)?)"?', html, flags=re.IGNORECASE)
        return float(match.group("value")) if match else None

    def _extract_rating_from_html(self, html: str) -> float | None:
        match = re.search(r'"ratingValue"\s*:\s*"?(?P<value>\d+(?:\.\d+)?)"?', html, flags=re.IGNORECASE)
        return float(match.group("value")) if match else None

    def _extract_reviews_from_html(self, html: str) -> int | None:
        match = re.search(r'"reviewCount"\s*:\s*"?(?P<value>\d+)"?', html, flags=re.IGNORECASE)
        return int(match.group("value")) if match else None

    def _extract_keywords_from_text(self, text: str) -> list[str]:
        phrases = [
            "wordpress speed",
            "core web vitals",
            "pagespeed insights",
            "woocommerce speed",
            "speed optimization",
            "gtmetrix",
            "lcp",
            "cls",
            "performance",
            "audit",
        ]
        haystack = text.lower()
        return [phrase for phrase in phrases if phrase in haystack]

    def _fallback_seller_name_from_url(self, gig_url: str) -> str:
        path_parts = [part for part in urlparse(gig_url).path.split("/") if part]
        return path_parts[0] if path_parts else ""

    def _reader_url(self, url: str) -> str:
        base = self.config.marketplace_reader_base_url.rstrip("/")
        return f"{base}/{url}"

    def _reader_get_markdown(self, url: str) -> str:
        return self._http_get_html(
            self._reader_url(url),
            extra_headers={
                "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8",
                "X-Respond-With": "markdown",
            },
        )

    def _extract_gig_page_overview_from_markdown(self, markdown: str, gig_url: str) -> GigPageOverview:
        lines = [line.strip() for line in markdown.splitlines()]
        title = ""
        seller_name = ""

        for line in lines:
            heading_match = re.match(r"^#\s+(.*?)\s+by\s+(.+?)\s+\|\s+Fiverr$", line, flags=re.IGNORECASE)
            if heading_match:
                title = heading_match.group(1).strip()
                seller_name = heading_match.group(2).strip()
        if not title:
            for line in lines:
                if line.startswith("# "):
                    candidate = re.sub(r"\s+\|\s+Fiverr$", "", line[2:].strip(), flags=re.IGNORECASE)
                    if len(candidate) > 8:
                        title = candidate
                        break
        if not seller_name:
            for line in lines:
                seller_match = re.match(r"^\[([^\]]+)\]\(https://www\.fiverr\.com/[^/?#]+\?source=gig_page\)", line)
                if seller_match:
                    seller_name = seller_match.group(1).strip()
                    break
        if not seller_name:
            seller_name = self._fallback_seller_name_from_url(gig_url)

        about_index = next(
            (index for index, line in enumerate(lines) if "about this gig" in line.lower()),
            -1,
        )
        description_lines: list[str] = []
        if about_index >= 0:
            for line in lines[about_index + 1 : about_index + 14]:
                cleaned = line.strip()
                if not cleaned:
                    if description_lines:
                        break
                    continue
                if cleaned.startswith("#") or cleaned.startswith("*") or cleaned.startswith("[") or cleaned.lower().startswith("read more"):
                    continue
                if "what's included" in cleaned.lower() or "why choose me" in cleaned.lower():
                    break
                description_lines.append(cleaned)

        description_excerpt = " ".join(description_lines[:3]).strip()
        if not description_excerpt:
            for line in lines:
                if len(line) > 40 and not line.startswith("[") and not line.startswith("!"):
                    description_excerpt = line
                    break

        price_match = re.search(r"\$(\d+(?:\.\d+)?)", markdown)
        price = float(price_match.group(1)) if price_match else None
        rating_match = re.search(r"\*\*(\d+(?:\.\d+)?)\*\*\(([^)]+)\)", markdown)
        rating = float(rating_match.group(1)) if rating_match else None
        reviews_count = self._parse_reviews_count_from_text(
            next(
                (
                    match.group(1)
                    for match in re.finditer(
                        r"##\s+([0-9kK+., ]+)\s+reviews?\s+for\s+this\s+Gig",
                        markdown,
                    )
                ),
                "",
            )
        )
        if reviews_count is None and rating_match:
            reviews_count = self._parse_reviews_count_from_text(rating_match.group(2))

        clean_title = self._clean_title(title)
        return GigPageOverview(
            url=gig_url,
            title=clean_title,
            seller_name=seller_name,
            description_excerpt=description_excerpt,
            starting_price=price,
            rating=rating,
            reviews_count=reviews_count,
            tags=self._extract_keywords_from_text(f"{clean_title} {description_excerpt}")[:8],
        )

    def _extract_search_gigs_from_markdown(self, markdown: str, term: str, *, search_url: str = "") -> list[MarketplaceGig]:
        lines = [line.strip() for line in markdown.splitlines()]
        gigs: list[MarketplaceGig] = []
        current_seller = ""
        recent_badges: list[str] = []
        current_rank = 0

        for index, line in enumerate(lines):
            if not line:
                continue

            seller_match = re.match(
                r"^\[([^\]]+)\]\(https://www\.fiverr\.com/([^/?#]+)\?source=gig_cards[^)]*\)",
                line,
            )
            if seller_match:
                current_seller = seller_match.group(1).strip()
                continue

            if line in {"Top Rated", "Level 2", "Level 1", "Vetted Pro", "Fiverr Pro", "Pro"}:
                if line not in recent_badges:
                    recent_badges.append(line)
                recent_badges = recent_badges[-3:]
                continue

            title_match = re.match(r"^\[([^\]]+)\]\((https://www\.fiverr\.com/[^)]+)\)$", line)
            if not title_match:
                continue

            title = title_match.group(1).strip()
            url = title_match.group(2).strip()
            if not self._looks_like_marketplace_title(title, url):
                continue
            current_rank += 1

            rating = None
            reviews_count = None
            starting_price = None
            delivery_days = None
            snippet = ""
            rank_position, page_number, is_first_page = self._extract_rank_metadata(url, fallback_position=current_rank)
            for look_ahead in lines[index + 1 : index + 8]:
                if not look_ahead:
                    continue
                rating_match = re.search(r"\*\*(\d+(?:\.\d+)?)\*\*\(([^)]+)\)", look_ahead)
                if rating is None and rating_match:
                    rating = float(rating_match.group(1))
                    reviews_count = self._parse_reviews_count_from_text(rating_match.group(2))
                if starting_price is None:
                    price_match = re.search(r"From\$(\d+(?:\.\d+)?)", look_ahead, flags=re.IGNORECASE)
                    if price_match:
                        starting_price = float(price_match.group(1))
                if delivery_days is None:
                    delivery_days = self._extract_delivery_days(look_ahead)
                if not snippet and len(look_ahead) > 20 and not look_ahead.startswith("[") and not look_ahead.startswith("!"):
                    snippet = look_ahead

            gigs.append(
                MarketplaceGig(
                    title=self._clean_title(title),
                    url=url,
                    seller_name=current_seller,
                    starting_price=starting_price,
                    rating=rating,
                    reviews_count=reviews_count,
                    delivery_days=delivery_days,
                    badges=recent_badges[:],
                    snippet=snippet,
                    matched_term=term,
                    rank_position=rank_position,
                    page_number=page_number,
                    is_first_page=is_first_page,
                    search_url=search_url,
                )
            )
        return gigs

    def _extract_rank_metadata(self, url: str, *, fallback_position: int) -> tuple[int | None, int | None, bool]:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        rank_position = self._safe_query_int(params, "pos") or fallback_position
        page_number = self._safe_query_int(params, "page") or 1
        is_first_page = page_number == 1 and rank_position <= 10
        return rank_position, page_number, is_first_page

    def _safe_query_int(self, params: dict[str, list[str]], key: str) -> int | None:
        values = params.get(key) or []
        if not values:
            return None
        try:
            return int(values[0])
        except (TypeError, ValueError):
            return None

    def _looks_like_marketplace_title(self, text: str, url: str) -> bool:
        lowered = text.lower()
        if lowered.startswith("from$") or lowered.startswith("image ") or lowered == "read more":
            return False
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            return False
        return any(
            token in lowered
            for token in ["wordpress", "speed", "pagespeed", "page speed", "core web vitals", "gtmetrix", "woocommerce"]
        )

    def _parse_reviews_count_from_text(self, text: str) -> int | None:
        cleaned = str(text or "").strip().lower().replace(",", "")
        if not cleaned:
            return None
        cleaned = cleaned.replace("reviews", "").replace("review", "").strip()
        match = re.search(r"(\d+(?:\.\d+)?)\s*k\+?", cleaned)
        if match:
            return int(float(match.group(1)) * 1000)
        match = re.search(r"(\d+)", cleaned)
        if match:
            return int(match.group(1))
        return None

    def _http_get_html(self, url: str, *, extra_headers: dict[str, str] | None = None) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        if extra_headers:
            headers.update(extra_headers)
        try:
            import requests

            response = requests.get(
                url,
                timeout=30,
                headers=headers,
            )
            response.raise_for_status()
            return response.text
        except ImportError:
            request = Request(
                url,
                headers=headers,
            )
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="ignore")

    def _looks_like_challenge_html(self, html: str) -> bool:
        lowered = html.lower()
        return "complete the task and we'll get you right back into fiverr" in lowered or "errcode pxcr" in lowered

    def _extract_title_from_html(self, html: str) -> str:
        match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return re.sub(r"\s+", " ", match.group(1)).strip()

    def _extract_meta_content_from_html(self, html: str, name: str) -> str:
        match = re.search(
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

    def _extract_meta_property_content_from_html(self, html: str, prop: str) -> str:
        match = re.search(
            rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\'](.*?)["\']',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

    def _notify(self, observer, **event) -> None:
        if observer is None:
            return
        observer(event)
