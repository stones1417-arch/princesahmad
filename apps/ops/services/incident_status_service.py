from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


def _normalize_reason(reason: Any) -> str:
    if reason is None:
        return ""

    return str(reason).strip()


def _validate_status(
    *,
    incident,
    new_status: str,
) -> str:
    normalized_status = str(
        new_status or ""
    ).strip().lower()

    status_field = incident._meta.get_field(
        "status"
    )

    allowed_statuses = {
        value
        for value, _label in status_field.choices
    }

    if normalized_status not in allowed_statuses:
        raise ValidationError(
            {
                "status": "حالة البلاغ المطلوبة غير صحيحة."
            }
        )

    return normalized_status


def _is_closed_status(status: str) -> bool:
    return status in {
        "closed",
        "resolved",
        "completed",
    }


@transaction.atomic
def change_incident_status(
    *,
    incident,
    new_status: str,
    request=None,
    user=None,
    reason: str = "",
    closing_notes: str = "",
):
    from apps.audit.services import (
        record_incident_status_history,
    )
    from apps.ops.models import Incident

    if incident is None:
        raise ValidationError(
            "البلاغ غير موجود."
        )

    if not getattr(incident, "pk", None):
        raise ValidationError(
            "البلاغ غير محفوظ."
        )

    locked_incident = (
        Incident.objects
        .select_for_update()
        .get(pk=incident.pk)
    )

    normalized_status = _validate_status(
        incident=locked_incident,
        new_status=new_status,
    )

    old_status = locked_incident.status

    if old_status == normalized_status:
        return locked_incident, False

    clean_reason = _normalize_reason(reason)

    if not clean_reason:
        clean_reason = (
            "تحديث حالة البلاغ من لوحة العمليات"
        )

    old_snapshot = {
        "incident_id": locked_incident.pk,
        "status": old_status,
    }

    for field_name in [
        "shift_plan_id",
        "door_shift_id",
        "priority",
        "incident_type",
        "closed_by_id",
        "closed_at",
        "closing_notes",
        "updated_at",
    ]:
        if hasattr(locked_incident, field_name):
            value = getattr(
                locked_incident,
                field_name,
            )

            if hasattr(value, "isoformat"):
                value = value.isoformat()

            old_snapshot[field_name] = value

    locked_incident.status = normalized_status

    update_fields = [
        "status",
    ]

    effective_user = user

    if effective_user is None and request is not None:
        request_user = getattr(
            request,
            "user",
            None,
        )

        if (
            request_user is not None
            and request_user.is_authenticated
        ):
            effective_user = request_user

    if _is_closed_status(normalized_status):
        if hasattr(locked_incident, "closed_at"):
            locked_incident.closed_at = timezone.now()
            update_fields.append("closed_at")

        if (
            hasattr(locked_incident, "closed_by")
            and effective_user is not None
            and getattr(
                effective_user,
                "is_authenticated",
                False,
            )
        ):
            locked_incident.closed_by = effective_user
            update_fields.append("closed_by")

        if (
            hasattr(locked_incident, "closing_notes")
            and closing_notes
        ):
            locked_incident.closing_notes = (
                str(closing_notes).strip()
            )
            update_fields.append("closing_notes")

    else:
        if hasattr(locked_incident, "closed_at"):
            locked_incident.closed_at = None
            update_fields.append("closed_at")

        if hasattr(locked_incident, "closed_by"):
            locked_incident.closed_by = None
            update_fields.append("closed_by")

    locked_incident.save(
        update_fields=list(
            dict.fromkeys(update_fields)
        )
    )

    new_snapshot = {
        "incident_id": locked_incident.pk,
        "status": locked_incident.status,
    }

    for field_name in [
        "shift_plan_id",
        "door_shift_id",
        "priority",
        "incident_type",
        "closed_by_id",
        "closed_at",
        "closing_notes",
        "updated_at",
    ]:
        if hasattr(locked_incident, field_name):
            value = getattr(
                locked_incident,
                field_name,
            )

            if hasattr(value, "isoformat"):
                value = value.isoformat()

            new_snapshot[field_name] = value

    record_incident_status_history(
        incident=locked_incident,
        old_value=old_snapshot,
        new_value=new_snapshot,
        request=request,
        user=effective_user,
        reason=clean_reason,
    )

    return locked_incident, True