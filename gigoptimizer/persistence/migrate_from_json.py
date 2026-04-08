from __future__ import annotations

import json
from pathlib import Path

from ..config import GigOptimizerConfig
from ..models import ApprovalRecord, ValidationIssue
from ..queue import HITLQueue
from .database import DatabaseManager
from .repository import BlueprintRepository


def migrate(config: GigOptimizerConfig | None = None) -> dict[str, int]:
    resolved = config or GigOptimizerConfig.from_env()
    repository = BlueprintRepository(DatabaseManager(resolved))

    migrated = {
        "gig_state": 0,
        "hitl_items": 0,
        "competitors": 0,
    }

    state_payload = _load_json(resolved.dashboard_state_path)
    snapshot_payload = _load_json(resolved.default_snapshot_path)
    if state_payload:
        repository.save_primary_state(state_payload, snapshot_payload=snapshot_payload)
        migrated["gig_state"] = 1
        comparison = state_payload.get("gig_comparison") or {}
        competitors = comparison.get("top_competitors") or []
        marketplace_gigs = []
        for item in competitors:
            if not isinstance(item, dict):
                continue
            from ..models import MarketplaceGig

            marketplace_gigs.append(MarketplaceGig(**{
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "seller_name": item.get("seller_name", ""),
                "starting_price": item.get("starting_price"),
                "rating": item.get("rating"),
                "reviews_count": item.get("reviews_count"),
                "delivery_days": item.get("delivery_days"),
                "badges": item.get("badges", []),
                "snippet": item.get("snippet", ""),
                "matched_term": item.get("matched_term", ""),
                "conversion_proxy_score": item.get("conversion_proxy_score", 0.0),
                "win_reasons": item.get("win_reasons", []),
            }))
        if marketplace_gigs:
            repository.replace_competitor_snapshots(gigs=marketplace_gigs, source="legacy_json")
            migrated["competitors"] = len(marketplace_gigs)

    if resolved.approval_queue_db_path.exists():
        legacy_queue = HITLQueue(resolved.approval_queue_db_path)
        records = legacy_queue.list_records()
        for record in records:
            repository.upsert_hitl_item(record)
        migrated["hitl_items"] = len(records)

    return migrated


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    result = migrate()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
