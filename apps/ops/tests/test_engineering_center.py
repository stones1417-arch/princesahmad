import json

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from django.core.management import call_command

from apps.core.tests.factories import create_door
from apps.locations.door_directions import OFFICIAL_DOOR_CODES
from apps.ops.engineering_center_service import EngineeringCenterService
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.role_manager import assign_role_to_user, create_or_update_role


class EngineeringCenterClosureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for code in OFFICIAL_DOOR_CODES:
            create_door(door_number=code)
        cls.admin = get_user_model().objects.create_superuser(username="engineering-admin")
        cls.unauthorized = get_user_model().objects.create_user(username="engineering-denied")
        call_command("setup_roles")
        create_or_update_role(
            code="engineering_viewer",
            name="Engineering viewer",
            permission_codes=[PlatformPermissions.VIEW_DOORS],
            operational_section="all",
        )
        cls.viewer = get_user_model().objects.create_user(username="engineering-viewer")
        assign_role_to_user(user=cls.viewer, role_code="engineering_viewer")

    def test_canonical_catalog_and_bulk_snapshot(self):
        with self.assertNumQueries(4):
            snapshot = EngineeringCenterService.build(active_shift=None)
        codes = [item.door.door_number for item in snapshot["doors"]]
        self.assertEqual(len(codes), 42)
        self.assertEqual(codes[:8], ["1", "2", "3", "4", "5", "6B", "6A", "7"])
        self.assertNotIn("6", codes)

    def test_status_data_security_and_json_contract(self):
        url = reverse("ops:door-status-data")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.unauthorized)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["doors"]), 42)
        self.assertEqual([item["number"] for item in payload["doors"][:8]], ["1", "2", "3", "4", "5", "6B", "6A", "7"])
        self.assertNotIn("6", {item["number"] for item in payload["doors"]})
        self.assertTrue(all(item["density_percent"] is None for item in payload["doors"]))
        self.assertTrue(all(item["density_label"] == "غير محددة" for item in payload["doors"]))

    def test_superuser_quick_actions_and_detail_links_are_visible(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, "data-incident-action")
        self.assertContains(response, "data-distribution-action")
        self.assertContains(response, reverse("ops:maintenance-list"))
        self.assertContains(response, reverse("distribution:dashboard"))

    def test_institutional_page_structure(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, "المركز الهندسي")
        self.assertContains(response, 'class="engineering-kpis"')
        self.assertContains(response, 'class="engineering-filters"')
        self.assertContains(response, 'class="engineering-card__metrics"', count=42)
        self.assertContains(response, 'id="resultCount"')
        self.assertContains(response, 'id="refreshTime"')

    def test_density_is_present_once_per_card_without_progress_bar(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, "لم تُحدد سعة تشغيلية لهذا الباب", count=42)
        self.assertNotContains(response, 'role="progressbar"')

    def test_primary_detail_action_and_actions_menu(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, 'class="engineering-card__details"', count=42)
        self.assertContains(response, 'class="engineering-actions__toggle"')
        self.assertContains(response, 'role="menu"')

    def test_empty_state_and_reset_controls_are_present(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, "لا توجد أبواب مطابقة للفلاتر الحالية.")
        self.assertContains(response, 'id="resetFilters"')
        self.assertContains(response, "data-reset-filters")

    def test_view_only_user_cannot_see_privileged_quick_actions_or_links(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("ops:doors"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "role=\"menuitem\" data-door-state-action")
        self.assertNotContains(response, "role=\"menuitem\" data-incident-action")
        self.assertNotContains(response, "role=\"menuitem\" data-maintenance-action")
        self.assertNotContains(response, "role=\"menuitem\" data-distribution-action")
        self.assertNotContains(response, f'href="{reverse("ops:maintenance-list")}?q=')
        self.assertNotContains(response, f'href="{reverse("distribution:dashboard")}?door=')

    def test_operational_map_layout_matches_master_catalog(self):
        layout_path = finders.find("data/ops/prophets_mosque_operational_map.json")
        self.assertIsNotNone(layout_path)
        with open(layout_path, encoding="utf-8") as layout_file:
            layout = json.load(layout_file)
        codes = [item["door"] for item in layout["doors"]]
        self.assertEqual(layout["accuracy"], "schematic")
        self.assertEqual(codes, list(OFFICIAL_DOOR_CODES))
        self.assertEqual(len(codes), 42)
        self.assertIn("6A", codes)
        self.assertIn("6B", codes)
        self.assertNotIn("6", codes)
        self.assertTrue(all(0 <= item["x"] <= 1 and 0 <= item["y"] <= 1 for item in layout["doors"]))
        self.assertTrue(all(set(item) == {"door", "x", "y", "zone"} for item in layout["doors"]))

    def test_operational_map_ui_contract_and_permissions(self):
        url = reverse("ops:doors")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.unauthorized)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        for contract in (
            'id="engineeringOperationalMapTab"',
            'data-operational-map',
            'data-map-summary',
            'engineering-map__legend',
            'data-map-filter="status"',
            'data-map-layer="employees"',
            'data-map-fullscreen',
            'data-map-zoom="in"',
            'data-map-drawer',
            'data-map-mode="model"',
            'data-map-mode="schematic"',
            'id="mosque-model"',
            'id="schematic-background"',
            'id="operational-door-layer"',
            'aria-label="القبة الخضراء — عنصر مرجعي بصري"',
        ):
            self.assertContains(response, contract)
        self.assertContains(response, "مجسم تشغيلي تقريبي")
        self.assertContains(response, "المسجد النبوي")
        self.assertContains(response, "ولا يمثل مخططًا مساحيًا أو معماريًا معتمدًا")
        self.assertContains(response, "فتح الخريطة الرسمية للموقع")
        content = response.content.decode()
        self.assertLess(content.index('id="mosque-model"'), content.index('id="operational-door-layer"'))

    def test_operational_map_live_update_preserves_client_state(self):
        script_path = finders.find("js/ops/engineering_operational_map.js")
        self.assertIsNotNone(script_path)
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn('engineering:center-refreshed', script)
        self.assertIn("updateMarker(item.number)", script)
        self.assertIn("if (selectedDoor) renderDrawer()", script)
        self.assertIn('markerLayer.classList.add("has-selection")', script)
        self.assertIn("data-map-visual='schematic'", script)
        self.assertNotIn("new WebSocket", script)
