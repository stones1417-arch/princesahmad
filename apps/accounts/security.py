from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.roles.services.access_control import user_has_role

ADMIN_2FA_SESSION_KEY = "admin_two_factor_verified"


def requires_two_factor(user) -> bool:
    if not user or not user.is_active:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if user_has_role(user, "system_admin"):
        return True
    if getattr(settings, "AUTHENTICA_2FA_ENABLED", False):
        return True
    activation_time = parse_datetime(
        str(getattr(settings, "AUTHENTICA_2FA_NEW_USERS_SINCE", "") or "")
    )
    if getattr(settings, "AUTHENTICA_2FA_REQUIRE_FOR_NEW_USERS", False) and activation_time:
        if timezone.is_naive(activation_time):
            activation_time = timezone.make_aware(activation_time)
        if user.date_joined >= activation_time:
            return True
    if not getattr(settings, "AUTHENTICA_2FA_PILOT_ENABLED", False):
        return False
    pilot_ids = {
        int(value)
        for value in getattr(settings, "AUTHENTICA_2FA_PILOT_USER_IDS", ()) or ()
        if str(value).isdigit()
    }
    return (
        user.pk in pilot_ids
        or (user.is_superuser and getattr(settings, "AUTHENTICA_2FA_PILOT_INCLUDE_SUPERUSERS", False))
        or (user.is_staff and getattr(settings, "AUTHENTICA_2FA_PILOT_INCLUDE_STAFF", False))
    )


def mark_two_factor_verified(request, user) -> None:
    if not request or not user:
        return
    request.session[ADMIN_2FA_SESSION_KEY] = getattr(user, "pk", None)
    request.session.modified = True


def clear_two_factor_verification(request) -> None:
    if not request:
        return
    request.session.pop(ADMIN_2FA_SESSION_KEY, None)
    request.session.modified = True


def has_completed_two_factor(request, user) -> bool:
    if not requires_two_factor(user):
        return True
    stored_user_id = request.session.get(ADMIN_2FA_SESSION_KEY)
    return stored_user_id == getattr(user, "pk", None)


def _client_ip(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if getattr(settings, "TRUST_PROXY_HEADERS", False) and forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _login_key(request: HttpRequest, username: str) -> str:
    identity = f"{_client_ip(request)}:{username.casefold()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"login-attempts:{digest}"


def login_is_limited(request: HttpRequest, username: str) -> bool:
    attempts = int(cache.get(_login_key(request, username), 0))
    return attempts >= settings.LOGIN_RATE_LIMIT_ATTEMPTS


def record_login_failure(request: HttpRequest, username: str) -> None:
    key = _login_key(request, username)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=settings.LOGIN_RATE_LIMIT_WINDOW)


def clear_login_failures(request: HttpRequest, username: str) -> None:
    cache.delete(_login_key(request, username))
