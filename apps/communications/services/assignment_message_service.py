from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.communications.models import CommunicationLog, CommunicationProvider
from apps.communications.providers.authentica import (
    OperationalMessagingNotConfiguredError,
)
from apps.communications.services.delivery_service import get_provider
from apps.communications.services.masking import mask_value
from apps.communications.services.recipient_resolver import (
    InvalidRecipientError,
    RecipientResolver,
)
from apps.core.system_settings import SystemSettingsService


logger = logging.getLogger("communications")
ASSIGNMENT_CHANNELS = ("sms", "whatsapp")


def _assignment_event_key(assignment, event_type, *, correlation_id=None):
    if correlation_id:
        return correlation_id

    if event_type == "assignment_created":
        return f"assignment:{assignment.pk}:created"
    if event_type == "assignment_updated":
        return f"assignment:{assignment.pk}:updated"
    if event_type == "assignment_cancelled":
        return f"assignment:{assignment.pk}:cancelled"
    return f"assignment:{assignment.pk}:{event_type or 'assignment'}"


def build_assignment_message(assignment, event_type="assignment_created") -> str:
    shift_plan = getattr(assignment, "shift_plan", None)
    door = getattr(assignment, "door", None)
    shift_type = getattr(shift_plan, "shift_type", None)
    supervisor = (
        assignment.__class__.objects.filter(
            shift_plan=shift_plan,
            door=door,
            role=assignment.__class__.Role.SUPERVISOR,
            is_active=True,
        )
        .select_related("employee")
        .first()
    )
    role_display = getattr(assignment, "get_role_display", lambda: "")()
    supervisor_name = getattr(getattr(supervisor, "employee", None), "full_name", "") or "غير محدد"
    door_name = getattr(door, "door_number", "") or "غير محدد"
    shift_name = getattr(shift_type, "name", "") or "غير محدد"
    date = getattr(shift_plan, "date", None)
    start_time = getattr(shift_plan, "start_time", None)
    end_time = getattr(shift_plan, "end_time", None)

    if event_type == "assignment_updated":
        lead = f"تم تحديث تكليفكم إلى الباب {door_name} في وردية {shift_name}."
    elif event_type == "assignment_cancelled":
        lead = f"تم إلغاء تكليفكم على الباب {door_name} في وردية {shift_name}."
    else:
        lead = f"تم تكليفكم بالعمل على الباب {door_name} في وردية {shift_name}."

    if role_display and event_type != "assignment_cancelled":
        lead = f"{lead[:-1]} بصفة {role_display}."

    return "\n".join(
        (
            lead,
            "",
            f"الباب: {door_name}",
            f"الوردية: {shift_name}",
            f"التاريخ: {date.isoformat() if date else 'غير محدد'}",
            f"وقت البداية: {start_time.strftime('%H:%M') if start_time else 'غير محدد'}",
            f"وقت النهاية: {end_time.strftime('%H:%M') if end_time else 'غير محدد'}",
            f"المشرف: {supervisor_name}",
            "",
            "يرجى الالتزام بالتكليف والتعليمات التشغيلية.",
        )
    )


def get_assignment_recipient(employee) -> str:
    return RecipientResolver().resolve(employee, "sms")


class AssignmentMessageService:
    def __init__(self, provider=None):
        self.provider = provider

    def dispatch_assignment_message(
        self,
        assignment,
        channels=("sms", "whatsapp"),
        actor=None,
        event_type="assignment_created",
        correlation_id=None,
    ):
        if not SystemSettingsService.get_effective_value(
            "communications_enabled"
        ):
            return []
        enabled_channels = tuple(
            channel
            for channel in channels
            if not (
                channel == "sms"
                and not SystemSettingsService.get_effective_value(
                    "sms_notifications_enabled"
                )
            )
        )
        return [
            self._dispatch_channel(
                assignment,
                channel,
                actor,
                event_type=event_type,
                correlation_id=correlation_id,
            )
            for channel in enabled_channels
            if channel in ASSIGNMENT_CHANNELS
        ]

    def retry_assignment_message(self, log):
        if not log.related_assignment_id:
            raise ValueError("سجل الرسالة لا يرتبط بتكليف.")
        if log.status == CommunicationLog.Status.SENT:
            raise ValueError("لا يمكن إعادة محاولة رسالة تم إرسالها.")
        if log.status == CommunicationLog.Status.SKIPPED:
            raise ValueError("لا يمكن إعادة المحاولة قبل تحديث رقم جوال الموظف.")
        if not (
            settings.OPERATIONAL_MESSAGING_ENABLED
            and SystemSettingsService.get_effective_value(
                "communications_enabled"
            )
        ):
            return log
        return self._dispatch_channel(
            log.related_assignment,
            log.channel,
            log.created_by,
            event_type=log.request_payload.get("event_type", "assignment_created"),
            correlation_id=log.request_payload.get("correlation_id"),
            retry_log=log,
        )

    def _dispatch_channel(
        self,
        assignment,
        channel,
        actor,
        retry_log=None,
        event_type="assignment_created",
        correlation_id=None,
    ):
        message = build_assignment_message(assignment, event_type=event_type)
        base_key = _assignment_event_key(assignment, event_type, correlation_id=correlation_id)
        idempotency_key = f"{base_key}:{channel}"
        try:
            recipient = get_assignment_recipient(assignment.employee)
        except InvalidRecipientError:
            return self._create_or_get_log(
                assignment=assignment,
                channel=channel,
                actor=actor,
                message=message,
                recipient_masked="",
                status=CommunicationLog.Status.SKIPPED,
                idempotency_key=idempotency_key,
                error_code="invalid_recipient",
                event_type=event_type,
                correlation_id=base_key,
            )

        log = retry_log or self._create_or_get_log(
            assignment=assignment,
            channel=channel,
            actor=actor,
            message=message,
            recipient_masked=mask_value(recipient),
            status=CommunicationLog.Status.PENDING,
            idempotency_key=idempotency_key,
            event_type=event_type,
            correlation_id=base_key,
        )
        if not (
            settings.OPERATIONAL_MESSAGING_ENABLED
            and SystemSettingsService.get_effective_value(
                "communications_enabled"
            )
        ):
            return log

        try:
            provider = self.provider or get_provider()
            method = (
                provider.send_operational_sms
                if channel == "sms"
                else provider.send_operational_whatsapp
            )
            result = method(recipient=recipient, message=message)
        except OperationalMessagingNotConfiguredError as exc:
            log.status = CommunicationLog.Status.FAILED
            log.error_code = "operational_messaging_not_configured"
            log.error_message = str(exc)
            log.retry_count += 1
            log.failed_at = timezone.now()
            log.save(update_fields=["status", "error_code", "error_message", "retry_count", "failed_at", "updated_at"])
            return log

        log.status = result.status
        log.provider_message_id = result.provider_message_id
        log.retry_count += 1
        log.sent_at = timezone.now() if result.status == CommunicationLog.Status.SENT else None
        log.save(update_fields=["status", "provider_message_id", "retry_count", "sent_at", "updated_at"])
        return log

    @staticmethod
    def _create_or_get_log(
        *,
        assignment,
        channel,
        actor,
        message,
        recipient_masked,
        status,
        idempotency_key,
        error_code="",
        event_type="assignment_created",
        correlation_id=None,
    ):
        existing = CommunicationLog.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        provider = CommunicationProvider.objects.filter(
            provider_code=settings.COMMUNICATION_PROVIDER,
            is_active=True,
        ).first()
        try:
            return CommunicationLog.objects.create(
                recipient_employee=assignment.employee,
                recipient_user=assignment.employee.user,
                channel=channel,
                section=assignment.section,
                recipient_address=recipient_masked,
                message_body=message,
                provider=provider,
                related_assignment=assignment,
                related_shift=assignment.shift_plan,
                related_door=assignment.door,
                created_by=actor,
                status=status,
                error_code=error_code,
                idempotency_key=idempotency_key,
                request_payload={
                    "type": "assignment",
                    "event_type": event_type,
                    "channel": channel,
                    "correlation_id": correlation_id,
                },
            )
        except IntegrityError:
            return CommunicationLog.objects.get(idempotency_key=idempotency_key)


def dispatch_assignment_message(
    assignment,
    channels=("sms", "whatsapp"),
    actor=None,
    event_type="assignment_created",
    correlation_id=None,
):
    return AssignmentMessageService().dispatch_assignment_message(
        assignment,
        channels,
        actor,
        event_type=event_type,
        correlation_id=correlation_id,
    )


def retry_assignment_message(log):
    return AssignmentMessageService().retry_assignment_message(log)
