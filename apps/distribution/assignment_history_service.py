from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction


def _serialize(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "pk"):
        return {
            "id": value.pk,
            "label": str(value),
        }

    if isinstance(value, dict):
        return {
            str(key): _serialize(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _serialize(item)
            for item in value
        ]

    return str(value)


def assignment_snapshot(assignment) -> dict[str, Any]:
    if assignment is None:
        return {}

    snapshot = {
        "assignment_id": assignment.pk,
    }

    fields = [
        "employee_id",
        "door_id",
        "shift_plan_id",
        "door_number",
        "role",
        "assignment_role",
        "is_supervisor",
        "is_active",
        "notes",
        "created_at",
        "updated_at",
        "assigned_at",
        "assigned_by_id",
    ]

    for field_name in fields:
        if hasattr(assignment, field_name):
            snapshot[field_name] = _serialize(
                getattr(assignment, field_name)
            )

    return snapshot


def resolve_assignment_relations(assignment):
    employee = getattr(
        assignment,
        "employee",
        None,
    )

    door = getattr(
        assignment,
        "door",
        None,
    )

    shift_plan = getattr(
        assignment,
        "shift_plan",
        None,
    )

    return employee, door, shift_plan


@transaction.atomic
def record_assignment_created(
    *,
    assignment,
    request=None,
    user=None,
    reason: str = "",
):
    from apps.audit.services import (
        record_assignment_history,
    )

    if assignment is None:
        raise ValidationError(
            "التوزيع غير موجود."
        )

    if not getattr(assignment, "pk", None):
        raise ValidationError(
            "يجب حفظ التوزيع قبل تسجيله تاريخيًا."
        )

    employee, door, shift_plan = (
        resolve_assignment_relations(
            assignment
        )
    )

    return record_assignment_history(
        assignment=assignment,
        employee=employee,
        door=door,
        shift_plan=shift_plan,
        old_value={},
        new_value=assignment_snapshot(
            assignment
        ),
        request=request,
        user=user,
        reason=str(
            reason or "إنشاء توزيع جديد"
        ).strip(),
    )


@transaction.atomic
def update_assignment_with_history(
    *,
    assignment,
    changes: dict[str, Any],
    request=None,
    user=None,
    reason: str = "",
):
    from apps.audit.services import (
        record_assignment_history,
    )
    from apps.distribution.models import (
        DoorAssignment,
    )

    if assignment is None:
        raise ValidationError(
            "التوزيع غير موجود."
        )

    locked_assignment = (
        DoorAssignment.objects
        .select_for_update()
        .get(pk=assignment.pk)
    )

    old_snapshot = assignment_snapshot(
        locked_assignment
    )

    valid_fields = {
        field.name
        for field in locked_assignment._meta.fields
    }

    changed_fields = []

    for field_name, value in changes.items():
        if field_name not in valid_fields:
            raise ValidationError(
                f"الحقل {field_name} غير موجود."
            )

        old_value = getattr(
            locked_assignment,
            field_name,
        )

        if getattr(old_value, "pk", old_value) == getattr(
            value,
            "pk",
            value,
        ):
            continue

        setattr(
            locked_assignment,
            field_name,
            value,
        )

        changed_fields.append(
            field_name
        )

    if not changed_fields:
        return locked_assignment, False

    locked_assignment.full_clean()

    locked_assignment.save(
        update_fields=changed_fields,
    )

    employee, door, shift_plan = (
        resolve_assignment_relations(
            locked_assignment
        )
    )

    record_assignment_history(
        assignment=locked_assignment,
        employee=employee,
        door=door,
        shift_plan=shift_plan,
        old_value=old_snapshot,
        new_value=assignment_snapshot(
            locked_assignment
        ),
        request=request,
        user=user,
        reason=str(
            reason or "تعديل توزيع موظف"
        ).strip(),
    )

    return locked_assignment, True


@transaction.atomic
def delete_assignment_with_history(
    *,
    assignment,
    request=None,
    user=None,
    reason: str = "",
):
    from apps.audit.services import (
        record_assignment_history,
    )
    from apps.distribution.models import (
        DoorAssignment,
    )

    if assignment is None:
        raise ValidationError(
            "التوزيع غير موجود."
        )

    locked_assignment = (
        DoorAssignment.objects
        .select_for_update()
        .get(pk=assignment.pk)
    )

    old_snapshot = assignment_snapshot(
        locked_assignment
    )

    employee, door, shift_plan = (
        resolve_assignment_relations(
            locked_assignment
        )
    )

    history = record_assignment_history(
        assignment=locked_assignment,
        employee=employee,
        door=door,
        shift_plan=shift_plan,
        old_value=old_snapshot,
        new_value={
            "deleted": True,
        },
        request=request,
        user=user,
        reason=str(
            reason or "حذف توزيع موظف"
        ).strip(),
    )

    assignment_id = locked_assignment.pk

    locked_assignment.delete()

    return {
        "deleted": True,
        "assignment_id": assignment_id,
        "history_id": history.pk,
    }