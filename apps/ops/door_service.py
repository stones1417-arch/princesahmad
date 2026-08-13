from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction


def _normalize_reason(reason: Any) -> str:
    """
    تنظيف سبب تغيير حالة الباب.
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
    التحقق من أن حالة الباب الجديدة ضمن الحالات المسموحة.
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
    تغيير حالة الباب مع تسجيل الحالة السابقة والجديدة.

    يعيد:
        tuple:
            updated_door_shift, changed
    """

    from apps.audit.services import (
        record_door_state_history,
    )
    from apps.ops.models import (
        DoorCurrentState,
        DoorShift,
    )

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

    if not locked_door_shift.is_active:
        raise ValidationError(
            "سجل الباب غير نشط."
        )

    if not locked_door_shift.shift_plan.is_active:
        raise ValidationError(
            "لا يمكن تعديل حالة باب تابع لوردية غير نشطة."
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

    effective_user = user

    if effective_user is None and request is not None:
        request_user = getattr(
            request,
            "user",
            None,
        )

        if (
            request_user is not None
            and getattr(
                request_user,
                "is_authenticated",
                False,
            )
        ):
            effective_user = request_user

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
            "updated_at",
        ]
    )

    # تحديث المصدر الرسمي للحالة الحالية إن كان الباب موجودًا
    # في نموذج locations.Door.
    try:
        from apps.locations.models import Door

        door = Door.objects.filter(
            door_number=locked_door_shift.door_number,
        ).first()

        if door is not None:
            DoorCurrentState.objects.update_or_create(
                door=door,
                defaults={
                    "state": normalized_state,
                    "notes": clean_reason,
                    "current_shift": locked_door_shift,
                    "updated_by": effective_user,
                    "update_source": (
                        DoorCurrentState
                        .UpdateSource
                        .OPERATIONS
                    ),
                },
            )

    except (
        LookupError,
        AttributeError,
    ):
        # لا نوقف تغيير حالة DoorShift إذا كان نموذج الباب
        # القديم لا يدعم door_number.
        pass

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
        user=effective_user,
        reason=clean_reason,
    )

    return locked_door_shift, True


class DoorService:
    """
    واجهة توافقية لخدمة الأبواب.

    تدعم الاستيراد المستخدم حاليًا داخل:
    apps/ops/views.py
    """

    @staticmethod
    def change_state(
        *,
        door_shift,
        new_state: str,
        request=None,
        user=None,
        reason: str = "",
    ):
        return change_door_state(
            door_shift=door_shift,
            new_state=new_state,
            request=request,
            user=user,
            reason=reason,
        )

    @staticmethod
    def change_door_state(
        *,
        door_shift,
        new_state: str,
        request=None,
        user=None,
        reason: str = "",
    ):
        return change_door_state(
            door_shift=door_shift,
            new_state=new_state,
            request=request,
            user=user,
            reason=reason,
        )

    @staticmethod
    def update_state(
        *,
        door_shift,
        new_state: str,
        request=None,
        user=None,
        reason: str = "",
    ):
        return change_door_state(
            door_shift=door_shift,
            new_state=new_state,
            request=request,
            user=user,
            reason=reason,
        )