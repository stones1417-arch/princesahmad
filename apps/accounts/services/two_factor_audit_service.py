import logging

from apps.accounts.models import TwoFactorAuditLog
from apps.accounts.security import _client_ip


logger = logging.getLogger("platform.security")

_METADATA_KEYS = {
    "verification_id",
    "reason",
    "attempt_number",
    "policy_source",
    "actor_id",
    "employee_id",
    "changed_fields",
}
_SENSITIVE_KEYS = {"otp", "password", "api_key", "authorization", "recipient", "phone", "email", "token", "secret"}


def _safe_metadata(metadata):
    if not isinstance(metadata, dict):
        return {}
    result = {}
    for key, value in metadata.items():
        normalized_key = str(key).lower()
        if normalized_key in _SENSITIVE_KEYS or key not in _METADATA_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = str(value)[:100] if isinstance(value, str) else value
    return result


def record_2fa_event(*, user, event, channel=None, status=None, request=None, metadata=None):
    """Persist a sanitized 2FA event without interrupting authentication."""
    try:
        TwoFactorAuditLog.objects.create(
            user=user,
            event=event,
            channel=(channel or "")[:20],
            status=(status or "")[:20],
            ip_address=_client_ip(request) if request else None,
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
            metadata=_safe_metadata(metadata),
        )
    except Exception:
        logger.exception("Unable to persist sanitized two-factor audit event.")