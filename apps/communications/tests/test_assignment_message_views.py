from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
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
from apps.roles.models import Role, UserRole


@override_settings(OPERATIONAL_MESSAGING_ENABLED=False)
class AssignmentMessageViewTests(TestCase):
    def setUp(self):
        self.user = create_user(is_staff=True)
        group = Group.objects.create(name="assignment-message-dashboard")
        group.permissions.add(Permission.objects.get(content_type__app_label="roles", codename="view_distribution"))
        role = Role.objects.create(code="assignment-message-dashboard", name="assignment-message-dashboard", group=group)
        UserRole.objects.create(user=self.user, role=role)
        self.employee = create_employee(
            user=create_user(username="assignment-recipient"),
            full_name="موظف رسائل التكليف",
            employee_number="77101",
            operational_section="male",
            phone_number="+966501234567",
        )
        shift_type = create_shift_type(name="وردية مركز الرسائل", start_time=time(8), end_time=time(16))
        shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8),
            end_time=time(16),
            is_active=True,
        )
        self.assignment = DoorAssignment.objects.create(
            shift_plan=shift,
            door=create_door(door_number=33),
            employee=self.employee,
            section="male",
            role=DoorAssignment.Role.MONITOR,
        )
        self.sms_log = self._log("sms", CommunicationLog.Status.PENDING, "رسالة SMS آمنة")
        self.whatsapp_log = self._log("whatsapp", CommunicationLog.Status.FAILED, "رسالة WhatsApp آمنة")
        self.other_log = CommunicationLog.objects.create(
            recipient_employee=self.employee,
            channel="email",
            section="male",
            status=CommunicationLog.Status.SENT,
            recipient_address="masked@example.test",
            message_body="تنبيه غير متعلق بالتكليف",
        )

    def _log(self, channel, status, message):
        return CommunicationLog.objects.create(
            recipient_employee=self.employee,
            recipient_user=self.employee.user,
            channel=channel,
            section="male",
            status=status,
            recipient_address="+9665*****567",
            message_body=message,
            related_assignment=self.assignment,
            related_shift=self.assignment.shift_plan,
            related_door=self.assignment.door,
            error_code="operational_messaging_not_configured" if status == CommunicationLog.Status.FAILED else "",
            error_message="Authorization: secret-token",
            idempotency_key=f"view-test:{channel}:{message}",
        )

    def _login(self):
        self.client.force_login(self.user)

    def test_list_requires_login(self):
        response = self.client.get(reverse("communications:assignment-messages"))

        self.assertEqual(response.status_code, 302)

    def test_list_contains_only_assignment_logs_and_stats(self):
        self._login()
        response = self.client.get(reverse("communications:assignment-messages"))

        log_ids = {log.pk for log in response.context["page_obj"].object_list}
        self.assertEqual(log_ids, {self.sms_log.pk, self.whatsapp_log.pk})
        self.assertEqual(response.context["stats"]["total"], 2)
        self.assertEqual(response.context["stats"]["sms"], 1)
        self.assertEqual(response.context["stats"]["whatsapp"], 1)

    def test_list_has_correct_header_and_empty_state_text(self):
        self._login()
        response = self.client.get(
            reverse("communications:assignment-messages"),
            {"channel": "sms", "status": "pending", "q": "مستخدم-غير-موجود"},
        )

        self.assertContains(response, "سجل رسائل التكليف")
        self.assertContains(response, "متابعة رسائل SMS وWhatsApp المرتبطة بالتكليفات التشغيلية")
        self.assertContains(response, "لا توجد رسائل تكليف مطابقة للفلاتر الحالية.")
        self.assertContains(response, "إعادة ضبط")
        self.assertNotContains(response, "لا توجد رسائل تكليف مطابقة.")

    def test_list_filters_channel_status_and_employee_search(self):
        self._login()
        url = reverse("communications:assignment-messages")
        response = self.client.get(url, {"channel": "whatsapp", "status": "failed", "q": "77101"})

        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["page_obj"].object_list[0].pk, self.whatsapp_log.pk)

    def test_list_paginates_and_preserves_query(self):
        for index in range(51):
            self._log("sms", CommunicationLog.Status.PENDING, f"رسالة {index}")
        self._login()
        response = self.client.get(reverse("communications:assignment-messages"), {"q": "موظف", "page": 2})

        self.assertEqual(len(response.context["page_obj"].object_list), 3)
        self.assertIn("q=", response.context["query_string"])

    def test_detail_masks_recipient_and_hides_secrets(self):
        self._login()
        response = self.client.get(reverse("communications:assignment-message-detail", args=[self.whatsapp_log.pk]))

        self.assertContains(response, "+9665*****567")
        self.assertNotContains(response, "+966501234567")
        self.assertNotContains(response, "secret-token")
        self.assertContains(response, "رسالة WhatsApp آمنة")

    def test_detail_builds_preview_when_snapshot_is_empty(self):
        self.sms_log.message_body = ""
        self.sms_log.save(update_fields=["message_body"])
        self._login()

        response = self.client.get(reverse("communications:assignment-message-detail", args=[self.sms_log.pk]))

        self.assertContains(response, "تم تكليفكم بالعمل")

    def test_retry_requires_post_and_permission(self):
        self._login()
        url = reverse("communications:assignment-message-retry", args=[self.sms_log.pk])

        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_retry_rejects_sent_and_skipped_logs(self):
        permission = Permission.objects.get(codename="can_retry_assignment_message")
        self.user.user_permissions.add(permission)
        sent = self._log("sms", CommunicationLog.Status.SENT, "تم الإرسال")
        skipped = self._log("whatsapp", CommunicationLog.Status.SKIPPED, "تم التخطي")
        self._login()

        sent_response = self.client.post(reverse("communications:assignment-message-retry", args=[sent.pk]), follow=True)
        skipped_response = self.client.post(reverse("communications:assignment-message-retry", args=[skipped.pk]), follow=True)

        self.assertContains(sent_response, "لا يمكن إعادة محاولة رسالة تم إرسالها")
        self.assertContains(skipped_response, "لا يمكن إعادة المحاولة قبل تحديث رقم جوال الموظف")

    def test_pending_retry_stays_pending_without_http(self):
        permission = Permission.objects.get(codename="can_retry_assignment_message")
        self.user.user_permissions.add(permission)
        self._login()
        with patch("apps.communications.services.assignment_message_service.get_provider") as provider:
            response = self.client.post(reverse("communications:assignment-message-retry", args=[self.sms_log.pk]), follow=True)

        self.sms_log.refresh_from_db()
        self.assertEqual(self.sms_log.status, CommunicationLog.Status.PENDING)
        self.assertFalse(provider.called)
        self.assertContains(response, "الإرسال التشغيلي الخارجي غير مفعّل حاليًا")

    def test_assignment_dashboard_shows_sms_and_whatsapp_status(self):
        self._login()
        response = self.client.get(reverse("distribution:dashboard"))

        self.assertContains(response, "SMS:")
        self.assertContains(response, "WhatsApp:")