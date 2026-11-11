"""Tests for the forms check."""

import sys
import types

from django import forms
from django.apps import apps

from pytest_django_autocheck.checks import forms as forms_module
from pytest_django_autocheck.checks.forms import FormsCheck
from tests.exampleapp.forms import AuthorForm
from tests.exampleapp.models import Author


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def test_check_metadata() -> None:
    check = FormsCheck()
    assert check.name == "forms"
    assert check.severity == "ERROR"


def test_clean_project_has_no_findings() -> None:
    check = FormsCheck()
    assert check.run(None) == []


def test_explicit_app_configs_are_inspected() -> None:
    check = FormsCheck()
    assert check.run(_exampleapp()) == []


def test_project_form_is_discovered() -> None:
    from tests.exampleapp import forms as exampleapp_forms

    assert AuthorForm in set(FormsCheck._collect_forms(exampleapp_forms))


def test_project_form_is_checked(monkeypatch) -> None:
    checked: list[type] = []
    check = FormsCheck()
    monkeypatch.setattr(
        check, "_check_form", lambda form_class: checked.append(form_class) or []
    )
    check.run(_exampleapp())
    assert checked == [AuthorForm]


def test_collect_forms_skips_abstract_and_imported(monkeypatch) -> None:
    module = types.ModuleType("fake_forms")

    class Good(forms.ModelForm):
        class Meta:
            model = Author
            fields = ["name"]

    class Abstract(forms.ModelForm):
        pass

    Good.__module__ = "fake_forms"
    Abstract.__module__ = "fake_forms"
    module.Good = Good
    module.Abstract = Abstract
    module.Imported = AuthorForm
    module.not_a_form = object()

    collected = list(FormsCheck._collect_forms(module))
    assert collected == [Good]


def test_missing_forms_module_has_no_findings() -> None:
    assert FormsCheck()._check_module("nonexistent_package_xyz.forms") == []


def test_run_skips_apps_without_forms(monkeypatch) -> None:
    class FakeConfig:
        name = "nonexistent_package_xyz"

    monkeypatch.setattr(
        forms_module, "project_apps", lambda app_configs: [FakeConfig()]
    )
    check = FormsCheck()
    assert check.run(None) == []


def test_forms_module_failing_to_import_is_reported(tmp_path, monkeypatch) -> None:
    """An existing but broken ``forms`` module is not "no forms module"."""
    app_dir = tmp_path / "autocheck_broken_forms_app"
    app_dir.mkdir()
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "forms.py").write_text(
        "from django.forms import NoSuchFormClass\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class FakeConfig:
        name = "autocheck_broken_forms_app"

    monkeypatch.setattr(
        forms_module, "project_apps", lambda app_configs: [FakeConfig()]
    )
    try:
        findings = FormsCheck().run(None)
    finally:
        sys.modules.pop("autocheck_broken_forms_app", None)
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "autocheck_broken_forms_app.forms"
    assert "could not import the module: ImportError" in findings[0].message
    assert "NoSuchFormClass" in findings[0].message


def test_instantiation_failure_is_reported() -> None:
    class BoomForm:
        __qualname__ = "BoomForm"
        __module__ = "tests.fake"

        def __init__(self) -> None:
            raise ValueError("unknown field 'ghost'")

    check = FormsCheck()
    findings = check._check_form(BoomForm)
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "tests.fake.BoomForm"
    assert "unknown field" in findings[0].message
