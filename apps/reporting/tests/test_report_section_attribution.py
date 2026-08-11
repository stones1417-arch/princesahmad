from __future__ import annotations

from datetime import time

from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.distribution.models import DoorAssignment
from apps.ops.models import DoorShift
from apps.reporting.services import ReportService


class ShiftReportSectionAttributionTests(TestCase):
    def test_snapshot_preserves_shared_door_and_assignment_sections(self):
        user = create_user(username="report-section-user", is_staff=True)
        shift_type = create_shift_type(
            name="وردية تقرير القسم",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )
        shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )
        shared_door = create_door(door_number=17)
        employee = create_employee(
            full_name="موظفة تقرير الباب المشترك",
            employee_number="REPORT-SHARED-1",
            operational_section="female",
        )
        DoorShift.objects.create(
            shift_plan=shift,
            door_number=shared_door.door_number,
            state=DoorShift.DoorState.OPEN,
            is_active=False,
        )
        DoorAssignment.objects.create(
            shift_plan=shift,
            door=shared_door,
            employee=employee,
            section="female",
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )
        shift.is_active = False
        shift.is_finished = True
        shift.save(update_fields=["is_active", "is_finished"])

        report = ReportService.generate_shift_report(
            shift_plan=shift,
            user=user,
        )

        self.assertEqual(
            report.snapshot_data["doors"][0]["operational_section"],
            "shared",
        )
        self.assertEqual(
            report.snapshot_data["door_assignments"][0]["section"],
            "female",
        )
