from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import AccountRegistrationRequest
from apps.accounts.services.registration_request_service import approve_account_registration_request
from apps.core.tests.factories import create_user
from apps.hr.models import Employee
from apps.roles.models import UserRole
from apps.roles.services.role_manager import assign_role_to_user


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="http://testserver")
class AccountProvisioningE2ETests(TestCase):
    def test_request_to_login_ready_account(self):
        call_command("setup_roles")
        approver = create_user(username="e2e-approver", password="Approver-Test-987!", email="e2e-approver@example.test")
        assign_role_to_user(user=approver, role_code="system_admin")
        registration = AccountRegistrationRequest.objects.create(full_name="موظف دورة كاملة", employee_number="E2E-ACCOUNT-1", requested_username="e2e-account", email="e2e-account@example.test", phone_number="+966551230099", gender="male")
        with self.captureOnCommitCallbacks(execute=True):
            user = approve_account_registration_request(registration, reviewer=approver, role_code="employee", operational_section="male")
        self.assertEqual(User.objects.filter(username="e2e-account").count(), 1)
        self.assertEqual(Employee.objects.filter(user=user).count(), 1)
        self.assertEqual(UserRole.objects.filter(user=user, role__code="employee", is_active=True).count(), 1)
        self.assertFalse(user.is_active)
        path = mail.outbox[0].body.split("http://testserver", 1)[1].strip()
        password = "New-Account-Secure-987!"
        self.client.post(path, {"new_password1": password, "new_password2": password})
        user.refresh_from_db(); registration.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(registration.status, registration.Status.ACTIVATED)
        self.assertTrue(self.client.login(username=user.username, password=password))
