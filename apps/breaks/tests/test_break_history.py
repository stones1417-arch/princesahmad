from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.breaks.models import (
    Break,
    BreakHistory,
)
from apps.core.tests.factories import (
    create_employee,
    create_shift_type,
)


User = get_user_model()


class BreakHistoryModelTests(TestCase):
    """
    اختبارات سجل تدقيق الراحات.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="break_history_user",
            password="StrongPassword123!",
            is_active=True,
        )

        self.employee = create_employee(
            full_name="موظف سجل الراحات",
            employee_number="BR-H-1001",
        )

        self.shift_type = create_shift_type(
            name="وردية سجل الراحات",
        )

        self.break_obj = Break.objects.create(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=True,
        )

    def create_history(
        self,
        **overrides,
    ) -> BreakHistory:
        data = {
            "break_record": self.break_obj,
            "break_id_snapshot": self.break_obj.pk,
            "employee": self.employee,
            "shift_type": self.shift_type,
            "action": BreakHistory.Action.CREATE,
            "old_value": {},
            "new_value": self.break_obj.to_snapshot(),
            "performed_by": self.user,
            "reason": "اختبار السجل",
            "ip_address": "127.0.0.1",
        }

        data.update(overrides)

        return BreakHistory.objects.create(
            **data
        )

    def test_history_can_be_created(self):
        """
        يجب إنشاء سجل تدقيق للراحة.
        """

        history = self.create_history()

        self.assertIsNotNone(
            history.pk
        )

    def test_history_keeps_break_id_snapshot(self):
        """
        يجب حفظ معرف الراحة داخل اللقطة.
        """

        history = self.create_history()

        self.assertEqual(
            history.break_id_snapshot,
            self.break_obj.pk,
        )

    def test_history_keeps_old_and_new_values(self):
        """
        يجب حفظ القيم السابقة والجديدة.
        """

        old_value = {
            "rest_days": (
                Break.RestDays.FRIDAY_SATURDAY
            )
        }

        new_value = {
            "rest_days": (
                Break.RestDays.SUNDAY_MONDAY
            )
        }

        history = self.create_history(
            action=BreakHistory.Action.UPDATE,
            old_value=old_value,
            new_value=new_value,
        )

        self.assertEqual(
            history.old_value,
            old_value,
        )

        self.assertEqual(
            history.new_value,
            new_value,
        )

    def test_deleting_break_keeps_history(self):
        """
        حذف الراحة لا يحذف سجل التاريخ.
        """

        history = self.create_history()

        break_pk = self.break_obj.pk

        self.break_obj.delete()

        history.refresh_from_db()

        self.assertIsNone(
            history.break_record_id
        )

        self.assertEqual(
            history.break_id_snapshot,
            break_pk,
        )

    def test_action_label_is_arabic(self):
        """
        يجب عرض اسم الإجراء باللغة العربية.
        """

        history = self.create_history(
            action=BreakHistory.Action.DEACTIVATE,
        )

        self.assertEqual(
            history.action_label,
            "تعطيل راحة",
        )

    def test_string_representation_contains_employee(self):
        """
        النص الظاهر يحتوي اسم الموظف.
        """

        history = self.create_history()

        self.assertIn(
            self.employee.full_name,
            str(history),
        )