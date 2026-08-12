from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccountProfile
from apps.accounts.security import has_completed_two_factor, requires_two_factor
from apps.accounts.views import _employee_otp_channels
from apps.core.tests.factories import create_user
from apps.hr.models import Employee
from apps.roles.models import Role, UserRole
from apps.roles.services.role_manager import assign_role_to_user


@override_settings(
    ALLOW_PUBLIC_REGISTRATION=True,
    AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"),
)
class RegistrationTwoFactorReadinessTests(TestCase):
    password = "StrongTestPassword123!"

    def _payload(self, **overrides):
        payload = {
            "full_name": "مستخدم تجريبي",
            "employee_number": "EMP-1001",
            "username": "new-user",
            "password": self.password,
            "operational_section": Employee.OperationalSection.MALE,
            "job_title": Employee.JobTitle.SECURITY,
            "email": "new.user@example.test",
            "phone_number": "0551234567",
        }
        payload.update(overrides)
        return payload

    def _register(self, **overrides):
        return self.client.post("/accounts/register/", self._payload(**overrides))

    def test_registration_persists_2fa_contact_details_and_channels(self):
        response = self._register()

        self.assertRedirects(response, "/accounts/login/")
        user = User.objects.get(username="new-user")
        employee = Employee.objects.get(user=user)
        profile = AccountProfile.objects.get(user=user)
        self.assertEqual(user.email, "new.user@example.test")
        self.assertEqual(employee.email, user.email)
        self.assertEqual(employee.phone_number, "+966551234567")
        self.assertEqual(profile.phone_number, "+966551234567")
        self.assertEqual(
            employee.operational_section,
            Employee.OperationalSection.MALE,
        )
        self.assertEqual(_employee_otp_channels(user), ["sms", "whatsapp", "email"])

    def test_registration_does_not_grant_roles_or_administrative_access(self):
        self._register()

        user = User.objects.get(username="new-user")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.platform_role_assignments.exists())

    def test_saudi_phone_formats_are_normalized(self):
        for index, value in enumerate(("0551234567", "551234567", "+966551234567"), 1):
            response = self._register(
                username=f"phone-user-{index}",
                employee_number=f"EMP-{index}",
                email=f"phone-{index}@example.test",
                phone_number=value,
            )

            self.assertRedirects(response, "/accounts/login/")
            self.assertEqual(
                Employee.objects.get(employee_number=f"EMP-{index}").phone_number,
                "+966551234567",
            )
            AccountProfile.objects.filter(
                user__username=f"phone-user-{index}"
            ).delete()
            Employee.objects.filter(employee_number=f"EMP-{index}").delete()

    def test_registration_accepts_the_female_operational_section(self):
        response = self._register(
            employee_number="EMP-1002",
            username="female-user",
            email="female.user@example.test",
            phone_number="0551234568",
            operational_section=Employee.OperationalSection.FEMALE,
        )

        self.assertRedirects(response, "/accounts/login/")
        self.assertEqual(
            Employee.objects.get(employee_number="EMP-1002").operational_section,
            Employee.OperationalSection.FEMALE,
        )

    def test_invalid_phone_and_email_are_rejected_without_creating_user(self):
        phone_response = self._register(phone_number="0411234567")
        email_response = self._register(
            username="invalid-email",
            employee_number="EMP-1002",
            email="invalid-email",
        )

        self.assertContains(phone_response, "رقم الجوال غير صالح")
        self.assertContains(email_response, "البريد الإلكتروني غير صالح")
        self.assertFalse(User.objects.filter(username="new-user").exists())
        self.assertFalse(User.objects.filter(username="invalid-email").exists())

    def test_invalid_operational_section_is_rejected_without_creating_user(self):
        response = self._register(operational_section="all")

        self.assertContains(response, "اختر القسم التشغيلي: رجالي أو نسائي.")
        self.assertFalse(User.objects.filter(username="new-user").exists())

    def test_duplicate_email_and_phone_are_rejected(self):
        User.objects.create_user(
            username="existing-email",
            password=self.password,
            email="new.user@example.test",
        )
        email_response = self._register()
        self.assertContains(email_response, "البريد الإلكتروني مستخدم مسبقًا.")

        existing_user = User.objects.create_user(
            username="existing-phone",
            password=self.password,
            email="existing.phone@example.test",
        )
        Employee.objects.create(
            user=existing_user,
            full_name="مستخدم قائم",
            employee_number="EMP-EXISTING",
            operational_section=Employee.OperationalSection.MALE,
            job_title=Employee.JobTitle.SECURITY,
            phone_number="+966551234567",
            email=existing_user.email,
        )
        phone_response = self._register(
            username="duplicate-phone",
            employee_number="EMP-1003",
            email="duplicate.phone@example.test",
        )
        self.assertContains(phone_response, "رقم الجوال مستخدم مسبقًا.")

    def test_password_is_not_rendered_after_validation_error(self):
        response = self._register(phone_number="invalid", password="SecretPassword987!")

        self.assertNotContains(response, "SecretPassword987!")

    def test_employee_creation_failure_rolls_back_user_and_profile(self):
        with patch(
            "apps.accounts.views.Employee.objects.create",
            side_effect=IntegrityError,
        ):
            response = self._register()

        self.assertContains(
            response,
            "تعذر إنشاء الحساب لأن بعض البيانات مستخدمة مسبقًا.",
        )
        self.assertFalse(User.objects.filter(username="new-user").exists())
        self.assertFalse(AccountProfile.objects.exists())


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