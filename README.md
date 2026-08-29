# pytest-django-autocheck

[![](https://img.shields.io/pypi/pyversions/pytest-django-autocheck.svg?color=blue&logo=python&logoColor=white)](https://www.python.org/)
[![](https://img.shields.io/pypi/djversions/pytest-django-autocheck?color=0C4B33&logo=django&logoColor=white&label=django)](https://www.djangoproject.com/)
[![](https://img.shields.io/pypi/v/pytest-django-autocheck.svg?color=blue&logo=pypi&logoColor=white)](https://pypi.org/project/pytest-django-autocheck/)
[![](https://static.pepy.tech/badge/pytest-django-autocheck/month)](https://pepy.tech/project/pytest-django-autocheck)
[![](https://img.shields.io/github/stars/fabiocaccamo/pytest-django-autocheck?logo=github&style=flat)](https://github.com/fabiocaccamo/pytest-django-autocheck/stargazers)
[![](https://img.shields.io/pypi/l/pytest-django-autocheck.svg?color=blue)](https://github.com/fabiocaccamo/pytest-django-autocheck/blob/main/LICENSE)

[![](https://results.pre-commit.ci/badge/github/fabiocaccamo/pytest-django-autocheck/main.svg)](https://results.pre-commit.ci/latest/github/fabiocaccamo/pytest-django-autocheck/main)
[![](https://img.shields.io/github/actions/workflow/status/fabiocaccamo/pytest-django-autocheck/test-package.yml?branch=main&label=build&logo=github)](https://github.com/fabiocaccamo/pytest-django-autocheck)
[![](https://img.shields.io/codecov/c/gh/fabiocaccamo/pytest-django-autocheck?logo=codecov)](https://codecov.io/gh/fabiocaccamo/pytest-django-autocheck)
[![](https://img.shields.io/badge/code%20style-black-000000.svg?logo=python&logoColor=black)](https://github.com/psf/black)
[![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocaccamo/pytest-django-autocheck/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocaccamo/pytest-django-autocheck)

Zero-config [pytest](https://docs.pytest.org/) plugin that runs generic safety checks on any Django project. .

Pulls in [pytest-django](https://pytest-django.readthedocs.io/) automatically
and discovers Django settings from your `manage.py`. Install and run:

```bash
pip install pytest-django-autocheck
pytest --autocheck
```

## Why

Legacy or untested Django projects rarely have any safety net. This plugin
catches the basics in CI before they reach production:

- modules that fail to import
- migrations that don't reverse, or are missing entirely
- models that can't be saved or stringified
- admin pages that return 500/404
- broken URLconfs
- public pages that return 500
- template syntax errors
- management commands that fail to load
- forms and serializers that can't be instantiated
- Django system check failures

## Requirements

- Python 3.10+
- Django 5.0+

## Installation

```bash
pip install pytest-django-autocheck
```

## Usage

From your project root (where `manage.py` lives):

```bash
pytest --autocheck
```

The plugin discovers `DJANGO_SETTINGS_MODULE` from `manage.py`. If you already
declare it explicitly (in `pytest.ini`/`pyproject.toml`, via `--ds`, or as an
environment variable), that value wins and auto-discovery is skipped.

Run only specific checks by repeating `--autocheck-only`:

```bash
# a single check
pytest --autocheck --autocheck-only=admin

# multiple checks
pytest --autocheck --autocheck-only=admin --autocheck-only=models
```

Or skip specific checks with `--autocheck-skip`:

```bash
pytest --autocheck --autocheck-skip=templates --autocheck-skip=serializers
```

Both flags can be combined; `--autocheck-skip` is applied after
`--autocheck-only`, so a check named in both ends up skipped.

Valid check names for both flags: `admin`, `forms`, `imports`,
`management_commands`, `migrations`, `models`, `serializers`, `system_checks`,
`templates`, `urls`, `views`.

## Checks

| Check | Description |
|-------|-------------|
| `admin` | Every admin registered for a *project* model validates its configuration and renders its changelist and changeform without 500/404. Admins for third-party models and for models defined inside a `tests` package are skipped. |
| `forms` | Every `ModelForm` defined in a project app's `forms` module instantiates without raising. |
| `imports` | Every module of every project app imports without `ImportError` or circular import (third-party pip apps are skipped). |
| `management_commands` | Every management command defined by a project app loads its class and builds its argument parser without raising. |
| `migrations` | Detects model changes not captured by a migration, statically inspects every *project* migration for irreversible operations and silent noop-reverse migrations, then dynamically verifies the whole graph by applying it forward, reversing to zero, and re-applying forward on a throwaway database. Third-party and `django.contrib` migrations are skipped: a dependency's irreversible data migration won't fail your build. |
| `models` | Every *project* model is instantiable, savable, and stringifiable via both `str()` and `repr()`. Third-party and `django.contrib` models are skipped, as are test-support models defined inside a `tests` package (a top-level `tests/` or an app-level `{app}/tests/`). |
| `serializers` | Every Django REST Framework serializer defined in a project app (`<app>.serializers` or `<app>.api.serializers`) binds its fields without raising. Skipped entirely when `djangorestframework` isn't installed. |
| `system_checks` | Runs Django's own system check framework (`django.core.checks`) and reports every error, warning and info message it raises. |
| `templates` | Every template under the project's own template directories compiles without a `TemplateSyntaxError`. |
| `urls` | Every URL pattern loads its included URLconf, resolves its callback, and reverses without raising (other than `NoReverseMatch`). |
| `views` | Every named URL that reverses without arguments and whose view is owned by a *project* app is requested with `GET` by an unauthenticated client; a raised exception or an HTTP 5xx response is reported. Anything below 500 (redirects, 403, 404) is a legitimate answer for an anonymous client and is ignored. Views shipped by third-party packages are skipped (ownership is resolved from the view callback's module, for both function-based and class-based views), and the `admin` namespace is skipped because the `admin` check already exercises it with a superuser. |

### Settings

Every option is read from Django settings under the
`PYTEST_DJANGO_AUTOCHECK_` prefix, with a safe default: override only what
you need.

| Setting | Default | Effect |
|---------|---------|--------|
| `PYTEST_DJANGO_AUTOCHECK_CHECKS` | `None` | List of check names to run, e.g. `["imports", "migrations"]`. When unset, every registered check runs. `--autocheck-only`, when given, takes precedence. |
| `PYTEST_DJANGO_AUTOCHECK_SKIP` | `None` | List of check names to exclude, e.g. `["templates", "serializers"]`. Applied after `CHECKS`/`--autocheck-only`. `--autocheck-skip`, when given, takes precedence. |
| `PYTEST_DJANGO_AUTOCHECK_MIGRATIONS_PROBE_TIMEOUT` | `300` | Max seconds the dynamic migration probe subprocess may run before it's aborted; on timeout the dynamic step is skipped with a `WARNING` and the run doesn't fail. The probe self-aborts at this deadline and destroys its throwaway database. |
| `PYTEST_DJANGO_AUTOCHECK_MODELS_EXCLUDE` | `[]` | List of `"app_label.ModelName"` labels (case-insensitive) excluded from instance building: the `models` check skips them entirely and the `admin` check skips their change view (attribute validation, changelist and add views still run). Escape hatch for models whose domain constraints can never be satisfied by generated data (e.g. a `clean()` that requires specific related rows, or a CHECK constraint between correlated fields). Every exclusion is reported as `INFO`, so it never disappears silently. |
| `PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES` | `{}` | Dict mapping `"app_label.ModelName"` labels (case-insensitive) to the dotted path of a zero-argument callable returning a *saved* instance, e.g. `{"billing.Plan": "billing.testing.make_plan"}`. The callable replaces the generic generator for that model in the `models` and `admin` checks. A model listed here wins over `MODELS_EXCLUDE`: providing a factory means the model can be checked after all, so prefer this over excluding it. |
| `PYTEST_DJANGO_AUTOCHECK_DEPLOY` | `False` | When `True`, `system_checks` also runs Django's deployment checks (`DEBUG`, `SECRET_KEY`, SSL/HSTS, secure cookies). Off by default since those fail on dev/test settings; enable for a pre-production audit. |

The dynamic migration verification runs in a short-lived subprocess, isolated
from the suite's own test database. If that subprocess can't set up its
environment, the dynamic step is skipped with a warning rather than failing
the run.

### Instance generation

The `models` and `admin` checks need a valid instance of every model. The
generator prefers the project's own `factory_boy` factories when present
(looked up in `<app>.factories` or `<app>.tests.factories`): they already
encode domain rules, which avoids false positives. Falls back to
[model_bakery](https://model-bakery.readthedocs.io/) when no factory is found.
`factory_boy` is optional; discovery is a no-op if it's not installed.

When neither a factory nor generated data can satisfy a model's domain
constraints, point `PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES` at your own
callable to keep the model checked, or, as a last resort, list it in
`PYTEST_DJANGO_AUTOCHECK_MODELS_EXCLUDE` (see [Settings](#settings)) to
exclude it from instance building.

The `serializers` check requires
[Django REST Framework](https://www.django-rest-framework.org/) and is skipped
if it's not installed.

### Custom checks

Third-party packages can ship their own checks through the
`pytest_django_autocheck.checks` entry-point group. Each entry point must
resolve to a check class (instantiated with no arguments) or a check instance
exposing `name`, `severity` and `run(app_configs) -> list[Finding]`:

```toml
[project.entry-points."pytest_django_autocheck.checks"]
mycheck = "mypackage.checks:MyCheck"
```

Registered checks run like the built-in ones: they get their own pytest item,
their name works with `--autocheck-only`/`--autocheck-skip` and the `CHECKS`/
`SKIP` settings, and their `ERROR` findings fail the run.

## Testing

```bash
# clone repository
git clone https://github.com/fabiocaccamo/pytest-django-autocheck.git && cd pytest-django-autocheck

# create virtualenv and activate it
python -m venv .venv && . .venv/bin/activate

# upgrade pip
python -m pip install --upgrade pip

# install package and test requirements
python -m pip install -e ".[test]"

# install pre-commit to run formatters and linters
pre-commit install --install-hooks

# run tests using tox
tox

# or run tests using pytest
coverage run -m pytest && coverage report -m
```

## License

Released under [MIT License](LICENSE).

---

## Supporting

- :star: Star this project on [GitHub](https://github.com/fabiocaccamo/pytest-django-autocheck)
- :octocat: Follow me on [GitHub](https://github.com/fabiocaccamo)
- :blue_heart: Follow me on [Bluesky](https://bsky.app/profile/fabiocaccamo.bsky.social)
- :moneybag: Sponsor me on [Github](https://github.com/sponsors/fabiocaccamo)

## See also

- [`django-admin-interface`](https://github.com/fabiocaccamo/django-admin-interface) - the default admin interface made customizable by the admin itself. popup windows replaced by modals. 🧙 ⚡

- [`django-cache-cleaner`](https://github.com/fabiocaccamo/django-cache-cleaner) - clear the entire cache or individual caches easily using the admin panel or management command. 🧹✨

- [`django-colorfield`](https://github.com/fabiocaccamo/django-colorfield) - simple color field for models with a nice color-picker in the admin. 🎨

- [`django-email-validators`](https://github.com/fabiocaccamo/django-email-validators) - no more invalid or disposable emails in your database. ✉️ ✅

- [`django-extra-settings`](https://github.com/fabiocaccamo/django-extra-settings) - config and manage typed extra settings using just the django admin. ⚙️

- [`django-maintenance-mode`](https://github.com/fabiocaccamo/django-maintenance-mode) - shows a 503 error page when maintenance-mode is on. 🚧 🛠️

- [`django-redirects`](https://github.com/fabiocaccamo/django-redirects) - redirects with full control. ↪️

- [`django-treenode`](https://github.com/fabiocaccamo/django-treenode) - probably the best abstract model / admin for your tree based stuff. 🌳

- [`python-benedict`](https://github.com/fabiocaccamo/python-benedict) - dict subclass with keylist/keypath support, I/O shortcuts (base64, csv, json, pickle, plist, query-string, toml, xml, yaml) and many utilities. 📘

- [`python-codicefiscale`](https://github.com/fabiocaccamo/python-codicefiscale) - encode/decode Italian fiscal codes - codifica/decodifica del Codice Fiscale. 🇮🇹 💳

- [`python-fontbro`](https://github.com/fabiocaccamo/python-fontbro) - friendly font operations. 🧢

- [`python-fsutil`](https://github.com/fabiocaccamo/python-fsutil) - file-system utilities for lazy devs. 🧟‍♂️
