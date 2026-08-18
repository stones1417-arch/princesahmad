from __future__ import annotations

import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.exports_center.models import ExportLog
from apps.exports_center.tasks import build_export_file_task


class ExportBackgroundTaskTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="export-task-tests-")
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.user = get_user_model().objects.create_user(
            username="export_task_user",
            password="StrongPassword123!",
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def create_export_log(self) -> ExportLog:
        return ExportLog.objects.create(
            user=self.user,
            module="الموارد البشرية",
            report_key="employees",
            report_name="سجل الموظفين",
            file_name="employees.csv",
            export_format=ExportLog.ExportFormat.CSV,
            status=ExportLog.ExportStatus.PENDING,
            filters={},
            metadata={"selected_columns": ["full_name"]},
        )

    def test_task_builds_and_stores_export_file(self):
        export_log = self.create_export_log()

        result = build_export_file_task(export_log.pk)

        export_log.refresh_from_db()
        self.assertEqual(result["status"], "success")
        self.assertEqual(export_log.status, ExportLog.ExportStatus.SUCCESS)
        self.assertTrue(export_log.file.storage.exists(export_log.file.name))

    def test_task_records_export_failure(self):
        export_log = self.create_export_log()

        with patch(
            "apps.exports_center.tasks.export_report",
            side_effect=RuntimeError("export unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                build_export_file_task(export_log.pk)

        export_log.refresh_from_db()
        self.assertEqual(export_log.status, ExportLog.ExportStatus.FAILED)
        self.assertIn("export unavailable", export_log.error_message)