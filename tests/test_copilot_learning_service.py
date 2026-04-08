from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.persistence import BlueprintRepository, DatabaseManager
from gigoptimizer.services.cache_service import CacheService
from gigoptimizer.services.copilot_learning_service import CopilotLearningService
from gigoptimizer.services.knowledge_service import KnowledgeService


class CopilotLearningServiceTests(unittest.TestCase):
    def test_sync_sources_ingests_feed_items_into_global_knowledge(self) -> None:
        rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>HTTP caching guide</title>
      <link>https://example.com/http-caching</link>
      <guid>cache-1</guid>
      <description><![CDATA[Learn browser caching and edge caching for production apps.]]></description>
      <pubDate>Wed, 09 Apr 2026 07:00:00 GMT</pubDate>
      <category>performance</category>
    </item>
    <item>
      <title>Firewall checklist</title>
      <link>https://example.com/firewall</link>
      <guid>firewall-1</guid>
      <description><![CDATA[Allow SSH, HTTP, and HTTPS only.]]></description>
      <pubDate>Wed, 09 Apr 2026 06:30:00 GMT</pubDate>
      <category>security</category>
    </item>
  </channel>
</rss>
"""

        class FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

            def raise_for_status(self) -> None:
                return None

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "DATABASE_URL": f"sqlite:///{(temp_root / 'data' / 'test.db').as_posix()}",
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                database = DatabaseManager(config)
                repository = BlueprintRepository(database)
                cache_service = CacheService(config)
                knowledge_service = KnowledgeService(config, repository, cache_service)
                service = CopilotLearningService(config, repository, knowledge_service, cache_service)
                service.DEFAULT_SOURCES = [
                    {
                        "slug": "example-feed",
                        "title": "Example Feed",
                        "feed_url": "https://example.com/feed.xml",
                        "focus": ["performance", "security"],
                    }
                ]

                with patch("gigoptimizer.services.copilot_learning_service.httpx.get", return_value=FakeResponse(rss)):
                    result = service.sync_sources(force=True)

                documents = knowledge_service.list_documents(gig_id=service.GLOBAL_GIG_ID, limit=20)
                retrieved = service.retrieve_context(query="firewall", limit=3)

        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["new_documents"], 2)
        self.assertGreaterEqual(len(documents), 2)
        self.assertTrue(any("firewall" in str(item.get("snippet", "")).lower() for item in retrieved))


if __name__ == "__main__":
    unittest.main()
