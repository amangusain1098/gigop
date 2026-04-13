"""Gig Health Score Engine.

Produces a structured 0-100 score with five weighted dimensions:

  SEO (25%)         title keywords, tag count, description length, FAQs
  CRO (25%)         impression-to-click rate, click-to-order rate
  Competitive (20%) price positioning vs competitors, review-count gap
  Social Proof (20%)review count, average rating, package variety
  Delivery (10%)    fastest delivery day, revisions clarity, response time

Colour bands:  80-100 Healthy (green) | 60-79 Fair (yellow)
               40-59 At Risk (orange)  |  0-39 Critical (red)
"""
import json
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from ..models import GigSnapshot, OptimizationReport
from ..assistant.client import build_default_client, LLMMessage


@dataclass(slots=True)
class DimensionScore:
    name: str
    score: int
    weight: float
    findings: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GigHealthScore:
    overall: int
    band: str
    band_color: str
    dimensions: list[DimensionScore]
    top_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "band": self.band,
            "band_color": self.band_color,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "top_action": self.top_action,
        }


class GigHealthScoreEngine:
    _WEIGHTS = {
        "SEO": 0.25,
        "CRO": 0.25,
        "Competitive": 0.20,
        "Social Proof": 0.20,
        "Delivery": 0.10,
    }

    def score(self, snapshot: GigSnapshot, report: OptimizationReport | None = None) -> GigHealthScore:
        # First attempt to score using the new AI Copilot (DeepSeek-R1)
        ai_score = self._score_with_ai(snapshot, report)
        if ai_score:
            return ai_score
        
        # Fallback to the offline heuristic deterministic engine
        return self._score_heuristic(snapshot, report)

    def _score_with_ai(self, snapshot: GigSnapshot, report: OptimizationReport | None) -> GigHealthScore | None:
        try:
            client = build_default_client()
            if client.name == "deterministic":
                return None  # No real AI available

            system_prompt = (
                "You are an expert Fiverr Gig Conversion Analyst.\n"
                "You will review the following GigSnapshot data and return a JSON object evaluating its health on a 0-100 scale.\n"
                "Evaluate 5 dimensions: SEO, CRO, Competitive, Social Proof, and Delivery.\n"
                "For findings and tips, be brutally honest but constructive about buyer psychology and persuasion, rather than just counting words.\n"
                "Your output MUST be ONLY raw JSON without any markdown formatting, matching this exact schema:\n"
                "{\n"
                '  "overall": 85,\n'
                '  "band": "Healthy",\n'
                '  "band_color": "green",\n'
                '  "top_action": "Your most urgent tip here.",\n'
                '  "dimensions": [\n'
                '    {"name": "SEO", "score": 80, "weight": 0.25, "findings": ["..."], "tips": ["..."]},\n'
                '    {"name": "CRO", "score": 75, "weight": 0.25, "findings": ["..."], "tips": ["..."]},\n'
                '    {"name": "Competitive", "score": 90, "weight": 0.20, "findings": ["..."], "tips": ["..."]},\n'
                '    {"name": "Social Proof", "score": 60, "weight": 0.20, "findings": ["..."], "tips": ["..."]},\n'
                '    {"name": "Delivery", "score": 95, "weight": 0.10, "findings": ["..."], "tips": ["..."]}\n'
                "  ]\n"
                "}\n"
            )

            gig_data = {
                "title": snapshot.title,
                "description": snapshot.description,
                "tags": snapshot.tags,
                "analytics": asdict(snapshot.analytics) if snapshot.analytics else None,
                "review_count": len(snapshot.reviews or []),
            }

            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=json.dumps(gig_data)),
            ]

            response = client.complete(messages, temperature=0.3, max_tokens=1500)
            
            # Extract JSON from potential <think> wrappers or markdown blocks
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            if text.rfind("}") > -1:
                text = text[text.find("{"):text.rfind("}")+1]

            data = json.loads(text.strip())
            
            dimensions = [
                DimensionScore(
                    name=d["name"], 
                    score=int(d["score"]), 
                    weight=float(d["weight"]), 
                    findings=d.get("findings", []), 
                    tips=d.get("tips", [])
                )
                for d in data.get("dimensions", [])
            ]
            
            # Use safe offline fallback for bands if AI hallucinates it
            overall = int(data.get("overall", 50))
            band, color = self._band(overall)

            return GigHealthScore(
                overall=overall,
                band=band,
                band_color=color,
                dimensions=dimensions,
                top_action=data.get("top_action", dimensions[0].tips[0] if dimensions and dimensions[0].tips else "Improve your gig copy.")
            )

        except Exception as e:
            # Silently fallback to heuristic if the AI fails or hallucinates JSON.
            import logging
            logging.getLogger(__name__).warning("AI Gig Health Score failed: %s. Falling back to heuristic.", e)
            return None

    def _score_heuristic(self, snapshot: GigSnapshot, report: OptimizationReport | None = None) -> GigHealthScore:
        dimensions = [
            self._seo_dimension(snapshot, report),
            self._cro_dimension(snapshot),
            self._competitive_dimension(snapshot, report),
            self._social_proof_dimension(snapshot),
            self._delivery_dimension(snapshot),
        ]
        overall = max(0, min(100, int(sum(d.score * d.weight for d in dimensions))))
        band, color = self._band(overall)
        worst = min(dimensions, key=lambda d: d.score)
        top_action = worst.tips[0] if worst.tips else f"Improve your {worst.name} score ({worst.score}/100)."
        return GigHealthScore(overall=overall, band=band, band_color=color,
                              dimensions=dimensions, top_action=top_action)

    # ── SEO (25%) ──────────────────────────────────────────────────────────
    def _seo_dimension(self, snapshot: GigSnapshot, report: OptimizationReport | None) -> DimensionScore:
        findings: list[str] = []
        tips: list[str] = []
        points = 0

        title_words = (snapshot.title or "").split()
        title_len = len(snapshot.title or "")
        if len(title_words) >= 8:
            points += 20
        elif len(title_words) >= 5:
            points += 12
            tips.append("Expand your gig title to at least 8 words covering your core buyer-intent keywords.")
        else:
            points += 4
            findings.append("Title is very short — likely missing important search keywords.")
            tips.append("Rewrite the title to 8-10 words that name the specific outcome buyers want.")
        if title_len > 75:
            findings.append("Title may be truncated in search results (>75 chars).")
            tips.append("Trim title to under 75 characters so it shows fully in Fiverr listings.")

        tag_count = len(snapshot.tags or [])
        if tag_count >= 5:
            points += 25
        elif tag_count >= 3:
            points += 15
            findings.append(f"Only {tag_count}/5 tags set.")
            tips.append("Fill all 5 tag slots with specific long-tail buyer-intent phrases.")
        elif tag_count > 0:
            points += 8
            findings.append(f"Only {tag_count} tags — leaving most search slots empty.")
            tips.append("Add 5 highly specific tags. Each is a separate search entry point.")
        else:
            findings.append("No tags found — severely limits discoverability.")
            tips.append("Add 5 specific tags immediately. This is your most urgent SEO fix.")

        desc_len = len((snapshot.description or "").strip())
        if desc_len >= 1200:
            points += 25
        elif desc_len >= 600:
            points += 18
            tips.append("Expand description to 1200+ characters, weaving keywords naturally.")
        elif desc_len >= 200:
            points += 10
            findings.append("Description is short — missing keywords and trust signals.")
            tips.append("Write a 1200+ character description covering deliverables, process, and credentials.")
        else:
            findings.append("Description is nearly empty — a critical SEO and conversion blocker.")
            tips.append("Write a complete gig description. This is your most important ranking signal.")

        faq_count = len(snapshot.faq or [])
        if faq_count >= 4:
            points += 15
        elif faq_count >= 2:
            points += 10
        elif faq_count == 1:
            points += 5
            tips.append("Add 4-6 FAQs covering delivery, revisions, scope, and what you need from buyers.")
        else:
            findings.append("No FAQs — buyers who cannot get quick answers go elsewhere.")
            tips.append("Add at least 4 FAQs. Gigs with FAQs convert measurably better.")

        if report and report.tag_recommendations:
            points = min(points + 5, 100)

        return DimensionScore(name="SEO", score=min(100, points),
                              weight=self._WEIGHTS["SEO"], findings=findings, tips=tips)

    # ── CRO (25%) ──────────────────────────────────────────────────────────
    def _cro_dimension(self, snapshot: GigSnapshot) -> DimensionScore:
        findings: list[str] = []
        tips: list[str] = []
        a = snapshot.analytics

        if not a.impressions:
            return DimensionScore(
                name="CRO", score=50, weight=self._WEIGHTS["CRO"],
                findings=["No analytics data yet — keep the gig live for 2+ weeks before evaluating CRO."],
                tips=["Enter impression/click/order data to get a real CRO score."],
            )

        points = 0
        ctr = (a.clicks / a.impressions) * 100
        if ctr >= 4.0:
            points += 45
        elif ctr >= 2.5:
            points += 32
            findings.append(f"CTR {ctr:.1f}% — room to improve the first-impression promise.")
            tips.append("A/B test a more outcome-driven title to push CTR above 4%.")
        elif ctr >= 1.0:
            points += 18
            findings.append(f"CTR {ctr:.1f}% — gig appears in search but rarely earns the click.")
            tips.append("Redesign thumbnail and rewrite title. The first impression is not converting.")
        else:
            points += 5
            findings.append(f"CTR {ctr:.1f}% — critically low. Title or thumbnail is actively repelling clicks.")
            tips.append("Complete overhaul needed: new thumbnail, rewritten title, tag refresh.")

        c2o = (a.orders / a.clicks) * 100 if a.clicks else 0.0
        if c2o >= 10.0:
            points += 45
        elif c2o >= 5.0:
            points += 32
            findings.append(f"Order conversion {c2o:.1f}% — decent but not compelling.")
            tips.append("Sharpen the opening line and add outcome-focused package highlights.")
        elif c2o >= 2.0:
            points += 18
            findings.append(f"Order conversion {c2o:.1f}% — buyers click but do not buy.")
            tips.append("Add testimonials, a guarantee, and clearer scope to reduce purchase friction.")
        else:
            points += 5
            findings.append(f"Order conversion {c2o:.1f}% — very few clickers become buyers.")
            tips.append("Audit pricing, package clarity, and social proof urgently.")

        if a.average_response_time_hours is not None:
            if a.average_response_time_hours <= 1:
                points = min(points + 10, 100)
            elif a.average_response_time_hours > 3:
                findings.append(f"Response time {a.average_response_time_hours:.0f}h — risks losing high-intent buyers.")
                tips.append("Check inbox 3x daily and use saved replies to stay under 2 hours.")

        return DimensionScore(name="CRO", score=min(100, points),
                              weight=self._WEIGHTS["CRO"], findings=findings, tips=tips)

    # ── Competitive (20%) ──────────────────────────────────────────────────
    def _competitive_dimension(self, snapshot: GigSnapshot, report: OptimizationReport | None) -> DimensionScore:
        findings: list[str] = []
        tips: list[str] = []
        points = 50

        competitors = snapshot.competitors or []
        if not competitors:
            if report and report.competitive_gap_analysis:
                gap = report.competitive_gap_analysis
                if gap.why_competitors_win:
                    findings.append(f"Key rival advantage: {gap.why_competitors_win[0]}")
                if gap.what_to_implement:
                    tips.append(gap.what_to_implement[0])
                points = 55
            else:
                findings.append("No competitor data — run a marketplace scan to benchmark your position.")
                tips.append("Use Competitor Analysis to scan your keyword and see page-one gigs.")
            return DimensionScore(name="Competitive", score=points,
                                  weight=self._WEIGHTS["Competitive"], findings=findings, tips=tips)

        my_price = min((p.price for p in (snapshot.packages or [])), default=None)
        rival_prices = [c.starting_price for c in competitors if c.starting_price is not None]
        if my_price and rival_prices:
            avg_rival = mean(rival_prices)
            ratio = my_price / avg_rival
            if ratio > 1.3:
                points = max(points - 15, 10)
                findings.append(f"Entry price ${my_price:.0f} is {(ratio-1)*100:.0f}% above competitor average ${avg_rival:.0f}.")
                tips.append("Justify the premium with stronger credentials, or add a budget entry package.")
            elif ratio < 0.7:
                points = max(points - 10, 10)
                findings.append(f"Entry price ${my_price:.0f} undercuts market average ${avg_rival:.0f} by over 30%.")
                tips.append("Underpricing signals low quality. Raise entry price and differentiate with a fast-delivery hook.")
            else:
                points = min(points + 20, 100)
                findings.append(f"Entry price ${my_price:.0f} is well-positioned near market average ${avg_rival:.0f}.")

        my_reviews = len(snapshot.reviews or [])
        rival_reviews = [c.reviews_count for c in competitors if c.reviews_count is not None]
        if rival_reviews:
            avg_rival_rev = mean(rival_reviews)
            if my_reviews < avg_rival_rev * 0.3:
                points = max(points - 15, 10)
                findings.append(f"Review count ({my_reviews}) is far below competitor average ({avg_rival_rev:.0f}).")
                tips.append("Send a polite post-delivery review request to all recent buyers.")
            elif my_reviews >= avg_rival_rev:
                points = min(points + 15, 100)
                findings.append(f"Review count ({my_reviews}) meets or exceeds the competitor average — strong position.")

        return DimensionScore(name="Competitive", score=min(100, max(0, points)),
                              weight=self._WEIGHTS["Competitive"], findings=findings, tips=tips)

    # ── Social Proof (20%) ─────────────────────────────────────────────────
    def _social_proof_dimension(self, snapshot: GigSnapshot) -> DimensionScore:
        findings: list[str] = []
        tips: list[str] = []
        points = 0

        reviews = snapshot.reviews or []
        rc = len(reviews)
        if rc >= 100:
            points += 40
        elif rc >= 30:
            points += 30
            findings.append(f"{rc} reviews is solid but top sellers show 100+.")
            tips.append("Every 10 new reviews measurably improves conversion rate.")
        elif rc >= 10:
            points += 20
            tips.append("Add a post-delivery message asking buyers to leave an honest review.")
        elif rc > 0:
            points += 10
            findings.append(f"Only {rc} reviews — the gig looks new and is hard to trust.")
            tips.append("Offer a discounted order to build initial social proof.")
        else:
            findings.append("Zero reviews — most urgent trust problem.")
            tips.append("Prioritise getting your first 5 reviews this week.")

        ratings = [float(r.rating) for r in reviews if getattr(r, "rating", None) is not None]
        if ratings:
            avg = mean(ratings)
            if avg >= 4.9:
                points += 35
                findings.append(f"Outstanding rating {avg:.1f} — powerful trust signal.")
            elif avg >= 4.7:
                points += 25
                tips.append("Identify delivery patterns causing sub-5 star reviews and fix them.")
            elif avg >= 4.5:
                points += 15
                findings.append(f"Rating {avg:.1f} — below top sellers who cluster at 4.9+.")
                tips.append("Read every sub-5 review carefully. One recurring complaint fixed lifts the average fast.")
            else:
                points += 5
                findings.append(f"Rating {avg:.1f} is concerning and will suppress algorithm placement.")
                tips.append("Pause new orders, fix delivery failures, then restart with tighter scope control.")
        else:
            points += 20

        packages = snapshot.packages or []
        if len(packages) >= 3:
            points += 25
        elif len(packages) == 2:
            points += 15
            tips.append("Add a Premium package 2-3x your standard price to increase average order value.")
        elif len(packages) == 1:
            points += 8
            findings.append("Single package caps revenue and limits buyer choice.")
            tips.append("Add Basic and Premium packages — three tiers is the Fiverr conversion sweet spot.")
        else:
            findings.append("No packages defined — single-price gigs underperform in search.")

        return DimensionScore(name="Social Proof", score=min(100, points),
                              weight=self._WEIGHTS["Social Proof"], findings=findings, tips=tips)

    # ── Delivery (10%) ─────────────────────────────────────────────────────
    def _delivery_dimension(self, snapshot: GigSnapshot) -> DimensionScore:
        findings: list[str] = []
        tips: list[str] = []
        points = 50

        packages = snapshot.packages or []
        delivery_days = [p.delivery_days for p in packages if p.delivery_days is not None]
        if delivery_days:
            fastest = min(delivery_days)
            if fastest <= 1:
                points = min(points + 25, 100)
                findings.append(f"Fastest delivery {fastest} day — strong signal for urgent buyers.")
            elif fastest <= 3:
                points = min(points + 15, 100)
            else:
                points = max(points - 10, 0)
                findings.append(f"Fastest delivery {fastest} days — slower than most Page 1 competitors.")
                tips.append("Offer a 1-2 day express option at a premium to capture urgency-driven buyers.")

        revisions = [p.revisions for p in packages if p.revisions is not None]
        if revisions:
            points = min(points + 15, 100)
        else:
            findings.append("Revision count not specified — creates buyer uncertainty.")
            tips.append("Add explicit revision counts to each package.")

        a = snapshot.analytics
        if a.average_response_time_hours is not None:
            if a.average_response_time_hours <= 1:
                points = min(points + 10, 100)
                findings.append(f"Response time {a.average_response_time_hours:.1f}h — excellent.")
            elif a.average_response_time_hours > 4:
                points = max(points - 15, 0)
                findings.append(f"Response time {a.average_response_time_hours:.0f}h — risks losing high-urgency buyers.")
                tips.append("Set 3 inbox check times daily and use saved replies for common questions.")

        return DimensionScore(name="Delivery", score=min(100, max(0, points)),
                              weight=self._WEIGHTS["Delivery"], findings=findings, tips=tips)

    @staticmethod
    def _band(score: int) -> tuple[str, str]:
        if score >= 80:
            return "Healthy", "green"
        if score >= 60:
            return "Fair", "yellow"
        if score >= 40:
            return "At Risk", "orange"
        return "Critical", "red"
