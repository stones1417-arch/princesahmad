from __future__ import annotations

from datetime import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.reporting.models import ShiftReport


User = get_user_model()


class ShiftReportApprovalTests(TestCase):
    """
    اختبارات دورة حياة التقرير واعتماده.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية اعتماد التقرير",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
            is_finished=True,
        )

        self.report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=self.shift,
            status=ShiftReport.ReportStatus.DRAFT,
            total_doors=41,
            open_doors=39,
            closed_doors=1,
            maintenance_doors=1,
            summary="ملخص التقرير التشغيلي",
        )

        self.approver = User.objects.create_user(
            username="report_approver",
            email="report-approver@example.com",
            password="StrongPassword123!",
            is_active=True,
        )

        self.normal_user = User.objects.create_user(
            username="report_normal_user",
            email="report-normal@example.com",
            password="StrongPassword123!",
            is_active=True,
        )

        permission = Permission.objects.get(
            codename="can_approve_shift_report",
            content_type__app_label="reporting",
        )

        self.approver.user_permissions.add(
            permission
        )

    def test_draft_report_can_be_finalized(self):
        """
        يجب تحويل التقرير من مسودة إلى نهائي.
        """

        self.report.finalize()

        self.report.refresh_from_db()

        self.assertEqual(
            self.report.status,
            ShiftReport.ReportStatus.FINAL,
        )

        self.assertTrue(
            self.report.is_final
        )

        self.assertTrue(
            self.report.is_locked
        )

    def test_unsaved_report_cannot_be_finalized(self):
        """
        لا يمكن تحويل تقرير غير محفوظ إلى نهائي.
        """

        report = ShiftReport(
            report_type=ShiftReport.ReportType.MANUAL,
            summary="تقرير غير محفوظ",
        )

        with self.assertRaises(
            ValidationError
        ):
            report.finalize()

    def test_finalizing_final_report_is_rejected(self):
        """
        لا يمكن تحويل التقرير النهائي إلى نهائي مرة أخرى.
        """

        self.report.finalize()

        with self.assertRaises(
            ValidationError
        ):
            self.report.finalize()

    def test_draft_report_cannot_be_approved(self):
        """
        لا يمكن اعتماد تقرير وهو مسودة.
        """

        with self.assertRaises(
            ValidationError
        ):
            self.report.approve(
                self.approver
            )

    def test_user_without_permission_cannot_approve(self):
        """
        المستخدم دون صلاحية لا يستطيع اعتماد التقرير.
        """

        self.report.finalize()

        with self.assertRaises(
            PermissionDenied
        ):
            self.report.approve(
                self.normal_user
            )

    def test_inactive_user_cannot_approve(self):
        """
        المستخدم غير النشط لا يستطيع اعتماد التقرير.
        """

        self.report.finalize()

        self.approver.is_active = False
        self.approver.save(
            update_fields=[
                "is_active",
            ]
        )

        with self.assertRaises(
            PermissionDenied
        ):
            self.report.approve(
                self.approver
            )

    def test_none_user_cannot_approve(self):
        """
        يجب تحديد مستخدم عند اعتماد التقرير.
        """

        self.report.finalize()

        with self.assertRaises(
            ValidationError
        ):
            self.report.approve(
                None
            )

    def test_authorized_user_can_approve_final_report(self):
        """
        المستخدم المخول يستطيع اعتماد التقرير النهائي.
        """

        self.report.finalize()

        self.report.approve(
            self.approver
        )

        self.report.refresh_from_db()

        self.assertEqual(
            self.report.status,
            ShiftReport.ReportStatus.APPROVED,
        )

        self.assertEqual(
            self.report.approved_by_id,
            self.approver.id,
        )

        self.assertIsNotNone(
            self.report.approved_at
        )

        self.assertTrue(
            self.report.is_approved
        )

        self.assertTrue(
            self.report.is_locked
        )

    def test_approved_report_cannot_be_approved_again(self):
        """
        لا يمكن اعتماد التقرير أكثر من مرة.
        """

        self.report.finalize()

        self.report.approve(
            self.approver
        )

        with self.assertRaises(
            ValidationError
        ):
            self.report.approve(
                self.approver
            )

    def test_approved_report_cannot_be_modified(self):
        """
        لا يمكن تعديل تقرير معتمد.
        """

        self.report.finalize()

        self.report.approve(
            self.approver
        )

        self.report.summary = (
            "محاولة تعديل تقرير معتمد"
        )

        with self.assertRaises(
            ValidationError
        ):
            self.report.save()

    def test_final_report_cannot_be_modified_directly(self):
        """
        لا يمكن تعديل تقرير نهائي مباشرة.
        """

        self.report.finalize()

        self.report.summary = (
            "محاولة تعديل التقرير النهائي"
        )

        with self.assertRaises(
            ValidationError
        ):
            self.report.save()

    def test_approved_report_cannot_be_deleted(self):
        """
        لا يمكن حذف تقرير معتمد.
        """

        self.report.finalize()

        self.report.approve(
            self.approver
        )

        with self.assertRaises(
            ValidationError
        ):
            self.report.delete()

        self.assertTrue(
            ShiftReport.objects.filter(
                pk=self.report.pk
            ).exists()
        )

    def test_final_report_cannot_be_deleted(self):
        """
        لا يمكن حذف تقرير نهائي.
        """

        self.report.finalize()

        with self.assertRaises(
            ValidationError
        ):
            self.report.delete()

        self.assertTrue(
            ShiftReport.objects.filter(
                pk=self.report.pk
            ).exists()
        )

    def test_draft_report_can_be_deleted(self):
        """
        يسمح بحذف التقرير وهو مسودة.
        """

        report_pk = self.report.pk

        self.report.delete()

        self.assertFalse(
            ShiftReport.objects.filter(
                pk=report_pk
            ).exists()
        )

    def test_final_report_can_return_to_draft(self):
        """
        يمكن إعادة التقرير النهائي إلى مسودة.
        """

        self.report.finalize()

        self.report.return_to_draft()

        self.report.refresh_from_db()

        self.assertEqual(
            self.report.status,
            ShiftReport.ReportStatus.DRAFT,
        )

        self.assertFalse(
            self.report.is_locked
        )

        self.assertIsNone(
            self.report.approved_by
        )

        self.assertIsNone(
            self.report.approved_at
        )

    def test_approved_report_cannot_return_to_draft(self):
        """
        لا يمكن إعادة تقرير معتمد إلى مسودة.
        """

        self.report.finalize()

        self.report.approve(
            self.approver
        )

        with self.assertRaises(
            ValidationError
        ):
            self.report.return_to_draft()

    def test_draft_report_cannot_return_to_draft_again(self):
        """
        لا يمكن إعادة التقرير إلى مسودة وهو مسودة أصلًا.
        """

        with self.assertRaises(
            ValidationError
        ):
            self.report.return_to_draft()