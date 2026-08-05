from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.hr.models import Employee
from apps.scheduling.models import ShiftPlan
from apps.ops.models import DoorShift, MaintenanceRequest
from apps.reporting.models import ShiftReport


@login_required
def dashboard_view(request):
    active_shift = (
        ShiftPlan.objects
        .select_related("shift_type")
        .filter(is_active=True)
        .first()
    )

    door_qs = DoorShift.objects.filter(
        shift_plan=active_shift,
        is_active=True
    ) if active_shift else DoorShift.objects.none()

    maintenance_qs = MaintenanceRequest.objects.all()

    context = {
        "active_shift": active_shift,

        "total_employees": Employee.objects.filter(is_active=True).count(),

        "total_doors": door_qs.count(),
        "open_doors": door_qs.filter(state=DoorShift.DoorState.OPEN).count(),
        "closed_doors": door_qs.filter(state=DoorShift.DoorState.CLOSED).count(),
        "maintenance_doors": door_qs.filter(state=DoorShift.DoorState.MAINTENANCE).count(),

        "maintenance_open": maintenance_qs.filter(status=MaintenanceRequest.Status.OPEN).count(),
        "maintenance_progress": maintenance_qs.filter(status=MaintenanceRequest.Status.IN_PROGRESS).count(),
        "maintenance_done": maintenance_qs.filter(status=MaintenanceRequest.Status.DONE).count(),

        "reports_count": ShiftReport.objects.count(),
        "approved_reports": ShiftReport.objects.filter(
            status=ShiftReport.ReportStatus.APPROVED
        ).count(),
    }

    return render(request, "dashboard/index.html", context)