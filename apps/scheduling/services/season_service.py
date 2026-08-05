from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.scheduling.models import Season


@transaction.atomic
def activate_season(
    *,
    season: Season,
    activated_by,
) -> Season:
    locked_season = (
        Season.objects
        .select_for_update()
        .get(pk=season.pk)
    )

    overlapping = (
        Season.objects
        .select_for_update()
        .exclude(pk=locked_season.pk)
        .filter(
            status=Season.SeasonStatus.ACTIVE,
            start_date__lte=locked_season.end_date,
            end_date__gte=locked_season.start_date,
        )
    )

    if overlapping.exists():
        raise ValidationError(
            "لا يمكن تفعيل الموسم لوجود موسم نشط متداخل معه."
        )

    if locked_season.status == Season.SeasonStatus.ARCHIVED:
        raise ValidationError(
            "لا يمكن تفعيل موسم مؤرشف."
        )

    locked_season.status = Season.SeasonStatus.ACTIVE
    locked_season.activated_by = activated_by
    locked_season.activated_at = timezone.now()

    locked_season.save(
        update_fields=[
            "status",
            "activated_by",
            "activated_at",
            "updated_at",
        ]
    )

    return locked_season


@transaction.atomic
def deactivate_season(
    *,
    season: Season,
) -> Season:
    locked_season = (
        Season.objects
        .select_for_update()
        .get(pk=season.pk)
    )

    locked_season.status = Season.SeasonStatus.INACTIVE

    locked_season.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return locked_season