"""Common interface and registry shared by every check.

This module defines the contract that all checks (built-in and third-party,
registered via entry points) must follow, and the registry that runs them in
registration order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
    from importlib.metadata import EntryPoint

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
    """Structural interface every check must satisfy.

    Checks may also expose a ``requires_db`` boolean (default ``True`` when
    absent): when ``False`` the pytest item does not request the database
    fixture, so running only such checks never creates the test database.
    """

    name: str
    severity: Severity

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]: ...


class BaseCheck:
    """Convenience base class for built-in checks.

    Subclasses must set ``name`` and ``severity`` and implement ``run``.
    ``requires_db`` defaults to ``True``; checks that never touch the
    database override it so their pytest item skips the database fixture.
    """

    name: str = ""
    severity: Severity = "ERROR"
    requires_db: bool = True

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
        """Add ``check``, refusing a name that is already taken.

        Names select checks (``--autocheck-only``) and identify their pytest
        items, so two checks sharing one would be indistinguishable.
        """
        if any(registered.name == check.name for registered in self._checks):
            raise ValueError(f"a check named '{check.name}' is already registered.")
        self._checks.append(check)
        return check

    @property
    def checks(self) -> list[Check]:
        return list(self._checks)


registry = CheckRegistry()


def load_builtin_checks() -> None:
    """Register the built-in checks."""
    from pytest_django_autocheck import checks  # noqa: F401  (registers on import)


ENTRY_POINT_GROUP = "pytest_django_autocheck.checks"

_entry_points_loaded = False


def load_entry_point_checks() -> None:
    """Register third-party checks declared under :data:`ENTRY_POINT_GROUP`.

    Each entry point must resolve to a check class (instantiated with no
    arguments) or a ready check instance satisfying :class:`Check`. A broken
    entry point raises instead of being skipped: silently ignoring it would
    green-light a project that believes its custom check is running. Every
    entry point is loaded before any check is registered, and the group only
    counts as loaded once all of them are, so a failure is raised again on
    the next call instead of leaving the rest silently unregistered.
    """
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    from importlib.metadata import entry_points

    checks = [
        _load_entry_point_check(entry_point)
        for entry_point in entry_points(group=ENTRY_POINT_GROUP)
    ]
    for check in checks:
        registry.register(check)
    _entry_points_loaded = True


def _load_entry_point_check(entry_point: EntryPoint) -> Check:
    loaded = entry_point.load()
    check = loaded() if isinstance(loaded, type) else loaded
    if not isinstance(check, Check):
        raise TypeError(
            f"entry point '{entry_point.name}' in group "
            f"'{ENTRY_POINT_GROUP}' must provide a check with 'name', "
            "'severity' and 'run(app_configs)'."
        )
    return check
