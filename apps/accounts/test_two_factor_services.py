from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import TwoFactorAuditLog
from apps.accounts.services.two_factor_audit_service import record_2fa_event
from apps.communications.models import OTPVerification
from apps.communications.providers.authentica import ProviderConnectionError
from apps.communications.services.otp_service import AuthenticaOTPService
from apps.core.tests.factories import create_employee, create_user


class FailingOTPProvider:
    def request_otp(self, **kwargs):
        raise ProviderConnectionError("provider unavailable")


@override_settings(
    COMMUNICATIONS_ENABLED=True,
    AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"),
)
class TwoFactorServiceSecurityTests(TestCase):
    password = "StrongTestPassword123!"

    def setUp(self):
        self.user = create_user(
            username="service-user",
            password=self.password,
            email="service@example.test",
        )
        self.employee = create_employee(
            user=self.user,
            phone_number="+966501234567",
            email=self.user.email,
        )

    def test_each_channel_provider_failure_is_audited_without_http(self):
        recipients = {
            "sms": self.employee.phone_number,
            "whatsapp": self.employee.phone_number,
            "email": self.user.email,
        }
        service = AuthenticaOTPService(FailingOTPProvider())

        for channel, recipient in recipients.items():
            with self.subTest(channel=channel):
                with self.assertRaises(ProviderConnectionError):
                    service.request_otp(
                        user=self.user,
                        employee=self.employee,
                        channel=channel,
                        recipient=recipient,
                        purpose=OTPVerification.Purpose.LOGIN,
                    )
                self.assertTrue(
                    TwoFactorAuditLog.objects.filter(
                        user=self.user,
                        event="2fa_send_failed",
                        channel=channel,
                    ).exists()
                )

    def test_audit_write_failure_does_not_raise(self):
        with patch(
            "apps.accounts.services.two_factor_audit_service.TwoFactorAuditLog.objects.create",
            side_effect=RuntimeError("database unavailable"),
        ):
            record_2fa_event(user=self.user, event="2fa_required")