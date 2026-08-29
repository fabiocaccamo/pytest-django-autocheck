"""Tests for the shared project-app detection helpers."""

import os
import site
import types

from django.apps import apps
from django.test import override_settings

from pytest_django_autocheck.checks.shared import scope


def test_excluded_model_labels_defaults_to_empty_set() -> None:
    assert scope.excluded_model_labels() == set()


@override_settings(PYTEST_DJANGO_AUTOCHECK_MODELS_EXCLUDE=["Billing.Plan"])
def test_excluded_model_labels_lowercases_labels() -> None:
    assert scope.excluded_model_labels() == {"billing.plan"}


def _stub_model(module: str, app_name: str) -> type:
    class Stub:
        pass

    Stub.__module__ = module
    Stub._meta = types.SimpleNamespace(app_config=types.SimpleNamespace(name=app_name))
    return Stub


def test_is_test_support_model_app_level_tests_package() -> None:
    model = _stub_model("core.tests.models", "core")
    assert scope.is_test_support_model(model) is True


def test_is_test_support_model_top_level_tests_package() -> None:
    model = _stub_model("tests.models", "core")
    assert scope.is_test_support_model(model) is True


def test_is_test_support_model_false_for_regular_module() -> None:
    model = _stub_model("core.models", "core")
    assert scope.is_test_support_model(model) is False


def test_is_test_support_model_false_for_app_installed_under_tests() -> None:
    model = _stub_model("tests.exampleapp.models", "tests.exampleapp")
    assert scope.is_test_support_model(model) is False


def test_is_test_support_model_false_for_tests_prefix_only() -> None:
    model = _stub_model("core.testsuite.models", "core")
    assert scope.is_test_support_model(model) is False


def test_is_project_app_true_for_local_app() -> None:
    assert scope.is_project_app(apps.get_app_config("exampleapp")) is True


def test_is_project_app_false_for_site_packages_app() -> None:
    class FakeConfig:
        path = site.getsitepackages()[0] + "/somepkg"

    assert scope.is_project_app(FakeConfig()) is False


def test_is_project_app_false_when_path_missing() -> None:
    class FakeConfig:
        path = ""

    assert scope.is_project_app(FakeConfig()) is False


def test_is_project_app_false_for_own_package() -> None:
    class FakeConfig:
        path = scope.own_package_dir()

    assert scope.is_project_app(FakeConfig()) is False


def test_is_project_app_false_for_vendored_subdir() -> None:
    class FakeConfig:
        path = os.path.join(scope.own_package_dir(), "checks")

    assert scope.is_project_app(FakeConfig()) is False


def test_own_package_dir_points_at_package_root() -> None:
    expected = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.realpath(scope.__file__)))
    )
    assert scope.own_package_dir() == expected


def test_is_within_helper() -> None:
    parent = os.sep + "pkg"
    assert scope.is_within(parent, parent) is True
    assert scope.is_within(os.path.join(parent, "sub"), parent) is True
    assert scope.is_within(os.sep + "pkgother", parent) is False


def test_project_apps_defaults_to_project_apps() -> None:
    labels = {config.label for config in scope.project_apps(None)}
    assert "exampleapp" in labels
    assert "auth" not in labels


def test_project_apps_filters_explicit_configs() -> None:
    configs = [
        apps.get_app_config("exampleapp"),
        apps.get_app_config("auth"),
    ]
    assert [c.label for c in scope.project_apps(configs)] == ["exampleapp"]


def test_inspected_labels_defaults_to_project_apps() -> None:
    labels = scope.inspected_labels(None)
    assert "exampleapp" in labels
    assert "auth" not in labels
    assert "contenttypes" not in labels


def test_inspected_labels_uses_given_app_configs() -> None:
    config = apps.get_app_config("exampleapp")
    assert scope.inspected_labels([config]) == {config.label}
