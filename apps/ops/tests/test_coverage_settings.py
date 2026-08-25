from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.tests.factories import create_door
from apps.dashboard.models import SystemActivityLog
from apps.locations.door_directions import OFFICIAL_DOOR_CODES
from apps.locations.models import Door
from apps.ops.models import DoorOperationalProfile
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.role_manager import assign_role_to_user, create_or_update_role


class DoorCoverageSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for code in OFFICIAL_DOOR_CODES:
            create_door(door_number=code)
        call_command("setup_roles")
        cls.admin = get_user_model().objects.create_superuser(username="coverage-admin")
        cls.denied = get_user_model().objects.create_user(username="coverage-denied")
        create_or_update_role(
            code="coverage_reader", name="Coverage reader",
            permission_codes=[PlatformPermissions.VIEW_SYSTEM_SETTINGS],
            operational_section="all",
        )
        cls.reader = get_user_model().objects.create_user(username="coverage-reader")
        assign_role_to_user(user=cls.reader, role_code="coverage_reader")
        cls.url = reverse("ops:door-coverage-settings")

    def test_page_security_and_editor_contract(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.denied)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.reader)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "إدارة التغطية التشغيلية للأبواب")
        self.assertNotContains(response, 'id="saveCoverageSettings"')
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)

    def test_page_lists_exact_official_catalog_in_order_without_n_plus_one(self):
        self.client.force_login(self.admin)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)
        rows = response.context["coverage_rows"]
        codes = [row.door.door_number for row in rows]
        self.assertEqual(len(codes), 42)
        self.assertEqual(codes[:8], ["1", "2", "3", "4", "5", "6B", "6A", "7"])
        self.assertNotIn("6", codes)
        self.assertLessEqual(len(queries), 35)

    def test_no_active_shift_means_zero_current_staff(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertTrue(all(row.employee_count == 0 for row in response.context["coverage_rows"]))

    def test_create_update_clear_and_no_blank_profile(self):
        door = Door.objects.get(door_number="6B")
        blank_door = Door.objects.get(door_number="6A")
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {
            f"target_{door.pk}": "3", f"target_{blank_door.pk}": "",
        })
        self.assertRedirects(response, f"{self.url}?updated=1")
        profile = DoorOperationalProfile.objects.get(door=door)
        self.assertEqual(profile.target_staff_count, 3)
        self.assertFalse(DoorOperationalProfile.objects.filter(door=blank_door).exists())
        self.client.post(self.url, {f"target_{door.pk}": "7"})
        profile.refresh_from_db()
        self.assertEqual(profile.target_staff_count, 7)
        center = self.client.get(reverse("ops:doors"))
        metric = next(row for row in center.context["engineering_doors"] if row.door.pk == door.pk)
        self.assertEqual(metric.target_staff_count, 7)
        self.client.post(self.url, {f"target_{door.pk}": ""})
        profile.refresh_from_db()
        self.assertIsNone(profile.target_staff_count)

    def test_validates_all_rows_before_writing(self):
        first = Door.objects.get(door_number="1")
        second = Door.objects.get(door_number="2")
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {
            f"target_{first.pk}": "4", f"target_{second.pk}": "1000",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "أدخل عددًا صحيحًا من 1 إلى 999", status_code=400)
        self.assertFalse(DoorOperationalProfile.objects.exists())
        for invalid in ("0", "-1"):
            response = self.client.post(self.url, {f"target_{first.pk}": invalid})
            self.assertEqual(response.status_code, 400)
            self.assertFalse(DoorOperationalProfile.objects.exists())

    def test_forged_nonexistent_and_inactive_doors_are_blocked(self):
        inactive = Door.objects.get(door_number="3")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url, {f"target_{inactive.pk}": "2"}).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"target_999999": "2"}).status_code, 403)
        self.assertFalse(DoorOperationalProfile.objects.exists())

    def test_audit_logs_changed_rows_only(self):
        first = Door.objects.get(door_number="1")
        second = Door.objects.get(door_number="2")
        DoorOperationalProfile.objects.create(door=first, target_staff_count=2)
        self.client.force_login(self.admin)
        before = SystemActivityLog.objects.count()
        self.client.post(self.url, {f"target_{first.pk}": "2", f"target_{second.pk}": "3"})
        logs = SystemActivityLog.objects.order_by("pk")[before:]
        self.assertEqual(len(logs), 1)
        self.assertIn("للـباب 2".replace("ـ", ""), logs[0].description)

    def test_one_to_one_prevents_duplicate_profiles(self):
        door = Door.objects.get(door_number="4")
        DoorOperationalProfile.objects.create(door=door, target_staff_count=2)
        with self.assertRaises(IntegrityError):
            DoorOperationalProfile.objects.create(door=door, target_staff_count=3)

    def test_ui_filters_bulk_dirty_preview_and_csrf_contract(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        for element_id in ("coverageSearch", "coverageStatus", "configurationFilter", "coverageLevel", "bulkTarget", "dirtyCount", "saveCoverageSettings"):
            self.assertContains(response, f'id="{element_id}"')
        script_path = finders.find("js/ops/coverage_settings.js")
        self.assertIsNotNone(script_path)
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn("Math.round", script)
        self.assertIn("updateDirty", script)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        door = Door.objects.get(door_number="5")
        self.assertEqual(csrf_client.post(self.url, {f"target_{door.pk}": "2"}).status_code, 403)

    def test_initial_plan_is_client_only_complete_and_catalog_safe(self):
        self.client.force_login(self.admin)
        before = DoorOperationalProfile.objects.count()
        response = self.client.get(self.url)
        self.assertEqual(DoorOperationalProfile.objects.count(), before)
        self.assertContains(response, 'id="openCoveragePreset"')
        self.assertContains(response, 'id="coveragePresetDialog"')
        self.assertContains(response, 'aria-labelledby="coveragePresetTitle"')
        self.assertContains(response, "لن يتم حفظ أي تغييرات")
        script_path = finders.find("js/ops/coverage_settings.js")
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        plan_fragment = script.split("Object.freeze({", 1)[1].split("});", 1)[0]
        self.assertEqual(plan_fragment.count(":"), 42)
        self.assertIn('"1":3', plan_fragment)
        self.assertIn('"6B":4', plan_fragment)
        self.assertIn('"6A":4', plan_fragment)
        self.assertNotIn('"6":', plan_fragment)
        self.assertIn("rows.length === planNumbers.length", script)
        self.assertIn("row.dataset.number", script)
        self.assertIn("updateDirty(); filterRows();", script)
        self.assertNotIn("fetch(", script)

    def test_engineering_center_has_single_authorized_entry_and_no_inline_form(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:doors"))
        self.assertContains(response, self.url, count=1)
        self.assertNotContains(response, "engineering-staff-targets")
        self.client.force_login(self.denied)
        response = self.client.get(reverse("ops:doors"))
        self.assertEqual(response.status_code, 403)
