from __future__ import annotations

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.exports_center.models import ExportLog


class ExportWorkflowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="exports-center-tests-")
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.user = get_user_model().objects.create_user(
            username="exports_workflow_user",
            password="StrongPassword123!",
        )
        self.client.force_login(self.user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_csv_export_is_logged_and_stored(self):
        response = self.client.get(
            reverse(
                "exports_center:export",
                kwargs={"report_key": "employees", "export_format": "csv"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        export_log = ExportLog.objects.get()
        self.assertEqual(export_log.status, ExportLog.ExportStatus.SUCCESS)
        self.assertEqual(response["X-Export-Log-ID"], str(export_log.pk))
        self.assertTrue(export_log.file.storage.exists(export_log.file.name))

    def test_stored_export_can_be_downloaded_again(self):
        first_response = self.client.get(
            reverse(
                "exports_center:export",
                kwargs={"report_key": "employees", "export_format": "csv"},
            )
        )
        export_log = ExportLog.objects.get(pk=first_response["X-Export-Log-ID"])

        response = self.client.get(
            reverse(
                "exports_center:download-export",
                kwargs={"export_log_id": export_log.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        export_log.refresh_from_db()
        self.assertEqual(export_log.download_count, 1)

    def test_unsupported_format_creates_failed_audit_entry(self):
        response = self.client.get(
            reverse(
                "exports_center:export",
                kwargs={"report_key": "employees", "export_format": "random"},
            )
        )

        self.assertEqual(response.status_code, 302)
        export_log = ExportLog.objects.get()
        self.assertEqual(export_log.status, ExportLog.ExportStatus.FAILED)
        self.assertTrue(export_log.error_message)
