"""Tests for the text output formatter."""

from pytest_django_autocheck.output.text import format_text
from pytest_django_autocheck.registry import Finding


def test_format_text_empty() -> None:
    assert "no issues found" in format_text([])


def test_format_text_orders_by_severity() -> None:
    findings = [
        Finding("c", "WARNING", "b", "warn"),
        Finding("c", "ERROR", "a", "err"),
    ]
    text = format_text(findings)
    assert text.index("[ERROR]") < text.index("[WARNING]")
