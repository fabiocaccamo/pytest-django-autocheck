"""Tests for the views check."""

import pytest
from django.urls import NoReverseMatch, get_resolver

from pytest_django_autocheck.checks import views as views_module
from pytest_django_autocheck.checks.views import ViewsCheck

pytestmark = pytest.mark.django_db


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeClient:
    def __init__(self, response: _FakeResponse | None = None) -> None:
        self._response = response

    def get(self, url):
        if self._response is None:
            raise ValueError("view exploded")
        return self._response


def test_check_metadata() -> None:
    check = ViewsCheck()
    assert check.name == "views"
    assert check.severity == "ERROR"


def test_clean_project_has_no_findings() -> None:
    check = ViewsCheck()
    assert check.run(None) == []


def test_iter_names_collects_named_patterns() -> None:
    check = ViewsCheck()
    names = set(check._iter_names(get_resolver()))
    assert "ok" in names
    assert "ok-cbv" in names


def test_iter_names_skips_the_admin_namespace() -> None:
    check = ViewsCheck()
    names = set(check._iter_names(get_resolver()))
    assert not any(name.startswith("admin:") for name in names)


def test_iter_names_prefixes_nested_namespaces() -> None:
    def project_view(request):  # pragma: no cover - never called
        return None

    class Pattern:
        name = "detail"
        callback = staticmethod(project_view)

    class Child(views_module.URLResolver):
        def __init__(self) -> None:
            self.namespace = "shop"

        @property
        def url_patterns(self):
            return [Pattern()]

    class Root(views_module.URLResolver):
        def __init__(self) -> None:
            self.namespace = None

        @property
        def url_patterns(self):
            return [Child()]

    check = ViewsCheck()
    assert list(check._iter_names(Root())) == ["shop:detail"]


def test_iter_names_is_silent_on_broken_resolver() -> None:
    class Broken:
        @property
        def url_patterns(self):
            raise ImportError("bad include")

    check = ViewsCheck()
    assert list(check._iter_names(Broken())) == []


def test_unnamed_patterns_are_skipped() -> None:
    class Pattern:
        name = None

    class Root:
        namespace = None
        url_patterns = [Pattern()]

    check = ViewsCheck()
    assert list(check._iter_names(Root())) == []


class _CallbackPattern:
    def __init__(self, callback) -> None:
        self.callback = callback
        self.name = "target"


def test_is_project_view_true_for_project_fbv() -> None:
    def view(request):  # pragma: no cover - never called
        return None

    assert ViewsCheck._is_project_view(_CallbackPattern(view)) is True


def test_is_project_view_true_for_project_cbv() -> None:
    from tests.urls import _OkView

    pattern = _CallbackPattern(_OkView.as_view())
    assert ViewsCheck._is_project_view(pattern) is True


def test_is_project_view_false_for_third_party_cbv() -> None:
    from django.views.generic import TemplateView

    pattern = _CallbackPattern(TemplateView.as_view(template_name="x.html"))
    assert ViewsCheck._is_project_view(pattern) is False


def test_is_project_view_false_for_third_party_fbv() -> None:
    from django.contrib.auth.views import LoginView

    pattern = _CallbackPattern(LoginView.as_view())
    assert ViewsCheck._is_project_view(pattern) is False


def test_is_project_view_unwraps_decorated_project_view() -> None:
    import functools

    def view(request):  # pragma: no cover - never called
        return None

    @functools.wraps(view)
    def wrapper(request):  # pragma: no cover - never called
        return view(request)

    assert ViewsCheck._is_project_view(_CallbackPattern(wrapper)) is True


def test_is_project_view_true_when_module_file_is_unknown() -> None:
    # ``len`` resolves to the ``builtins`` module, which has no ``__file__``:
    # the check must conservatively treat the view as part of the project.
    assert ViewsCheck._is_project_view(_CallbackPattern(len)) is True


def test_is_project_view_false_for_own_package_view() -> None:
    # A callable defined inside this package (e.g. when vendored) must be
    # excluded even though it does not live under site-packages.
    pattern = _CallbackPattern(views_module.ViewsCheck.run)
    assert ViewsCheck._is_project_view(pattern) is False


def test_is_project_view_false_when_callback_is_broken() -> None:
    class BrokenPattern:
        name = "broken"

        @property
        def callback(self):
            raise ImportError("bad dotted path")

    assert ViewsCheck._is_project_view(BrokenPattern()) is False


def test_iter_names_skips_third_party_views() -> None:
    from django.views.generic import TemplateView

    class Root:
        namespace = None
        url_patterns = [_CallbackPattern(TemplateView.as_view(template_name="x.html"))]

    check = ViewsCheck()
    assert list(check._iter_names(Root())) == []


def test_reverse_failure_is_ignored(monkeypatch) -> None:
    def boom(name):
        raise NoReverseMatch("needs args")

    monkeypatch.setattr(views_module, "reverse", boom)
    check = ViewsCheck()
    assert check._check_view(_FakeClient(), "needs-args", set()) == []


def test_duplicate_urls_are_requested_once(monkeypatch) -> None:
    monkeypatch.setattr(views_module, "reverse", lambda name: "/same/")
    check = ViewsCheck()
    client = _FakeClient(_FakeResponse(200))
    seen: set[str] = set()
    assert check._check_view(client, "first", seen) == []
    assert check._check_view(client, "alias", seen) == []
    assert seen == {"/same/"}


def test_view_exception_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(views_module, "reverse", lambda name: "/boom/")
    check = ViewsCheck()
    findings = check._check_view(_FakeClient(), "boom", set())
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "boom"
    assert "view exploded" in findings[0].message


def test_server_error_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(views_module, "reverse", lambda name: "/broken/")
    check = ViewsCheck()
    findings = check._check_view(_FakeClient(_FakeResponse(500)), "broken", set())
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "HTTP 500" in findings[0].message


@pytest.mark.parametrize("status_code", [200, 302, 403, 404])
def test_non_server_errors_are_ignored(monkeypatch, status_code) -> None:
    monkeypatch.setattr(views_module, "reverse", lambda name: "/any/")
    check = ViewsCheck()
    client = _FakeClient(_FakeResponse(status_code))
    assert check._check_view(client, "any", set()) == []
