"""Tests for the urls check."""

from django.core.exceptions import ImproperlyConfigured
from django.urls import NoReverseMatch

from pytest_django_autocheck.checks import urls as urls_module
from pytest_django_autocheck.checks.urls import UrlsCheck


def test_check_metadata() -> None:
    check = UrlsCheck()
    assert check.name == "urls"
    assert check.severity == "ERROR"


def test_clean_project_has_no_errors() -> None:
    check = UrlsCheck()
    findings = check.run(None)
    assert [f for f in findings if f.severity == "ERROR"] == []


def test_broken_include_is_reported() -> None:
    class BoomResolver:
        urlconf_name = "broken.urls"

        @property
        def url_patterns(self):
            raise ImproperlyConfigured("bad include")

    check = UrlsCheck()
    findings = check._walk(BoomResolver())
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "broken.urls"
    assert "bad include" in findings[0].message


def test_unresolvable_view_is_reported() -> None:
    class BoomPattern:
        name = None
        pattern = "broken/"

        @property
        def callback(self):
            raise ImportError("no such view")

    check = UrlsCheck()
    findings = check._check_pattern(BoomPattern(), "")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "broken/"
    assert "no such view" in findings[0].message


def test_named_pattern_triggers_reverse(monkeypatch) -> None:
    class Pattern:
        name = "home"
        pattern = "home/"
        callback = staticmethod(lambda request: None)

    seen = {}
    monkeypatch.setattr(
        urls_module, "reverse", lambda name: seen.setdefault("name", name)
    )
    check = UrlsCheck()
    assert check._check_pattern(Pattern(), "shop:") == []
    assert seen["name"] == "shop:home"


def test_reverse_noreversematch_is_ignored(monkeypatch) -> None:
    def boom(name):
        raise NoReverseMatch("needs args")

    monkeypatch.setattr(urls_module, "reverse", boom)
    check = UrlsCheck()
    assert check._check_reverse("needs-args") == []


def test_reverse_other_exception_is_reported(monkeypatch) -> None:
    def boom(name):
        raise ValueError("broken reverse")

    monkeypatch.setattr(urls_module, "reverse", boom)
    check = UrlsCheck()
    findings = check._check_reverse("broken")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "broken reverse" in findings[0].message
