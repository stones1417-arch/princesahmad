from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.dashboard.models import SystemActivityLog
from apps.hr.models import Employee
from apps.roles.models import Role, UserRole
from apps.roles.services.access_control import get_user_permission_codes
from apps.roles.services.assignment_management import (
    assign_employee_role,
    remove_employee_role,
)
from apps.roles.services.permission_presentation import permission_comparison
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.role_manager import assign_role_to_user, get_platform_permission


User = get_user_model()


class EmployeeRoleAssignmentUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")
        cls.manager = User.objects.create_user(username="role-manager", password="password")
        assign_role_to_user(user=cls.manager, role_code="system_admin")
        cls.target = User.objects.create_user(username="role-target", password="password")
        cls.employee = Employee.objects.create(
            user=cls.target,
            employee_number="ROLE-100",
            full_name="موظف اختبار التسكين",
            operational_section=Employee.OperationalSection.MALE,
            is_active=True,
        )
        cls.url = reverse("roles:employee-assignment")

    def test_authorized_manager_sees_real_role_cards(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["role_cards"]), Role.objects.filter(is_active=True).count())
        self.assertContains(response, "shift_supervisor")
        modules = {
            group["module"]
            for card in response.context["role_cards"]
            for group in card["permissions"]
        }
        self.assertIn("الورديات", modules)
        self.assertIn("التقارير", modules)

    def test_anonymous_redirects_and_unauthorized_is_forbidden(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.target)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_preview_equals_runtime_permissions_after_assignment(self):
        role = Role.objects.get(code="shift_supervisor")
        preview = permission_comparison(self.target, role)["after_codes"]
        assign_employee_role(
            actor=self.manager,
            employee=self.employee,
            role=role,
            section=Employee.OperationalSection.MALE,
        )
        self.assertEqual(preview, get_user_permission_codes(self.target))

    def test_assignment_adds_role_preserves_existing_role_and_invalidates_cache(self):
        assign_role_to_user(user=self.target, role_code="employee")
        self.assertFalse(self.target.has_perm(PlatformPermissions.APPROVE_DISTRIBUTION))
        role = Role.objects.get(code="shift_supervisor")
        assign_employee_role(
            actor=self.manager,
            employee=self.employee,
            role=role,
            section=Employee.OperationalSection.MALE,
        )
        self.assertTrue(self.target.has_perm(PlatformPermissions.APPROVE_DISTRIBUTION))
        self.assertTrue(UserRole.objects.filter(user=self.target, role__code="employee", is_active=True).exists())
        self.assertEqual(self.employee.operational_section, Employee.OperationalSection.MALE)
        self.assertTrue(SystemActivityLog.objects.filter(user=self.manager, module="roles").exists())
        self.assertFalse(self.target.user_permissions.exists())

    def test_self_escalation_is_blocked(self):
        manager_employee = Employee.objects.create(
            user=self.manager,
            employee_number="ROLE-SELF",
            full_name="مدير الأدوار",
            operational_section=Employee.OperationalSection.MALE,
        )
        with self.assertRaises(PermissionDenied):
            assign_employee_role(
                actor=self.manager,
                employee=manager_employee,
                role=Role.objects.get(code="system_admin"),
                section=Employee.OperationalSection.MALE,
            )

    def test_manager_cannot_grant_permissions_not_held(self):
        group = Group.objects.create(name="limited-role-manager")
        group.permissions.add(get_platform_permission(PlatformPermissions.MANAGE_ROLES))
        limited_role = Role.objects.create(
            code="limited-role-manager",
            name="مدير أدوار محدود",
            group=group,
            operational_section=Role.OperationalSection.MALE,
        )
        actor = User.objects.create_user(username="limited-manager")
        assign_role_to_user(user=actor, role_code=limited_role.code)
        with self.assertRaises(PermissionDenied):
            assign_employee_role(
                actor=actor,
                employee=self.employee,
                role=Role.objects.get(code="system_admin"),
                section=Employee.OperationalSection.MALE,
            )

    def test_forged_section_is_rejected(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.url, {
            "employee": self.employee.pk,
            "role": "employee",
            "section": "forged",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserRole.objects.filter(user=self.target).exists())

    def test_role_detail_lists_permissions_and_assignees(self):
        assign_role_to_user(user=self.target, role_code="employee")
        self.client.force_login(self.manager)
        response = self.client.get(reverse("roles:role-detail", args=["employee"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "موظف اختبار التسكين")
        self.assertEqual(response.context["permission_count"], Role.objects.get(code="employee").group.permissions.count())

    def test_role_removal_uses_service_and_invalidates_cache(self):
        role = Role.objects.get(code="employee")
        assign_role_to_user(user=self.target, role_code=role.code)
        self.assertTrue(self.target.has_perm(PlatformPermissions.VIEW_SHIFTS))
        remove_employee_role(actor=self.manager, employee=self.employee, role=role)
        self.assertFalse(self.target.has_perm(PlatformPermissions.VIEW_SHIFTS))
        self.assertFalse(UserRole.objects.filter(user=self.target, role=role).exists())
        self.assertTrue(SystemActivityLog.objects.filter(description__contains="إزالة الدور").exists())
