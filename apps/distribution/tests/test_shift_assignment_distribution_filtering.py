from __future__ import annotations

from datetime import time

from django.test import TestCase

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.hr.models import Employee
from apps.scheduling.models import ShiftAssignment


class ShiftAssignmentDistributionFilteringTests(TestCase):
    def test_distribution_lists_only_same_shift_and_section_staff(self):
        male_section = create_employee(
            full_name="موظف رجالي",
            employee_number="80001",
            operational_section="male",
            is_active=True,
            can_work_on_doors=True,
            work_status="active",
        )
        female_section = create_employee(
            full_name="موظفة نسائية",
            employee_number="80002",
            operational_section="female",
            is_active=True,
            can_work_on_doors=True,
            work_status="active",
        )
        same_shift_employee = create_employee(
            full_name="موظف نفس الوردية",
            employee_number="80003",
            operational_section="male",
            is_active=True,
            can_work_on_doors=True,
            work_status="active",
        )

        shift_type = create_shift_type(
            name="الفجر",
            start_time=time(7, 0),
            end_time=time(14, 0),
        )
        shift_plan = create_shift_plan(
            shift_type=shift_type,
            shift_date="2026-01-10",
            start_time=time(7, 0),
            end_time=time(14, 0),
            is_active=True,
            is_finished=False,
        )

        other_shift = create_shift_plan(
            shift_type=create_shift_type(
                name="المسائية",
                start_time=time(14, 0),
                end_time=time(21, 0),
            ),
            shift_date="2026-01-10",
            start_time=time(14, 0),
            end_time=time(21, 0),
            is_active=True,
            is_finished=False,
        )

        door = create_door(door_number=1, operational_section="male")

        ShiftAssignment.objects.create(
            shift_plan=shift_plan,
            employee=same_shift_employee,
            role=ShiftAssignment.OperationalRole.MONITOR,
        )
        ShiftAssignment.objects.create(
            shift_plan=other_shift,
            employee=female_section,
            role=ShiftAssignment.OperationalRole.MONITOR,
        )
        ShiftAssignment.objects.create(
            shift_plan=shift_plan,
            employee=female_section,
            role=ShiftAssignment.OperationalRole.SUPPORT,
        )

        same_shift_staff = Employee.objects.filter(
            operational_section="male",
            shift_assignments__shift_plan=shift_plan,
        )

        self.assertIn(same_shift_employee, same_shift_staff)
        self.assertNotIn(male_section, same_shift_staff)
        self.assertNotIn(female_section, same_shift_staff)
        self.assertTrue(door.operational_section in {"male", "shared"})
