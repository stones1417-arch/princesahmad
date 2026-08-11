from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.distribution.models import DoorAssignment
from apps.roles.models import Role, UserRole


class DistributionDashboardFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="distribution_user",
            password="StrongPassword123!",
            is_staff=True,
        )
        self._grant_distribution_access(
            self.user,
            code="distribution-test-role",
            section=Role.OperationalSection.ALL,
        )
        self.client.force_login(self.user)

        self.shift_type = create_shift_type(
            name="وردية توزيع",
            start_time="08:00",
            end_time="16:00",
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date="2026-01-01",
            start_time="08:00",
            end_time="16:00",
            is_active=True,
            is_finished=False,
        )

        self.door = create_door(
            door_number=1,
            is_active=True,
        )

        self.door2 = create_door(
            door_number=12,
            is_active=True,
        )

        self.male_employee = create_employee(
            full_name="موظف رجالي",
            employee_number="90001",
            operational_section="male",
            is_active=True,
            can_work_on_doors=True,
        )

        self.female_employee = create_employee(
            full_name="موظفة نسائية",
            employee_number="90002",
            operational_section="female",
            is_active=True,
            can_work_on_doors=True,
        )

        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.door,
            employee=self.male_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.door2,
            employee=self.female_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

    def test_dashboard_filter_by_operational_section(self):
        response = self.client.get(
            reverse("distribution:dashboard"),
            {"operational_section": "female"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("operational_section_choices", response.context)
        self.assertEqual(
            response.context["selected_operational_section"],
            "female",
        )
        self.assertNotIn(
            self.male_employee.full_name,
            response.content.decode(),
        )
        self.assertIn(
            self.female_employee.full_name,
            response.content.decode(),
        )

    def test_dashboard_enforces_institutional_section_scope(self):
        scoped_user = get_user_model().objects.create_user(
            username="male_distribution_supervisor",
            is_staff=True,
        )
        self._grant_distribution_access(
            scoped_user,
            code="male-distribution-supervisor",
            section=Role.OperationalSection.MALE,
        )
        self.client.force_login(scoped_user)

        response = self.client.get(
            reverse("distribution:dashboard"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.male_employee.full_name)
        self.assertNotContains(response, self.female_employee.full_name)

    def _grant_distribution_access(self, user, *, code, section):
        group = Group.objects.create(name=code)
        group.permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="view_distribution",
            )
        )
        role = Role.objects.create(
            code=code,
            name=code,
            group=group,
            operational_section=section,
        )
        UserRole.objects.create(user=user, role=role)
