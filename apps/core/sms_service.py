from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from django.core.exceptions import ValidationError


@dataclass(slots=True)
class SmsResult:
    success: bool
    message_id: str = ""
    error: str = ""
    response_data: dict[str, Any] | None = None


class SmsService:
    API_URL = "https://el.cloud.unifonic.com/rest/SMS/messages"
    REQUEST_TIMEOUT = 20

    @staticmethod
    def _clean_setting(value: Any) -> str:
        cleaned = str(value or "").strip()
        if (
            len(cleaned) >= 2
            and cleaned[0] == cleaned[-1]
            and cleaned[0] in {'"', "'"}
        ):
            cleaned = cleaned[1:-1].strip()
        return cleaned

    @classmethod
    def normalize_saudi_phone(cls, phone: str) -> str:
        value = re.sub(r"\D", "", phone or "")

        if value.startswith("00966"):
            value = value[2:]

        if value.startswith("966"):
            normalized = value
        elif value.startswith("05") and len(value) == 10:
            normalized = f"966{value[1:]}"
        elif value.startswith("5") and len(value) == 9:
            normalized = f"966{value}"
        else:
            raise ValidationError(
                "رقم الجوال غير صحيح. استخدم صيغة 05XXXXXXXX."
            )

        if not re.fullmatch(r"9665\d{8}", normalized):
            raise ValidationError("رقم الجوال السعودي غير صالح.")

        return normalized

    @classmethod
    def send(
        cls,
        *,
        recipient: str,
        message: str,
        correlation_id: str = "",
    ) -> SmsResult:
        enabled = bool(getattr(settings, "SMS_ENABLED", False))
        app_sid = cls._clean_setting(
            getattr(settings, "UNIFONIC_APP_SID", "")
        )
        sender_id = cls._clean_setting(
            getattr(settings, "UNIFONIC_SENDER_ID", "")
        )

        if not enabled:
            return SmsResult(
                success=False,
                error="خدمة SMS غير مفعلة في إعدادات النظام.",
            )

        if not app_sid:
            return SmsResult(
                success=False,
                error="مفتاح UNIFONIC_APP_SID غير موجود.",
            )

        if "ضع_" in app_sid or app_sid.lower() in {"xxxxxxxx", "appsid"}:
            return SmsResult(
                success=False,
                error=(
                    "قيمة UNIFONIC_APP_SID تجريبية وليست AppSid الحقيقي."
                ),
            )

        if any(character.isspace() for character in app_sid):
            return SmsResult(
                success=False,
                error="قيمة UNIFONIC_APP_SID تحتوي على مسافات أو أسطر.",
            )

        if not sender_id:
            return SmsResult(
                success=False,
                error="اسم المرسل UNIFONIC_SENDER_ID غير موجود.",
            )

        message_body = (message or "").strip()

        if not message_body:
            return SmsResult(
                success=False,
                error="لا يمكن إرسال رسالة فارغة.",
            )

        try:
            normalized_phone = cls.normalize_saudi_phone(recipient)
        except ValidationError as error:
            error_message = (
                error.messages[0]
                if getattr(error, "messages", None)
                else str(error)
            )
            return SmsResult(
                success=False,
                error=error_message,
            )

        payload = {
            "AppSid": app_sid,
            "SenderID": sender_id,
            "Recipient": normalized_phone,
            "Body": message_body,
            "responseType": "JSON",
            "CorrelationID": (correlation_id or "").strip(),
            "baseEncode": "true",
            "async": "false",
        }

        try:
            response = requests.post(
                cls.API_URL,
                data=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=cls.REQUEST_TIMEOUT,
            )
        except requests.RequestException as error:
            return SmsResult(
                success=False,
                error=f"تعذر الاتصال بمزود الرسائل: {error}",
            )

        try:
            response_data = response.json()
        except ValueError:
            return SmsResult(
                success=False,
                error=(
                    "وصلت استجابة غير صالحة من Unifonic "
                    f"(HTTP {response.status_code})."
                ),
            )

        if not isinstance(response_data, dict):
            return SmsResult(
                success=False,
                error="صيغة استجابة Unifonic غير متوقعة.",
            )

        success_value = response_data.get("success")
        is_success = (
            success_value is True
            or str(success_value).lower() == "true"
        )

        if response.ok and is_success:
            message_data = response_data.get("data") or {}
            message_id = ""

            if isinstance(message_data, dict):
                message_id = str(
                    message_data.get("MessageID")
                    or message_data.get("messageId")
                    or ""
                )

            return SmsResult(
                success=True,
                message_id=message_id,
                response_data=response_data,
            )

        provider_message = (
            response_data.get("message")
            or response_data.get("error")
            or response_data.get("errorCode")
            or f"فشل الإرسال برمز HTTP {response.status_code}"
        )

        if (
            response.status_code in {401, 402}
            or "AppSid" in str(provider_message)
        ):
            provider_message = (
                "رفض Unifonic قيمة AppSid. انسخ Application ID الحقيقي "
                "من حساب Unifonic، ثم أعد تشغيل Django من نافذة "
                "PowerShell نفسها."
            )

        return SmsResult(
            success=False,
            error=str(provider_message),
            response_data=response_data,
        )