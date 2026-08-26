from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.ops.models import Incident, IncidentSupervisoryAction, MaintenanceRequest
from apps.ops.supervisory_leadership_service import SupervisoryLeadershipService

from .test_incident_routing_lifecycle import IncidentRoutingLifecycleE2ETests


class SupervisoryIncidentLifecycleE2ETests(IncidentRoutingLifecycleE2ETests):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.department_deputy = cls._role_user(
            "supervisory-department-deputy", "doors_department_deputy",
            "male", "SV-DDEP",
        )
        cls.senior_administrator = cls._role_user(
            "supervisory-senior-admin", "senior_administrator",
            "male", "SV-SADM",
        )

    def test_supervisory_and_maintenance_lifecycles_remain_separate(self):
        incident = self._create_incident()
        owner = self.incident_supervisor
        update_url = reverse("ops:incident-update", args=[incident.pk])
        escalation_url = reverse("ops:incident-escalate", args=[incident.pk])

        self.assertEqual(incident.assigned_to, owner)
        self.assertEqual(
            self.client.post(update_url, {"status": "in_progress"}).status_code, 200
        )
        self.assertEqual(
            self.client.post(escalation_url, {"note": "يحتاج قرار القسم"}).status_code,
            200,
        )
        incident.refresh_from_db()
        self.assertEqual(incident.assigned_to, owner)
        self.assertEqual(incident.escalation_level, Incident.EscalationLevel.DEPARTMENT_HEAD)

        self.client.force_login(self.head)
        self.assertContains(
            self.client.get(reverse("ops:department-command-center")),
            "تحتاج قرارك",
        )
        request_action = SupervisoryLeadershipService.create_action(
            incident=incident, actor=self.head,
            action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            note="أرسل نتيجة المعاينة.",
        )
        response = SupervisoryLeadershipService.respond_to_update_request(
            request_action, owner, "تم تحديد الجزء المتعطل."
        )
        self.assertEqual(response.parent, request_action)
        SupervisoryLeadershipService.resolve_update_request(request_action, self.head)
        directive = SupervisoryLeadershipService.create_action(
            incident=incident, actor=self.head,
            action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE,
            note="وثّق الاختبار بعد الإصلاح.",
        )
        SupervisoryLeadershipService.acknowledge_directive(directive, owner)

        self.client.force_login(owner)
        start = timezone.now() + timedelta(hours=1)
        conversion = self.client.post(
            reverse("ops:incident-convert-maintenance", args=[incident.pk]),
            {"planned_start_at": start.isoformat(),
             "planned_end_at": (start + timedelta(hours=2)).isoformat()},
        )
        self.assertEqual(conversion.status_code, 200)
        maintenance = MaintenanceRequest.objects.get(source_incident=incident)
        maintenance_url = reverse(
            "ops:maintenance-update-status-ajax", args=[maintenance.pk]
        )
        self.client.force_login(self.operations_supervisor)
        self.assertEqual(
            self.client.post(maintenance_url, {"status": "approved"}).status_code, 200
        )
        self.client.force_login(self.maintenance_supervisor)
        self.assertEqual(
            self.client.post(maintenance_url, {"status": "in_progress"}).status_code,
            200,
        )
        self.assertEqual(self.client.post(
            maintenance_url,
            {"status": "done", "closing_notes": "تم الإصلاح والاختبار"},
        ).status_code, 200)

        SupervisoryLeadershipService.complete_directive(
            directive, owner, "تم توثيق اختبار التشغيل."
        )
        escalation = SupervisoryLeadershipService.create_action(
            incident=incident, actor=self.head,
            action_type=IncidentSupervisoryAction.ActionType.ESCALATE_TO_GENERAL_MANAGER,
            note="للاعتماد التنفيذي.",
        )
        self.assertEqual(escalation.incident.assigned_to, owner)
        executive = SupervisoryLeadershipService.create_action(
            incident=incident, actor=self.general_manager,
            action_type=IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE,
            note="استكمل التحقق النهائي.",
        )
        SupervisoryLeadershipService.acknowledge_directive(executive, owner)
        SupervisoryLeadershipService.complete_directive(
            executive, owner, "اكتمل التحقق التنفيذي."
        )
        incident.refresh_from_db()
        self.assertEqual(incident.assigned_to, owner)
        self.assertNotEqual(incident.status, Incident.Status.CLOSED)

        for non_owner in (
            self.head, self.department_deputy, self.senior_administrator,
            self.general_manager,
        ):
            self.client.force_login(non_owner)
            self.assertEqual(self.client.post(
                update_url,
                {"status": "closed", "closing_notes": "إغلاق غير مخول"},
            ).status_code, 403)

        self.client.force_login(owner)
        self.assertEqual(self.client.post(
            update_url,
            {"status": "closed", "closing_notes": "تحقق مشرف البلاغات"},
        ).status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.status, Incident.Status.CLOSED)
        self.assertEqual(incident.closed_by, owner)
        self.assertEqual(incident.assigned_to, owner)

    def test_incident_center_exposes_supervisory_section_and_response_controls(self):
        incident = self._create_incident()
        action = SupervisoryLeadershipService.create_action(
            incident=incident, actor=self.head,
            action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            note="أرسل تحديث الحالة.",
        )
        self.client.force_login(self.incident_supervisor)
        page = self.client.get(reverse("ops:incidents"))
        self.assertContains(page, "القيادة الإشرافية")
        self.assertContains(page, reverse(
            "ops:supervisory-request-respond", args=[action.pk]
        ))
        self.assertNotContains(page, "window.alert")
        self.assertNotContains(page, "window.confirm")
        self.assertNotContains(page, "window.prompt")
