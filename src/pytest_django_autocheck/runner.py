"""Programmatic entry point that selects the registered checks.

This is the thin layer the pytest plugin builds upon. It owns no Django setup:
callers must run it inside an environment where Django is configured and the
database is reachable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytest_django_autocheck.registry import (
    load_builtin_checks,
    load_entry_point_checks,
    registry,
)
from pytest_django_autocheck.settings import get_setting

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pytest_django_autocheck.registry import Check


def get_checks(
    only: Sequence[str] | None = None,
    skip: Sequence[str] | None = None,
) -> list[Check]:
    """Return the registered checks, optionally filtered by name.

    When ``only`` is ``None`` the selection falls back to the
    ``PYTEST_DJANGO_AUTOCHECK_CHECKS`` setting; if that is unset too, every
    registered check is returned. When ``skip`` is ``None`` the exclusion falls
    back to the ``PYTEST_DJANGO_AUTOCHECK_SKIP`` setting. The exclusion is
    applied after the inclusion, so a check named in both is skipped.
    """
    load_builtin_checks()
    load_entry_point_checks()
    checks = registry.checks
    known = {check.name for check in checks}
    if only is None:
        only = get_setting("CHECKS")
    _validate_names(only, known, "only")
    if only:
        wanted = set(only)
        checks = [check for check in checks if check.name in wanted]
    if skip is None:
        skip = get_setting("SKIP")
    _validate_names(skip, known, "skip")
    if skip:
        unwanted = set(skip)
        checks = [check for check in checks if check.name not in unwanted]
    return checks


def _validate_names(names: Sequence[str] | None, known: set[str], label: str) -> None:
    """Raise when a requested check name is not registered.

    A silently ignored typo (``--autocheck-only=admins``) would run nothing and
    still exit ``0``, giving a false green in CI; failing loudly instead.
    """
    if not names:
        return
    unknown = sorted(set(names) - known)
    if unknown:
        raise ValueError(
            f"unknown autocheck {label} name(s): {', '.join(unknown)}; "
            f"valid names are: {', '.join(sorted(known))}."
        )
