import sys, pathlib, types, tempfile, unittest

sys.path.insert(0, '/tmp/gigop_commit')
import gigoptimizer.models as _m
from gigoptimizer.models import (
    GigSnapshot, GigAnalytics, GigPackage, GigFAQ,
    CompetitorGig, MarketplaceGig, ReviewSnippet,
)

def _direct(mod_name, relpath):
    p = pathlib.Path('/tmp/gigop_commit') / relpath
    src = p.read_text()
    src = src.replace('from ..models import', 'from gigoptimizer.models import')
    src = src.replace('from ..config import GigOptimizerConfig', '')
    mod = types.ModuleType(mod_name)
    mod.__file__ = str(p)
    mod.__package__ = 'gigoptimizer.services'
    mod.__name__ = mod_name
    mod.__spec__ = None
    sys.modules[mod_name] = mod
    exec(compile(src, str(p), 'exec'), mod.__dict__)
    return mod

hs = _direct('gigoptimizer.services.health_score_service', 'gigoptimizer/services/health_score_service.py')
tg = _direct('gigoptimizer.services.tag_gap_analyzer',     'gigoptimizer/services/tag_gap_analyzer.py')
pa = _direct('gigoptimizer.services.price_alert_service',  'gigoptimizer/services/price_alert_service.py')

GigHealthScoreEngine = hs.GigHealthScoreEngine
TagGapAnalyzer       = tg.TagGapAnalyzer
PriceAlertService    = pa.PriceAlertService

# ── Fixtures (field names match actual model signatures) ──────────────────
SNAP = GigSnapshot(
    niche="wordpress-speed",
    title="I will speed up your WordPress website for Google PageSpeed 90 plus score",
    description="A" * 1300,
    tags=["wordpress speed", "pagespeed", "core web vitals"],
    packages=[
        GigPackage("Basic",    60.0,  delivery_days=3, revisions=2),
        GigPackage("Standard", 120.0, delivery_days=2, revisions=3),
        GigPackage("Premium",  250.0, delivery_days=1, revisions=5),
    ],
    faq=[GigFAQ("What do you need?", "WP admin."), GigFAQ("Revisions?", "As needed.")],
    analytics=GigAnalytics(impressions=5000, clicks=200, orders=18, average_response_time_hours=1.5),
    reviews=[ReviewSnippet(text="Great", rating=5), ReviewSnippet(text="Fast", rating=5)] * 12,
    competitors=[
        CompetitorGig("WP Speed Pro", starting_price=55.0, reviews_count=400, rating=4.9,
                      tags=["wordpress speed","gtmetrix","pagespeed","site speed","woocommerce"]),
        CompetitorGig("SpeedMaster",  starting_price=80.0, reviews_count=300, rating=4.8,
                      tags=["wordpress speed","core web vitals","pagespeed","lcp fix"]),
    ],
)

EMPTY = GigSnapshot(niche="x", title="short", description="x")

MGS = [
    MarketplaceGig(title="WP Speed Pro", seller_name="wpspeedpro",  starting_price=55.0, reviews_count=400),
    MarketplaceGig(title="SpeedMaster",  seller_name="speedmaster", starting_price=80.0, reviews_count=300),
    MarketplaceGig(title="FastWP",       seller_name="fastwp",      starting_price=45.0, reviews_count=150),
]


class TestGigHealthScore(unittest.TestCase):
    def setUp(self): self.e = GigHealthScoreEngine()

    def test_overall_range(self):
        h = self.e.score(SNAP)
        self.assertIsInstance(h.overall, int)
        self.assertIn(h.overall, range(101))

    def test_five_dimensions(self):
        h = self.e.score(SNAP)
        self.assertEqual(len(h.dimensions), 5)
        self.assertEqual({d.name for d in h.dimensions},
                         {"SEO","CRO","Competitive","Social Proof","Delivery"})

    def test_band_valid(self):
        h = self.e.score(SNAP)
        self.assertIn(h.band, ("Healthy","Fair","At Risk","Critical"))
        self.assertIn(h.band_color, ("green","yellow","orange","red"))

    def test_top_action_nonempty(self):
        self.assertGreater(len(self.e.score(SNAP).top_action), 10)

    def test_to_dict_keys(self):
        d = self.e.score(SNAP).to_dict()
        for k in ("overall","band","band_color","dimensions","top_action"):
            self.assertIn(k, d)

    def test_seo_score_good_snapshot(self):
        seo = next(d.score for d in self.e.score(SNAP).dimensions if d.name == "SEO")
        self.assertGreater(seo, 50, f"SEO={seo}")

    def test_cro_score_with_analytics(self):
        cro = next(d.score for d in self.e.score(SNAP).dimensions if d.name == "CRO")
        self.assertGreater(cro, 40, f"CRO={cro}")

    def test_empty_snap_is_critical_or_at_risk(self):
        self.assertIn(self.e.score(EMPTY).band, ("Critical","At Risk"))

    def test_weights_sum_to_one(self):
        total = sum(d.weight for d in self.e.score(SNAP).dimensions)
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_no_analytics_cro_is_neutral(self):
        cro = next(d for d in self.e.score(EMPTY).dimensions if d.name == "CRO")
        self.assertEqual(cro.score, 50)

    def test_all_dimension_scores_in_range(self):
        for d in self.e.score(SNAP).dimensions:
            self.assertIn(d.score, range(101), f"{d.name} score {d.score} out of range")


class TestTagGapAnalyzer(unittest.TestCase):
    # MarketplaceGig has no 'tags' field in this repo version — we test with
    # CompetitorGig (via snapshot.competitors) which does have tags.
    def setUp(self):
        self.az = TagGapAnalyzer()

    def test_coverage_score_range(self):
        r = self.az.analyze(SNAP)   # uses snapshot.competitors which have tags
        self.assertIn(r.coverage_score, range(101))

    def test_my_tags_match_snapshot(self):
        r = self.az.analyze(SNAP)
        self.assertEqual(set(r.my_tags), set(SNAP.tags))

    def test_recommendations_present(self):
        r = self.az.analyze(SNAP)
        self.assertGreater(len(r.recommendations), 0)

    def test_to_dict_keys(self):
        d = self.az.analyze(SNAP).to_dict()
        for k in ("my_tags","missing_tags","unique_tags","shared_tags",
                  "power_tags","coverage_score","recommendations"):
            self.assertIn(k, d)

    def test_missing_not_in_my_tags(self):
        r = self.az.analyze(SNAP)
        my = {t.lower() for t in r.my_tags}
        for t in r.missing_tags:
            self.assertNotIn(t, my, f"'{t}' listed as missing but present in my_tags")

    def test_missing_is_subset_of_shared(self):
        r = self.az.analyze(SNAP)
        shared_set = set(r.shared_tags)
        for t in r.missing_tags:
            self.assertIn(t, shared_set, f"'{t}' in missing but not in shared")

    def test_no_competitors_returns_gracefully(self):
        r = self.az.analyze(EMPTY)
        self.assertIsInstance(r.coverage_score, int)
        self.assertGreater(len(r.recommendations), 0)

    def test_shared_has_common_competitor_tags(self):
        r = self.az.analyze(SNAP)
        # Both competitors have "wordpress speed" and "pagespeed"
        self.assertIn("wordpress speed", r.shared_tags)
        self.assertIn("pagespeed", r.shared_tags)


class TestPriceAlertService(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.svc  = PriceAlertService(data_dir=pathlib.Path(self._tmp.name))
        self.gid  = "test-gig-001"

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_run_zero_alerts(self):
        self.assertEqual(len(self.svc.check_and_alert(self.gid, MGS)), 0)

    def test_baseline_stores_prices(self):
        self.svc.check_and_alert(self.gid, MGS)
        b = self.svc.get_baseline(self.gid)
        self.assertEqual(b["prices"]["wpspeedpro"], 55.0)

    def test_baseline_stores_reviews(self):
        self.svc.check_and_alert(self.gid, MGS)
        b = self.svc.get_baseline(self.gid)
        self.assertEqual(b["reviews"]["wpspeedpro"], 400)

    def test_price_drop_alert_fires(self):
        self.svc.check_and_alert(self.gid, MGS)
        dropped = [MarketplaceGig(title="X", seller_name="wpspeedpro",
                                  starting_price=40.0, reviews_count=400)]
        types = [a.alert_type for a in self.svc.check_and_alert(self.gid, dropped)]
        self.assertIn("price_drop", types)

    def test_price_spike_alert_fires(self):
        self.svc.check_and_alert(self.gid, MGS)
        spiked = [MarketplaceGig(title="X", seller_name="wpspeedpro",
                                 starting_price=75.0, reviews_count=400)]
        types = [a.alert_type for a in self.svc.check_and_alert(self.gid, spiked)]
        self.assertIn("price_spike", types)

    def test_review_surge_alert_fires(self):
        self.svc.check_and_alert(self.gid, MGS)
        surged = [MarketplaceGig(title="X", seller_name="speedmaster",
                                 starting_price=80.0, reviews_count=360)]
        types = [a.alert_type for a in self.svc.check_and_alert(self.gid, surged)]
        self.assertIn("review_surge", types)

    def test_small_change_no_alert(self):
        self.svc.check_and_alert(self.gid, MGS)
        small = [MarketplaceGig(title="X", seller_name="wpspeedpro",
                                starting_price=52.0, reviews_count=405)]
        self.assertEqual(len(self.svc.check_and_alert(self.gid, small)), 0)

    def test_same_data_idempotent(self):
        self.svc.check_and_alert(self.gid, MGS)
        self.svc.check_and_alert(self.gid, MGS)
        self.assertEqual(len(self.svc.check_and_alert(self.gid, MGS)), 0)

    def test_ws_event_format(self):
        self.svc.check_and_alert(self.gid, MGS)
        dropped = [MarketplaceGig(title="X", seller_name="wpspeedpro",
                                  starting_price=40.0, reviews_count=400)]
        ws = self.svc.check_and_alert(self.gid, dropped)[0].to_ws_event()
        self.assertEqual(ws["type"], "price_alert")
        self.assertIn("alert_type", ws)
        self.assertIn("message", ws)

    def test_to_dict_required_keys(self):
        self.svc.check_and_alert(self.gid, MGS)
        dropped = [MarketplaceGig(title="X", seller_name="wpspeedpro",
                                  starting_price=40.0, reviews_count=400)]
        d = self.svc.check_and_alert(self.gid, dropped)[0].to_dict()
        for k in ("gig_id","seller_name","alert_type","message",
                  "old_value","new_value","change_pct"):
            self.assertIn(k, d)

    def test_clear_baseline(self):
        self.svc.check_and_alert(self.gid, MGS)
        self.svc.clear_baseline(self.gid)
        self.assertEqual(self.svc.get_baseline(self.gid)["prices"], {})

    def test_drop_message_contains_old_and_new_price(self):
        self.svc.check_and_alert(self.gid, MGS)
        dropped = [MarketplaceGig(title="X", seller_name="wpspeedpro",
                                  starting_price=40.0, reviews_count=400)]
        alert = next(a for a in self.svc.check_and_alert(self.gid, dropped)
                     if a.alert_type == "price_drop")
        self.assertIn("40", alert.message)
        self.assertIn("55", alert.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
