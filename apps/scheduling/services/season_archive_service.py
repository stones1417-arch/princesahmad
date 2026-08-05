from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.scheduling.models import Season


@transaction.atomic
def archive_season(
    *,
    season: Season,
    archived_by,
) -> Season:
    season = (
        Season.objects
        .select_for_update()
        .get(pk=season.pk)
    )

    if season.shift_plans.filter(
        is_active=True,
    ).exists():
        raise ValidationError(
            "لا يمكن أرشفة موسم يحتوي على ورديات نشطة."
        )

    unfinished_shifts = season.shift_plans.filter(
        is_finished=False,
    )

    if unfinished_shifts.exists():
        raise ValidationError(
            "لا يمكن أرشفة الموسم قبل إنهاء جميع وردياته."
        )

    season.status = Season.SeasonStatus.ARCHIVED
    season.archived_by = archived_by
    season.archived_at = timezone.now()

    season.save(
        update_fields=[
            "status",
            "archived_by",
            "archived_at",
            "updated_at",
        ]
    )

    return season