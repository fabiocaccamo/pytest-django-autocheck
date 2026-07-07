"""Common interface and registry shared by every check.

This module defines the contract that all checks (built-in and third-party,
registered via entry points) must follow, and the registry that runs them in
registration order.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.apps.config import AppConfig

Severity = Literal["ERROR", "WARNING", "INFO"]


@dataclass(slots=True)
class Finding:
    """A single result produced by a check.

    Attributes:
        check_name: Name of the check that produced this finding.
        severity: One of ``ERROR``, ``WARNING`` or ``INFO``.
        target: The inspected object, e.g. ``"app_label.ModelName"``.
        message: Human readable description of the finding.
        exception: The original exception, when the finding wraps one.
    """

    check_name: str
    severity: Severity
    target: str
    message: str
    exception: Exception | None = None


@runtime_checkable
class Check(Protocol):
    """Structural interface every check must satisfy."""

    name: str
    severity: Severity

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]: ...


class BaseCheck:
    """Convenience base class for built-in checks.

    Subclasses must set ``name`` and ``severity`` and implement ``run``.
    """

    name: str = ""
    severity: Severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        raise NotImplementedError


class CheckRegistry:
    """Ordered collection of checks.

    Registration order is the order in which findings are reported. Each check
    is independent: it is collected as its own pytest item and runs in its own
    isolated database transaction, so the order never affects correctness, only
    the order of the output.
    """

    def __init__(self) -> None:
        self._checks: list[Check] = []

    def register(self, check: Check) -> Check:
        self._checks.append(check)
        return check

    @property
    def checks(self) -> list[Check]:
        return list(self._checks)


registry = CheckRegistry()


def load_builtin_checks() -> None:
    """Register the built-in checks."""
    from pytest_django_autocheck import checks  # noqa: F401  (registers on import)
