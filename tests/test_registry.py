"""Tests for the check registry and the common interface."""

import importlib
import importlib.metadata

import pytest

from pytest_django_autocheck.registry import (
    BaseCheck,
    CheckRegistry,
    Finding,
    load_builtin_checks,
    load_entry_point_checks,
    registry,
)


class _FakeEntryPoint:
    name = "third_party"

    def __init__(self, obj):
        self._obj = obj

    def load(self):
        return self._obj


class _ThirdPartyCheck(BaseCheck):
    name = "third_party"
    severity = "ERROR"

    def run(self, app_configs):
        return []


@pytest.fixture
def _entry_point(monkeypatch):
    """Reset the load flag and clean the registry after the test."""
    # The package's __init__ re-exports the ``registry`` instance, shadowing
    # the submodule attribute, so the module is resolved explicitly.
    registry_module = importlib.import_module("pytest_django_autocheck.registry")
    monkeypatch.setattr(registry_module, "_entry_points_loaded", False)
    yield
    registry._checks[:] = [
        check for check in registry._checks if check.name != "third_party"
    ]


def _fake_entry_points(monkeypatch, obj) -> None:
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda group: [_FakeEntryPoint(obj)],
    )


def test_load_entry_point_checks_instantiates_classes(
    monkeypatch, _entry_point
) -> None:
    _fake_entry_points(monkeypatch, _ThirdPartyCheck)
    load_entry_point_checks()
    assert "third_party" in {check.name for check in registry.checks}


def test_load_entry_point_checks_accepts_instances(monkeypatch, _entry_point) -> None:
    _fake_entry_points(monkeypatch, _ThirdPartyCheck())
    load_entry_point_checks()
    assert "third_party" in {check.name for check in registry.checks}


def test_load_entry_point_checks_is_idempotent(monkeypatch, _entry_point) -> None:
    _fake_entry_points(monkeypatch, _ThirdPartyCheck)
    load_entry_point_checks()
    load_entry_point_checks()
    names = [check.name for check in registry.checks]
    assert names.count("third_party") == 1


def test_load_entry_point_checks_rejects_invalid_objects(
    monkeypatch, _entry_point
) -> None:
    _fake_entry_points(monkeypatch, object())
    with pytest.raises(TypeError, match="third_party"):
        load_entry_point_checks()


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


def test_requires_db_defaults_and_overrides() -> None:
    from pytest_django_autocheck.checks import (
        ImportsCheck,
        MigrationsCheck,
        ModelsCheck,
        TemplatesCheck,
        UrlsCheck,
    )

    assert BaseCheck.requires_db is True
    assert ModelsCheck.requires_db is True
    assert ImportsCheck.requires_db is False
    assert MigrationsCheck.requires_db is False
    assert TemplatesCheck.requires_db is False
    assert UrlsCheck.requires_db is False


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
