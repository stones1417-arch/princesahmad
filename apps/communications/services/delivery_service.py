from __future__ import annotations

from django.conf import settings

from apps.communications.providers import AuthenticaProvider


def get_provider():
    if settings.COMMUNICATION_PROVIDER == "authentica":
        return AuthenticaProvider()
    raise ValueError("مزود الاتصالات المحدد غير مدعوم.")