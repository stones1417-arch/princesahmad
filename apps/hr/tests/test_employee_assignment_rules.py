from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
)
from apps.distribution.models import DoorAssignment


class EmployeeAssignmentRulesTests(TestCase):
    """
    اختبارات منع تسكين الموظفين غير المؤهلين.
    """

    def test_inactive_employee_cannot_be_assigned(self):
        """
        لا يسمح بتسكين موظف غير نشط على باب.
        """

        employee = create_employee(
            full_name="موظف غير نشط",
            employee_number="72001",
            is_active=False,
        )

        shift_plan = create_shift_plan(
            is_active=True,
            is_finished=False,
        )

        door = create_door(
            door_number=1,
        )

        assignment = DoorAssignment(
            employee=employee,
            shift_plan=shift_plan,
            door=door,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_employee_without_door_permission_cannot_be_assigned(self):
        """
        لا يسمح بتسكين موظف غير مصرح له بالعمل على الأبواب.
        """

        employee_fields = {
            field.name
            for field in employee_model_fields()
        }

        if "can_work_on_doors" not in employee_fields:
            self.skipTest(
                "نموذج Employee لا يحتوي على can_work_on_doors."
            )

        employee = create_employee(
            full_name="موظف غير مصرح",
            employee_number="72002",
            can_work_on_doors=False,
        )

        shift_plan = create_shift_plan(
            is_active=True,
        )

        door = create_door(
            door_number=2,
        )

        assignment = DoorAssignment(
            employee=employee,
            shift_plan=shift_plan,
            door=door,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_active_authorized_employee_can_be_assigned(self):
        """
        يسمح بتسكين الموظف النشط والمصرح له.
        """

        employee = create_employee(
            full_name="موظف نشط",
            employee_number="72003",
            is_active=True,
            can_work_on_doors=True,
        )

        shift_plan = create_shift_plan(
            is_active=True,
        )

        door = create_door(
            door_number=3,
        )

        assignment = DoorAssignment(
            employee=employee,
            shift_plan=shift_plan,
            door=door,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        assignment.full_clean()
        assignment.save()

        self.assertTrue(
            DoorAssignment.objects.filter(
                pk=assignment.pk,
            ).exists()
        )


def employee_model_fields():
    """
    إرجاع حقول Employee دون تكرار الاستيراد داخل الاختبارات.
    """

    from apps.hr.models import Employee

    return Employee._meta.fields