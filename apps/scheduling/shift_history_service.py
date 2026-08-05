from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction


VALID_ACTIONS = {
    "created",
    "activated",
    "updated",
    "finished",
    "cancelled",
    "reopened",
}


def _serialize(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "pk"):
        return {
            "id": value.pk,
            "label": str(value),
        }

    if isinstance(value, dict):
        return {
            str(key): _serialize(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _serialize(item)
            for item in value
        ]

    return str(value)


def shift_plan_snapshot(shift_plan) -> dict[str, Any]:
    """
    أخذ نسخة تاريخية من بيانات الوردية.
    """

    if shift_plan is None:
        return {}

    snapshot = {
        "shift_plan_id": shift_plan.pk,
    }

    candidate_fields = [
        "name",
        "date",
        "shift_date",
        "shift_type_id",
        "season_id",
        "start_time",
        "end_time",
        "effective_start_time",
        "effective_end_time",
        "is_active",
        "is_finished",
        "is_archived",
        "notes",
        "created_at",
        "updated_at",
        "finished_at",
        "created_by_id",
        "finished_by_id",
    ]

    for field_name in candidate_fields:
        if not hasattr(shift_plan, field_name):
            continue

        try:
            value = getattr(
                shift_plan,
                field_name,
            )
        except Exception:
            continue

        snapshot[field_name] = _serialize(
            value
        )

    return snapshot


def _validate_action(action: str) -> str:
    normalized_action = str(
        action or ""
    ).strip().lower()

    if normalized_action not in VALID_ACTIONS:
        raise ValidationError(
            {
                "action": (
                    "إجراء الوردية غير صحيح."
                )
            }
        )

    return normalized_action


@transaction.atomic
def record_shift_created(
    *,
    shift_plan,
    request=None,
    user=None,
    reason: str = "",
):
    """
    تسجيل إنشاء وردية جديدة.
    """

    from apps.audit.services import (
        record_shift_plan_history,
    )

    if shift_plan is None:
        raise ValidationError(
            "الوردية غير موجودة."
        )

    if not getattr(shift_plan, "pk", None):
        raise ValidationError(
            "يجب حفظ الوردية قبل تسجيلها تاريخيًا."
        )

    return record_shift_plan_history(
        shift_plan=shift_plan,
        action="created",
        old_value={},
        new_value=shift_plan_snapshot(
            shift_plan
        ),
        request=request,
        user=user,
        reason=str(
            reason or "إنشاء وردية جديدة"
        ).strip(),
    )


@transaction.atomic
def record_shift_action(
    *,
    shift_plan,
    action: str,
    old_value: dict[str, Any] | None = None,
    request=None,
    user=None,
    reason: str = "",
):
    """
    تسجيل إجراء تم تنفيذه على الوردية.
    """

    from apps.audit.services import (
        record_shift_plan_history,
    )

    if shift_plan is None:
        raise ValidationError(
            "الوردية غير موجودة."
        )

    if not getattr(shift_plan, "pk", None):
        raise ValidationError(
            "الوردية غير محفوظة."
        )

    normalized_action = _validate_action(
        action
    )

    default_reasons = {
        "created": "إنشاء الوردية",
        "activated": "تفعيل الوردية",
        "updated": "تعديل الوردية",
        "finished": "إنهاء الوردية",
        "cancelled": "إلغاء الوردية",
        "reopened": "إعادة فتح الوردية",
    }

    return record_shift_plan_history(
        shift_plan=shift_plan,
        action=normalized_action,
        old_value=old_value or {},
        new_value=shift_plan_snapshot(
            shift_plan
        ),
        request=request,
        user=user,
        reason=str(
            reason
            or default_reasons[
                normalized_action
            ]
        ).strip(),
    )


@transaction.atomic
def update_shift_with_history(
    *,
    shift_plan,
    changes: dict[str, Any],
    action: str = "updated",
    request=None,
    user=None,
    reason: str = "",
):
    """
    تعديل الوردية مع حفظ القيم السابقة والجديدة.
    """

    from apps.audit.services import (
        record_shift_plan_history,
    )
    from apps.scheduling.models import ShiftPlan

    if shift_plan is None:
        raise ValidationError(
            "الوردية غير موجودة."
        )

    if not getattr(shift_plan, "pk", None):
        raise ValidationError(
            "الوردية غير محفوظة."
        )

    normalized_action = _validate_action(
        action
    )

    locked_shift = (
        ShiftPlan.objects
        .select_for_update()
        .get(
            pk=shift_plan.pk,
        )
    )

    old_snapshot = shift_plan_snapshot(
        locked_shift
    )

    valid_fields = {
        field.name
        for field in locked_shift._meta.fields
    }

    changed_fields = []

    for field_name, value in changes.items():
        if field_name not in valid_fields:
            raise ValidationError(
                {
                    field_name: (
                        f"الحقل {field_name} غير موجود "
                        "في نموذج الوردية."
                    )
                }
            )

        old_value = getattr(
            locked_shift,
            field_name,
        )

        old_comparable = getattr(
            old_value,
            "pk",
            old_value,
        )

        new_comparable = getattr(
            value,
            "pk",
            value,
        )

        if old_comparable == new_comparable:
            continue

        setattr(
            locked_shift,
            field_name,
            value,
        )

        changed_fields.append(
            field_name
        )

    if not changed_fields:
        return locked_shift, False

    locked_shift.full_clean()

    locked_shift.save(
        update_fields=changed_fields,
    )

    record_shift_plan_history(
        shift_plan=locked_shift,
        action=normalized_action,
        old_value=old_snapshot,
        new_value=shift_plan_snapshot(
            locked_shift
        ),
        request=request,
        user=user,
        reason=str(
            reason or "تحديث بيانات الوردية"
        ).strip(),
    )

    return locked_shift, True