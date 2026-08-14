from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class OTPRecipientValidationError(ValueError):
    pass


def normalize_saudi_phone_number(value: str) -> str:
    """Normalize supported Saudi mobile formats to E.164."""
    normalized_phone = re.sub(r"[\s()\-]", "", (value or "").strip())

    if not normalized_phone:
        raise OTPRecipientValidationError(
            "رقم الجوال غير صالح. استخدم رقمًا سعوديًا صحيحًا مثل +9665XXXXXXXX."
        )

    if normalized_phone.startswith("00"):
        normalized_phone = f"+{normalized_phone[2:]}"

    if normalized_phone.startswith("+966"):
        national_number = normalized_phone[4:]
    elif normalized_phone.startswith("966"):
        national_number = normalized_phone[3:]
    elif normalized_phone.startswith("05"):
        national_number = normalized_phone[1:]
    elif normalized_phone.startswith("5"):
        national_number = normalized_phone
    else:
        national_number = normalized_phone

    if not re.fullmatch(r"5\d{8}", national_number):
        raise OTPRecipientValidationError(
            "رقم الجوال غير صالح. استخدم رقمًا سعوديًا صحيحًا مثل +9665XXXXXXXX."
        )

    return f"+966{national_number}"


def normalize_otp_recipient(channel: str, recipient: str) -> str:
    value = (recipient or "").strip()
    if channel in {"sms", "whatsapp"}:
        normalized_phone = re.sub(r"[\s()\-]", "", value)
        if normalized_phone.startswith("00"):
            normalized_phone = f"+{normalized_phone[2:]}"
        if not E164_PATTERN.fullmatch(normalized_phone):
            raise OTPRecipientValidationError("رقم الهاتف يجب أن يكون بصيغة E.164.")
        return normalized_phone
    if channel == "email":
        try:
            validate_email(value)
        except ValidationError as exc:
            raise OTPRecipientValidationError("البريد الإلكتروني غير صالح.") from exc
        return value
    raise OTPRecipientValidationError("قناة OTP غير مدعومة.")