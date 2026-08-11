from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.breaks.models import Break
from apps.core.tests.factories import (
    create_employee,
    create_shift_type,
)


class BreakModelTests(TestCase):
    """
    اختبارات نموذج الراحة الأسبوعية.
    """

    def setUp(self):
        self.employee = create_employee(
            full_name="موظف اختبار الراحات",
            employee_number="BR-1001",
            is_active=True,
        )

        self.shift_type = create_shift_type(
            name="وردية اختبار الراحات",
            is_active=True,
        )

    def create_break(
        self,
        **overrides,
    ) -> Break:
        data = {
            "employee": self.employee,
            "shift_type": self.shift_type,
            "job_title": Break.BreakJobTitle.MONITOR,
            "rest_days": Break.RestDays.FRIDAY_SATURDAY,
            "is_active": True,
            "notes": "راحة اختبارية",
        }

        data.update(overrides)

        return Break.objects.create(
            **data
        )

    def test_valid_break_is_saved(self):
        """
        يجب حفظ راحة صحيحة.
        """

        break_obj = self.create_break()

        self.assertIsNotNone(
            break_obj.pk
        )

        self.assertTrue(
            break_obj.is_active
        )

    def test_operational_section_follows_employee_gender(self):
        """
        قسم الراحة لا ينفصل عن قسم الموظف التشغيلي.
        """
        self.employee.operational_section = "male"
        self.employee.save(
            update_fields=[
                "operational_section",
                "updated_at",
            ]
        )

        break_obj = self.create_break()

        self.assertEqual(
            break_obj.operational_section,
            "male",
        )
        self.assertEqual(
            break_obj.operational_section_label,
            "رجالي",
        )

    def test_inactive_employee_is_rejected(self):
        """
        لا يمكن إضافة راحة لموظف غير نشط.
        """

        self.employee.is_active = False
        self.employee.work_status = (
            self.employee.WorkStatus.INACTIVE
        )
        self.employee.save(
            update_fields=[
                "is_active",
                "work_status",
                "updated_at",
            ]
        )

        break_obj = Break(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            break_obj.full_clean()

    def test_inactive_shift_type_is_rejected_for_active_break(self):
        """
        لا يمكن إنشاء راحة نشطة على نوع وردية غير نشط.
        """

        self.shift_type.is_active = False
        self.shift_type.save(
            update_fields=[
                "is_active",
            ]
        )

        break_obj = Break(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            break_obj.full_clean()

    def test_inactive_break_can_reference_inactive_shift_type(self):
        """
        يسمح بحفظ سجل راحة غير نشط على نوع وردية غير نشط.
        """

        self.shift_type.is_active = False
        self.shift_type.save(
            update_fields=[
                "is_active",
            ]
        )

        break_obj = Break.objects.create(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=False,
        )

        self.assertFalse(
            break_obj.is_active
        )

    def test_duplicate_active_break_is_rejected(self):
        """
        يمنع وجود راحتين نشطتين للموظف في الوردية نفسها.
        """

        self.create_break()

        duplicate = Break(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.ADMIN,
            rest_days=Break.RestDays.SUNDAY_MONDAY,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            duplicate.full_clean()

    def test_database_rejects_duplicate_active_break(self):
        """
        قاعدة البيانات تمنع التكرار حتى عند تجاوز clean.
        """

        self.create_break()

        with self.assertRaises(
            IntegrityError
        ):
            with transaction.atomic():
                Break.objects.bulk_create(
                    [
                        Break(
                            employee=self.employee,
                            shift_type=self.shift_type,
                            job_title=Break.BreakJobTitle.ADMIN,
                            rest_days=Break.RestDays.SUNDAY_MONDAY,
                            is_active=True,
                        )
                    ]
                )

    def test_inactive_old_break_does_not_block_new_active_break(self):
        """
        الراحة القديمة غير النشطة لا تمنع إنشاء راحة نشطة جديدة.
        """

        self.create_break(
            is_active=False,
        )

        new_break = self.create_break(
            rest_days=Break.RestDays.SUNDAY_MONDAY,
            is_active=True,
        )

        self.assertTrue(
            new_break.is_active
        )

    def test_same_employee_can_have_breaks_in_different_shifts(self):
        """
        يسمح براحة للموظف في نوعي وردية مختلفين.
        """

        self.create_break()

        second_shift = create_shift_type(
            name="وردية راحة ثانية",
            is_active=True,
        )

        second_break = Break.objects.create(
            employee=self.employee,
            shift_type=second_shift,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.SUNDAY_MONDAY,
            is_active=True,
        )

        self.assertIsNotNone(
            second_break.pk
        )

    def test_invalid_job_title_is_rejected(self):
        """
        يجب رفض مسمى تشغيلي غير صحيح.
        """

        break_obj = Break(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title="invalid_job_title",
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
        )

        with self.assertRaises(
            ValidationError
        ):
            break_obj.full_clean()

    def test_invalid_rest_days_are_rejected(self):
        """
        يجب رفض قيمة أيام راحة غير صحيحة.
        """

        break_obj = Break(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days="invalid_rest_days",
        )

        with self.assertRaises(
            ValidationError
        ):
            break_obj.full_clean()

    def test_save_runs_full_clean(self):
        """
        الحفظ المباشر يجب أن يطبق قواعد التحقق.
        """

        self.employee.is_active = False
        self.employee.work_status = (
            self.employee.WorkStatus.INACTIVE
        )
        self.employee.save(
            update_fields=[
                "is_active",
                "work_status",
                "updated_at",
            ]
        )

        break_obj = Break(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
        )

        with self.assertRaises(
            ValidationError
        ):
            break_obj.save()

    def test_status_label_for_active_break(self):
        """
        يجب عرض الحالة العربية للراحة النشطة.
        """

        break_obj = self.create_break()

        self.assertEqual(
            break_obj.status_label,
            "نشط",
        )

    def test_status_label_for_inactive_break(self):
        """
        يجب عرض الحالة العربية للراحة غير النشطة.
        """

        break_obj = self.create_break(
            is_active=False,
        )

        self.assertEqual(
            break_obj.status_label,
            "غير نشط",
        )

    def test_string_representation_contains_employee_and_shift(self):
        """
        النص الظاهر يحتوي الموظف والوردية.
        """

        break_obj = self.create_break()

        text = str(
            break_obj
        )

        self.assertIn(
            self.employee.full_name,
            text,
        )

        self.assertIn(
            self.shift_type.name,
            text,
        )

    def test_snapshot_contains_operational_data(self):
        """
        لقطة الراحة تحتوي البيانات الأساسية.
        """

        break_obj = self.create_break()

        snapshot = break_obj.to_snapshot()

        self.assertEqual(
            snapshot["break_id"],
            break_obj.pk,
        )

        self.assertEqual(
            snapshot["employee_id"],
            self.employee.pk,
        )

        self.assertEqual(
            snapshot["employee_number"],
            self.employee.employee_number,
        )

        self.assertEqual(
            snapshot["shift_type_id"],
            self.shift_type.pk,
        )

        self.assertEqual(
            snapshot["job_title"],
            Break.BreakJobTitle.MONITOR,
        )

        self.assertEqual(
            snapshot["rest_days"],
            Break.RestDays.FRIDAY_SATURDAY,
        )

        self.assertTrue(
            snapshot["is_active"]
        )

        self.assertIsNotNone(
            snapshot["created_at"]
        )