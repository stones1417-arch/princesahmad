from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.monitoring import (
    _window_key,
    collect_monitoring_snapshot,
    record_response_status,
)
from apps.exports_center.models import ExportLog


@override_settings(
    MONITOR_DB_MAX_LATENCY_MS=250,
    MONITOR_QUEUE_BACKLOG_MAX=100,
    MONITOR_FAILED_EXPORTS_MAX=0,
    MONITOR_STALE_EXPORTS_MAX=0,
    MONITOR_EXPORT_STALE_MINUTES=15,
    MONITOR_HTTP_500_MAX=0,
    MONITOR_HTTP_403_MAX=25,
)
class MonitoringTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.core.monitoring._queue_backlog", return_value=0)
    def test_snapshot_is_ok_when_no_threshold_is_exceeded(self, _queue_backlog):
        snapshot = collect_monitoring_snapshot()

        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["alerts"], [])
        self.assertEqual(snapshot["queue_backlog"], 0)

    @patch("apps.core.monitoring._queue_backlog", return_value=0)
    def test_stale_export_is_critical(self, _queue_backlog):
        export = ExportLog.objects.create(
            module="monitoring",
            status=ExportLog.ExportStatus.PENDING,
        )
        ExportLog.objects.filter(pk=export.pk).update(
            created_at=timezone.now() - timedelta(minutes=16)
        )

        snapshot = collect_monitoring_snapshot()

        self.assertEqual(snapshot["status"], "critical")
        self.assertIn(
            "stale_exports",
            [alert["code"] for alert in snapshot["alerts"]],
        )

    def test_records_only_monitored_response_statuses(self):
        record_response_status(200)
        record_response_status(403)
        record_response_status(500)

        self.assertIsNone(cache.get(_window_key(200)))
        self.assertEqual(cache.get(_window_key(403)), 1)
        self.assertEqual(cache.get(_window_key(500)), 1)