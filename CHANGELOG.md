# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
-   Always destroy the migration probe's throwaway database, also when a forward migration fails or times out (it used to leave one database behind per run).
-   Skip the dynamic migration check with a `WARNING` on projects configuring more than one database: only `default` can be isolated, so a data migration routed to another alias would have reached its real database.
-   Fix a false `ERROR` in the dynamic migration check on projects setting `TEST["MIGRATE"] = False`.
-   Remove the `runpy` `RuntimeWarning` from the dynamic migration findings.
-   Fix the `imports` check registering duplicate models for an app nested inside another installed app, which then failed the `models` check.
-   Import packages made of their `__init__.py` alone in the `imports` check.
-   Make `--autocheck-only` and `--autocheck-skip` imply `--autocheck`: given alone they were silently ignored.
-   Report unknown check names and missing Django settings as usage errors instead of an `INTERNALERROR`.
-   Report a `forms`/`serializers` module that fails to import instead of skipping it as if it were missing; a broken project `factories` module now raises instead of silently falling back to generated data.
-   Discover `factory_boy` factories in project apps only.
-   Support admin sites with a custom name in the `admin` check (the `admin` namespace was hardcoded).
-   Raise `ImproperlyConfigured` in the `admin` check when `MODELS_EXCLUDE` or `MODELS_FACTORIES` is misconfigured, instead of reporting a failed superuser setup.
-   Report any exception raised while compiling a template, per template, instead of aborting the `templates` check.
-   Reject a check registered under a name that is already taken, and raise a broken check entry point again on the next load instead of skipping it.
-   Emit a warning when no project app is detected, since the checks scoped to project apps would otherwise pass without inspecting anything.
-   Report the configured limit (not the padded one) when the migration probe times out.

## [0.3.0](https://github.com/fabiocaccamo/pytest-django-autocheck/releases/tag/0.3.0) - 2026-08-30
-   Classify a failure while creating the migration probe's throwaway database by its traceback: environment problems (e.g. the database user lacks the CREATEDB privilege) are now reported as `WARNING` instead of a false `ERROR`; broken migrations still fail the run.
-   Register an `always` filter for `AutocheckWarning` so projects running with `filterwarnings = ["error"]` no longer turn `WARNING`/`INFO` findings into failures.
-   Report any `admin` view redirect as `WARNING`: the client is logged in as a superuser, so a redirect (SSL/www rewrite or a bounce to the login page) means the view was never exercised.
-   Add the `autocheck` marker to the synthetic items and name them `autocheck[check]`, so they can be selected or excluded with `-m autocheck` / `-m "not autocheck"`.
-   Load third-party checks from the `pytest_django_autocheck.checks` entry-point group.
-   Validate the `MODELS_EXCLUDE` and `MODELS_FACTORIES` settings: wrong types and labels that match no installed model now raise `ImproperlyConfigured` instead of being silently ignored.
-   Prune hidden directories (`.venv`, `.git`, ...) and `node_modules` from the `imports` check walk.
-   Request the database fixture only for checks that need it: running only `imports`, `migrations`, `templates` or `urls` no longer creates the test database.
-   Ignore same-path redirects that add a query string in the `admin`/`views` checks: the view was exercised and chose to redirect.
-   Skip test-support models (models defined inside a `tests` package, either a top-level `tests/` or an app-level `{app}/tests/`) in the `models` and `admin` checks: they only exist to support the project's own test suite.
-   Add the `PYTEST_DJANGO_AUTOCHECK_MODELS_EXCLUDE` setting (list of `"app_label.ModelName"` labels, default `[]`): excluded models are skipped by the `models` check and by the change view of the `admin` check, each with an `INFO` finding. Escape hatch for models whose domain constraints can never be satisfied by generated data.
-   Add the `PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES` setting (dict of `"app_label.ModelName"` labels to dotted paths, default `{}`): the configured callable replaces the generic instance generator for that model in the `models` and `admin` checks and must return a saved instance. A model listed here wins over `MODELS_EXCLUDE`.
-   Identify the operation in the `migrations` reversibility findings by its index in the migration's `operations` list and, for `RunPython`, by the name of its forward callable: a migration with several `RunPython`/`RunSQL` operations no longer produces identical duplicate messages.
-   Run the CI test matrix against every supported `Python`/`Django` combination on `ubuntu`, `macos` and `windows` (previously only the latest `Django` release was tested).
-   Run the CI test matrix on `ubuntu` against both `sqlite` and `postgres` (`DATABASE_ENGINE` environment variable).
-   Add support for `Django 6.1`.

## [0.2.0](https://github.com/fabiocaccamo/pytest-django-autocheck/releases/tag/0.2.0) - 2026-08-29
-   Request admin and project views over simulated HTTPS (`secure=True`) so projects with `SECURE_SSL_REDIRECT` enabled no longer answer every GET with a 301 that silently skipped the `admin` and `views` checks.
-   Report a `WARNING` when a view responds with a redirect pointing back at the same path (only the scheme or host changes, e.g. `PREPEND_WWW` or a custom SSL middleware): the view was never actually exercised.
-   Bump GitHub actions.
-   Bump `pre-commit` hooks.

## [0.1.0](https://github.com/fabiocaccamo/pytest-django-autocheck/releases/tag/0.1.0) - 2026-07-08
-   Initial release.
