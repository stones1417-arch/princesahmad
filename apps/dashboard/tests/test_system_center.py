from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog


class SystemCenterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin = user_model.objects.create_superuser(
            username="system_center_admin",
            password="test-password",
        )
        cls.regular_user = user_model.objects.create_user(
            username="system_center_user",
            password="test-password",
        )
        cls.url = reverse("dashboard:system-center")

    def test_admin_renders_system_generated_activity_without_user(self):
        log_activity(
            module="system",
            action=SystemActivityLog.ActionType.OTHER,
            description="System-generated activity",
        )
        self.client.force_login(self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System-generated activity")
        self.assertContains(response, "عملية نظامية")

    def test_authenticated_non_superuser_is_forbidden(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
