from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.distribution.models import DoorAssignment
from apps.scheduling.models import ShiftPlan


@transaction.atomic
def copy_shift_distribution(
    *,
    source_shift: ShiftPlan,
    target_dates: Iterable[date],
    copied_by,
) -> int:
    source_shift = (
        ShiftPlan.objects
        .select_for_update()
        .get(pk=source_shift.pk)
    )

    source_assignments = list(
        DoorAssignment.objects
        .filter(
            shift_plan=source_shift,
            is_active=True,
        )
        .select_related(
            "door",
            "employee",
        )
    )

    if not source_assignments:
        raise ValidationError(
            "الوردية المصدر لا تحتوي على توزيع لنسخه."
        )

    copied_count = 0

    for target_date in target_dates:
        target_shift = ShiftPlan.objects.filter(
            season=source_shift.season,
            seasonal_template=source_shift.seasonal_template,
            date=target_date,
        ).first()

        if not target_shift:
            raise ValidationError(
                f"لا توجد وردية مستهدفة بتاريخ {target_date}."
            )

        if target_shift.is_finished:
            raise ValidationError(
                f"لا يمكن النسخ إلى وردية منتهية بتاريخ {target_date}."
            )

        for source in source_assignments:
            _, created = DoorAssignment.objects.get_or_create(
                shift_plan=target_shift,
                door=source.door,
                employee=source.employee,
                defaults={
                    "role": source.role,
                    "is_supervisor": source.is_supervisor,
                    "is_active": source.is_active,
                    "notes": source.notes,
                    "assigned_by": copied_by,
                },
            )

            if created:
                copied_count += 1

    return copied_count