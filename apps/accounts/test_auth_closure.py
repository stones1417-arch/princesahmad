from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import AccountRegistrationRequest
from apps.accounts.services.registration_request_service import (
    approve_account_registration_request,
)
from apps.hr.models import Employee
from apps.roles.services.permission_registry import get_role_definitions
from apps.roles.services.role_manager import (
    assign_role_to_user,
    get_platform_permissions,
    remove_role_from_user,
)

User = get_user_model()


class AuthenticationClosureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")

    def test_every_registered_role_permission_resolves(self):
        definitions = get_role_definitions()

        self.assertEqual(len(definitions), 11)
        for definition in definitions.values():
            permission_codes = definition["permissions"]
            self.assertEqual(
                len(get_platform_permissions(permission_codes)),
                len(permission_codes),
            )

    def test_role_changes_invalidate_permission_cache(self):
        user = User.objects.create_user(username="permission-cache-user")

        self.assertFalse(user.has_perm("roles.manage_users"))
        assign_role_to_user(user=user, role_code="system_admin")
        self.assertTrue(user.has_perm("roles.manage_users"))

        remove_role_from_user(user=user, role_code="system_admin")
        self.assertFalse(user.has_perm("roles.manage_users"))

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
