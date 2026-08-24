from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import create_door, create_shift_plan, create_user, create_zone
from apps.ops.models import DoorShift, Incident, IncidentRoutingEvent


class ShiftCenterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(username="shift-center-admin", is_superuser=True)
        cls.shift = create_shift_plan(is_active=True, is_finished=False)
        zone = create_zone(name="Shift center")
        cls.door = create_door(door_number="40", zone=zone, operational_section="male")
        cls.door_shift = DoorShift.objects.create(
            shift_plan=cls.shift,
            door_number=cls.door.door_number,
            section="male",
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def incident(self, **overrides):
        data = {
            "shift_plan": self.shift,
            "door": self.door,
            "door_shift": self.door_shift,
            "section": "male",
            "description": "بلاغ مركز الوردية",
            "created_by": self.user,
        }
        data.update(overrides)
        return Incident.objects.create(**data)

    def test_route_is_preserved_and_navigation_uses_shift_center_label(self):
        response = self.client.get(reverse("scheduling:current"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/current_shift.html")
        self.assertContains(response, "مركز الوردية")
        self.assertNotContains(response, "<strong>الوردية الحالية</strong>")
        self.assertEqual(reverse("scheduling:current"), "/scheduling/")

    def test_state_tabs_are_scoped_and_display_expected_incidents(self):
        new = self.incident(description="بلاغ جديد")
        processing = self.incident(description="بلاغ معالجة", status=Incident.Status.IN_PROGRESS)
        escalated = self.incident(
            description="بلاغ مصعد",
            escalation_level=Incident.EscalationLevel.DEPARTMENT_HEAD,
        )
        completed = self.incident(description="بلاغ مكتمل", status=Incident.Status.CLOSED)
        cases = {
            "inbox": new,
            "processing": processing,
            "escalated": escalated,
            "completed": completed,
        }
        for tab, expected in cases.items():
            response = self.client.get(reverse("scheduling:current"), {"tab": tab})
            self.assertContains(response, expected.incident_number)
            self.assertIn(expected, list(response.context["incidents"]))

    def test_shift_update_endpoint_records_note_for_engineering_timeline(self):
        incident = self.incident()
        response = self.client.post(
            reverse("ops:incident-shift-update", args=[incident.pk]),
            {"note": "تمت المعاينة الميدانية."},
        )
        self.assertEqual(response.status_code, 200)
        event = IncidentRoutingEvent.objects.get(incident=incident)
        self.assertEqual(event.event_type, IncidentRoutingEvent.EventType.PROCESSING_STARTED)
        self.assertEqual(event.note, "تمت المعاينة الميدانية.")
        self.assertContains(self.client.get(reverse("ops:incidents")), event.note)

    def test_no_active_shift_is_safe_and_uses_unassigned_queue(self):
        self.shift.is_active = False
        self.shift.save(update_fields=["is_active", "updated_at"])
        unassigned = Incident.objects.create(
            section="male", description="بلاغ دون وردية", created_by=self.user
        )
        response = self.client.get(reverse("scheduling:current"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لا توجد وردية نشطة حاليًا")
        self.assertContains(response, unassigned.incident_number)
