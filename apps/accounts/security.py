from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest


def _client_ip(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
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
