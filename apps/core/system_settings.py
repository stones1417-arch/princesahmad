from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog

from .models import SystemConfiguration


class ConcurrentSettingsUpdate(ValidationError):
    pass


class SystemSettingsService:
    CACHE_KEY = "core:system-configuration:v1"
    EDITABLE_FIELDS = (
        "organization_name",
        "platform_name",
        "timezone",
        "default_language",
        "support_email",
        "support_phone",
        "communications_enabled",
        "email_notifications_enabled",
        "sms_notifications_enabled",
    )

    @classmethod
    def get_settings(cls) -> SystemConfiguration:
        configuration = cache.get(cls.CACHE_KEY)
        if configuration is not None:
            return configuration
        configuration, _ = SystemConfiguration.objects.get_or_create(
            pk=SystemConfiguration.SINGLETON_PK
        )
        cache.set(cls.CACHE_KEY, configuration, timeout=None)
        return configuration

    @classmethod
    def get_effective_value(cls, name: str):
        configuration = cls.get_settings()
        if name == "communications_enabled":
            return bool(
                django_settings.COMMUNICATIONS_ENABLED
                and configuration.communications_enabled
            )
        if name == "email_notifications_enabled":
            return bool(
                cls.get_effective_value("communications_enabled")
                and configuration.email_notifications_enabled
            )
        if name == "sms_notifications_enabled":
            return bool(
                cls.get_effective_value("communications_enabled")
                and configuration.sms_notifications_enabled
            )
        if name not in cls.EDITABLE_FIELDS:
            raise KeyError(name)
        return getattr(configuration, name)

    @classmethod
    def update_settings(
        cls,
        *,
        values: dict,
        request=None,
        expected_updated_at=None,
    ) -> SystemConfiguration:
        safe_values = {
            key: value
            for key, value in values.items()
            if key in cls.EDITABLE_FIELDS
        }
        with transaction.atomic():
            configuration = (
                SystemConfiguration.objects.select_for_update().get(
                    pk=SystemConfiguration.SINGLETON_PK
                )
            )
            if (
                expected_updated_at
                and configuration.updated_at != expected_updated_at
            ):
                raise ConcurrentSettingsUpdate(
                    "تم تعديل الإعدادات بواسطة مستخدم آخر. حدّث الصفحة ثم أعد المحاولة."
                )

            changes = {}
            for field, value in safe_values.items():
                old_value = getattr(configuration, field)
                if old_value != value:
                    changes[field] = (old_value, value)
                    setattr(configuration, field, value)

            if changes:
                configuration.save()
                changed_fields = "، ".join(sorted(changes))
                log_activity(
                    user=getattr(request, "user", None),
                    module="إعدادات النظام",
                    action=SystemActivityLog.ActionType.UPDATE,
                    description=f"تم تحديث إعدادات النظام: {changed_fields}",
                    request=request,
                )
                transaction.on_commit(cls.invalidate_cache)

        cls.invalidate_cache()
        return configuration

    @classmethod
    def invalidate_cache(cls) -> None:
        cache.delete(cls.CACHE_KEY)


@dataclass(frozen=True)
class ServiceStatus:
    key: str
    label: str
    status: str
    detail: str


class SystemHealthService:
    OPERATIONAL = "operational"
    WARNING = "warning"
    UNAVAILABLE = "unavailable"

    @classmethod
    def collect(cls) -> list[ServiceStatus]:
        return [
            cls._database(),
            cls._redis(),
            cls._celery(),
            cls._cloudinary(),
            cls._email(),
            cls._sms(),
        ]

    @classmethod
    def _database(cls):
        from django.db import connection

        try:
            connection.ensure_connection()
            status = cls.OPERATIONAL
        except Exception:
            status = cls.UNAVAILABLE
        return ServiceStatus("database", "PostgreSQL", status, "قاعدة البيانات")

    @classmethod
    def _redis(cls):
        if not getattr(django_settings, "REDIS_URL", ""):
            return ServiceStatus("redis", "Redis", cls.WARNING, "غير مهيأ")
        try:
            import redis

            client = redis.Redis.from_url(
                django_settings.REDIS_URL,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            status = cls.OPERATIONAL if client.ping() else cls.UNAVAILABLE
        except Exception:
            status = cls.UNAVAILABLE
        return ServiceStatus("redis", "Redis", status, "ذاكرة مشتركة")

    @classmethod
    def _celery(cls):
        if not getattr(django_settings, "CELERY_BROKER_URL", ""):
            return ServiceStatus("celery", "Celery Worker", cls.WARNING, "غير مهيأ")
        try:
            from princesahmad.celery import app

            online = bool(app.control.inspect(timeout=0.5).ping() or {})
            status = cls.OPERATIONAL if online else cls.WARNING
        except Exception:
            status = cls.WARNING
        return ServiceStatus("celery", "Celery Worker", status, "عامل الخلفية")

    @classmethod
    def _cloudinary(cls):
        configured = all(
            getattr(django_settings, name, "")
            for name in (
                "CLOUDINARY_CLOUD_NAME",
                "CLOUDINARY_API_KEY",
                "CLOUDINARY_API_SECRET",
            )
        )
        return ServiceStatus(
            "cloudinary",
            "Cloudinary Storage",
            cls.OPERATIONAL if configured else cls.WARNING,
            "التخزين السحابي",
        )

    @classmethod
    def _email(cls):
        configured = bool(
            django_settings.EMAIL_BACKEND
            and django_settings.EMAIL_HOST
            and django_settings.DEFAULT_FROM_EMAIL
        )
        return ServiceStatus(
            "email", "Email", cls.OPERATIONAL if configured else cls.WARNING, "SMTP"
        )

    @classmethod
    def _sms(cls):
        credentials = bool(
            getattr(django_settings, "FOURJAWALY_API_KEY", "")
            and getattr(django_settings, "FOURJAWALY_API_SECRET", "")
        )
        sender = bool(getattr(django_settings, "FOURJAWALY_SENDER_ID", ""))
        status = cls.OPERATIONAL if credentials and sender else cls.WARNING
        return ServiceStatus(
            "sms", "SMS Provider", status, "يتطلب تفعيل مزود الخدمة" if not sender else "4jawaly"
        )
