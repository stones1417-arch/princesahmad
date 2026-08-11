from __future__ import annotations

import logging

from celery import shared_task
from django.core.mail import send_mail

from apps.core.monitoring import (
    collect_monitoring_snapshot,
    emit_critical_alerts,
)
from apps.core.sms_service import SmsService


logger = logging.getLogger("platform.tasks")


@shared_task
def monitor_platform_task() -> dict:
    """Collect release-health signals from Celery Beat."""
    snapshot = collect_monitoring_snapshot()
    emit_critical_alerts(snapshot)
    return snapshot


@shared_task
def send_sms_task(
    *,
    recipient: str,
    message: str,
    correlation_id: str = "",
) -> dict[str, str | bool]:
    """Deliver an SMS outside the web request."""
    result = SmsService.send(
        recipient=recipient,
        message=message,
        correlation_id=correlation_id,
    )
    if not result.success:
        logger.warning(
            "SMS delivery failed: %s",
            result.error,
            extra={"event": "sms_failed", "task_name": "send_sms_task"},
        )
    else:
        logger.info(
            "SMS delivery completed.",
            extra={"event": "sms_sent", "task_name": "send_sms_task"},
        )

    return {
        "success": result.success,
        "message_id": result.message_id,
        "error": result.error,
    }


@shared_task
def send_email_task(
    *,
    subject: str,
    message: str,
    recipients: list[str],
    html_message: str | None = None,
) -> int:
    """Deliver an application email outside the web request."""
    try:
        delivered = send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Email delivery failed.",
            extra={"event": "email_failed", "task_name": "send_email_task"},
        )
        raise

    logger.info(
        "Email delivery completed.",
        extra={"event": "email_sent", "task_name": "send_email_task"},
    )
    return delivered