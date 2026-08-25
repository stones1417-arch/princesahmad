from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_user,
    create_zone,
)
from apps.ops.models import DoorShift, Incident, IncidentRoutingEvent, MaintenanceRequest
from apps.roles.services.role_manager import assign_role_to_user
from apps.scheduling.models import ShiftAssignment
from apps.scheduling.operational_leadership_service import assign_shift_operational_leader


class IncidentRoutingLifecycleE2ETests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")
        cls.shift = create_shift_plan(is_active=True, is_finished=False)
        cls.zone = create_zone(name="Incident routing E2E")
        cls.door = create_door(
            door_number="1", zone=cls.zone, operational_section="male"
        )
        cls.door_shift = DoorShift.objects.create(
            shift_plan=cls.shift,
            door_number="1",
            section="male",
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )
        cls.supervisor = cls._role_user(
            "routing-supervisor", "shift_supervisor", "male", "RT-SUP",
            ShiftAssignment.OperationalRole.SHIFT_HEAD,
        )
        cls.incident_supervisor = cls._role_user(
            "routing-incident", "incident_supervisor", "male", "RT-INC",
            ShiftAssignment.OperationalRole.SUPERVISOR,
        )
        cls.operations_supervisor = cls._role_user(
            "routing-operations", "operations_supervisor", "male", "RT-OPS",
            ShiftAssignment.OperationalRole.SUPERVISOR,
        )
        cls.maintenance_supervisor = cls._role_user(
            "routing-maintenance-specialist", "maintenance_shift_supervisor", "male", "RT-MSP",
            ShiftAssignment.OperationalRole.SUPERVISOR,
        )
        for responsibility, user in (
            ("incident_supervisor", cls.incident_supervisor),
            ("operations_supervisor", cls.operations_supervisor),
            ("maintenance_shift_supervisor", cls.maintenance_supervisor),
        ):
            assign_shift_operational_leader(
                shift_plan=cls.shift,
                responsibility=responsibility,
                employee=user.employee,
                actor=cls.supervisor,
            )
        cls.deputy = cls._role_user(
            "routing-deputy", "shift_deputy", "male", "RT-DEP",
            ShiftAssignment.OperationalRole.SHIFT_DEPUTY,
        )
        cls.head = cls._role_user(
            "routing-head", "doors_department_head", "male", "RT-HEAD"
        )
        cls.general_manager = cls._role_user(
            "routing-gm", "general_manager", "all", "RT-GM"
        )
        cls.maintenance_manager = cls._role_user(
            "routing-maintenance", "maintenance_manager", "all", "RT-MAINT"
        )
        cls.ordinary = create_user(username="routing-ordinary")
        create_employee(
            user=cls.ordinary,
            employee_number="RT-ORD",
            operational_section="male",
        )

    @classmethod
    def _role_user(cls, username, role_code, section, employee_number, assignment_role=None):
        user = create_user(username=username)
        employee = create_employee(
            user=user,
            employee_number=employee_number,
            operational_section="male" if section == "all" else section,
        )
        assign_role_to_user(user=user, role_code=role_code)
        if assignment_role:
            ShiftAssignment.objects.create(
                shift_plan=cls.shift,
                employee=employee,
                role=assignment_role,
                is_confirmed=True,
            )
        return user

    def _create_incident(self):
        self.client.force_login(self.incident_supervisor)
        response = self.client.post(reverse("ops:incident-create"), {
            "door_id": self.door.pk,
            "description": "تعطل وحدة التحكم الإلكترونية بالباب",
            "incident_type": Incident.IncidentType.DOOR_FAULT,
            "priority": Incident.Priority.CRITICAL,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        return Incident.objects.get(pk=response.json()["incident"]["id"])

    def test_complete_incident_routing_lifecycle_through_runtime_endpoints(self):
        incident = self._create_incident()
        self.assertEqual(incident.assigned_to, self.incident_supervisor)
        self.assertNotEqual(incident.assigned_to, self.supervisor)
        self.assertContains(
            self.client.get(reverse("scheduling:current")), incident.incident_number
        )
        self.assertEqual(
            list(incident.routing_events.values_list("event_type", flat=True)),
            [IncidentRoutingEvent.EventType.CREATED, IncidentRoutingEvent.EventType.ASSIGNED],
        )

        self.client.force_login(self.deputy)
        self.assertContains(self.client.get(reverse("ops:incidents")), incident.incident_number)
        self.assertContains(
            self.client.get(reverse("scheduling:current")), incident.incident_number
        )
        incident.refresh_from_db()
        self.assertEqual(incident.assigned_to, self.incident_supervisor)

        self.client.force_login(self.head)
        self.assertContains(self.client.get(reverse("ops:incidents")), incident.incident_number)

        self.client.force_login(self.ordinary)
        protected_posts = [
            (reverse("ops:incident-shift-update", args=[incident.pk]), {"note": "forged"}),
            (reverse("ops:incident-escalate", args=[incident.pk]), {"note": "forged"}),
            (reverse("ops:incident-convert-maintenance", args=[incident.pk]), {}),
            (reverse("ops:incident-update", args=[incident.pk]), {"status": "closed", "closing_notes": "forged"}),
        ]
        for url, payload in protected_posts:
            self.assertEqual(self.client.post(url, payload).status_code, 403)

        self.client.force_login(self.incident_supervisor)
        update_url = reverse("ops:incident-update", args=[incident.pk])
        self.assertEqual(self.client.post(update_url, {"status": "in_progress"}).status_code, 200)
        shift_update = self.client.post(
            reverse("ops:incident-shift-update", args=[incident.pk]),
            {"note": "تمت معاينة الباب ويجري التعامل مع الخلل."},
        )
        self.assertEqual(shift_update.status_code, 200)
        self.assertContains(
            self.client.get(reverse("ops:incidents")),
            "تمت معاينة الباب ويجري التعامل مع الخلل.",
        )
        escalation_url = reverse("ops:incident-escalate", args=[incident.pk])
        self.assertEqual(self.client.post(escalation_url, {"note": "يتطلب إشراف القسم"}).status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.escalation_level, Incident.EscalationLevel.DEPARTMENT_HEAD)
        self.assertEqual(incident.assigned_to, self.incident_supervisor)

        self.client.force_login(self.head)
        self.assertEqual(self.client.post(escalation_url, {"note": "بلاغ حرج"}).status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.escalation_level, Incident.EscalationLevel.GENERAL_MANAGER)
        self.assertEqual(incident.assigned_to, self.incident_supervisor)
        self.client.force_login(self.general_manager)
        self.assertContains(self.client.get(reverse("ops:incidents")), incident.incident_number)

        self.client.force_login(self.incident_supervisor)
        start = timezone.now() + timedelta(hours=1)
        end = start + timedelta(hours=2)
        conversion_url = reverse("ops:incident-convert-maintenance", args=[incident.pk])
        conversion = self.client.post(conversion_url, {
            "planned_start_at": start.isoformat(),
            "planned_end_at": end.isoformat(),
        })
        self.assertEqual(conversion.status_code, 200)
        maintenance = MaintenanceRequest.objects.get(source_incident=incident)
        self.assertEqual(maintenance.door_shift, self.door_shift)
        self.assertEqual(maintenance.description, incident.description)
        self.assertEqual(maintenance.priority, MaintenanceRequest.Priority.URGENT)
        self.assertEqual(maintenance.section, incident.section)
        self.assertEqual(self.client.post(conversion_url, {
            "planned_start_at": start.isoformat(), "planned_end_at": end.isoformat(),
        }).status_code, 400)
        self.assertEqual(MaintenanceRequest.objects.filter(source_incident=incident).count(), 1)
        converted_page = self.client.get(reverse("ops:incidents"))
        self.assertNotContains(
            converted_page,
            f'data-action-url="{conversion_url}"',
        )
        self.assertContains(converted_page, "عرض طلب الصيانة")

        maintenance_url = reverse("ops:maintenance-update-status-ajax", args=[maintenance.pk])
        self.client.force_login(self.operations_supervisor)
        self.assertEqual(self.client.post(maintenance_url, {"status": "approved"}).status_code, 200)
        self.client.force_login(self.maintenance_supervisor)
        self.assertEqual(self.client.post(maintenance_url, {"status": "in_progress"}).status_code, 200)
        self.assertEqual(self.client.post(maintenance_url, {
            "status": "done", "closing_notes": "تم الإصلاح والاختبار",
        }).status_code, 200)
        maintenance.refresh_from_db()
        incident.refresh_from_db()
        self.assertIsNotNone(maintenance.started_at)
        self.assertIsNotNone(maintenance.fixed_at)
        self.assertIsNone(incident.closed_at)

        self.client.force_login(self.incident_supervisor)
        completion_page = self.client.get(reverse("ops:incidents"))
        self.assertContains(completion_page, "اكتملت الصيانة — بانتظار تأكيد مشرف الوردية")
        self.assertContains(completion_page, "تأكيد معالجة البلاغ وإغلاقه")

        self.assertEqual(self.client.post(update_url, {
            "status": "closed", "closing_notes": "تم التحقق التشغيلي",
        }).status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.status, Incident.Status.CLOSED)
        self.assertEqual(incident.closed_by, self.incident_supervisor)
        self.assertIsNotNone(incident.closed_at)
        major_events = list(incident.routing_events.values_list("event_type", flat=True))
        expected = [
            "created", "assigned", "processing_started", "escalated", "escalated",
            "converted_to_maintenance", "maintenance_approved", "maintenance_started",
            "maintenance_completed", "closed",
        ]
        positions = []
        start_at = 0
        for event in expected:
            position = major_events.index(event, start_at)
            positions.append(position)
            start_at = position + 1
        self.assertEqual(positions, sorted(positions))

    def test_no_active_shift_creates_visible_unassigned_incident(self):
        self.shift.is_active = False
        self.shift.save(update_fields=["is_active", "updated_at"])
        incident = self._create_incident()
        self.assertIsNone(incident.assigned_to)
        self.client.force_login(self.head)
        self.assertContains(self.client.get(reverse("ops:incidents")), incident.incident_number)

    def test_permission_aware_dialogs_and_routing_presentation(self):
        incident = self._create_incident()
        self.client.force_login(self.incident_supervisor)
        content = self.client.get(reverse("ops:incidents")).content.decode()
        self.assertIn("incidentEscalationDialog", content)
        self.assertIn("incidentConversionDialog", content)
        self.assertIn("incidentCloseDialog", content)
        self.assertIn("مسار البلاغ", content)
        self.assertIn("المسؤول التنفيذي", content)
        self.assertNotIn('name="escalation_level"', content)
        self.assertNotIn("window.prompt", content)
        self.assertNotIn("window.confirm", content)

        self.client.force_login(self.general_manager)
        unauthorized_content = self.client.get(reverse("ops:incidents")).content.decode()
        self.assertNotIn('<button type="button" class="incident-escalate-button"', unauthorized_content)
        self.assertNotIn('<button type="button" class="incident-convert-button"', unauthorized_content)
        self.assertNotIn('<button type="button" class="incident-close-button"', unauthorized_content)

        self.client.force_login(self.ordinary)
        self.assertEqual(self.client.get(reverse("ops:incidents")).status_code, 403)
