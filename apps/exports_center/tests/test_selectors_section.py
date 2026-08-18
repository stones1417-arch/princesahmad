from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.distribution.models import DoorAssignment
from apps.exports_center.selectors import (
    build_report_indicators,
    door_distribution_selector,
    incidents_selector,
    locations_selector,
    maintenance_selector,
    reports_selector,
    select_report_queryset,
)
from apps.locations.models import Door
from apps.ops.models import DoorShift, Incident, MaintenanceRequest
from apps.reporting.models import ShiftReport
from apps.roles.models import Role, UserRole


class ExportSelectorsSectionTests(TestCase):
    def setUp(self):
        self.client_user_model = get_user_model()
        self.shift_type = create_shift_type(
            name="وردية اختبار قسم",
            start_time="08:00",
            end_time="16:00",
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=date(2026, 1, 10),
            is_active=True,
            is_finished=False,
        )

        self.shift_female = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=date(2026, 1, 11),
            is_active=True,
            is_finished=False,
        )

        self.door_male = create_door(
            door_number=1,
            is_active=True,
        )

        self.door_shared = create_door(
            door_number=17,
            is_active=True,
            operational_section=Door.OperationalSection.SHARED,
        )

        self.door_female = create_door(
            door_number=12,
            is_active=True,
        )

        self.employee_male = create_employee(
            full_name="موظف رجالي",
            employee_number="70001",
            operational_section="male",
            is_active=True,
            can_work_on_doors=True,
        )

        self.employee_female = create_employee(
            full_name="موظفة نسائية",
            employee_number="70002",
            operational_section="female",
            is_active=True,
            can_work_on_doors=True,
        )

        self.employee_female_2 = create_employee(
            full_name="موظفة نسائية 2",
            employee_number="70003",
            operational_section="female",
            is_active=True,
            can_work_on_doors=True,
        )

        self.employee_male_2 = create_employee(
            full_name="موظف رجالي 2",
            employee_number="70004",
            operational_section="male",
            is_active=True,
            can_work_on_doors=True,
        )

        self.assignment_male_only = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.door_male,
            employee=self.employee_male,
            section=DoorAssignment.AssignmentSection.MALE,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        self.assignment_shared_male = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.door_shared,
            employee=self.employee_male_2,
            section=DoorAssignment.AssignmentSection.MALE,
            role=DoorAssignment.Role.SUPERVISOR,
            is_supervisor=True,
            is_active=True,
        )

        self.assignment_shared_female = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.door_shared,
            employee=self.employee_female,
            section=DoorAssignment.AssignmentSection.FEMALE,
            role=DoorAssignment.Role.SUPERVISOR,
            is_supervisor=True,
            is_active=True,
        )

        self.assignment_shared_female_second_shift = DoorAssignment.objects.create(
            shift_plan=self.shift_female,
            door=self.door_shared,
            employee=self.employee_female_2,
            section=DoorAssignment.AssignmentSection.FEMALE,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        self.door_shift_male = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=self.door_male.door_number,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

        self.door_shift_shared = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=self.door_shared.door_number,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

        self.incident_male_only = Incident.objects.create(
            shift_plan=self.shift,
            door_shift=self.door_shift_male,
            description="بلاغ باب رجالي",
            status=Incident.Status.NEW,
        )

        self.incident_shared = Incident.objects.create(
            shift_plan=self.shift,
            door_shift=self.door_shift_shared,
            description="بلاغ باب مشترك",
            status=Incident.Status.NEW,
        )

        self.maintenance_male_only = MaintenanceRequest.objects.create(
            door_shift=self.door_shift_male,
            description="صيانة باب رجالي",
            status=MaintenanceRequest.Status.NEW,
        )

        self.maintenance_shared = MaintenanceRequest.objects.create(
            door_shift=self.door_shift_shared,
            description="صيانة باب مشترك",
            status=MaintenanceRequest.Status.NEW,
        )

        self.report_shared = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.MANUAL,
            shift_plan=self.shift,
            status=ShiftReport.ReportStatus.DRAFT,
            summary="ملخص قسم مشترك",
            total_doors=2,
            open_doors=2,
        )

        self.report_female = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.MANUAL,
            shift_plan=self.shift_female,
            status=ShiftReport.ReportStatus.DRAFT,
            summary="ملخص قسم نسائي",
            total_doors=1,
            open_doors=1,
        )

    def test_door_distribution_section_filter_and_indicators(self):
        male_queryset = door_distribution_selector({"section": "male"})
        female_queryset = door_distribution_selector({"section": "female"})

        self.assertQuerySetEqual(
            male_queryset.order_by("pk").values_list("pk", flat=True),
            [self.assignment_male_only.pk, self.assignment_shared_male.pk],
            transform=lambda value: value,
        )

        self.assertQuerySetEqual(
            female_queryset.order_by("pk").values_list("pk", flat=True),
            [
                self.assignment_shared_female.pk,
                self.assignment_shared_female_second_shift.pk,
            ],
            transform=lambda value: value,
        )

        indicators = build_report_indicators(
            "door_distribution",
            door_distribution_selector({}),
        )

        self.assertEqual(indicators["male_doors_count"], 2)
        self.assertEqual(indicators["female_doors_count"], 1)
        self.assertEqual(indicators["male_assignments_count"], 2)
        self.assertEqual(indicators["female_assignments_count"], 2)

    def test_institutional_male_scope_limits_distribution_report(self):
        user = self._create_scoped_user(
            username="male_report_reader",
            section=Role.OperationalSection.MALE,
        )

        queryset = select_report_queryset(
            "door_distribution",
            {},
            user=user,
        )

        self.assertQuerySetEqual(
            queryset.order_by("pk").values_list("pk", flat=True),
            [
                self.assignment_male_only.pk,
                self.assignment_shared_male.pk,
            ],
            transform=lambda value: value,
        )

    def test_institutional_scope_keeps_shared_door_visible(self):
        user = self._create_scoped_user(
            username="female_report_reader",
            section=Role.OperationalSection.FEMALE,
        )

        queryset = select_report_queryset(
            "locations",
            {},
            user=user,
        )

        self.assertQuerySetEqual(
            queryset.order_by("pk").values_list("pk", flat=True),
            [self.door_shared.pk, self.door_female.pk],
            transform=lambda value: value,
        )

    def _create_scoped_user(self, *, username, section):
        user = self.client_user_model.objects.create_user(
            username=username,
        )
        role = Role.objects.create(
            code=f"{username}-role",
            name=f"{username} role",
            group=Group.objects.create(
                name=f"{username} group",
            ),
            operational_section=section,
        )
        UserRole.objects.create(user=user, role=role)
        return user

    def test_incidents_section_filter_counts_shared_in_both_sections(self):
        male_queryset = incidents_selector({"section": "male"})
        female_queryset = incidents_selector({"section": "female"})

        self.assertQuerySetEqual(
            male_queryset.order_by("pk").values_list("pk", flat=True),
            [self.incident_male_only.pk, self.incident_shared.pk],
            transform=lambda value: value,
        )

        self.assertQuerySetEqual(
            female_queryset.order_by("pk").values_list("pk", flat=True),
            [self.incident_shared.pk],
            transform=lambda value: value,
        )

        indicators = build_report_indicators(
            "incidents",
            incidents_selector({}),
        )

        self.assertEqual(indicators["male_count"], 2)
        self.assertEqual(indicators["female_count"], 1)

    def test_maintenance_section_filter_counts_shared_in_both_sections(self):
        male_queryset = maintenance_selector({"section": "male"})
        female_queryset = maintenance_selector({"section": "female"})

        self.assertQuerySetEqual(
            male_queryset.order_by("pk").values_list("pk", flat=True),
            [self.maintenance_male_only.pk, self.maintenance_shared.pk],
            transform=lambda value: value,
        )

        self.assertQuerySetEqual(
            female_queryset.order_by("pk").values_list("pk", flat=True),
            [self.maintenance_shared.pk],
            transform=lambda value: value,
        )

        indicators = build_report_indicators(
            "maintenance",
            maintenance_selector({}),
        )

        self.assertEqual(indicators["male_count"], 2)
        self.assertEqual(indicators["female_count"], 1)

    def test_reports_section_filter_counts_shared_shift_in_both_sections(self):
        male_queryset = reports_selector({"section": "male"})
        female_queryset = reports_selector({"section": "female"})

        self.assertQuerySetEqual(
            male_queryset.order_by("pk").values_list("pk", flat=True),
            [self.report_shared.pk],
            transform=lambda value: value,
        )

        self.assertQuerySetEqual(
            female_queryset.order_by("pk").values_list("pk", flat=True),
            [self.report_shared.pk, self.report_female.pk],
            transform=lambda value: value,
        )

        indicators = build_report_indicators(
            "reports",
            reports_selector({}),
        )

        self.assertEqual(indicators["male_count"], 1)
        self.assertEqual(indicators["female_count"], 2)

    def test_locations_operational_section_filter(self):
        male_queryset = locations_selector(
            {"operational_section": "male"}
        )
        female_queryset = locations_selector(
            {"operational_section": "female"}
        )
        shared_queryset = locations_selector(
            {"operational_section": "shared"}
        )

        self.assertQuerySetEqual(
            male_queryset.order_by("pk").values_list("pk", flat=True),
            [self.door_male.pk],
            transform=lambda value: value,
        )

        self.assertQuerySetEqual(
            female_queryset.order_by("pk").values_list("pk", flat=True),
            [self.door_female.pk],
            transform=lambda value: value,
        )

        self.assertQuerySetEqual(
            shared_queryset.order_by("pk").values_list("pk", flat=True),
            [self.door_shared.pk],
            transform=lambda value: value,
        )
