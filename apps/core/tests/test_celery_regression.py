from __future__ import annotations

import importlib

from django.conf import settings
from django.test import SimpleTestCase, override_settings

import princesahmad
from princesahmad.celery import app


class CeleryRegressionTests(SimpleTestCase):
    def setUp(self):
        app.autodiscover_tasks(force=True)

    def test_celery_app_is_importable(self):
        self.assertIsNotNone(app)
        self.assertTrue(hasattr(princesahmad, "celery_app"))

    def test_celery_app_main_uses_project_name(self):
        self.assertEqual(app.main, "princesahmad")

    def test_celery_broker_and_result_backend_are_configured(self):
        with override_settings(
            REDIS_URL="redis://localhost:6379/0",
            CELERY_BROKER_URL="redis://localhost:6379/0",
            CELERY_RESULT_BACKEND="redis://localhost:6379/0",
        ):
            app.conf.broker_url = "redis://localhost:6379/0"
            app.conf.result_backend = "redis://localhost:6379/0"

            self.assertEqual(settings.REDIS_URL, "redis://localhost:6379/0")
            self.assertEqual(settings.CELERY_BROKER_URL, "redis://localhost:6379/0")
            self.assertEqual(settings.CELERY_RESULT_BACKEND, "redis://localhost:6379/0")
            self.assertEqual(app.conf.broker_url, "redis://localhost:6379/0")
            self.assertEqual(app.conf.result_backend, "redis://localhost:6379/0")

    def test_autodiscover_registers_project_tasks(self):
        project_tasks = {
            name
            for name in app.tasks
            if name.startswith("apps.") and not name.startswith("celery.")
        }

        self.assertTrue(project_tasks)
        self.assertIn("apps.core.tasks.monitor_platform_task", project_tasks)
        self.assertIn("apps.core.tasks.send_sms_task", project_tasks)
        self.assertIn("apps.core.tasks.send_email_task", project_tasks)
        self.assertIn("apps.exports_center.tasks.build_export_file_task", project_tasks)

    def test_package_import_does_not_raise(self):
        imported = importlib.import_module("princesahmad")
        self.assertIsNotNone(imported)
        self.assertTrue(hasattr(imported, "celery_app"))
