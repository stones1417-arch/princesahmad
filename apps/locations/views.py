from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from apps.core.permissions import require_staff
from apps.distribution.models import DoorAssignment
from apps.ops.models import DoorShift, MaintenanceRequest
from apps.scheduling.models import ShiftPlan

from .models import Door, Zone
from .services import LocationService, OFFICIAL_ZONES




def ensure_official_zones():
    for zone_name in OFFICIAL_ZONES:
        Zone.objects.get_or_create(
            name=zone_name,
            defaults={"notes": "منطقة رسمية"}
        )


@login_required
def locations_dashboard_view(request):
    require_staff(request.user)
    ensure_official_zones()

    q = (request.GET.get("q") or "").strip()
    zone_id = (request.GET.get("zone") or "").strip()
    active_filter = (request.GET.get("active") or "").strip()
    state_filter = (request.GET.get("state") or "").strip()

    q = (request.GET.get("q") or "").strip()
    zone_id = (request.GET.get("zone") or "").strip()
    active_filter = (request.GET.get("active") or "").strip()
    state_filter = (request.GET.get("state") or "").strip()

    doors = (
        Door.objects
        .select_related("zone")
        .filter(zone__name__in=OFFICIAL_ZONES)
    )

    if q:
        doors = doors.filter(
            Q(name__icontains=q)
            | Q(door_number__icontains=q)
            | Q(zone__name__icontains=q)
        )

    if zone_id.isdigit():
        doors = doors.filter(zone_id=int(zone_id))

    if active_filter == "active":
        doors = doors.filter(is_active=True)
    elif active_filter == "inactive":
        doors = doors.filter(is_active=False)

    doors = doors.order_by("zone__name", "door_number", "name")

    active_shift = (
        ShiftPlan.objects
        .select_related("shift_type")
        .filter(is_active=True)
        .first()
    )

    door_shift_map = {}
    assignment_stats = {}
    maintenance_stats = {}
    supervisor_stats = {}
    monitor_stats = {}
    technician_stats = {}

    if active_shift:
        door_shifts = DoorShift.objects.filter(
            shift_plan=active_shift,
            is_active=True,
        )

        if state_filter:
            door_shifts = door_shifts.filter(state=state_filter)

        for ds in door_shifts:
            door_shift_map[ds.door_number] = ds

        assignment_stats = {
            item["door_id"]: item["total"]
            for item in (
                DoorAssignment.objects
                .filter(shift_plan=active_shift, is_active=True)
                .values("door_id")
                .annotate(total=Count("id"))
            )
        }

        supervisor_stats = {
            item["door_id"]: item["total"]
            for item in (
                DoorAssignment.objects
                .filter(
                    shift_plan=active_shift,
                    is_active=True,
                    role=DoorAssignment.Role.SUPERVISOR,
                )
                .values("door_id")
                .annotate(total=Count("id"))
            )
        }

        monitor_stats = {
            item["door_id"]: item["total"]
            for item in (
                DoorAssignment.objects
                .filter(
                    shift_plan=active_shift,
                    is_active=True,
                    role=DoorAssignment.Role.MONITOR,
                )
                .values("door_id")
                .annotate(total=Count("id"))
            )
        }

        technician_stats = {
            item["door_id"]: item["total"]
            for item in (
                DoorAssignment.objects
                .filter(
                    shift_plan=active_shift,
                    is_active=True,
                    role=DoorAssignment.Role.TECHNICIAN,
                )
                .values("door_id")
                .annotate(total=Count("id"))
            )
        }

        maintenance_stats = {
            item["door_shift__door_number"]: item["total"]
            for item in (
                MaintenanceRequest.objects
                .filter(door_shift__shift_plan=active_shift)
                .exclude(
                    status__in=[
                        MaintenanceRequest.Status.CLOSED,
                        MaintenanceRequest.Status.DONE,
                        MaintenanceRequest.Status.FIXED,
                    ]
                )
                .values("door_shift__door_number")
                .annotate(total=Count("id"))
            )
        }

    door_rows = []
    grouped_by_zone = {zone_name: [] for zone_name in OFFICIAL_ZONES}

    open_doors = 0
    closed_doors = 0
    maintenance_doors = 0
    secured_doors = 0
    doors_without_staff = 0
    doors_without_supervisor = 0
    doors_without_monitor = 0
    maintenance_open_total = 0

    for door in doors:
        door_shift = door_shift_map.get(door.door_number)

        if state_filter and active_shift and not door_shift:
            continue

        assignments_count = assignment_stats.get(door.id, 0)
        supervisors_count = supervisor_stats.get(door.id, 0)
        monitors_count = monitor_stats.get(door.id, 0)
        technicians_count = technician_stats.get(door.id, 0)
        maintenance_count = maintenance_stats.get(door.door_number, 0)

        if assignments_count == 0:
            doors_without_staff += 1

        if supervisors_count == 0:
            doors_without_supervisor += 1

        if monitors_count == 0:
            doors_without_monitor += 1

        maintenance_open_total += maintenance_count

        if door_shift:
            if door_shift.state == DoorShift.DoorState.OPEN:
                open_doors += 1
            elif door_shift.state == DoorShift.DoorState.CLOSED:
                closed_doors += 1
            elif door_shift.state == DoorShift.DoorState.MAINTENANCE:
                maintenance_doors += 1
            elif door_shift.state == DoorShift.DoorState.SECURED:
                secured_doors += 1

        row = {
            "door": door,
            "door_shift": door_shift,
            "assignments_count": assignments_count,
            "supervisors_count": supervisors_count,
            "monitors_count": monitors_count,
            "technicians_count": technicians_count,
            "maintenance_count": maintenance_count,
            "has_alert": (
                assignments_count == 0
                or supervisors_count == 0
                or monitors_count == 0
                or maintenance_count > 0
                or (
                    door_shift
                    and door_shift.state in [
                        DoorShift.DoorState.CLOSED,
                        DoorShift.DoorState.MAINTENANCE,
                    ]
                )
            ),
        }

        door_rows.append(row)

        if door.zone and door.zone.name in grouped_by_zone:
            grouped_by_zone[door.zone.name].append(row)

    zones = (
        Zone.objects
        .filter(name__in=OFFICIAL_ZONES)
        .annotate(doors_count=Count("doors"))
        .order_by("name")
    )

    context = {
        "doors": door_rows,
        "grouped_by_zone": grouped_by_zone,
        "zones": zones,
        "active_shift": active_shift,
        "q": q,
        "selected_zone": zone_id,
        "selected_active": active_filter,
        "selected_state": state_filter,
        "state_choices": DoorShift.DoorState.choices,
        "total_doors": len(door_rows),
        "active_doors": Door.objects.filter(
            zone__name__in=OFFICIAL_ZONES,
            is_active=True,
        ).count(),
        "inactive_doors": Door.objects.filter(
            zone__name__in=OFFICIAL_ZONES,
            is_active=False,
        ).count(),
        "zones_count": Zone.objects.filter(name__in=OFFICIAL_ZONES).count(),
        "open_doors": open_doors,
        "closed_doors": closed_doors,
        "maintenance_doors": maintenance_doors,
        "secured_doors": secured_doors,
        "doors_without_staff": doors_without_staff,
        "doors_without_supervisor": doors_without_supervisor,
        "doors_without_monitor": doors_without_monitor,
        "maintenance_open_total": maintenance_open_total,
    }

    return render(
        request,
        "locations/dashboard.html",
        context,
    )


@login_required
@require_POST
def zone_create_view(request):
    _require_staff(request.user)

    try:
        LocationService.create_zone(
            request=request,
            name=request.POST.get("name"),
            notes=request.POST.get("notes"),
        )

        messages.success(request, "تم إضافة المنطقة بنجاح")

    except ValidationError as e:
        messages.error(
            request,
            e.messages[0] if hasattr(e, "messages") and e.messages else str(e),
        )

    return redirect("locations:dashboard")


@login_required
@require_POST
def zone_update_view(request, pk):
    _require_staff(request.user)

    zone = get_object_or_404(Zone, pk=pk)

    try:
        LocationService.update_zone(
            request=request,
            zone=zone,
            name=request.POST.get("name"),
            notes=request.POST.get("notes"),
        )

        messages.success(request, "تم تحديث المنطقة بنجاح")

    except ValidationError as e:
        messages.error(
            request,
            e.messages[0] if hasattr(e, "messages") and e.messages else str(e),
        )

    return redirect("locations:dashboard")


@login_required
@require_POST
def door_update_view(request, pk):
    _require_staff(request.user)

    door = get_object_or_404(Door, pk=pk)

    zone_id = (request.POST.get("zone_id") or "").strip()

    if not zone_id.isdigit():
        messages.error(request, "يجب اختيار المنطقة")
        return redirect("locations:dashboard")

    zone = get_object_or_404(
        Zone,
        pk=int(zone_id),
        name__in=OFFICIAL_ZONES,
    )

    try:
        LocationService.update_door(
            request=request,
            door=door,
            door_number=request.POST.get("door_number"),
            name=request.POST.get("name"),
            zone=zone,
            notes=request.POST.get("notes"),
        )

        messages.success(request, "تم تحديث بيانات الباب بنجاح")

    except ValidationError as e:
        messages.error(
            request,
            e.messages[0] if hasattr(e, "messages") and e.messages else str(e),
        )

    return redirect("locations:dashboard")


@login_required
@require_POST
def door_toggle_active_view(request, pk):
    _require_staff(request.user)

    door = get_object_or_404(
        Door,
        pk=pk,
        zone__name__in=OFFICIAL_ZONES,
    )

    was_active = door.is_active

    door = LocationService.toggle_door_active(
        request=request,
        door=door,
    )

    if was_active:
        messages.warning(request, f"تم تعطيل {door}")
    else:
        messages.success(request, f"تم تفعيل {door}")

    return redirect("locations:dashboard")