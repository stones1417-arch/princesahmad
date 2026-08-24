from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q

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
    active_maintenance_count: int
    density_percent: None
    density_level: None
    last_activity: object
    door_shift: DoorShift | None


class EngineeringCenterService:
    """Build the engineering-center snapshot with a fixed number of bulk queries."""

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

    @classmethod
    def build(cls, *, active_shift, include_employee_names=False, allowed_sections=None):
        doors = list(
            Door.objects.filter(is_active=True)
            .select_related("zone")
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
        incident_activity = {}
        incidents = Incident.objects.filter(
            status__in=cls.OPEN_INCIDENT_STATUSES,
        ).filter(
            Q(door_id__in=door_ids) | Q(door_shift__door_number__in=door_numbers)
        )
        if allowed_sections is not None:
            incidents = incidents.filter(section__in=allowed_sections)
        incidents = incidents.values("door_id", "door_shift__door_number", "updated_at")
        door_id_by_number = {door.door_number: door.pk for door in doors}
        for incident in incidents:
            door_id = incident["door_id"] or door_id_by_number.get(incident["door_shift__door_number"])
            if not door_id:
                continue
            incident_counts[door_id] += 1
            incident_activity[door_id] = max(
                incident_activity.get(door_id, incident["updated_at"]), incident["updated_at"]
            )

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
            rows.append(EngineeringDoorMetric(
                door=door,
                status=status,
                status_label=labels.get(status, status),
                employee_count=len(assignment_rows),
                employee_names=names,
                open_incident_count=incident_counts[door.pk],
                active_maintenance_count=maintenance_counts[door.pk],
                density_percent=None,
                density_level=None,
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
        }
        return {"doors": rows, "summary": summary}
