from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.dashboard.models import SystemActivityLog

from .operations_center_service import OperationsCenterService


class CommandCenterService:
    """
    خدمة غرفة القيادة التشغيلية V2.

    تعتمد على OperationsCenterService كمصدر موحد لبيانات:
    - الوردية النشطة.
    - حالات الأبواب.
    - توزيع الموظفين.
    - البلاغات المفتوحة.
    - طلبات الصيانة المفتوحة.
    """

    LIVE_MODULES = (
        "الأبواب",
        "الصيانة",
        "البلاغات",
        "توزيع الأبواب",
    )

    STALE_AFTER_MINUTES = 30
    MAX_ALERTS = 30
    MAX_LIVE_FEED = 25

    ALERT_PRIORITY = {
        "critical": 0,
        "warning": 1,
        "info": 2,
    }

    # =====================================================
    # التجهيز الرئيسي
    # =====================================================

    @classmethod
    def build(cls):
        """
        تجهيز سياق صفحة غرفة القيادة.
        """

        operations_data = OperationsCenterService.build()

        active_shift = operations_data["active_shift"]
        groups = list(operations_data["groups"])
        metrics = operations_data["metrics"]

        generated_at = timezone.now()

        stale_limit = (
            generated_at
            - timedelta(
                minutes=cls.STALE_AFTER_MINUTES,
            )
        )

        direction_metrics = cls._build_direction_metrics(
            groups=groups,
        )

        alerts = cls._build_alerts(
            groups=groups,
            metrics=metrics,
            stale_limit=stale_limit,
        )

        critical_alerts_count = sum(
            1
            for alert in alerts
            if alert.get("level") == "critical"
        )
        warning_alerts_count = sum(
            1
            for alert in alerts
            if alert.get("level") == "warning"
        )

        live_feed = list(
            SystemActivityLog.objects
            .select_related("user")
            .filter(
                module__in=cls.LIVE_MODULES,
            )
            .order_by("-created_at")[
                :cls.MAX_LIVE_FEED
            ]
        )

        readiness_rate = (
            cls._calculate_readiness_rate(
                metrics=metrics,
            )
        )

        supervision_coverage_rate = (
            cls._calculate_supervision_coverage(
                metrics=metrics,
            )
        )

        monitor_coverage_rate = (
            cls._calculate_monitor_coverage(
                metrics=metrics,
            )
        )

        operational_score = (
            cls._calculate_operational_score(
                readiness_rate=readiness_rate,
                supervision_coverage_rate=(
                    supervision_coverage_rate
                ),
                monitor_coverage_rate=(
                    monitor_coverage_rate
                ),
                critical_incidents=(
                    metrics.critical_incidents
                ),
                open_maintenance=(
                    metrics.open_maintenance
                ),
            )
        )

        (
            operational_status_key,
            operational_status_label,
        ) = cls._get_operational_status(
            score=operational_score,
            critical_incidents=(
                metrics.critical_incidents
            ),
        )

        return {
            **operations_data,

            "active_shift": active_shift,
            "groups": groups,
            "metrics": metrics,

            "direction_metrics": direction_metrics,

            "alerts": alerts,
            "alerts_count": len(alerts),
            "critical_alerts_count": critical_alerts_count,
            "warning_alerts_count": warning_alerts_count,

            "live_feed": live_feed,

            "generated_at": generated_at,

            "readiness_rate": readiness_rate,

            "coverage_rate": (
                supervision_coverage_rate
            ),

            "supervision_coverage_rate": (
                supervision_coverage_rate
            ),

            "monitor_coverage_rate": (
                monitor_coverage_rate
            ),

            "operational_score": (
                operational_score
            ),

            "operational_status_key": (
                operational_status_key
            ),

            "operational_status_label": (
                operational_status_label
            ),

            "stale_after_minutes": (
                cls.STALE_AFTER_MINUTES
            ),
        }

    # =====================================================
    # JSON
    # =====================================================

    @classmethod
    def build_json(cls):
        """
        تجهيز البيانات اللحظية بصيغة JSON.
        """

        context = cls.build()

        metrics = context["metrics"]
        active_shift = context["active_shift"]

        groups_payload = cls._groups_to_json(
            context["groups"]
        )

        direction_metrics_payload = [
            {
                "key": item["key"],
                "label": item["label"],
                "total_doors": item["total_doors"],
                "open_doors": item["open_doors"],
                "closed_doors": item["closed_doors"],
                "maintenance_doors": (
                    item["maintenance_doors"]
                ),
                "secured_doors": item["secured_doors"],
                "employees": item["employees"],
                "incidents": item["incidents"],
                "maintenance_requests": (
                    item["maintenance_requests"]
                ),
                "without_supervisor": (
                    item["without_supervisor"]
                ),
                "readiness_rate": (
                    item["readiness_rate"]
                ),
            }
            for item in context["direction_metrics"]
        ]

        feed_payload = cls._feed_to_json(
            context["live_feed"]
        )

        active_shift_payload = None

        if active_shift:
            start_time = getattr(
                active_shift,
                "effective_start_time",
                None,
            )
            end_time = getattr(
                active_shift,
                "effective_end_time",
                None,
            )
            active_shift_payload = {
                "id": active_shift.id,
                "name": cls._shift_type_name(active_shift),
                "shift_type": cls._shift_type_name(
                    active_shift
                ),
                "date": (
                    active_shift.date.isoformat()
                    if active_shift.date
                    else ""
                ),
                "start_time": (
                    start_time.strftime("%H:%M")
                    if start_time
                    else ""
                ),
                "end_time": (
                    end_time.strftime("%H:%M")
                    if end_time
                    else ""
                ),
                "status": (
                    "running"
                    if active_shift.is_active
                    else "ended"
                    if active_shift.is_finished
                    else "preparation"
                ),
                "status_label": (
                    "قيد التشغيل"
                    if active_shift.is_active
                    else "منتهية"
                    if active_shift.is_finished
                    else "قيد التجهيز"
                ),
            }

        return {
            "success": True,

            "generated_at": (
                context["generated_at"].isoformat()
            ),

            "active_shift": active_shift_payload,

            "metrics": {
                "total_doors": (
                    metrics.total_doors
                ),

                "open_doors": (
                    metrics.open_doors
                ),

                "closed_doors": (
                    metrics.closed_doors
                ),

                "maintenance_doors": (
                    metrics.maintenance_doors
                ),

                "secured_doors": (
                    metrics.secured_doors
                ),

                "open_incidents": (
                    metrics.open_incidents
                ),

                "critical_incidents": (
                    metrics.critical_incidents
                ),

                "open_maintenance": (
                    metrics.open_maintenance
                ),

                "assigned_employees": (
                    metrics.assigned_employees
                ),

                "doors_without_supervisor": (
                    metrics.doors_without_supervisor
                ),

                "doors_without_monitor": (
                    metrics.doors_without_monitor
                ),
            },

            "indicators": {
                "readiness_rate": (
                    context["readiness_rate"]
                ),

                "coverage_rate": (
                    context["coverage_rate"]
                ),

                "supervision_coverage_rate": (
                    context[
                        "supervision_coverage_rate"
                    ]
                ),

                "monitor_coverage_rate": (
                    context[
                        "monitor_coverage_rate"
                    ]
                ),

                "operational_score": (
                    context["operational_score"]
                ),

                "status_key": (
                    context[
                        "operational_status_key"
                    ]
                ),

                "status_label": (
                    context[
                        "operational_status_label"
                    ]
                ),
            },

            "alerts": context["alerts"],

            "alert_summary": {
                "total": context["alerts_count"],
                "critical": context[
                    "critical_alerts_count"
                ],
                "warning": context[
                    "warning_alerts_count"
                ],
            },

            "direction_metrics": (
                direction_metrics_payload
            ),

            "groups": groups_payload,

            "live_feed": feed_payload,
        }

    # =====================================================
    # تحويل بيانات الأبواب
    # =====================================================

    @classmethod
    def _groups_to_json(cls, groups):
        """
        تحويل مجموعات الأبواب إلى JSON.
        """

        groups_payload = []

        for group in groups:
            doors_payload = []

            for item in group["doors"]:
                door = item["door"]

                supervisor_assignment = (
                    item["supervisor_assignment"]
                )

                supervisor_name = ""

                if supervisor_assignment:
                    supervisor_name = (
                        supervisor_assignment
                        .employee
                        .full_name
                    )

                assignments_payload = []

                for assignment in item["assignments"]:
                    assignments_payload.append(
                        {
                            "id": assignment.id,

                            "employee_id": (
                                assignment.employee_id
                            ),

                            "employee_name": (
                                assignment
                                .employee
                                .full_name
                            ),

                            "employee_number": (
                                assignment
                                .employee
                                .employee_number
                            ),

                            "role": assignment.role,

                            "role_label": (
                                assignment
                                .get_role_display()
                            ),

                            "is_supervisor": (
                                assignment.is_supervisor
                            ),
                        }
                    )

                doors_payload.append(
                    {
                        "id": door.id,

                        "number": door.door_number,

                        "sort_order": door.sort_order,

                        "direction_key": item["direction_key"],

                        "name": str(door),

                        "zone": (
                            door.zone.name
                            if door.zone_id
                            else ""
                        ),

                        "state": item["state"],

                        "state_label": (
                            item["state_label"]
                        ),

                        "notes": (
                            item["notes"]
                            or ""
                        ),

                        "updated_at": (
                            item["updated_at"].isoformat()
                            if item["updated_at"]
                            else None
                        ),

                        "employee_count": (
                            item["employee_count"]
                        ),

                        "monitor_count": (
                            item["monitor_count"]
                        ),

                        "supervisor_name": (
                            supervisor_name
                        ),

                        "has_supervisor": bool(
                            supervisor_assignment
                        ),

                        "incident_count": (
                            item[
                                "open_incident_count"
                            ]
                        ),

                        "maintenance_count": (
                            item[
                                "open_maintenance_count"
                            ]
                        ),

                        "assignments": (
                            assignments_payload
                        ),
                    }
                )

            groups_payload.append(
                {
                    "key": group["key"],
                    "label": group["label"],
                    "doors": doors_payload,
                }
            )

        return groups_payload

    @staticmethod
    def _feed_to_json(live_feed):
        """
        تحويل سجل العمليات إلى JSON.
        """

        payload = []

        for log in live_feed:
            username = "النظام"

            if log.user:
                username = (
                    log.user.get_full_name()
                    or log.user.username
                )

            payload.append(
                {
                    "id": log.id,

                    "module": log.module,

                    "action": log.action,

                    "action_label": (
                        log.get_action_display()
                    ),

                    "description": (
                        log.description
                    ),

                    "username": username,

                    "created_at": (
                        log.created_at.isoformat()
                    ),
                }
            )

        return payload

    # =====================================================
    # مؤشرات الجهات
    # =====================================================

    @classmethod
    def _build_direction_metrics(
        cls,
        *,
        groups,
    ):
        """
        حساب مؤشرات كل جهة بصورة مستقلة.
        """

        direction_metrics = []

        for group in groups:
            doors = group["doors"]

            total_doors = len(doors)

            open_doors = sum(
                1
                for item in doors
                if item["state"] == "open"
            )

            closed_doors = sum(
                1
                for item in doors
                if item["state"] == "closed"
            )

            maintenance_doors = sum(
                1
                for item in doors
                if item["state"] == "maintenance"
            )

            secured_doors = sum(
                1
                for item in doors
                if item["state"] == "secured"
            )

            employees = sum(
                item["employee_count"]
                for item in doors
            )

            incidents = sum(
                item["open_incident_count"]
                for item in doors
            )

            maintenance_requests = sum(
                item["open_maintenance_count"]
                for item in doors
            )

            without_supervisor = sum(
                1
                for item in doors
                if not item["supervisor_assignment"]
            )

            ready_doors = (
                open_doors
                + secured_doors
            )

            readiness_rate = cls._percentage(
                ready_doors,
                total_doors,
            )

            direction_metrics.append(
                {
                    "key": group["key"],
                    "label": group["label"],

                    "total_doors": total_doors,

                    "open_doors": open_doors,

                    "closed_doors": closed_doors,

                    "maintenance_doors": (
                        maintenance_doors
                    ),

                    "secured_doors": (
                        secured_doors
                    ),

                    "employees": employees,

                    "incidents": incidents,

                    "maintenance_requests": (
                        maintenance_requests
                    ),

                    "without_supervisor": (
                        without_supervisor
                    ),

                    "readiness_rate": (
                        readiness_rate
                    ),
                }
            )

        return direction_metrics

    # =====================================================
    # التنبيهات
    # =====================================================

    @classmethod
    def _build_alerts(
        cls,
        *,
        groups,
        metrics,
        stale_limit,
    ):
        """
        بناء التنبيهات التشغيلية.
        """

        alerts = []

        if metrics.critical_incidents:
            alerts.append(
                {
                    "level": "critical",

                    "title": "بلاغات حرجة",

                    "message": (
                        f"يوجد "
                        f"{metrics.critical_incidents} "
                        "بلاغ حرج مفتوح."
                    ),
                }
            )

        if metrics.open_maintenance:
            alerts.append(
                {
                    "level": "warning",

                    "title": (
                        "طلبات صيانة مفتوحة"
                    ),

                    "message": (
                        f"يوجد "
                        f"{metrics.open_maintenance} "
                        "طلب صيانة مفتوح."
                    ),
                }
            )

        if metrics.doors_without_supervisor:
            alerts.append(
                {
                    "level": "warning",

                    "title": (
                        "أبواب دون مشرف"
                    ),

                    "message": (
                        f"يوجد "
                        f"{metrics.doors_without_supervisor} "
                        "باب دون مشرف."
                    ),
                }
            )

        if metrics.doors_without_monitor:
            alerts.append(
                {
                    "level": "info",

                    "title": (
                        "أبواب دون مراقب"
                    ),

                    "message": (
                        f"يوجد "
                        f"{metrics.doors_without_monitor} "
                        "باب دون مراقب."
                    ),
                }
            )

        for group in groups:
            for item in group["doors"]:
                door_number = (
                    item["door"].door_number
                )

                updated_at = item["updated_at"]

                if (
                    updated_at
                    and updated_at < stale_limit
                ):
                    alerts.append(
                        {
                            "level": "info",

                            "title": (
                                f"تحديث باب "
                                f"{door_number}"
                            ),

                            "message": (
                                "لم يتم تحديث حالة "
                                "الباب منذ أكثر من "
                                f"{cls.STALE_AFTER_MINUTES} "
                                "دقيقة."
                            ),
                        }
                    )

                if item["open_incident_count"]:
                    alerts.append(
                        {
                            "level": "critical",

                            "title": (
                                f"بلاغ على باب "
                                f"{door_number}"
                            ),

                            "message": (
                                "عدد البلاغات "
                                "المفتوحة: "
                                f"{item['open_incident_count']}."
                            ),
                        }
                    )

                if item[
                    "open_maintenance_count"
                ]:
                    alerts.append(
                        {
                            "level": "warning",

                            "title": (
                                f"صيانة باب "
                                f"{door_number}"
                            ),

                            "message": (
                                "عدد طلبات الصيانة "
                                "المفتوحة: "
                                f"{item['open_maintenance_count']}."
                            ),
                        }
                    )

        alerts.sort(
            key=lambda item: (
                cls.ALERT_PRIORITY.get(
                    item["level"],
                    9,
                )
            )
        )

        return alerts[:cls.MAX_ALERTS]

    # =====================================================
    # المؤشرات
    # =====================================================

    @classmethod
    def _calculate_readiness_rate(
        cls,
        *,
        metrics,
    ):
        ready_doors = (
            metrics.open_doors
            + metrics.secured_doors
        )

        return cls._percentage(
            ready_doors,
            metrics.total_doors,
        )

    @classmethod
    def _calculate_supervision_coverage(
        cls,
        *,
        metrics,
    ):
        covered_doors = max(
            metrics.total_doors
            - metrics.doors_without_supervisor,
            0,
        )

        return cls._percentage(
            covered_doors,
            metrics.total_doors,
        )

    @classmethod
    def _calculate_monitor_coverage(
        cls,
        *,
        metrics,
    ):
        covered_doors = max(
            metrics.total_doors
            - metrics.doors_without_monitor,
            0,
        )

        return cls._percentage(
            covered_doors,
            metrics.total_doors,
        )

    @staticmethod
    def _calculate_operational_score(
        *,
        readiness_rate,
        supervision_coverage_rate,
        monitor_coverage_rate,
        critical_incidents,
        open_maintenance,
    ):
        """
        حساب مؤشر التشغيل من 100.
        """

        score = round(
            (readiness_rate * 0.50)
            + (
                supervision_coverage_rate
                * 0.30
            )
            + (
                monitor_coverage_rate
                * 0.20
            )
        )

        score -= (
            critical_incidents * 12
        )

        score -= min(
            open_maintenance * 2,
            20,
        )

        return max(
            0,
            min(score, 100),
        )

    @staticmethod
    def _get_operational_status(
        *,
        score,
        critical_incidents,
    ):
        if critical_incidents:
            return (
                "critical",
                "حالة حرجة",
            )

        if score >= 85:
            return (
                "stable",
                "التشغيل مستقر",
            )

        if score >= 65:
            return (
                "warning",
                "يحتاج متابعة",
            )

        return (
            "critical",
            "يحتاج تدخل عاجل",
        )

    @staticmethod
    def _percentage(value, total):
        if not total:
            return 0

        return round(
            (value / total) * 100
        )

    @staticmethod
    def _shift_type_name(active_shift):
        shift_type = getattr(
            active_shift,
            "shift_type",
            None,
        )

        if not shift_type:
            return ""

        return getattr(
            shift_type,
            "name",
            str(shift_type),
        )
