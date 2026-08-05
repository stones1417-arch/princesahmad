from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.db import transaction

from apps.audit.models import (
    AssignmentHistory,
    DoorStateHistory,
    IncidentStatusHistory,
    MaintenanceStatusHistory,
    ReportApprovalHistory,
    ShiftPlanHistory,
)
from apps.audit.utils import (
    get_client_ip,
    get_request_user,
)


def _prepare(value: dict[str, Any] | None):
    """
    تجهيز بيانات JSON قبل الحفظ.
    """

    if value is None:
        return {}

    return value


# ==========================================================
# Door State History
# ==========================================================

@transaction.atomic
def record_door_state_history(
    *,
    door_shift,
    old_value: dict,
    new_value: dict,
    request: HttpRequest | None = None,
    user=None,
    reason: str = "",
    ip_address: str | None = None,
):
    return DoorStateHistory.objects.create(
        door_shift=door_shift,
        old_value=_prepare(old_value),
        new_value=_prepare(new_value),
        changed_by=user or get_request_user(request),
        change_reason=reason,
        ip_address=ip_address or get_client_ip(request),
    )


# ==========================================================
# Assignment History
# ==========================================================

@transaction.atomic
def record_assignment_history(
    *,
    assignment=None,
    employee=None,
    door=None,
    shift_plan=None,
    old_value=None,
    new_value=None,
    request=None,
    user=None,
    reason="",
    ip_address=None,
):
    return AssignmentHistory.objects.create(
        assignment=assignment,
        employee=employee,
        door=door,
        shift_plan=shift_plan,
        old_value=_prepare(old_value),
        new_value=_prepare(new_value),
        changed_by=user or get_request_user(request),
        change_reason=reason,
        ip_address=ip_address or get_client_ip(request),
    )


# ==========================================================
# Maintenance History
# ==========================================================

@transaction.atomic
def record_maintenance_status_history(
    *,
    maintenance_request,
    old_value,
    new_value,
    request=None,
    user=None,
    reason="",
    ip_address=None,
):
    return MaintenanceStatusHistory.objects.create(
        maintenance_request=maintenance_request,
        old_value=_prepare(old_value),
        new_value=_prepare(new_value),
        changed_by=user or get_request_user(request),
        change_reason=reason,
        ip_address=ip_address or get_client_ip(request),
    )


# ==========================================================
# Incident History
# ==========================================================

@transaction.atomic
def record_incident_status_history(
    *,
    incident,
    old_value,
    new_value,
    request=None,
    user=None,
    reason="",
    ip_address=None,
):
    return IncidentStatusHistory.objects.create(
        incident=incident,
        old_value=_prepare(old_value),
        new_value=_prepare(new_value),
        changed_by=user or get_request_user(request),
        change_reason=reason,
        ip_address=ip_address or get_client_ip(request),
    )


# ==========================================================
# Shift History
# ==========================================================

@transaction.atomic
def record_shift_plan_history(
    *,
    shift_plan,
    action,
    old_value=None,
    new_value=None,
    request=None,
    user=None,
    reason="",
    ip_address=None,
):
    return ShiftPlanHistory.objects.create(
        shift_plan=shift_plan,
        action=action,
        old_value=_prepare(old_value),
        new_value=_prepare(new_value),
        changed_by=user or get_request_user(request),
        change_reason=reason,
        ip_address=ip_address or get_client_ip(request),
    )


# ==========================================================
# Report Approval History
# ==========================================================

@transaction.atomic
def record_report_approval_history(
    *,
    report,
    action,
    old_value=None,
    new_value=None,
    request=None,
    user=None,
    reason="",
    ip_address=None,
):
    return ReportApprovalHistory.objects.create(
        report=report,
        action=action,
        old_value=_prepare(old_value),
        new_value=_prepare(new_value),
        changed_by=user or get_request_user(request),
        change_reason=reason,
        ip_address=ip_address or get_client_ip(request),
    )