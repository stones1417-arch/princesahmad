from __future__ import annotations

import shutil
import tempfile

from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.factories import (
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.exports_center.models import ExportLog
from apps.reporting.models import ShiftReport
from apps.roles.models import Role, UserRole


@override_settings(ASYNC_EXPORTS_ENABLED=False)
class LoginReportExportCycleTests(TestCase):
    """Exercise an authenticated report approval and export workflow."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="cycle-export-tests-")
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.password = "CyclePassword123!"
        self.user = create_user(
            username="report_export_cycle_user",
            password=self.password,
        )
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="create_report",
            ),
            Permission.objects.get(
                content_type__app_label="roles",
                codename="approve_report",
            ),
            Permission.objects.get(
                content_type__app_label="roles",
                codename="view_reports",
            ),
            Permission.objects.get(
                content_type__app_label="reporting",
                codename="can_approve_shift_report",
            ),
        )
        group = Group.objects.create(name="report-export-cycle")
        group.permissions.add(
            Permission.objects.get(content_type__app_label="roles", codename="export_report"),
        )
        role = Role.objects.create(code="report-export-cycle", name="report-export-cycle", group=group)
        UserRole.objects.create(user=self.user, role=role)
        shift_type = create_shift_type(name="وردية دورة التشغيل")
        self.shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )
        create_employee(
            full_name="موظف تصدير رجالي",
            employee_number="CYCLE-M-1",
            operational_section="male",
        )
        create_employee(
            full_name="موظفة تصدير نسائي",
            employee_number="CYCLE-F-1",
            operational_section="female",
        )

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_login_generate_approve_and_export_report_cycle(self):
        self.assertTrue(
            self.client.login(
                username=self.user.username,
                password=self.password,
            )
        )

        generate_response = self.client.post(
            reverse("reporting:generate", kwargs={"pk": self.shift.pk})
        )
        self.assertEqual(generate_response.status_code, 302)
        report = ShiftReport.objects.get(shift_plan=self.shift)
        self.assertEqual(report.status, ShiftReport.ReportStatus.FINAL)

        approve_response = self.client.post(
            reverse("reporting:approve", kwargs={"pk": report.pk})
        )
        self.assertEqual(approve_response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, ShiftReport.ReportStatus.APPROVED)
        self.assertEqual(report.approved_by_id, self.user.pk)

        export_response = self.client.post(
            reverse(
                "exports_center:export",
                kwargs={
                    "report_key": "employees",
                    "export_format": "csv",
                },
            ),
            {"section": "male"},
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("text/csv", export_response["Content-Type"])

        export_log = ExportLog.objects.get(
            report_key="employees",
            user=self.user,
        )
        self.assertEqual(export_log.status, ExportLog.ExportStatus.SUCCESS)
        self.assertEqual(export_log.filters["section"], "male")
        self.assertTrue(export_log.file.storage.exists(export_log.file.name))