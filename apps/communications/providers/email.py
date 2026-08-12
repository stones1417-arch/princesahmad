from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

from apps.communications.providers.authentica import ProviderConnectionError

from .base import BaseCommunicationProvider, ProviderResult


class EmailProvider(BaseCommunicationProvider):
    """Marker base class for email-capable providers."""

    def send_sms(self, *, recipient: str, message: str) -> ProviderResult:
        raise NotImplementedError("Email provider does not support SMS.")

    def send_whatsapp(self, *, recipient: str, message: str) -> ProviderResult:
        raise NotImplementedError("Email provider does not support WhatsApp.")

    def send_email(self, *, recipient: str, subject: str, message: str) -> ProviderResult:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER or None,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return ProviderResult(status="sent", provider_message_id="")

    def normalize_response(self, response: Any) -> ProviderResult:
        return ProviderResult(status="sent", provider_message_id=str(response or ""))

    def health_check(self) -> dict[str, bool]:
        return {"email": True}

    def clear_challenge(self, provider_request_id: str | None = None) -> None:
        challenge_id = (provider_request_id or "").strip()
        if challenge_id:
            cache.delete(challenge_id)


class LocalEmailOTPProvider(EmailProvider):
    """Local email OTP provider using Django SMTP and hash-only cache storage."""

    provider_code = "local_email"

    @staticmethod
    def _hash_otp(value: str) -> str:
        return hashlib.sha256((value or "").strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_otp(length: int = 6) -> str:
        return "".join(secrets.choice("0123456789") for _ in range(length))

    def request_otp(
        self,
        *,
        channel: str,
        recipient: str,
        purpose: str,
        template_id: str | int | None = None,
        provider_request_id: str | None = None,
    ) -> ProviderResult:
        del purpose, template_id
        if channel != "email":
            raise ValueError("LocalEmailOTPProvider only supports email channel.")

        normalized_recipient = (recipient or "").strip()
        if not normalized_recipient:
            raise ValueError("Recipient is required.")

        challenge_id = (provider_request_id or f"email-otp-{secrets.token_urlsafe(24)}").strip()
        if not challenge_id:
            challenge_id = f"email-otp-{secrets.token_urlsafe(24)}"

        otp = self._generate_otp()
        cache.set(
            challenge_id,
            self._hash_otp(otp),
            timeout=int(getattr(settings, "AUTHENTICA_OTP_TTL_SECONDS", 300)),
        )

        try:
            send_mail(
                subject="Verification code",
                message=(
                    "Your verification code is: "
                    f"{otp}\n"
                    f"This code expires in {getattr(settings, 'AUTHENTICA_OTP_TTL_SECONDS', 300)} seconds."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER or None,
                recipient_list=[normalized_recipient],
                fail_silently=False,
            )
        except Exception as exc:  # pragma: no cover - exercised by SMTP failure tests
            cache.delete(challenge_id)
            raise ProviderConnectionError("Unable to send OTP via Django SMTP.") from exc

        return ProviderResult(
            status="sent",
            provider_message_id=challenge_id,
            payload={"challenge_id": challenge_id},
        )

    def verify_otp(
        self,
        *,
        channel: str,
        recipient: str,
        otp: str,
        provider_request_id: str | None = None,
    ) -> ProviderResult:
        if channel != "email":
            raise ValueError("LocalEmailOTPProvider only supports email channel.")

        challenge_id = (provider_request_id or "").strip()
        if not challenge_id:
            return ProviderResult(status="expired", provider_message_id="")

        stored_hash = cache.get(challenge_id)
        if stored_hash is None:
            return ProviderResult(status="expired", provider_message_id=challenge_id)

        if not isinstance(otp, str) or not otp.strip():
            return ProviderResult(status="failed", provider_message_id=challenge_id)

        if hmac.compare_digest(str(stored_hash), self._hash_otp(otp)):
            cache.delete(challenge_id)
            return ProviderResult(status="verified", provider_message_id=challenge_id)

        return ProviderResult(status="failed", provider_message_id=challenge_id)
