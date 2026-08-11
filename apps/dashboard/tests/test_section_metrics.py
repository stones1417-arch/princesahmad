from __future__ import annotations

from datetime import time

from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.dashboard.views import _build_section_dashboard_metrics
from apps.distribution.models import DoorAssignment
from apps.ops.models import DoorShift


class SectionDashboardMetricsTests(TestCase):
    def setUp(self):
        shift_type = create_shift_type(
            name="وردية مؤشرات الأقسام",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )
        self.shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )
        self.male_door = create_door(door_number=1)
        self.female_door = create_door(door_number=12)
        self.shared_door = create_door(door_number=17)
        self.male_employee = create_employee(
            full_name="موظف مؤشرات رجالي",
            employee_number="DASH-M-1",
            operational_section="male",
        )
        self.female_employee = create_employee(
            full_name="موظفة مؤشرات نسائية",
            employee_number="DASH-F-1",
            operational_section="female",
        )

    def test_shared_door_counts_once_in_all_and_in_both_sections(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.shared_door,
            employee=self.male_employee,
            section="male",
            role=DoorAssignment.Role.MONITOR,
        )
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.female_door,
            employee=self.female_employee,
            section="female",
            role=DoorAssignment.Role.MONITOR,
        )
        all_doors = [
            {"door_obj": door, "state": DoorShift.DoorState.OPEN}
            for door in (
                self.male_door,
                self.female_door,
                self.shared_door,
            )
        ]

        metrics = _build_section_dashboard_metrics(
            active_shift=self.shift,
            all_doors=all_doors,
            all_assignments=DoorAssignment.objects.filter(
                shift_plan=self.shift,
                is_active=True,
            ),
        )

        self.assertEqual(metrics["all"]["total_doors"], 3)
        self.assertEqual(metrics["male"]["total_doors"], 2)
        self.assertEqual(metrics["female"]["total_doors"], 2)
        self.assertEqual(metrics["shared"]["total_doors"], 1)
        self.assertEqual(metrics["male"]["active_assignments"], 1)
        self.assertEqual(metrics["female"]["active_assignments"], 1)
        self.assertEqual(metrics["all"]["active_assignments"], 2)
