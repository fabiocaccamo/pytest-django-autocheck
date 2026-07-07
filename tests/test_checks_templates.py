"""Tests for the templates check."""

import os
import types

from django.template import TemplateSyntaxError, engines

from pytest_django_autocheck.checks import templates as templates_module
from pytest_django_autocheck.checks.templates import TemplatesCheck


def test_check_metadata() -> None:
    check = TemplatesCheck()
    assert check.name == "templates"
    assert check.severity == "ERROR"


def test_clean_project_has_no_findings() -> None:
    check = TemplatesCheck()
    assert check.run(None) == []


def test_project_template_is_discovered() -> None:
    check = TemplatesCheck()
    names = [name for _backend, name in check._iter_templates()]
    assert "exampleapp/valid.html" in names


def test_syntax_error_is_reported() -> None:
    class BoomBackend:
        def get_template(self, name):
            raise TemplateSyntaxError("Invalid block tag")

    check = TemplatesCheck()
    findings = check._check_template(BoomBackend(), "broken.html")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "broken.html"
    assert "Invalid block tag" in findings[0].message


def test_valid_template_compiles() -> None:
    backend = next(
        engine for engine in engines.all() if hasattr(engine, "get_template")
    )
    check = TemplatesCheck()
    assert check._check_template(backend, "exampleapp/valid.html") == []


def test_binary_file_is_skipped() -> None:
    class BinaryBackend:
        def get_template(self, name):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    check = TemplatesCheck()
    assert check._check_template(BinaryBackend(), "favicon.ico") == []


def test_non_django_backend_is_skipped(monkeypatch) -> None:
    monkeypatch.setattr(templates_module.engines, "all", lambda: [object()])
    check = TemplatesCheck()
    assert list(check._iter_templates()) == []


def test_external_dir_is_not_a_project_dir() -> None:
    external = os.path.join(
        templates_module.external_prefixes()[0], "somepkg", "templates"
    )
    assert TemplatesCheck._is_project_dir(external) is False


def test_own_package_dir_is_not_a_project_dir() -> None:
    own = templates_module.own_package_dir()
    assert TemplatesCheck._is_project_dir(own) is False


def test_loader_dirs_recurses_into_cached_loaders() -> None:
    class Leaf:
        def get_dirs(self):
            return ["/tmp/templates"]

    class Cached:
        loaders = [Leaf()]

    check = TemplatesCheck()
    assert check._loader_dirs([Cached(), object()]) == ["/tmp/templates"]


def test_iter_templates_deduplicates_names(monkeypatch, tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "dup.html").write_text("<p>1</p>")
    (second / "dup.html").write_text("<p>2</p>")

    check = TemplatesCheck()
    monkeypatch.setattr(
        check, "_project_dirs", lambda engine: [str(first), str(second)]
    )
    names = [name for _backend, name in check._iter_templates()]
    assert names.count("dup.html") == 1


def test_project_dirs_deduplicates_directories(monkeypatch, tmp_path) -> None:
    directory = tmp_path / "templates"
    directory.mkdir()

    check = TemplatesCheck()
    monkeypatch.setattr(
        check, "_loader_dirs", lambda loaders: [str(directory), str(directory)]
    )
    monkeypatch.setattr(
        TemplatesCheck, "_is_project_dir", staticmethod(lambda real: True)
    )
    engine = types.SimpleNamespace(template_loaders=[])
    assert check._project_dirs(engine) == [str(directory)]


def test_walk_dir_skips_pycache(tmp_path) -> None:
    (tmp_path / "ok.html").write_text("<p>ok</p>")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.html").write_text("<p>nested</p>")
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "junk.html").write_text("<p>junk</p>")

    names = list(TemplatesCheck._walk_dir(str(tmp_path)))
    assert "ok.html" in names
    assert "sub/nested.html" in names
    assert all("__pycache__" not in name for name in names)
