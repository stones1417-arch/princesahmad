from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification
from apps.roles.models import UserRole
from apps.roles.services.access_control import user_has_role
from apps.roles.services.section_access import get_allowed_sections
from apps.scheduling.models import ShiftAssignment
from apps.scheduling.models import ShiftOperationalLeadership
from apps.scheduling.operational_leadership_service import resolve_shift_leader

from .models import Incident, IncidentRoutingEvent, MaintenanceRequest


class IncidentRoutingService:
    """Institutional routing, escalation and maintenance hand-off for incidents."""

    ROLE_SUPERVISOR = "shift_supervisor"
    ROLE_DEPUTY = "shift_deputy"
    ROLE_HEAD = "doors_department_head"
    ROLE_GENERAL_MANAGER = "general_manager"
    ROLE_INCIDENT_SUPERVISOR = "incident_supervisor"

    @staticmethod
    def _role_users(role_code, section):
        queryset = UserRole.objects.filter(
            is_active=True,
            role__is_active=True,
            role__code=role_code,
            user__is_active=True,
        )
        if section in {"male", "female"}:
            queryset = queryset.filter(
                Q(role__operational_section=section)
                | Q(role__operational_section="all")
            )
        return queryset.values_list("user_id", flat=True).distinct()

    @classmethod
    def resolve_primary_assignee(cls, active_shift, section):
        if active_shift is None or section not in {"male", "female"}:
            return None, ""
        leader = resolve_shift_leader(
            active_shift,
            ShiftOperationalLeadership.Responsibility.INCIDENT_SUPERVISOR,
        )
        if leader and getattr(leader, "employee", None):
            if leader.employee.operational_section == section:
                return leader, leader.employee.full_name
        return None, ""

    @classmethod
    def visible_incidents(cls, queryset, user):
        if user.is_superuser:
            return queryset
        queryset = queryset.filter(section__in=get_allowed_sections(user))
        if user_has_role(user, cls.ROLE_GENERAL_MANAGER):
            return queryset.filter(
                escalation_level=Incident.EscalationLevel.GENERAL_MANAGER
            )
        if user_has_role(user, cls.ROLE_HEAD) or user_has_role(
            user, "doors_department_deputy"
        ):
            return queryset
        if user_has_role(user, cls.ROLE_INCIDENT_SUPERVISOR):
            shift_ids = ShiftOperationalLeadership.objects.filter(
                employee__user=user,
                responsibility=ShiftOperationalLeadership.Responsibility.INCIDENT_SUPERVISOR,
            ).values_list("shift_plan_id", flat=True)
            return queryset.filter(shift_plan_id__in=shift_ids)
        if user_has_role(user, cls.ROLE_SUPERVISOR) or user_has_role(
            user, cls.ROLE_DEPUTY
        ):
            shift_ids = ShiftAssignment.objects.filter(
                employee__user=user,
                is_confirmed=True,
            ).values_list("shift_plan_id", flat=True)
            return queryset.filter(shift_plan_id__in=shift_ids)
        return queryset.filter(Q(assigned_to=user) | Q(created_by=user))

    @classmethod
    def route_created_incident(cls, incident, actor=None):
        assignee, assignee_name = cls.resolve_primary_assignee(
            incident.shift_plan, incident.section
        )
        incident.assigned_to = assignee
        incident.assigned_to_name = assignee_name
        incident.save(update_fields=["assigned_to", "assigned_to_name", "updated_at"])
        IncidentRoutingEvent.objects.create(
            incident=incident,
            event_type=IncidentRoutingEvent.EventType.CREATED,
            actor=actor,
        )
        if assignee:
            IncidentRoutingEvent.objects.create(
                incident=incident,
                event_type=IncidentRoutingEvent.EventType.ASSIGNED,
                actor=actor,
                target_user=assignee,
            )
            Notification.objects.create(
                user=assignee,
                title="بلاغ تشغيلي جديد",
                message=f"تم إسناد البلاغ {incident.incident_number} إليك.",
                section=incident.section,
                url="/ops/incidents/",
            )
        return incident

    @classmethod
    @transaction.atomic
    def escalate_incident(cls, incident, actor, note=""):
        locked = Incident.objects.select_for_update().get(pk=incident.pk)
        if locked.escalation_level == Incident.EscalationLevel.NONE:
            target = Incident.EscalationLevel.DEPARTMENT_HEAD
            role_code = cls.ROLE_HEAD
        elif locked.escalation_level == Incident.EscalationLevel.DEPARTMENT_HEAD:
            if not (
                user_has_role(actor, cls.ROLE_HEAD)
                or user_has_role(actor, "doors_department_deputy")
                or actor.is_superuser
            ):
                raise ValidationError("التصعيد إلى المدير العام متاح لرئاسة القسم فقط.")
            target = Incident.EscalationLevel.GENERAL_MANAGER
            role_code = cls.ROLE_GENERAL_MANAGER
        else:
            raise ValidationError("وصل البلاغ إلى أعلى مستوى تصعيد.")
        locked.escalation_level = target
        locked.escalated_at = timezone.now()
        locked.escalated_by = actor
        locked.escalation_note = str(note or "").strip()
        locked.save(update_fields=[
            "escalation_level", "escalated_at", "escalated_by",
            "escalation_note", "updated_at",
        ])
        IncidentRoutingEvent.objects.create(
            incident=locked,
            event_type=IncidentRoutingEvent.EventType.ESCALATED,
            actor=actor,
            target_level=target,
            note=locked.escalation_note,
        )
        recipient_ids = set(cls._role_users(role_code, locked.section))
        if role_code == cls.ROLE_HEAD:
            from .models import LeadershipDelegation

            recipient_ids.update(LeadershipDelegation.objects.filter(
                section=locked.section, revoked_at__isnull=True,
                starts_at__lte=timezone.now(), ends_at__gt=timezone.now(),
                delegate__is_active=True,
            ).values_list("delegate_id", flat=True))
        recipient_ids.discard(getattr(actor, "pk", None))
        for user_id in recipient_ids:
            Notification.objects.create(
                user_id=user_id,
                title="تصعيد بلاغ تشغيلي",
                message=f"تم تصعيد البلاغ {locked.incident_number} إلى مستواك.",
                section=locked.section,
                url="/ops/incidents/",
                level=Notification.Level.WARNING,
            )
        return locked

    @staticmethod
    @transaction.atomic
    def add_shift_update(incident, actor, note):
        clean_note = str(note or "").strip()
        if not clean_note:
            raise ValidationError("ملاحظات المعالجة مطلوبة.")
        locked = Incident.objects.select_for_update().get(pk=incident.pk)
        event = IncidentRoutingEvent.objects.create(
            incident=locked,
            event_type=IncidentRoutingEvent.EventType.PROCESSING_STARTED,
            actor=actor,
            note=clean_note,
        )
        if locked.created_by_id and locked.created_by_id != getattr(actor, "pk", None):
            Notification.objects.create(
                user_id=locked.created_by_id,
                title="تحديث من الوردية",
                message=f"ورد تحديث جديد على البلاغ {locked.incident_number}.",
                section=locked.section,
                url="/ops/incidents/",
            )
        return event

    @staticmethod
    @transaction.atomic
    def convert_to_maintenance(
        incident, request, planned_start_at, planned_end_at, actor=None
    ):
        from .maintenance_service import MaintenanceService

        locked = Incident.objects.select_for_update().get(pk=incident.pk)
        if MaintenanceRequest.objects.filter(source_incident=locked).exists():
            raise ValidationError("تم إنشاء طلب صيانة لهذا البلاغ مسبقًا.")
        if not locked.door_shift_id:
            raise ValidationError("لا يمكن التحويل دون سجل باب في وردية نشطة.")
        priority_map = {
            Incident.Priority.LOW: MaintenanceRequest.Priority.LOW,
            Incident.Priority.MEDIUM: MaintenanceRequest.Priority.MEDIUM,
            Incident.Priority.HIGH: MaintenanceRequest.Priority.HIGH,
            Incident.Priority.CRITICAL: MaintenanceRequest.Priority.URGENT,
        }
        maintenance = MaintenanceService.create_request(
            request=request,
            door=locked.door_shift,
            description=locked.description,
            priority=priority_map[locked.priority],
            planned_start_at=planned_start_at,
            planned_end_at=planned_end_at,
            section=locked.section,
            assignment=locked.assignment,
            source_incident=locked,
        )
        locked.status = Incident.Status.FORWARDED
        locked.save(update_fields=["status", "updated_at"])
        IncidentRoutingEvent.objects.create(
            incident=locked,
            event_type=IncidentRoutingEvent.EventType.CONVERTED_TO_MAINTENANCE,
            actor=actor,
            note=maintenance.request_number,
        )
        return maintenance
