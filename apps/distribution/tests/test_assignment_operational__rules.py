from __future__ import annotations

from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.distribution.models import DoorAssignment


class DoorAssignmentOperationalRulesTests(TestCase):
    """
    اختبارات تشغيلية إضافية لتوزيع الموظفين.
    """

    def setUp(self):
        self.employee = create_employee(
            full_name="موظف تشغيل",
            employee_number="83001",
            is_active=True,
            can_work_on_doors=True,
        )

        self.first_door = create_door(
            door_number=20,
        )

        self.second_door = create_door(
            door_number=21,
        )

    def test_same_employee_can_be_assigned_in_different_non_overlapping_shifts(self):
        first_type = create_shift_type(
            name="وردية أولى توزيع",
            start_time=time(8, 0),
            end_time=time(14, 0),
        )

        second_type = create_shift_type(
            name="وردية ثانية توزيع",
            start_time=time(14, 0),
            end_time=time(20, 0),
        )

        first_shift = create_shift_plan(
            shift_type=first_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(14, 0),
            is_active=True,
        )

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        first_shift.is_active = False
        first_shift.is_finished = True
        first_shift.save(
            update_fields=[
                "is_active",
                "is_finished",
            ]
        )

        second_shift = create_shift_plan(
            shift_type=second_type,
            shift_date=timezone.localdate(),
            start_time=time(14, 0),
            end_time=time(20, 0),
            is_active=True,
        )

        assignment = DoorAssignment.objects.create(
            shift_plan=second_shift,
            door=self.second_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        self.assertIsNotNone(
            assignment.pk
        )

    def test_assignment_save_runs_full_clean(self):
        shift_type = create_shift_type(
            name="وردية تحقق الحفظ",
        )

        inactive_shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=(
                timezone.localdate()
                + timedelta(days=1)
            ),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
        )

        assignment = DoorAssignment(
            shift_plan=inactive_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.save()