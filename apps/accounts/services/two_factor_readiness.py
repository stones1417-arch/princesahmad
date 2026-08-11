from django.conf import settings

from apps.accounts.models import AccountProfile
from apps.communications.services.masking import mask_email, mask_phone
from apps.communications.services.otp_validation import OTPRecipientValidationError, normalize_otp_recipient
from apps.hr.models import Employee


def get_user_otp_channels(user):
    employee = Employee.objects.filter(user=user).only("phone_number", "email").first()
    profile = AccountProfile.objects.filter(user=user).only("phone_number").first()
    phone = (getattr(employee, "phone_number", "") or getattr(profile, "phone_number", "") or "").strip()
    email = (getattr(employee, "email", "") or user.email or "").strip()
    allowed = {str(value).strip().lower() for value in settings.AUTHENTICA_OTP_ALLOWED_CHANNELS}
    channels = []
    if phone:
        channels.extend(channel for channel in ("sms", "whatsapp") if channel in allowed)
    if email and "email" in allowed:
        channels.append("email")
    return channels


def is_user_2fa_ready(user):
    return bool(get_user_otp_channels(user))


def _is_valid_recipient(channel, value):
    if not value:
        return False
    try:
        normalize_otp_recipient(channel, value)
    except OTPRecipientValidationError:
        return False
    return True


def _mask_email(value):
    return mask_email(value) or "-"


def _mask_phone(value):
    return mask_phone(value) or "-"


def get_user_2fa_readiness_details(user):
    """Return non-sensitive readiness diagnostics without changing user data."""
    employee = Employee.objects.filter(user=user).only("id", "phone_number", "email").first()
    profile = AccountProfile.objects.filter(user=user).only("phone_number").first()
    phone = (getattr(employee, "phone_number", "") or getattr(profile, "phone_number", "") or "").strip()
    email = (getattr(employee, "email", "") or user.email or "").strip()
    allowed = {str(value).strip().lower() for value in settings.AUTHENTICA_OTP_ALLOWED_CHANNELS}
    phone_valid = _is_valid_recipient("sms", phone)
    email_valid = _is_valid_recipient("email", email)
    sms_available = phone_valid and "sms" in allowed
    whatsapp_available = phone_valid and "whatsapp" in allowed
    email_available = email_valid and "email" in allowed
    channels = [
        channel
        for channel, available in (
            ("sms", sms_available),
            ("whatsapp", whatsapp_available),
            ("email", email_available),
        )
        if available
    ]
    reasons = []
    if not phone and not email:
        reasons.append("No OTP contact details")
    else:
        if phone and not phone_valid:
            reasons.append("Invalid mobile number")
        if email and not email_valid:
            reasons.append("Invalid email address")
    if not channels:
        if not any((sms_available, whatsapp_available, email_available)) and (phone_valid or email_valid):
            reasons.append("No valid OTP channel is enabled")
        elif not reasons:
            reasons.append("No verified OTP channel")

    username = user.username.casefold()
    user_email = (user.email or "").casefold()
    if user.is_staff or user.is_superuser:
        classification = "Administrative account - do not modify"
    elif employee:
        classification = "Operational employee account - do not delete"
    elif username.startswith(("test-", "test_", "test.")) or user_email.endswith("@example.test"):
        classification = "Potential test account"
    else:
        classification = "Real account needs 2FA setup"

    return {
        "has_employee": bool(employee),
        "channels": channels,
        "email_masked": _mask_email(email),
        "phone_masked": _mask_phone(phone),
        "email_valid": email_valid,
        "phone_valid": phone_valid,
        "sms_available": sms_available,
        "whatsapp_available": whatsapp_available,
        "reason": "; ".join(reasons) or "-",
        "classification": classification,
    }


def get_employee_2fa_readiness_details(employee):
    """Return readiness details for HR views, including unlinked employees."""
    if employee.user_id:
        return get_user_2fa_readiness_details(employee.user)

    phone = (employee.phone_number or "").strip()
    email = (employee.email or "").strip()
    return {
        "has_employee": True,
        "channels": [],
        "email_masked": _mask_email(email),
        "phone_masked": _mask_phone(phone),
        "email_valid": _is_valid_recipient("email", email),
        "phone_valid": _is_valid_recipient("sms", phone),
        "sms_available": False,
        "whatsapp_available": False,
        "reason": "No linked user account",
        "classification": "Operational employee account - do not delete",
    }