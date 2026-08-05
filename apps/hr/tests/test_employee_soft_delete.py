from __future__ import annotations

from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
)
from apps.distribution.models import DoorAssignment
from apps.hr.models import Employee


class EmployeeSoftDeleteTests(TestCase):
    """
    اختبارات الحذف الآمن للموظفين.
    """

    def test_employee_delete_should_not_remove_database_record(self):
        """
        استدعاء delete يجب أن يعطل الموظف بدل حذفه نهائيًا.

        هذا الاختبار سيفشل إذا لم يكن الحذف الآمن مطبقًا،
        وهي نتيجة متوقعة تكشف الفجوة قبل الإطلاق.
        """

        employee = create_employee(
            full_name="موظف الحذف الآمن",
            employee_number="73001",
            is_active=True,
        )

        employee_id = employee.pk

        employee.delete()

        self.assertTrue(
            Employee.objects.filter(
                pk=employee_id,
            ).exists(),
            msg=(
                "تم حذف الموظف نهائيًا من قاعدة البيانات. "
                "يجب تطبيق الحذف الآمن."
            ),
        )

        employee.refresh_from_db()

        self.assertFalse(
            employee.is_active,
            msg=(
                "يجب أن تصبح حالة الموظف غير نشطة "
                "بعد طلب الحذف."
            ),
        )

    def test_soft_deleted_employee_is_excluded_from_active_queryset(self):
        """
        الموظف المحذوف آمنًا لا يظهر في قوائم الموظفين النشطين.
        """

        employee = create_employee(
            full_name="موظف مستبعد",
            employee_number="73002",
            is_active=True,
        )

        employee.delete()

        active_employees = Employee.objects.filter(
            is_active=True,
        )

        self.assertNotIn(
            employee.pk,
            active_employees.values_list(
                "pk",
                flat=True,
            ),
        )

    def test_employee_with_assignment_cannot_be_physically_deleted(self):
        """
        علاقات PROTECT تمنع الحذف النهائي لموظف مرتبط بتوزيع.
        """

        employee = create_employee(
            full_name="موظف مرتبط بتوزيع",
            employee_number="73003",
            is_active=True,
            can_work_on_doors=True,
        )

        shift_plan = create_shift_plan(
            is_active=True,
        )

        door = create_door(
            door_number=4,
        )

        DoorAssignment.objects.create(
            employee=employee,
            shift_plan=shift_plan,
            door=door,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        try:
            employee.delete()
        except ProtectedError:
            pass

        self.assertTrue(
            Employee.objects.filter(
                pk=employee.pk,
            ).exists()
        )