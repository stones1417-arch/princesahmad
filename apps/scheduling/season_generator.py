from datetime import timedelta

from django.db import transaction

from apps.scheduling.models import (
    ShiftPlan,
    ShiftType,
)


@transaction.atomic
def generate_season_shifts(
    season_template,
):
    """
    إنشاء جميع ورديات الموسم.
    """

    current_date = season_template.start_date

    while current_date <= season_template.end_date:

        for season_shift in (
            season_template.shift_times
            .filter(is_enabled=True)
            .select_related("shift_type")
        ):

            ShiftPlan.objects.get_or_create(
                date=current_date,
                shift_type=season_shift.shift_type,
                defaults={
                    "notes": (
                        f"وردية "
                        f"{season_template.get_season_type_display()}"
                    ),
                },
            )

        current_date += timedelta(days=1)