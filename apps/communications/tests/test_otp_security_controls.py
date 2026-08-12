from __future__ import annotations

import hashlib
from unittest.mock import patch

from smtplib import SMTPException

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.communications.models import OTPVerification
from apps.communications.providers.authentica import AuthenticaProvider, ProviderConnectionError
from apps.communications.providers.email import LocalEmailOTPProvider
from apps.communications.services.delivery_service import get_otp_provider
from apps.communications.services.otp_service import AuthenticaOTPService, OTPReplayError
from apps.core.tests.factories import create_employee, create_user


@override_settings(
    COMMUNICATIONS_ENABLED=True,
    AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"),
    AUTHENTICA_OTP_TTL_SECONDS=300,
    AUTHENTICA_OTP_MAX_ATTEMPTS=5,
    AUTHENTICA_OTP_RESEND_COOLDOWN_SECONDS=0,
    AUTHENTICA_OTP_RATE_LIMIT_ATTEMPTS=10,
    AUTHENTICA_OTP_RATE_LIMIT_WINDOW=600,
)
class EmailOTPRegressionTests(TestCase):
    def setUp(self):
        self.user = create_user(username="email-otp-user", password="StrongTestPassword123!", email="user@example.test")
        self.employee = create_employee(user=self.user, phone_number="+966501234567", email=self.user.email)

    def test_email_routes_to_local_provider_and_sms_whatsapp_remain_authentica(self):
        self.assertIsInstance(get_otp_provider("email"), LocalEmailOTPProvider)
        self.assertIsInstance(get_otp_provider("sms"), AuthenticaProvider)
        self.assertIsInstance(get_otp_provider("whatsapp"), AuthenticaProvider)

    @patch.object(LocalEmailOTPProvider, "_generate_otp", return_value="123456")
    @patch("apps.communications.providers.email.send_mail")
    def test_email_otp_uses_hash_only_storage_and_successful_verification(self, mock_send_mail, _mock_generate_otp):
        service = AuthenticaOTPService(get_otp_provider("email"))

        verification = service.request_otp(
            user=self.user,
            employee=self.employee,
            channel="email",
            recipient=self.user.email,
            purpose=OTPVerification.Purpose.LOGIN,
        )

        cached_hash = cache.get(verification.provider_request_id)
        self.assertIsNotNone(cached_hash)
        self.assertNotEqual(cached_hash, "123456")
        self.assertEqual(cached_hash, hashlib.sha256("123456".encode("utf-8")).hexdigest())
        self.assertTrue(mock_send_mail.called)

        result = service.verify_otp(
            verification=verification,
            otp="123456",
            recipient=self.user.email,
        )
        self.assertEqual(result.status, OTPVerification.Status.VERIFIED)
        self.assertIsNone(cache.get(verification.provider_request_id))

        with self.assertRaises(OTPReplayError):
            service.verify_otp(
                verification=verification,
                otp="123456",
                recipient=self.user.email,
            )

        verification.refresh_from_db()
        self.assertEqual(verification.status, OTPVerification.Status.VERIFIED)
        self.assertIsNone(cache.get(verification.provider_request_id))

    @patch("apps.communications.providers.email.send_mail", side_effect=SMTPException("smtp failed"))
    def test_smtp_failure_is_fail_closed(self, _mock_send_mail):
        service = AuthenticaOTPService(get_otp_provider("email"))

        with self.assertRaises(ProviderConnectionError):
            service.request_otp(
                user=self.user,
                employee=self.employee,
                channel="email",
                recipient=self.user.email,
                purpose=OTPVerification.Purpose.LOGIN,
            )

        verification = OTPVerification.objects.filter(user=self.user, channel="email").order_by("-created_at").first()
        self.assertIsNotNone(verification)
        self.assertEqual(verification.status, OTPVerification.Status.FAILED)
        self.assertIsNone(cache.get(verification.provider_request_id))

    @patch.object(LocalEmailOTPProvider, "_generate_otp", return_value="456789")
    def test_missing_or_expired_cache_fails_closed(self, _mock_generate_otp):
        service = AuthenticaOTPService(get_otp_provider("email"))
        verification = service.request_otp(
            user=self.user,
            employee=self.employee,
            channel="email",
            recipient=self.user.email,
            purpose=OTPVerification.Purpose.LOGIN,
        )

        cache.delete(verification.provider_request_id)
        failed = service.verify_otp(
            verification=verification,
            otp="456789",
            recipient=self.user.email,
        )
        self.assertIn(failed.status, {OTPVerification.Status.EXPIRED, OTPVerification.Status.FAILED})

    @patch.object(LocalEmailOTPProvider, "_generate_otp", side_effect=["111111", "222222"])
    @patch("apps.communications.providers.email.send_mail")
    def test_resend_invalidates_previous_challenge(self, _mock_send_mail, _mock_generate_otp):
        service = AuthenticaOTPService(get_otp_provider("email"))
        first = service.request_otp(
            user=self.user,
            employee=self.employee,
            channel="email",
            recipient=self.user.email,
            purpose=OTPVerification.Purpose.LOGIN,
        )
        previous_key = first.provider_request_id

        second = service.resend_otp(
            verification=first,
            recipient=self.user.email,
        )

        self.assertIsNotNone(second.provider_request_id)
        self.assertNotEqual(second.provider_request_id, previous_key)
        self.assertIsNone(cache.get(previous_key))

        invalid = service.verify_otp(
            verification=first,
            otp="111111",
            recipient=self.user.email,
        )
        self.assertNotEqual(invalid.status, OTPVerification.Status.VERIFIED)
