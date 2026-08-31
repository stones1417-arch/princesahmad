from datetime import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.dashboard.views import build_dashboard_context
from apps.locations.models import Door, Zone
from apps.ops.command_center_service import CommandCenterService
from apps.ops.engineering_center_service import EngineeringCenterService
from apps.ops.models import DoorCurrentState, DoorShift
from apps.ops.operations_center_service import OperationsCenterService
from apps.scheduling.models import ShiftPlan, ShiftType


class DoorStateConsistencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="door_state_consistency_admin",
            password="test-only-password",
            email="door-state@example.invalid",
        )
        shift_type = ShiftType.objects.create(
            name="Canonical state test shift",
            start_time=time(6),
            end_time=time(14),
            ordering=1,
        )
        cls.shift = ShiftPlan.objects.create(
            shift_type=shift_type,
            date=timezone.localdate(),
            start_time=time(6),
            end_time=time(14),
            is_active=True,
        )
        zone = Zone.objects.create(name="Canonical state test zone")
        numbers = [str(number) for number in range(1, 6)]
        numbers += ["6B", "6A"]
        numbers += [str(number) for number in range(7, 42)]
        states = list(DoorShift.DoorState.values)
        for index, number in enumerate(numbers, start=1):
            door = Door.objects.create(
                door_number=number,
                name=f"Door {number}",
                zone=zone,
                operational_section=Door.OperationalSection.MALE,
                sort_order=index,
            )
            canonical_state = states[(index - 1) % len(states)]
            door_shift = DoorShift.objects.create(
                door_number=number,
                shift_plan=cls.shift,
                state=canonical_state,
                is_active=True,
            )
            DoorCurrentState.objects.create(
                door=door,
                state=(
                    DoorShift.DoorState.CLOSED
                    if canonical_state != DoorShift.DoorState.CLOSED
                    else DoorShift.DoorState.OPEN
                ),
                update_source=DoorCurrentState.UpdateSource.SYSTEM,
                current_shift=door_shift,
            )

    @staticmethod
    def _operation_states(snapshot):
        return {
            item["door"].door_number: item["state"]
            for group in snapshot["groups"]
            for item in group["doors"]
        }

    def test_all_42_centers_use_the_same_canonical_state(self):
        operations = OperationsCenterService.build()
        command = CommandCenterService.build()
        engineering = EngineeringCenterService.build(active_shift=self.shift)
        request = RequestFactory().get("/")
        request.user = self.user
        executive = build_dashboard_context(request)

        canonical = self._operation_states(operations)
        command_states = self._operation_states(command)
        engineering_states = {
            row.door.door_number: row.status for row in engineering["doors"]
        }
        executive_states = {
            row["door_obj"].door_number: row["state"]
            for rows in executive["grouped_doors"].values()
            for row in rows
        }

        self.assertEqual(len(canonical), 42)
        self.assertEqual(command_states, canonical)
        self.assertEqual(engineering_states, canonical)
        self.assertEqual(executive_states, canonical)
        self.assertIn("6A", canonical)
        self.assertIn("6B", canonical)
        self.assertNotIn("6", canonical)
        self.assertEqual(
            set(canonical.values()),
            set(DoorShift.DoorState.values),
        )

    def test_stale_current_rows_are_resolved_in_bulk_without_n_plus_one(self):
        with CaptureQueriesContext(connection) as queries:
            snapshot = EngineeringCenterService.build(active_shift=self.shift)
        self.assertEqual(len(snapshot["doors"]), 42)
        self.assertLessEqual(len(queries), 12)

    def test_executive_ajax_response_uses_canonical_state(self):
        door_shift = DoorShift.objects.get(
            shift_plan=self.shift,
            door_number="5",
        )
        expected = OperationsCenterService._resolve_state(
            door_shift=door_shift,
            current_state=DoorCurrentState.objects.get(door__door_number="5"),
        )
        self.client.force_login(self.user)
        with patch(
            "apps.ops.views.DoorService.update_state",
            return_value=(door_shift, False),
        ):
            response = self.client.post(
                f"/ops/doors/{door_shift.pk}/update/ajax/",
                {"state": DoorShift.DoorState.OPEN, "reason": "test"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["door"]["state"], expected)
