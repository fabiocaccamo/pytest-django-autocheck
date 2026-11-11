"""Tests for the system checks adapter."""

from django.apps import apps
from django.core import checks as django_checks
from django.core.checks import Error, Info, Warning
from django.test import override_settings

from pytest_django_autocheck.checks import system as system_module
from pytest_django_autocheck.checks.system import SystemChecksCheck


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def test_check_metadata() -> None:
    check = SystemChecksCheck()
    assert check.name == "system_checks"
    assert check.severity == "ERROR"


def test_clean_project_has_no_errors() -> None:
    check = SystemChecksCheck()
    findings = check.run(None)
    assert [f for f in findings if f.severity == "ERROR"] == []


def test_severity_mapping(monkeypatch) -> None:
    messages = [
        Error("an error", id="x.E001"),
        Warning("a warning", id="x.W001"),
        Info("an info", id="x.I001"),
    ]
    monkeypatch.setattr(
        system_module.django_checks, "run_checks", lambda **kw: messages
    )
    findings = SystemChecksCheck().run(_exampleapp())
    severities = {f.target: f.severity for f in findings}
    assert severities["x.E001"] == "ERROR"
    assert severities["x.W001"] == "WARNING"
    assert severities["x.I001"] == "INFO"


def test_critical_level_maps_to_error() -> None:
    check = SystemChecksCheck()
    assert check._severity_for(django_checks.CRITICAL) == "ERROR"


def test_debug_level_maps_to_info() -> None:
    check = SystemChecksCheck()
    assert check._severity_for(django_checks.DEBUG) == "INFO"


def test_target_uses_object_when_present(monkeypatch) -> None:
    message = Error("broken", obj="myapp.MyModel", id="m.E001", hint="fix it")
    monkeypatch.setattr(
        system_module.django_checks, "run_checks", lambda **kw: [message]
    )
    findings = SystemChecksCheck().run(None)
    assert findings[0].target == "myapp.MyModel"
    assert "hint: fix it" in findings[0].message
    assert "[m.E001]" in findings[0].message


def test_target_falls_back_to_system_without_id(monkeypatch) -> None:
    message = Error("no id and no obj")
    monkeypatch.setattr(
        system_module.django_checks, "run_checks", lambda **kw: [message]
    )
    findings = SystemChecksCheck().run(None)
    assert findings[0].target == "system"


def test_deploy_disabled_by_default(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        system_module.django_checks,
        "run_checks",
        lambda **kw: captured.update(kw) or [],
    )
    SystemChecksCheck().run(None)
    assert captured["include_deployment_checks"] is False


@override_settings(PYTEST_DJANGO_AUTOCHECK_DEPLOY=True)
def test_deploy_enabled_includes_deployment_checks(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        system_module.django_checks,
        "run_checks",
        lambda **kw: captured.update(kw) or [],
    )
    SystemChecksCheck().run(None)
    assert captured["include_deployment_checks"] is True
