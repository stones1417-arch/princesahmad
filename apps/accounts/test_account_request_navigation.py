from django.core.management import call_command
from django.test import TestCase
from django.template.loader import get_template
from django.urls import reverse

from apps.accounts.models import AccountRegistrationRequest
from apps.core.tests.factories import create_user
from apps.roles.services.role_manager import assign_role_to_user


class AccountRequestNavigationTests(TestCase):
    password = "Navigation-Test-987!"

    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")
        cls.reviewer = create_user(username="navigation-reviewer", password=cls.password, email="nav-reviewer@example.test")
        assign_role_to_user(user=cls.reviewer, role_code="system_admin")
        cls.outsider = create_user(username="navigation-outsider", password=cls.password, email="nav-outsider@example.test")
        cls.registration = AccountRegistrationRequest.objects.create(full_name="طلب تنقل", employee_number="NAV-001", requested_username="navigation-request", email="nav-request@example.test", phone_number="+966551234501", gender="male")

    def test_authorized_menu_targets_institutional_list_not_admin(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertContains(response, f'href="{reverse("accounts:registration-request-list")}"')
        self.assertNotContains(response, f'href="{reverse("admin:accounts_accountregistrationrequest_changelist")}"')
        self.assertContains(response, "admin-dropdown enterprise-nav-dropdown is-active")
        self.assertContains(response, "الإدارة")

    def test_unauthorized_menu_hidden_and_direct_routes_forbidden(self):
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse("dashboard:index")), reverse("accounts:registration-request-list"))
        self.assertEqual(self.client.get(reverse("accounts:registration-request-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:registration-request-review", args=[self.registration.pk])).status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_list_review_link_stays_in_institutional_ui(self):
        self.client.force_login(self.reviewer)
        source = get_template("accounts/registration_request_list.html").template.source
        self.assertIn("accounts:registration-request-review", source)
        self.assertNotIn("admin:accounts_accountregistrationrequest_change", source)
        review_url = reverse("accounts:registration-request-review", args=[self.registration.pk])
        response = self.client.get(review_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مراجعة الطلب")

    def test_django_admin_fallback_remains_registered(self):
        self.assertEqual(reverse("admin:accounts_accountregistrationrequest_changelist"), "/admin/accounts/accountregistrationrequest/")
