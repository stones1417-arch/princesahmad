from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.distribution.models import DoorAssignment
from apps.ops.models import Incident, MaintenanceRequest
from apps.scheduling.models import ShiftPlan


def get_shift_export_data(
    shift_plan_id: int,
) -> dict[str, Any]:
    """
    جلب بيانات الوردية المطلوبة للتصدير.
    """
    shift_plan = get_object_or_404(
        ShiftPlan.objects.select_related(
            "shift_type",
        ),
        pk=shift_plan_id,
    )

    distribution = (
        DoorAssignment.objects
        .filter(shift_plan=shift_plan)
        .select_related(
            "door",
            "employee",
            "shift_plan__shift_type",
        )
        .order_by(
            "door__door_number",
            "employee__employee_number",
        )
    )

    maintenance = (
        MaintenanceRequest.objects
        .filter(
            door_shift__shift_plan=shift_plan,
        )
        .select_related(
            "door_shift",
            "door_shift__shift_plan",
            "technician",
            "created_by",
        )
        .order_by("-created_at")
    )

    incidents = (
        Incident.objects
        .filter(
            Q(shift_plan=shift_plan)
            | Q(door_shift__shift_plan=shift_plan)
        )
        .distinct()
        .select_related(
            "shift_plan",
            "door_shift",
            "created_by",
            "closed_by",
        )
        .order_by("-created_at")
    )

    return {
        "shift_plan": shift_plan,
        "distribution": distribution,
        "maintenance": maintenance,
        "incidents": incidents,
    }


def get_shift_records_count(
    data: dict[str, Any],
    section: str,
) -> int:
    """
    حساب عدد السجلات حسب القسم الذي تم تصديره.
    """
    if section == "distribution":
        return data["distribution"].count()

    if section == "maintenance":
        return data["maintenance"].count()

    if section == "incidents":
        return data["incidents"].count()

    return (
        data["distribution"].count()
        + data["maintenance"].count()
        + data["incidents"].count()
    )