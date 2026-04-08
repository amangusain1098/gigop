from __future__ import annotations

import unittest

from gigoptimizer.api.security import is_allowed_origin
from gigoptimizer.config import GigOptimizerConfig


class SecurityOriginTests(unittest.TestCase):
    def test_forwarded_host_allows_public_websocket_origin(self) -> None:
        config = GigOptimizerConfig(app_base_url="", app_trusted_hosts="")
        allowed = is_allowed_origin(
            "https://theatre-spell-territories-yang.trycloudflare.com",
            config,
            "theatre-spell-territories-yang.trycloudflare.com, 127.0.0.1:8001",
        )
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
