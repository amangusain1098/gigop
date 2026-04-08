from __future__ import annotations

import re
from typing import Iterable

from ..models import ValidationIssue, ValidationResult
from .tos_checker import TOSChecker


class HallucinationValidator:
    NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")

    def __init__(self) -> None:
        self.tos_checker = TOSChecker()

    def validate(
        self,
        text: str,
        *,
        allowed_numbers: Iterable[int | float | str] = (),
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        sanitized_output = text

        normalized_allowed = self._normalize_allowed_numbers(allowed_numbers)
        output_numbers = self._extract_numeric_tokens(text)
        for token in output_numbers:
            normalized_token = self._normalize_token(token)
            if normalized_allowed and normalized_token not in normalized_allowed:
                issues.append(
                    ValidationIssue(
                        code="number_mismatch",
                        message=f"Output contains a number not present in the provided data: '{token}'.",
                        severity="high",
                    )
                )

        tos_issues = self.tos_checker.scan(text)
        if tos_issues:
            issues.extend(tos_issues)
            sanitized_output = self.tos_checker.sanitize(sanitized_output)

        confidence = 100
        for issue in issues:
            if issue.severity == "high":
                confidence -= 20
            else:
                confidence -= 10
        confidence = max(0, confidence)

        return ValidationResult(
            valid=not issues,
            confidence=confidence,
            issues=issues,
            sanitized_output=sanitized_output,
        )

    def _extract_numeric_tokens(self, text: str) -> list[str]:
        return self.NUMBER_PATTERN.findall(text)

    def _normalize_allowed_numbers(self, values: Iterable[int | float | str]) -> set[str]:
        normalized: set[str] = set()
        for value in values:
            normalized.add(self._normalize_token(str(value)))
        return normalized

    def _normalize_token(self, token: str) -> str:
        cleaned = token.strip().replace("%", "")
        try:
            number = float(cleaned)
        except ValueError:
            return cleaned.lower()
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")
