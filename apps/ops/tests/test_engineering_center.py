from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import create_door
from apps.locations.door_directions import OFFICIAL_DOOR_CODES
from apps.ops.engineering_center_service import EngineeringCenterService
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.role_manager import assign_role_to_user, create_or_update_role


OFFICIAL_MAP_URL = "https://maps.alharamain.gov.sa/navQ/default-kiosk/2?lang=ar"


class EngineeringCenterClosureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for code in OFFICIAL_DOOR_CODES:
            create_door(door_number=code)
        cls.admin = get_user_model().objects.create_superuser(username="engineering-admin")
        cls.unauthorized = get_user_model().objects.create_user(username="engineering-denied")
        call_command("setup_roles")
        create_or_update_role(code="engineering_viewer", name="Engineering viewer", permission_codes=[PlatformPermissions.VIEW_DOORS], operational_section="all")
        cls.viewer = get_user_model().objects.create_user(username="engineering-viewer")
        assign_role_to_user(user=cls.viewer, role_code="engineering_viewer")

    def test_canonical_catalog_and_bulk_snapshot(self):
        with self.assertNumQueries(4):
            snapshot = EngineeringCenterService.build(active_shift=None)
        codes = [item.door.door_number for item in snapshot["doors"]]
        self.assertEqual(len(codes), 42)
        self.assertEqual(codes[:8], ["1", "2", "3", "4", "5", "6B", "6A", "7"])
        self.assertNotIn("6", codes)
        for item in snapshot["doors"]:
            self.assertIsInstance(item.employee_count, int)
            self.assertIsInstance(item.open_incident_count, int)
            self.assertIsInstance(item.active_maintenance_count, int)

    def test_status_data_security_and_json_contract(self):
        url = reverse("ops:door-status-data")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.unauthorized)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        payload = response.json()
        self.assertEqual(len(payload["doors"]), 42)
        self.assertEqual([item["number"] for item in payload["doors"][:8]], ["1", "2", "3", "4", "5", "6B", "6A", "7"])
        self.assertNotIn("6", {item["number"] for item in payload["doors"]})
        for item in payload["doors"]:
            self.assertTrue({"employee_count", "open_incident_count", "active_maintenance_count"} <= item.keys())

    def test_page_has_only_overview_and_official_map_tabs(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, 'id="engineeringOverviewTab"')
        self.assertContains(response, 'id="engineeringMapTab"')
        self.assertContains(response, 'role="tab"', count=2)
        self.assertNotContains(response, "engineeringOperationalMapTab")
        self.assertNotContains(response, "engineering3DMapTab")
        self.assertNotContains(response, "data-operational-map")
        self.assertNotContains(response, "data-3d-viewport")

    def test_official_map_contract_and_scoped_csp(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, "مصدر خارجي رسمي")
        self.assertContains(response, f'data-src="{OFFICIAL_MAP_URL}"')
        self.assertContains(response, 'loading="lazy"')
        self.assertContains(response, 'title="الخريطة الرسمية للمسجد النبوي"')
        self.assertContains(response, "فتح الخريطة بملء الشاشة")
        self.assertContains(response, "فتح في نافذة جديدة")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("frame-src 'self' https://maps.alharamain.gov.sa", csp)
        self.assertNotIn("frame-src *", csp)

    def test_institutional_overview_structure_and_metrics(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, 'class="engineering-kpis"')
        self.assertContains(response, 'class="engineering-filters"')
        self.assertContains(response, 'class="engineering-card__metrics"', count=42)
        self.assertContains(response, 'data-metric="employees"', count=42)
        self.assertContains(response, 'data-metric="incidents"', count=42)
        self.assertContains(response, 'data-metric="maintenance"', count=42)
        self.assertContains(response, 'id="resultCount"')
        self.assertContains(response, 'id="refreshTime"')

    def test_filters_empty_state_and_auto_refresh_contract(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        for control_id in ("q", "status", "density", "incident", "maint", "sort", "resetFilters"):
            self.assertContains(response, f'id="{control_id}"')
        self.assertContains(response, "لا توجد أبواب مطابقة للفلاتر الحالية.")
        script_path = finders.find("js/ops/engineering_center.js")
        self.assertIsNotNone(script_path)
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn("45000", script)
        self.assertIn("engineering:center-refreshed", script)

    def test_superuser_quick_actions_and_detail_links_are_visible(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, 'class="engineering-card__details"', count=42)
        self.assertContains(response, "data-incident-action", count=42)
        self.assertContains(response, "إنشاء بلاغ تشغيلي", count=42)
        self.assertNotContains(response, "data-door-state-action")
        self.assertNotContains(response, "data-distribution-action")
        self.assertNotContains(response, 'role="menu"')
        self.assertNotContains(response, 'class="engineering-actions__toggle"')
        self.assertContains(response, "?door=6A&amp;create=1")
        self.assertContains(response, "?door=6B&amp;create=1")

    def test_view_only_user_cannot_see_privileged_quick_actions_or_links(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("ops:doors"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'role="menuitem" data-door-state-action')
        self.assertNotContains(response, 'role="menuitem" data-incident-action')
        self.assertNotContains(response, 'role="menuitem" data-distribution-action')
        self.assertNotContains(response, "data-incident-action")
        self.assertNotContains(response, f'href="{reverse("ops:maintenance-list")}?q=')

    def test_engineering_actions_are_scoped_and_incident_endpoint_stays_protected(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, 'class="engineering-card__status"', count=42)
        self.assertContains(response, 'data-metric="employees"', count=42)
        self.assertNotContains(response, "engineeringDoorStatusDialog")
        self.assertNotContains(response, f'href="{reverse("distribution:dashboard")}?door=')
        self.assertNotContains(response, reverse("ops:door-update-ajax", args=[1]))

        script_path = finders.find("js/ops/engineering_center.js")
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertNotIn("data-door-state-action", script)
        self.assertNotIn("data-distribution-action", script)

        self.client.logout()
        incident_url = reverse("ops:incident-create")
        self.assertEqual(self.client.post(incident_url).status_code, 302)
        self.client.force_login(self.unauthorized)
        self.assertEqual(self.client.post(incident_url).status_code, 403)

    def test_density_is_present_once_per_card_without_progress_bar(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, "لم تُحدد سعة تشغيلية لهذا الباب", count=42)
        self.assertNotContains(response, 'role="progressbar"')
