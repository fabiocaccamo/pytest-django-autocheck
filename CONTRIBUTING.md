# Contributing

Thank you for considering contributing to `pytest-django-autocheck`!

## Reporting bugs

Please open a [GitHub issue](https://github.com/fabiocaccamo/pytest-django-autocheck/issues) with:
- A minimal reproducible example.
- The Python, Django and `pytest-django-autocheck` versions you are using.
- The expected vs. actual behaviour.

Since the plugin runs against your own project, the full output of
`pytest --autocheck` (with the failing check isolated via `--autocheck-only`)
is usually the most useful thing to include.

> [!WARNING]
> If the bug is a security vulnerability, please **do not** open a public issue. Follow the [Security Policy](SECURITY.md) instead.

## Suggesting features

Open a [GitHub issue](https://github.com/fabiocaccamo/pytest-django-autocheck/issues) labelled `enhancement` describing your use case and the proposed API.

## How to contribute

1. **Fork** the repository and create your branch from `main`.
2. **Make your changes**: add tests that cover any new behaviour or bug fix. Coverage is enforced at 100%, so every new line must be exercised. Measure it with `coverage run -m pytest` rather than `pytest --cov`: the package is itself a pytest plugin, imported at startup before `pytest-cov` would start measuring, so `coverage run` is needed to capture import-time lines.
3. **Run the test suite**: see the [Testing](README.md#testing) section for full details.
4. **Open a Pull Request** against `main` with a clear description of what you changed and why, and reference the related issue.

## Code style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting,
[Black](https://black.readthedocs.io/) for formatting and
[isort](https://pycqa.github.io/isort/) for import sorting. All checks are
enforced via [pre-commit](https://pre-commit.com/) hooks:

```bash
pre-commit install
pre-commit run --all-files
```

## License

By contributing you agree that your contributions will be licensed under the [MIT License](LICENSE).
