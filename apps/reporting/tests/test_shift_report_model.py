from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.reporting.models import ShiftReport


class ShiftReportModelTests(TestCase):
    """
    اختبارات نموذج تقرير الوردية.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية التقرير",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

    def test_operational_report_requires_finished_shift(self):
        """
        لا يمكن إنشاء تقرير تشغيلي لوردية غير منتهية.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )

        report = ShiftReport(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
        )

        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_finished_shift_can_have_operational_report(self):
        """
        يسمح بإنشاء تقرير لوردية منتهية.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
            is_finished=True,
        )

        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
            total_doors=41,
            open_doors=40,
            closed_doors=1,
        )

        self.assertIsNotNone(report.pk)

    def test_manual_report_requires_summary_or_recommendations(self):
        """
        التقرير الإداري يحتاج ملخصًا أو توصيات.
        """

        report = ShiftReport(
            report_type=ShiftReport.ReportType.MANUAL,
        )

        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_total_doors_validation(self):
        """
        مجموع الحالات لا يتجاوز إجمالي الأبواب.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        report = ShiftReport(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
            total_doors=10,
            open_doors=5,
            closed_doors=5,
            maintenance_doors=1,
        )

        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_completed_maintenance_cannot_exceed_total(self):
        """
        المنجز لا يتجاوز إجمالي الطلبات.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        report = ShiftReport(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
            total_doors=10,
            open_doors=10,
            total_maintenance_requests=2,
            completed_maintenance_requests=3,
        )

        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_report_number_is_generated(self):
        """
        يجب توليد رقم تقرير تلقائيًا.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
            total_doors=41,
            open_doors=41,
        )

        self.assertTrue(
            report.report_number.startswith("SR-")
        )

    def test_report_numbers_are_unique(self):
        """
        أرقام التقارير لا تتكرر.
        """

        first_shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        second_shift = create_shift_plan(
            shift_type=create_shift_type(
                name="وردية ثانية"
            ),
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        first = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=first_shift,
            total_doors=41,
            open_doors=41,
        )

        second = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=second_shift,
            total_doors=41,
            open_doors=40,
            closed_doors=1,
        )

        self.assertNotEqual(
            first.report_number,
            second.report_number,
        )

    def test_maintenance_completion_rate(self):
        """
        حساب نسبة إنجاز الصيانة.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
            total_doors=41,
            open_doors=41,
            total_maintenance_requests=10,
            completed_maintenance_requests=8,
        )

        self.assertEqual(
            report.maintenance_completion_rate,
            80.0,
        )

    def test_open_doors_rate(self):
        """
        حساب نسبة الأبواب المفتوحة.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
            total_doors=40,
            open_doors=30,
            closed_doors=10,
        )

        self.assertEqual(
            report.doors_open_rate,
            75.0,
        )

    def test_unaccounted_doors(self):
        """
        حساب الأبواب غير المحتسبة.
        """

        shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            is_finished=True,
        )

        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=shift,
            total_doors=41,
            open_doors=30,
            closed_doors=5,
            maintenance_doors=3,
        )

        self.assertEqual(
            report.accounted_doors,
            38,
        )

        self.assertEqual(
            report.unaccounted_doors,
            3,
        )