from __future__ import annotations

from datetime import time
from unittest.mock import Mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.communications.models import CommunicationLog
from apps.communications.providers.authentica import (
    AuthenticaProvider,
    OperationalMessagingNotConfiguredError,
)
from apps.communications.services.assignment_message_service import (
    AssignmentMessageService,
    build_assignment_message,
    get_assignment_recipient,
)
from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.distribution.models import DoorAssignment


@override_settings(
    OPERATIONAL_MESSAGING_ENABLED=False,
    ASSIGNMENT_SMS_ENABLED=False,
    ASSIGNMENT_WHATSAPP_ENABLED=False,
)
class AssignmentMessageServiceTests(TestCase):
    def setUp(self):
        shift_type = create_shift_type(name="وردية اختبار تكليف", start_time=time(8), end_time=time(16))
        shift_plan = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8),
            end_time=time(16),
            is_active=True,
        )
        self.employee = create_employee(phone_number="0501234567", operational_section="male")
        self.assignment = DoorAssignment.objects.create(
            shift_plan=shift_plan,
            door=create_door(door_number=31),
            employee=self.employee,
            section="male",
            role=DoorAssignment.Role.MONITOR,
        )

    def test_build_assignment_message_uses_assignment_context(self):
        message = build_assignment_message(self.assignment)

        self.assertIn("الباب: 31", message)
        self.assertIn("الوردية: وردية اختبار تكليف", message)
        self.assertIn("وقت البداية: 08:00", message)
        self.assertIn("المشرف: غير محدد", message)

    def test_phone_normalization_accepts_saudi_formats(self):
        self.employee.phone_number = "5 0123 4567"
        self.assertEqual(get_assignment_recipient(self.employee), "+966501234567")
        self.employee.phone_number = "+966501234567"
        self.assertEqual(get_assignment_recipient(self.employee), "+966501234567")

    def test_invalid_phone_creates_skipped_logs(self):
        self.employee.phone_number = "0412345678"
        self.employee.save(update_fields=["phone_number"])

        logs = AssignmentMessageService().dispatch_assignment_message(self.assignment)

        self.assertEqual(len(logs), 2)
        self.assertTrue(all(log.status == CommunicationLog.Status.SKIPPED for log in logs))
        self.assertTrue(all(not log.recipient_address for log in logs))

    def test_creates_pending_sms_and_whatsapp_logs_with_masked_recipient(self):
        logs = AssignmentMessageService().dispatch_assignment_message(self.assignment)

        self.assertEqual({log.channel for log in logs}, {"sms", "whatsapp"})
        self.assertTrue(all(log.status == CommunicationLog.Status.PENDING for log in logs))
        self.assertTrue(all("501234567" not in log.recipient_address for log in logs))
        self.assertTrue(all(log.related_assignment_id == self.assignment.pk for log in logs))

    def test_duplicate_dispatch_reuses_existing_logs(self):
        service = AssignmentMessageService()
        service.dispatch_assignment_message(self.assignment)
        logs = service.dispatch_assignment_message(self.assignment)

        self.assertEqual(CommunicationLog.objects.filter(related_assignment=self.assignment).count(), 2)
        self.assertEqual(len(logs), 2)

    def test_disabled_messaging_never_calls_provider_or_otp(self):
        provider = Mock()

        AssignmentMessageService(provider=provider).dispatch_assignment_message(self.assignment)

        provider.method_calls == []
        self.assertFalse(provider.method_calls)

    def test_retry_keeps_pending_log_when_operational_messaging_is_disabled(self):
        log = AssignmentMessageService().dispatch_assignment_message(self.assignment, channels=("sms",))[0]

        retried = AssignmentMessageService().retry_assignment_message(log)

        self.assertEqual(retried.pk, log.pk)
        self.assertEqual(retried.status, CommunicationLog.Status.PENDING)

    def test_log_does_not_store_secrets_or_otp(self):
        log = AssignmentMessageService().dispatch_assignment_message(self.assignment, channels=("sms",))[0]

        serialized = f"{log.request_payload} {log.message_body} {log.recipient_address}".lower()
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("otp", serialized)

    @override_settings(OPERATIONAL_MESSAGING_ENABLED=True, AUTHENTICA_SMS_ENDPOINT="", AUTHENTICA_SMS_SENDER="")
    def test_missing_operational_endpoint_does_not_make_http_request(self):
        session = Mock()
        provider = AuthenticaProvider(session=session)

        with self.assertRaises(OperationalMessagingNotConfiguredError):
            provider.send_operational_sms(recipient="+966501234567", message="assignment")

        session.post.assert_not_called()