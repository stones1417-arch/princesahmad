from typing import ClassVar

from django.db.models import Case, IntegerField, Q, Value, When
from django.urls import reverse
from django.utils import timezone

from .incident_routing_service import IncidentRoutingService
from .models import Incident, IncidentRoutingEvent, MaintenanceRequest


class EngineeringIncidentFollowupService:
    CLOSED = (Incident.Status.RESOLVED, Incident.Status.CLOSED)
    EVENT_LABELS: ClassVar[dict[str, str]] = {
        "created": "تم إنشاء البلاغ",
        "assigned": "تم إسناد البلاغ إلى مشرف البلاغات",
        "processing_started": "بدأ مشرف البلاغات المعالجة",
        "escalated": "تم تصعيد البلاغ",
        "converted_to_maintenance": "تم تحويل البلاغ للصيانة",
        "maintenance_approved": "اعتمد مركز العمليات طلب الصيانة",
        "maintenance_started": "بدأت أعمال الصيانة",
        "maintenance_completed": "اكتملت أعمال الصيانة",
        "closed": "أغلق مشرف البلاغات البلاغ",
    }

    @classmethod
    def operational_stage(cls, incident):
        maintenance = getattr(incident, "maintenance_request", None)
        if incident.closed_at or incident.status in cls.CLOSED:
            return "closed", "مغلق"
        if maintenance and maintenance.status in {
            MaintenanceRequest.Status.DONE, MaintenanceRequest.Status.CLOSED,
        }:
            return "awaiting_close", "اكتملت الصيانة — بانتظار تحقق مشرف البلاغات"
        if maintenance and maintenance.status == MaintenanceRequest.Status.IN_PROGRESS:
            return "maintenance", "الصيانة قيد التنفيذ"
        if maintenance:
            labels = {
                MaintenanceRequest.Status.APPROVED: "طلب الصيانة معتمد",
                MaintenanceRequest.Status.ASSIGNED: "محول للفريق الفني",
            }
            return "maintenance_review", labels.get(
                maintenance.status, "بانتظار اعتماد الصيانة"
            )
        if incident.escalation_level == Incident.EscalationLevel.GENERAL_MANAGER:
            return "general_manager", "مصعّد للمدير العام"
        if incident.escalation_level == Incident.EscalationLevel.DEPARTMENT_HEAD:
            return "department_head", "مصعّد لرئيس قسم الأبواب"
        if incident.status == Incident.Status.IN_PROGRESS:
            return "processing", "قيد المعالجة"
        if incident.assigned_to_id:
            return "assigned", "تم تعيين مشرف البلاغات"
        return "unassigned", "بانتظار التعيين"

    @classmethod
    def build(cls, *, door, user, active_shift=None, incident_supervisor=None,
              section_label="النطاق التشغيلي", door_status_label="متاح",
              can_view_maintenance_details=False):
        queryset = IncidentRoutingService.visible_incidents(
            Incident.objects.filter(
                Q(door=door) | Q(door_shift__door_number=door.door_number)
            ), user
        ).select_related(
            "assigned_to", "door", "door_shift", "shift_plan", "closed_by",
            "escalated_by", "maintenance_request", "maintenance_request__technician",
        ).prefetch_related("routing_events", "routing_events__actor").annotate(
            closed_order=Case(
                When(status__in=cls.CLOSED, then=Value(1)),
                default=Value(0), output_field=IntegerField(),
            )
        ).order_by("closed_order", "-created_at")
        incidents = list(queryset)
        today = timezone.localdate()
        items = [
            cls.serialize(
                item,
                can_view_maintenance_details=can_view_maintenance_details,
            )
            for item in incidents
        ]
        return {
            "door": {"id": door.pk, "number": door.door_number},
            "context": {
                "section": section_label,
                "status": door_status_label,
                "owner": "المركز الهندسي",
            },
            "supervisor": ({
                "name": incident_supervisor.employee.full_name,
                "role": "مشرف البلاغات",
                "shift": str(active_shift),
                "section": getattr(incident_supervisor.employee, "get_operational_section_display", lambda: "")(),
            } if incident_supervisor else None),
            "incident_center_url": f'{reverse("ops:incidents")}?door={door.pk}',
            "create_url": reverse("ops:engineering-incident-create", args=[door.pk]),
            "summary": {
                "open": sum(item.status not in cls.CLOSED for item in incidents),
                "today": sum(timezone.localdate(item.created_at) == today for item in incidents),
                "processing": sum(item.status == Incident.Status.IN_PROGRESS for item in incidents),
                "escalated": sum(item.escalation_level != Incident.EscalationLevel.NONE for item in incidents),
                "maintenance": sum(hasattr(item, "maintenance_request") for item in incidents),
                "closed_today": sum(bool(item.closed_at and timezone.localtime(item.closed_at).date() == today) for item in incidents),
            },
            "incidents": items,
        }

    @classmethod
    def serialize(cls, incident, *, can_view_maintenance_details=False):
        events = list(incident.routing_events.all())
        last_update = next((event for event in reversed(events) if event.note and event.event_type == IncidentRoutingEvent.EventType.PROCESSING_STARTED), None)
        stage_key, stage_label = cls.operational_stage(incident)
        serialized_events = []
        for index, event in enumerate(events):
            label = cls.EVENT_LABELS.get(event.event_type, event.get_event_type_display())
            if event.note and event.event_type == IncidentRoutingEvent.EventType.PROCESSING_STARTED:
                label = "تحديث من مشرف البلاغات"
            if event.event_type == IncidentRoutingEvent.EventType.ESCALATED:
                label = "تم التصعيد إلى المدير العام" if event.target_level == Incident.EscalationLevel.GENERAL_MANAGER else "تم التصعيد إلى رئيس قسم الأبواب"
            serialized_events.append({
                "type": event.event_type, "label": label,
                "state": "current" if index == len(events) - 1 and stage_key != "closed" else "done",
                "note": event.note, "actor": event.actor.get_full_name() or event.actor.username if event.actor else "النظام",
                "created_at": timezone.localtime(event.created_at).strftime("%Y-%m-%d %H:%M"),
            })
        maintenance = getattr(incident, "maintenance_request", None)
        return {
            "id": incident.pk, "number": incident.incident_number,
            "type": incident.get_incident_type_display(), "priority": incident.priority,
            "priority_label": incident.get_priority_display(), "status": incident.status,
            "status_label": incident.get_status_display(), "stage": stage_key,
            "is_closed": incident.status in cls.CLOSED,
            "stage_label": stage_label, "description": incident.description,
            "created_at": timezone.localtime(incident.created_at).strftime("%Y-%m-%d %H:%M"),
            "waiting_seconds": max(0, int((timezone.now() - incident.created_at).total_seconds())),
            "assignee": incident.assigned_to_name or "بانتظار تعيين مشرف البلاغات",
            "escalation": incident.get_escalation_level_display(),
            "escalation_note": incident.escalation_note,
            "escalated_by": (incident.escalated_by.get_full_name() or incident.escalated_by.username) if incident.escalated_by else "",
            "escalated_at": timezone.localtime(incident.escalated_at).strftime("%Y-%m-%d %H:%M") if incident.escalated_at else "",
            "maintenance": ({"number": maintenance.request_number, "status": maintenance.status, "status_label": maintenance.get_status_display(), "technician": maintenance.technician_name if can_view_maintenance_details else "", "planned_start": timezone.localtime(maintenance.planned_start_at).strftime("%Y-%m-%d %H:%M") if maintenance.planned_start_at else "", "planned_end": timezone.localtime(maintenance.planned_end_at).strftime("%Y-%m-%d %H:%M") if maintenance.planned_end_at else ""} if maintenance else None),
            "last_update": ({"note": last_update.note, "actor": last_update.actor.get_full_name() or last_update.actor.username if last_update.actor else "النظام", "created_at": timezone.localtime(last_update.created_at).strftime("%Y-%m-%d %H:%M")} if last_update else None),
            "closed_by": (incident.closed_by.get_full_name() or incident.closed_by.username) if incident.closed_by else "",
            "closed_at": timezone.localtime(incident.closed_at).strftime("%Y-%m-%d %H:%M") if incident.closed_at else "",
            "events": serialized_events,
        }
