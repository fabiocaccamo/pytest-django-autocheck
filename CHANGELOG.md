# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/fabiocaccamo/pytest-django-autocheck/releases/tag/0.2.0) - 2026-08-29
-   Request admin and project views over simulated HTTPS (`secure=True`) so projects with `SECURE_SSL_REDIRECT` enabled no longer answer every GET with a 301 that silently skipped the `admin` and `views` checks.
-   Report a `WARNING` when a view responds with a redirect pointing back at the same path (only the scheme or host changes, e.g. `PREPEND_WWW` or a custom SSL middleware): the view was never actually exercised.
-   Bump GitHub actions.
-   Bump `pre-commit` hooks.

## [0.1.0](https://github.com/fabiocaccamo/pytest-django-autocheck/releases/tag/0.1.0) - 2026-07-08
-   Initial release.
