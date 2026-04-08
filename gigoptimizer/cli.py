from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import GigOptimizerConfig
from .orchestrator import GigOptimizerOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Fiverr gig optimization report.")
    parser.add_argument("--input", help="Path to a gig snapshot JSON file.")
    parser.add_argument("--output", default=None, help="Optional output path for the generated report JSON.")
    parser.add_argument(
        "--use-live-connectors",
        action="store_true",
        help="Enrich the report with Google Trends, SEMrush, and Fiverr connector data when configured.",
    )
    parser.add_argument(
        "--show-connector-status",
        action="store_true",
        help="Print connector setup status before running.",
    )
    parser.add_argument(
        "--debug-selectors",
        action="store_true",
        help="Dump Fiverr dashboard HTML and selector metadata for inspection.",
    )
    parser.add_argument(
        "--selector-debug-output",
        default=None,
        help="Optional path for the Fiverr selector debug HTML output.",
    )
    args = parser.parse_args()

    if not args.input and not args.debug_selectors:
        parser.error("--input is required unless you are using --debug-selectors.")

    config = GigOptimizerConfig.from_env()
    if args.show_connector_status or args.use_live_connectors or args.debug_selectors:
        _print_connector_status(config.validate_credentials())

    orchestrator = GigOptimizerOrchestrator(config=config)

    if args.debug_selectors:
        status = orchestrator.fiverr.debug_selectors(args.selector_debug_output)
        _print_connector_status([status])
        return

    report = orchestrator.optimize_file(
        args.input,
        use_live_connectors=args.use_live_connectors,
    )
    payload = report.to_dict()

    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved report to {args.output}")
        return

    print(json.dumps(payload, indent=2))


def _print_connector_status(statuses) -> None:
    icon_map = {
        "active": "[✓]",
        "ok": "[✓]",
        "skipped": "[✗]",
        "warning": "[!]",
        "partial": "[!]",
        "error": "[!]",
    }
    for status in statuses:
        icon = icon_map.get(status.status, "[ ]")
        label = _humanize_connector_name(status.connector)
        print(f"{icon} {label:<16} {status.detail}", file=sys.stderr)


def _humanize_connector_name(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split("_"))


if __name__ == "__main__":
    main()
