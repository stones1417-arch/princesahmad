from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.scheduling.models import ShiftPlan


@transaction.atomic
def activate_shift(
    *,
    shift_plan: ShiftPlan,
    activated_by,
    allow_parallel: bool = False,
) -> ShiftPlan:
    """
    تفعيل وردية مع منع وجود ورديتين نشطتين إلا بإذن صريح.
    """
    locked_shift = (
        ShiftPlan.objects
        .select_for_update()
        .get(pk=shift_plan.pk)
    )

    active_shifts = (
        ShiftPlan.objects
        .select_for_update()
        .filter(is_active=True)
        .exclude(pk=locked_shift.pk)
    )

    if active_shifts.exists() and not allow_parallel:
        raise ValidationError(
            "لا يمكن تفعيل ورديتين في الوقت نفسه."
        )

    if _has_seasonal_daily_conflict(locked_shift):
        raise ValidationError(
            "توجد وردية موسمية أو يومية متعارضة مع هذه الوردية."
        )

    locked_shift.is_active = True
    locked_shift.is_finished = False
    locked_shift.activated_by = activated_by
    locked_shift.activated_at = timezone.now()

    locked_shift.save(
        update_fields=[
            "is_active",
            "is_finished",
            "activated_by",
            "activated_at",
        ]
    )

    return locked_shift
def _has_seasonal_daily_conflict(
    shift_plan: ShiftPlan,
) -> bool:
    """
    منع تداخل الوردية الموسمية واليومية حسب وقت البداية والنهاية.
    """
    return (
        ShiftPlan.objects
        .filter(
            date=shift_plan.date,
            start_time__lt=shift_plan.end_time,
            end_time__gt=shift_plan.start_time,
        )
        .exclude(pk=shift_plan.pk)
        .filter(
            is_active=True,
        )
        .exists()
    )
class ShiftCategory(models.TextChoices):
    DAILY = "daily", "يومية"
    SEASONAL = "seasonal", "موسمية" .filter(
    category__in=[
        ShiftPlan.ShiftCategory.DAILY,
        ShiftPlan.ShiftCategory.SEASONAL,
    ]
)