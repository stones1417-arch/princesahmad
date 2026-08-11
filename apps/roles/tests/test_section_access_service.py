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
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.roles.models import Role, UserRole
from apps.roles.services.section_access import (
    can_manage_section,
    can_view_section,
    filter_assignments_for_user,
    filter_doors_for_user,
    filter_employees_for_user,
    get_allowed_sections,
)


class SectionAccessServiceTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.male_employee = create_employee(
            full_name="موظف رجالي",
            employee_number="91001",
            operational_section="male",
        )
        self.female_employee = create_employee(
            full_name="موظفة نسائية",
            employee_number="91002",
            operational_section="female",
        )
        self.male_door = create_door(door_number=1)
        self.female_door = create_door(door_number=12)
        self.shared_door = create_door(door_number=17)
        shift_type = create_shift_type(
            name="وردية صلاحيات الأقسام",
            start_time="08:00",
            end_time="16:00",
        )
        self.shift = create_shift_plan(
            shift_type=shift_type,
            shift_date="2026-02-01",
            start_time="08:00",
            end_time="16:00",
            is_active=True,
            is_finished=False,
        )

    def _scoped_user(self, username, section):
        user = self.user_model.objects.create_user(username=username)
        role = Role.objects.create(
            code=f"{username}-role",
            name=f"{username} role",
            group=Group.objects.create(name=f"{username} group"),
            operational_section=section,
        )
        UserRole.objects.create(user=user, role=role)
        return user

    def test_male_scope_filters_all_operational_surfaces(self):
        user = self._scoped_user(
            "male_scope",
            Role.OperationalSection.MALE,
        )

        self.assertEqual(get_allowed_sections(user), {"male"})
        self.assertTrue(can_view_section(user, "male"))
        self.assertFalse(can_view_section(user, "female"))
        self.assertTrue(can_manage_section(user, "male"))
        self.assertFalse(can_manage_section(user, "female"))
        self.assertQuerySetEqual(
            filter_employees_for_user(
                Employee.objects.all(),
                user,
            ).values_list("pk", flat=True),
            [self.male_employee.pk],
            transform=lambda value: value,
        )
        self.assertQuerySetEqual(
            filter_doors_for_user(
                Door.objects.all(),
                user,
            ).order_by("pk").values_list("pk", flat=True),
            [self.male_door.pk, self.shared_door.pk],
            transform=lambda value: value,
        )

    def test_female_scope_filters_assignments_by_assignment_section(self):
        user = self._scoped_user(
            "female_scope",
            Role.OperationalSection.FEMALE,
        )
        male_assignment = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.shared_door,
            employee=self.male_employee,
            section="male",
        )
        female_assignment = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.shared_door,
            employee=self.female_employee,
            section="female",
        )

        self.assertQuerySetEqual(
            filter_assignments_for_user(
                DoorAssignment.objects.all(),
                user,
            ).values_list("pk", flat=True),
            [female_assignment.pk],
            transform=lambda value: value,
        )
        self.assertNotIn(
            male_assignment.pk,
            filter_assignments_for_user(
                DoorAssignment.objects.all(),
                user,
            ).values_list("pk", flat=True),
        )

    def test_all_scope_sees_both_sections_and_shared_doors(self):
        user = self._scoped_user(
            "all_scope",
            Role.OperationalSection.ALL,
        )

        self.assertEqual(get_allowed_sections(user), {"male", "female"})
        self.assertTrue(can_view_section(user, "male"))
        self.assertTrue(can_view_section(user, "female"))
        self.assertEqual(
            filter_doors_for_user(Door.objects.all(), user).count(),
            3,
        )
