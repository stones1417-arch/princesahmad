from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.core.tests.factories import create_user


class ProductionPreflightTests(TestCase):
    @override_settings(DEBUG=True)
    def test_development_never_reports_safe_for_production(self):
        output = StringIO()
        users_before = self._user_count()

        call_command("production_preflight", stdout=output)

        self.assertIn("Django: DEVELOPMENT", output.getvalue())
        self.assertIn("CODE READY: FAIL", output.getvalue())
        self.assertIn("PRODUCTION READY: NO", output.getvalue())
        self.assertIn("Safe for production: NO", output.getvalue())
        self.assertEqual(self._user_count(), users_before)

    @override_settings(DEBUG=True)
    def test_strict_rejects_development_configuration(self):
        with self.assertRaises(CommandError):
            call_command("production_preflight", "--strict")

    @override_settings(DEBUG=True)
    def test_preflight_reports_missing_database_password_without_printing_values(self):
        output = StringIO()
        with override_settings(
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": "platform",
                    "USER": "platform_user",
                    "PASSWORD": "",
                    "HOST": "127.0.0.1",
                    "PORT": "5432",
                },
            }
        ):
            call_command("production_preflight", stdout=output)

        self.assertIn("DATABASE PASSWORD: MISSING", output.getvalue())
        self.assertNotIn("platform_user", output.getvalue())

    @override_settings(DEBUG=True)
    def test_preflight_uses_dynamic_two_factor_user_counts(self):
        create_user(username="ready", password="StrongTestPassword123!", email="ready@example.test")
        missing = create_user(username="missing", password="StrongTestPassword123!")
        missing.email = ""
        missing.save(update_fields=["email"])
        output = StringIO()

        call_command("production_preflight", stdout=output)

        self.assertIn("Active users: 2", output.getvalue())
        self.assertIn("2FA ready users: 1", output.getvalue())
        self.assertIn("2FA not ready users: 1", output.getvalue())
        self.assertIn("Global 2FA ready: NO", output.getvalue())

    @override_settings(DEBUG=True)
    def test_gunicorn_check_is_safe_and_reports_valid_config(self):
        output = StringIO()

        call_command("production_preflight", "--check-gunicorn", stdout=output)

        self.assertIn("GUNICORN CONFIG: READY", output.getvalue())

    @override_settings(
        DEBUG=False,
        SECRET_KEY="production-test-secret-key",
        ALLOWED_HOSTS=["*"],
        CSRF_TRUSTED_ORIGINS=["https://platform.example.test"],
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
        SECURE_REFERRER_POLICY="same-origin",
    )
    def test_wildcard_host_is_not_production_ready(self):
        output = StringIO()

        call_command("production_preflight", stdout=output)

        self.assertIn("Allowed hosts: NOT_READY", output.getvalue())
        self.assertIn("CONFIGURATION READY: FAIL", output.getvalue())
        self.assertIn("PRODUCTION READY: NO", output.getvalue())
        self.assertIn("Safe for production: NO", output.getvalue())
        self.assertNotIn("production-test-secret-key", output.getvalue())

    @override_settings(
        DEBUG=False,
        SECRET_KEY="",
        ALLOWED_HOSTS=["platform.example.test"],
        CSRF_TRUSTED_ORIGINS=["https://platform.example.test"],
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
        SECURE_REFERRER_POLICY="same-origin",
    )
    def test_missing_secret_key_is_not_production_ready(self):
        output = StringIO()

        call_command("production_preflight", stdout=output)

        self.assertIn("Secret key: NOT_READY", output.getvalue())
        self.assertIn("CODE READY: FAIL", output.getvalue())
        self.assertIn("PRODUCTION READY: NO", output.getvalue())
        self.assertIn("Safe for production: NO", output.getvalue())

    def _user_count(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.count()