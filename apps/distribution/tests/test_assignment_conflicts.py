from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.distribution.models import DoorAssignment


class DoorAssignmentConflictTests(TestCase):
    """
    اختبارات تعارضات التوزيع.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية تعارض توزيع",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )

        self.first_door = create_door(
            door_number=10,
        )

        self.second_door = create_door(
            door_number=11,
        )

        self.first_employee = create_employee(
            full_name="الموظف الأول",
            employee_number="82001",
        )

        self.second_employee = create_employee(
            full_name="الموظف الثاني",
            employee_number="82002",
        )

    def test_employee_cannot_be_assigned_twice_in_same_shift(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        duplicate_assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.second_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            duplicate_assignment.full_clean()

    def test_database_rejects_duplicate_active_employee_assignment(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            (
                ValidationError,
                IntegrityError,
            )
        ):
            with transaction.atomic():
                DoorAssignment.objects.create(
                    shift_plan=self.shift,
                    door=self.second_door,
                    employee=self.first_employee,
                    role=DoorAssignment.Role.MONITOR,
                    is_active=True,
                )

    def test_door_cannot_have_two_active_supervisors(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=True,
        )

        second_supervisor = DoorAssignment(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.second_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            second_supervisor.full_clean()

    def test_inactive_old_assignment_does_not_block_new_assignment(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=False,
        )

        new_assignment = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.second_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        self.assertIsNotNone(
            new_assignment.pk
        )

    def test_inactive_supervisor_does_not_block_new_supervisor(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=False,
        )

        new_supervisor = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.second_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=True,
        )

        self.assertTrue(
            new_supervisor.is_supervisor
        )