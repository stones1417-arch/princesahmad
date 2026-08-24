from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import create_door, create_shift_plan, create_user
from apps.ops.models import DoorShift


class ExecutiveMaintenanceDialogTests(TestCase):
    def setUp(self):
        self.shift = create_shift_plan(is_active=True, is_finished=False)
        self.doors = [create_door(door_number="1"), create_door(door_number="6B")]
        for door in self.doors:
            DoorShift.objects.create(
                shift_plan=self.shift,
                door_number=door.door_number,
                state=DoorShift.DoorState.OPEN,
                is_active=True,
            )

    def test_authorized_user_gets_one_dialog_and_action_for_every_active_door(self):
        user = create_user(is_superuser=True)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(html.count('id="maintenanceDialog"'), 1)
        self.assertEqual(html.count('class="dashboard-door-maintenance"'), len(self.doors))
        self.assertContains(response, 'data-door-number="6B"')
        self.assertContains(response, 'id="maintenanceTechnicianPhone"')
        self.assertContains(response, 'id="maintenancePlannedStart"')
        self.assertContains(response, 'id="maintenancePlannedEnd"')
        self.assertContains(response, 'id="maintenanceExpectedDuration"')

    def test_unauthorized_user_does_not_see_maintenance_actions(self):
        user = create_user()
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="dashboard-door-maintenance"')

    def test_engineering_center_has_no_create_maintenance_trigger(self):
        user = create_user(is_superuser=True)
        self.client.force_login(user)
        response = self.client.get(reverse("ops:doors"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-maintenance-action")
        self.assertNotContains(response, "engineeringMaintenanceDialog")
