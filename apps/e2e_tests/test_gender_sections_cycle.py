from __future__ import annotations

from datetime import time

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.breaks.models import Break
from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.distribution.models import DoorAssignment
from apps.exports_center.registry import REPORT_REGISTRY
from apps.exports_center.selectors import select_report_queryset
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.ops.models import DoorShift, Incident, MaintenanceRequest
from apps.reporting.models import ShiftReport
from apps.roles.models import Role, UserRole
from apps.scheduling.services import activate_shift
from apps.scheduling.services import finish_shift
from apps.roles.services.section_access import can_manage_section


class GenderSectionsCycleE2ETests(TestCase):
    """End-to-end coverage for male, female, and shared-door operations."""

    def setUp(self):
        self.operator = create_user(
            username="gender_cycle_operator",
            is_staff=True,
        )
        self.shift_type = create_shift_type(
            name="وردية دورة القسمين",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )
        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
            is_finished=False,
        )
        self.male_door = create_door(door_number=1)
        self.female_door = create_door(door_number=12)
        self.shared_door = create_door(door_number=17)
        self.male_employee = create_employee(
            full_name="موظف دورة رجالي",
            employee_number="E2E-GENDER-M-1",
            operational_section=Employee.OperationalSection.MALE,
        )
        self.female_employee = create_employee(
            full_name="موظفة دورة نسائية",
            employee_number="E2E-GENDER-F-1",
            operational_section=Employee.OperationalSection.FEMALE,
        )
        self.male_supervisor = create_employee(
            full_name="مشرف دورة رجالي",
            employee_number="E2E-GENDER-M-2",
            operational_section=Employee.OperationalSection.MALE,
        )
        self.female_supervisor = create_employee(
            full_name="مشرفة دورة نسائية",
            employee_number="E2E-GENDER-F-2",
            operational_section=Employee.OperationalSection.FEMALE,
        )
        self.active_shift = activate_shift(self.shift)
        self.male_door_shift = DoorShift.objects.get(
            shift_plan=self.active_shift,
            door_number=self.male_door.door_number,
        )
        self.female_door_shift = DoorShift.objects.get(
            shift_plan=self.active_shift,
            door_number=self.female_door.door_number,
        )
        self.shared_door_shift = DoorShift.objects.get(
            shift_plan=self.active_shift,
            door_number=self.shared_door.door_number,
        )

    def _assignment(self, *, door, employee, section, role=DoorAssignment.Role.MONITOR):
        return DoorAssignment.objects.create(
            shift_plan=self.active_shift,
            door=door,
            employee=employee,
            section=section,
            role=role,
            is_supervisor=role == DoorAssignment.Role.SUPERVISOR,
            is_active=True,
            assigned_by=self.operator,
        )

    def _operational_records(self, *, door_shift, assignment, section, label):
        maintenance = MaintenanceRequest(
            door_shift=door_shift,
            assignment=assignment,
            section=section,
            description=f"صيانة {label}",
        )
        maintenance.full_clean()
        maintenance.save()

        incident = Incident(
            shift_plan=self.active_shift,
            door_shift=door_shift,
            assignment=assignment,
            section=section,
            description=f"بلاغ {label}",
        )
        incident.full_clean()
        incident.save()
        return maintenance, incident

    def test_complete_male_and_female_operational_cycles(self):
        male_assignment = self._assignment(
            door=self.male_door,
            employee=self.male_employee,
            section=DoorAssignment.AssignmentSection.MALE,
        )
        female_assignment = self._assignment(
            door=self.female_door,
            employee=self.female_employee,
            section=DoorAssignment.AssignmentSection.FEMALE,
        )

        male_break = Break.objects.create(
            employee=self.male_employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=True,
        )
        female_break = Break.objects.create(
            employee=self.female_employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=True,
        )
        self.assertEqual(male_break.operational_section, "male")
        self.assertEqual(female_break.operational_section, "female")

        male_maintenance, male_incident = self._operational_records(
            door_shift=self.male_door_shift,
            assignment=male_assignment,
            section="male",
            label="رجالي",
        )
        female_maintenance, female_incident = self._operational_records(
            door_shift=self.female_door_shift,
            assignment=female_assignment,
            section="female",
            label="نسائي",
        )

        finished_shift = finish_shift(self.active_shift)

        male_report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=finished_shift,
            status=ShiftReport.ReportStatus.DRAFT,
            total_doors=1,
            summary="تقرير القسم الرجالي",
            created_by=self.operator,
        )
        self.assertEqual(male_maintenance.section, "male")
        self.assertEqual(female_maintenance.section, "female")
        self.assertEqual(male_incident.section, "male")
        self.assertEqual(female_incident.section, "female")
        self.assertEqual(male_report.shift_plan_id, finished_shift.pk)

        male_incidents = select_report_queryset("incidents", {"section": "male"})
        female_incidents = select_report_queryset("incidents", {"section": "female"})
        self.assertIn(male_incident.pk, male_incidents.values_list("pk", flat=True))
        self.assertNotIn(male_incident.pk, female_incidents.values_list("pk", flat=True))
        self.assertIn(female_incident.pk, female_incidents.values_list("pk", flat=True))

        male_maintenance_rows = select_report_queryset("maintenance", {"section": "male"})
        female_maintenance_rows = select_report_queryset("maintenance", {"section": "female"})
        self.assertIn(male_maintenance.pk, male_maintenance_rows.values_list("pk", flat=True))
        self.assertNotIn(male_maintenance.pk, female_maintenance_rows.values_list("pk", flat=True))
        self.assertIn(female_maintenance.pk, female_maintenance_rows.values_list("pk", flat=True))

        self.assertIn("incidents", REPORT_REGISTRY)
        self.assertIn("maintenance", REPORT_REGISTRY)
        self.assertIn("section", {column.key for column in REPORT_REGISTRY["incidents"].columns})
        self.assertIn("section", {column.key for column in REPORT_REGISTRY["maintenance"].columns})

    def test_shared_door_supports_both_sections_without_conflict(self):
        male_assignment = self._assignment(
            door=self.shared_door,
            employee=self.male_supervisor,
            section=DoorAssignment.AssignmentSection.MALE,
            role=DoorAssignment.Role.SUPERVISOR,
        )
        female_assignment = self._assignment(
            door=self.shared_door,
            employee=self.female_supervisor,
            section=DoorAssignment.AssignmentSection.FEMALE,
            role=DoorAssignment.Role.SUPERVISOR,
        )

        self.assertEqual(
            DoorAssignment.objects.filter(
                shift_plan=self.active_shift,
                door=self.shared_door,
                is_active=True,
            ).count(),
            2,
        )
        self.assertEqual(male_assignment.section, "male")
        self.assertEqual(female_assignment.section, "female")

        male_maintenance, male_incident = self._operational_records(
            door_shift=self.shared_door_shift,
            assignment=male_assignment,
            section="male",
            label="مشترك رجالي",
        )
        female_maintenance, female_incident = self._operational_records(
            door_shift=self.shared_door_shift,
            assignment=female_assignment,
            section="female",
            label="مشترك نسائي",
        )

        self.assertEqual(male_maintenance.section, "male")
        self.assertEqual(female_maintenance.section, "female")
        self.assertEqual(male_incident.section, "male")
        self.assertEqual(female_incident.section, "female")

        male_rows = select_report_queryset("incidents", {"section": "male"})
        female_rows = select_report_queryset("incidents", {"section": "female"})
        self.assertIn(male_incident.pk, male_rows.values_list("pk", flat=True))
        self.assertNotIn(male_incident.pk, female_rows.values_list("pk", flat=True))
        self.assertIn(female_incident.pk, female_rows.values_list("pk", flat=True))

    def test_cross_section_assignments_are_rejected(self):
        male_on_female = DoorAssignment(
            shift_plan=self.active_shift,
            door=self.female_door,
            employee=self.male_employee,
            section=DoorAssignment.AssignmentSection.MALE,
            role=DoorAssignment.Role.MONITOR,
            assigned_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            male_on_female.full_clean()

        female_on_male = DoorAssignment(
            shift_plan=self.active_shift,
            door=self.male_door,
            employee=self.female_employee,
            section=DoorAssignment.AssignmentSection.FEMALE,
            role=DoorAssignment.Role.MONITOR,
            assigned_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            female_on_male.full_clean()

        wrong_section_alternative = DoorAssignment(
            shift_plan=self.active_shift,
            door=self.shared_door,
            employee=self.male_employee,
            section=DoorAssignment.AssignmentSection.FEMALE,
            role=DoorAssignment.Role.MONITOR,
            assigned_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            wrong_section_alternative.full_clean()

    def test_scoped_user_cannot_override_section_query_parameter(self):
        male_reader = self._scoped_user(
            username="gender_cycle_male_reader",
            section=Role.OperationalSection.MALE,
        )
        female_assignment = self._assignment(
            door=self.female_door,
            employee=self.female_employee,
            section=DoorAssignment.AssignmentSection.FEMALE,
        )
        _, female_incident = self._operational_records(
            door_shift=self.female_door_shift,
            assignment=female_assignment,
            section="female",
            label="اختبار الصلاحيات",
        )

        self.assertTrue(can_manage_section(male_reader, "male"))
        self.assertFalse(can_manage_section(male_reader, "female"))

        client = Client()
        client.force_login(male_reader)
        response = client.get(
            reverse("ops:incidents"),
            {"section": "female"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            female_incident.pk,
            [incident.pk for incident in response.context["incidents"]],
        )

        exported = select_report_queryset(
            "incidents",
            {"section": "female"},
            user=male_reader,
        )
        self.assertNotIn(
            female_incident.pk,
            exported.values_list("pk", flat=True),
        )

    def test_shared_door_is_visible_to_both_sections_but_records_are_isolated(self):
        male_assignment = self._assignment(
            door=self.shared_door,
            employee=self.male_supervisor,
            section=DoorAssignment.AssignmentSection.MALE,
        )
        female_assignment = self._assignment(
            door=self.shared_door,
            employee=self.female_supervisor,
            section=DoorAssignment.AssignmentSection.FEMALE,
        )
        male_incident = self._operational_records(
            door_shift=self.shared_door_shift,
            assignment=male_assignment,
            section="male",
            label="مشترك 1",
        )[1]
        female_incident = self._operational_records(
            door_shift=self.shared_door_shift,
            assignment=female_assignment,
            section="female",
            label="مشترك 2",
        )[1]

        male_reader = self._scoped_user(
            username="shared_male_location_reader",
            section=Role.OperationalSection.MALE,
        )
        female_reader = self._scoped_user(
            username="shared_female_location_reader",
            section=Role.OperationalSection.FEMALE,
        )
        male_locations = select_report_queryset(
            "locations",
            {},
            user=male_reader,
        )
        female_locations = select_report_queryset(
            "locations",
            {},
            user=female_reader,
        )
        self.assertIn(self.shared_door.pk, male_locations.values_list("pk", flat=True))
        self.assertIn(self.shared_door.pk, female_locations.values_list("pk", flat=True))

        male_incidents = select_report_queryset("incidents", {"section": "male"})
        female_incidents = select_report_queryset("incidents", {"section": "female"})
        self.assertIn(male_incident.pk, male_incidents.values_list("pk", flat=True))
        self.assertNotIn(male_incident.pk, female_incidents.values_list("pk", flat=True))
        self.assertIn(female_incident.pk, female_incidents.values_list("pk", flat=True))
        self.assertNotIn(female_incident.pk, male_incidents.values_list("pk", flat=True))

    def _scoped_user(self, *, username, section):
        user = create_user(username=username)
        role = Role.objects.create(
            code=f"{username}-role",
            name=f"{username} role",
            group=Group.objects.create(name=f"{username}-group"),
            operational_section=section,
        )
        UserRole.objects.create(user=user, role=role)
        return user
