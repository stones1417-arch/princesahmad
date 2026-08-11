from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.monitoring import record_response_status
from apps.roles.services.section_context import (
    get_effective_section,
    set_current_section,
)


class OperationalSectionMiddleware:
    """Make the session-backed operational section available to every view."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        requested_section = request.GET.get("section")
        if requested_section is not None:
            set_current_section(request, requested_section)

        query = request.GET.copy()
        query["section"] = get_effective_section(request)
        request.GET = query

        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Apply browser security policy headers to every platform response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        record_response_status(response.status_code)
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault(
            "Content-Security-Policy",
            "; ".join(
                (
                    "default-src 'self'",
                    "base-uri 'self'",
                    "form-action 'self'",
                    "frame-ancestors 'none'",
                    "object-src 'none'",
                    "img-src 'self' data: blob:",
                    "font-src 'self' data:",
                    "style-src 'self' 'unsafe-inline'",
                    "script-src 'self' 'unsafe-inline'",
                    "connect-src 'self'",
                )
            ),
        )
        return response
