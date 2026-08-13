from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction

if TYPE_CHECKING:
    pass


def _normalize_reason(reason: Any) -> str:
    """
    تنظيف سبب التغيير قبل حفظه.
    """

    if reason is None:
        return ""

    return str(reason).strip()


def _validate_new_state(
    *,
    door_shift,
    new_state: str,
) -> str:
    """
    التحقق من أن الحالة الجديدة ضمن الحالات المسموحة.
    """

    normalized_state = str(
        new_state or ""
    ).strip().lower()

    state_field = door_shift._meta.get_field(
        "state"
    )

    allowed_states = {
        value
        for value, _label in state_field.choices
    }

    if normalized_state not in allowed_states:
        raise ValidationError(
            {
                "state": (
                    "حالة الباب المطلوبة غير صحيحة."
                )
            }
        )

    return normalized_state


@transaction.atomic
def change_door_state(
    *,
    door_shift,
    new_state: str,
    request=None,
    user=None,
    reason: str = "",
):
    """
    تحديث حالة الباب وإنشاء سجل تاريخي داخل معاملة واحدة.

    Returns:
        tuple:
            updated_door_shift, changed
    """

    # الاستيراد داخل الدالة يمنع تحميل النماذج
    # قبل اكتمال تشغيل Django.
    from apps.audit.services import (
        record_door_state_history,
    )
    from apps.ops.models import DoorShift

    if door_shift is None:
        raise ValidationError(
            "سجل حالة الباب غير موجود."
        )

    if not getattr(
        door_shift,
        "pk",
        None,
    ):
        raise ValidationError(
            "سجل حالة الباب غير محفوظ."
        )

    locked_door_shift = (
        DoorShift.objects
        .select_for_update()
        .get(
            pk=door_shift.pk,
        )
    )

    normalized_state = _validate_new_state(
        door_shift=locked_door_shift,
        new_state=new_state,
    )

    old_state = locked_door_shift.state

    if old_state == normalized_state:
        return locked_door_shift, False

    clean_reason = _normalize_reason(
        reason
    )

    if not clean_reason:
        clean_reason = (
            "تحديث حالة الباب من لوحة العمليات"
        )

    old_snapshot = {
        "door_shift_id": locked_door_shift.pk,
        "door_number": locked_door_shift.door_number,
        "state": old_state,
        "is_active": locked_door_shift.is_active,
        "shift_plan_id": (
            locked_door_shift.shift_plan_id
        ),
    }

    locked_door_shift.state = normalized_state

    locked_door_shift.save(
        update_fields=[
            "state",
        ]
    )

    new_snapshot = {
        "door_shift_id": locked_door_shift.pk,
        "door_number": locked_door_shift.door_number,
        "state": locked_door_shift.state,
        "is_active": locked_door_shift.is_active,
        "shift_plan_id": (
            locked_door_shift.shift_plan_id
        ),
    }

    record_door_state_history(
        door_shift=locked_door_shift,
        old_value=old_snapshot,
        new_value=new_snapshot,
        request=request,
        user=user,
        reason=clean_reason,
    )

    return locked_door_shift, True