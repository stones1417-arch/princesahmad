from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import AccountProfile
from apps.accounts.services.two_factor_readiness import get_user_2fa_readiness_details, is_user_2fa_ready
from apps.core.tests.factories import create_user


@override_settings(
    AUTHENTICA_2FA_ENABLED=False,
    AUTHENTICA_2FA_PILOT_ENABLED=False,
    AUTHENTICA_2FA_REQUIRE_SUPERUSERS=False,
    AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"),
)
class TwoFactorReadinessTests(TestCase):
    password = "StrongTestPassword123!"

    def test_email_only_user_is_ready(self):
        user = create_user(username="email-ready", password=self.password, email="ready@example.test")

        self.assertTrue(is_user_2fa_ready(user))

    def test_user_without_channels_is_not_ready(self):
        user = create_user(username="not-ready", password=self.password)
        user.email = ""
        user.save(update_fields=["email"])

        self.assertFalse(is_user_2fa_ready(user))

    def test_readiness_details_identify_missing_contacts_without_exposure(self):
        user = create_user(username="not-ready-report", password=self.password)
        user.email = ""
        user.save(update_fields=["email"])

        details = get_user_2fa_readiness_details(user)

        self.assertEqual(details["reason"], "No OTP contact details")
        self.assertEqual(details["email_masked"], "-")
        self.assertEqual(details["phone_masked"], "-")
        self.assertEqual(details["classification"], "Real account needs 2FA setup")

    def test_global_readiness_report_masks_valid_contact_values(self):
        user = create_user(username="masked-report", password=self.password, email="masked@example.test")
        output = StringIO()

        call_command("audit_2fa_readiness", "--global-readiness", stdout=output)

        self.assertIn(user.username, output.getvalue())
        self.assertNotIn(user.email, output.getvalue())
        self.assertIn("ma***@example.test", output.getvalue())

    def test_profile_phone_makes_admin_ready(self):
        user = create_user(username="admin-ready", password=self.password, is_staff=True)
        AccountProfile.objects.create(user=user, phone_number="+966501234567")

        self.assertTrue(is_user_2fa_ready(user))

    def test_required_only_uses_current_policy(self):
        user = create_user(username="ordinary", password=self.password)
        output = StringIO()

        call_command("audit_2fa_readiness", "--required-only", stdout=output)

        self.assertNotIn(user.username, output.getvalue())

    def test_global_readiness_strict_rejects_active_user_without_channel(self):
        user = create_user(username="global-blocker", password=self.password)
        user.email = ""
        user.save(update_fields=["email"])

        with self.assertRaises(CommandError):
            call_command("audit_2fa_readiness", "--global-readiness", "--strict")


@override_settings(
    DEBUG=True,
    AUTHENTICA_API_KEY="test-api-key",
    AUTHENTICA_BASE_URL="https://authentica.example.test",
    AUTHENTICA_OTP_REQUEST_ENDPOINT="/send-otp",
    AUTHENTICA_OTP_VERIFY_ENDPOINT="/verify-otp",
    AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"),
    AUTHENTICA_2FA_REQUIRE_SUPERUSERS=True,
)
class TwoFactorPreflightTests(TestCase):
    password = "StrongTestPassword123!"

    def _ready_user(self, username="ready-user", *, superuser=False):
        user = create_user(
            username=username,
            password=self.password,
            is_staff=superuser,
            is_superuser=superuser,
            email=f"{username}@example.test",
        )
        return user

    def test_functional_readiness_is_yes_when_all_active_users_are_ready(self):
        self._ready_user("ahmad")
        self._ready_user("admin", superuser=True)
        output = StringIO()

        call_command("authentica_2fa_preflight", "--functional-strict", stdout=output)

        self.assertIn("Functional global 2FA readiness: YES", output.getvalue())
        self.assertIn("Production HTTPS: DEVELOPMENT", output.getvalue())
        self.assertIn("Production global 2FA readiness: NO", output.getvalue())
        self.assertNotIn("ahmad@example.test", output.getvalue())

    def test_functional_readiness_is_no_when_an_active_user_has_no_channel(self):
        self._ready_user()
        missing = create_user(username="not-ready", password=self.password)
        missing.email = ""
        missing.save(update_fields=["email"])

        with self.assertRaises(CommandError):
            call_command("authentica_2fa_preflight", "--functional-strict")

    def test_production_strict_fails_in_debug(self):
        self._ready_user()

        with self.assertRaises(CommandError):
            call_command("authentica_2fa_preflight", "--production-strict")

    @override_settings(
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        SECURE_HSTS_SECONDS=0,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=False,
        SECURE_CONTENT_TYPE_NOSNIFF=False,
        SECURE_REFERRER_POLICY="strict-origin-when-cross-origin",
    )
    def test_production_readiness_is_no_with_incomplete_https_settings(self):
        self._ready_user()
        output = StringIO()

        call_command("authentica_2fa_preflight", stdout=output)

        self.assertIn("Functional global 2FA readiness: YES", output.getvalue())
        self.assertIn("Production global 2FA readiness: NO", output.getvalue())

    @override_settings(
        DEBUG=False,
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_CONTENT_TYPE_NOSNIFF=True,
        SECURE_REFERRER_POLICY="same-origin",
    )
    def test_production_readiness_is_yes_only_with_complete_mocked_settings(self):
        self._ready_user("ahmad")
        self._ready_user("admin", superuser=True)
        output = StringIO()

        call_command("authentica_2fa_preflight", "--production-strict", stdout=output)

        self.assertIn("Functional global 2FA readiness: YES", output.getvalue())
        self.assertIn("Production HTTPS: READY", output.getvalue())
        self.assertIn("Production global 2FA readiness: YES", output.getvalue())