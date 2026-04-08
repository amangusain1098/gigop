from __future__ import annotations

import csv
import io
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from ..config import GigOptimizerConfig
from ..models import ConnectorStatus, KeywordSignal


class SemrushConnector:
    name = "semrush"
    api_url = "https://api.semrush.com/"

    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config

    def fetch_keyword_signals(self, keywords: list[str]) -> tuple[list[KeywordSignal], ConnectorStatus]:
        if not self.config.semrush_api_key:
            return [], ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="Set SEMRUSH_API_KEY in .env to enable search-volume enrichment.",
            )

        signals: list[KeywordSignal] = []
        failures: list[str] = []
        for keyword in self._dedupe(keywords)[:10]:
            try:
                signal = self._lookup_keyword(keyword)
                if signal is not None:
                    signals.append(signal)
            except Exception as exc:
                failures.append(f"{keyword}: {exc}")

        if signals:
            status = ConnectorStatus(
                connector=self.name,
                status="ok" if not failures else "partial",
                detail=f"Collected {len(signals)} keyword signals from Semrush.",
            )
        else:
            detail = failures[0] if failures else "Semrush returned no keyword data."
            status = ConnectorStatus(
                connector=self.name,
                status="error",
                detail=detail,
            )

        return signals, status

    def _lookup_keyword(self, keyword: str) -> KeywordSignal | None:
        params = urlencode(
            {
                "type": "phrase_this",
                "key": self.config.semrush_api_key,
                "phrase": keyword,
                "database": self.config.semrush_database,
                "export_columns": "Ph,Nq,Cp,Co,Kd",
            }
        )
        url = f"{self.api_url}?{params}"
        try:
            with urlopen(url, timeout=self.config.semrush_timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc

        if body.strip().startswith("ERROR"):
            raise RuntimeError(body.strip())

        reader = csv.DictReader(io.StringIO(body), delimiter=";")
        row = next(reader, None)
        if row is None:
            return None

        return KeywordSignal(
            keyword=str(row.get("Ph", keyword)).strip(),
            source=self.name,
            search_volume=self._to_int(row.get("Nq")),
            keyword_difficulty=self._to_float(row.get("Kd")),
            cpc=self._to_float(row.get("Cp")),
            competition=self._to_float(row.get("Co")),
        )

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            key = value.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(value.strip())
        return ordered

    def _to_int(self, value: str | None) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    def _to_float(self, value: str | None) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except ValueError:
            return None
