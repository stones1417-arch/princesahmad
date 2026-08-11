from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.roles.models import Role, UserRole
from apps.roles.services.access_control import (
    get_user_operational_sections,
    user_can_access_operational_section,
)


class OperationalSectionAccessTests(TestCase):
    def _assign_role(
        self,
        *,
        user,
        code: str,
        section: str,
    ) -> None:
        role = Role.objects.create(
            code=code,
            name=code,
            group=Group.objects.create(name=code),
            operational_section=section,
        )

        UserRole.objects.create(
            user=user,
            role=role,
        )

    def test_male_role_is_limited_to_male_section(self):
        user = get_user_model().objects.create_user(
            username="male_supervisor",
        )

        self._assign_role(
            user=user,
            code="male-supervisor",
            section=Role.OperationalSection.MALE,
        )

        self.assertEqual(
            get_user_operational_sections(user),
            {Role.OperationalSection.MALE},
        )
        self.assertTrue(
            user_can_access_operational_section(user, "male")
        )
        self.assertFalse(
            user_can_access_operational_section(user, "female")
        )

    def test_all_scope_role_can_access_both_sections(self):
        user = get_user_model().objects.create_user(
            username="executive_user",
        )

        self._assign_role(
            user=user,
            code="executive",
            section=Role.OperationalSection.ALL,
        )

        self.assertTrue(
            user_can_access_operational_section(user, "male")
        )
        self.assertTrue(
            user_can_access_operational_section(user, "female")
        )

    def test_combined_section_roles_allow_both_sections(self):
        user = get_user_model().objects.create_user(
            username="dual_section_user",
        )

        self._assign_role(
            user=user,
            code="male-supervisor",
            section=Role.OperationalSection.MALE,
        )
        self._assign_role(
            user=user,
            code="female-supervisor",
            section=Role.OperationalSection.FEMALE,
        )

        self.assertEqual(
            get_user_operational_sections(user),
            {
                Role.OperationalSection.MALE,
                Role.OperationalSection.FEMALE,
            },
        )
        self.assertTrue(
            user_can_access_operational_section(user, "male")
        )
        self.assertTrue(
            user_can_access_operational_section(user, "female")
        )

    def test_inactive_role_assignments_do_not_grant_access(self):
        user = get_user_model().objects.create_user(
            username="inactive_role_user",
        )
        role = Role.objects.create(
            code="inactive-female-supervisor",
            name="inactive-female-supervisor",
            group=Group.objects.create(
                name="inactive-female-supervisor",
            ),
            operational_section=Role.OperationalSection.FEMALE,
            is_active=False,
        )
        UserRole.objects.create(
            user=user,
            role=role,
            is_active=False,
        )

        self.assertEqual(get_user_operational_sections(user), set())
        self.assertFalse(
            user_can_access_operational_section(user, "female")
        )