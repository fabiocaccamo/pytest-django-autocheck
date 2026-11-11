"""Tests for the serializers check."""

import sys
import types

from django.apps import apps

from pytest_django_autocheck.checks import serializers as serializers_module
from pytest_django_autocheck.checks.serializers import SerializersCheck
from tests.exampleapp.serializers import AuthorSerializer


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def _base():
    return SerializersCheck._serializer_base()


def test_check_metadata() -> None:
    check = SerializersCheck()
    assert check.name == "serializers"


def test_clean_project_has_no_findings() -> None:
    check = SerializersCheck()
    assert check.run(None) == []


def test_explicit_app_configs_are_inspected() -> None:
    check = SerializersCheck()
    assert check.run(_exampleapp()) == []


def test_project_serializer_is_discovered() -> None:
    from tests.exampleapp import serializers as exampleapp_serializers

    discovered = set(
        SerializersCheck._collect_serializers(exampleapp_serializers, _base())
    )
    assert AuthorSerializer in discovered


def test_project_serializer_is_checked(monkeypatch) -> None:
    checked: list[type] = []
    check = SerializersCheck()
    monkeypatch.setattr(
        check,
        "_check_serializer",
        lambda serializer_class: checked.append(serializer_class) or [],
    )
    check.run(_exampleapp())
    assert checked == [AuthorSerializer]


def test_run_is_noop_without_drf(monkeypatch) -> None:
    monkeypatch.setattr(
        SerializersCheck, "_serializer_base", staticmethod(lambda: None)
    )
    assert SerializersCheck().run(None) == []


def test_serializer_base_returns_none_on_import_error(monkeypatch) -> None:
    def boom(name):
        raise ImportError("no drf")

    monkeypatch.setattr(serializers_module.importlib, "import_module", boom)
    assert SerializersCheck._serializer_base() is None


def test_collect_skips_abstract_and_imported() -> None:
    base = _base()
    module = types.ModuleType("fake_serializers")
    from rest_framework import serializers

    class Concrete(serializers.ModelSerializer):
        class Meta:
            model = apps.get_model("exampleapp", "Author")
            fields = ["id", "name"]

    class Abstract(serializers.Serializer):
        pass

    Concrete.__module__ = "fake_serializers"
    Abstract.__module__ = "fake_serializers"
    module.Concrete = Concrete
    module.Abstract = Abstract
    module.Imported = AuthorSerializer
    module.not_a_serializer = object()

    collected = list(SerializersCheck._collect_serializers(module, base))
    assert collected == [Concrete]


def test_field_build_failure_is_reported() -> None:
    class BoomSerializer:
        __qualname__ = "BoomSerializer"
        __module__ = "tests.fake"

        def __init__(self) -> None:
            pass

        @property
        def fields(self):
            raise ValueError("unknown field 'ghost'")

    check = SerializersCheck()
    findings = check._check_serializer(BoomSerializer)
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "tests.fake.BoomSerializer"
    assert "unknown field" in findings[0].message


def test_run_skips_apps_without_module(monkeypatch) -> None:
    class FakeConfig:
        name = "nonexistent_package_xyz"

    monkeypatch.setattr(
        serializers_module, "project_apps", lambda app_configs: [FakeConfig()]
    )
    check = SerializersCheck()
    assert check.run(None) == []


def test_serializers_module_failing_to_import_is_reported(
    tmp_path, monkeypatch
) -> None:
    """An existing but broken serializers module is not "no such module"."""
    app_dir = tmp_path / "autocheck_broken_serializers_app"
    app_dir.mkdir()
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "serializers.py").write_text(
        "from rest_framework.serializers import NoSuchSerializer\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class FakeConfig:
        name = "autocheck_broken_serializers_app"

    monkeypatch.setattr(
        serializers_module, "project_apps", lambda app_configs: [FakeConfig()]
    )
    try:
        findings = SerializersCheck().run(None)
    finally:
        sys.modules.pop("autocheck_broken_serializers_app", None)
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "autocheck_broken_serializers_app.serializers"
    assert "could not import the module: ImportError" in findings[0].message
    assert "NoSuchSerializer" in findings[0].message
