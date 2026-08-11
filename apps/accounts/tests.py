from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.hr.models import Employee

from apps.accounts.models import AccountProfile


class RegisterViewTests(TestCase):
    def test_new_executive_job_titles_are_available(self):
        labels = dict(Employee.JobTitle.choices)
        self.assertEqual(
            labels[Employee.JobTitle.DEPUTY_CEO_OPERATIONS],
            "نائب الرئيس التنفيذي للتشغيل للمسجد النبوي الشريف",
        )
        self.assertEqual(
            labels[Employee.JobTitle.CEO_OFFICE],
            "مكتب الرئيس التنفيذي",
        )
        self.assertEqual(
            labels[Employee.JobTitle.CHAIRMAN_OFFICE],
            "مكتب معالي: رئيس مجلس الإدارة",
        )
        self.assertEqual(
            list(Employee.JobTitle.values)[:3],
            [
                Employee.JobTitle.CHAIRMAN_OFFICE,
                Employee.JobTitle.CEO_OFFICE,
                Employee.JobTitle.DEPUTY_CEO_OPERATIONS,
            ],
        )

    def test_registration_without_photo_is_allowed(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "مستخدم تجريبي",
                "employee_number": "EMP-9001",
                "job_title": Employee.JobTitle.MONITOR,
                "username": "register_test",
                "password": "SafePass123!",
                "operational_section": Employee.OperationalSection.MALE,
                "email": "register@example.test",
                "phone_number": "0551234567",
            },
        )

        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(username="register_test")
        self.assertEqual(user.employee.job_title, Employee.JobTitle.MONITOR)
        self.assertEqual(
            user.employee.operational_section,
            Employee.OperationalSection.MALE,
        )
        self.assertFalse(bool(user.account_profile.photo))

    def test_invalid_job_title_does_not_create_account(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "مستخدم تجريبي",
                "employee_number": "EMP-9002",
                "job_title": "invalid-title",
                "username": "invalid_title_test",
                "password": "SafePass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="invalid_title_test").exists())
        self.assertFalse(AccountProfile.objects.exists())

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "مستخدم ضعيف",
                "employee_number": "EMP-9003",
                "job_title": Employee.JobTitle.MONITOR,
                "username": "weak_password",
                "password": "12345678",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="weak_password").exists())

    @override_settings(ALLOW_PUBLIC_REGISTRATION=False)
    def test_public_registration_can_be_disabled(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 403)


class LoginViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="login_test",
            password="SafePass123!",
        )

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "login_test", "password": "SafePass123!"},
        )
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_external_next_url_is_not_used(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "login_test",
                "password": "SafePass123!",
                "next": "https://example.com/unsafe",
            },
        )
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_remember_me_creates_persistent_session(self):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "login_test",
                "password": "SafePass123!",
                "remember_me": "on",
            },
        )
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24 * 29)

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=3, LOGIN_RATE_LIMIT_WINDOW=60)
    def test_repeated_failed_logins_are_temporarily_limited(self):
        for _ in range(3):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": "login_test", "password": "wrong"},
                REMOTE_ADDR="192.0.2.10",
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "login_test", "password": "wrong"},
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertEqual(response.status_code, 429)

    def test_security_headers_are_applied(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertEqual(
            response["Referrer-Policy"],
            "strict-origin-when-cross-origin",
        )
