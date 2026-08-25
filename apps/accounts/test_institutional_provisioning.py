from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccountRegistrationRequest
from apps.accounts.services.registration_request_service import approve_account_registration_request
from apps.core.tests.factories import create_user
from apps.hr.models import Employee
from apps.roles.models import UserRole
from apps.roles.services.role_manager import assign_role_to_user


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="http://testserver")
class InstitutionalProvisioningTests(TestCase):
    password = "Strong-Test-Password-987!"

    def setUp(self):
        call_command("setup_roles")
        self.approver = create_user(username="account-approver", password=self.password, email="approver@example.test")
        assign_role_to_user(user=self.approver, role_code="system_admin")
        self.registration = AccountRegistrationRequest.objects.create(full_name="موظف جديد", employee_number="INST-001", requested_username="institutional-user", email="institutional@example.test", phone_number="+966551234599", gender="male")

    def approve(self, **kwargs):
        params = {"reviewer": self.approver, "role_code": "employee", "operational_section": "male"}
        params.update(kwargs)
        with self.captureOnCommitCallbacks(execute=True):
            return approve_account_registration_request(self.registration, **params)

    def test_full_provision_and_activation(self):
        user = self.approve()
        self.registration.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(Employee.objects.filter(user=user).count(), 1)
        self.assertEqual(UserRole.objects.filter(user=user, is_active=True).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.password, mail.outbox[0].body)
        activation_path = mail.outbox[0].body.split("http://testserver", 1)[1].strip()
        response = self.client.post(activation_path, {"new_password1": self.password, "new_password2": self.password})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db(); self.registration.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(self.registration.status, self.registration.Status.ACTIVATED)
        self.assertContains(self.client.get(activation_path), "غير صالح")

    def test_double_approval_is_idempotent(self):
        first = self.approve()
        second = approve_account_registration_request(self.registration, reviewer=self.approver, role_code="employee", operational_section="male")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(User.objects.filter(username="institutional-user").count(), 1)
        self.assertEqual(Employee.objects.filter(employee_number="INST-001").count(), 1)
        self.assertEqual(UserRole.objects.filter(user=first, role__code="employee").count(), 1)

    def test_role_failure_rolls_back_everything(self):
        with patch("apps.accounts.services.registration_request_service.assign_role_to_user", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.approve()
        self.assertFalse(User.objects.filter(username="institutional-user").exists())
        self.assertFalse(Employee.objects.filter(employee_number="INST-001").exists())

    def test_forged_section_and_role_are_blocked(self):
        with self.assertRaises(ValidationError):
            self.approve(operational_section="female")
        with self.assertRaises(PermissionDenied):
            self.approve(role_code="missing-role")

    def test_self_approval_is_blocked(self):
        self.registration.requested_username = self.approver.username
        self.registration.save(update_fields=["requested_username"])
        with self.assertRaises(PermissionDenied):
            self.approve()

    def test_institutional_pages_require_permission(self):
        outsider = create_user(username="outsider", password=self.password, email="outside@example.test")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("accounts:registration-request-list")).status_code, 403)
        self.client.force_login(self.approver)
        self.assertEqual(self.client.get(reverse("accounts:registration-request-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:registration-request-review", args=[self.registration.pk])).status_code, 200)
