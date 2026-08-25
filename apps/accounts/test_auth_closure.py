from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AccountRegistrationRequest
from apps.accounts.services.registration_request_service import (
    approve_account_registration_request,
)
from apps.hr.models import Employee
from apps.roles.models import Role, UserRole
from apps.roles.services.permission_registry import get_role_definitions
from apps.roles.services.role_manager import (
    assign_role_to_user,
    get_platform_permission,
    get_platform_permissions,
    remove_role_from_user,
)

User = get_user_model()


class AuthenticationClosureTests(TestCase):
    password = "StrongAuthClosurePassword123!"

    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")

    def _create_role(self, *, code, permission_codes, section=Role.OperationalSection.ALL):
        group = Group.objects.create(name=f"auth-closure-{code}")
        group.permissions.set(
            [get_platform_permission(value) for value in permission_codes]
        )
        return Role.objects.create(
            code=code,
            name=f"Auth closure {code}",
            group=group,
            operational_section=section,
            is_active=True,
        )

    def _admin_create_payload(self, **overrides):
        payload = {
            "full_name": "مستخدم اختبار الصلاحيات",
            "employee_number": "AUTH-CLOSURE-NEW",
            "username": "auth-closure-new-user",
            "email": "auth-closure-new@example.test",
            "password": self.password,
            "phone_number": "0551234599",
            "job_title": Employee.JobTitle.SECURITY,
            "operational_section": Employee.OperationalSection.MALE,
            "role": "employee",
        }
        payload.update(overrides)
        return payload

    def test_every_registered_role_permission_resolves(self):
        definitions = get_role_definitions()

        self.assertEqual(len(definitions), 14)
        for definition in definitions.values():
            permission_codes = definition["permissions"]
            self.assertEqual(
                len(get_platform_permissions(permission_codes)),
                len(permission_codes),
            )

    def test_explicit_cross_app_permission_resolves_and_grants(self):
        permission_code = "core.view_systemconfiguration"
        permission = get_platform_permission(permission_code)
        self.assertEqual(permission.content_type.app_label, "core")

        role = self._create_role(
            code="cross-app-reader",
            permission_codes=[permission_code],
        )
        user = User.objects.create_user(username="cross-app-reader")
        assign_role_to_user(user=user, role_code=role.code)

        self.assertTrue(user.has_perm(permission_code))

    def test_unknown_permission_fails_closed(self):
        with self.assertRaises(Permission.DoesNotExist):
            get_platform_permission("reporting.permission_that_does_not_exist")

        with self.assertRaises(ValidationError):
            get_platform_permissions(["reporting.permission_that_does_not_exist"])

    def test_role_changes_invalidate_permission_cache(self):
        user = User.objects.create_user(username="permission-cache-user")

        self.assertFalse(user.has_perm("roles.manage_users"))
        assign_role_to_user(user=user, role_code="system_admin")
        self.assertTrue(user.has_perm("roles.manage_users"))

        remove_role_from_user(user=user, role_code="system_admin")
        self.assertFalse(user.has_perm("roles.manage_users"))

    def test_role_replacement_invalidates_permission_cache(self):
        first_role = self._create_role(
            code="replacement-first",
            permission_codes=["roles.view_employees"],
        )
        second_role = self._create_role(
            code="replacement-second",
            permission_codes=["roles.view_reports"],
        )
        user = User.objects.create_user(username="replacement-user")
        assignment = UserRole.objects.create(user=user, role=first_role)

        self.assertTrue(user.has_perm("roles.view_employees"))
        self.assertFalse(user.has_perm("roles.view_reports"))

        assignment.role = second_role
        assignment.save(update_fields=["role", "updated_at"])

        self.assertFalse(user.has_perm("roles.view_employees"))
        self.assertTrue(user.has_perm("roles.view_reports"))

    def test_direct_user_role_create_and_delete_invalidate_permission_cache(self):
        role = self._create_role(
            code="direct-mutation",
            permission_codes=["roles.view_reports"],
        )
        user = User.objects.create_user(username="direct-mutation-user")

        self.assertFalse(user.has_perm("roles.view_reports"))
        assignment = UserRole.objects.create(user=user, role=role)
        self.assertTrue(user.has_perm("roles.view_reports"))

        assignment.delete()
        self.assertFalse(user.has_perm("roles.view_reports"))

    def test_low_privilege_user_cannot_grant_self_system_admin_role(self):
        actor = User.objects.create_user(
            username="self-escalation-actor",
            password=self.password,
            is_staff=True,
        )
        system_admin = Role.objects.get(code="system_admin")
        self.client.force_login(actor)

        response = self.client.post(
            reverse("admin:roles_userrole_add"),
            {"user": actor.pk, "role": system_admin.pk, "is_active": "on"},
        )

        self.assertIn(response.status_code, {302, 403})
        self.assertFalse(
            UserRole.objects.filter(user=actor, role=system_admin, is_active=True).exists()
        )

    def test_low_privilege_user_cannot_grant_another_user_privileged_role(self):
        actor = User.objects.create_user(
            username="other-escalation-actor",
            password=self.password,
        )
        target = User.objects.create_user(username="other-escalation-target")
        self.client.force_login(actor)

        response = self.client.post(
            reverse("accounts:admin-user-create"),
            self._admin_create_payload(
                username=target.username,
                employee_number="AUTH-OTHER-ESCALATION",
                role="system_admin",
                is_staff="on",
                is_superuser="on",
                groups=[Group.objects.first().pk],
                user_permissions=[Permission.objects.first().pk],
            ),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserRole.objects.filter(user=target).exists())
        target.refresh_from_db()
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)

    def test_low_privilege_staff_cannot_mutate_role_or_group(self):
        actor = User.objects.create_user(
            username="role-permission-escalation-actor",
            password=self.password,
            is_staff=True,
        )
        employee_role = Role.objects.select_related("group").get(code="employee")
        original_group_id = employee_role.group_id
        system_admin = Role.objects.select_related("group").get(code="system_admin")
        self.client.force_login(actor)

        response = self.client.post(
            reverse("admin:roles_role_change", args=[employee_role.pk]),
            {
                "code": employee_role.code,
                "name": employee_role.name,
                "description": employee_role.description,
                "operational_section": employee_role.operational_section,
                "group": system_admin.group_id,
                "is_system_role": "on",
                "is_active": "on",
            },
        )

        self.assertIn(response.status_code, {302, 403})
        employee_role.refresh_from_db()
        self.assertEqual(employee_role.group_id, original_group_id)

    def test_is_staff_alone_does_not_grant_platform_permissions(self):
        user = User.objects.create_user(username="staff-only", is_staff=True)

        self.assertFalse(user.has_perm("roles.manage_users"))
        self.assertFalse(user.has_perm("roles.manage_roles"))

    def test_scoped_manager_cannot_create_user_outside_section(self):
        role = self._create_role(
            code="scoped-user-manager",
            permission_codes=["roles.manage_users"],
            section=Role.OperationalSection.MALE,
        )
        actor = User.objects.create_user(
            username="scoped-user-manager",
            password=self.password,
        )
        assign_role_to_user(user=actor, role_code=role.code)
        self.client.force_login(actor)

        response = self.client.post(
            reverse("accounts:admin-user-create"),
            self._admin_create_payload(
                employee_number="AUTH-SECTION-ESCALATION",
                username="section-escalation-target",
                operational_section=Employee.OperationalSection.FEMALE,
            ),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="section-escalation-target").exists())

    def test_registration_rolls_back_when_role_assignment_fails(self):
        registration = AccountRegistrationRequest.objects.create(
            full_name="مستخدم اختبار التراجع",
            employee_number="AUTH-ROLLBACK-1",
            requested_username="auth-rollback-user",
            email="auth.rollback@example.test",
            phone_number="+966551234570",
            gender=AccountRegistrationRequest.Gender.MALE,
        )

        with patch(
            "apps.accounts.services.registration_request_service.assign_role_to_user",
            side_effect=RuntimeError("role assignment failed"),
        ):
            with self.assertRaises(RuntimeError):
                approve_account_registration_request(registration)

        self.assertFalse(User.objects.filter(username="auth-rollback-user").exists())
        self.assertFalse(Employee.objects.filter(employee_number="AUTH-ROLLBACK-1").exists())
        registration.refresh_from_db()
        self.assertEqual(registration.status, AccountRegistrationRequest.Status.PENDING)
