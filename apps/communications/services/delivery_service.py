from __future__ import annotations

from django.conf import settings

from apps.communications.providers import AuthenticaProvider
from apps.communications.providers.email import LocalEmailOTPProvider


def get_provider():
    if settings.COMMUNICATION_PROVIDER == "authentica":
        return AuthenticaProvider()
    raise ValueError("مزود الاتصالات المحدد غير مدعوم.")


def get_otp_provider(channel: str):
    channel_name = (channel or "").strip().lower()
    if channel_name == "email":
        return LocalEmailOTPProvider()
    if channel_name in {"sms", "whatsapp"}:
        return AuthenticaProvider()
    raise ValueError(f"مزود OTP غير مدعوم للقناة: {channel_name}")