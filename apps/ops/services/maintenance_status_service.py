from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction


def _normalize_reason(reason: Any) -> str:
    if reason is None:
        return ""

    return str(reason).strip()


def _validate_status(
    *,
    maintenance_request,
    new_status: str,
) -> str:
    normalized_status = str(
        new_status or ""
    ).strip().lower()

    status_field = maintenance_request._meta.get_field(
        "status"
    )

    allowed_statuses = {
        value
        for value, _label in status_field.choices
    }

    if normalized_status not in allowed_statuses:
        raise ValidationError(
            {
                "status": (
                    "حالة طلب الصيانة المطلوبة غير صحيحة."
                )
            }
        )

    return normalized_status


def _serialize_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


@transaction.atomic
def change_maintenance_status(
    *,
    maintenance_request,
    new_status: str,
    request=None,
    user=None,
    reason: str = "",
):
    """
    تحديث حالة طلب الصيانة مع تسجيل القيمة السابقة والجديدة.

    Returns:
        tuple:
            updated_maintenance_request, changed
    """

    from apps.audit.services import (
        record_maintenance_status_history,
    )
    from apps.ops.models import MaintenanceRequest

    if maintenance_request is None:
        raise ValidationError(
            "طلب الصيانة غير موجود."
        )

    if not getattr(
        maintenance_request,
        "pk",
        None,
    ):
        raise ValidationError(
            "طلب الصيانة غير محفوظ."
        )

    locked_request = (
        MaintenanceRequest.objects
        .select_for_update()
        .get(
            pk=maintenance_request.pk,
        )
    )

    normalized_status = _validate_status(
        maintenance_request=locked_request,
        new_status=new_status,
    )

    old_status = locked_request.status

    if old_status == normalized_status:
        return locked_request, False

    clean_reason = _normalize_reason(
        reason
    )

    if not clean_reason:
        clean_reason = (
            "تحديث حالة طلب الصيانة من لوحة العمليات"
        )

    snapshot_fields = [
        "door_shift_id",
        "shift_plan_id",
        "assigned_to_id",
        "completed_at",
        "updated_at",
        "notes",
        "description",
    ]

    old_snapshot = {
        "maintenance_request_id": locked_request.pk,
        "status": old_status,
    }

    for field_name in snapshot_fields:
        if hasattr(
            locked_request,
            field_name,
        ):
            old_snapshot[field_name] = _serialize_value(
                getattr(
                    locked_request,
                    field_name,
                )
            )

    locked_request.status = normalized_status

    locked_request.save(
        update_fields=[
            "status",
        ]
    )

    new_snapshot = {
        "maintenance_request_id": locked_request.pk,
        "status": locked_request.status,
    }

    for field_name in snapshot_fields:
        if hasattr(
            locked_request,
            field_name,
        ):
            new_snapshot[field_name] = _serialize_value(
                getattr(
                    locked_request,
                    field_name,
                )
            )

    record_maintenance_status_history(
        maintenance_request=locked_request,
        old_value=old_snapshot,
        new_value=new_snapshot,
        request=request,
        user=user,
        reason=clean_reason,
    )

    return locked_request, True