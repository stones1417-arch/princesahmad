from __future__ import annotations

from datetime import time

from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.reporting.models import ShiftReport


class ShiftReportIndicatorsTests(TestCase):
    """
    اختبارات مؤشرات تقرير الوردية.
    """

    def setUp(self):
        shift_type = create_shift_type(
            name="وردية مؤشرات التقرير",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
            is_finished=True,
        )

    def create_report(
        self,
        **overrides,
    ) -> ShiftReport:
        data = {
            "report_type": (
                ShiftReport
                .ReportType
                .OPERATIONAL
            ),
            "shift_plan": self.shift,
            "total_doors": 41,
            "open_doors": 35,
            "closed_doors": 3,
            "maintenance_doors": 2,
            "total_employees": 80,
            "total_maintenance_requests": 10,
            "completed_maintenance_requests": 8,
        }

        data.update(
            overrides
        )

        return ShiftReport.objects.create(
            **data
        )

    def test_maintenance_completion_rate_is_correct(self):
        """
        يجب حساب نسبة إنجاز الصيانة بصورة صحيحة.
        """

        report = self.create_report()

        self.assertEqual(
            report.maintenance_completion_rate,
            80.0,
        )

    def test_maintenance_completion_rate_is_zero_without_requests(self):
        """
        عند عدم وجود طلبات صيانة تكون النسبة صفرًا.
        """

        report = self.create_report(
            total_maintenance_requests=0,
            completed_maintenance_requests=0,
        )

        self.assertEqual(
            report.maintenance_completion_rate,
            0.0,
        )

    def test_open_doors_rate_is_correct(self):
        """
        يجب حساب نسبة الأبواب المفتوحة بصورة صحيحة.
        """

        report = self.create_report(
            total_doors=40,
            open_doors=30,
            closed_doors=5,
            maintenance_doors=5,
        )

        self.assertEqual(
            report.doors_open_rate,
            75.0,
        )

    def test_open_doors_rate_is_zero_without_doors(self):
        """
        عند عدم وجود أبواب تكون النسبة صفرًا.
        """

        report = self.create_report(
            total_doors=0,
            open_doors=0,
            closed_doors=0,
            maintenance_doors=0,
        )

        self.assertEqual(
            report.doors_open_rate,
            0.0,
        )

    def test_accounted_doors_is_correct(self):
        """
        يجب حساب عدد الأبواب المحتسبة.
        """

        report = self.create_report(
            total_doors=41,
            open_doors=30,
            closed_doors=5,
            maintenance_doors=3,
        )

        self.assertEqual(
            report.accounted_doors,
            38,
        )

    def test_unaccounted_doors_is_correct(self):
        """
        يجب حساب عدد الأبواب غير المحتسبة.
        """

        report = self.create_report(
            total_doors=41,
            open_doors=30,
            closed_doors=5,
            maintenance_doors=3,
        )

        self.assertEqual(
            report.unaccounted_doors,
            3,
        )

    def test_unaccounted_doors_never_becomes_negative(self):
        """
        لا يجب أن تكون قيمة الأبواب غير المحتسبة سالبة.
        """

        report = ShiftReport(
            report_type=(
                ShiftReport
                .ReportType
                .OPERATIONAL
            ),
            shift_plan=self.shift,
            total_doors=10,
            open_doors=8,
            closed_doors=4,
            maintenance_doors=1,
        )

        self.assertEqual(
            report.unaccounted_doors,
            0,
        )

    def test_draft_report_is_not_locked(self):
        """
        التقرير المسودة لا يعتبر مقفلًا.
        """

        report = self.create_report(
            status=(
                ShiftReport
                .ReportStatus
                .DRAFT
            )
        )

        self.assertFalse(
            report.is_locked
        )

    def test_final_report_is_locked(self):
        """
        التقرير النهائي يعتبر مقفلًا.
        """

        report = self.create_report()

        report.finalize()

        self.assertTrue(
            report.is_locked
        )

        self.assertTrue(
            report.is_final
        )

    def test_approved_report_is_locked(self):
        """
        التقرير المعتمد يعتبر مقفلًا.
        """

        report = self.create_report()

        report.status = (
            ShiftReport
            .ReportStatus
            .APPROVED
        )

        self.assertTrue(
            report.is_locked
        )

        self.assertTrue(
            report.is_approved
        )