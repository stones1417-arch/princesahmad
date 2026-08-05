from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.forms.models import model_to_dict
from django.db.models import Model


SENSITIVE_FIELDS = {
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret_key",
}


def get_client_ip(
    request: HttpRequest | None,
) -> str | None:
    """
    استخراج عنوان IP الحقيقي للمستخدم.

    يدعم التشغيل المباشر وخلف Proxy.
    """

    if request is None:
        return None

    forwarded_for = request.META.get(
        "HTTP_X_FORWARDED_FOR",
    )

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def get_request_user(
    request: HttpRequest | None,
):
    """
    إرجاع المستخدم المسجل أو None.
    """

    if request is None:
        return None

    user = getattr(request, "user", None)

    if user is None:
        return None

    if not user.is_authenticated:
        return None

    return user


def clean_history_value(
    value: Any,
) -> Any:
    """
    تحويل القيم إلى صيغة مناسبة لـ JSONField.
    """

    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if isinstance(value, Model):
        return {
            "id": value.pk,
            "label": str(value),
        }

    if isinstance(value, dict):
        return {
            str(key): clean_history_value(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_FIELDS
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            clean_history_value(item)
            for item in value
        ]

    return str(value)


def model_snapshot(
    instance: Model,
    *,
    fields: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """
    أخذ نسخة آمنة من بيانات النموذج قبل أو بعد التغيير.
    """

    if instance is None:
        return {}

    if fields:
        result = {}

        for field_name in fields:
            if field_name.lower() in SENSITIVE_FIELDS:
                continue

            try:
                value = getattr(
                    instance,
                    field_name,
                )
            except AttributeError:
                continue

            result[field_name] = clean_history_value(
                value,
            )

        return result

    raw_data = model_to_dict(instance)

    cleaned_data = {}

    for field_name, value in raw_data.items():
        if field_name.lower() in SENSITIVE_FIELDS:
            continue

        cleaned_data[field_name] = clean_history_value(
            value,
        )

    cleaned_data["id"] = instance.pk

    return cleaned_data