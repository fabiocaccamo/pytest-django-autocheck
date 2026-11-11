"""Tests for the shared optional module import."""

import sys

import pytest

from pytest_django_autocheck.checks.shared.modules import import_optional_module


@pytest.fixture
def package_dir(tmp_path, monkeypatch):
    """Provide an importable ``autocheck_optional_app`` package directory."""
    directory = tmp_path / "autocheck_optional_app"
    directory.mkdir()
    (directory / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield directory
    for name in list(sys.modules):
        if name.split(".")[0] == "autocheck_optional_app":
            del sys.modules[name]


def test_existing_module_is_returned() -> None:
    module = import_optional_module("tests.exampleapp.forms")
    assert module is sys.modules["tests.exampleapp.forms"]


def test_missing_module_returns_none(package_dir) -> None:
    assert import_optional_module("autocheck_optional_app.forms") is None


def test_missing_parent_package_returns_none(package_dir) -> None:
    assert import_optional_module("autocheck_optional_app.api.serializers") is None


def test_missing_top_level_package_returns_none() -> None:
    assert import_optional_module("nope.does.not.exist") is None


def test_module_importing_a_missing_dependency_raises(package_dir) -> None:
    (package_dir / "forms.py").write_text(
        "import autocheck_dependency_that_does_not_exist\n", encoding="utf-8"
    )
    with pytest.raises(ModuleNotFoundError, match="autocheck_dependency"):
        import_optional_module("autocheck_optional_app.forms")


def test_module_importing_a_missing_name_raises(package_dir) -> None:
    (package_dir / "forms.py").write_text(
        "from django.forms import NoSuchFormClass\n", encoding="utf-8"
    )
    with pytest.raises(ImportError, match="NoSuchFormClass"):
        import_optional_module("autocheck_optional_app.forms")
