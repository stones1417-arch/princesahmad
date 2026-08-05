from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.ops.models import (
    DoorShift,
    Incident,
)


class IncidentTests(TestCase):
    """
    اختبارات البلاغات التشغيلية.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية البلاغات",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
        )

        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=15,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def test_incident_generates_number(self):
        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ ازدحام",
            incident_type=(
                Incident
                .IncidentType
                .CROWDING
            ),
        )

        self.assertTrue(
            incident.incident_number.startswith(
                "INC-"
            )
        )

    def test_incident_numbers_are_sequential(self):
        first = Incident.objects.create(
            shift_plan=self.shift,
            description="البلاغ الأول",
        )

        second = Incident.objects.create(
            shift_plan=self.shift,
            description="البلاغ الثاني",
        )

        first_number = int(
            first.incident_number.split("-")[-1]
        )

        second_number = int(
            second.incident_number.split("-")[-1]
        )

        self.assertEqual(
            second_number,
            first_number + 1,
        )

    def test_description_is_required(self):
        incident = Incident(
            shift_plan=self.shift,
            description="   ",
        )

        with self.assertRaises(
            ValidationError
        ):
            incident.full_clean()

    def test_closed_incident_requires_closing_notes(self):
        incident = Incident(
            shift_plan=self.shift,
            description="بلاغ مكتمل",
            status=Incident.Status.CLOSED,
            closing_notes="",
        )

        with self.assertRaises(
            ValidationError
        ):
            incident.full_clean()

    def test_open_incident_property(self):
        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ مفتوح",
            status=Incident.Status.NEW,
        )

        self.assertTrue(
            incident.is_open
        )

    def test_resolved_incident_is_not_open(self):
        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ محلول",
            status=Incident.Status.RESOLVED,
        )

        self.assertFalse(
            incident.is_open
        )

    def test_closed_incident_sets_closed_at(self):
        incident = Incident(
            shift_plan=self.shift,
            description="بلاغ مغلق",
            status=Incident.Status.CLOSED,
            closing_notes="تمت معالجة البلاغ",
        )

        incident.full_clean()
        incident.save()
        incident.refresh_from_db()

        self.assertIsNotNone(
            incident.closed_at
        )

    def test_reopening_incident_clears_closed_at(self):
        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ سيعاد فتحه",
            status=Incident.Status.CLOSED,
            closing_notes="تم الإغلاق",
        )

        incident.status = Incident.Status.IN_PROGRESS
        incident.save()
        incident.refresh_from_db()

        self.assertIsNone(
            incident.closed_at
        )

    def test_door_shift_sets_shift_plan_automatically(self):
        incident = Incident.objects.create(
            door_shift=self.door_shift,
            description="بلاغ مرتبط بالباب",
        )

        self.assertEqual(
            incident.shift_plan,
            self.shift,
        )

    def test_critical_incident_can_be_created(self):
        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ أمني حرج",
            incident_type=(
                Incident
                .IncidentType
                .SECURITY
            ),
            priority=Incident.Priority.CRITICAL,
        )

        self.assertEqual(
            incident.priority,
            Incident.Priority.CRITICAL,
        )