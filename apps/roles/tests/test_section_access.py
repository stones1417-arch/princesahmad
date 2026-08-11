from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import create_door, create_employee
from apps.distribution.models import DoorAssignment
from apps.exports_center.selectors import select_report_queryset
from apps.exports_center.services.export_service import export_report
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.roles.models import Role, UserRole
from apps.roles.services.section_access import (
    can_view_section,
    filter_assignments_for_user,
    filter_doors_for_user,
    filter_employees_for_user,
    get_allowed_sections,
)


class SectionAccessIsolationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.male_employee = create_employee(
            full_name="اختبار موظف رجالي",
            employee_number="93001",
            operational_section=Employee.OperationalSection.MALE,
        )
        self.female_employee = create_employee(
            full_name="اختبار موظفة نسائية",
            employee_number="93002",
            operational_section=Employee.OperationalSection.FEMALE,
        )
        self.male_door = create_door(door_number=1)
        self.female_door = create_door(door_number=12)
        self.shared_door = create_door(door_number=17)

        self.male_assignment = DoorAssignment.objects.create(
            shift_plan=self._shift_plan(),
            door=self.shared_door,
            employee=self.male_employee,
            section=DoorAssignment.AssignmentSection.MALE,
        )
        self.female_assignment = DoorAssignment.objects.create(
            shift_plan=self.male_assignment.shift_plan,
            door=self.shared_door,
            employee=self.female_employee,
            section=DoorAssignment.AssignmentSection.FEMALE,
        )

    def _shift_plan(self):
        from apps.core.tests.factories import (
            create_shift_plan,
            create_shift_type,
        )

        shift_type = create_shift_type(
            name="وردية عزل الصلاحيات",
            start_time="08:00",
            end_time="16:00",
        )
        return create_shift_plan(
            shift_type=shift_type,
            shift_date="2026-03-01",
            start_time="08:00",
            end_time="16:00",
            is_active=True,
            is_finished=False,
        )

    def _user(self, username, section, *, is_staff=False):
        user = self.user_model.objects.create_user(
            username=username,
            is_staff=is_staff,
        )
        role = Role.objects.create(
            code=f"{username}-role",
            name=f"{username} role",
            group=Group.objects.create(name=f"{username} group"),
            operational_section=section,
        )
        role.group.permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="view_employees",
            )
        )
        UserRole.objects.create(user=user, role=role)
        return user

    def test_all_scope_can_access_both_sections(self):
        user = self._user("all_access", Role.OperationalSection.ALL)

        self.assertEqual(get_allowed_sections(user), {"male", "female"})
        self.assertTrue(can_view_section(user, "male"))
        self.assertTrue(can_view_section(user, "female"))
        self.assertEqual(
            filter_employees_for_user(
                Employee.objects.all(),
                user,
            ).count(),
            2,
        )

    def test_male_scope_is_denied_female_section(self):
        user = self._user("male_access", Role.OperationalSection.MALE)

        self.assertTrue(can_view_section(user, "male"))
        self.assertFalse(can_view_section(user, "female"))
        self.assertQuerySetEqual(
            filter_employees_for_user(Employee.objects.all(), user)
            .values_list("pk", flat=True),
            [self.male_employee.pk],
            transform=lambda value: value,
        )

    def test_female_scope_is_denied_male_section(self):
        user = self._user("female_access", Role.OperationalSection.FEMALE)

        self.assertTrue(can_view_section(user, "female"))
        self.assertFalse(can_view_section(user, "male"))
        self.assertQuerySetEqual(
            filter_employees_for_user(Employee.objects.all(), user)
            .values_list("pk", flat=True),
            [self.female_employee.pk],
            transform=lambda value: value,
        )

    def test_shared_door_is_visible_to_both_sections(self):
        male_user = self._user("shared_male", Role.OperationalSection.MALE)
        female_user = self._user("shared_female", Role.OperationalSection.FEMALE)

        for user in (male_user, female_user):
            self.assertIn(
                self.shared_door.pk,
                filter_doors_for_user(Door.objects.all(), user)
                .values_list("pk", flat=True),
            )

    def test_shared_door_assignments_are_isolated_by_assignment_section(self):
        male_user = self._user("assignment_male", Role.OperationalSection.MALE)
        female_user = self._user("assignment_female", Role.OperationalSection.FEMALE)

        male_ids = filter_assignments_for_user(
            DoorAssignment.objects.all(),
            male_user,
        ).values_list("pk", flat=True)
        female_ids = filter_assignments_for_user(
            DoorAssignment.objects.all(),
            female_user,
        ).values_list("pk", flat=True)

        self.assertIn(self.male_assignment.pk, male_ids)
        self.assertNotIn(self.female_assignment.pk, male_ids)
        self.assertIn(self.female_assignment.pk, female_ids)
        self.assertNotIn(self.male_assignment.pk, female_ids)

    def test_manual_female_section_filter_cannot_bypass_male_scope(self):
        user = self._user(
            "manual_male_filter",
            Role.OperationalSection.MALE,
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("hr:list"),
            {"section": "female", "operational_section": "female"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["employees"].count(), 0)
        self.assertNotContains(response, self.female_employee.full_name)

    def test_unscoped_staff_user_cannot_use_section_filter_to_gain_data(self):
        user = self.user_model.objects.create_user(
            username="unscoped_staff",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("hr:list"),
            {"section": "female", "operational_section": "female"},
        )

        self.assertEqual(response.status_code, 403)

    def test_all_scope_can_extract_complete_employee_report(self):
        user = self._user("all_export", Role.OperationalSection.ALL)

        result = export_report(
            report_key="employees",
            export_format="csv",
            user=user,
            filters={},
        )

        self.assertEqual(result.records_count, 2)
        self.assertIn(
            self.male_employee.full_name.encode(),
            result.content,
        )
        self.assertIn(
            self.female_employee.full_name.encode(),
            result.content,
        )

    def test_export_scope_cannot_be_broadened_by_section_filter(self):
        user = self._user("male_export", Role.OperationalSection.MALE)

        queryset = select_report_queryset(
            "employees",
            {"section": "female"},
            user=user,
        )

        self.assertEqual(queryset.count(), 0)

        result = export_report(
            report_key="employees",
            export_format="csv",
            user=user,
            filters={"section": "female"},
        )
        self.assertEqual(result.records_count, 0)
