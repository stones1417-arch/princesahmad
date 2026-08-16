from __future__ import annotations

from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from apps.core.sms_service import SmsResult, SmsService
from apps.core.tasks import send_sms_task


class FourJawalyProviderTests(SimpleTestCase):
    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_success_response_from_fourjawaly(self):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {"messageId": "msg-9001"},
        }

        with patch("apps.core.sms_service.requests.post", return_value=mock_response) as mocked_post:
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا بالعالم",
                correlation_id="corr-01",
            )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, "msg-9001")
        self.assertEqual(result.error, "")
        mocked_post.assert_called_once()
        self.assertEqual(
            mocked_post.call_args.kwargs["auth"],
            ("api-key-123", "api-secret-123"),
        )
        self.assertEqual(
            mocked_post.call_args.kwargs["json"]["messages"][0]["numbers"],
            ["966500000000"],
        )
        self.assertEqual(
            mocked_post.call_args.kwargs["json"]["messages"][0]["sender"],
            "Abwab",
        )

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_missing_fourjawaly_api_key_fails_without_request(self):
        with patch("apps.core.sms_service.requests.post") as mocked_post:
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-02",
            )

        self.assertFalse(result.success)
        self.assertIn("FOURJAWALY_API_KEY", result.error)
        mocked_post.assert_not_called()

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_missing_fourjawaly_api_secret_fails_without_request(self):
        with patch("apps.core.sms_service.requests.post") as mocked_post:
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-03",
            )

        self.assertFalse(result.success)
        self.assertIn("FOURJAWALY_API_SECRET", result.error)
        mocked_post.assert_not_called()

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
    )
    def test_missing_fourjawaly_sender_id_fails_without_request(self):
        with patch("apps.core.sms_service.requests.post") as mocked_post:
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-04",
            )

        self.assertFalse(result.success)
        self.assertIn("FOURJAWALY_SENDER_ID", result.error)
        mocked_post.assert_not_called()

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_arabic_message_is_preserved_in_payload(self):
        message = "تم تكليفكم بالعمل على الباب 15"
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {"messageId": "msg-ar-01"},
        }

        with patch("apps.core.sms_service.requests.post", return_value=mock_response) as mocked_post:
            result = SmsService.send(
                recipient="0500000000",
                message=message,
                correlation_id="corr-arabic",
            )

        self.assertTrue(result.success)
        self.assertEqual(
            mocked_post.call_args.kwargs["json"]["messages"][0]["text"],
            message,
        )

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_invalid_saudi_phone_fails_without_request(self):
        with patch("apps.core.sms_service.requests.post") as mocked_post:
            result = SmsService.send(
                recipient="12345",
                message="مرحبا",
                correlation_id="corr-05",
            )

        self.assertFalse(result.success)
        self.assertIn("غير صحيح", result.error)
        mocked_post.assert_not_called()

    def test_handles_saudi_phone_normalization_variants(self):
        self.assertEqual(
            SmsService.normalize_saudi_phone("0500000000"),
            "966500000000",
        )
        self.assertEqual(
            SmsService.normalize_saudi_phone("+966500000000"),
            "966500000000",
        )
        self.assertEqual(
            SmsService.normalize_saudi_phone("966500000000"),
            "966500000000",
        )

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_authentication_failure_is_safe(self):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Unauthorized"}

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-06",
            )

        self.assertFalse(result.success)
        self.assertIn("Authentication", result.error)
        self.assertNotIn("api-key-123", result.error)
        self.assertNotIn("api-secret-123", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_rate_limit_429_is_handled_safely(self):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 429
        mock_response.json.return_value = {"message": "Too Many Requests"}

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-429",
            )

        self.assertFalse(result.success)
        self.assertIn("Rate limit", result.error)
        self.assertNotIn("api-key-123", result.error)
        self.assertNotIn("api-secret-123", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_server_error_500_is_handled_safely(self):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal Server Error"}

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-500",
            )

        self.assertFalse(result.success)
        self.assertIn("FourJawaly provider server error", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_timeout_failure_is_handled_safely(self):
        with patch(
            "apps.core.sms_service.requests.post",
            side_effect=requests.Timeout("timed out"),
        ):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-timeout",
            )

        self.assertFalse(result.success)
        self.assertIn("تعذر الاتصال", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_connection_error_is_handled_safely(self):
        with patch(
            "apps.core.sms_service.requests.post",
            side_effect=requests.ConnectionError("connection failed"),
        ):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-conn",
            )

        self.assertFalse(result.success)
        self.assertIn("تعذر الاتصال", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_invalid_json_response_is_handled_safely(self):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-invalid-json",
            )

        self.assertFalse(result.success)
        self.assertIn("غير صالحة", result.error)
        self.assertNotIn("api-key-123", result.error)
        self.assertNotIn("api-secret-123", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_success_response_uses_job_ids_when_message_id_missing(self):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "job_ids": ["abc-123"],
        }

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-job-ids",
            )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, "abc-123")

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_failure_response_uses_official_errors_without_numbers(self):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": False,
            "total_success": 0,
            "total_failed": 1,
            "job_ids": [],
            "errors": {"Sender is not allowed": ["966500000000"]},
        }

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-error-keys",
            )

        self.assertFalse(result.success)
        self.assertIn("Sender is not allowed", result.error)
        self.assertNotIn("966500000000", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_multiple_official_errors_are_summarized_safely(self):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": False,
            "total_success": 0,
            "total_failed": 2,
            "job_ids": [],
            "errors": {
                "Sender is not allowed": ["966500000000"],
                "Account blocked": ["966500000001"],
            },
        }

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-error-keys-multi",
            )

        self.assertFalse(result.success)
        self.assertIn("Sender is not allowed", result.error)
        self.assertIn("Account blocked", result.error)
        self.assertNotIn("966500000000", result.error)
        self.assertNotIn("966500000001", result.error)

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_malformed_official_errors_fall_back_safely(self):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": False,
            "errors": ["broken-format"],
            "message": "Request rejected",
        }

        with patch("apps.core.sms_service.requests.post", return_value=mock_response):
            result = SmsService.send(
                recipient="0500000000",
                message="مرحبا",
                correlation_id="corr-error-malformed",
            )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Request rejected")

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="unifonic",
        UNIFONIC_APP_SID="appsid-123",
        UNIFONIC_SENDER_ID="Abwab",
    )
    @patch("apps.core.sms_service.UnifonicSMSProvider.send", return_value=SmsResult(success=True, message_id="legacy-999"))
    def test_unifonic_provider_routes_when_configured(self, mocked_unifonic_send):
        result = SmsService.send(
            recipient="0500000000",
            message="مرحبا",
            correlation_id="corr-legacy",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, "legacy-999")
        mocked_unifonic_send.assert_called_once_with(
            recipient="0500000000",
            message="مرحبا",
            correlation_id="corr-legacy",
        )

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    def test_unknown_provider_fails_closed(self):
        with override_settings(SMS_PROVIDER="unknown"):
            with patch("apps.core.sms_service.requests.post") as mocked_post:
                result = SmsService.send(
                    recipient="0500000000",
                    message="مرحبا",
                    correlation_id="corr-07",
                )

        self.assertFalse(result.success)
        self.assertIn("SMS_PROVIDER", result.error)
        mocked_post.assert_not_called()

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="4jawaly",
        FOURJAWALY_API_KEY="api-key-123",
        FOURJAWALY_API_SECRET="api-secret-123",
        FOURJAWALY_SENDER_ID="Abwab",
    )
    @patch(
        "apps.core.sms_service.FourJawalySMSProvider.send",
        return_value=SmsResult(success=True, message_id="msg-task-9002"),
    )
    def test_send_sms_task_routes_to_fourjawaly(self, mocked_send):
        result = send_sms_task(
            recipient="0500000000",
            message="مرحبا",
            correlation_id="corr-08",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "msg-task-9002")
        mocked_send.assert_called_once_with(
            recipient="0500000000",
            message="مرحبا",
            correlation_id="corr-08",
        )
