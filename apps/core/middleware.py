from __future__ import annotations

from collections.abc import Callable

from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from apps.accounts.security import (
    clear_two_factor_verification,
    has_completed_two_factor,
    requires_two_factor,
)
from apps.core.monitoring import record_response_status
from apps.roles.services.section_context import (
    get_effective_section,
    set_current_section,
)


class OperationalSectionMiddleware:
    """Make the session-backed operational section available to non-admin views."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith("/admin/"):
            return self.get_response(request)

        requested_section = request.GET.get("section")
        if requested_section is not None:
            set_current_section(request, requested_section)

        query = request.GET.copy()
        query["section"] = get_effective_section(request)
        request.GET = query

        return self.get_response(request)


class AdministrativeTwoFactorMiddleware:
    """Fail closed for staff/superuser access unless 2FA has been completed."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith("/admin/") and request.user.is_authenticated:
            user = request.user
            if (user.is_superuser or user.is_staff) and requires_two_factor(user):
                if not has_completed_two_factor(request, user):
                    clear_two_factor_verification(request)
                    logout(request)
                    return redirect("accounts:login")
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
