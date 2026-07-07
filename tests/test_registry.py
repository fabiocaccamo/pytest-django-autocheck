"""Tests for the check registry and the common interface."""

import pytest

from pytest_django_autocheck.registry import (
    BaseCheck,
    CheckRegistry,
    Finding,
    load_builtin_checks,
    registry,
)


def test_finding_defaults() -> None:
    finding = Finding(
        check_name="demo",
        severity="ERROR",
        target="app.Model",
        message="boom",
    )
    assert finding.exception is None


def test_base_check_run_is_abstract() -> None:
    with pytest.raises(NotImplementedError):
        BaseCheck().run(None)


def test_registry_preserves_registration_order() -> None:
    local_registry = CheckRegistry()

    class First(BaseCheck):
        name = "first"

        def run(self, app_configs):
            return [Finding("first", "INFO", "a", "a")]

    class Second(BaseCheck):
        name = "second"

        def run(self, app_configs):
            return [Finding("second", "INFO", "b", "b")]

    local_registry.register(First())
    local_registry.register(Second())

    assert [check.name for check in local_registry.checks] == [
        "first",
        "second",
    ]


def test_load_builtin_checks_registers_the_builtin_checks() -> None:
    load_builtin_checks()
    names = {check.name for check in registry.checks}
    assert {
        "imports",
        "system_checks",
        "migrations",
        "models",
        "admin",
        "urls",
        "views",
        "templates",
        "management_commands",
        "forms",
        "serializers",
    } <= names
