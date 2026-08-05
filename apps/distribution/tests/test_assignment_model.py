from __future__ import annotations

from datetime import time

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


class DoorAssignmentModelTests(TestCase):
    """
    اختبارات القواعد الأساسية لنموذج توزيع الأبواب.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية توزيع",
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

        self.door = create_door(
            door_number=1,
            is_active=True,
        )

        self.employee = create_employee(
            full_name="موظف توزيع",
            employee_number="81001",
            is_active=True,
            can_work_on_doors=True,
        )

    def test_active_employee_can_be_assigned(self):
        assignment = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        self.assertIsNotNone(
            assignment.pk
        )

    def test_inactive_shift_is_rejected(self):
        self.shift.is_active = False
        self.shift.save(
            update_fields=[
                "is_active",
            ]
        )

        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_finished_shift_is_rejected(self):
        self.shift.is_active = False
        self.shift.is_finished = True
        self.shift.save(
            update_fields=[
                "is_active",
                "is_finished",
            ]
        )

        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_inactive_door_is_rejected(self):
        self.door.is_active = False
        self.door.save(
            update_fields=[
                "is_active",
            ]
        )

        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_inactive_employee_is_rejected(self):
        self.employee.is_active = False
        self.employee.save(
            update_fields=[
                "is_active",
            ]
        )

        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_employee_without_door_permission_is_rejected(self):
        self.employee.can_work_on_doors = False
        self.employee.save(
            update_fields=[
                "can_work_on_doors",
            ]
        )

        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_technician_requires_maintenance_permission(self):
        self.employee.can_execute_maintenance = False
        self.employee.save(
            update_fields=[
                "can_execute_maintenance",
            ]
        )

        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.TECHNICIAN,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_supervisor_role_sets_is_supervisor(self):
        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=True,
        )

        assignment.full_clean()

        self.assertTrue(
            assignment.is_supervisor
        )

    def test_is_supervisor_sets_supervisor_role(self):
        assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_supervisor=True,
            is_active=True,
        )

        assignment.full_clean()

        self.assertEqual(
            assignment.role,
            DoorAssignment.Role.SUPERVISOR,
        )