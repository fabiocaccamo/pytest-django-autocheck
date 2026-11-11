"""Tests for the imports check."""

import importlib
import os
import sys

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


def test_nested_installed_app_is_pruned_from_the_outer_walk(
    tmp_path, monkeypatch
) -> None:
    """A nested app is imported once, under its own dotted name.

    Importing ``core.apps.shop.models`` on top of ``shop.models`` would
    register a second ``core.Product`` model with no table.
    """
    outer_dir = tmp_path / "core"
    nested_dir = outer_dir / "apps" / "shop"
    nested_dir.mkdir(parents=True)
    (outer_dir / "service.py").write_text("x = 1\n", encoding="utf-8")
    (nested_dir / "models.py").write_text("x = 1\n", encoding="utf-8")

    class OuterConfig:
        name = "core"
        path = str(outer_dir)

    class NestedConfig:
        name = "shop"
        path = str(nested_dir)

    outer, nested = OuterConfig(), NestedConfig()
    monkeypatch.setattr(imports_module.apps, "get_app_configs", lambda: [outer, nested])

    assert set(ImportsCheck._iter_app_modules(outer)) == {"core.service"}
    assert set(ImportsCheck._iter_app_modules(nested)) == {"shop.models"}


def test_packages_are_discovered_by_their_own_name() -> None:
    discovered = set(ImportsCheck._iter_modules(_exampleapp()))
    assert "tests.exampleapp" in discovered
    assert "tests.exampleapp.management.commands" in discovered


def test_broken_package_without_other_modules_is_reported(
    tmp_path, monkeypatch
) -> None:
    """A package made of its ``__init__.py`` alone must still be imported."""
    app_dir = tmp_path / "autocheck_initonly_app"
    (app_dir / "helpers").mkdir(parents=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "helpers" / "__init__.py").write_text(
        "import autocheck_module_that_does_not_exist\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class FakeConfig:
        name = "autocheck_initonly_app"
        path = str(app_dir)

    try:
        findings = ImportsCheck().run([FakeConfig()])
    finally:
        sys.modules.pop("autocheck_initonly_app", None)
    assert [finding.target for finding in findings] == [
        "autocheck_initonly_app.helpers"
    ]
    assert "autocheck_module_that_does_not_exist" in findings[0].message


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
