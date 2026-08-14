from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.tests.factories import (
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.scheduling.models import ShiftAssignment, ShiftPlan


class ShiftAssignmentModelRulesTests(TestCase):
    def test_shift_is_required_for_assignment(self):
        employee = create_employee(
            full_name="موظف بدون وردية",
            employee_number="99001",
            is_active=True,
            can_work_on_doors=True,
        )

        assignment = ShiftAssignment(
            employee=employee,
            role=ShiftAssignment.OperationalRole.MONITOR,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_overlapping_shift_assignment_for_same_employee_is_rejected(self):
        employee = create_employee(
            full_name="موظف متداخل",
            employee_number="99002",
            is_active=True,
            can_work_on_doors=True,
        )

        first_type = create_shift_type(
            name="الفجر",
            start_time=time(7, 0),
            end_time=time(14, 0),
        )
        second_type = create_shift_type(
            name="المسائية",
            start_time=time(14, 0),
            end_time=time(21, 0),
        )

        first_shift = create_shift_plan(
            shift_type=first_type,
            shift_date="2026-01-10",
            start_time=time(7, 0),
            end_time=time(14, 0),
            is_active=True,
            is_finished=False,
        )

        ShiftPlan.objects.bulk_create(
            [
                ShiftPlan(
                    shift_type=second_type,
                    date="2026-01-10",
                    start_time=time(13, 30),
                    end_time=time(20, 0),
                    is_active=True,
                    is_finished=False,
                )
            ]
        )
        overlapping_shift = ShiftPlan.objects.get(
            shift_type=second_type,
            date="2026-01-10",
            start_time=time(13, 30),
        )

        ShiftAssignment.objects.create(
            shift_plan=first_shift,
            employee=employee,
            role=ShiftAssignment.OperationalRole.SUPPORT,
        )

        conflicting_assignment = ShiftAssignment(
            shift_plan=overlapping_shift,
            employee=employee,
            role=ShiftAssignment.OperationalRole.MONITOR,
        )

        with self.assertRaises(ValidationError):
            conflicting_assignment.full_clean()
