from django.db.models import Count, Q
from django.utils import timezone

from apps.ops.engineering_center_service import EngineeringCenterService
from apps.ops.incident_routing_service import IncidentRoutingService
from apps.ops.models import Incident
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.section_access import get_allowed_sections
from apps.scheduling.models import ShiftAssignment, ShiftPlan


class ShiftCenterService:
    """Build the current-shift operational inbox without template-side scoping."""

    CLOSED = (Incident.Status.RESOLVED, Incident.Status.CLOSED)

    @classmethod
    def build(cls, request):
        active_shift = ShiftPlan.objects.select_related("shift_type").filter(
            is_active=True
        ).first()
        sections = get_allowed_sections(request.user)
        assignments = ShiftAssignment.objects.none()
        if active_shift:
            assignments = ShiftAssignment.objects.filter(
                shift_plan=active_shift,
                is_confirmed=True,
                employee__is_active=True,
            ).select_related("employee", "employee__user")

        supervisor = assignments.filter(
            role=ShiftAssignment.OperationalRole.SHIFT_HEAD,
            employee__operational_section__in=sections,
        ).first()
        deputy = assignments.filter(
            role=ShiftAssignment.OperationalRole.SHIFT_DEPUTY,
            employee__operational_section__in=sections,
        ).first()

        base = IncidentRoutingService.visible_incidents(
            Incident.objects.all(), request.user
        )
        if active_shift:
            base = base.filter(shift_plan=active_shift)
        else:
            base = base.filter(assigned_to__isnull=True)
        base = base.select_related(
            "door", "door_shift", "assigned_to", "maintenance_request"
        ).prefetch_related("routing_events", "routing_events__actor")

        query = str(request.GET.get("q", "") or "").strip()
        door = str(request.GET.get("door", "") or "").strip()
        priority = str(request.GET.get("priority", "") or "").strip()
        status = str(request.GET.get("status", "") or "").strip()
        escalation = str(request.GET.get("escalation", "") or "").strip()
        maintenance = str(request.GET.get("maintenance", "") or "").strip()
        if query:
            base = base.filter(
                Q(incident_number__icontains=query)
                | Q(description__icontains=query)
                | Q(door__door_number__icontains=query)
            )
        if door:
            base = base.filter(
                Q(door__door_number=door) | Q(door_shift__door_number=door)
            )
        if priority in dict(Incident.Priority.choices):
            base = base.filter(priority=priority)
        if status in dict(Incident.Status.choices):
            base = base.filter(status=status)
        if escalation in dict(Incident.EscalationLevel.choices):
            base = base.filter(escalation_level=escalation)
        if maintenance == "yes":
            base = base.filter(maintenance_request__isnull=False)
        elif maintenance == "no":
            base = base.filter(maintenance_request__isnull=True)

        tab = str(request.GET.get("tab", "") or "").strip()
        if not tab:
            tab = "inbox" if active_shift else "overview"
        tab_filters = {
            "inbox": Q(status=Incident.Status.NEW),
            "processing": Q(status=Incident.Status.IN_PROGRESS),
            "escalated": ~Q(escalation_level=Incident.EscalationLevel.NONE),
            "completed": Q(status__in=cls.CLOSED),
        }
        incidents = base.filter(tab_filters[tab]) if tab in tab_filters else base
        today = timezone.localdate()
        counters = base.aggregate(
            new=Count("pk", filter=Q(status=Incident.Status.NEW), distinct=True),
            processing=Count("pk", filter=Q(status=Incident.Status.IN_PROGRESS), distinct=True),
            escalated=Count("pk", filter=~Q(escalation_level=Incident.EscalationLevel.NONE), distinct=True),
            maintenance=Count("pk", filter=Q(maintenance_request__isnull=False), distinct=True),
            completed=Count("pk", filter=Q(status__in=cls.CLOSED, closed_at__date=today), distinct=True),
        )
        incident_rows = list(incidents.order_by("-created_at"))
        coverage = EngineeringCenterService.build(
            active_shift=active_shift,
            allowed_sections=sections,
        )
        coverage_rows = coverage["doors"]
        coverage_summary = {
            "complete": sum(
                row.staff_coverage_level in ("complete", "surplus")
                for row in coverage_rows
            ),
            "partial": sum(
                row.staff_coverage_level in ("partial", "low")
                for row in coverage_rows
            ),
            "uncovered": sum(
                row.staff_coverage_level == "uncovered" for row in coverage_rows
            ),
            "suspended": sum(
                row.staff_coverage_level == "suspended" for row in coverage_rows
            ),
            "assigned_staff": coverage["summary"]["assigned_employees"],
        }
        attention_items = []
        if active_shift and not supervisor:
            attention_items.append({
                "level": "critical",
                "title": "الوردية تعمل بدون مشرف معيّن",
                "description": "يجب تعيين مشرف لضمان توجيه البلاغات التشغيلية تلقائيًا.",
                "tab": "overview",
            })
        if counters["new"]:
            attention_items.append({
                "level": "critical",
                "title": f"{counters['new']} بلاغ جديد ينتظر الاستلام",
                "description": "بلاغات واردة لم تبدأ معالجتها بعد.",
                "tab": "inbox",
            })
        if counters["escalated"]:
            attention_items.append({
                "level": "warning",
                "title": f"{counters['escalated']} بلاغ مصعّد",
                "description": "بلاغات تحتاج متابعة إشرافية ضمن المسار الحالي.",
                "tab": "escalated",
            })
        if coverage_summary["uncovered"]:
            attention_items.append({
                "level": "warning",
                "title": f"{coverage_summary['uncovered']} باب مفتوح بدون تغطية",
                "description": "التغطية محسوبة وفق الخطة التشغيلية المعتمدة.",
                "tab": "overview",
            })

        activity_feed = []
        for incident in incident_rows:
            events = list(incident.routing_events.all())
            if events:
                activity_feed.append({"incident": incident, "event": events[-1]})
        activity_feed.sort(key=lambda item: item["event"].created_at, reverse=True)

        return {
            "active_shift": active_shift,
            "supervisor_assignment": supervisor,
            "deputy_assignment": deputy,
            "assignment_count": assignments.count(),
            "operational_sections": sections,
            "incidents": incident_rows,
            "incident_counters": counters,
            "selected_tab": tab,
            "filters": {"q": query, "door": door, "priority": priority, "status": status, "escalation": escalation, "maintenance": maintenance},
            "priority_choices": Incident.Priority.choices,
            "status_choices": Incident.Status.choices,
            "escalation_choices": Incident.EscalationLevel.choices,
            "coverage_summary": coverage_summary,
            "attention_items": attention_items,
            "activity_feed": activity_feed[:5],
            "has_active_filters": any((query, door, priority, status, escalation, maintenance)),
            "can_manage_assignments": user_has_permission(
                request.user, PlatformPermissions.ASSIGN_EMPLOYEES
            ),
        }
