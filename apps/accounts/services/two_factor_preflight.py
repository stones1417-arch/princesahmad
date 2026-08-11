from django.conf import settings
from django.contrib.auth import get_user_model

from apps.accounts.models import TwoFactorAuditLog
from apps.accounts.services.two_factor_readiness import is_user_2fa_ready
from apps.communications.models import OTPVerification


def get_global_two_factor_readiness():
    """Return dynamic, non-sensitive 2FA readiness signals."""
    users = get_user_model().objects.filter(is_active=True)
    total_users = users.count()
    ready_users = sum(is_user_2fa_ready(user) for user in users)
    superusers_ready = all(
        is_user_2fa_ready(user) for user in users.filter(is_superuser=True)
    )
    allowed_channels = set(settings.AUTHENTICA_OTP_ALLOWED_CHANNELS)
    core_ready = bool(settings.AUTHENTICA_BASE_URL and settings.AUTHENTICA_API_KEY)
    send_ready = bool(
        settings.AUTHENTICA_OTP_REQUEST_ENDPOINT and allowed_channels
    )
    verify_ready = bool(settings.AUTHENTICA_OTP_VERIFY_ENDPOINT)
    required_channels_ready = {"sms", "whatsapp", "email"}.issubset(
        allowed_channels
    )
    invalid_pending = OTPVerification.objects.filter(
        status__in=[
            OTPVerification.Status.PENDING,
            OTPVerification.Status.SENT,
        ],
        expires_at__isnull=True,
    ).exists()
    audit_ready = TwoFactorAuditLog._meta.managed
    functional_ready = all(
        (
            core_ready,
            send_ready,
            verify_ready,
            required_channels_ready,
            audit_ready,
            superusers_ready,
            ready_users == total_users,
            not invalid_pending,
        )
    )
    return {
        "active_users": total_users,
        "ready_users": ready_users,
        "not_ready_users": total_users - ready_users,
        "core_ready": core_ready,
        "send_ready": send_ready,
        "verify_ready": verify_ready,
        "required_channels_ready": required_channels_ready,
        "audit_ready": audit_ready,
        "superusers_ready": superusers_ready,
        "invalid_pending": invalid_pending,
        "functional_ready": functional_ready,
    }
