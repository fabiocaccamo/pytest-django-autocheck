"""Check: admin configuration and views are healthy.

For every model of a *project* app registered on the admin site the check runs
in two layers:

1. attribute validation, isolated from any HTTP request: the per-request
   getters (``get_list_display``, ``get_list_filter``, ``get_search_fields``,
   ``get_ordering``) and ``get_urls()`` are called directly, so a broken
   configuration yields a finding that points at the exact attribute instead of
   a generic 500;
2. view rendering: the changelist, add and change views are requested with a
   logged-in superuser. The change view requires a real instance, provided by
   the shared generator (the same mechanism used by the models check). Any
   404/500 response or raised exception is reported.

The check is generic: the superuser is built with the project's own user model
through the shared generator, admin URLs are resolved by reverse(), and no
assumption is made about the project under inspection. The admin site is
injectable for testability and defaults to ``django.contrib.admin.site``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client, RequestFactory
from django.urls import NoReverseMatch, reverse

from pytest_django_autocheck.checks.shared.builders import make_instance
from pytest_django_autocheck.checks.shared.scope import inspected_labels
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.apps.config import AppConfig
    from django.contrib.admin import AdminSite, ModelAdmin
    from django.db.models import Model
    from django.http import HttpRequest

_REQUEST_GETTERS = (
    "get_list_display",
    "get_list_filter",
    "get_search_fields",
    "get_ordering",
)


class AdminCheck(BaseCheck):
    name = "admin"
    severity = "ERROR"

    def __init__(self, site: AdminSite | None = None) -> None:
        self._site = site

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        site = self._site or admin.site
        if not site._registry:
            return []
        allowed = inspected_labels(app_configs)

        try:
            user = self._build_superuser()
            client = self._build_client(user)
            request = self._build_request(user)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "WARNING",
                    "admin",
                    "could not set up an admin superuser to exercise the "
                    "admin site, skipping "
                    f"({type(exc).__name__}: {exc}).",
                    exc,
                )
            ]

        findings: list[Finding] = []
        for model, admin_instance in site._registry.items():
            opts = model._meta
            if opts.app_label not in allowed:
                continue
            findings.extend(self._check_model(client, request, model, admin_instance))
        return findings

    @staticmethod
    def _build_superuser() -> Model:
        user = AdminCheck._promote_superuser(make_instance(get_user_model()))
        user.save()
        return user

    @staticmethod
    def _build_client(user: Model) -> Client:
        client = Client()
        client.force_login(user)
        return client

    @staticmethod
    def _build_request(user: Model) -> HttpRequest:
        request = RequestFactory().get("/")
        request.user = user
        return request

    @staticmethod
    def _promote_superuser(user: Model) -> Model:
        for attr in ("is_staff", "is_superuser", "is_active"):
            if hasattr(user, attr):
                setattr(user, attr, True)
        return user

    def _check_model(
        self,
        client: Client,
        request: HttpRequest,
        model: type[Model],
        admin_instance: ModelAdmin,
    ) -> list[Finding]:
        opts = model._meta
        target = f"{opts.app_label}.{model.__name__}"
        info = (opts.app_label, opts.model_name)

        findings: list[Finding] = []
        findings.extend(self._check_config(request, admin_instance, target))
        findings.extend(self._check_view(client, "changelist", info, [], target))
        findings.extend(self._check_view(client, "add", info, [], target))

        try:
            # Nested savepoint: a failed INSERT (e.g. a column missing
            # because of an unapplied migration) would otherwise abort the
            # whole transaction on PostgreSQL and cascade "you can't execute
            # queries until the end of the 'atomic' block" errors onto every
            # model checked after this one.
            with transaction.atomic():
                instance = make_instance(model)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            findings.append(
                Finding(
                    self.name,
                    "WARNING",
                    target,
                    "Could not create an instance to test the change view: " f"{exc}",
                    exc,
                )
            )
            return findings

        findings.extend(self._check_view(client, "change", info, [instance.pk], target))
        return findings

    def _check_config(
        self,
        request: HttpRequest,
        admin_instance: ModelAdmin,
        target: str,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for getter_name in _REQUEST_GETTERS:
            getter = getattr(admin_instance, getter_name, None)
            if getter is not None:
                findings.extend(self._call_admin(target, getter_name, getter, request))
        findings.extend(self._call_admin(target, "get_urls", admin_instance.get_urls))
        return findings

    def _call_admin(
        self,
        target: str,
        label: str,
        func: object,
        *args: object,
    ) -> list[Finding]:
        try:
            func(*args)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"admin {label} raised {type(exc).__name__}: {exc}",
                    exc,
                )
            ]
        return []

    def _check_view(
        self,
        client: Client,
        view: str,
        info: tuple[str, str],
        args: list[object],
        target: str,
    ) -> list[Finding]:
        app_label, model_name = info
        url_name = f"admin:{app_label}_{model_name}_{view}"
        try:
            url = reverse(url_name, args=args)
        except NoReverseMatch as exc:
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"admin {view} URL could not be reversed: {exc}",
                    exc,
                )
            ]

        try:
            # Nested savepoint: a view that dies on a broken query must not
            # poison the transaction for the views and models checked next.
            with transaction.atomic():
                response = client.get(url)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"admin {view} raised {type(exc).__name__}: {exc}",
                    exc,
                )
            ]

        if response.status_code == 404 or response.status_code >= 500:
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"admin {view} returned HTTP {response.status_code}.",
                )
            ]
        return []
