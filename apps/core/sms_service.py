from __future__ import annotations

import re
from abc import ABC, abstractmethod
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


class SMSProvider(ABC):
    name = "base"

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

    @staticmethod
    def normalize_saudi_phone(phone: str) -> str:
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

    @abstractmethod
    def send(
        cls,
        *,
        recipient: str,
        message: str,
        correlation_id: str = "",
    ) -> SmsResult:
        raise NotImplementedError


class UnifonicSMSProvider(SMSProvider):
    name = "unifonic"
    API_URL = "https://el.cloud.unifonic.com/rest/SMS/messages"
    REQUEST_TIMEOUT = 20

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


class FourJawalySMSProvider(SMSProvider):
    name = "4jawaly"
    API_URL = "https://api-sms.4jawaly.com/api/v1/account/area/sms/send"
    REQUEST_TIMEOUT = (5, 15)

    def send(
        cls,
        *,
        recipient: str,
        message: str,
        correlation_id: str = "",
    ) -> SmsResult:
        if not getattr(settings, "SMS_ENABLED", False):
            return SmsResult(
                success=False,
                error="خدمة SMS غير مفعلة في إعدادات النظام.",
            )

        api_key = cls._clean_setting(
            getattr(settings, "FOURJAWALY_API_KEY", "")
        )
        api_secret = cls._clean_setting(
            getattr(settings, "FOURJAWALY_API_SECRET", "")
        )
        sender_id = cls._clean_setting(
            getattr(settings, "FOURJAWALY_SENDER_ID", "")
        )

        if not api_key:
            return SmsResult(
                success=False,
                error="FOURJAWALY_API_KEY is not configured",
            )

        if not api_secret:
            return SmsResult(
                success=False,
                error="FOURJAWALY_API_SECRET is not configured",
            )

        if not sender_id:
            return SmsResult(
                success=False,
                error="FOURJAWALY_SENDER_ID is not configured",
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
            "messages": [
                {
                    "text": message_body,
                    "numbers": [normalized_phone],
                    "sender": sender_id,
                }
            ]
        }

        try:
            response = requests.post(
                cls.API_URL,
                auth=(api_key, api_secret),
                json=payload,
                timeout=cls.REQUEST_TIMEOUT,
                verify=True,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
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
                    "وصلت استجابة غير صالحة من FourJawaly "
                    f"(HTTP {response.status_code})."
                ),
            )

        if not isinstance(response_data, dict):
            return SmsResult(
                success=False,
                error="صيغة استجابة FourJawaly غير متوقعة.",
            )

        if response.status_code in {401, 403}:
            return SmsResult(
                success=False,
                error="Authentication failed for FourJawaly provider.",
                response_data=response_data,
            )

        if response.status_code == 429:
            return SmsResult(
                success=False,
                error="Rate limit exceeded by FourJawaly provider.",
                response_data=response_data,
            )

        if response.status_code >= 500:
            return SmsResult(
                success=False,
                error="FourJawaly provider server error.",
                response_data=response_data,
            )

        success_value = response_data.get("success")
        is_success = (
            success_value is True
            or str(success_value).lower() == "true"
            or response_data.get("status") == "success"
        )

        if response.ok and is_success:
            message_id = ""
            data = response_data.get("data") if isinstance(response_data.get("data"), dict) else {}
            message_id = str(
                response_data.get("messageId")
                or response_data.get("message_id")
                or data.get("messageId")
                or data.get("id")
                or data.get("message_id")
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
            or response_data.get("errorMessage")
            or response_data.get("details")
            or f"فشل الإرسال برمز HTTP {response.status_code}"
        )
        return SmsResult(
            success=False,
            error=str(provider_message),
            response_data=response_data,
        )


class SmsService:
    @staticmethod
    def _resolve_provider() -> SMSProvider:
        provider_name = (
            str(getattr(settings, "SMS_PROVIDER", "unifonic") or "unifonic")
            .strip()
            .lower()
        )
        if provider_name in {"4jawaly", "fourjawaly", "four_jawaly"}:
            return FourJawalySMSProvider()
        if provider_name in {"unifonic", "legacy"}:
            return UnifonicSMSProvider()
        raise ValueError(f"Unsupported SMS_PROVIDER: {provider_name}")

    @staticmethod
    def normalize_saudi_phone(phone: str) -> str:
        return SMSProvider.normalize_saudi_phone(phone)

    @classmethod
    def send(
        cls,
        *,
        recipient: str,
        message: str,
        correlation_id: str = "",
    ) -> SmsResult:
        try:
            provider = cls._resolve_provider()
            return provider.send(
                recipient=recipient,
                message=message,
                correlation_id=correlation_id,
            )
        except ValueError as exc:
            return SmsResult(
                success=False,
                error=str(exc),
            )