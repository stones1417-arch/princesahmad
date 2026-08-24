from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.role_manager import assign_role_to_user, create_or_update_role


class WorkforceNavigationContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.distribution_user = get_user_model().objects.create_user(username="nav-distribution")
        create_or_update_role(
            code="nav_distribution_viewer",
            name="Navigation distribution viewer",
            permission_codes=[PlatformPermissions.VIEW_DISTRIBUTION],
            operational_section="all",
        )
        assign_role_to_user(user=cls.distribution_user, role_code="nav_distribution_viewer")

        cls.breaks_user = get_user_model().objects.create_user(username="nav-breaks", is_staff=True)
        cls.breaks_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="breaks",
                codename="can_view_break_dashboard",
            )
        )
        cls.unauthorized = get_user_model().objects.create_user(username="nav-unauthorized")

    def render_menus(self, permission_codes, namespace="core"):
        request = RequestFactory().get("/")
        request.user = self.unauthorized
        request.resolver_match = SimpleNamespace(namespace=namespace)
        context = {"request": request, "platform_permission_codes": set(permission_codes)}
        return (
            render_to_string("components/menu_operations.html", context, request=request),
            render_to_string("components/menu_hr.html", context, request=request),
        )

    def test_links_move_to_employees_menu_without_duplicates(self):
        operations, employees = self.render_menus(
            {"roles.view_distribution", "breaks.can_view_break_dashboard"}
        )
        distribution_url = reverse("distribution:dashboard")
        breaks_url = reverse("breaks:list")
        self.assertNotIn(f'href="{distribution_url}"', operations)
        self.assertNotIn(f'href="{breaks_url}"', operations)
        self.assertEqual(employees.count(f'href="{distribution_url}"'), 1)
        self.assertEqual(employees.count(f'href="{breaks_url}"'), 1)
        self.assertEqual(employees.count(">إدارة التوزيع<"), 1)
        self.assertEqual(employees.count(">إدارة الراحات<"), 1)
        self.assertIn("توزيع الموظفين على الأبواب والمواقع", employees)
        self.assertIn("تنظيم الاستراحات والتناوب والتغطية", employees)

    def test_menu_visibility_reuses_existing_permission_codes(self):
        _, distribution_menu = self.render_menus({"roles.view_distribution"})
        self.assertIn(reverse("distribution:dashboard"), distribution_menu)
        self.assertNotIn(reverse("breaks:list"), distribution_menu)

        _, breaks_menu = self.render_menus({"breaks.can_view_break_dashboard"})
        self.assertIn(reverse("breaks:list"), breaks_menu)
        self.assertNotIn(reverse("distribution:dashboard"), breaks_menu)

        _, unauthorized_menu = self.render_menus(set())
        self.assertNotIn(reverse("distribution:dashboard"), unauthorized_menu)
        self.assertNotIn(reverse("breaks:list"), unauthorized_menu)

    def test_employees_menu_is_active_for_distribution_and_breaks(self):
        _, distribution_menu = self.render_menus({"roles.view_distribution"}, "distribution")
        self.assertIn("hr-dropdown is-active", distribution_menu)
        self.assertIn('aria-current="page"', distribution_menu)

        _, breaks_menu = self.render_menus({"breaks.can_view_break_dashboard"}, "breaks")
        self.assertIn("hr-dropdown is-active", breaks_menu)
        self.assertIn('aria-current="page"', breaks_menu)

    def test_employees_menu_is_viewport_safe_without_text_truncation(self):
        _, employees = self.render_menus(
            {"roles.view_distribution", "breaks.can_view_break_dashboard"}
        )
        for item in (
            "مركز القوى العاملة",
            "ملفات الموظفين",
            "إدارة التوزيع",
            "إدارة الراحات",
            "تسكين الوردية",
            "الوردية الحالية",
            "إدارة الورديات",
        ):
            self.assertIn(item, employees)
        for contract in (
            "--hr-menu-available-height",
            "100dvh",
            "box-sizing:border-box",
            "overflow-y:auto",
            "overscroll-behavior:contain",
            "scrollbar-width:thin",
            "white-space:normal",
            "text-overflow:clip",
            "overflow-wrap:break-word",
            "position:sticky",
            ":focus-within",
            "safe-area-inset-bottom",
            "menu.scrollTop = 0",
        ):
            self.assertIn(contract, employees)
        self.assertNotIn("text-overflow:ellipsis", employees)

    def test_distribution_direct_url_security_contract_is_unchanged(self):
        url = reverse("distribution:dashboard")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.unauthorized)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.distribution_user)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_breaks_direct_url_security_contract_is_unchanged(self):
        url = reverse("breaks:list")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.unauthorized)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.breaks_user)
        self.assertEqual(self.client.get(url).status_code, 200)
