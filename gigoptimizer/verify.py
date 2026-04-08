from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def verify(
    base_url: str,
    username: str | None,
    password: str | None,
    output_path: Path,
    *,
    client: httpx.Client | None = None,
) -> int:
    base_url = normalize_base_url(base_url)
    own_client = client is None
    client = client or httpx.Client(base_url=base_url, follow_redirects=True, timeout=30.0)
    checks: list[dict[str, Any]] = []
    csrf_token = ""

    def run_check(name: str, func):
        started = time.perf_counter()
        try:
            detail = func()
            status = "passed"
        except Exception as exc:  # pragma: no cover - exercised by manual verification
            detail = str(exc)
            status = "failed"
        checks.append(
            {
                "name": name,
                "status": status,
                "detail": detail,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )

    def get_json(path: str) -> tuple[int, dict]:
        response = client.get(path)
        payload = response.json() if response.text else {}
        return response.status_code, payload

    def post_json(path: str, payload: dict) -> tuple[int, dict]:
        headers = {"X-CSRF-Token": csrf_token} if csrf_token else {}
        response = client.post(path, json=payload, headers=headers)
        body = response.json() if response.text else {}
        return response.status_code, body

    def get_text(path: str) -> tuple[int, str]:
        response = client.get(path)
        return response.status_code, response.text

    def check_health():
        status, payload = get_json("/api/health")
        if status != 200 or payload.get("status") != "ok":
            raise RuntimeError(f"Unexpected health response: {status} {payload}")
        return payload

    def check_root():
        status, body = get_text("/")
        if status != 200:
            raise RuntimeError(f"Unexpected root status: {status}")
        if "GigOptimizer Pro" not in body and "Secure dashboard login" not in body:
            raise RuntimeError("Expected dashboard or login page content was not found.")
        return {"status": status}

    def check_static_assets():
        assets = ["/static/dashboard.css", "/static/dashboard.js", "/static/manifest.webmanifest"]
        results = {}
        for asset in assets:
            status, body = get_text(asset)
            if status != 200 or not body:
                raise RuntimeError(f"Asset failed: {asset} ({status})")
            results[asset] = status
        return results

    def maybe_login():
        nonlocal csrf_token
        status, session = get_json("/api/auth/session")
        if status != 200:
            raise RuntimeError(f"Unexpected auth session status: {status}")
        if session.get("enabled") and not session.get("authenticated"):
            if not username or not password:
                raise RuntimeError("Authentication is enabled. Provide --username and --password to verify protected routes.")
            login_status, login_payload = post_json(
                "/api/auth/login",
                {"username": username, "password": password},
            )
            if login_status != 200 or not login_payload.get("auth", {}).get("authenticated"):
                raise RuntimeError(f"Login failed: {login_status} {login_payload}")
            csrf_token = str(login_payload.get("auth", {}).get("csrf_token", "")).strip()
            return {"authenticated": True, "username": login_payload["auth"].get("username", "")}
        csrf_token = str(session.get("csrf_token", "")).strip()
        return session

    def check_state():
        status, payload = get_json("/api/state")
        if status != 200:
            raise RuntimeError(f"Unexpected state status: {status}")
        if "latest_report" not in payload or "notifications" not in payload:
            raise RuntimeError("State payload is missing required keys.")
        return {
            "optimization_score": (payload.get("latest_report") or {}).get("optimization_score"),
            "queue_items": len(payload.get("queue", [])),
        }

    def check_run():
        status, payload = post_json("/api/run", {"use_live_connectors": False})
        if status != 200:
            raise RuntimeError(f"Unexpected run status: {status}")
        report = payload.get("latest_report") or {}
        if report.get("optimization_score") is None:
            raise RuntimeError("Pipeline run did not return an optimization score.")
        return {"optimization_score": report.get("optimization_score")}

    def check_reports():
        status, payload = post_json("/api/reports/run", {"use_live_connectors": False})
        if status != 200:
            raise RuntimeError(f"Unexpected report status: {status}")
        report = payload.get("report") or {}
        html_path = report.get("html_path")
        if not html_path:
            raise RuntimeError("Report generation did not return an HTML path.")
        file_name = Path(html_path).name
        file_status, _ = get_text(f"/reports/{quote(file_name)}")
        if file_status != 200:
            raise RuntimeError(f"Generated report could not be opened over HTTP: {file_status}")
        return {"report_id": report.get("report_id"), "html_file": file_name}

    def check_settings():
        status, payload = get_json("/api/settings")
        if status != 200:
            raise RuntimeError(f"Unexpected settings status: {status}")
        expected_keys = {"email", "slack", "whatsapp", "ai", "marketplace", "events"}
        if not expected_keys.issubset(payload.keys()):
            raise RuntimeError(f"Settings payload is missing keys: {sorted(expected_keys - set(payload.keys()))}")
        return {"keys": sorted(payload.keys())}

    try:
        run_check("health_endpoint", check_health)
        run_check("root_page", check_root)
        run_check("static_assets", check_static_assets)
        run_check("authentication", maybe_login)
        run_check("state_endpoint", check_state)
        run_check("pipeline_run", check_run)
        run_check("settings_endpoint", check_settings)
        run_check("report_generation", check_reports)
    finally:
        if own_client:
            client.close()

    passed = sum(1 for item in checks if item["status"] == "passed")
    failed = len(checks) - passed
    report = {
        "base_url": base_url,
        "generated_at_epoch": int(time.time()),
        "summary": {
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "checks": checks,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Verification target: {base_url}")
    for item in checks:
        prefix = "[PASS]" if item["status"] == "passed" else "[FAIL]"
        print(f"{prefix} {item['name']}: {item['detail']}")
    print(f"Verification report saved to: {output_path}")

    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a running GigOptimizer Pro instance.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Running dashboard base URL.")
    parser.add_argument("--username", default="", help="Dashboard username when auth is enabled.")
    parser.add_argument("--password", default="", help="Dashboard password when auth is enabled.")
    parser.add_argument(
        "--output",
        default="artifacts/verification-report.json",
        help="Path to save the verification report JSON.",
    )
    args = parser.parse_args()
    return verify(
        base_url=args.base_url,
        username=args.username or None,
        password=args.password or None,
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    sys.exit(main())
