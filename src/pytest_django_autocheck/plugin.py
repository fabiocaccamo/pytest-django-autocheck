"""pytest entry point.

The plugin is zero-config: ``pip install`` then ``pytest --autocheck`` is all
that is needed. When ``DJANGO_SETTINGS_MODULE`` is not configured (no env var,
no ``--ds`` and no ini option), the plugin discovers it from the project's
``manage.py`` the same way ``manage.py`` itself does, and sets it before
pytest-django reads it. pytest-django then handles ``django.setup()``
and the test database. The single entry point is the ``--autocheck`` flag
(implied by ``--autocheck-only`` and ``--autocheck-skip``): when set, one
synthetic test item per registered check is collected so findings flow into
the standard pytest report (``ERROR`` findings fail the run,
``WARNING``/``INFO`` are shown alongside).
"""

from __future__ import annotations

import os
import re
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.core.exceptions import ImproperlyConfigured

from pytest_django_autocheck.output.text import format_text
from pytest_django_autocheck.runner import UnknownCheckError, get_checks

if TYPE_CHECKING:
    from pytest_django_autocheck.registry import Check


class AutocheckWarning(UserWarning):
    """Warning emitted for non-error autocheck findings (WARNING/INFO)."""


_SETTINGS_ENV = "DJANGO_SETTINGS_MODULE"
_SETTINGS_RE = re.compile(r"""DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([\w.]+)['"]""")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("django-autocheck", "Django autocheck options")
    group.addoption(
        "--autocheck",
        action="store_true",
        default=False,
        dest="autocheck",
        help="Run the pytest-django-autocheck generic Django checks.",
    )
    group.addoption(
        "--autocheck-only",
        action="append",
        default=[],
        dest="autocheck_only",
        metavar="CHECK",
        help=(
            "Run only the named check(s), e.g. --autocheck-only=admin "
            "(implies --autocheck)."
        ),
    )
    group.addoption(
        "--autocheck-skip",
        action="append",
        default=[],
        dest="autocheck_skip",
        metavar="CHECK",
        help=(
            "Skip the named check(s), e.g. --autocheck-skip=templates "
            "(implies --autocheck)."
        ),
    )


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(
    early_config: pytest.Config,
    parser: pytest.Parser,
    args: list[str],
) -> None:
    if not any(arg.startswith("--autocheck") for arg in args):
        return
    if _settings_already_configured(early_config, args):
        return
    _autodiscover_settings(args)


def _settings_already_configured(
    early_config: pytest.Config,
    args: list[str],
) -> bool:
    if os.environ.get(_SETTINGS_ENV):
        return True
    if any(arg == "--ds" or arg.startswith("--ds=") for arg in args):
        return True
    try:
        return bool(early_config.getini(_SETTINGS_ENV))
    except (ValueError, KeyError):
        return False


def _autodiscover_settings(args: list[str]) -> None:
    manage_py = _find_manage_py(args)
    if manage_py is None:
        return
    settings_module = _read_settings_module(manage_py)
    if settings_module is None:
        return
    project_dir = str(manage_py.parent)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    os.environ[_SETTINGS_ENV] = settings_module


def _find_manage_py(args: list[str]) -> Path | None:
    candidates = [
        Path(arg.split("::", 1)[0]).resolve() for arg in args if not arg.startswith("-")
    ]
    candidates.append(Path.cwd())
    for candidate in candidates:
        for directory in (candidate, *candidate.parents):
            manage = directory / "manage.py"
            if manage.is_file():
                return manage
    return None


def _read_settings_module(manage_py: Path) -> str | None:
    try:
        content = manage_py.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _SETTINGS_RE.search(content)
    return match.group(1) if match else None


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "autocheck: mark a test as part of the Django autocheck suite.",
    )
    # Non-error findings are reported as AutocheckWarning; without this filter
    # a project running with ``filterwarnings = ["error"]`` would turn every
    # WARNING/INFO finding into a failure, inverting the severity contract.
    config.addinivalue_line(
        "filterwarnings",
        "always::pytest_django_autocheck.plugin.AutocheckWarning",
    )


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if not _is_autocheck_requested(config):
        return
    only = config.option.autocheck_only or None
    skip = config.option.autocheck_skip or None
    try:
        checks = get_checks(only, skip)
    except (UnknownCheckError, ImproperlyConfigured) as error:
        # A mistyped check name or missing Django settings are usage errors:
        # report the message alone instead of an internal error traceback.
        raise pytest.UsageError(str(error)) from error
    items.extend(_build_item(session, check) for check in checks)


def _is_autocheck_requested(config: pytest.Config) -> bool:
    """Return whether the checks must run.

    Selecting or skipping checks implies running them: ignoring
    ``--autocheck-only=admin`` because ``--autocheck`` was left out would run
    nothing and still exit green.
    """
    option = config.option
    return bool(option.autocheck or option.autocheck_only or option.autocheck_skip)


def _build_item(session: pytest.Session, check: Check) -> pytest.Function:
    item = pytest.Function.from_parent(
        session,
        name=f"autocheck[{check.name}]",
        callobj=_make_callobj(check),
    )
    # The marker makes the synthetic items selectable with -m autocheck (and
    # excludable with -m "not autocheck").
    item.add_marker("autocheck")
    return item


def _make_callobj(check: Check):
    """Build the item body, requesting the db fixture only when needed.

    Checks that never touch the database declare ``requires_db = False``, so
    running only those never creates the test database.
    """
    if getattr(check, "requires_db", True):

        def autocheck(db) -> None:
            _run_check_item(check)

    else:

        def autocheck() -> None:  # type: ignore[misc]
            _run_check_item(check)

    autocheck.__name__ = f"autocheck_{check.name}"
    return autocheck


def _run_check_item(check: Check) -> None:
    findings = check.run(None)
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    non_errors = [finding for finding in findings if finding.severity != "ERROR"]
    if non_errors:
        warnings.warn(format_text(non_errors), AutocheckWarning, stacklevel=2)
    if errors:
        # Non-error findings were already emitted as warnings above.
        pytest.fail(format_text(errors), pytrace=False)
