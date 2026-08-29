"""Shared HTTP helpers for checks that drive the Django test client."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from django.http import HttpResponse


def same_path_redirect(response: HttpResponse, path: str) -> str | None:
    """Return the Location of a redirect that points back at *path* itself.

    A redirect whose target has the same path and no query string (only the
    scheme or host changes, e.g. an SSL or www redirect) means the view was
    never executed: callers report it instead of silently treating the
    response as healthy. Returns ``None`` for non-redirect responses and for
    redirects to a different path or with a query string (e.g. a login page
    or a ``?next=`` bounce), which are decisions the view itself made.
    """
    if not 300 <= response.status_code < 400:
        return None
    location = response.headers.get("Location", "")
    parts = urlsplit(location)
    return location if parts.path == path and not parts.query else None
