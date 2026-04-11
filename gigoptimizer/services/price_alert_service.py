"""Competitor Price Alert Service.

Monitors page-one competitor prices and review counts against a stored
baseline and fires alerts when meaningful changes are detected:

  price_drop    competitor entry price dropped > 15%
  price_spike   competitor entry price raised  > 25%
  review_surge  competitor gained >= 50 new reviews

State is stored at data/price_alerts/<gig_id>/baseline.json.
Alerts are returned as PriceAlert objects; the API layer pushes them
to the dashboard via the existing WebSocket bus.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..models import MarketplaceGig

PRICE_DROP_PCT  = 0.15
PRICE_SPIKE_PCT = 0.25
REVIEW_SURGE    = 50


@dataclass(slots=True)
class PriceAlert:
    gig_id: str
    seller_name: str
    alert_type: str
    message: str
    old_value: float
    new_value: float
    change_pct: float
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_ws_event(self) -> dict[str, Any]:
        return {
            "type": "price_alert",
            "gig_id": self.gig_id,
            "seller": self.seller_name,
            "alert_type": self.alert_type,
            "message": self.message,
            "change_pct": round(self.change_pct * 100, 1),
            "ts": self.detected_at,
        }


class PriceAlertService:
    def __init__(self, config: Any = None, data_dir: Path | None = None) -> None:
        self._data_dir = (data_dir or Path("data/price_alerts")).resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def check_and_alert(self, gig_id: str, current: list[MarketplaceGig]) -> list[PriceAlert]:
        baseline = self._load(gig_id)
        alerts: list[PriceAlert] = []

        for gig in current:
            key = (gig.seller_name or "unknown").lower()
            old_price   = baseline["prices"].get(key)
            old_reviews = baseline["reviews"].get(key)
            new_price   = gig.starting_price
            new_reviews = gig.reviews_count

            if old_price and new_price and old_price > 0:
                chg = (new_price - old_price) / old_price
                if chg <= -PRICE_DROP_PCT:
                    alerts.append(PriceAlert(
                        gig_id=gig_id, seller_name=key, alert_type="price_drop",
                        message=(f"{key} dropped entry price from ${old_price:.0f} to ${new_price:.0f} "
                                 f"({abs(chg)*100:.0f}% decrease). Review your own positioning."),
                        old_value=old_price, new_value=new_price, change_pct=chg,
                    ))
                elif chg >= PRICE_SPIKE_PCT:
                    alerts.append(PriceAlert(
                        gig_id=gig_id, seller_name=key, alert_type="price_spike",
                        message=(f"{key} raised entry price from ${old_price:.0f} to ${new_price:.0f} "
                                 f"({chg*100:.0f}% increase). Demand may be rising — consider raising yours."),
                        old_value=old_price, new_value=new_price, change_pct=chg,
                    ))

            if old_reviews is not None and new_reviews is not None:
                surge = new_reviews - old_reviews
                if surge >= REVIEW_SURGE:
                    alerts.append(PriceAlert(
                        gig_id=gig_id, seller_name=key, alert_type="review_surge",
                        message=(f"{key} gained {surge} reviews since last check "
                                 f"({old_reviews} -> {new_reviews}). Accelerate your review velocity."),
                        old_value=float(old_reviews), new_value=float(new_reviews),
                        change_pct=surge / max(old_reviews, 1),
                    ))

        self._save(gig_id, current)
        return alerts

    def get_baseline(self, gig_id: str) -> dict[str, Any]:
        return self._load(gig_id)

    def clear_baseline(self, gig_id: str) -> None:
        p = self._path(gig_id)
        if p.exists():
            p.unlink()

    def _path(self, gig_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in gig_id)
        d = self._data_dir / safe
        d.mkdir(parents=True, exist_ok=True)
        return d / "baseline.json"

    def _load(self, gig_id: str) -> dict[str, Any]:
        p = self._path(gig_id)
        if not p.exists():
            return {"prices": {}, "reviews": {}, "updated_at": None}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"prices": {}, "reviews": {}, "updated_at": None}

    def _save(self, gig_id: str, competitors: list[MarketplaceGig]) -> None:
        prices: dict[str, float] = {}
        reviews: dict[str, int]  = {}
        for g in competitors:
            key = (g.seller_name or "unknown").lower()
            if g.starting_price  is not None: prices[key]  = g.starting_price
            if g.reviews_count   is not None: reviews[key] = g.reviews_count
        self._path(gig_id).write_text(
            json.dumps({"prices": prices, "reviews": reviews, "updated_at": time.time()}, indent=2),
            encoding="utf-8",
        )
