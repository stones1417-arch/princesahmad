from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any, Iterable

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from apps.audit.models import DoorStateHistory
from apps.distribution.models import DoorAssignment
from apps.hr.models import Employee
from apps.locations.door_directions import get_official_door_direction
from apps.locations.models import Door
from apps.ops.models import DoorCurrentState, DoorShift, Incident, MaintenanceRequest
from apps.reporting.models import ShiftReport
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.scheduling.models import ShiftPlan


CLOSED_MAINTENANCE_STATUSES = {"done", "closed", "fixed", "completed", "resolved"}
PENDING_REPORT_STATUSES = {"draft", "final", "pending", "submitted"}


def _model_has_field(model: type, field_name: str) -> bool:
    return any(field.name == field_name for field in model._meta.get_fields())


def _first_existing_field(model: type, names: Iterable[str]) -> str | None:
    for name in names:
        if _model_has_field(model, name):
            return name
    return None


def _percentage(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100, 1)


def _display_user_name(user: Any) -> str:
    if not user:
        return "غير محدد"

    get_full_name = getattr(user, "get_full_name", None)
    if callable(get_full_name):
        full_name = (get_full_name() or "").strip()
        if full_name:
            return full_name

    employee = getattr(user, "employee", None)
    employee_name = getattr(employee, "full_name", "")
    if employee_name:
        return employee_name

    return (
        getattr(user, "full_name", "")
        or getattr(user, "username", "")
        or str(user)
    )


def _get_shift_time(shift: ShiftPlan | None, kind: str):
    if not shift:
        return None

    effective_name = f"effective_{kind}_time"
    effective_value = getattr(shift, effective_name, None)
    if callable(effective_value):
        effective_value = effective_value()

    if effective_value:
        return effective_value

    direct_value = getattr(shift, f"{kind}_time", None)
    if direct_value:
        return direct_value

    shift_type = getattr(shift, "shift_type", None)
    return getattr(shift_type, f"{kind}_time", None)


def _get_direction(door_number: Any) -> tuple[str, str]:
    """Return the official direction using the central mapping helper."""
    try:
        direction = get_official_door_direction(door_number)
    except Exception:
        return "unknown", "غير محدد"

    labels = {
        "south": "الجهة الجنوبية",
        "west": "الجهة الغربية",
        "north": "الجهة الشمالية",
        "east": "الجهة الشرقية",
        "southeast": "الجهة الجنوبية الشرقية",
    }
    return direction, labels.get(direction, "غير محدد")


def _find_door_by_number(door_number: Any) -> Door | None:
    filters = {"is_active": True}

    if _model_has_field(Door, "door_number"):
        filters["door_number"] = door_number
    elif _model_has_field(Door, "number"):
        filters["number"] = door_number
    else:
        return None

    return Door.objects.filter(**filters).first()


def _get_employee_active_filter() -> dict[str, bool]:
    if _model_has_field(Employee, "is_active"):
        return {"is_active": True}
    return {}


def _get_assignment_created_field() -> str | None:
    return _first_existing_field(
        DoorAssignment,
        ("created_at", "assigned_at", "created_on"),
    )


def _get_maintenance_closed_field() -> str | None:
    return _first_existing_field(
        MaintenanceRequest,
        ("completed_at", "resolved_at", "closed_at", "fixed_at"),
    )


def _get_average_duration_minutes(queryset, end_field: str | None) -> float | None:
    if not end_field or not _model_has_field(queryset.model, "created_at"):
        return None

    filtered = queryset.exclude(**{f"{end_field}__isnull": True})

    duration_expression = ExpressionWrapper(
        F(end_field) - F("created_at"),
        output_field=DurationField(),
    )

    value = filtered.aggregate(
        average_duration=Avg(duration_expression)
    )["average_duration"]

    if not value:
        return None

    return round(value.total_seconds() / 60, 1)


def _build_section_dashboard_metrics(
    *,
    active_shift,
    all_doors: list[dict[str, Any]],
    all_assignments,
) -> dict[str, dict[str, int]]:
    """Build comparable institution, male, female, and shared metrics."""
    open_incident_statuses = [
        Incident.Status.NEW,
        Incident.Status.IN_PROGRESS,
        Incident.Status.FORWARDED,
    ]

    active_employees = Employee.objects.filter(
        **_get_employee_active_filter()
    )
    active_incidents = Incident.objects.filter(
        status__in=open_incident_statuses
    )
    active_maintenance = MaintenanceRequest.objects.exclude(
        status__in=CLOSED_MAINTENANCE_STATUSES
    )

    section_definitions = {
        "male": "male",
        "female": "female",
    }
    metrics: dict[str, dict[str, int]] = {}

    for key, employee_section in section_definitions.items():
        section_doors = [
            door
            for door in all_doors
            if getattr(
                door.get("door_obj"),
                "operational_section",
                "",
            ) in {key, Door.OperationalSection.SHARED}
        ]
        section_assignments = all_assignments.filter(section=key)
        metrics[key] = {
            "employees": active_employees.filter(
                operational_section=employee_section
            ).count(),
            "supervisors": section_assignments.filter(
                role=DoorAssignment.Role.SUPERVISOR
            ).count(),
            "active_assignments": section_assignments.count(),
            "available_doors": sum(
                door["state"] in {
                    DoorShift.DoorState.OPEN,
                    DoorShift.DoorState.SECURED,
                }
                for door in section_doors
            ),
            "open_incidents": active_incidents.filter(
                section=key
            ).count(),
            "open_maintenance": active_maintenance.filter(
                section=key
            ).count(),
            "total_doors": len(section_doors),
        }

    shared_doors = [
        door
        for door in all_doors
        if getattr(
            door.get("door_obj"),
            "operational_section",
            "",
        ) == Door.OperationalSection.SHARED
    ]
    metrics["shared"] = {
        "total_doors": len(shared_doors),
        "available_doors": sum(
            door["state"] in {
                DoorShift.DoorState.OPEN,
                DoorShift.DoorState.SECURED,
            }
            for door in shared_doors
        ),
        "active_assignments": all_assignments.filter(
            door__operational_section=Door.OperationalSection.SHARED
        ).count(),
        "supervisors": all_assignments.filter(
            door__operational_section=Door.OperationalSection.SHARED,
            role=DoorAssignment.Role.SUPERVISOR,
        ).count(),
    }

    metrics["all"] = {
        "employees": active_employees.count(),
        "supervisors": all_assignments.filter(
            role=DoorAssignment.Role.SUPERVISOR
        ).count(),
        "active_assignments": all_assignments.count(),
        "available_doors": sum(
            door["state"] in {
                DoorShift.DoorState.OPEN,
                DoorShift.DoorState.SECURED,
            }
            for door in all_doors
        ),
        "open_incidents": active_incidents.count(),
        "open_maintenance": active_maintenance.count(),
        "total_doors": len(all_doors),
    }

    return metrics


def _get_optional_incident_metrics(today):
    """
    يحاول قراءة نموذج البلاغات عند وجوده دون تعطيل لوحة التحكم إذا لم يكن التطبيق موجودًا.
    """
    result = {
        "high_priority_count": 0,
        "average_resolution_minutes": None,
    }

    queryset = Incident.objects.all()

    priority_field = _first_existing_field(
        Incident,
        ("priority", "severity", "level"),
    )
    status_field = _first_existing_field(
        Incident,
        ("status", "state"),
    )

    high_values = ("high", "urgent", "critical", "عالي", "عاجل", "حرج")
    open_values = ("open", "new", "pending", "in_progress")

    if priority_field:
        high_query = Q(**{f"{priority_field}__in": high_values})

        if status_field:
            high_query &= Q(**{f"{status_field}__in": open_values})

        result["high_priority_count"] = queryset.filter(high_query).count()

    end_field = _first_existing_field(
        Incident,
        ("resolved_at", "closed_at", "completed_at"),
    )
    result["average_resolution_minutes"] = _get_average_duration_minutes(
        queryset,
        end_field,
    )

    return result


def _get_break_conflicts(active_shift, now):
    """
    يحاول اكتشاف الموظفين الموجودين في راحة ولديهم تسكين فعال.
    """
    try:
        from apps.breaks.models import Break
    except (ImportError, ModuleNotFoundError):
        return []

    break_queryset = Break.objects.all()

    if _model_has_field(Break, "start_time"):
        break_queryset = break_queryset.filter(start_time__lte=now)

    if _model_has_field(Break, "end_time"):
        break_queryset = break_queryset.filter(end_time__gte=now)

    if not _model_has_field(Break, "assignment"):
        return []

    break_queryset = break_queryset.select_related(
        "assignment",
        "assignment__employee",
        "assignment__door",
    )

    if active_shift:
        break_queryset = break_queryset.filter(
            assignment__shift_plan=active_shift,
            assignment__is_active=True,
        )

    return list(break_queryset[:20])


def build_dashboard_context(request):
    now = timezone.localtime()
    today = timezone.localdate()
    late_threshold = now - timedelta(hours=24)

    active_shift = (
        ShiftPlan.objects
        .select_related("shift_type")
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    sections = {
        "south": "الجهة الجنوبية",
        "west": "الجهة الغربية",
        "north": "الجهة الشمالية",
        "east": "الجهة الشرقية",
        "southeast": "الجهة الجنوب شرقي",
        "unknown": "غير محدد",
    }

    grouped_doors = {key: [] for key in sections}
    direction_summary = {
        key: {
            "key": key,
            "label": label,
            "total": 0,
            "open": 0,
            "closed": 0,
            "maintenance": 0,
            "secured": 0,
            "unassigned": 0,
        }
        for key, label in sections.items()
    }

    shift_leaders = {
        "shift_heads": [],
        "shift_deputies": [],
        "supervisors": [],
        "monitors": [],
        "technicians": [],
        "admins": [],
        "senior_admins": [],
        "support": [],
        "total_on_duty": 0,
    }

    all_assignments = DoorAssignment.objects.none()
    door_shifts = DoorShift.objects.none()

    duplicate_employee_rows = []
    inactive_assignments = []
    doors_without_supervisor = []
    doors_without_monitors = []
    unassigned_doors = []

    assigned_employee_ids: set[int] = set()
    assigned_door_ids: set[int] = set()

    current_states_by_number = {
        item.door.door_number: item
        for item in (
            DoorCurrentState.objects
            .select_related(
                "door",
                "current_shift",
                "updated_by",
            )
            .filter(door__is_active=True)
        )
    }

    if active_shift:
        all_assignments = (
            DoorAssignment.objects
            .filter(shift_plan=active_shift, is_active=True)
            .select_related("employee", "door")
            .order_by("role", "employee__employee_number")
        )

        shift_leaders["total_on_duty"] = all_assignments.count()

        shift_leaders["supervisors"] = list(
            all_assignments.filter(role=DoorAssignment.Role.SUPERVISOR)
        )
        shift_leaders["monitors"] = list(
            all_assignments.filter(role=DoorAssignment.Role.MONITOR)
        )
        shift_leaders["technicians"] = list(
            all_assignments.filter(role=DoorAssignment.Role.TECHNICIAN)
        )

        if hasattr(DoorAssignment.Role, "SUPPORT"):
            shift_leaders["support"] = list(
                all_assignments.filter(role=DoorAssignment.Role.SUPPORT)
            )

        shift_leaders["shift_heads"] = list(
            all_assignments.filter(
                employee__job_title__in=[
                    "fajr_supervisor",
                    "duha_supervisor",
                    "evening_supervisor",
                    "support_supervisor",
                ]
            )
        )
        shift_leaders["shift_deputies"] = list(
            all_assignments.filter(
                employee__job_title__in=[
                    "fajr_deputy",
                    "duha_deputy",
                    "evening_deputy",
                ]
            )
        )
        shift_leaders["senior_admins"] = list(
            all_assignments.filter(employee__job_title="senior_admin")
        )
        shift_leaders["admins"] = list(
            all_assignments.filter(
                employee__job_title__in=[
                    "admin_secretary",
                    "tech_secretary",
                ]
            )
        )

        assigned_employee_ids = set(
            all_assignments.values_list("employee_id", flat=True)
        )
        assigned_door_ids = set(
            all_assignments.exclude(door_id__isnull=True)
            .values_list("door_id", flat=True)
        )

        duplicate_employee_rows = list(
            all_assignments
            .values(
                "employee_id",
                "employee__full_name",
                "employee__employee_number",
            )
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .order_by("-total", "employee__full_name")[:20]
        )

        if _model_has_field(Employee, "is_active"):
            inactive_assignments = list(
                all_assignments
                .filter(employee__is_active=False)
                .select_related("employee", "door")[:20]
            )

        shift_doors_by_number = {
            item.door_number: item
            for item in (
            DoorShift.objects
            .filter(shift_plan=active_shift, is_active=True)
            .select_related(
                "supervisor",
                "shift_plan",
                "shift_plan__shift_type",
            )
            )
        }
        master_doors = list(Door.objects.filter(is_active=True).order_by("sort_order"))
        door_shifts = [
            shift_doors_by_number[door.door_number]
            for door in master_doors
            if door.door_number in shift_doors_by_number
        ]

        doors_by_number = {door.door_number: door for door in master_doors}
        assignments_by_door = defaultdict(list)
        for assignment in all_assignments:
            assignments_by_door[assignment.door_id].append(assignment)

        for door_shift in door_shifts:
            direction_key, direction_label = _get_direction(
                door_shift.door_number
            )
            door_obj = doors_by_number.get(door_shift.door_number)

            supervisor = None
            monitors = []
            technicians = []
            support_members = []
            assignments_count = 0

            if door_obj:
                assignments = sorted(
                    assignments_by_door.get(door_obj.pk, []),
                    key=lambda assignment: (
                        not assignment.is_supervisor,
                        assignment.role,
                        assignment.employee.employee_number,
                    ),
                )

                assignments_count = len(assignments)

                supervisor_assignment = next(
                    (
                        assignment
                        for assignment in assignments
                        if assignment.role == DoorAssignment.Role.SUPERVISOR
                    ),
                    None,
                )

                if not supervisor_assignment:
                    supervisor_assignment = next(
                        (
                            assignment
                            for assignment in assignments
                            if assignment.is_supervisor
                        ),
                        None,
                    )

                if supervisor_assignment:
                    supervisor = supervisor_assignment.employee

                monitors = [
                    assignment
                    for assignment in assignments
                    if assignment.role == DoorAssignment.Role.MONITOR
                ]
                technicians = [
                    assignment
                    for assignment in assignments
                    if assignment.role == DoorAssignment.Role.TECHNICIAN
                ]

                if hasattr(DoorAssignment.Role, "SUPPORT"):
                    support_members = [
                        assignment
                        for assignment in assignments
                        if assignment.role == DoorAssignment.Role.SUPPORT
                    ]

            if not supervisor and door_shift.supervisor:
                supervisor = door_shift.supervisor

            current_state = current_states_by_number.get(
                door_shift.door_number
            )
            effective_state = (
                current_state.state
                if current_state
                else door_shift.state
            )
            effective_state_label = (
                current_state.get_state_display()
                if current_state
                else door_shift.get_state_display()
            )
            effective_notes = (
                current_state.notes
                if current_state
                else door_shift.notes
            )

            door_data = {
                "id": door_shift.id,
                "door_number": door_shift.door_number,
                "state": effective_state,
                "state_label": effective_state_label,
                "direction_key": direction_key,
                "direction_label": direction_label,
                "notes": effective_notes,
                "current_state": current_state,
                "door_obj": door_obj,
                "supervisor": supervisor,
                "monitors": monitors,
                "technicians": technicians,
                "support_members": support_members,
                "assignments_count": assignments_count,
                "is_unassigned": assignments_count == 0,
            }

            if not supervisor:
                doors_without_supervisor.append(door_data)

            if not monitors:
                doors_without_monitors.append(door_data)

            if assignments_count == 0:
                unassigned_doors.append(door_data)

            grouped_doors[direction_key].append(door_data)

            direction_summary[direction_key]["total"] += 1
            direction_summary[direction_key][effective_state] = (
                direction_summary[direction_key].get(effective_state, 0) + 1
            )
            if assignments_count == 0:
                direction_summary[direction_key]["unassigned"] += 1

    all_doors = [
        door
        for direction_doors in grouped_doors.values()
        for door in direction_doors
    ]

    section_dashboard_metrics = (
        _build_section_dashboard_metrics(
            active_shift=active_shift,
            all_doors=all_doors,
            all_assignments=all_assignments,
        )
    )

    open_doors_count = sum(
        door["state"] == DoorShift.DoorState.OPEN
        for door in all_doors
    )
    closed_doors_count = sum(
        door["state"] == DoorShift.DoorState.CLOSED
        for door in all_doors
    )
    maintenance_doors_count = sum(
        door["state"] == DoorShift.DoorState.MAINTENANCE
        for door in all_doors
    )
    secured_doors_count = sum(
        door["state"] == DoorShift.DoorState.SECURED
        for door in all_doors
    )

    maintenance_queryset = MaintenanceRequest.objects.all()
    open_maintenance = maintenance_queryset.exclude(
        status__in=CLOSED_MAINTENANCE_STATUSES
    )
    late_maintenance = open_maintenance.filter(created_at__lt=late_threshold)
    urgent_maintenance = open_maintenance.filter(
        priority__in=["urgent", "high", "critical"]
    )

    latest_maintenance = (
        maintenance_queryset
        .select_related("door_shift", "created_by")
        .order_by("-created_at")[:6]
    )

    report_status_field = (
        "status" if _model_has_field(ShiftReport, "status") else None
    )
    if report_status_field:
        pending_reports = ShiftReport.objects.filter(
            status__in=PENDING_REPORT_STATUSES
        )
    else:
        pending_reports = ShiftReport.objects.none()

    active_employee_count = Employee.objects.filter(
        **_get_employee_active_filter()
    ).count()
    assigned_unique_employee_count = len(assigned_employee_ids)

    break_conflicts = _get_break_conflicts(active_shift, now)
    incident_metrics = _get_optional_incident_metrics(today)

    total_operational_doors = len(all_doors)
    ready_doors_count = open_doors_count + secured_doors_count
    assigned_door_count = sum(
        door["assignments_count"] > 0
        for door in all_doors
    )

    door_readiness_percentage = _percentage(
        ready_doors_count,
        total_operational_doors,
    )
    distribution_completion_percentage = _percentage(
        assigned_door_count,
        total_operational_doors,
    )
    attendance_percentage = _percentage(
        assigned_unique_employee_count,
        active_employee_count,
    )

    maintenance_closed_field = _get_maintenance_closed_field()
    average_maintenance_minutes = _get_average_duration_minutes(
        maintenance_queryset,
        maintenance_closed_field,
    )

    today_operations = DoorStateHistory.objects.filter(
        changed_at__date=today
    ).count()

    if _model_has_field(MaintenanceRequest, "created_at"):
        today_operations += maintenance_queryset.filter(
            created_at__date=today
        ).count()

    assignment_created_field = _get_assignment_created_field()
    if assignment_created_field:
        today_operations += DoorAssignment.objects.filter(
            **{f"{assignment_created_field}__date": today}
        ).count()

    shift_start_time = _get_shift_time(active_shift, "start")
    shift_end_time = _get_shift_time(active_shift, "end")

    shift_supervisor_name = "غير محدد"
    if active_shift:
        shift_supervisor_name = _display_user_name(
            getattr(active_shift, "supervisor", None)
        )

        if shift_supervisor_name == "غير محدد" and shift_leaders["shift_heads"]:
            shift_supervisor_name = (
                shift_leaders["shift_heads"][0].employee.full_name
            )
        elif (
            shift_supervisor_name == "غير محدد"
            and shift_leaders["supervisors"]
        ):
            shift_supervisor_name = (
                shift_leaders["supervisors"][0].employee.full_name
            )

    shift_without_distribution = bool(
        active_shift and not all_assignments.exists()
    )

    alerts = [
        {
            "key": "doors_without_supervisor",
            "title": "أبواب بلا مشرف",
            "description": "أبواب تشغيلية لا يوجد لها مشرف مسند.",
            "count": len(doors_without_supervisor),
            "level": "danger",
            "icon": "⚠",
        },
        {
            "key": "duplicate_employees",
            "title": "موظفون مكررون",
            "description": "موظفون ظهروا في أكثر من تسكين خلال الوردية.",
            "count": len(duplicate_employee_rows),
            "level": "warning",
            "icon": "⧉",
        },
        {
            "key": "late_maintenance",
            "title": "طلبات صيانة متأخرة",
            "description": "طلبات مفتوحة تجاوزت 24 ساعة دون إغلاق.",
            "count": late_maintenance.count(),
            "level": "danger",
            "icon": "🛠",
        },
        {
            "key": "high_priority_incidents",
            "title": "بلاغات عالية الأولوية",
            "description": "بلاغات أو طلبات عاجلة تحتاج تدخلًا مباشرًا.",
            "count": (
                incident_metrics["high_priority_count"]
                or urgent_maintenance.count()
            ),
            "level": "danger",
            "icon": "!",
        },
        {
            "key": "shift_without_distribution",
            "title": "وردية بلا توزيع",
            "description": "الوردية النشطة لا تحتوي على تسكين موظفين.",
            "count": 1 if shift_without_distribution else 0,
            "level": "warning",
            "icon": "◷",
        },
        {
            "key": "pending_reports",
            "title": "تقارير لم تعتمد",
            "description": "تقارير ما زالت في حالة مسودة أو انتظار اعتماد.",
            "count": pending_reports.count(),
            "level": "warning",
            "icon": "▤",
        },
        {
            "key": "break_conflicts",
            "title": "موظفون في راحة وتم تسكينهم",
            "description": "تعارض بين فترة الراحة والتوزيع التشغيلي.",
            "count": len(break_conflicts),
            "level": "danger",
            "icon": "☕",
        },
        {
            "key": "inactive_assignments",
            "title": "تسكين موظفين غير نشطين",
            "description": "توجد تكليفات مرتبطة بموظفين غير نشطين.",
            "count": len(inactive_assignments),
            "level": "danger",
            "icon": "⊘",
        },
    ]

    critical_alerts_count = sum(
        alert["count"]
        for alert in alerts
        if alert["level"] == "danger"
    )
    warning_alerts_count = sum(
        alert["count"]
        for alert in alerts
        if alert["level"] == "warning"
    )

    if not active_shift:
        operational_status = {
            "key": "inactive",
            "label": "لا توجد وردية نشطة",
            "description": "فعّل وردية من صفحة إدارة الورديات.",
        }
    elif critical_alerts_count:
        operational_status = {
            "key": "critical",
            "label": "تحتاج تدخلًا",
            "description": "توجد تنبيهات حرجة تتطلب المعالجة.",
        }
    elif warning_alerts_count:
        operational_status = {
            "key": "warning",
            "label": "مستقرة مع تنبيهات",
            "description": "التشغيل مستقر مع وجود نقاط تحتاج متابعة.",
        }
    else:
        operational_status = {
            "key": "stable",
            "label": "مستقرة",
            "description": "جميع المؤشرات التشغيلية ضمن الوضع الطبيعي.",
        }

    latest_logs = (
        DoorStateHistory.objects
        .select_related(
            "door_shift",
            "door_shift__shift_plan",
            "changed_by",
        )
        .order_by("-changed_at")[:8]
    )

    context = {
        "active_shift": active_shift,
        "selected_operational_section": str(
            request.GET.get("section", "all") or "all"
        ).strip().lower()
        if str(
            request.GET.get("section", "all") or "all"
        ).strip().lower() in {"all", "male", "female"}
        else "all",
        "shift_start_time": shift_start_time,
        "shift_end_time": shift_end_time,
        "shift_supervisor_name": shift_supervisor_name,
        "operational_status": operational_status,
        "sections": sections,
        "grouped_doors": grouped_doors,
        "direction_summary": list(direction_summary.values()),
        "section_dashboard_metrics": section_dashboard_metrics,
        "shift_leaders": shift_leaders,

        "open_doors_count": open_doors_count,
        "closed_doors_count": closed_doors_count,
        "maintenance_doors_count": maintenance_doors_count,
        "secured_doors_count": secured_doors_count,
        "unassigned_doors_count": len(unassigned_doors),
        "total_doors": total_operational_doors,

        "assigned_unique_employee_count": assigned_unique_employee_count,
        "total_employees": active_employee_count,

        "doors_without_supervisor": doors_without_supervisor[:10],
        "doors_without_monitors": doors_without_monitors[:10],
        "duplicate_employee_rows": duplicate_employee_rows,
        "inactive_assignments": inactive_assignments,
        "break_conflicts": break_conflicts,
        "unassigned_doors": unassigned_doors[:10],

        "maintenance_open": open_maintenance.count(),
        "maintenance_urgent": urgent_maintenance.count(),
        "late_maintenance_count": late_maintenance.count(),
        "latest_maintenance": latest_maintenance,

        "pending_reports_count": pending_reports.count(),
        "reports_count": ShiftReport.objects.count(),

        "alerts": alerts,
        "critical_alerts_count": critical_alerts_count,
        "warning_alerts_count": warning_alerts_count,

        "door_readiness_percentage": door_readiness_percentage,
        "distribution_completion_percentage": distribution_completion_percentage,
        "attendance_percentage": attendance_percentage,
        "average_incident_minutes": incident_metrics[
            "average_resolution_minutes"
        ],
        "average_maintenance_minutes": average_maintenance_minutes,
        "today_operations": today_operations,

        "latest_logs": latest_logs,
        "dashboard_generated_at": now,
        "can_create_maintenance": user_has_permission(
            request.user, PlatformPermissions.CREATE_MAINTENANCE_REQUEST
        ),
        "open_incidents_count": Incident.objects.filter(
            status__in=[
                Incident.Status.NEW,
                Incident.Status.IN_PROGRESS,
                Incident.Status.FORWARDED,
            ]
        ).count(),
        "critical_incidents_count": Incident.objects.filter(
            priority=Incident.Priority.CRITICAL,
        ).exclude(status=Incident.Status.CLOSED).count(),
        "upcoming_shifts": ShiftPlan.objects.select_related(
            "shift_type", "season"
        ).filter(
            date__gte=today,
            is_finished=False,
        ).exclude(pk=getattr(active_shift, "pk", None)).order_by(
            "date", "start_time"
        )[:4],
        "latest_reports": ShiftReport.objects.select_related(
            "shift_plan", "shift_plan__shift_type"
        ).order_by("-created_at")[:4],
    }

    return context


@login_required
def dashboard_view(request):
    return render(
        request,
        "dashboard/index.html",
        build_dashboard_context(request),
    )


@login_required
def audit_logs_view(request):
    """
    عرض سجل تغييرات حالات الأبواب من سجل التدقيق الموحد،
    مع البحث والتصفية حسب الحالة والمستخدم والوردية والتاريخ،
    وترقيم الصفحات.
    """
    today = timezone.localdate()

    base_logs = (
        DoorStateHistory.objects
        .select_related(
            "door_shift",
            "door_shift__shift_plan",
            "door_shift__shift_plan__shift_type",
            "changed_by",
        )
        .order_by("-changed_at")
    )

    # الإحصائيات العامة تبقى مبنية على كامل السجل، لا على الصفحة الحالية.
    logs_count = base_logs.count()
    today_changes = base_logs.filter(changed_at__date=today).count()

    most_changed_door = (
        base_logs
        .values("door_shift__door_number")
        .annotate(total=Count("id"))
        .order_by("-total", "door_shift__door_number")
        .first()
    )

    top_changed_by = (
        base_logs
        .exclude(changed_by__isnull=True)
        .values(
            "changed_by_id",
            "changed_by__username",
            "changed_by__first_name",
            "changed_by__last_name",
        )
        .annotate(total=Count("id"))
        .order_by("-total", "changed_by__username")
        .first()
    )

    log_users = (
        base_logs
        .exclude(changed_by__isnull=True)
        .values(
            "changed_by_id",
            "changed_by__username",
            "changed_by__first_name",
            "changed_by__last_name",
        )
        .distinct()
        .order_by(
            "changed_by__first_name",
            "changed_by__last_name",
            "changed_by__username",
        )
    )

    shift_ids = (
        base_logs
        .exclude(door_shift__shift_plan_id__isnull=True)
        .values_list("door_shift__shift_plan_id", flat=True)
        .distinct()
    )
    log_shifts = (
        ShiftPlan.objects
        .filter(id__in=shift_ids)
        .select_related("shift_type")
        .order_by("-id")
    )

    search_query = request.GET.get("q", "").strip()
    state_filter = request.GET.get("state", "all").strip().lower()
    user_filter = request.GET.get("user", "all").strip()
    shift_filter = request.GET.get("shift", "all").strip()
    date_from_value = request.GET.get("date_from", "").strip()
    date_to_value = request.GET.get("date_to", "").strip()

    filtered_logs = base_logs

    if search_query:
        filtered_logs = filtered_logs.filter(
            Q(change_reason__icontains=search_query)
            | Q(ip_address__icontains=search_query)
            | Q(changed_by__username__icontains=search_query)
            | Q(changed_by__first_name__icontains=search_query)
            | Q(changed_by__last_name__icontains=search_query)
            | Q(door_shift__door_number__icontains=search_query)
        )

    valid_states = {"open", "closed", "maintenance", "secured"}
    if state_filter in valid_states:
        filtered_logs = filtered_logs.filter(new_value__state=state_filter)

    if user_filter != "all" and user_filter.isdigit():
        filtered_logs = filtered_logs.filter(changed_by_id=int(user_filter))

    if shift_filter != "all" and shift_filter.isdigit():
        filtered_logs = filtered_logs.filter(
            door_shift__shift_plan_id=int(shift_filter)
        )

    date_from = parse_date(date_from_value) if date_from_value else None
    date_to = parse_date(date_to_value) if date_to_value else None

    if date_from:
        filtered_logs = filtered_logs.filter(changed_at__date__gte=date_from)

    if date_to:
        filtered_logs = filtered_logs.filter(changed_at__date__lte=date_to)

    filtered_count = filtered_logs.count()
    paginator = Paginator(filtered_logs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    query_params = request.GET.copy()
    query_params.pop("page", None)

    context = {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "logs_count": logs_count,
        "filtered_count": filtered_count,
        "today_changes": today_changes,
        "most_changed_door": most_changed_door,
        "top_changed_by": top_changed_by,
        "log_users": log_users,
        "log_shifts": log_shifts,
        "search_query": search_query,
        "state_filter": state_filter,
        "user_filter": user_filter,
        "shift_filter": shift_filter,
        "date_from_value": date_from_value,
        "date_to_value": date_to_value,
        "query_string": query_params.urlencode(),
    }

    return render(request, "dashboard/audit_logs.html", context)
