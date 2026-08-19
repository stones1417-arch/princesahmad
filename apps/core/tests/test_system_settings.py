from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import SystemConfiguration
from apps.core.system_settings import (
    ConcurrentSettingsUpdate,
    ServiceStatus,
    SystemHealthService,
    SystemSettingsService,
)
from apps.core.tests.factories import create_door
from apps.dashboard.models import SystemActivityLog
from apps.locations.door_directions import OFFICIAL_DOOR_CODES


class SystemSettingsCenterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(username="settings-admin")
        cls.viewer = get_user_model().objects.create_user(username="settings-viewer")
        cls.outsider = get_user_model().objects.create_user(username="settings-outsider")
        view_permission = Permission.objects.get(
            content_type__app_label="core",
            codename="view_systemconfiguration",
        )
        change_permission = Permission.objects.get(
            content_type__app_label="core",
            codename="change_systemconfiguration",
        )
        cls.admin.user_permissions.add(view_permission, change_permission)
        cls.viewer.user_permissions.add(view_permission)

    def setUp(self):
        cache.clear()
        self.url = reverse("core:system-settings")
        self.health_patch = patch.object(
            SystemHealthService,
            "collect",
            return_value=[
                ServiceStatus("database", "PostgreSQL", "operational", "قاعدة البيانات")
            ],
        )
        self.health_patch.start()
        self.addCleanup(self.health_patch.stop)

    def _post_data(self, configuration=None, **overrides):
        configuration = configuration or SystemSettingsService.get_settings()
        data = {
            "organization_name": configuration.organization_name,
            "platform_name": configuration.platform_name,
            "timezone": configuration.timezone,
            "default_language": configuration.default_language,
            "support_email": configuration.support_email,
            "support_phone": configuration.support_phone,
            "communications_enabled": "on",
            "email_notifications_enabled": "on",
            "sms_notifications_enabled": "on",
            "updated_at": configuration.updated_at.isoformat(),
        }
        data.update(overrides)
        return data

    def test_anonymous_is_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_unauthorized_user_gets_403(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_authorized_view_is_200(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_read_only_user_cannot_post(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(self.url, self._post_data()).status_code, 403)

    def test_admin_updates_safe_setting_and_creates_audit_record(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            self._post_data(platform_name="بوابة أبواب المؤسسية"),
        )
        self.assertRedirects(response, self.url)
        configuration = SystemConfiguration.objects.get(pk=1)
        self.assertEqual(configuration.platform_name, "بوابة أبواب المؤسسية")
        log = SystemActivityLog.objects.get(module="إعدادات النظام")
        self.assertEqual(log.user, self.admin)
        self.assertIn("platform_name", log.description)
        self.assertNotIn("بوابة أبواب المؤسسية", log.description)

    def test_invalid_input_returns_field_error_without_500(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            self._post_data(support_email="not-an-email"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "support_email", html=False)

    def test_transaction_rolls_back_when_audit_write_fails(self):
        configuration = SystemSettingsService.get_settings()
        original = configuration.platform_name
        with patch(
            "apps.core.system_settings.log_activity",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                SystemSettingsService.update_settings(
                    values={"platform_name": "must rollback"},
                    expected_updated_at=configuration.updated_at,
                )
        configuration.refresh_from_db()
        self.assertEqual(configuration.platform_name, original)

    def test_optimistic_concurrency_rejects_stale_update(self):
        configuration = SystemSettingsService.get_settings()
        stale_timestamp = configuration.updated_at
        SystemSettingsService.update_settings(
            values={"platform_name": "first update"},
            expected_updated_at=stale_timestamp,
        )
        with self.assertRaises(ConcurrentSettingsUpdate):
            SystemSettingsService.update_settings(
                values={"platform_name": "silent overwrite"},
                expected_updated_at=stale_timestamp,
            )

    def test_database_constraint_rejects_a_second_configuration_row(self):
        SystemSettingsService.get_settings()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SystemConfiguration.objects.bulk_create(
                [SystemConfiguration(pk=2)]
            )
        self.assertLessEqual(SystemConfiguration.objects.count(), 1)

    def test_get_settings_recreates_missing_singleton(self):
        SystemConfiguration.objects.all().delete()
        cache.clear()

        configuration = SystemSettingsService.get_settings()

        self.assertEqual(configuration.pk, SystemConfiguration.SINGLETON_PK)
        self.assertEqual(SystemConfiguration.objects.count(), 1)

    @override_settings(
        DATABASE_URL="database-sentinel",
        REDIS_URL="redis-sentinel",
        DJANGO_SECRET_KEY="django-sentinel",
        FOURJAWALY_API_SECRET="sms-sentinel",
        EMAIL_HOST_PASSWORD="email-sentinel",
        CLOUDINARY_API_SECRET="cloud-sentinel",
    )
    def test_secrets_and_environment_values_never_appear_in_html(self):
        self.client.force_login(self.viewer)
        content = self.client.get(self.url).content.decode()
        for forbidden in (
            "DATABASE_URL",
            "REDIS_URL",
            "DJANGO_SECRET_KEY",
            "FOURJAWALY_API_SECRET",
            "EMAIL_HOST_PASSWORD",
            "CLOUDINARY_API_SECRET",
            "-sentinel",
        ):
            self.assertNotIn(forbidden, content)

    def test_environment_panel_exposes_status_only(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.url)
        self.assertContains(response, "Configured")
        self.assertNotContains(response, "redis://")
        self.assertNotContains(response, "postgres://")

    @override_settings(TOTAL_DOORS_COUNT=41)
    def test_active_door_count_is_dynamic_and_ignores_stale_setting(self):
        for code in OFFICIAL_DOOR_CODES:
            create_door(door_number=code)
        self.client.force_login(self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.context["metrics"]["active_doors"], 42)
        self.assertNotContains(response, "TOTAL_DOORS_COUNT")

    @override_settings(COMMUNICATIONS_ENABLED=True)
    def test_communications_flag_changes_runtime_behavior(self):
        configuration = SystemSettingsService.get_settings()
        SystemSettingsService.update_settings(
            values={"communications_enabled": False},
            expected_updated_at=configuration.updated_at,
        )
        self.assertFalse(
            SystemSettingsService.get_effective_value("communications_enabled")
        )
        from apps.communications.providers.authentica import (
            AuthenticaProvider,
            ProviderConnectionError,
        )

        with self.assertRaises(ProviderConnectionError):
            AuthenticaProvider._ensure_communications_enabled()

    def test_cache_invalidates_after_update(self):
        configuration = SystemSettingsService.get_settings()
        self.assertIsNotNone(cache.get(SystemSettingsService.CACHE_KEY))
        SystemSettingsService.update_settings(
            values={"platform_name": "cache update"},
            expected_updated_at=configuration.updated_at,
        )
        self.assertIsNone(cache.get(SystemSettingsService.CACHE_KEY))

    def test_get_never_sends_external_email_or_sms(self):
        self.client.force_login(self.viewer)
        with patch("django.core.mail.send_mail") as send_mail, patch(
            "apps.communications.providers.authentica.AuthenticaProvider.send_operational_sms"
        ) as send_sms:
            self.assertEqual(self.client.get(self.url).status_code, 200)
        send_mail.assert_not_called()
        send_sms.assert_not_called()

    def test_health_failure_renders_warning_not_500(self):
        self.health_patch.stop()
        self.addCleanup(lambda: None)
        with patch.object(
            SystemHealthService,
            "collect",
            return_value=[
                ServiceStatus("redis", "Redis", "unavailable", "ذاكرة مشتركة")
            ],
        ):
            self.client.force_login(self.viewer)
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "status-unavailable")
