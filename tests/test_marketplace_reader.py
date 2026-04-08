from __future__ import annotations

import unittest

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.connectors.fiverr_marketplace import FiverrMarketplaceConnector


GIG_MARKDOWN = """
Title: Tezpage: I will speed up wordpress and improve google page speed for 90 pagespeed insight speed for $125 on fiverr.com

URL Source: https://www.fiverr.com/tezpage/optimize-wordpress-for-90-plus-google-pagespeed-score

Markdown Content:
# Speed up wordpress and improve google page speed for 90 pagespeed insight speed by Tezpage | Fiverr

### **Quick Boost Plan**

$125

# I will speed up wordpress and improve google page speed for 90 pagespeed insight speed

[Aman G](https://www.fiverr.com/tezpage?source=gig_page)

**5.0**(1)

##### About this Gig

WordPress Speed Optimization - 90+ PageSpeed Score Guaranteed or Full Refund

Slow WordPress site killing your traffic? I'll fix it fast.

I optimize WordPress sites to 90+ Google PageSpeed score on mobile and desktop.

## 1 reviews for this Gig
"""


SEARCH_MARKDOWN = """
Title: Fiverr / Search Results for 'wordpress speed'

URL Source: https://www.fiverr.com/search/gigs?query=wordpress+speed

Markdown Content:
[Wordprofessors](https://www.fiverr.com/wordprofessors?source=gig_cards&referrer_gig_slug=increase-wordpress-speed-optimization-for-gtmetrix-and-pagespeed)

Top Rated

[I will do wordpress speed optimization for google pagespeed insight](https://www.fiverr.com/wordprofessors/increase-wordpress-speed-optimization-for-gtmetrix-and-pagespeed?context_referrer=search_gigs_with_modalities)

**5.0**(804)

[From$60](https://www.fiverr.com/wordprofessors/increase-wordpress-speed-optimization-for-gtmetrix-and-pagespeed?context_referrer=search_gigs_with_modalities)

[Kofil](https://www.fiverr.com/kofil2?source=gig_cards&referrer_gig_slug=speed-up-wordpress-website-speed)

Level 2

[I will speed up wordpress website for google pagespeed insights](https://www.fiverr.com/kofil2/speed-up-wordpress-website-speed?context_referrer=search_gigs_with_modalities)

**4.9**(1k+)

[From$30](https://www.fiverr.com/kofil2/speed-up-wordpress-website-speed?context_referrer=search_gigs_with_modalities)
"""


ANIME_LOGO_SEARCH_MARKDOWN = """
Title: Fiverr / Search Results for 'anime logo'

URL Source: https://www.fiverr.com/search/gigs?query=anime+logo

Markdown Content:
[Pixelkoi](https://www.fiverr.com/pixelkoi?source=gig_cards&referrer_gig_slug=design-anime-logo)

Level 2

[I will design anime logo for your brand or stream](https://www.fiverr.com/pixelkoi/design-anime-logo?context_referrer=search_gigs_with_modalities&pos=1&page=1)

**4.9**(230)

[From$35](https://www.fiverr.com/pixelkoi/design-anime-logo?context_referrer=search_gigs_with_modalities&pos=1&page=1)

[Otakustudio](https://www.fiverr.com/otakustudio?source=gig_cards&referrer_gig_slug=create-anime-logo-design)

Top Rated

[I will create custom anime logo design](https://www.fiverr.com/otakustudio/create-anime-logo-design?context_referrer=search_gigs_with_modalities&pos=2&page=1)

**5.0**(410)

[From$55](https://www.fiverr.com/otakustudio/create-anime-logo-design?context_referrer=search_gigs_with_modalities&pos=2&page=1)
"""


class MarketplaceReaderTests(unittest.TestCase):
    def test_reader_parses_gig_page_markdown(self) -> None:
        connector = FiverrMarketplaceConnector(
            GigOptimizerConfig(
                marketplace_reader_enabled=True,
                marketplace_reader_base_url="https://r.jina.ai/http://",
            )
        )

        overview = connector._extract_gig_page_overview_from_markdown(  # noqa: SLF001
            GIG_MARKDOWN,
            "https://www.fiverr.com/tezpage/optimize-wordpress-for-90-plus-google-pagespeed-score",
        )

        self.assertIn("wordpress", overview.title.lower())
        self.assertEqual(overview.seller_name, "Tezpage")
        self.assertEqual(overview.starting_price, 125.0)
        self.assertEqual(overview.rating, 5.0)
        self.assertEqual(overview.reviews_count, 1)
        self.assertTrue(overview.tags)

    def test_reader_parses_search_markdown_into_competitor_gigs(self) -> None:
        connector = FiverrMarketplaceConnector(
            GigOptimizerConfig(
                marketplace_reader_enabled=True,
                marketplace_reader_base_url="https://r.jina.ai/http://",
            )
        )

        gigs = connector._extract_search_gigs_from_markdown(SEARCH_MARKDOWN, "wordpress speed")  # noqa: SLF001

        self.assertGreaterEqual(len(gigs), 2)
        self.assertEqual(gigs[0].seller_name, "Wordprofessors")
        self.assertEqual(gigs[0].starting_price, 60.0)
        self.assertEqual(gigs[0].reviews_count, 804)
        self.assertIn("Top Rated", gigs[0].badges)
        self.assertEqual(gigs[1].reviews_count, 1000)

    def test_reader_parses_non_wordpress_search_markdown(self) -> None:
        connector = FiverrMarketplaceConnector(
            GigOptimizerConfig(
                marketplace_reader_enabled=True,
                marketplace_reader_base_url="https://r.jina.ai/http://",
            )
        )

        gigs = connector._extract_search_gigs_from_markdown(ANIME_LOGO_SEARCH_MARKDOWN, "anime logo")  # noqa: SLF001

        self.assertEqual(len(gigs), 2)
        self.assertIn("anime logo", gigs[0].title.lower())
        self.assertEqual(gigs[0].matched_term, "anime logo")
        self.assertEqual(gigs[0].rank_position, 1)
        self.assertTrue(gigs[0].is_first_page)


if __name__ == "__main__":
    unittest.main()
