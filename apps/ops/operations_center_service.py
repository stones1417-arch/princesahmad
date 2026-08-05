from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Prefetch

from apps.distribution.models import DoorAssignment
from apps.locations.models import Door
from apps.scheduling.models import ShiftPlan

from .models import (
    DoorCurrentState,
    DoorShift,
    Incident,
    MaintenanceRequest,
)


# ==========================================================
# قواعد توزيع الأبواب حسب الجهات
# ==========================================================

DIRECTION_RULES = (
    (
        "south",
        "الجهة الجنوبية",
        1,
        6,
    ),
    (
        "west",
        "الجهة الغربية",
        7,
        14,
    ),
    (
        "north",
        "الجهة الشمالية",
        15,
        27,
    ),
    (
        "east",
        "الجهة الشرقية",
        28,
        35,
    ),
    (
        "southeast",
        "الجهة الجنوبية الشرقية",
        36,
        41,
    ),
)


@dataclass
class OperationsCenterMetrics:
    """
    المؤشرات العامة لمركز العمليات.
    """

    total_doors: int = 0

    open_doors: int = 0
    closed_doors: int = 0
    maintenance_doors: int = 0
    secured_doors: int = 0

    open_incidents: int = 0
    critical_incidents: int = 0

    open_maintenance: int = 0

    doors_without_supervisor: int = 0
    doors_without_monitor: int = 0

    assigned_employees: int = 0


class OperationsCenterService:
    """
    الخدمة الموحدة لبناء بيانات:

    - مركز العمليات.
    - غرفة القيادة والتحكم.
    - خريطة الأبواب التشغيلية.
    - مؤشرات التغطية.
    - البلاغات.
    - طلبات الصيانة.
    """

    OPEN_INCIDENT_STATUSES = (
        Incident.Status.NEW,
        Incident.Status.IN_PROGRESS,
        Incident.Status.FORWARDED,
    )

    OPEN_MAINTENANCE_STATUSES = (
        MaintenanceRequest.Status.NEW,
        MaintenanceRequest.Status.APPROVED,
        MaintenanceRequest.Status.ASSIGNED,
        MaintenanceRequest.Status.IN_PROGRESS,
        MaintenanceRequest.Status.OPEN,
    )

    STATE_LABELS = dict(
        DoorShift.DoorState.choices
    )

    # ======================================================
    # الوردية النشطة
    # ======================================================

    @staticmethod
    def get_active_shift() -> ShiftPlan | None:
        """
        جلب الوردية النشطة الحالية.
        """

        return (
            ShiftPlan.objects
            .select_related(
                "shift_type",
            )
            .filter(
                is_active=True,
            )
            .order_by(
                "-date",
                "-id",
            )
            .first()
        )

    # ======================================================
    # تحديد الجهة
    # ======================================================

    @staticmethod
    def direction_for_number(
        door_number: int,
    ) -> tuple[str, str]:
        """
        تحديد الجهة حسب رقم الباب.
        """

        for (
            key,
            label,
            first_number,
            last_number,
        ) in DIRECTION_RULES:

            if (
                first_number
                <= door_number
                <= last_number
            ):
                return key, label

        return (
            "other",
            "غير مصنف",
        )

    # ======================================================
    # إنشاء هيكل الجهات
    # ======================================================

    @staticmethod
    def empty_groups() -> dict[str, dict[str, Any]]:
        """
        إنشاء هيكل فارغ للجهات بنفس الترتيب الرسمي.
        """

        return {
            key: {
                "key": key,
                "label": label,
                "first_number": first_number,
                "last_number": last_number,
                "doors": [],
            }
            for (
                key,
                label,
                first_number,
                last_number,
            ) in DIRECTION_RULES
        }

    # ======================================================
    # البناء الرئيسي
    # ======================================================

    @classmethod
    def build(cls) -> dict[str, Any]:
        """
        بناء بيانات مركز العمليات وغرفة القيادة.
        """

        active_shift = cls.get_active_shift()

        groups = cls.empty_groups()

        metrics = OperationsCenterMetrics()

        doors = list(
            Door.objects
            .filter(
                is_active=True,
                door_number__gte=1,
                door_number__lte=41,
            )
            .select_related(
                "zone",
            )
            .order_by(
                "door_number",
            )
        )

        metrics.total_doors = len(doors)

        if not active_shift:
            cls._append_doors_without_shift(
                doors=doors,
                groups=groups,
                metrics=metrics,
            )

            return {
                "active_shift": None,
                "groups": list(
                    groups.values()
                ),
                "metrics": metrics,
            }

        assignments = list(
            DoorAssignment.objects
            .filter(
                shift_plan=active_shift,
                is_active=True,
            )
            .select_related(
                "employee",
                "door",
                "assigned_by",
            )
            .order_by(
                "door__door_number",
                "-is_supervisor",
                "employee__employee_number",
            )
        )

        assignments_by_door: dict[
            int,
            list[DoorAssignment],
        ] = {}

        for assignment in assignments:
            assignments_by_door.setdefault(
                assignment.door_id,
                [],
            ).append(
                assignment
            )

        metrics.assigned_employees = len(
            {
                assignment.employee_id
                for assignment in assignments
            }
        )

        door_shifts = {
            item.door_number: item
            for item in (
                DoorShift.objects
                .filter(
                    shift_plan=active_shift,
                    is_active=True,
                    door_number__gte=1,
                    door_number__lte=41,
                )
                .select_related(
                    "supervisor",
                    "shift_plan",
                    "shift_plan__shift_type",
                )
                .order_by(
                    "door_number",
                )
            )
        }

        current_states = {
            item.door_id: item
            for item in (
                DoorCurrentState.objects
                .filter(
                    door__is_active=True,
                    door__door_number__gte=1,
                    door__door_number__lte=41,
                )
                .select_related(
                    "door",
                    "current_shift",
                    "updated_by",
                )
            )
        }

        open_incidents = list(
            Incident.objects
            .filter(
                shift_plan=active_shift,
                status__in=(
                    cls.OPEN_INCIDENT_STATUSES
                ),
            )
            .select_related(
                "door_shift",
                "created_by",
            )
            .order_by(
                "-created_at",
            )
        )

        incidents_by_number: dict[
            int,
            list[Incident],
        ] = {}

        for incident in open_incidents:
            if not incident.door_shift_id:
                continue

            incidents_by_number.setdefault(
                incident.door_shift.door_number,
                [],
            ).append(
                incident
            )

        metrics.open_incidents = len(
            open_incidents
        )

        metrics.critical_incidents = sum(
            1
            for incident in open_incidents
            if (
                incident.priority
                == Incident.Priority.CRITICAL
            )
        )

        open_maintenance = list(
            MaintenanceRequest.objects
            .filter(
                door_shift__shift_plan=active_shift,
                status__in=(
                    cls.OPEN_MAINTENANCE_STATUSES
                ),
            )
            .select_related(
                "door_shift",
                "created_by",
                "technician",
            )
            .order_by(
                "-created_at",
            )
        )

        maintenance_by_number: dict[
            int,
            list[MaintenanceRequest],
        ] = {}

        for maintenance in open_maintenance:
            maintenance_by_number.setdefault(
                maintenance.door_shift.door_number,
                [],
            ).append(
                maintenance
            )

        metrics.open_maintenance = len(
            open_maintenance
        )

        for door in doors:
            cls._append_door(
                door=door,
                groups=groups,
                metrics=metrics,
                door_shift=door_shifts.get(
                    door.door_number
                ),
                current_state=current_states.get(
                    door.id
                ),
                assignments=assignments_by_door.get(
                    door.id,
                    [],
                ),
                incidents=incidents_by_number.get(
                    door.door_number,
                    [],
                ),
                maintenance_requests=(
                    maintenance_by_number.get(
                        door.door_number,
                        [],
                    )
                ),
            )

        return {
            "active_shift": active_shift,
            "groups": list(
                groups.values()
            ),
            "metrics": metrics,
        }

    # ======================================================
    # إضافة باب
    # ======================================================

    @classmethod
    def _append_door(
        cls,
        *,
        door: Door,
        groups: dict[str, dict[str, Any]],
        metrics: OperationsCenterMetrics,
        door_shift: DoorShift | None,
        current_state: DoorCurrentState | None,
        assignments: list[DoorAssignment],
        incidents: list[Incident],
        maintenance_requests: list[
            MaintenanceRequest
        ],
    ) -> None:
        """
        إضافة بيانات باب إلى مجموعته.
        """

        state = cls._resolve_state(
            door_shift=door_shift,
            current_state=current_state,
        )

        notes = cls._resolve_notes(
            door_shift=door_shift,
            current_state=current_state,
        )

        updated_at = cls._resolve_updated_at(
            door_shift=door_shift,
            current_state=current_state,
        )

        supervisor_assignment = next(
            (
                assignment
                for assignment in assignments
                if (
                    assignment.is_supervisor
                    or assignment.role
                    == DoorAssignment.Role.SUPERVISOR
                )
            ),
            None,
        )

        monitor_count = sum(
            1
            for assignment in assignments
            if (
                assignment.role
                == DoorAssignment.Role.MONITOR
            )
        )

        if not supervisor_assignment:
            metrics.doors_without_supervisor += 1

        if monitor_count == 0:
            metrics.doors_without_monitor += 1

        cls._update_state_metrics(
            metrics=metrics,
            state=state,
        )

        direction_key, direction_label = (
            cls.direction_for_number(
                door.door_number
            )
        )

        groups[direction_key]["doors"].append(
            {
                "door": door,

                "shift": door_shift,

                "current_state": current_state,

                "direction_key": direction_key,

                "direction_label": (
                    direction_label
                ),

                "state": state,

                "state_label": (
                    cls.STATE_LABELS.get(
                        state,
                        state,
                    )
                ),

                "notes": notes,

                "updated_at": updated_at,

                "assignments": assignments,

                "supervisor_assignment": (
                    supervisor_assignment
                ),

                "monitor_count": monitor_count,

                "employee_count": len(
                    assignments
                ),

                "open_incident_count": len(
                    incidents
                ),

                "open_maintenance_count": len(
                    maintenance_requests
                ),

                "incidents": incidents,

                "maintenance_requests": (
                    maintenance_requests
                ),
            }
        )

    # ======================================================
    # في حال عدم وجود وردية
    # ======================================================

    @classmethod
    def _append_doors_without_shift(
        cls,
        *,
        doors: list[Door],
        groups: dict[str, dict[str, Any]],
        metrics: OperationsCenterMetrics,
    ) -> None:
        """
        عرض الأبواب حتى في حال عدم وجود وردية نشطة.
        """

        current_states = {
            item.door_id: item
            for item in (
                DoorCurrentState.objects
                .filter(
                    door__in=doors,
                )
                .select_related(
                    "door",
                    "current_shift",
                    "updated_by",
                )
            )
        }

        for door in doors:
            current_state = current_states.get(
                door.id
            )

            state = (
                current_state.state
                if current_state
                else DoorShift.DoorState.CLOSED
            )

            cls._update_state_metrics(
                metrics=metrics,
                state=state,
            )

            metrics.doors_without_supervisor += 1
            metrics.doors_without_monitor += 1

            (
                direction_key,
                direction_label,
            ) = cls.direction_for_number(
                door.door_number
            )

            groups[
                direction_key
            ]["doors"].append(
                {
                    "door": door,

                    "shift": None,

                    "current_state": (
                        current_state
                    ),

                    "direction_key": (
                        direction_key
                    ),

                    "direction_label": (
                        direction_label
                    ),

                    "state": state,

                    "state_label": (
                        cls.STATE_LABELS.get(
                            state,
                            state,
                        )
                    ),

                    "notes": (
                        current_state.notes
                        if current_state
                        else ""
                    ),

                    "updated_at": (
                        current_state.updated_at
                        if current_state
                        else None
                    ),

                    "assignments": [],

                    "supervisor_assignment": None,

                    "monitor_count": 0,

                    "employee_count": 0,

                    "open_incident_count": 0,

                    "open_maintenance_count": 0,

                    "incidents": [],

                    "maintenance_requests": [],
                }
            )

    # ======================================================
    # تحديد الحالة الفعلية
    # ======================================================

    @staticmethod
    def _resolve_state(
        *,
        door_shift: DoorShift | None,
        current_state: DoorCurrentState | None,
    ) -> str:
        """
        الحالة الحالية لها الأولوية.
        """

        if current_state:
            return current_state.state

        if door_shift:
            return door_shift.state

        return DoorShift.DoorState.CLOSED

    @staticmethod
    def _resolve_notes(
        *,
        door_shift: DoorShift | None,
        current_state: DoorCurrentState | None,
    ) -> str:
        """
        تحديد الملاحظات الحالية.
        """

        if current_state:
            return current_state.notes or ""

        if door_shift:
            return door_shift.notes or ""

        return ""

    @staticmethod
    def _resolve_updated_at(
        *,
        door_shift: DoorShift | None,
        current_state: DoorCurrentState | None,
    ):
        """
        تحديد آخر وقت تحديث.
        """

        if current_state:
            return current_state.updated_at

        if door_shift:
            return door_shift.updated_at

        return None

    # ======================================================
    # تحديث العدادات
    # ======================================================

    @staticmethod
    def _update_state_metrics(
        *,
        metrics: OperationsCenterMetrics,
        state: str,
    ) -> None:
        """
        تحديث عدادات حالات الأبواب.
        """

        if state == DoorShift.DoorState.OPEN:
            metrics.open_doors += 1

        elif state == DoorShift.DoorState.CLOSED:
            metrics.closed_doors += 1

        elif (
            state
            == DoorShift.DoorState.MAINTENANCE
        ):
            metrics.maintenance_doors += 1

        elif state == DoorShift.DoorState.SECURED:
            metrics.secured_doors += 1