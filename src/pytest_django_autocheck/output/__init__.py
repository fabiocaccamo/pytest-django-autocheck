"""Output formatters for check findings.

Findings are rendered as human readable text for local use and for the pytest
report.
"""

from pytest_django_autocheck.output.text import format_text

__all__ = ["format_text"]
