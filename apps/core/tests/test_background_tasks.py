from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.sms_service import SmsResult
from apps.core.tasks import send_email_task, send_sms_task


class BackgroundTaskTests(SimpleTestCase):
    def test_sms_task_returns_provider_result(self):
        with patch(
            "apps.core.tasks.SmsService.send",
            return_value=SmsResult(success=True, message_id="message-123"),
        ) as mocked_send:
            result = send_sms_task(
                recipient="0500000000",
                message="رسالة اختبار",
                correlation_id="test-123",
            )

        self.assertEqual(
            result,
            {"success": True, "message_id": "message-123", "error": ""},
        )
        mocked_send.assert_called_once()

    def test_email_task_delegates_to_django_mail_backend(self):
        with patch("apps.core.tasks.send_mail", return_value=1) as mocked_send:
            delivered = send_email_task(
                subject="عنوان",
                message="نص الرسالة",
                recipients=["user@example.test"],
                html_message="<p>نص الرسالة</p>",
            )

        self.assertEqual(delivered, 1)
        mocked_send.assert_called_once()