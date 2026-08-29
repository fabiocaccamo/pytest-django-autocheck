"""Tests for the imports check."""

import importlib
import os

import pytest
from django.apps import apps

from pytest_django_autocheck.checks import imports as imports_module
from pytest_django_autocheck.checks.imports import ImportsCheck


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def test_check_metadata() -> None:
    check = ImportsCheck()
    assert check.name == "imports"
    assert check.severity == "ERROR"


def test_clean_app_has_no_findings() -> None:
    check = ImportsCheck()
    assert check.run(_exampleapp()) == []


def test_run_on_whole_project_has_no_errors() -> None:
    check = ImportsCheck()
    findings = check.run(None)
    assert [f for f in findings if f.severity == "ERROR"] == []


def test_iter_modules_discovers_app_modules() -> None:
    discovered = set(ImportsCheck._iter_modules(_exampleapp()))
    assert "tests.exampleapp.models" in discovered
    assert "tests.exampleapp.admin" in discovered
    assert "tests.exampleapp.factories" in discovered


def test_migrations_and_dunder_are_skipped() -> None:
    discovered = set(ImportsCheck._iter_modules(_exampleapp()))
    assert not any(".migrations" in module for module in discovered)
    assert not any(module.endswith("__init__") for module in discovered)


def test_pip_installed_apps_are_skipped() -> None:
    discovered = set(ImportsCheck._iter_modules(None))
    assert any(module.startswith("tests.exampleapp") for module in discovered)
    assert not any(module.startswith("django.contrib") for module in discovered)


def test_vendored_package_is_pruned_from_walk(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "myapp"
    (app_dir / "vendor" / "pytest_django_autocheck").mkdir(parents=True)
    (app_dir / "service.py").write_text("x = 1\n", encoding="utf-8")
    (app_dir / "vendor" / "pytest_django_autocheck" / "plugin.py").write_text(
        "raise ImportError('should never be imported')\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        imports_module,
        "own_package_dir",
        lambda: os.path.realpath(app_dir / "vendor" / "pytest_django_autocheck"),
    )

    class FakeConfig:
        name = "myapp"
        path = str(app_dir)

    discovered = set(ImportsCheck._iter_app_modules(FakeConfig()))
    assert "myapp.service" in discovered
    assert not any("pytest_django_autocheck" in module for module in discovered)


def test_hidden_and_node_modules_dirs_are_pruned_from_walk(tmp_path) -> None:
    app_dir = tmp_path / "myapp"
    (app_dir / ".venv" / "lib").mkdir(parents=True)
    (app_dir / "node_modules" / "pkg").mkdir(parents=True)
    (app_dir / "service.py").write_text("x = 1\n", encoding="utf-8")
    (app_dir / ".venv" / "lib" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (app_dir / "node_modules" / "pkg" / "mod.py").write_text(
        "x = 1\n", encoding="utf-8"
    )

    class FakeConfig:
        name = "myapp"
        path = str(app_dir)

    discovered = set(ImportsCheck._iter_app_modules(FakeConfig()))
    assert discovered == {"myapp.service"}


def test_module_prefix_root_uses_base_name() -> None:
    assert ImportsCheck._module_prefix("app", os.sep + "base", os.sep + "base") == "app"


def test_module_prefix_nested_subpackage() -> None:
    base = os.sep + "base"
    root = os.path.join(base, "sub", "pkg")
    assert ImportsCheck._module_prefix("app", base, root) == "app.sub.pkg"


def test_import_error_is_reported() -> None:
    check = ImportsCheck()

    def boom(module_path):
        raise ImportError("no module named foo")

    original = importlib.import_module
    importlib.import_module = boom  # type: ignore[assignment]
    try:
        findings = check._check_module("some.module")
    finally:
        importlib.import_module = original

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "ImportError" in findings[0].message
    assert findings[0].target == "some.module"


def test_circular_import_is_reported(monkeypatch) -> None:
    check = ImportsCheck()

    def boom(module_path):
        raise ImportError(
            "cannot import name 'X' (most likely due to a circular import)"
        )

    monkeypatch.setattr(imports_module.importlib, "import_module", boom)
    findings = check._check_module("some.module")
    assert len(findings) == 1
    assert "circular import" in findings[0].message


def test_generic_exception_is_reported(monkeypatch) -> None:
    check = ImportsCheck()

    def boom(module_path):
        raise ValueError("boom at import time")

    monkeypatch.setattr(imports_module.importlib, "import_module", boom)
    findings = check._check_module("some.module")
    assert len(findings) == 1
    assert "import raised ValueError" in findings[0].message


def test_run_reports_failing_module(monkeypatch) -> None:
    check = ImportsCheck()

    def boom(module_path):
        raise ImportError("broken")

    monkeypatch.setattr(imports_module.importlib, "import_module", boom)
    findings = check.run(_exampleapp())
    assert findings
    assert all(f.severity == "ERROR" for f in findings)


@pytest.mark.parametrize(
    "message",
    [
        "cannot import name 'X' (most likely due to a circular import)",
        "partially initialized module 'a' has no attribute 'b'",
    ],
)
def test_is_circular_import_by_message(message) -> None:
    assert ImportsCheck._is_circular_import(ImportError(message)) is True


def test_is_circular_import_false_for_plain_error() -> None:
    assert ImportsCheck._is_circular_import(ImportError("no module named foo")) is False
