"""Aggregate release-health signals and raise actionable critical alerts."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.mail import mail_admins
from django.db import connection
from django.utils import timezone

from apps.exports_center.models import ExportLog


logger = logging.getLogger("platform.monitoring")
STATUS_CODES = (403, 500)


def _window_key(status_code: int) -> str:
    window = timezone.now().strftime("%Y%m%d%H")
    return f"monitoring:http:{window}:{status_code}"


def record_response_status(status_code: int) -> None:
    """Record monitored response statuses without affecting the response."""
    if status_code not in STATUS_CODES:
        return
    try:
        key = _window_key(status_code)
        cache.add(key, 0, timeout=7200)
        cache.incr(key)
    except Exception:
        logger.exception("Unable to record HTTP monitoring metric.")


def _response_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for status_code in STATUS_CODES:
        try:
            counts[str(status_code)] = int(cache.get(_window_key(status_code), 0))
        except Exception:
            counts[str(status_code)] = 0
    return counts


def _database_latency_ms() -> float:
    started_at = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return round((time.perf_counter() - started_at) * 1000, 2)


def _queue_backlog() -> int | None:
    broker_url = settings.CELERY_BROKER_URL
    if not broker_url.startswith(("redis://", "rediss://")):
        return None

    import redis

    client = redis.Redis.from_url(broker_url, socket_connect_timeout=2)
    return int(client.llen(settings.CELERY_TASK_DEFAULT_QUEUE))


def _alert(code: str, value: Any, threshold: Any) -> dict[str, Any]:
    return {"code": code, "value": value, "threshold": threshold}


def collect_monitoring_snapshot() -> dict[str, Any]:
    """Collect post-release signals without exposing sensitive application data."""
    now = timezone.now()
    stale_before = now - timedelta(
        minutes=settings.MONITOR_EXPORT_STALE_MINUTES
    )
    database_latency_ms: float | None
    database_error = False
    try:
        database_latency_ms = _database_latency_ms()
    except Exception:
        database_latency_ms = None
        database_error = True

    queue_backlog: int | None
    queue_error = False
    try:
        queue_backlog = _queue_backlog()
    except Exception:
        queue_backlog = None
        queue_error = True

    failed_exports = ExportLog.objects.filter(
        status=ExportLog.ExportStatus.FAILED,
        created_at__gte=stale_before,
    ).count()
    stale_exports = ExportLog.objects.filter(
        status__in=(
            ExportLog.ExportStatus.PENDING,
            ExportLog.ExportStatus.PROCESSING,
        ),
        created_at__lt=stale_before,
    ).count()
    response_counts = _response_counts()
    alerts: list[dict[str, Any]] = []

    if database_error:
        alerts.append(_alert("database_unavailable", True, False))
    elif database_latency_ms > settings.MONITOR_DB_MAX_LATENCY_MS:
        alerts.append(
            _alert(
                "database_latency_ms",
                database_latency_ms,
                settings.MONITOR_DB_MAX_LATENCY_MS,
            )
        )
    if queue_error:
        alerts.append(_alert("queue_unavailable", True, False))
    elif (
        queue_backlog is not None
        and queue_backlog > settings.MONITOR_QUEUE_BACKLOG_MAX
    ):
        alerts.append(
            _alert(
                "queue_backlog",
                queue_backlog,
                settings.MONITOR_QUEUE_BACKLOG_MAX,
            )
        )
    if failed_exports > settings.MONITOR_FAILED_EXPORTS_MAX:
        alerts.append(
            _alert(
                "failed_exports",
                failed_exports,
                settings.MONITOR_FAILED_EXPORTS_MAX,
            )
        )
    if stale_exports > settings.MONITOR_STALE_EXPORTS_MAX:
        alerts.append(
            _alert(
                "stale_exports",
                stale_exports,
                settings.MONITOR_STALE_EXPORTS_MAX,
            )
        )
    for status_code, threshold in (
        (500, settings.MONITOR_HTTP_500_MAX),
        (403, settings.MONITOR_HTTP_403_MAX),
    ):
        count = response_counts[str(status_code)]
        if count > threshold:
            alerts.append(_alert(f"http_{status_code}", count, threshold))

    return {
        "status": "critical" if alerts else "ok",
        "checked_at": now.isoformat(),
        "database_latency_ms": database_latency_ms,
        "queue_backlog": queue_backlog,
        "failed_exports": failed_exports,
        "stale_exports": stale_exports,
        "http_statuses": response_counts,
        "alerts": alerts,
    }


def emit_critical_alerts(snapshot: dict[str, Any]) -> None:
    """Write structured alerts and optionally notify Django site administrators."""
    for alert in snapshot["alerts"]:
        logger.critical(
            "Critical post-release monitoring threshold exceeded.",
            extra={"event": "critical_alert", "monitor": alert["code"]},
        )
    if snapshot["alerts"] and settings.MONITOR_EMAIL_ALERTS:
        try:
            mail_admins(
                "[CRITICAL] Abwab platform monitoring alert",
                "Critical monitoring thresholds were exceeded. "
                "Review the structured platform.monitoring logs.",
                fail_silently=False,
            )
        except Exception:
            logger.exception("Unable to send monitoring alert email.")