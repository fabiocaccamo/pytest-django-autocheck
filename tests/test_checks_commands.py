"""Tests for the management_commands check."""

from django.apps import apps

from pytest_django_autocheck.checks import commands as commands_module
from pytest_django_autocheck.checks.commands import ManagementCommandsCheck


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def test_check_metadata() -> None:
    check = ManagementCommandsCheck()
    assert check.name == "management_commands"
    assert check.severity == "ERROR"


def test_clean_project_has_no_findings() -> None:
    check = ManagementCommandsCheck()
    assert check.run(None) == []


def test_allowed_app_names_includes_only_project_apps() -> None:
    allowed = ManagementCommandsCheck._allowed_app_names(None)
    assert "tests.exampleapp" in allowed
    assert "django.core" not in allowed


def test_allowed_app_names_with_explicit_configs() -> None:
    allowed = ManagementCommandsCheck._allowed_app_names(_exampleapp())
    assert allowed == {"tests.exampleapp"}


def test_noop_command_is_clean() -> None:
    check = ManagementCommandsCheck()
    assert check._check_command("tests.exampleapp", "noop") == []


def test_load_failure_is_reported(monkeypatch) -> None:
    def boom(app_name, name):
        raise ImportError("broken command module")

    monkeypatch.setattr(commands_module, "load_command_class", boom)
    check = ManagementCommandsCheck()
    findings = check._check_command("tests.exampleapp", "noop")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "broken command module" in findings[0].message


def test_create_parser_failure_is_reported(monkeypatch) -> None:
    class BoomCommand:
        def create_parser(self, prog, name):
            raise ValueError("bad arguments")

    monkeypatch.setattr(
        commands_module, "load_command_class", lambda a, n: BoomCommand()
    )
    check = ManagementCommandsCheck()
    findings = check._check_command("tests.exampleapp", "noop")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "bad arguments" in findings[0].message


def test_run_checks_the_project_command(monkeypatch) -> None:
    checked: list[tuple[str, str]] = []

    def record(app_name, name):
        checked.append((app_name, name))
        return []

    monkeypatch.setattr(
        ManagementCommandsCheck, "_check_command", lambda self, a, n: record(a, n)
    )
    ManagementCommandsCheck().run(None)
    assert ("tests.exampleapp", "noop") in checked
