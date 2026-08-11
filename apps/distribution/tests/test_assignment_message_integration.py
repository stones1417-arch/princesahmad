from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.communications.models import CommunicationLog
from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.distribution.models import DoorAssignment
from apps.distribution.services import DistributionService


class AssignmentMessageIntegrationTests(TestCase):
    def _assignment_inputs(self):
        shift_type = create_shift_type(name="وردية تكامل رسائل", start_time=time(8), end_time=time(16))
        shift_plan = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8),
            end_time=time(16),
            is_active=True,
        )
        return shift_plan, create_employee(operational_section="male"), create_door(door_number=32)

    def test_assignment_creation_creates_pending_local_sms_and_whatsapp_logs(self):
        shift_plan, employee, door = self._assignment_inputs()

        assignment = DistributionService.create_assignment(
            shift_plan=shift_plan,
            employee=employee,
            door=door,
            role=DoorAssignment.Role.MONITOR,
        )

        logs = CommunicationLog.objects.filter(related_assignment=assignment)
        self.assertEqual(logs.count(), 2)
        self.assertTrue(all(log.status == CommunicationLog.Status.PENDING for log in logs))

    def test_assignment_is_saved_when_message_dispatcher_fails(self):
        shift_plan, employee, door = self._assignment_inputs()

        with patch("apps.distribution.services.dispatch_assignment_message", side_effect=RuntimeError("dispatch failed")):
            assignment = DistributionService.create_assignment(
                shift_plan=shift_plan,
                employee=employee,
                door=door,
                role=DoorAssignment.Role.MONITOR,
            )

        self.assertTrue(DoorAssignment.objects.filter(pk=assignment.pk).exists())

    def test_staff_without_assignment_permission_is_denied(self):
        user = create_user(is_staff=True)
        self.client.force_login(user)

        response = self.client.post("/distribution/create/", {"role": DoorAssignment.Role.MONITOR})

        self.assertEqual(response.status_code, 403)