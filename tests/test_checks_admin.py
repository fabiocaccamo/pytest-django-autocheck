"""Tests for the admin check (PoC 4.3)."""

import types

import pytest
from django.apps import apps
from django.contrib import admin
from django.contrib.admin import site
from django.test import Client

from pytest_django_autocheck.checks import admin as admin_module
from pytest_django_autocheck.checks.admin import AdminCheck
from tests.exampleapp.models import Author

pytestmark = pytest.mark.django_db


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def test_check_metadata() -> None:
    check = AdminCheck()
    assert check.name == "admin"
    assert check.severity == "ERROR"


def test_registered_admins_render() -> None:
    check = AdminCheck()
    findings = check.run(_exampleapp())
    assert findings == []


def test_run_on_whole_project_has_no_errors() -> None:
    check = AdminCheck()
    findings = check.run(None)
    assert [f for f in findings if f.severity == "ERROR"] == []


def test_run_skips_when_no_models_registered() -> None:
    from django.contrib.admin import AdminSite

    check = AdminCheck(site=AdminSite())
    assert check.run(None) == []


def test_run_skips_admins_for_third_party_models() -> None:
    from django.contrib.admin import AdminSite
    from django.contrib.auth.models import Group

    class BrokenAdmin(admin.ModelAdmin):
        def get_list_display(self, request):
            raise AssertionError("third-party admin must not be inspected")

    site = AdminSite()
    site.register(Group, BrokenAdmin)
    check = AdminCheck(site=site)
    assert check.run(None) == []


def test_run_skips_admins_for_test_support_models(monkeypatch) -> None:
    from django.contrib.admin import AdminSite

    class BrokenAdmin(admin.ModelAdmin):
        def get_list_display(self, request):
            raise AssertionError("test-support admin must not be inspected")

    monkeypatch.setattr(Author, "__module__", "tests.exampleapp.tests.models")
    site = AdminSite()
    site.register(Author, BrokenAdmin)
    check = AdminCheck(site=site)
    assert check.run(None) == []


def test_run_warns_when_superuser_setup_fails(monkeypatch) -> None:
    check = AdminCheck()

    def boom() -> None:
        raise RuntimeError("no user model")

    monkeypatch.setattr(check, "_build_superuser", boom)
    findings = check.run(None)
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert findings[0].target == "admin"
    assert "no user model" in findings[0].message


def test_promote_superuser_sets_only_existing_attrs() -> None:
    user = types.SimpleNamespace(is_staff=False)
    AdminCheck._promote_superuser(user)
    assert user.is_staff is True
    assert not hasattr(user, "is_superuser")


def test_check_view_reports_unreversible_url() -> None:
    check = AdminCheck()
    findings = check._check_view(
        Client(), "changelist", ("nope", "missing"), [], "nope.Missing"
    )
    assert findings[0].severity == "ERROR"
    assert "could not be reversed" in findings[0].message


def test_check_view_reports_server_error_status() -> None:
    check = AdminCheck()
    fake_client = types.SimpleNamespace(
        get=lambda url, **kwargs: types.SimpleNamespace(status_code=500)
    )
    findings = check._check_view(
        fake_client, "changelist", ("exampleapp", "author"), [], "exampleapp.Author"
    )
    assert findings[0].severity == "ERROR"
    assert "HTTP 500" in findings[0].message


def test_check_view_reports_raised_exception() -> None:
    def boom(url, **kwargs):
        raise RuntimeError("render exploded")

    check = AdminCheck()
    fake_client = types.SimpleNamespace(get=boom)
    findings = check._check_view(
        fake_client, "changelist", ("exampleapp", "author"), [], "exampleapp.Author"
    )
    assert findings[0].severity == "ERROR"
    assert "render exploded" in findings[0].message


def test_check_view_requests_over_https() -> None:
    calls: dict[str, object] = {}

    def get(url, secure=False):
        calls["secure"] = secure
        return types.SimpleNamespace(status_code=200, headers={})

    check = AdminCheck()
    fake_client = types.SimpleNamespace(get=get)
    findings = check._check_view(
        fake_client, "changelist", ("exampleapp", "author"), [], "exampleapp.Author"
    )
    assert findings == []
    assert calls["secure"] is True


def test_check_view_warns_on_same_path_redirect() -> None:
    def get(url, **kwargs):
        return types.SimpleNamespace(
            status_code=301, headers={"Location": f"https://www.testserver{url}"}
        )

    check = AdminCheck()
    fake_client = types.SimpleNamespace(get=get)
    findings = check._check_view(
        fake_client, "changelist", ("exampleapp", "author"), [], "exampleapp.Author"
    )
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert "never exercised" in findings[0].message


def test_run_survives_ssl_redirect_settings(settings) -> None:
    """With SECURE_SSL_REDIRECT on, admin views must still be exercised."""
    settings.MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        *settings.MIDDLEWARE,
    ]
    settings.SECURE_SSL_REDIRECT = True
    check = AdminCheck()
    assert check.run(_exampleapp()) == []


def test_change_view_instance_failure_is_warning(monkeypatch) -> None:
    check = AdminCheck()
    user = check._build_superuser()
    client = check._build_client(user)
    request = check._build_request(user)

    def boom(model):
        raise ValueError("no instance")

    monkeypatch.setattr(admin_module, "make_instance", boom)
    findings = check._check_model(client, request, Author, site._registry[Author])
    warnings = [f for f in findings if f.severity == "WARNING"]
    assert warnings
    assert "no instance" in warnings[0].message


def test_change_view_instance_failure_rolls_back_partial_writes(
    monkeypatch,
) -> None:
    """A failing generation must not leak writes nor poison the transaction.

    The instance creation runs in a savepoint so that, on PostgreSQL, a
    failed INSERT cannot abort the transaction and cascade errors onto every
    model checked after this one.
    """
    check = AdminCheck()
    user = check._build_superuser()
    client = check._build_client(user)
    request = check._build_request(user)

    def partial_write_then_boom(model):
        Author.objects.create(name="leaked")
        raise ValueError("boom after write")

    monkeypatch.setattr(admin_module, "make_instance", partial_write_then_boom)
    findings = check._check_model(client, request, Author, site._registry[Author])
    assert [f for f in findings if f.severity == "WARNING"]
    assert Author.objects.filter(name="leaked").exists() is False


def test_check_config_reports_broken_getter() -> None:
    class BrokenAdmin:
        def get_list_display(self, request):
            raise ValueError("broken list_display")

        def get_urls(self):
            return []

    check = AdminCheck()
    findings = check._check_config(object(), BrokenAdmin(), "app.Model")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "get_list_display" in findings[0].message
    assert "broken list_display" in findings[0].message


def test_check_config_reports_broken_get_urls() -> None:
    class BrokenAdmin:
        def get_urls(self):
            raise RuntimeError("broken urls")

    check = AdminCheck()
    findings = check._check_config(object(), BrokenAdmin(), "app.Model")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "get_urls" in findings[0].message


def test_check_config_clean_admin_has_no_findings() -> None:
    class CleanAdmin:
        def get_list_display(self, request):
            return ("id",)

        def get_urls(self):
            return []

    check = AdminCheck()
    assert check._check_config(object(), CleanAdmin(), "app.Model") == []
