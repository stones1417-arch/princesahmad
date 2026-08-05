from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.breaks.models import Break
from apps.distribution.models import DoorAssignment
from apps.scheduling.models import ShiftAssignment


@transaction.atomic
def assign_employee_to_door(
    *,
    shift_plan,
    door,
    employee,
    assigned_by,
    role,
    is_supervisor: bool = False,
    notes: str = "",
) -> DoorAssignment:
    shift_plan = (
        type(shift_plan).objects
        .select_for_update()
        .get(pk=shift_plan.pk)
    )

    employee = (
        type(employee).objects
        .select_for_update()
        .get(pk=employee.pk)
    )

    if not employee.is_active:
        raise ValidationError(
            "لا يمكن تسكين موظف غير نشط."
        )

    if not getattr(employee, "can_work_on_doors", False):
        raise ValidationError(
            "الموظف لا يملك صلاحية العمل على الأبواب."
        )

    if _employee_is_on_break(
        employee=employee,
        shift_plan=shift_plan,
    ):
        raise ValidationError(
            "لا يمكن تسكين الموظف أثناء وقت راحته."
        )

    if _has_conflicting_shift(
        employee=employee,
        shift_plan=shift_plan,
    ):
        raise ValidationError(
            "الموظف مسكن في وردية أخرى متعارضة."
        )

    if DoorAssignment.objects.filter(
        shift_plan=shift_plan,
        door=door,
        employee=employee,
        is_active=True,
    ).exists():
        raise ValidationError(
            "الموظف موزع مسبقًا على هذا الباب."
        )

    if is_supervisor and DoorAssignment.objects.filter(
        shift_plan=shift_plan,
        door=door,
        is_supervisor=True,
        is_active=True,
    ).exists():
        raise ValidationError(
            "يوجد مشرف مسجل مسبقًا لهذا الباب."
        )

    return DoorAssignment.objects.create(
        shift_plan=shift_plan,
        door=door,
        employee=employee,
        role=role,
        is_supervisor=is_supervisor,
        notes=notes,
        is_active=True,
        assigned_by=assigned_by,
        assigned_at=timezone.now(),
    )
def _has_conflicting_shift(
    *,
    employee,
    shift_plan,
) -> bool:
    return (
        ShiftAssignment.objects
        .filter(
            employee=employee,
            shift_plan__date=shift_plan.date,
            shift_plan__start_time__lt=shift_plan.end_time,
            shift_plan__end_time__gt=shift_plan.start_time,
        )
        .exclude(shift_plan=shift_plan)
        .exists()
    )


def _employee_is_on_break(
    *,
    employee,
    shift_plan,
) -> bool:
    return Break.objects.filter(
        employee=employee,
        shift_type=shift_plan.shift_type,
        is_active=True,
    ).exists()
from django.db import models
from django.db.models import Q


class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=[
                "shift_plan",
                "door",
                "employee",
            ],
            condition=Q(is_active=True),
            name="unique_active_employee_per_door_shift",
        ),
        models.UniqueConstraint(
            fields=[
                "shift_plan",
                "door",
            ],
            condition=Q(
                is_active=True,
                is_supervisor=True,
            ),
            name="one_active_supervisor_per_door_shift",
        ),
    ]
    assigned_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    related_name="created_door_assignments",
    verbose_name="وزع بواسطة",
)

assigned_at = models.DateTimeField(
    auto_now_add=True,
    db_index=True,
    verbose_name="وقت التوزيع",
)