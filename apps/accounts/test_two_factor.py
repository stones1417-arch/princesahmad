from __future__ import annotations

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AccountProfile
from apps.accounts.models import TwoFactorAuditLog
from apps.accounts.security import requires_two_factor
from apps.communications.models import OTPVerification
from apps.communications.providers.base import ProviderResult
from apps.communications.services.otp_service import AuthenticaOTPService
from apps.core.tests.factories import create_employee, create_user
from apps.roles.services.role_manager import assign_role_to_user

from .views import TWO_FACTOR_SESSION_KEY


class FakeOTPProvider:
    def __init__(self, verification_status=OTPVerification.Status.VERIFIED):
        self.verification_status = verification_status
        self.requests = []
        self.verifications = []

    def request_otp(self, *, channel, recipient, purpose, template_id=None):
        self.requests.append((channel, recipient, purpose))
        return ProviderResult(status=OTPVerification.Status.SENT, provider_message_id="test-message")

    def verify_otp(self, *, channel, recipient, otp):
        self.verifications.append((channel, recipient, otp))
        return ProviderResult(status=self.verification_status)


@override_settings(
    AUTHENTICA_2FA_ENABLED=False,
    AUTHENTICA_2FA_PILOT_ENABLED=True,
    AUTHENTICA_2FA_PILOT_INCLUDE_STAFF=True,
    AUTHENTICA_2FA_PILOT_INCLUDE_SUPERUSERS=False,
    AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"),
    AUTHENTICA_OTP_RATE_LIMIT_ATTEMPTS=3,
    COMMUNICATIONS_ENABLED=True,
)
class PilotTwoFactorLoginTests(TestCase):
    password = "StrongTestPassword123!"

    def setUp(self):
        self.user = create_user(username="pilot-user", password=self.password, is_staff=True)
        self.employee = create_employee(
            user=self.user,
            phone_number="+966501234567",
            email="pilot@example.test",
        )
        self.provider = FakeOTPProvider()
        self.provider_patch = patch("apps.accounts.views.get_provider", return_value=self.provider)
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)

    def _login(self, password=None):
        return self.client.post(
            "/accounts/login/",
            {"username": self.user.username, "password": password or self.password},
        )

    def _verification(self):
        return OTPVerification.objects.get(user=self.user, purpose=OTPVerification.Purpose.LOGIN)

    def test_correct_password_requires_otp_without_authenticated_session(self):
        response = self._login()

        self.assertRedirects(response, "/accounts/two-factor/")
        self.assertEqual(self.provider.requests[0][0], "sms")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn(TWO_FACTOR_SESSION_KEY, self.client.session)

    def test_incorrect_password_does_not_send_otp(self):
        response = self._login(password="not-the-password")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.provider.requests, [])
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(AUTHENTICA_OTP_RATE_LIMIT_ATTEMPTS=10)
    def test_user_can_switch_to_sms_whatsapp_or_email(self):
        self._login()

        for channel in ("whatsapp", "email", "sms"):
            response = self.client.post(
                "/accounts/two-factor/",
                {"action": "change-channel", "channel": channel},
            )
            self.assertRedirects(response, "/accounts/two-factor/")

        self.assertEqual([call[0] for call in self.provider.requests], ["sms", "whatsapp", "email", "sms"])

    def test_successful_otp_creates_authenticated_session(self):
        self._login()
        response = self.client.post("/accounts/two-factor/", {"action": "verify", "otp": "123456"})

        self.assertRedirects(response, "/")
        self.assertEqual(str(self.user.pk), self.client.session["_auth_user_id"])
        self.assertNotIn(TWO_FACTOR_SESSION_KEY, self.client.session)
        self.assertEqual(self._verification().status, OTPVerification.Status.VERIFIED)

    def test_admin_without_employee_uses_profile_phone_for_sms_send_and_verify(self):
        admin = create_user(
            username="profile-admin",
            password=self.password,
            is_staff=True,
            is_superuser=True,
            email="admin@example.test",
        )
        AccountProfile.objects.create(user=admin, phone_number="+966509876543")

        response = self.client.post(
            "/accounts/login/",
            {"username": admin.username, "password": self.password},
        )
        self.assertRedirects(response, "/accounts/two-factor/")

        response = self.client.post(
            "/accounts/two-factor/",
            {"action": "verify", "otp": "123456"},
        )

        self.assertRedirects(response, "/")
        self.assertEqual(self.provider.requests[-1][1], "+966509876543")
        self.assertEqual(self.provider.verifications[-1][1], "+966509876543")
        verification = OTPVerification.objects.get(
            user=admin,
            purpose=OTPVerification.Purpose.LOGIN,
        )
        self.assertEqual(verification.status, OTPVerification.Status.VERIFIED)
        self.assertEqual(str(admin.pk), self.client.session["_auth_user_id"])

    def test_admin_without_employee_uses_user_email_fallback(self):
        admin = create_user(
            username="email-admin",
            password=self.password,
            is_staff=True,
            email="admin@example.test",
        )

        response = self.client.post(
            "/accounts/login/",
            {"username": admin.username, "password": self.password},
        )
        self.assertRedirects(response, "/accounts/two-factor/")
        response = self.client.post(
            "/accounts/two-factor/",
            {"action": "change-channel", "channel": "email"},
        )

        self.assertRedirects(response, "/accounts/two-factor/")
        self.assertEqual(self.provider.requests[-1][:2], ("email", "admin@example.test"))

    def test_failed_otp_does_not_log_in_and_increments_attempts(self):
        self.provider.verification_status = OTPVerification.Status.FAILED
        self._login()
        response = self.client.post("/accounts/two-factor/", {"action": "verify", "otp": "bad-code"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self._verification().attempts, 1)

    @override_settings(AUTHENTICA_OTP_MAX_ATTEMPTS=2)
    def test_max_attempts_rejects_without_another_provider_call(self):
        self.provider.verification_status = OTPVerification.Status.FAILED
        self._login()

        self.client.post("/accounts/two-factor/", {"action": "verify", "otp": "one"})
        self.client.post("/accounts/two-factor/", {"action": "verify", "otp": "two"})
        self.client.post("/accounts/two-factor/", {"action": "verify", "otp": "three"})

        self.assertEqual(len(self.provider.verifications), 2)
        self.assertEqual(self._verification().status, OTPVerification.Status.REJECTED)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(
            TwoFactorAuditLog.objects.filter(
                user=self.user,
                event="2fa_max_attempts_reached",
            ).exists()
        )

    @override_settings(AUTHENTICA_OTP_RESEND_COOLDOWN_SECONDS=60)
    def test_resend_cooldown_prevents_duplicate_provider_request(self):
        self._login()
        response = self.client.post("/accounts/two-factor/", {"action": "resend"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.provider.requests), 1)

    @override_settings(AUTHENTICA_OTP_RATE_LIMIT_ATTEMPTS=1)
    def test_rate_limit_blocks_second_otp_request(self):
        self._login()
        self.client.session.flush()
        response = self._login()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(self.provider.requests), 1)

    def test_non_pilot_user_keeps_normal_login_when_global_two_factor_disabled(self):
        user = create_user(username="ordinary-user", password=self.password)
        create_employee(user=user, phone_number="+966509876543", email="ordinary@example.test")

        response = self.client.post("/accounts/login/", {"username": user.username, "password": self.password})

        self.assertRedirects(response, "/")
        self.assertEqual(str(user.pk), self.client.session["_auth_user_id"])
        self.assertEqual(self.provider.requests, [])

    @override_settings(
        AUTHENTICA_2FA_ENABLED=True,
        AUTHENTICA_2FA_PILOT_USER_IDS=(),
        AUTHENTICA_2FA_PILOT_INCLUDE_STAFF=False,
        AUTHENTICA_2FA_PILOT_INCLUDE_SUPERUSERS=False,
    )
    def test_global_two_factor_requires_otp_for_non_pilot_normal_staff_and_superuser(self):
        users = [
            create_user(username="global-normal", password=self.password),
            create_user(username="global-staff", password=self.password, is_staff=True),
            create_user(
                username="global-superuser",
                password=self.password,
                is_staff=True,
                is_superuser=True,
            ),
        ]
        for user in users:
            create_employee(
                user=user,
                phone_number="+966501234567",
                email=f"{user.username}@example.test",
            )
            self.client.logout()
            response = self.client.post(
                "/accounts/login/",
                {
                    "username": user.username,
                    "password": self.password,
                    "remember_me": "on",
                    "next": "/dashboard/",
                },
            )
            self.assertRedirects(response, "/accounts/two-factor/")
            self.assertNotIn("_auth_user_id", self.client.session)
            self.assertIn(TWO_FACTOR_SESSION_KEY, self.client.session)

    @override_settings(AUTHENTICA_2FA_ENABLED=True)
    def test_global_two_factor_completes_login_only_after_mocked_otp_verification(self):
        ordinary = create_user(username="global-flow", password=self.password)
        create_employee(
            user=ordinary,
            phone_number="+966509876543",
            email="global-flow@example.test",
        )

        response = self.client.post(
            "/accounts/login/",
            {
                "username": ordinary.username,
                "password": self.password,
                "remember_me": "on",
                "next": "/dashboard/",
            },
        )
        self.assertRedirects(response, "/accounts/two-factor/")
        self.assertNotIn("_auth_user_id", self.client.session)

        response = self.client.post(
            "/accounts/two-factor/",
            {"action": "verify", "otp": "123456"},
        )
        self.assertRedirects(
            response,
            "/dashboard/",
            fetch_redirect_response=False,
        )
        self.assertEqual(str(ordinary.pk), self.client.session["_auth_user_id"])
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24)

    def test_two_factor_screen_only_contains_masked_recipient_and_no_otp(self):
        self._login()
        response = self.client.get("/accounts/two-factor/")

        self.assertNotContains(response, self.employee.email)
        self.assertNotContains(response, self.employee.phone_number)
        self.assertNotContains(response, "123456")
        self.assertNotIn("otp", {field.name for field in OTPVerification._meta.fields})

    def test_expired_otp_cannot_authenticate_or_call_provider(self):
        self._login()
        verification = self._verification()
        verification.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        verification.save(update_fields=["expires_at"])

        response = self.client.post("/accounts/two-factor/", {"action": "verify", "otp": "123456"})

        verification.refresh_from_db()
        self.assertEqual(verification.status, OTPVerification.Status.EXPIRED)
        self.assertEqual(self.provider.verifications, [])
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            TwoFactorAuditLog.objects.filter(
                user=self.user,
                event="2fa_expired",
            ).exists()
        )

    def test_verified_otp_record_cannot_be_replayed(self):
        self._login()
        verification = self._verification()
        verification.status = OTPVerification.Status.VERIFIED
        verification.save(update_fields=["status"])

        AuthenticaOTPService(self.provider).verify_otp(
            verification=verification,
            otp="123456",
            recipient=self.employee.phone_number,
        )

        self.assertEqual(self.provider.verifications, [])
        self.assertTrue(
            TwoFactorAuditLog.objects.filter(
                user=self.user,
                event="2fa_replay_blocked",
            ).exists()
        )

    @override_settings(AUTHENTICA_2FA_PENDING_SESSION_AGE=60)
    def test_expired_pending_session_is_cleared(self):
        self._login()
        session = self.client.session
        pending = session[TWO_FACTOR_SESSION_KEY]
        pending["created_at"] = 0
        session[TWO_FACTOR_SESSION_KEY] = pending
        session.save()

        response = self.client.get("/accounts/two-factor/")

        self.assertRedirects(response, "/accounts/login/")
        self.assertNotIn(TWO_FACTOR_SESSION_KEY, self.client.session)

    @override_settings(
        AUTHENTICA_2FA_ENABLED=False,
        AUTHENTICA_2FA_PILOT_ENABLED=False,
        AUTHENTICA_2FA_REQUIRE_SUPERUSERS=False,
    )
    def test_superuser_requires_two_factor_even_when_global_policy_is_off(self):
        superuser = create_user(
            username="protected-superuser",
            password=self.password,
            is_superuser=True,
            is_staff=True,
            email="protected@example.test",
        )

        self.assertTrue(requires_two_factor(superuser))

        response = self.client.post(
            "/accounts/login/",
            {"username": superuser.username, "password": self.password},
        )

        self.assertRedirects(response, "/accounts/two-factor/")
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        AUTHENTICA_2FA_ENABLED=False,
        AUTHENTICA_2FA_PILOT_ENABLED=False,
        AUTHENTICA_2FA_REQUIRE_SUPERUSERS=False,
    )
    def test_system_admin_requires_two_factor_even_when_global_policy_is_off(self):
        call_command("setup_roles")
        system_admin = create_user(
            username="system-admin-no-2fa",
            password=self.password,
            email="system-admin-no-2fa@example.test",
        )
        assign_role_to_user(user=system_admin, role_code="system_admin")

        self.assertTrue(requires_two_factor(system_admin))

        response = self.client.post(
            "/accounts/login/",
            {"username": system_admin.username, "password": self.password},
        )

        self.assertRedirects(response, "/accounts/two-factor/")
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        AUTHENTICA_2FA_ENABLED=False,
        AUTHENTICA_2FA_PILOT_ENABLED=False,
        AUTHENTICA_2FA_REQUIRE_SUPERUSERS=False,
    )
    def test_staff_without_two_factor_is_blocked_from_direct_admin_access(self):
        staff_user = create_user(
            username="staff-no-2fa",
            password=self.password,
            is_staff=True,
            email="staff-no-2fa@example.test",
        )

        self.client.force_login(staff_user)
        response = self.client.get("/admin/")

        self.assertIn(response.status_code, (302, 403))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("admin_two_factor_verified", self.client.session)

    @override_settings(
        AUTHENTICA_2FA_ENABLED=False,
        AUTHENTICA_2FA_PILOT_ENABLED=False,
        AUTHENTICA_2FA_REQUIRE_SUPERUSERS=False,
    )
    def test_missing_profile_does_not_bypass_admin_two_factor_requirement(self):
        admin = create_user(
            username="missing-profile-admin",
            password=self.password,
            is_superuser=True,
            is_staff=True,
            email="missing-profile-admin@example.test",
        )

        self.assertTrue(requires_two_factor(admin))
        response = self.client.post(
            "/accounts/login/",
            {"username": admin.username, "password": self.password},
        )

        self.assertRedirects(response, "/accounts/two-factor/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_normal_login_blocks_external_next_url(self):
        user = create_user(username="redirect-user", password=self.password)
        response = self.client.post(
            "/accounts/login/",
            {
                "username": user.username,
                "password": self.password,
                "next": "https://evil.example",
            },
        )

        self.assertRedirects(response, "/")

    def test_successful_login_persists_safe_audit_events(self):
        self._login()
        self.client.post("/accounts/two-factor/", {"action": "verify", "otp": "123456"})

        events = set(
            TwoFactorAuditLog.objects.filter(user=self.user).values_list("event", flat=True)
        )
        self.assertTrue(
            {
                "2fa_required",
                "2fa_send_started",
                "2fa_send_succeeded",
                "2fa_verify_started",
                "2fa_verify_succeeded",
                "2fa_session_completed",
            }.issubset(events),
            events,
        )
        serialized = str(list(TwoFactorAuditLog.objects.filter(user=self.user).values("metadata")))
        self.assertNotIn("123456", serialized)
        self.assertNotIn(self.employee.phone_number, serialized)
        self.assertNotIn(self.employee.email, serialized)

    def test_audit_service_filters_sensitive_metadata(self):
        from apps.accounts.services.two_factor_audit_service import record_2fa_event

        record_2fa_event(
            user=self.user,
            event="2fa_required",
            metadata={
                "verification_id": 7,
                "otp": "123456",
                "password": "secret-password",
                "recipient": self.employee.phone_number,
                "unknown": "discarded",
            },
        )

        self.assertEqual(TwoFactorAuditLog.objects.get().metadata, {"verification_id": 7})