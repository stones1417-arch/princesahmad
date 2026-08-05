from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.ops.models import (
    DoorShift,
    DoorStateHistory,
    MaintenanceRequest,
)


@transaction.atomic
def change_door_state(
    *,
    door_shift: DoorShift,
    new_state: str,
    changed_by,
    reason: str = "",
) -> DoorShift:
    locked_door = (
        DoorShift.objects
        .select_for_update()
        .get(pk=door_shift.pk)
    )

    previous_state = locked_door.state

    if new_state not in DoorShift.DoorState.values:
        raise ValidationError(
            "حالة الباب غير صحيحة."
        )

    if (
        previous_state == DoorShift.DoorState.MAINTENANCE
        and new_state == DoorShift.DoorState.CLOSED
    ):
        open_requests = MaintenanceRequest.objects.filter(
            door_shift=locked_door,
        ).exclude(
            status__in=[
                MaintenanceRequest.Status.CLOSED,
                MaintenanceRequest.Status.COMPLETED,
            ]
        )

        if open_requests.exists() and not reason.strip():
            raise ValidationError(
                "لا يمكن إغلاق باب تحت الصيانة قبل إغلاق "
                "طلب الصيانة أو تسجيل سبب واضح."
            )

    if previous_state == new_state:
        raise ValidationError(
            "الباب موجود بالفعل على الحالة المطلوبة."
        )

    locked_door.state = new_state
    locked_door.save(
        update_fields=[
            "state",
            "updated_at",
        ]
    )

    DoorStateHistory.objects.create(
        door_shift=locked_door,
        previous_state=previous_state,
        new_state=new_state,
        reason=reason.strip(),
        changed_by=changed_by,
    )

    return locked_door