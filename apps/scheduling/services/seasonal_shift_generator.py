from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.scheduling.models import (
    Season,
    ShiftPlan,
)


@transaction.atomic
def generate_season_shifts(
    *,
    season: Season,
    created_by,
) -> list[ShiftPlan]:
    season = (
        Season.objects
        .select_for_update()
        .prefetch_related("shift_templates")
        .get(pk=season.pk)
    )

    if season.status == Season.SeasonStatus.ARCHIVED:
        raise ValidationError(
            "لا يمكن إنشاء ورديات لموسم مؤرشف."
        )

    templates = list(
        season.shift_templates.filter(
            is_active=True,
        )
    )

    if not templates:
        raise ValidationError(
            "يجب إضافة وقت وردية موسمية واحدة على الأقل."
        )

    created_shifts: list[ShiftPlan] = []
    current_date = season.start_date

    while current_date <= season.end_date:
        for template in templates:
            shift, created = ShiftPlan.objects.get_or_create(
                season=season,
                seasonal_template=template,
                date=current_date,
                defaults={
                    "shift_type": None,
                    "start_time": template.start_time,
                    "end_time": template.end_time,
                    "created_by": created_by,
                    "is_active": False,
                    "is_finished": False,
                },
            )

            if created:
                created_shifts.append(shift)

        current_date += timedelta(days=1)

    return created_shifts