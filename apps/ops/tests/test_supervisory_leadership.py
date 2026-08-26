from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import Notification
from apps.roles.models import Role, UserRole

from apps.ops.models import Incident, IncidentSupervisoryAction, LeadershipDelegation
from apps.ops.supervisory_leadership_service import SupervisoryLeadershipService


class SupervisoryLeadershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for code, section in (
            ("doors_department_head", "male"),
            ("doors_department_deputy", "male"),
            ("senior_administrator", "male"),
            ("general_manager", "all"),
        ):
            group = Group.objects.create(name=f"test-{code}")
            role = Role.objects.create(
                code=code, name=f"اختبار {code}", group=group,
                operational_section=section, is_system_role=True,
            )
            user = get_user_model().objects.create_user(username=f"u-{code}")
            UserRole.objects.create(user=user, role=role)
            cls.users[code] = user
        cls.owner = get_user_model().objects.create_user(username="incident-owner")
        cls.incident = Incident.objects.create(
            section="male", description="بلاغ اختبار إشرافي",
            assigned_to=cls.owner, assigned_to_name="المالك التنفيذي",
            created_by=cls.owner,
        )

    def test_head_action_preserves_executive_owner_and_notifies_internally(self):
        action = SupervisoryLeadershipService.create_action(
            incident=self.incident,
            actor=self.users["doors_department_head"],
            action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            note="تزويد القيادة بتحديث الحالة.",
        )
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.assigned_to, self.owner)
        self.assertEqual(action.target_user, self.owner)
        self.assertTrue(Notification.objects.filter(user=self.owner).exists())

    def test_deputy_requires_active_non_overlapping_delegation(self):
        deputy = self.users["doors_department_deputy"]
        with self.assertRaises(PermissionDenied):
            SupervisoryLeadershipService.create_action(
                incident=self.incident, actor=deputy,
                action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_NOTE,
                note="قبل التفويض",
            )
        now = timezone.now()
        delegation = SupervisoryLeadershipService.create_delegation(
            principal=self.users["doors_department_head"], delegate=deputy,
            section="male", starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(hours=1), reason="تغطية مؤقتة",
        )
        action = SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=deputy,
            action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_NOTE,
            note="أثناء التفويض",
        )
        self.assertEqual(action.acting_for, delegation.principal)
        with self.assertRaises(ValidationError):
            SupervisoryLeadershipService.create_delegation(
                principal=delegation.principal, delegate=deputy, section="male",
                starts_at=now, ends_at=now + timedelta(minutes=30),
            )

    def test_senior_admin_cannot_issue_supervisory_directive(self):
        with self.assertRaises(PermissionDenied):
            SupervisoryLeadershipService.create_action(
                incident=self.incident, actor=self.users["senior_administrator"],
                action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE,
                note="غير مسموح",
            )

    def test_general_manager_only_sees_and_acts_on_escalated_incidents(self):
        manager = self.users["general_manager"]
        self.assertFalse(SupervisoryLeadershipService.visible_incidents(manager).exists())
        with self.assertRaises(PermissionDenied):
            SupervisoryLeadershipService.create_action(
                incident=self.incident, actor=manager,
                action_type=IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE,
                note="قبل التصعيد",
            )
        self.incident.escalation_level = Incident.EscalationLevel.GENERAL_MANAGER
        self.incident.save(update_fields=["escalation_level"])
        self.assertTrue(SupervisoryLeadershipService.visible_incidents(manager).exists())

    def test_supervisory_resolution_does_not_close_incident(self):
        SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=self.users["doors_department_head"],
            action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_RESOLVED,
            note="اكتملت المتابعة الإشرافية",
        )
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.NEW)
        self.assertEqual(
            self.incident.supervisory_actions.get().status,
            IncidentSupervisoryAction.Status.RESOLVED,
        )

    def test_delegation_model_rejects_self_and_invalid_period(self):
        head = self.users["doors_department_head"]
        now = timezone.now()
        item = LeadershipDelegation(
            principal=head, delegate=head, section="male", starts_at=now,
            ends_at=now - timedelta(minutes=1), created_by=head,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_department_center_renders_bounded_inbox_and_detail(self):
        self.incident.escalation_level = Incident.EscalationLevel.DEPARTMENT_HEAD
        self.incident.save(update_fields=["escalation_level"])
        self.client.force_login(self.users["doors_department_head"])
        response = self.client.get(reverse("ops:department-command-center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.incident.incident_number)
        detail = self.client.get(reverse("ops:supervisory-incident-detail", args=[self.incident.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "المسؤول التنفيذي")

    def test_command_center_ui_uses_arabic_role_identity_and_compact_empty_state(self):
        self.client.force_login(self.users["doors_department_head"])
        response = self.client.get(reverse("ops:department-command-center"))
        self.assertContains(response, "مركز قيادة قسم الأبواب")
        self.assertContains(response, "صفة الدخول: رئيس قسم الأبواب")
        self.assertContains(response, "المركز: قيادة قسم الأبواب")
        self.assertContains(response, "لا توجد حالات تحتاج قرارك حاليًا")
        self.assertNotContains(response, "نطاقك الحالي: doors_department_head")
        self.assertNotContains(response, "تفاصيل البلاغ")
        self.assertContains(response, "supervisory_command_center.css")
        self.assertContains(response, "supervisory_command_center.js")

    def test_role_specific_centers_render_only_the_active_identity(self):
        cases = (
            ("senior_administrator", "administrative-command-center", "مركز المتابعة الإدارية", "المتابعات المفتوحة"),
            ("general_manager", "executive-command-center", "مركز القيادة التنفيذية", "قرارات تنتظر المدير العام"),
        )
        for role, route, title, queue_title in cases:
            with self.subTest(role=role):
                self.client.force_login(self.users[role])
                response = self.client.get(reverse(f"ops:{route}"))
                self.assertContains(response, title)
                self.assertContains(response, queue_title)
                self.assertNotContains(response, "مركز رئيس القسم")

    def test_natural_center_context_uses_actual_arabic_capacity(self):
        cases = (
            ("doors_department_head", "department-command-center", "رئيس قسم الأبواب"),
            ("senior_administrator", "administrative-command-center", "كبير الإداريين"),
            ("general_manager", "executive-command-center", "المدير العام"),
        )
        for role, route, label in cases:
            with self.subTest(role=role):
                self.client.force_login(self.users[role])
                response = self.client.get(reverse(f"ops:{route}"))
                self.assertEqual(response.context["actual_role_label"], label)
                self.assertEqual(response.context["effective_capacity_label"], label)
                self.assertFalse(response.context["is_cross_center_oversight"])
                self.assertContains(response, f"صفة الدخول: {label}")
                self.assertNotContains(response, "عرض إشرافي")

    def test_general_manager_cross_center_context_is_oversight_not_relabeling(self):
        manager = self.users["general_manager"]
        for role_code in ("doors_department_head", "senior_administrator"):
            role = UserRole.objects.get(user=self.users[role_code]).role
            UserRole.objects.create(user=manager, role=role)
        self.client.force_login(manager)
        for route, center_label in (
            ("department-command-center", "قيادة قسم الأبواب"),
            ("administrative-command-center", "المتابعة الإدارية"),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(f"ops:{route}"))
                self.assertEqual(response.context["actual_role_label"], "المدير العام")
                self.assertEqual(response.context["center_label"], center_label)
                self.assertTrue(response.context["is_cross_center_oversight"])
                self.assertContains(response, "صفة الدخول: المدير العام")
                self.assertContains(response, f"المركز: {center_label}")
                self.assertContains(response, "عرض إشرافي")
                self.assertNotContains(response, "صفة الدخول: رئيس قسم الأبواب")
                self.assertNotContains(response, "صفة الدخول: كبير الإداريين")

    def test_deputy_ui_is_read_only_without_delegation_and_active_with_it(self):
        deputy = self.users["doors_department_deputy"]
        self.client.force_login(deputy)
        response = self.client.get(reverse("ops:department-command-center"))
        self.assertContains(response, "صفة الدخول: وكيل رئيس قسم الأبواب")
        self.assertContains(response, "عرض إشرافي")
        self.assertContains(response, "لا يوجد تفويض نشط")
        self.assertNotContains(response, "تسجيل إجراء")
        now = timezone.now()
        SupervisoryLeadershipService.create_delegation(
            principal=self.users["doors_department_head"], delegate=deputy,
            section="male", starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(hours=1), reason="تغطية مؤقتة",
        )
        response = self.client.get(reverse("ops:department-command-center"))
        self.assertContains(response, "صفة الدخول: وكيل رئيس قسم الأبواب")
        self.assertContains(response, "تفويض نشط")
        self.assertContains(response, "تعمل بالنيابة عن رئيس قسم الأبواب")
        self.assertNotContains(response, "صفة الدخول: رئيس قسم الأبواب")

    def test_detail_is_a_drawer_with_responsibility_and_operational_blocks(self):
        self.client.force_login(self.users["doors_department_head"])
        response = self.client.get(
            reverse("ops:supervisory-incident-detail", args=[self.incident.pk])
        )
        self.assertContains(response, 'class="supervisory-center-drawer"')
        self.assertContains(response, "المسؤول التنفيذي عن البلاغ")
        self.assertContains(response, "تبقى المسؤولية التنفيذية")
        self.assertContains(response, "المسار الإشرافي")
        self.assertContains(response, "طلبات التحديث والتوجيهات والمتابعة الإدارية")
        self.assertContains(response, "لا يوجد طلب صيانة مرتبط")
        self.assertContains(response, "الخط الزمني")

    def test_center_switcher_is_permission_aware_and_marks_current_center(self):
        senior_role = UserRole.objects.get(user=self.users["senior_administrator"]).role
        UserRole.objects.create(user=self.users["doors_department_head"], role=senior_role)
        self.client.force_login(self.users["doors_department_head"])
        response = self.client.get(reverse("ops:department-command-center"))
        self.assertContains(response, "مراكز القيادة")
        self.assertContains(response, "قيادة قسم الأبواب")
        self.assertContains(response, "المتابعة الإدارية")
        self.assertContains(response, 'aria-selected="true"')

    def test_incident_list_query_is_bounded(self):
        query = SupervisoryLeadershipService.visible_incidents(
            self.users["doors_department_head"]
        )
        with self.assertNumQueries(2):
            list(query)

    def test_request_update_response_is_linked_answered_and_preserves_incident(self):
        request_action = SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=self.users["doors_department_head"],
            action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            subject="حالة التنفيذ", note="أرسل آخر تحديث.",
        )
        response = SupervisoryLeadershipService.respond_to_update_request(
            request_action, self.owner, "تمت المعالجة الميدانية.",
        )
        request_action.refresh_from_db()
        self.incident.refresh_from_db()
        self.assertEqual(response.parent, request_action)
        self.assertEqual(request_action.status, IncidentSupervisoryAction.Status.ANSWERED)
        self.assertEqual(self.incident.assigned_to, self.owner)
        self.assertEqual(self.incident.status, Incident.Status.NEW)
        self.assertEqual(Notification.objects.filter(
            user=self.users["doors_department_head"], title="رد على طلب تحديث",
        ).count(), 1)
        SupervisoryLeadershipService.resolve_update_request(
            request_action, self.users["doors_department_head"]
        )
        request_action.refresh_from_db()
        self.assertEqual(request_action.status, IncidentSupervisoryAction.Status.RESOLVED)

    def test_only_request_target_can_respond_and_response_is_single(self):
        request_action = SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=self.users["senior_administrator"],
            action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            note="تحديث مطلوب",
        )
        with self.assertRaises(PermissionDenied):
            SupervisoryLeadershipService.respond_to_update_request(
                request_action, self.users["doors_department_head"], "رد مزور"
            )
        SupervisoryLeadershipService.respond_to_update_request(
            request_action, self.owner, "الرد الصحيح"
        )
        with self.assertRaises(ValidationError):
            SupervisoryLeadershipService.respond_to_update_request(
                request_action, self.owner, "رد مكرر"
            )

    def test_directive_requires_target_ack_before_completion(self):
        directive = SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=self.users["doors_department_head"],
            action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE,
            note="تحقق من سبب التكرار.",
        )
        self.assertEqual(directive.status, IncidentSupervisoryAction.Status.OPEN)
        with self.assertRaises(PermissionDenied):
            SupervisoryLeadershipService.acknowledge_directive(
                directive, self.users["senior_administrator"]
            )
        with self.assertRaises(ValidationError):
            SupervisoryLeadershipService.complete_directive(
                directive, self.owner, "قبل الاستلام"
            )
        SupervisoryLeadershipService.acknowledge_directive(directive, self.owner)
        directive.refresh_from_db()
        self.assertEqual(directive.status, IncidentSupervisoryAction.Status.ACKNOWLEDGED)
        SupervisoryLeadershipService.complete_directive(
            directive, self.owner, "نُفذ التحقق المطلوب."
        )
        directive.refresh_from_db()
        self.incident.refresh_from_db()
        self.assertEqual(directive.status, IncidentSupervisoryAction.Status.COMPLETED)
        self.assertEqual(directive.completed_by, self.owner)
        self.assertEqual(self.incident.status, Incident.Status.NEW)
        self.assertEqual(self.incident.assigned_to, self.owner)

    def test_head_attention_queue_contains_answered_request_deterministically(self):
        request_action = SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=self.users["doors_department_head"],
            action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            note="تحديث",
        )
        SupervisoryLeadershipService.respond_to_update_request(
            request_action, self.owner, "تم"
        )
        queue = SupervisoryLeadershipService.head_attention_queue(
            self.users["doors_department_head"]
        )
        self.assertEqual([item.pk for item in queue], [self.incident.pk])
        self.assertEqual(queue[0].attention_rank, 4)

    def test_incident_supervisor_response_endpoint_and_drawer_integration(self):
        action = SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=self.users["doors_department_head"],
            action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            note="أفدنا بالحالة",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("ops:supervisory-request-respond", args=[action.pk]),
            {"note": "تم التنفيذ"},
        )
        self.assertEqual(response.status_code, 200)

    def test_notification_recipients_are_relevant_deduplicated_and_exclude_actor(self):
        head = self.users["doors_department_head"]
        manager = self.users["general_manager"]
        SupervisoryLeadershipService._notify(
            recipients=[head, head, manager], actor=head, title="اختبار الضوضاء",
            message="اختبار", section="male", url="/ops/leadership/",
        )
        self.assertEqual(Notification.objects.filter(title="اختبار الضوضاء").count(), 1)
        self.assertTrue(Notification.objects.filter(
            title="اختبار الضوضاء", user=manager
        ).exists())
        self.assertFalse(Notification.objects.filter(
            title="اختبار الضوضاء", user=head
        ).exists())

    def test_administrative_alert_notifies_head_not_owner_or_gm(self):
        action = SupervisoryLeadershipService.create_action(
            incident=self.incident, actor=self.users["senior_administrator"],
            action_type=IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT,
            note="تنبيه إداري يحتاج مراجعة.",
        )
        self.assertEqual(action.target_user, self.users["doors_department_head"])
        self.assertTrue(Notification.objects.filter(
            user=self.users["doors_department_head"], title="تنبيه إداري",
        ).exists())
        self.assertFalse(Notification.objects.filter(
            user=self.owner, title="تنبيه إداري",
        ).exists())
        self.assertFalse(Notification.objects.filter(
            user=self.users["general_manager"], title="تنبيه إداري",
        ).exists())
