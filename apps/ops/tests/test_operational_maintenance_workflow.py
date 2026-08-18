from __future__ import annotations

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import create_door, create_shift_plan
from apps.locations.door_directions import OFFICIAL_DOOR_CODES
from apps.ops.command_center_service import CommandCenterService
from apps.ops.maintenance_service import MaintenanceService
from apps.ops.models import DoorCurrentState, DoorShift, MaintenanceRequest
from apps.roles.models import Role, UserRole


class OperationalMaintenanceWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="door-operations-admin",
        )
        self.client.force_login(self.user)
        self.shift = create_shift_plan(is_active=True, is_finished=False)
        self.catalog_door = create_door(door_number="6A")
        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number="6A",
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def test_real_create_url_is_visible_in_maintenance_center_and_is_canonical(self):
        create_url = reverse(
            "ops:maintenance-create-ajax",
            args=[self.door_shift.pk],
        )
        response = self.client.post(
            create_url,
            {
                "description": "Door motor requires inspection",
                "priority": MaintenanceRequest.Priority.HIGH,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["maintenance"]
        maintenance = MaintenanceRequest.objects.get(pk=payload["id"])
        self.door_shift.refresh_from_db()
        current_state = DoorCurrentState.objects.get(door=self.catalog_door)

        self.assertEqual(maintenance.created_by, self.user)
        self.assertEqual(maintenance.section, self.door_shift.section)
        self.assertEqual(maintenance.status, MaintenanceRequest.Status.NEW)
        self.assertEqual(self.door_shift.state, DoorShift.DoorState.MAINTENANCE)
        self.assertEqual(current_state.state, DoorShift.DoorState.MAINTENANCE)
        self.assertEqual(current_state.current_shift, self.door_shift)
        self.assertEqual(payload["state"], DoorShift.DoorState.MAINTENANCE)

        center = self.client.get(reverse("ops:maintenance-list"))
        self.assertEqual(center.status_code, 200)
        self.assertContains(center, maintenance.request_number)
        self.assertContains(center, "6A")
        self.assertContains(center, self.user.username)

        duplicate = self.client.post(
            create_url,
            {
                "description": "Duplicate request",
                "priority": MaintenanceRequest.Priority.MEDIUM,
            },
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(MaintenanceRequest.objects.count(), 1)

    def test_state_endpoint_maintenance_creates_request_and_returns_canonical_data(self):
        response = self.client.post(
            reverse("ops:door-update-ajax", args=[self.door_shift.pk]),
            {
                "state": DoorShift.DoorState.MAINTENANCE,
                "notes": "State transition maintenance request",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        maintenance = MaintenanceRequest.objects.get(
            pk=payload["maintenance_request_id"]
        )
        self.assertEqual(payload["door"]["state"], "maintenance")
        self.assertEqual(payload["maintenance_status"], maintenance.status)

        context = CommandCenterService.build()
        self.assertEqual(context["metrics"].open_doors, 0)
        self.assertEqual(context["metrics"].maintenance_doors, 1)
        self.assertEqual(context["metrics"].open_maintenance, 1)

    def test_finishing_maintenance_uses_official_open_state_contract(self):
        maintenance = MaintenanceService.create_request(
            request=None,
            door=self.door_shift,
            description="Finish workflow",
            priority=MaintenanceRequest.Priority.MEDIUM,
        )
        updated = MaintenanceService.update_status(
            request=None,
            user=self.user,
            maintenance=maintenance,
            new_status=MaintenanceRequest.Status.CLOSED,
            closing_notes="Repair completed",
        )
        self.door_shift.refresh_from_db()

        self.assertEqual(updated.status, MaintenanceRequest.Status.CLOSED)
        self.assertEqual(self.door_shift.state, DoorShift.DoorState.OPEN)
        self.assertFalse(updated.is_open_request)

    def test_authorized_buttons_render_with_real_urls_and_matching_selectors(self):
        response = self.client.get(reverse("ops:doors"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-door-state-action")
        self.assertContains(response, "data-maintenance-action")
        self.assertContains(
            response,
            reverse("ops:door-update-ajax", args=[self.door_shift.pk]),
        )
        self.assertContains(
            response,
            reverse("ops:maintenance-create-ajax", args=[self.door_shift.pk]),
        )
        self.assertNotContains(response, "disabled")
        self.assertContains(response, 'type="button"')


class CommandCenterDoorCatalogTests(TestCase):
    def setUp(self):
        for code in OFFICIAL_DOOR_CODES:
            create_door(door_number=code)

    def test_command_center_uses_exact_master_catalog_codes(self):
        payload = CommandCenterService.build_json()
        map_codes = [
            door["number"]
            for group in payload["groups"]
            for door in group["doors"]
        ]
        active_codes = set(OFFICIAL_DOOR_CODES)

        self.assertEqual(len(active_codes), 42)
        self.assertEqual(len(map_codes), 42)
        self.assertEqual(len(set(map_codes)), 42)
        self.assertEqual(set(map_codes) - active_codes, set())
        self.assertEqual(active_codes - set(map_codes), set())
        self.assertIn("6A", map_codes)
        self.assertIn("6B", map_codes)
        self.assertNotIn("6", map_codes)

    def test_javascript_map_positions_cover_the_official_catalog(self):
        source = Path("static/js/ops/command_center.js").read_text(
            encoding="utf-8"
        )
        group_source = source.split("const MAP_DOOR_CODES", 1)[0]
        configured_codes = re.findall(r'"(6A|6B|[1-9]|[1-3][0-9]|4[01])"', group_source)

        self.assertEqual(configured_codes, list(OFFICIAL_DOOR_CODES))
        self.assertNotIn('Number(\n                    point.dataset.doorNumber', source)
        self.assertIn("MAP_DOOR_CODES.includes(normalizedDoor.number)", source)


class OperationalMaintenanceSecurityTests(TestCase):
    def setUp(self):
        self.shift = create_shift_plan(is_active=True, is_finished=False)
        create_door(door_number="6A", operational_section="male")
        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number="6A",
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def _scoped_user(self, section: str):
        user = get_user_model().objects.create_user(username=f"{section}-operator")
        group = Group.objects.create(name=f"{section}-operator-group")
        group.permissions.add(
            *Permission.objects.filter(
                content_type__app_label="roles",
                codename__in=(
                    "view_doors",
                    "move_door_to_maintenance",
                    "create_maintenance_request",
                    "view_maintenance_requests",
                ),
            )
        )
        role = Role.objects.create(
            code=f"{section}-operator-role",
            name=f"{section} operator",
            group=group,
            operational_section=section,
        )
        UserRole.objects.create(user=user, role=role)
        return user

    def test_unauthenticated_and_unauthorized_requests_are_denied(self):
        urls = (
            reverse("ops:maintenance-create-ajax", args=[self.door_shift.pk]),
            reverse("ops:door-update-ajax", args=[self.door_shift.pk]),
        )
        for url in urls:
            unauthenticated = self.client.post(url, {"description": "Denied"})
            self.assertEqual(unauthenticated.status_code, 302)

        user = get_user_model().objects.create_user(username="no-door-permissions")
        self.client.force_login(user)
        for url in urls:
            unauthorized = self.client.post(url, {"description": "Denied"})
            self.assertEqual(unauthorized.status_code, 403)

    def test_female_scope_cannot_modify_male_door(self):
        self.client.force_login(self._scoped_user(Role.OperationalSection.FEMALE))
        response = self.client.post(
            reverse("ops:maintenance-create-ajax", args=[self.door_shift.pk]),
            {
                "description": "Cross-scope attempt",
                "priority": MaintenanceRequest.Priority.MEDIUM,
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(MaintenanceRequest.objects.count(), 0)

    def test_male_scope_cannot_modify_female_door(self):
        create_door(door_number="14", operational_section="female")
        female_door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number="14",
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )
        self.client.force_login(self._scoped_user(Role.OperationalSection.MALE))
        response = self.client.post(
            reverse("ops:door-update-ajax", args=[female_door_shift.pk]),
            {
                "state": DoorShift.DoorState.MAINTENANCE,
                "notes": "Cross-scope attempt",
            },
        )
        self.assertEqual(response.status_code, 404)
        female_door_shift.refresh_from_db()
        self.assertEqual(female_door_shift.state, DoorShift.DoorState.OPEN)
