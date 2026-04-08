from __future__ import annotations

import base64
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from gigoptimizer.models import ConnectorStatus, MarketplaceGig


class DashboardApiTests(unittest.TestCase):
    def test_dashboard_routes_and_actions_work(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    page = client.get("/")
                    self.assertEqual(page.status_code, 200)
                    self.assertIn("GigOptimizer Pro", page.text)

                    state = client.get("/api/state")
                    self.assertEqual(state.status_code, 200)
                    payload = state.json()
                    self.assertIn("latest_report", payload)

                    run = client.post("/api/run", json={"use_live_connectors": False})
                    self.assertEqual(run.status_code, 200)
                    run_payload = run.json()
                    self.assertTrue(run_payload["metrics_history"])

                    queue = client.get("/api/queue")
                    self.assertEqual(queue.status_code, 200)
                    records = queue.json()["records"]
                    self.assertTrue(records)
                    pending = next(
                        item
                        for item in records
                        if item["status"] in {"pending", "auto_approved", "approved"}
                    )

                    approve = client.post(f"/api/queue/{pending['id']}/approve", json={})
                    self.assertEqual(approve.status_code, 200)
                    approved_records = approve.json()["queue"]
                    self.assertTrue(any(item["status"] == "approved" for item in approved_records))

                    report = client.post("/api/reports/run", json={"use_live_connectors": False})
                    self.assertEqual(report.status_code, 200)
                    report_payload = report.json()
                    self.assertIn("report", report_payload)
                    self.assertTrue(Path(report_payload["report"]["html_path"]).exists())

                    with client.websocket_connect("/ws/dashboard") as websocket:
                        message = websocket.receive_json()
                        self.assertEqual(message["type"], "state")
                        self.assertIn("payload", message)

    def test_marketplace_scraper_route_streams_state(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    service = client.app.state.dashboard_service

                    def fake_fetch(search_terms, observer=None):
                        if observer is not None:
                            observer({"stage": "term_started", "term": search_terms[0], "url": "https://example.com/search", "message": "Starting test scrape."})
                            observer({"stage": "gig_found", "term": search_terms[0], "gig_title": "I will fix wordpress speed", "seller_name": "SellerOne", "url": "https://example.com/gig/1", "starting_price": 45, "rating": 4.9, "message": "Found a gig."})
                            observer({"stage": "run_completed", "result_count": 1, "message": "Completed test scrape."})
                        return (
                            [
                                MarketplaceGig(
                                    title="I will fix wordpress speed",
                                    url="https://example.com/gig/1",
                                    seller_name="SellerOne",
                                    starting_price=45.0,
                                    rating=4.9,
                                    reviews_count=128,
                                    matched_term=search_terms[0],
                                )
                            ],
                            ConnectorStatus("fiverr_marketplace", "ok", "Collected 1 test gig."),
                        )

                    with patch.object(service.orchestrator.marketplace, "fetch_competitor_gigs", side_effect=fake_fetch):
                        response = client.post("/api/marketplace/run", json={"search_terms": ["wordpress speed"]})

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["scraper_run"]["status"], "ok")
                    self.assertEqual(payload["scraper_run"]["total_results"], 1)
                    self.assertTrue(payload["scraper_run"]["recent_events"])
                    self.assertTrue(payload["scraper_run"]["recent_gigs"])
                    self.assertIn("competitive_gap_analysis", payload["latest_report"])

    def test_marketplace_verification_route_starts_flow(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    service = client.app.state.dashboard_service

                    class ImmediateThread:
                        def __init__(self, target=None, daemon=None, **kwargs):
                            self.target = target

                        def start(self):
                            if self.target is not None:
                                self.target()

                    with patch.object(service, "run_marketplace_verification", return_value=service.get_state()):
                        with patch("gigoptimizer.api.main.threading.Thread", ImmediateThread):
                            response = client.post(
                                "/api/marketplace/verification/start",
                                json={"search_terms": ["wordpress speed"]},
                            )

                    self.assertEqual(response.status_code, 200)
                    self.assertIn("scraper_run", response.json())

    def test_compare_my_gig_route_returns_market_comparison(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    service = client.app.state.dashboard_service
                    fake_state = service.get_state()
                    fake_state["gig_comparison"] = {
                        "status": "ok",
                        "message": "Compared your gig against 3 public Fiverr gigs in the same niche.",
                        "gig_url": "https://www.fiverr.com/example/my-gig",
                        "my_gig": {
                            "url": "https://www.fiverr.com/example/my-gig",
                            "title": "I will fix wordpress speed",
                            "seller_name": "Me",
                            "description_excerpt": "Speed optimization for WordPress.",
                            "starting_price": 45.0,
                            "rating": 4.9,
                            "reviews_count": 44,
                            "tags": ["wordpress speed", "core web vitals"],
                        },
                        "detected_search_terms": ["wordpress speed", "core web vitals"],
                        "top_search_titles": ["I will fix wordpress speed and core web vitals"],
                        "title_patterns": ["wordpress speed", "core web vitals"],
                        "market_anchor_price": 55.0,
                        "competitor_count": 3,
                        "what_to_implement": ["Add PageSpeed Insights to the title."],
                        "why_competitors_win": ["Their titles hit stronger buyer-intent phrases."],
                        "my_advantages": ["Your offer already converts once buyers click."],
                        "top_competitors": [
                            {
                                "title": "I will fix wordpress speed and core web vitals",
                                "url": "https://www.fiverr.com/example/competitor",
                                "seller_name": "SellerOne",
                                "starting_price": 55.0,
                                "rating": 5.0,
                                "reviews_count": 120,
                                "delivery_days": 2,
                                "badges": ["Level 2"],
                                "snippet": "Fast WordPress optimization.",
                                "matched_term": "wordpress speed",
                                "conversion_proxy_score": 88.0,
                                "win_reasons": ["Keyword match", "Review trust"],
                            }
                        ],
                    }

                    with patch.object(service, "compare_my_gig_to_market", return_value=fake_state):
                        response = client.post(
                            "/api/marketplace/compare-gig",
                            json={"gig_url": "https://www.fiverr.com/example/my-gig"},
                        )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["gig_comparison"]["status"], "ok")
                    self.assertEqual(payload["gig_comparison"]["competitor_count"], 3)
                    self.assertTrue(payload["gig_comparison"]["what_to_implement"])
                    self.assertTrue(payload["recent_reports"])
                    self.assertEqual(payload["recent_reports"][0]["report_type"], "market_watch")

    def test_compare_manual_market_route_returns_market_comparison(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/marketplace/compare-manual",
                        json={
                            "gig_url": "",
                            "competitor_input": (
                                "I will fix wordpress speed | 45 | 4.9 | 120 | 2 days | https://www.fiverr.com/example/1\n"
                                "I will improve core web vitals | 55 | 5.0 | 80 | 1 day | https://www.fiverr.com/example/2"
                            ),
                            "search_terms": ["wordpress speed"],
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["gig_comparison"]["comparison_source"], "manual")
                    self.assertEqual(payload["gig_comparison"]["competitor_count"], 2)
                    self.assertTrue(payload["gig_comparison"]["top_competitors"])
                    blueprint = payload["gig_comparison"]["implementation_blueprint"]
                    self.assertTrue(blueprint["recommended_title"])
                    self.assertTrue(blueprint["recommended_tags"])
                    self.assertTrue(blueprint["description_full"])
                    self.assertTrue(blueprint["title_options"])
                    self.assertTrue(blueprint["description_options"])
                    self.assertTrue(payload["recent_reports"])
                    self.assertEqual(payload["recent_reports"][0]["report_type"], "market_watch")
                    self.assertTrue(payload["comparison_history"])
                    self.assertTrue(payload["setup_health"]["checks"])

    def test_compare_manual_market_route_accepts_browser_capture_json(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/marketplace/compare-manual",
                        json={
                            "gig_url": "",
                            "competitor_input": """
                            {
                              "source": "browser_capture",
                              "searchTerm": "wordpress speed",
                              "gigs": [
                                {
                                  "title": "I will fix wordpress speed and core web vitals",
                                  "seller_name": "SellerOne",
                                  "starting_price": 45,
                                  "rating": 4.9,
                                  "reviews_count": 120,
                                  "delivery_days": 2,
                                  "url": "https://www.fiverr.com/example/1"
                                },
                                {
                                  "title": "I will improve pagespeed insights score",
                                  "seller_name": "SellerTwo",
                                  "starting_price": 55,
                                  "rating": 5.0,
                                  "reviews_count": 84,
                                  "delivery_days": 1,
                                  "url": "https://www.fiverr.com/example/2"
                                }
                              ]
                            }
                            """,
                            "search_terms": ["wordpress speed"],
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["gig_comparison"]["comparison_source"], "manual")
                    self.assertEqual(payload["gig_comparison"]["competitor_count"], 2)
                    self.assertIn("wordpress speed", payload["gig_comparison"]["detected_search_terms"])
                    self.assertTrue(payload["gig_comparison"]["implementation_blueprint"]["recommended_title"])
                    self.assertTrue(payload["gig_comparison"]["implementation_blueprint"]["title_options"])
                    self.assertTrue(payload["gig_comparison"]["implementation_blueprint"]["description_options"])

    def test_authentication_and_settings_routes_work(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-session-secret",
                    "HOSTINGER_ENABLED": "false",
                    "HOSTINGER_API_TOKEN": "",
                    "HOSTINGER_VIRTUAL_MACHINE_ID": "",
                    "HOSTINGER_PROJECT_NAME": "",
                    "HOSTINGER_DOMAIN": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    login_page = client.get("/login")
                    self.assertEqual(login_page.status_code, 200)
                    self.assertIn("Secure dashboard login", login_page.text)

                    unauth_state = client.get("/api/state")
                    self.assertEqual(unauth_state.status_code, 401)

                    bad_login = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
                    self.assertEqual(bad_login.status_code, 401)

                    good_login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    self.assertEqual(good_login.status_code, 200)
                    self.assertTrue(good_login.json()["auth"]["authenticated"])
                    csrf_token = good_login.json()["auth"]["csrf_token"]

                    state = client.get("/api/state")
                    self.assertEqual(state.status_code, 200)
                    self.assertIn("notifications", state.json())

                    with client.websocket_connect("/ws/dashboard") as websocket:
                        message = websocket.receive_json()
                        self.assertEqual(message["type"], "state")
                        self.assertEqual(message["payload"]["auth"]["csrf_token"], csrf_token)

                    missing_csrf = client.post("/api/settings", json={})
                    self.assertEqual(missing_csrf.status_code, 403)

                    saved = client.post(
                        "/api/settings",
                        json={
                            "events": {
                                "pipeline_run": True,
                                "queue_pending": False,
                                "approval_decision": True,
                                "report_generated": True,
                                "error": True,
                            },
                            "slack": {
                                "enabled": True,
                                "webhook_url": "https://hooks.slack.com/services/test/value",
                            },
                            "whatsapp": {
                                "enabled": True,
                                "access_token": "token-value",
                                "phone_number_id": "1234567890",
                                "recipient_number": "+15551234567",
                                "api_version": "v23.0",
                            },
                            "marketplace": {
                                "enabled": True,
                                "reader_enabled": True,
                                "reader_base_url": "https://r.jina.ai/http://",
                                "my_gig_url": "https://www.fiverr.com/example/my-gig",
                                "auto_compare_enabled": True,
                                "auto_compare_interval_minutes": 5,
                                "serpapi_api_key": "serpapi-secret",
                                "serpapi_engine": "google",
                                "serpapi_num_results": 8,
                            },
                        },
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(saved.status_code, 200)
                    settings_payload = saved.json()
                    self.assertTrue(settings_payload["slack"]["configured"])
                    self.assertEqual(settings_payload["whatsapp"]["phone_number_id"], "1234567890")
                    self.assertFalse(settings_payload["hostinger"]["configured"])
                    self.assertTrue(settings_payload["marketplace"]["auto_compare_enabled"])
                    self.assertTrue(settings_payload["marketplace"]["reader_enabled"])
                    self.assertEqual(settings_payload["marketplace"]["reader_base_url"], "https://r.jina.ai/http://")
                    self.assertTrue(settings_payload["marketplace"]["serpapi_configured"])

                    queued = client.post(
                        "/api/marketplace/recommendations/apply",
                        json={
                            "action_type": "title_update",
                            "proposed_value": "I will optimize WordPress speed and improve PageSpeed Insights",
                        },
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(queued.status_code, 200)
                    self.assertTrue(any(item["action_type"] == "title_update" for item in queued.json()["queue"]))

                    mock_response = MagicMock()
                    mock_response.__enter__.return_value.status = 200
                    mock_response.__exit__.return_value = False
                    with patch("gigoptimizer.services.slack_service.urlopen", return_value=mock_response):
                        slack_test = client.post(
                            "/api/settings/notifications/test",
                            json={"channel": "slack"},
                            headers={"X-CSRF-Token": csrf_token},
                        )
                    self.assertEqual(slack_test.status_code, 200)
                    self.assertTrue(slack_test.json()["result"]["ok"])

                    logout = client.post("/api/auth/logout", json={}, headers={"X-CSRF-Token": csrf_token})
                    self.assertEqual(logout.status_code, 200)

                    post_logout_state = client.get("/api/state")
                    self.assertEqual(post_logout_state.status_code, 401)

    def test_hostinger_status_and_assistant_routes_work(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    with patch.object(
                        client.app.state.hostinger_service,
                        "get_public_status",
                        return_value={
                            "status": "ok",
                            "enabled": True,
                            "configured": True,
                            "domain": "animha.co.in",
                            "project_name": "deploy",
                            "virtual_machines": [],
                            "metrics": {"cpu": 28},
                            "project_logs": [],
                        },
                    ):
                        hostinger = client.get("/api/hostinger/status")
                    self.assertEqual(hostinger.status_code, 200)
                    self.assertEqual(hostinger.json()["hostinger"]["status"], "ok")

                    assistant = client.post(
                        "/api/assistant/chat",
                        json={"message": "What title should I use now?"},
                    )
                    self.assertEqual(assistant.status_code, 200)
                    payload = assistant.json()["assistant"]
                    self.assertTrue(payload["reply"])
                    self.assertIn("title", payload["reply"].lower())

    def test_hostinger_status_and_assistant_chat_routes_work(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-session-secret",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    good_login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    csrf_token = good_login.json()["auth"]["csrf_token"]

                    with patch.object(client.app.state.hostinger_service, "get_public_status", return_value={"status": "ok", "configured": True, "project_name": "deploy"}):
                        hostinger = client.get("/api/hostinger/status")

                    self.assertEqual(hostinger.status_code, 200)
                    self.assertEqual(hostinger.json()["hostinger"]["status"], "ok")

                    with patch.object(client.app.state.ai_overview_service, "chat", return_value={"status": "ok", "reply": "Use the recommended title.", "suggestions": ["Queue the title update."]}):
                        assistant = client.post(
                            "/api/assistant/chat",
                            json={"message": "What title should I use?"},
                            headers={"X-CSRF-Token": csrf_token},
                        )

                    self.assertEqual(assistant.status_code, 200)
                    self.assertEqual(assistant.json()["assistant"]["reply"], "Use the recommended title.")
                    self.assertTrue(assistant.json()["assistant_history"])
                    self.assertEqual(assistant.json()["assistant_history"][0]["role"], "user")
                    self.assertEqual(assistant.json()["assistant_history"][-1]["role"], "assistant")

    def test_dataset_upload_and_delete_routes_work(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-session-secret",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    csrf_token = login.json()["auth"]["csrf_token"]
                    payload = base64.b64encode(
                        b"Use PageSpeed Insights near the top of the title and mention GTmetrix proof."
                    ).decode("ascii")

                    uploaded = client.post(
                        "/api/v2/datasets/upload",
                        json={
                            "filename": "market-notes.txt",
                            "content_type": "text/plain",
                            "content_base64": payload,
                        },
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(uploaded.status_code, 200)
                    datasets = uploaded.json()["datasets"]
                    self.assertTrue(datasets)
                    document_id = datasets[0]["id"]

                    assistant = client.post(
                        "/api/assistant/chat",
                        json={"message": "What does the uploaded dataset say about PageSpeed Insights?"},
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(assistant.status_code, 200)
                    self.assertIn("uploaded knowledge", assistant.json()["assistant"]["reply"].lower())

                    deleted = client.delete(
                        f"/api/v2/datasets/{document_id}",
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(deleted.status_code, 200)
                    self.assertFalse(deleted.json()["datasets"])

    def test_marketplace_compare_job_persists_active_gig_and_terms(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-session-secret",
                    "JOB_QUEUE_EAGER": "true",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    csrf_token = login.json()["auth"]["csrf_token"]

                    queued = client.post(
                        "/api/v2/jobs",
                        json={
                            "job_type": "marketplace_compare",
                            "gig_url": "https://www.fiverr.com/example/custom-anime-logo",
                            "search_terms": ["anime logo", "mascot logo"],
                        },
                        headers={"X-CSRF-Token": csrf_token},
                    )

                    self.assertEqual(queued.status_code, 200)
                    marketplace = queued.json()["state"]["notifications"]["marketplace"]
                    self.assertEqual(marketplace["my_gig_url"], "https://www.fiverr.com/example/custom-anime-logo")
                    self.assertEqual(marketplace["search_terms"], ["anime logo", "mascot logo"])

    def test_dataset_upload_anchors_to_selected_gig_and_generic_chat_uses_it(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-session-secret",
                    "AI_PROVIDER": "n8n",
                    "AI_API_KEY": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    csrf_token = login.json()["auth"]["csrf_token"]
                    payload = base64.b64encode(
                        b"Use anime logo and mascot logo near the top of the title, then mention color variants."
                    ).decode("ascii")

                    uploaded = client.post(
                        "/api/v2/datasets/upload",
                        json={
                            "filename": "anime-notes.txt",
                            "content_type": "text/plain",
                            "content_base64": payload,
                            "gig_url": "https://www.fiverr.com/example/custom-anime-logo",
                        },
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(uploaded.status_code, 200)
                    self.assertTrue(uploaded.json()["datasets"])
                    self.assertEqual(
                        uploaded.json()["state"]["notifications"]["marketplace"]["my_gig_url"],
                        "https://www.fiverr.com/example/custom-anime-logo",
                    )

                    assistant = client.post(
                        "/api/assistant/chat",
                        json={"message": "How should I rewrite my title right now?"},
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(assistant.status_code, 200)
                    reply = assistant.json()["assistant"]["reply"].lower()
                    self.assertIn("uploaded", reply)
                    self.assertIn("anime-notes.txt", assistant.json()["assistant"]["reply"])

    def test_health_endpoint_redacts_database_url_and_summarizes_last_run(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    client.app.state.config.database_url = "postgresql+psycopg://gigoptimizer:super-secret@postgres:5432/gigoptimizer"
                    fake_run = {
                        "run_id": "run-123",
                        "run_type": "marketplace_compare",
                        "status": "completed",
                        "progress": 1.0,
                        "result_payload": {
                            "optimization_score": 94,
                            "recommended_title": "I will optimize WordPress speed",
                            "state": {
                                "gig_comparison": {
                                    "competitor_count": 12,
                                    "implementation_blueprint": {
                                        "recommended_title": "I will optimize WordPress speed"
                                    },
                                }
                            },
                        },
                    }
                    with patch.object(client.app.state.repository, "last_successful_run", return_value=fake_run):
                        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["components"]["database"]["url"],
            "postgresql+psycopg://<credentials>@postgres:5432/gigoptimizer",
        )
        last_run = payload["components"]["last_successful_run"]
        self.assertEqual(last_run["run_id"], "run-123")
        self.assertEqual(last_run["optimization_score"], 94)
        self.assertEqual(last_run["recommended_title"], "I will optimize WordPress speed")
        self.assertEqual(last_run["competitor_count"], 12)
        self.assertNotIn("result_payload", last_run)


if __name__ == "__main__":
    unittest.main()
