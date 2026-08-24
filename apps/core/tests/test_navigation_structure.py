from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse


class NavigationStructureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="navigation-user")

    def render_menu(self, template_name, user, *, namespace="core", url_name="home"):
        request = RequestFactory().get("/")
        request.user = user
        request.resolver_match = SimpleNamespace(
            namespace=namespace,
            url_name=url_name,
        )
        return render_to_string(template_name, {"request": request}, request=request)

    def test_operations_center_exists_only_in_operations_navigation(self):
        home = self.render_menu("components/menu_home.html", self.user)
        operations = self.render_menu("components/menu_operations.html", self.user)
        center_url = reverse("ops:operations-center")

        self.assertNotIn(f'href="{center_url}"', home)
        self.assertNotIn("مركز العمليات المباشرة", home)
        self.assertEqual(operations.count(f'href="{center_url}"'), 1)
        self.assertEqual((home + operations).count(f'href="{center_url}"'), 1)
        self.assertIn("مركز العمليات المباشرة", operations)
        self.assertIn("لوحة موحدة للمتابعة والتحكم", operations)

    def test_home_keeps_existing_executive_and_account_entries(self):
        home = self.render_menu("components/menu_home.html", self.user)
        for label in (
            "لوحة التحكم التنفيذية",
            "الملف الشخصي",
        ):
            self.assertIn(label, home)
        self.assertIn(reverse("dashboard:index"), home)

    def test_command_room_moves_to_operations_and_activity_log_leaves_home(self):
        home = self.render_menu("components/menu_home.html", self.user)
        operations = self.render_menu("components/menu_operations.html", self.user)
        command_url = reverse("ops:command-center")
        activity_log_url = reverse("ops:activity-log")

        self.assertNotIn(f'href="{command_url}"', home)
        self.assertNotIn("غرفة القيادة والتحكم", home)
        self.assertEqual(operations.count(f'href="{command_url}"'), 1)
        self.assertEqual((home + operations).count(f'href="{command_url}"'), 1)
        self.assertIn("غرفة القيادة والتحكم", operations)
        self.assertIn("المتابعة اللحظية واتخاذ القرار", operations)
        self.assertNotIn(f'href="{activity_log_url}"', home)
        self.assertNotIn("سجل العمليات", home)

    def test_command_room_active_state_belongs_to_operations_menu(self):
        operations = self.render_menu(
            "components/menu_operations.html",
            self.user,
            namespace="ops",
            url_name="command-center",
        )
        home = self.render_menu(
            "components/menu_home.html",
            self.user,
            namespace="ops",
            url_name="command-center",
        )

        self.assertIn("operations-dropdown enterprise-nav-dropdown is-active", operations)
        self.assertIn('aria-current="page"', operations)
        self.assertNotIn("is-active", home)

    def test_command_room_keeps_existing_authentication_contract(self):
        anonymous = type(
            "Anonymous",
            (),
            {"is_authenticated": False, "is_staff": False},
        )()
        authenticated_menu = self.render_menu(
            "components/menu_operations.html", self.user
        )
        anonymous_menu = self.render_menu(
            "components/menu_operations.html", anonymous
        )
        command_url = reverse("ops:command-center")

        self.assertIn(f'href="{command_url}"', authenticated_menu)
        self.assertNotIn(f'href="{command_url}"', anonymous_menu)
        self.assertEqual(self.client.get(command_url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(command_url).status_code, 200)

    def test_activity_log_direct_security_contract_is_unchanged(self):
        activity_log_url = reverse("ops:activity-log")

        self.assertEqual(self.client.get(activity_log_url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(activity_log_url).status_code, 403)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.assertEqual(self.client.get(activity_log_url).status_code, 200)

    def test_operations_center_active_state_belongs_to_operations_menu(self):
        operations = self.render_menu(
            "components/menu_operations.html",
            self.user,
            namespace="ops",
            url_name="operations-center",
        )
        home = self.render_menu(
            "components/menu_home.html",
            self.user,
            namespace="ops",
            url_name="operations-center",
        )
        self.assertIn("operations-dropdown enterprise-nav-dropdown is-active", operations)
        self.assertIn('aria-current="page"', operations)
        self.assertIn("operations-dropdown.is-active", operations)
        self.assertIn("[aria-current=page]", operations)
        self.assertNotIn("is-active", home)

    def test_operations_center_navigation_uses_existing_authentication_contract(self):
        anonymous = type(
            "Anonymous",
            (),
            {"is_authenticated": False, "is_staff": False},
        )()
        authenticated_menu = self.render_menu(
            "components/menu_operations.html", self.user
        )
        anonymous_menu = self.render_menu(
            "components/menu_operations.html", anonymous
        )
        center_url = reverse("ops:operations-center")
        self.assertIn(f'href="{center_url}"', authenticated_menu)
        self.assertNotIn(f'href="{center_url}"', anonymous_menu)

        self.assertEqual(self.client.get(center_url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(center_url).status_code, 200)
