from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..models import GeneratedReportFile
from .dashboard_service import DashboardService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WeeklyReportService:
    def __init__(self, dashboard_service: DashboardService) -> None:
        self.dashboard_service = dashboard_service
        self.config = dashboard_service.config

    def generate_weekly_report(self, *, use_live_connectors: bool = False) -> GeneratedReportFile:
        state = self.dashboard_service.run_pipeline(use_live_connectors=use_live_connectors)
        latest_report = state["latest_report"] or {}
        metrics_history = state["metrics_history"]
        now = utc_now()
        report_id = now.strftime("%Y%m%d-%H%M%S")
        base_name = f"weekly-report-{report_id}"
        json_path = self.config.reports_dir / f"{base_name}.json"
        markdown_path = self.config.reports_dir / f"{base_name}.md"
        html_path = self.config.reports_dir / f"{base_name}.html"

        summary = self._summary_block(metrics_history, latest_report)
        projected_impact = self._projected_impact(latest_report)
        report_payload = {
            "report_id": report_id,
            "generated_at": now.isoformat(),
            "summary": summary,
            "projected_impact": projected_impact,
            "latest_report": latest_report,
        }
        json_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        markdown_path.write_text(
            self._render_markdown(report_payload),
            encoding="utf-8",
        )
        html_path.write_text(
            self._render_html(report_payload),
            encoding="utf-8",
        )

        generated = GeneratedReportFile(
            report_id=report_id,
            generated_at=now.isoformat(),
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            html_path=str(html_path),
            report_type="weekly",
        )
        self.dashboard_service.register_report(generated)
        return generated

    def generate_market_watch_report(
        self,
        *,
        gig_url: str = "",
        search_terms: list[str] | None = None,
    ) -> GeneratedReportFile | None:
        settings_service = self.dashboard_service.settings_service
        marketplace_settings = settings_service.get_settings().marketplace if settings_service is not None else None
        target_url = gig_url.strip() or (marketplace_settings.my_gig_url if marketplace_settings is not None else "")
        if not target_url:
            return None

        state = self.dashboard_service.compare_my_gig_to_market(
            gig_url=target_url,
            search_terms=search_terms or (marketplace_settings.search_terms if marketplace_settings is not None else None),
        )
        return self.generate_market_watch_report_from_state(state)

    def generate_market_watch_report_from_state(self, state: dict | None = None) -> GeneratedReportFile:
        effective_state = state or self.dashboard_service.get_state()
        comparison = effective_state.get("gig_comparison") or {}
        latest_report = effective_state.get("latest_report") or {}
        now = utc_now()
        report_id = now.strftime("%Y%m%d-%H%M%S")
        base_name = f"market-watch-{report_id}"
        json_path = self.config.reports_dir / f"{base_name}.json"
        markdown_path = self.config.reports_dir / f"{base_name}.md"
        html_path = self.config.reports_dir / f"{base_name}.html"

        summary = self._market_watch_summary(comparison)
        report_payload = {
            "report_id": report_id,
            "report_type": "market_watch",
            "generated_at": now.isoformat(),
            "summary": summary,
            "gig_comparison": comparison,
            "latest_report": latest_report,
        }
        json_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        markdown_path.write_text(self._render_market_watch_markdown(report_payload), encoding="utf-8")
        html_path.write_text(self._render_market_watch_html(report_payload), encoding="utf-8")

        generated = GeneratedReportFile(
            report_id=report_id,
            generated_at=now.isoformat(),
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            html_path=str(html_path),
            report_type="market_watch",
        )
        self.dashboard_service.register_report(generated)
        current_state = self.dashboard_service._load_dashboard_state()
        if current_state.gig_comparison:
            current_state.gig_comparison["latest_report_file"] = asdict(generated)
            blueprint = current_state.gig_comparison.get("implementation_blueprint") or {}
            history_entry = {
                "captured_at": now.isoformat(),
                "status": current_state.gig_comparison.get("status", "unknown"),
                "comparison_source": current_state.gig_comparison.get("comparison_source", "live"),
                "competitor_count": current_state.gig_comparison.get("competitor_count", 0),
                "market_anchor_price": current_state.gig_comparison.get("market_anchor_price"),
                "recommended_title": blueprint.get("recommended_title", ""),
                "recommended_tags": blueprint.get("recommended_tags", []),
                "do_this_first": blueprint.get("do_this_first", [])[:3],
                "implementation_summary": current_state.gig_comparison.get("implementation_summary", ""),
                "report_html_path": str(html_path),
            }
            current_state.comparison_history = [history_entry, *current_state.comparison_history][:12]
            self.dashboard_service._save_dashboard_state(current_state)
        return generated

    def _summary_block(self, metrics_history, latest_report):
        latest = metrics_history[-1] if metrics_history else None
        previous = metrics_history[-2] if len(metrics_history) > 1 else None
        changes: list[str] = []
        if latest and previous:
            changes.append(
                f"Impressions moved from {previous['impressions']} to {latest['impressions']}."
            )
            changes.append(
                f"CTR moved from {previous['ctr']}% to {latest['ctr']}%."
            )
            changes.append(
                f"Conversion moved from {previous['conversion_rate']}% to {latest['conversion_rate']}%."
            )
        elif latest:
            changes.append(
                f"This is the first stored weekly point with {latest['impressions']} impressions and {latest['ctr']}% CTR."
            )
        else:
            changes.append("No stored metrics were available yet.")

        latest_actions = latest_report.get("weekly_action_plan", [])[:3]
        return {
            "what_changed": changes,
            "recommendations": latest_actions,
            "ab_tests_ready": self._ab_test_notes(metrics_history),
        }

    def _ab_test_notes(self, metrics_history) -> list[str]:
        if len(metrics_history) < 4:
            return ["Keep collecting weekly points before concluding an A/B cycle."]
        return [
            "You have enough weekly points to compare title or tag experiments across multiple runs.",
            "Review CTR changes first; if CTR improved but conversion did not, test offer framing next.",
        ]

    def _projected_impact(self, latest_report) -> list[str]:
        recommendations = latest_report.get("weekly_action_plan", [])
        if not recommendations:
            return ["Projected impact is unavailable until the optimizer generates a fresh action plan."]
        return [
            "Applying the highest-priority title and keyword recommendations should improve discovery before deeper funnel tweaks.",
            "Queue approval flow should reduce risky edits while still keeping experiments moving each week.",
        ]

    def _market_watch_summary(self, comparison: dict) -> dict:
        blueprint = comparison.get("implementation_blueprint") or {}
        return {
            "status": comparison.get("status", "unknown"),
            "message": comparison.get("message", ""),
            "recommended_title": blueprint.get("recommended_title", ""),
            "recommended_tags": blueprint.get("recommended_tags", []),
            "top_actions": blueprint.get("weekly_actions", [])[:3] or comparison.get("what_to_implement", [])[:3],
            "do_this_first": blueprint.get("do_this_first", [])[:3],
            "competitors_compared": comparison.get("competitor_count", 0),
        }

    def _render_markdown(self, payload: dict) -> str:
        summary = payload["summary"]
        latest_report = payload["latest_report"]
        competitive = latest_report.get("competitive_gap_analysis") or {}
        ai_overview = latest_report.get("ai_overview") or {}
        lines = [
            f"# Weekly Gig Report {payload['report_id']}",
            "",
            f"Generated at: {payload['generated_at']}",
            "",
            "## What Changed",
            *[f"- {item}" for item in summary["what_changed"]],
            "",
            "## Recommended Changes",
            *[f"- {item}" for item in summary["recommendations"]],
            "",
            "## A/B Tests Ready To Conclude",
            *[f"- {item}" for item in summary["ab_tests_ready"]],
            "",
            "## Projected Impact",
            *[f"- {item}" for item in payload["projected_impact"]],
            "",
            "## Keyword Pulse",
            *[f"- {item}" for item in latest_report.get("niche_pulse", {}).get("trending_queries", [])],
            "",
            "## Competitive Gap Analysis",
            f"- {competitive.get('proxy_warning', 'No competitive comparison was available for this run.')}",
            *[f"- {item}" for item in competitive.get("why_competitors_win", [])],
            "",
            "## What To Implement",
            *[f"- {item}" for item in competitive.get("what_to_implement", [])],
            "",
            "## AI Overview",
            f"- {ai_overview.get('summary', 'No AI overview was generated for this run.')}",
            *[f"- {item}" for item in ai_overview.get("next_steps", [])],
        ]
        return "\n".join(lines)

    def _render_market_watch_markdown(self, payload: dict) -> str:
        comparison = payload["gig_comparison"]
        blueprint = comparison.get("implementation_blueprint") or {}
        lines = [
            f"# Market Watch Report {payload['report_id']}",
            "",
            f"Generated at: {payload['generated_at']}",
            "",
            "## Market Status",
            f"- Status: {comparison.get('status', 'unknown')}",
            f"- Message: {comparison.get('message', 'No comparison message was generated.')}",
            f"- Competitors compared: {comparison.get('competitor_count', 0)}",
            "",
            "## Recommended Title",
            f"- {blueprint.get('recommended_title', 'No recommended title generated yet.')}",
            "",
            "## Title Options",
            *[
                f"- {item.get('label', 'Option')}: {item.get('title', '')}"
                for item in blueprint.get("title_options", [])
            ],
            "",
            "## Recommended Tags",
            *[f"- {item}" for item in blueprint.get("recommended_tags", [])],
            "",
            "## Description Blueprint",
            *[f"- {item}" for item in blueprint.get("description_blueprint", [])],
            "",
            "## Description Options",
            *[
                f"- {item.get('label', 'Option')}: {item.get('summary', '')}"
                for item in blueprint.get("description_options", [])
            ],
            "",
            "## Pricing Strategy",
            *[f"- {item}" for item in blueprint.get("pricing_strategy", [])],
            "",
            "## What To Implement Next",
            *[f"- {item}" for item in blueprint.get("do_this_first", [])[:3]],
            "",
            "## Weekly Actions",
            *[f"- {item}" for item in blueprint.get("weekly_actions", [])],
            "",
            "## Why Competitors Win",
            *[f"- {item}" for item in comparison.get("why_competitors_win", [])],
        ]
        return "\n".join(lines)

    def _render_html(self, payload: dict) -> str:
        summary = payload["summary"]
        latest_report = payload["latest_report"]
        competitive = latest_report.get("competitive_gap_analysis") or {}
        ai_overview = latest_report.get("ai_overview") or {}
        def list_html(items):
            return "".join(f"<li>{item}</li>" for item in items)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weekly Gig Report {payload['report_id']}</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 0; background: #f6f1e8; color: #1f1c18; }}
    .page {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 60px; }}
    .card {{ background: white; border-radius: 20px; padding: 24px; margin-bottom: 20px; box-shadow: 0 14px 34px rgba(0,0,0,0.08); }}
    h1, h2 {{ margin-top: 0; }}
    ul {{ line-height: 1.7; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="card">
      <h1>Weekly Gig Report {payload['report_id']}</h1>
      <p>Generated at {payload['generated_at']}</p>
    </div>
    <div class="card">
      <h2>What Changed</h2>
      <ul>{list_html(summary['what_changed'])}</ul>
    </div>
    <div class="card">
      <h2>Recommended Changes</h2>
      <ul>{list_html(summary['recommendations'])}</ul>
    </div>
    <div class="card">
      <h2>A/B Tests Ready To Conclude</h2>
      <ul>{list_html(summary['ab_tests_ready'])}</ul>
    </div>
    <div class="card">
      <h2>Projected Impact</h2>
      <ul>{list_html(payload['projected_impact'])}</ul>
    </div>
    <div class="card">
      <h2>Keyword Pulse</h2>
      <ul>{list_html(latest_report.get('niche_pulse', {}).get('trending_queries', []))}</ul>
    </div>
    <div class="card">
      <h2>Competitive Gap Analysis</h2>
      <p>{competitive.get('proxy_warning', 'No competitive comparison was available for this run.')}</p>
      <ul>{list_html(competitive.get('why_competitors_win', []))}</ul>
    </div>
    <div class="card">
      <h2>What To Implement</h2>
      <ul>{list_html(competitive.get('what_to_implement', []))}</ul>
    </div>
    <div class="card">
      <h2>AI Overview</h2>
      <p>{ai_overview.get('summary', 'No AI overview was generated for this run.')}</p>
      <ul>{list_html(ai_overview.get('next_steps', []))}</ul>
    </div>
  </div>
</body>
</html>"""

    def _render_market_watch_html(self, payload: dict) -> str:
        comparison = payload["gig_comparison"]
        blueprint = comparison.get("implementation_blueprint") or {}

        def list_html(items):
            return "".join(f"<li>{item}</li>" for item in items)

        description_full = str(blueprint.get("description_full", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Watch Report {payload['report_id']}</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 0; background: #f6f1e8; color: #1f1c18; }}
    .page {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 60px; }}
    .card {{ background: white; border-radius: 20px; padding: 24px; margin-bottom: 20px; box-shadow: 0 14px 34px rgba(0,0,0,0.08); }}
    h1, h2 {{ margin-top: 0; }}
    ul {{ line-height: 1.7; }}
    pre {{ white-space: pre-wrap; background: #f8f4ec; border-radius: 16px; padding: 16px; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="card">
      <h1>Market Watch Report {payload['report_id']}</h1>
      <p>Generated at {payload['generated_at']}</p>
      <p>Status: {comparison.get('status', 'unknown')}</p>
      <p>{comparison.get('message', 'No comparison message was generated.')}</p>
    </div>
    <div class="card">
      <h2>Recommended Title</h2>
      <p>{blueprint.get('recommended_title', 'No recommended title generated yet.')}</p>
    </div>
    <div class="card">
      <h2>Title Options</h2>
      <ul>{list_html([f"{item.get('label', 'Option')}: {item.get('title', '')}" for item in blueprint.get('title_options', [])])}</ul>
    </div>
    <div class="card">
      <h2>Recommended Tags</h2>
      <ul>{list_html(blueprint.get('recommended_tags', []))}</ul>
    </div>
    <div class="card">
      <h2>Description Blueprint</h2>
      <ul>{list_html(blueprint.get('description_blueprint', []))}</ul>
      <pre>{description_full}</pre>
    </div>
    <div class="card">
      <h2>Description Options</h2>
      <ul>{list_html([f"{item.get('label', 'Option')}: {item.get('summary', '')}" for item in blueprint.get('description_options', [])])}</ul>
    </div>
    <div class="card">
      <h2>Pricing Strategy</h2>
      <ul>{list_html(blueprint.get('pricing_strategy', []))}</ul>
    </div>
    <div class="card">
      <h2>What To Implement Next</h2>
      <ul>{list_html(blueprint.get('do_this_first', []))}</ul>
    </div>
    <div class="card">
      <h2>Weekly Actions</h2>
      <ul>{list_html(blueprint.get('weekly_actions', []))}</ul>
    </div>
    <div class="card">
      <h2>Why Competitors Win</h2>
      <ul>{list_html(comparison.get('why_competitors_win', []))}</ul>
    </div>
  </div>
</body>
</html>"""
