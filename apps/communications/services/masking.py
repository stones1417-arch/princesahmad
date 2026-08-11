from __future__ import annotations

from typing import Any


SENSITIVE_KEYS = {
    "authorization",
    "x-authorization",
    "api_key",
    "apikey",
    "api-key",
    "api_secret",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "otp",
    "code",
}


def mask_value(
    value: Any,
    key: str = "",
    *,
    visible_start: int = 3,
    visible_end: int = 3,
    mask_char: str = "*",
) -> Any:
    """
    إخفاء قيمة حساسة بشكل عام.

    مثال:
        abcdefghijkl
        -> abc******jkl

    لا تستخدم هذه الدالة لتسجيل OTP.
    OTP يجب إخفاؤه بالكامل.
    """

    normalized_key = key.strip().lower().replace("-", "_")
    sensitive_keys = {
        item.replace("-", "_")
        for item in SENSITIVE_KEYS
    }
    if (
        normalized_key in sensitive_keys
        or normalized_key.endswith("_secret")
        or normalized_key.endswith("_token")
        or normalized_key.startswith("x_") and normalized_key.endswith("secret")
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            item_key: mask_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_value(item) for item in value)
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    if "@" in text:
        return mask_email(text)
    if text.startswith("+") and text[1:].isdigit():
        return mask_phone(text)

    if visible_start < 0:
        visible_start = 0

    if visible_end < 0:
        visible_end = 0

    if len(text) <= (
        visible_start
        + visible_end
    ):
        return mask_char * len(text)

    hidden_length = (
        len(text)
        - visible_start
        - visible_end
    )

    return (
        text[:visible_start]
        + (
            mask_char
            * hidden_length
        )
        + (
            text[-visible_end:]
            if visible_end
            else ""
        )
    )


def mask_secret(
    value: Any,
) -> str:
    """
    إخفاء Secret أو API Key.

    لا يعرض إلا جزءًا صغيرًا جدًا
    من البداية والنهاية.
    """

    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    if len(text) <= 8:
        return "*" * len(text)

    return mask_value(
        text,
        visible_start=3,
        visible_end=3,
    )


def mask_otp(
    value: Any,
) -> str:
    """
    إخفاء OTP بالكامل.

    لا يجب أبدًا تسجيل قيمة OTP
    الفعلية في logs.
    """

    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    return "*" * len(text)


def mask_phone(
    value: Any,
) -> str:
    """
    إخفاء رقم الجوال مع الإبقاء
    على جزء بسيط منه للتتبع التشغيلي.

    مثال تقريبي:
        +966551234567
        -> +9665*****567
    """

    if value is None:
        return ""

    phone = str(value).strip()

    if not phone:
        return ""

    if len(phone) <= 7:
        return "*" * len(phone)

    prefix_length = (
        5
        if phone.startswith("+")
        else 3
    )

    suffix_length = 3

    hidden_length = max(
        len(phone)
        - prefix_length
        - suffix_length,
        3,
    )

    return (
        phone[:prefix_length]
        + (
            "*"
            * hidden_length
        )
        + phone[-suffix_length:]
    )


def mask_email(
    value: Any,
) -> str:
    """
    إخفاء البريد الإلكتروني.

    مثال:
        ahmed@example.com
        -> a***@example.com
    """

    if value is None:
        return ""

    email = str(value).strip()

    if not email:
        return ""

    if "@" not in email:
        return mask_value(
            email,
            visible_start=1,
            visible_end=0,
        )

    local_part, domain = email.split(
        "@",
        1,
    )

    if not local_part:
        masked_local = "***"
    else:
        masked_local = local_part[:2] + "***"

    return (
        f"{masked_local}@{domain}"
    )


def mask_recipient(
    value: Any,
) -> str:
    """
    اكتشاف نوع المستلم وإخفائه.

    يدعم:
    - Email
    - Phone
    """

    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    if "@" in text:
        return mask_email(
            text
        )

    return mask_phone(
        text
    )


def sanitize_mapping(
    data: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    تنظيف dictionary قبل تسجيله في logs.

    أي مفتاح حساس يتم إخفاء قيمته.
    ويتم تنظيف القواميس والقوائم المتداخلة.
    """

    if not data:
        return {}

    sanitized: dict[str, Any] = {}

    for key, value in data.items():
        normalized_key = str(
            key
        ).strip().lower()

        if normalized_key in SENSITIVE_KEYS:
            if (
                normalized_key
                in {
                    "otp",
                    "code",
                }
            ):
                sanitized[key] = (
                    mask_otp(
                        value
                    )
                )
            else:
                sanitized[key] = (
                    mask_secret(
                        value
                    )
                )

            continue

        if isinstance(
            value,
            dict,
        ):
            sanitized[key] = (
                sanitize_mapping(
                    value
                )
            )

        elif isinstance(
            value,
            list,
        ):
            sanitized[key] = [
                (
                    sanitize_mapping(item)
                    if isinstance(
                        item,
                        dict,
                    )
                    else item
                )
                for item in value
            ]

        elif (
            normalized_key
            in {
                "phone",
                "mobile",
                "recipient_phone",
                "fallback_phone",
            }
        ):
            sanitized[key] = (
                mask_phone(
                    value
                )
            )

        elif (
            normalized_key
            in {
                "email",
                "recipient_email",
                "fallback_email",
            }
        ):
            sanitized[key] = (
                mask_email(
                    value
                )
            )

        else:
            sanitized[key] = value

    return sanitized