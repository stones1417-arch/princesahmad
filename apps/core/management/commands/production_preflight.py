import runpy
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from pathlib import Path

from apps.accounts.services.two_factor_preflight import (
    get_global_two_factor_readiness,
)


class Command(BaseCommand):
    help = "Report production configuration readiness without changing data or contacting providers."

    @staticmethod
    def _database_ready():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return False
        return True

    @staticmethod
    def _migrations_ready():
        try:
            executor = MigrationExecutor(connection)
            return not executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception:
            return False

    @staticmethod
    def _secret_key_ready():
        try:
            secret_key = settings.SECRET_KEY
        except ImproperlyConfigured:
            return False
        return bool(secret_key) and not secret_key.startswith("django-insecure-")

    @staticmethod
    def _gunicorn_ready():
        try:
            config = runpy.run_path(settings.BASE_DIR / "gunicorn.conf.py")
        except Exception:
            return False
        return bool(config.get("bind") and config.get("workers", 0) >= 1)

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--check-gunicorn", action="store_true")

    def handle(self, *args, **options):
        is_production = not settings.DEBUG
        database_ready = (
            settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
            and self._database_ready()
        )
        csrf_ready = bool(settings.CSRF_TRUSTED_ORIGINS) and all(
            origin.startswith("https://")
            and "localhost" not in origin
            and "127.0.0.1" not in origin
            for origin in settings.CSRF_TRUSTED_ORIGINS
        )
        hsts_ready = settings.SECURE_HSTS_SECONDS > 0
        https_ready = all(
            (
                settings.SECURE_SSL_REDIRECT,
                settings.SESSION_COOKIE_SECURE,
                settings.CSRF_COOKIE_SECURE,
                hsts_ready,
                settings.SECURE_CONTENT_TYPE_NOSNIFF,
                settings.SECURE_REFERRER_POLICY == "same-origin",
                settings.TRUST_PROXY_HEADERS,
            )
        )
        hosts_ready = bool(settings.ALLOWED_HOSTS) and not any(
            host in {"*", "localhost", "127.0.0.1"}
            for host in settings.ALLOWED_HOSTS
        )
        email_ready = all(
            (
                not settings.EMAIL_BACKEND.endswith("console.EmailBackend"),
                settings.EMAIL_HOST,
                settings.EMAIL_HOST_USER,
                settings.EMAIL_HOST_PASSWORD,
                settings.DEFAULT_FROM_EMAIL,
            )
        )
        authentica_ready = bool(
            settings.AUTHENTICA_BASE_URL
            and settings.AUTHENTICA_API_KEY
            and settings.AUTHENTICA_OTP_REQUEST_ENDPOINT
            and settings.AUTHENTICA_OTP_VERIFY_ENDPOINT
        )
        two_factor = get_global_two_factor_readiness()
        global_two_factor_ready = two_factor["functional_ready"]
        two_factor_ready = authentica_ready and global_two_factor_ready
        configuration_ready = all(
            (
                is_production,
                hosts_ready,
                csrf_ready,
                settings.TRUST_PROXY_HEADERS,
                bool(settings.CELERY_BROKER_URL),
                not settings.CACHES["default"]["BACKEND"].endswith("LocMemCache"),
            )
        )
        static_ready = bool(
            settings.STATIC_ROOT
            and settings.STATIC_URL
            and (Path(settings.STATIC_ROOT) / "staticfiles.json").is_file()
        )
        media_ready = all(
            (
                settings.CLOUDINARY_CLOUD_NAME,
                settings.CLOUDINARY_API_KEY,
                settings.CLOUDINARY_API_SECRET,
            )
        )
        backup_ready = bool(settings.PRODUCTION_BACKUP_VALIDATED)
        data_ready = bool(settings.PRODUCTION_DATA_VALIDATED)
        database_password_present = bool(
            settings.DATABASES["default"].get("PASSWORD")
        )
        gunicorn_ready = self._gunicorn_ready()
        checks = {
            "Django": is_production,
            "Secret key": self._secret_key_ready(),
            "Database": database_ready,
            "Allowed hosts": hosts_ready,
            "HTTPS": https_ready,
            "Cookies": settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
            "CSRF": csrf_ready,
            "Static": static_ready,
            "Media": media_ready,
            "Email": email_ready,
            "SMS": authentica_ready and "sms" in settings.AUTHENTICA_OTP_ALLOWED_CHANNELS,
            "WhatsApp": authentica_ready and "whatsapp" in settings.AUTHENTICA_OTP_ALLOWED_CHANNELS,
            "2FA Core": two_factor_ready,
            "Superusers": two_factor["superusers_ready"],
            "Migrations": self._migrations_ready(),
            "Gunicorn": gunicorn_ready,
        }
        release_checks = {
            "CODE READY": is_production and self._secret_key_ready() and self._migrations_ready(),
            "CONFIGURATION READY": configuration_ready,
            "DATA READY": data_ready,
            "HTTPS READY": https_ready,
            "DATABASE READY": database_ready,
            "STATIC READY": static_ready,
            "MEDIA READY": media_ready,
            "EMAIL READY": email_ready,
            "SMS READY": authentica_ready and "sms" in settings.AUTHENTICA_OTP_ALLOWED_CHANNELS,
            "WHATSAPP READY": authentica_ready and "whatsapp" in settings.AUTHENTICA_OTP_ALLOWED_CHANNELS,
            "2FA READY": two_factor_ready,
            "BACKUP READY": backup_ready,
            "GUNICORN READY": gunicorn_ready,
        }
        safe = all(release_checks.values())

        self.stdout.write("PRODUCTION PREFLIGHT")
        for name, ready in checks.items():
            status = "READY" if ready else ("DEVELOPMENT" if name == "Django" and not is_production else "NOT_READY")
            self.stdout.write(f"{name}: {status}")
        self.stdout.write(
            f"DATABASE ENGINE: {settings.DATABASES['default']['ENGINE']}"
        )
        self.stdout.write(
            f"DATABASE PASSWORD: {'READY' if database_password_present else 'MISSING'}"
        )
        self.stdout.write(f"Active users: {two_factor['active_users']}")
        self.stdout.write(f"2FA ready users: {two_factor['ready_users']}")
        self.stdout.write(f"2FA not ready users: {two_factor['not_ready_users']}")
        self.stdout.write(f"Global 2FA ready: {'YES' if global_two_factor_ready else 'NO'}")
        self.stdout.write(
            f"2FA GLOBAL: {'ENABLED' if settings.AUTHENTICA_2FA_ENABLED else 'DISABLED'}"
        )
        self.stdout.write(
            f"2FA READINESS: {'READY' if global_two_factor_ready else 'NOT_READY'}"
        )
        self.stdout.write(
            f"PRODUCTION HTTPS: {'DEVELOPMENT' if settings.DEBUG else ('READY' if https_ready else 'NOT_READY')}"
        )
        self.stdout.write(
            f"HSTS: {'READY' if hsts_ready else 'WARNING'}"
        )
        if options["check_gunicorn"]:
            self.stdout.write(
                f"GUNICORN CONFIG: {'READY' if gunicorn_ready else 'INVALID'}"
            )
        for name, ready in release_checks.items():
            self.stdout.write(f"{name}: {'PASS' if ready else 'FAIL'}")
        self.stdout.write(f"PRODUCTION READY: {'YES' if safe else 'NO'}")
        self.stdout.write(f"Safe for production deployment: {'YES' if safe else 'NO'}")
        self.stdout.write(f"Safe for production: {'YES' if safe else 'NO'}")
        if options["strict"] and not safe:
            raise CommandError("Production preflight found blocking configuration.")