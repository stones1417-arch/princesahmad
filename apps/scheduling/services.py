from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.locations.models import Door
from apps.ops.models import DoorShift

from .models import ShiftPlan


def ensure_shift_door_states(
    shift: ShiftPlan,
) -> int:
    """
    التأكد من وجود سجل DoorShift لكل باب نشط
    داخل الوردية المحددة.

    يعيد عدد السجلات التي تم إنشاؤها.
    """

    if not isinstance(shift, ShiftPlan):
        raise ValidationError(
            "الوردية المحددة غير صحيحة."
        )

    active_doors = (
        Door.objects
        .filter(
            is_active=True,
            door_number__gte=1,
            door_number__lte=41,
        )
        .order_by(
            "door_number"
        )
    )

    existing_door_numbers = set(
        DoorShift.objects
        .filter(
            shift_plan=shift
        )
        .values_list(
            "door_number",
            flat=True,
        )
    )

    door_shifts_to_create = []

    for door in active_doors:
        if (
            door.door_number
            in existing_door_numbers
        ):
            continue

        door_shifts_to_create.append(
            DoorShift(
                shift_plan=shift,
                door_number=door.door_number,
                state=(
                    DoorShift
                    .DoorState
                    .OPEN
                ),
                is_active=True,
                notes="",
            )
        )

    if door_shifts_to_create:
        DoorShift.objects.bulk_create(
            door_shifts_to_create,
            ignore_conflicts=True,
        )

    DoorShift.objects.filter(
        shift_plan=shift,
        door_number__in=active_doors.values_list(
            "door_number",
            flat=True,
        ),
    ).update(
        is_active=True
    )

    return len(
        door_shifts_to_create
    )


@transaction.atomic
def activate_shift(
    shift: ShiftPlan,
) -> ShiftPlan:
    """
    تفعيل وردية محددة وإنهاء أي وردية نشطة أخرى.

    يعتمد النظام على:
    - is_active
    - is_finished

    وعند تفعيل الوردية يتم إنشاء حالة تشغيلية
    لكل باب نشط داخل DoorShift.
    """

    if not isinstance(shift, ShiftPlan):
        raise ValidationError(
            "الوردية المحددة غير صحيحة."
        )

    shift = (
        ShiftPlan.objects
        .select_for_update(of=("self",))
        .get(
            pk=shift.pk
        )
    )

    if shift.is_finished:
        raise ValidationError(
            "لا يمكن تفعيل وردية منتهية."
        )

    other_active_shifts = (
        ShiftPlan.objects
        .select_for_update(of=("self",))
        .filter(
            is_active=True
        )
        .exclude(
            pk=shift.pk
        )
    )

    for active_shift in other_active_shifts:
        active_shift.is_active = False
        active_shift.is_finished = True

        update_fields = [
            "is_active",
            "is_finished",
        ]

        if hasattr(
            active_shift,
            "finished_at",
        ):
            active_shift.finished_at = (
                timezone.now()
            )

            update_fields.append(
                "finished_at"
            )

        active_shift.save(
            update_fields=update_fields
        )

        DoorShift.objects.filter(
            shift_plan=active_shift,
            is_active=True,
        ).update(
            is_active=False
        )

    update_fields = []

    if not shift.is_active:
        shift.is_active = True

        update_fields.append(
            "is_active"
        )

    if shift.is_finished:
        shift.is_finished = False

        update_fields.append(
            "is_finished"
        )

    if hasattr(
        shift,
        "activated_at",
    ):
        shift.activated_at = (
            timezone.now()
        )

        update_fields.append(
            "activated_at"
        )

    if hasattr(
        shift,
        "finished_at",
    ):
        if shift.finished_at is not None:
            shift.finished_at = None

            update_fields.append(
                "finished_at"
            )

    if update_fields:
        shift.save(
            update_fields=list(
                dict.fromkeys(
                    update_fields
                )
            )
        )

    ensure_shift_door_states(
        shift
    )

    shift.refresh_from_db()

    return shift


@transaction.atomic
def finish_shift(
    shift: ShiftPlan,
) -> ShiftPlan:
    """
    إنهاء وردية محددة وإيقاف حالات أبوابها.
    """

    if not isinstance(shift, ShiftPlan):
        raise ValidationError(
            "الوردية المحددة غير صحيحة."
        )

    shift = (
        ShiftPlan.objects
        .select_for_update()
        .get(
            pk=shift.pk
        )
    )

    if shift.is_finished:
        DoorShift.objects.filter(
            shift_plan=shift,
            is_active=True,
        ).update(
            is_active=False
        )

        return shift

    shift.is_active = False
    shift.is_finished = True

    update_fields = [
        "is_active",
        "is_finished",
    ]

    if hasattr(
        shift,
        "finished_at",
    ):
        shift.finished_at = (
            timezone.now()
        )

        update_fields.append(
            "finished_at"
        )

    shift.save(
        update_fields=update_fields
    )

    DoorShift.objects.filter(
        shift_plan=shift,
        is_active=True,
    ).update(
        is_active=False
    )

    return shift


@transaction.atomic
def deactivate_shift(
    shift: ShiftPlan,
) -> ShiftPlan:
    """
    إلغاء تفعيل الوردية دون اعتبارها منتهية،
    مع إيقاف حالات أبوابها التشغيلية.
    """

    if not isinstance(shift, ShiftPlan):
        raise ValidationError(
            "الوردية المحددة غير صحيحة."
        )

    shift = (
        ShiftPlan.objects
        .select_for_update()
        .get(
            pk=shift.pk
        )
    )

    if shift.is_active:
        shift.is_active = False

        shift.save(
            update_fields=[
                "is_active",
            ]
        )

    DoorShift.objects.filter(
        shift_plan=shift,
        is_active=True,
    ).update(
        is_active=False
    )

    return shift