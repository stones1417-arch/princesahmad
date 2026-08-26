from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class OperationsMenuNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="operations-menu-admin",
            email="operations-menu@example.test",
            password="test-pass",
        )

    def test_required_operations_routes_remain_in_menu_dom(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("ops:operations-center"))
        self.assertEqual(response.status_code, 200)
        for route in (
            "ops:operations-center",
            "ops:command-center",
            "ops:department-command-center",
            "ops:doors",
            "ops:incidents",
            "ops:maintenance-list",
        ):
            self.assertContains(response, f'href="{reverse(route)}"')
        self.assertContains(response, "data-operations-menu-scroll")
        self.assertContains(response, "مركز البلاغات التشغيلية")
        self.assertContains(response, "مركز إدارة الصيانة")

    def test_menu_marks_low_items_active_without_changing_routes(self):
        self.client.force_login(self.user)
        for route in ("ops:doors", "ops:incidents", "ops:maintenance-list"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertContains(
                    response,
                    f'href="{reverse(route)}" class="unified-menu-item" aria-current="page"',
                )

    def test_scroll_css_and_keyboard_contracts_are_owned_by_menu(self):
        root = Path(__file__).resolve().parents[3]
        css = (root / "static/css/components/enterprise_header.css").read_text(
            encoding="utf-8"
        )
        template = (root / "templates/components/menu_operations.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(".operations-menu__scroll", css)
        self.assertIn("min-height: 0", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("overflow-x: hidden", css)
        self.assertIn("100dvh", css)
        self.assertIn('scrollIntoView({block:"nearest"})', template)
        self.assertIn('event.key==="Escape"', template)
