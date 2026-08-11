from __future__ import annotations

import json
import logging
import sys

from django.test import SimpleTestCase

from apps.core.logging import JsonFormatter, SensitiveDataFilter, redact_sensitive


class StructuredLoggingTests(SimpleTestCase):
    def test_redaction_removes_credentials_from_text_and_mapping(self):
        redacted_text = redact_sensitive(
            "password=secret-value Authorization: Bearer token-value"
        )
        redacted_mapping = redact_sensitive(
            {
                "password": "secret-value",
                "nested": {"api_key": "key-value"},
            }
        )

        self.assertNotIn("secret-value", redacted_text)
        self.assertNotIn("token-value", redacted_text)
        self.assertEqual(redacted_mapping["password"], "[REDACTED]")
        self.assertEqual(redacted_mapping["nested"]["api_key"], "[REDACTED]")

    def test_filter_and_formatter_emit_safe_structured_record(self):
        record = logging.LogRecord(
            name="platform.exports",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Export failed with token=secret-token",
            args=(),
            exc_info=None,
        )
        record.event = "export_failed"
        record.export_log_id = 42
        record.password = "secret-password"

        self.assertTrue(SensitiveDataFilter().filter(record))
        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["event"], "export_failed")
        self.assertEqual(payload["export_log_id"], 42)
        self.assertNotIn("secret-token", payload["message"])
        self.assertFalse(hasattr(record, "password") and record.password != "[REDACTED]")

    def test_formatter_redacts_exception_details(self):
        try:
            raise RuntimeError("Authorization: Bearer exception-token")
        except RuntimeError:
            record = logging.LogRecord(
                name="platform.tasks",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="Task failed",
                args=(),
                exc_info=sys.exc_info(),
            )

        payload = json.loads(JsonFormatter().format(record))
        self.assertNotIn("exception-token", payload["exception"])