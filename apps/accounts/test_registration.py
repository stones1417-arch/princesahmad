from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccountProfile, AccountRegistrationRequest
from apps.accounts.security import has_completed_two_factor, requires_two_factor
from apps.accounts.services.registration_request_service import (
    approve_account_registration_request,
)
from apps.core.tests.factories import create_user
from apps.hr.models import Employee
from apps.roles.models import Role, UserRole
from apps.roles.services.role_manager import assign_role_to_user


@override_settings(
    ALLOW_PUBLIC_REGISTRATION=True,
    AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"),
)
class RegistrationRequestFlowTests(TestCase):
    password = "StrongTestPassword123!"

    def setUp(self):
        call_command("setup_roles")

    def _payload(self, **overrides):
        payload = {
            "full_name": "مستخدم تجريبي",
            "employee_number": "EMP-1001",
            "requested_username": "new-user",
            "email": "new.user@example.test",
            "phone_number": "0551234567",
            "gender": AccountRegistrationRequest.Gender.MALE,
        }
        payload.update(overrides)
        return payload

    def _register(self, **overrides):
        return self.client.post("/accounts/register/", self._payload(**overrides))

    def test_public_registration_creates_a_pending_request_only(self):
        response = self._register()

        self.assertRedirects(response, "/accounts/login/")
        self.assertEqual(AccountRegistrationRequest.objects.count(), 1)

        request = AccountRegistrationRequest.objects.get(requested_username="new-user")
        self.assertEqual(request.status, AccountRegistrationRequest.Status.PENDING)
        self.assertIsNone(request.created_user)
        self.assertFalse(User.objects.filter(username="new-user").exists())
        self.assertFalse(Employee.objects.filter(employee_number="EMP-1001").exists())
        self.assertFalse(AccountProfile.objects.filter(phone_number="+966551234567").exists())

    def test_invalid_phone_and_email_are_rejected_without_creating_request(self):
        phone_response = self._register(phone_number="0411234567")
        email_response = self._register(
            requested_username="invalid-email",
            employee_number="EMP-1002",
            email="invalid-email",
        )

        self.assertContains(phone_response, "رقم الجوال غير صالح")
        self.assertContains(email_response, "البريد الإلكتروني غير صالح")
        self.assertFalse(AccountRegistrationRequest.objects.filter(requested_username="new-user").exists())
        self.assertFalse(AccountRegistrationRequest.objects.filter(requested_username="invalid-email").exists())

    def test_duplicate_pending_request_data_is_rejected(self):
        AccountRegistrationRequest.objects.create(
            full_name="مستخدم قائم",
            employee_number="EMP-1001",
            requested_username="new-user",
            email="new.user@example.test",
            phone_number="+966551234567",
            gender=AccountRegistrationRequest.Gender.MALE,
        )

        response = self._register()

        self.assertContains(response, "اسم المستخدم مستخدم مسبقًا.")
        self.assertEqual(AccountRegistrationRequest.objects.filter(requested_username__iexact="new-user").count(), 1)

    def test_approval_service_requires_pending_or_needs_edit_and_uses_unusable_password(self):
        approver = create_user(
            username="approver-2",
            password=self.password,
            email="approver-2@example.test",
        )
        assign_role_to_user(user=approver, role_code="system_admin")

        request_obj = AccountRegistrationRequest.objects.create(
            full_name="مستخدم يحتاج مراجعة",
            employee_number="EMP-APPROVED-2",
            requested_username="needs-edit-user",
            email="needs.edit@example.test",
            phone_number="+966551234569",
            gender=AccountRegistrationRequest.Gender.MALE,
            status=AccountRegistrationRequest.Status.NEEDS_EDIT,
        )

        created = approve_account_registration_request(request_obj, reviewer=approver)

        self.assertFalse(created.is_active)
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertFalse(created.has_usable_password())
        self.assertEqual(request_obj.status, AccountRegistrationRequest.Status.APPROVED)

    def test_approval_service_creates_user_and_assigns_employee_role(self):
        request_obj = AccountRegistrationRequest.objects.create(
            full_name="مستخدم معتمد",
            employee_number="EMP-APPROVED-1",
            requested_username="approved-user",
            email="approved.user@example.test",
            phone_number="+966551234568",
            gender=AccountRegistrationRequest.Gender.FEMALE,
        )

        approver = create_user(
            username="approver",
            password=self.password,
            email="approver@example.test",
        )
        assign_role_to_user(user=approver, role_code="system_admin")

        created = approve_account_registration_request(request_obj, reviewer=approver)

        self.assertEqual(request_obj.status, AccountRegistrationRequest.Status.APPROVED)
        self.assertEqual(request_obj.created_user, created)
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertTrue(
            UserRole.objects.filter(user=created, role__code="employee", is_active=True).exists()
        )
        self.assertEqual(created.employee.operational_section, Employee.OperationalSection.FEMALE)
        self.assertEqual(created.employee.job_title, Employee.JobTitle.MONITOR)


@override_settings(ALLOW_PUBLIC_REGISTRATION=False)
class AccountRegistrationAdminMenuTests(TestCase):
    password = "StrongTestPassword123!"

    def setUp(self):
        call_command("setup_roles")

    def test_system_admin_sees_registration_requests_menu_with_pending_count(self):
        AccountRegistrationRequest.objects.create(
            full_name="طلب معلق 1",
            employee_number="EMP-LIST-1",
            requested_username="pending-register-1",
            email="pending-register-1@example.test",
            phone_number="+966551234561",
            gender=AccountRegistrationRequest.Gender.MALE,
            status=AccountRegistrationRequest.Status.PENDING,
        )
        AccountRegistrationRequest.objects.create(
            full_name="طلب معتمد",
            employee_number="EMP-LIST-2",
            requested_username="approved-register-1",
            email="approved-register-1@example.test",
            phone_number="+966551234562",
            gender=AccountRegistrationRequest.Gender.FEMALE,
            status=AccountRegistrationRequest.Status.APPROVED,
        )

        user = create_user(username="menu-admin", password=self.password, email="menu-admin@example.test")
        assign_role_to_user(user=user, role_code="system_admin")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "طلبات إنشاء الحساب")
        self.assertContains(response, "<b>1</b>", html=False)
        self.assertNotContains(response, "<b>2</b>", html=False)

    def test_regular_user_does_not_see_registration_requests_menu(self):
        user = create_user(username="normal-user", password=self.password, email="normal-user@example.test")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "طلبات إنشاء الحساب")

    def test_registration_request_admin_changelist_requires_manage_users_permission(self):
        user = create_user(
            username="non-manager",
            password=self.password,
            email="non-manager@example.test",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:accounts_accountregistrationrequest_changelist"))

        self.assertEqual(response.status_code, 302)

        user_with_permission = create_user(
            username="manager-user",
            password=self.password,
            email="manager-user@example.test",
            is_staff=True,
        )
        assign_role_to_user(user=user_with_permission, role_code="system_admin")
        self.client.force_login(user_with_permission)
        session = self.client.session
        session["admin_two_factor_verified"] = user_with_permission.pk
        session.save()

        permitted = self.client.get(reverse("admin:accounts_accountregistrationrequest_changelist"))
        self.assertEqual(permitted.status_code, 200)

    def test_pending_registration_request_change_page_opens_for_authorized_admin(self):
        user = create_user(
            username="change-admin",
            password=self.password,
            email="change-admin@example.test",
            is_staff=True,
        )
        assign_role_to_user(user=user, role_code="system_admin")
        self.client.force_login(user)

        session = self.client.session
        session["admin_two_factor_verified"] = user.pk
        session.save()

        request_obj = AccountRegistrationRequest.objects.create(
            full_name="طلب مراجعة",
            employee_number="EMP-CHANGE-1",
            requested_username="pending-change-user",
            email="pending-change-user@example.test",
            phone_number="+966551234560",
            gender=AccountRegistrationRequest.Gender.MALE,
            status=AccountRegistrationRequest.Status.PENDING,
        )

        response = self.client.get(
            reverse("admin:accounts_accountregistrationrequest_change", args=[request_obj.pk])
        )

        self.assertEqual(response.status_code, 200)


@override_settings(ALLOW_PUBLIC_REGISTRATION=False)
class AdminUserCreationSecurityTests(TestCase):
    password = "StrongTestPassword123!"

    def setUp(self):
        call_command("setup_roles")

    def _login_admin(self, *, username="admin-creator", role_code="system_admin"):
        user = create_user(username=username, password=self.password, email=f"{username}@example.test")
        assign_role_to_user(user=user, role_code=role_code)
        role = Role.objects.get(code=role_code)
        role.operational_section = Role.OperationalSection.ALL
        role.save(update_fields=["operational_section", "updated_at"])
        self.client.force_login(user)
        session = self.client.session
        session["admin_two_factor_verified"] = user.pk
        session.save()
        return user

    def test_public_registration_is_blocked_in_production(self):
        response = self.client.get("/accounts/register/")
        self.assertEqual(response.status_code, 403)

    def test_system_admin_with_manage_users_and_completed_2fa_can_open_admin_create_page(self):
        self._login_admin()
        response = self.client.get(reverse("accounts:admin-user-create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "إنشاء حساب جديد")
        self.assertNotContains(response, "/accounts/register/")

    def test_user_without_manage_users_cannot_open_admin_create_page(self):
        user = create_user(username="no-manage-users", password=self.password, email="no-manage@example.test")
        self.client.force_login(user)
        session = self.client.session
        session["admin_two_factor_verified"] = user.pk
        session.save()
        response = self.client.get(reverse("accounts:admin-user-create"))
        self.assertEqual(response.status_code, 403)

    def test_user_without_completed_2fa_is_blocked_from_admin_create_page(self):
        self._login_admin()
        session = self.client.session
        session.pop("admin_two_factor_verified", None)
        session.save()

        user = User.objects.get(username="admin-creator")
        request = RequestFactory().get(reverse("accounts:admin-user-create"))
        request.session = session
        request.user = user

        self.assertTrue(requires_two_factor(user))
        self.assertFalse(has_completed_two_factor(request, user))

        response = self.client.get(reverse("accounts:admin-user-create"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:two-factor"))

    def test_post_without_completed_2fa_is_blocked_and_does_not_create_user(self):
        self._login_admin()
        session = self.client.session
        session.pop("admin_two_factor_verified", None)
        session.save()

        user = User.objects.get(username="admin-creator")
        request = RequestFactory().get(reverse("accounts:admin-user-create"))
        request.session = session
        request.user = user

        self.assertTrue(requires_two_factor(user))
        self.assertFalse(has_completed_two_factor(request, user))

        before_count = User.objects.count()
        payload = {
            "full_name": "مستخدم إداري جديد",
            "employee_number": "EMP-ADMIN-2004",
            "username": "new-admin-user-no-2fa",
            "email": "new-admin-user-no-2fa@example.test",
            "password": self.password,
            "operational_section": Employee.OperationalSection.MALE,
            "job_title": Employee.JobTitle.SECURITY,
            "phone_number": "0551234570",
            "role": "hr_manager",
        }
        response = self.client.post(reverse("accounts:admin-user-create"), payload, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:two-factor"))
        self.assertEqual(User.objects.count(), before_count)
        self.assertFalse(User.objects.filter(username="new-admin-user-no-2fa").exists())

    def test_valid_admin_post_creates_user_and_assigns_role(self):
        self._login_admin()
        payload = {
            "full_name": "مستخدم إداري جديد",
            "employee_number": "EMP-ADMIN-2001",
            "username": "new-admin-user",
            "email": "new-admin-user@example.test",
            "password": self.password,
            "operational_section": Employee.OperationalSection.MALE,
            "job_title": Employee.JobTitle.SECURITY,
            "phone_number": "0551234567",
            "role": "hr_manager",
        }
        response = self.client.post(reverse("accounts:admin-user-create"), payload)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="new-admin-user")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(UserRole.objects.filter(user=user, role__code="hr_manager", is_active=True).exists())

    def test_duplicate_username_is_rejected_for_admin_create(self):
        self._login_admin()
        User.objects.create_user(username="existing-admin-user", password=self.password, email="existing-admin-user@example.test")
        payload = {
            "full_name": "مستخدم إداري",
            "employee_number": "EMP-ADMIN-2002",
            "username": "existing-admin-user",
            "email": "existing-admin-user@example.test",
            "password": self.password,
            "operational_section": Employee.OperationalSection.MALE,
            "job_title": Employee.JobTitle.SECURITY,
            "phone_number": "0551234568",
            "role": "hr_manager",
        }
        response = self.client.post(reverse("accounts:admin-user-create"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اسم المستخدم مستخدم مسبقًا")

    def test_limited_admin_cannot_create_user_outside_allowed_section(self):
        user = self._login_admin(role_code="hr_manager")
        role = Role.objects.get(code="hr_manager")
        role.operational_section = Role.OperationalSection.MALE
        role.save(update_fields=["operational_section", "updated_at"])
        payload = {
            "full_name": "مستخدم إداري محدود",
            "employee_number": "EMP-ADMIN-2003",
            "username": "limited-admin-create",
            "email": "limited-admin-create@example.test",
            "password": self.password,
            "operational_section": Employee.OperationalSection.FEMALE,
            "job_title": Employee.JobTitle.SECURITY,
            "phone_number": "0551234569",
            "role": "hr_manager",
        }
        response = self.client.post(reverse("accounts:admin-user-create"), payload)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="limited-admin-create").exists())
