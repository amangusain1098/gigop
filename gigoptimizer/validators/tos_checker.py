from __future__ import annotations

import re

from ..models import ValidationIssue


ABSOLUTE_CLAIM_PATTERNS = [
    (re.compile(r"\bguarantee(?:d|s)?\b", flags=re.IGNORECASE), "guaranteed"),
    (re.compile(r"\b100%\b", flags=re.IGNORECASE), "100%"),
    (re.compile(r"\balways\b", flags=re.IGNORECASE), "always"),
    (re.compile(r"\bnever fails?\b", flags=re.IGNORECASE), "never fails"),
    (re.compile(r"\bwill definitely\b", flags=re.IGNORECASE), "will definitely"),
]


class TOSChecker:
    def scan(self, text: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for pattern, label in ABSOLUTE_CLAIM_PATTERNS:
            if pattern.search(text):
                issues.append(
                    ValidationIssue(
                        code="absolute_claim",
                        message=f"Contains risky guarantee language: '{label}'.",
                        severity="high",
                    )
                )
        return issues

    def sanitize(self, text: str) -> str:
        sanitized = text
        replacements = [
            (re.compile(r"\bguarantee(?:d|s)?\b", flags=re.IGNORECASE), "aim to improve"),
            (re.compile(r"\b100%\b", flags=re.IGNORECASE), "strong"),
            (re.compile(r"\balways\b", flags=re.IGNORECASE), "typically"),
            (re.compile(r"\bnever fails?\b", flags=re.IGNORECASE), "is designed to help"),
            (re.compile(r"\bwill definitely\b", flags=re.IGNORECASE), "can often"),
        ]
        for pattern, replacement in replacements:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized
