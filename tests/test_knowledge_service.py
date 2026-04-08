from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.persistence import BlueprintRepository, DatabaseManager
from gigoptimizer.services import CacheService, KnowledgeService


class KnowledgeServiceTests(unittest.TestCase):
    def test_ingest_and_retrieve_text_dataset(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                repository = BlueprintRepository(DatabaseManager(config))
                service = KnowledgeService(config, repository, CacheService(config))
                document = service.ingest_document(
                    gig_id="https://www.fiverr.com/example/my-gig",
                    filename="notes.md",
                    content_type="text/markdown",
                    raw_bytes=(
                        b"Use PageSpeed Insights and GTmetrix in the title.\n\n"
                        b"Lead with before-and-after proof for WordPress speed buyers."
                    ),
                )
                results = service.retrieve_context(
                    gig_id="https://www.fiverr.com/example/my-gig",
                    query="What should I say about GTmetrix in my title?",
                    limit=3,
                )

        self.assertEqual(document["filename"], "notes.md")
        self.assertTrue(results)
        self.assertIn("gtmetrix", results[0]["content"].lower())

    def test_reuploading_same_dataset_reuses_existing_document(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                repository = BlueprintRepository(DatabaseManager(config))
                service = KnowledgeService(config, repository, CacheService(config))
                payload = b'{"title":"WordPress speed","proof":"Went from 45 to 96"}'
                first = service.ingest_document(
                    gig_id="primary",
                    filename="dataset.json",
                    content_type="application/json",
                    raw_bytes=payload,
                )
                second = service.ingest_document(
                    gig_id="primary",
                    filename="dataset.json",
                    content_type="application/json",
                    raw_bytes=payload,
                )

        self.assertEqual(first["id"], second["id"])


if __name__ == "__main__":
    unittest.main()
