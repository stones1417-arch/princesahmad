from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from apps.distribution.models import DoorAssignment
from apps.locations.models import Door
from apps.ops.models import DoorCurrentState, DoorShift, Incident, MaintenanceRequest

from .operations_center_service import OperationsCenterService


@dataclass
class EngineeringDoorMetric:
    door: Door
    status: str
    status_label: str
    employee_count: int
    employee_names: list[str]
    open_incident_count: int
    today_incident_count: int
    active_maintenance_count: int
    target_staff_count: int | None
    staff_coverage_percent: int | None
    staff_coverage_level: str
    staff_coverage_label: str
    staff_coverage_detail: str
    staff_coverage_applicable: bool
    staff_coverage_reason: str
    staff_delta: int | None
    last_activity: object
    door_shift: DoorShift | None


class EngineeringCenterService:
    """Build the engineering-center snapshot with a fixed number of bulk queries.

    Staff coverage is intentionally separate from future visitor-density metrics.
    Real occupancy or flow must come from an authorized counter, sensor, camera
    analytics API, or manual occupancy feed before being exposed here.
    """

    OPEN_INCIDENT_STATUSES = (
        Incident.Status.NEW,
        Incident.Status.IN_PROGRESS,
        Incident.Status.FORWARDED,
    )
    ACTIVE_MAINTENANCE_STATUSES = (
        MaintenanceRequest.Status.NEW,
        MaintenanceRequest.Status.APPROVED,
        MaintenanceRequest.Status.ASSIGNED,
        MaintenanceRequest.Status.IN_PROGRESS,
        MaintenanceRequest.Status.OPEN,
    )

    SUSPENDED_COVERAGE_REASONS = {
        DoorShift.DoorState.MAINTENANCE: "الباب تحت الصيانة",
        DoorShift.DoorState.CLOSED: "الباب مغلق تشغيليًا",
        DoorShift.DoorState.SECURED: "الباب مؤمّن",
    }

    @classmethod
    def staff_coverage(cls, *, current_staff, target_staff, door_status=DoorShift.DoorState.OPEN):
        if door_status != DoorShift.DoorState.OPEN:
            return (
                None, "suspended", "معلّقة",
                cls.SUSPENDED_COVERAGE_REASONS.get(door_status, "الباب غير متاح للتشغيل"),
                False, door_status, current_staff - target_staff if target_staff else None,
            )
        if not target_staff:
            return None, "unconfigured", "غير مهيأة", "لم يُحدد العدد المستهدف لهذا الباب", True, "", None
        percent = round((current_staff / target_staff) * 100)
        difference = current_staff - target_staff
        if current_staff == 0:
            level, label = "uncovered", "بدون تغطية"
        elif percent < 70:
            level, label = "low", "تغطية منخفضة"
        elif percent < 100:
            level, label = "partial", "تغطية جزئية"
        elif percent < 130:
            level, label = "complete", "تغطية مكتملة"
        else:
            level, label = "surplus", "فائض تشغيلي"
        if difference < 0:
            detail = f"نقص {abs(difference)} موظف"
        elif difference > 0:
            detail = f"فائض {difference} موظف"
        else:
            detail = "مكتملة"
        return percent, level, label, detail, True, "", difference

    @classmethod
    def build(cls, *, active_shift, include_employee_names=False, allowed_sections=None):
        doors = list(
            Door.objects.filter(is_active=True)
            .select_related("zone", "operational_profile")
            .order_by("sort_order", "door_number")
        )
        door_ids = [door.pk for door in doors]
        door_numbers = [door.door_number for door in doors]

        shifts = []
        if active_shift:
            shifts = list(
                DoorShift.objects.filter(
                    shift_plan=active_shift,
                    is_active=True,
                    door_number__in=door_numbers,
                ).select_related("shift_plan", "shift_plan__shift_type", "supervisor")
            )
        shift_by_number = {item.door_number: item for item in shifts}
        shift_ids = [item.pk for item in shifts]

        states = DoorCurrentState.objects.filter(door_id__in=door_ids).select_related(
            "current_shift", "current_shift__shift_plan"
        )
        state_by_door = {item.door_id: item for item in states}

        assignments_by_door = defaultdict(list)
        if active_shift:
            assignments = DoorAssignment.objects.filter(
                shift_plan=active_shift,
                is_active=True,
                door_id__in=door_ids,
            )
            if allowed_sections is not None:
                assignments = assignments.filter(section__in=allowed_sections)
            assignments = assignments.select_related("employee")
            for assignment in assignments:
                assignments_by_door[assignment.door_id].append(assignment)

        incident_counts = defaultdict(int)
        today_incident_counts = defaultdict(int)
        incident_activity = {}
        today = timezone.localdate()
        incidents = Incident.objects.filter(
            Q(door_id__in=door_ids) | Q(door_shift__door_number__in=door_numbers)
        ).filter(
            Q(status__in=cls.OPEN_INCIDENT_STATUSES) | Q(created_at__date=today)
        )
        if allowed_sections is not None:
            incidents = incidents.filter(section__in=allowed_sections)
        incidents = incidents.values(
            "door_id", "door_shift__door_number", "status", "created_at", "updated_at"
        )
        door_id_by_number = {door.door_number: door.pk for door in doors}
        for incident in incidents:
            door_id = incident["door_id"] or door_id_by_number.get(incident["door_shift__door_number"])
            if not door_id:
                continue
            if incident["status"] in cls.OPEN_INCIDENT_STATUSES:
                incident_counts[door_id] += 1
                incident_activity[door_id] = max(
                    incident_activity.get(door_id, incident["updated_at"]),
                    incident["updated_at"],
                )
            if timezone.localdate(incident["created_at"]) == today:
                today_incident_counts[door_id] += 1

        maintenance_counts = defaultdict(int)
        maintenance_activity = {}
        maintenance = MaintenanceRequest.objects.filter(
            status__in=cls.ACTIVE_MAINTENANCE_STATUSES,
            door_shift__door_number__in=door_numbers,
        )
        if allowed_sections is not None:
            maintenance = maintenance.filter(section__in=allowed_sections)
        maintenance = maintenance.values("door_shift__door_number", "created_at")
        for request in maintenance:
            door_id = door_id_by_number.get(request["door_shift__door_number"])
            if not door_id:
                continue
            maintenance_counts[door_id] += 1
            maintenance_activity[door_id] = max(
                maintenance_activity.get(door_id, request["created_at"]), request["created_at"]
            )

        labels = dict(DoorShift.DoorState.choices)
        rows = []
        for door in doors:
            door_shift = shift_by_number.get(door.door_number)
            current_state = state_by_door.get(door.pk)
            status = OperationsCenterService._resolve_state(
                door_shift=door_shift, current_state=current_state
            )
            assignment_rows = assignments_by_door[door.pk]
            activities = [
                value for value in (
                    getattr(current_state, "updated_at", None),
                    getattr(door_shift, "updated_at", None),
                    incident_activity.get(door.pk),
                    maintenance_activity.get(door.pk),
                ) if value is not None
            ]
            names = []
            if include_employee_names:
                names = [item.employee.full_name for item in assignment_rows]
            try:
                target_staff = door.operational_profile.target_staff_count
            except Door.operational_profile.RelatedObjectDoesNotExist:
                target_staff = None
            coverage_percent, coverage_level, coverage_label, coverage_detail, coverage_applicable, coverage_reason, staff_delta = (
                cls.staff_coverage(
                    current_staff=len(assignment_rows), target_staff=target_staff,
                    door_status=status,
                )
            )
            rows.append(EngineeringDoorMetric(
                door=door,
                status=status,
                status_label=labels.get(status, status),
                employee_count=len(assignment_rows),
                employee_names=names,
                open_incident_count=incident_counts[door.pk],
                today_incident_count=today_incident_counts[door.pk],
                active_maintenance_count=maintenance_counts[door.pk],
                target_staff_count=target_staff,
                staff_coverage_percent=coverage_percent,
                staff_coverage_level=coverage_level,
                staff_coverage_label=coverage_label,
                staff_coverage_detail=coverage_detail,
                staff_coverage_applicable=coverage_applicable,
                staff_coverage_reason=coverage_reason,
                staff_delta=staff_delta,
                last_activity=max(activities) if activities else None,
                door_shift=door_shift,
            ))

        summary = {
            "total_doors": len(rows),
            "working_doors": sum(row.status == DoorShift.DoorState.OPEN for row in rows),
            "stopped_doors": sum(row.status in (DoorShift.DoorState.CLOSED, DoorShift.DoorState.SECURED) for row in rows),
            "maintenance_doors": sum(row.status == DoorShift.DoorState.MAINTENANCE for row in rows),
            "open_incidents": sum(row.open_incident_count for row in rows),
            "active_maintenance": sum(row.active_maintenance_count for row in rows),
            "assigned_employees": sum(row.employee_count for row in rows),
            "coverage_applicable_doors": sum(row.staff_coverage_applicable for row in rows),
            "suspended_coverage_doors": sum(not row.staff_coverage_applicable for row in rows),
            "uncovered_doors": sum(row.staff_coverage_level == "uncovered" for row in rows),
            "low_coverage_doors": sum(row.staff_coverage_level == "low" for row in rows),
        }
        return {"doors": rows, "summary": summary}
