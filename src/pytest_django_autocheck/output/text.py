"""Human readable text output for local use."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pytest_django_autocheck.registry import Finding

_SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}


def format_text(findings: Sequence[Finding]) -> str:
    """Render findings as plain text, most severe first."""
    if not findings:
        return "pytest-django-autocheck: no issues found."

    ordered = sorted(
        findings, key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.target)
    )
    lines = [
        f"[{finding.severity}] {finding.check_name}: "
        f"{finding.target}: {finding.message}"
        for finding in ordered
    ]
    return "\n".join(lines)
