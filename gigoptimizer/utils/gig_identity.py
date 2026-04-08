from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse


def build_gig_key(value: str | None, *, fallback: str = "primary") -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    if raw.startswith(("fiverr:", "url:", "text:")):
        return _bounded_key(raw)

    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.lower()
        path_parts = [part for part in parsed.path.split("/") if part]
        canonical_path = "/".join(path_parts[:2]) if path_parts else parsed.path.strip("/")
        canonical = f"{host}/{canonical_path}".strip("/")
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]

        if "fiverr.com" in host:
            seller = _slugify(path_parts[0] if len(path_parts) >= 1 else "seller", limit=48)
            gig_slug = _slugify(path_parts[1] if len(path_parts) >= 2 else "gig", limit=96)
            return _bounded_key(f"fiverr:{seller}:{gig_slug}:{digest}")

        path_slug = _slugify(canonical_path or parsed.netloc or "gig", limit=140)
        host_slug = _slugify(host, limit=48)
        return _bounded_key(f"url:{host_slug}:{path_slug}:{digest}")

    return _bounded_key(f"text:{_slugify(raw, limit=180)}")


def _slugify(value: str, *, limit: int) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (cleaned or "item")[:limit]


def _bounded_key(value: str) -> str:
    return value[:255]
