from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.notifications.models import Notification
from apps.roles.models import UserRole
from apps.roles.services.access_control import user_has_role
from apps.roles.services.section_access import get_allowed_sections

from .models import Incident, IncidentSupervisoryAction, LeadershipDelegation


class SupervisoryLeadershipService:
    HEAD = "doors_department_head"
    DEPUTY = "doors_department_deputy"
    SENIOR_ADMIN = "senior_administrator"
    GENERAL_MANAGER = "general_manager"

    ROLE_ACTIONS = {
        HEAD: {
            "request_update", "supervisory_note", "supervisory_directive",
            "return_to_followup", "escalate_to_general_manager",
            "administrative_alert", "supervisory_resolved",
        },
        DEPUTY: {
            "request_update", "supervisory_note", "supervisory_directive",
            "return_to_followup", "escalate_to_general_manager",
            "administrative_alert", "supervisory_resolved",
        },
        SENIOR_ADMIN: {
            "request_update", "administrative_note", "administrative_alert",
        },
        GENERAL_MANAGER: {
            "request_update", "executive_directive", "return_to_followup",
            "supervisory_resolved",
        },
    }

    @staticmethod
    def _role_users(role_code, section):
        query = UserRole.objects.filter(
            is_active=True, role__is_active=True, role__code=role_code,
            user__is_active=True,
        )
        if section in {"male", "female"}:
            query = query.filter(
                Q(role__operational_section=section) | Q(role__operational_section="all")
            )
        return query.select_related("user", "role")

    @staticmethod
    def _notify(*, recipients, actor, title, message, section, url, level=Notification.Level.WARNING):
        recipient_ids = {
            recipient.pk for recipient in recipients
            if recipient and recipient.is_active and recipient != actor
        }
        Notification.objects.bulk_create([
            Notification(
                user_id=user_id, title=title, message=message, section=section,
                url=url, level=level,
            )
            for user_id in recipient_ids
        ])

    @classmethod
    def active_delegation(cls, user, section, at=None):
        at = at or timezone.now()
        return LeadershipDelegation.objects.select_related("principal", "delegate").filter(
            delegate=user, section=section, starts_at__lte=at, ends_at__gt=at,
            revoked_at__isnull=True,
        ).first()

    @classmethod
    def authority(cls, user, section):
        if not user or not user.is_authenticated or not user.is_active:
            return None, None
        if user.is_superuser:
            return cls.HEAD, None
        if section not in get_allowed_sections(user):
            return None, None
        for role in (cls.GENERAL_MANAGER, cls.HEAD, cls.SENIOR_ADMIN):
            if user_has_role(user, role):
                return role, None
        if user_has_role(user, cls.DEPUTY):
            delegation = cls.active_delegation(user, section)
            if delegation:
                return cls.DEPUTY, delegation
        return None, None

    @classmethod
    def visible_incidents(cls, user):
        sections = get_allowed_sections(user)
        query = Incident.objects.filter(section__in=sections).select_related(
            "assigned_to", "shift_plan", "door", "door_shift", "maintenance_request",
        ).prefetch_related(Prefetch(
            "supervisory_actions",
            queryset=IncidentSupervisoryAction.objects.select_related(
                "actor", "acting_for", "target_user", "parent",
            ).prefetch_related("responses"),
        ))
        roles = {role for role in cls.ROLE_ACTIONS if user_has_role(user, role)}
        delegated = LeadershipDelegation.objects.filter(
            delegate=user, revoked_at__isnull=True, starts_at__lte=timezone.now(),
            ends_at__gt=timezone.now(), section__in=sections,
        ).values_list("section", flat=True)
        if not roles and not delegated and not user.is_superuser:
            raise PermissionDenied
        if cls.GENERAL_MANAGER in roles and len(roles) == 1:
            query = query.filter(escalation_level=Incident.EscalationLevel.GENERAL_MANAGER)
        return query

    @classmethod
    def head_attention_queue(cls, user):
        """Return only cases requiring a head decision, in deterministic priority order."""
        incidents = list(cls.visible_incidents(user).exclude(
            status__in=(Incident.Status.RESOLVED, Incident.Status.CLOSED),
        )[:50])
        queue = []
        open_states = {
            IncidentSupervisoryAction.Status.OPEN,
            IncidentSupervisoryAction.Status.ANSWERED,
            IncidentSupervisoryAction.Status.ACKNOWLEDGED,
        }
        for incident in incidents:
            actions = list(incident.supervisory_actions.all())
            reason = None
            rank = 99
            if any(
                item.action_type == IncidentSupervisoryAction.ActionType.RETURN_TO_FOLLOWUP
                and item.status in open_states for item in actions
            ):
                rank, reason = 1, "أعاد المدير العام الحالة إلى القسم"
            elif incident.escalation_level == Incident.EscalationLevel.DEPARTMENT_HEAD:
                rank, reason = 2, "تصعيد جديد ينتظر مراجعة رئيس القسم"
            elif any(
                item.action_type == IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT
                and item.status == IncidentSupervisoryAction.Status.OPEN for item in actions
            ):
                rank, reason = 3, "تنبيه إداري مفتوح"
            elif any(
                item.action_type == IncidentSupervisoryAction.ActionType.REQUEST_UPDATE
                and item.status == IncidentSupervisoryAction.Status.ANSWERED
                and (item.actor_id == user.pk or item.acting_for_id == user.pk)
                for item in actions
            ):
                rank, reason = 4, "رد تحديث ينتظر المراجعة"
            elif any(
                item.action_type == IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE
                and item.status in {
                    IncidentSupervisoryAction.Status.OPEN,
                    IncidentSupervisoryAction.Status.ACKNOWLEDGED,
                } for item in actions
            ):
                rank, reason = 5, "توجيه إشرافي ما زال قيد المتابعة"
            elif (
                getattr(incident, "maintenance_request", None)
                and incident.maintenance_request.status in {"done", "closed"}
                and any(item.status in open_states for item in actions)
            ):
                rank, reason = 6, "اكتملت الصيانة والمتابعة الإشرافية ما زالت مفتوحة"
            if reason:
                incident.attention_reason = reason
                incident.attention_rank = rank
                incident.latest_supervisory_action = actions[0] if actions else None
                queue.append(incident)
        return sorted(queue, key=lambda item: (
            item.attention_rank, -item.latest_supervisory_action.pk
            if item.latest_supervisory_action else 0, item.pk,
        ))

    @classmethod
    def center_attention_queue(cls, user, center):
        """Build a bounded, presentation-only queue for the active command center."""
        if center == "department":
            return cls.head_attention_queue(user)

        incidents = list(cls.visible_incidents(user).exclude(
            status__in=(Incident.Status.RESOLVED, Incident.Status.CLOSED),
        )[:50])
        open_states = {
            IncidentSupervisoryAction.Status.OPEN,
            IncidentSupervisoryAction.Status.ANSWERED,
            IncidentSupervisoryAction.Status.ACKNOWLEDGED,
        }
        queue = []
        for incident in incidents:
            actions = list(incident.supervisory_actions.all())
            if center == "administrative":
                relevant = [item for item in actions if item.action_type in {
                    IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
                    IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_NOTE,
                    IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT,
                } and item.status in open_states]
                reason = "متابعة إدارية مفتوحة"
            else:
                relevant = [item for item in actions if item.action_type in {
                    IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE,
                    IncidentSupervisoryAction.ActionType.RETURN_TO_FOLLOWUP,
                    IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
                } and item.status in open_states]
                if incident.escalation_level == Incident.EscalationLevel.GENERAL_MANAGER:
                    relevant.append(None)
                reason = "قرار تنفيذي ينتظر المراجعة"
            if relevant:
                incident.attention_reason = reason
                incident.latest_supervisory_action = next(
                    (item for item in actions if item is not None), None
                )
                queue.append(incident)
        return queue

    @classmethod
    @transaction.atomic
    def create_delegation(cls, *, principal, delegate, section, starts_at, ends_at, reason=""):
        if not user_has_role(principal, cls.HEAD) and not principal.is_superuser:
            raise PermissionDenied
        if section not in get_allowed_sections(principal):
            raise PermissionDenied
        if not user_has_role(delegate, cls.DEPUTY) or section not in get_allowed_sections(delegate):
            raise ValidationError("يجب اختيار نائب نشط من القسم التشغيلي نفسه.")
        overlap = LeadershipDelegation.objects.filter(
            section=section, revoked_at__isnull=True,
            starts_at__lt=ends_at, ends_at__gt=starts_at,
        ).filter(Q(principal=principal) | Q(delegate=delegate))
        if overlap.exists():
            raise ValidationError("يوجد تفويض متداخل ضمن الفترة المحددة.")
        delegation = LeadershipDelegation(
            principal=principal, delegate=delegate, section=section,
            starts_at=starts_at, ends_at=ends_at, reason=str(reason or "").strip(),
            created_by=principal,
        )
        delegation.full_clean()
        delegation.save()
        Notification.objects.create(
            user=delegate, title="تفويض إشرافي جديد",
            message=f"فُوّضت بصلاحيات المتابعة الإشرافية حتى {ends_at:%Y-%m-%d %H:%M}.",
            section=section, url="/ops/leadership/department/",
        )
        return delegation

    @classmethod
    @transaction.atomic
    def revoke_delegation(cls, delegation, actor):
        if actor != delegation.principal and not actor.is_superuser:
            raise PermissionDenied
        if delegation.revoked_at:
            raise ValidationError("التفويض ملغى مسبقًا.")
        delegation.revoked_at = timezone.now()
        delegation.revoked_by = actor
        delegation.save(update_fields=["revoked_at", "revoked_by"])
        return delegation

    @classmethod
    @transaction.atomic
    def create_action(
        cls, *, incident, actor, action_type, note, subject="", parent=None,
        target_user=None,
    ):
        role, delegation = cls.authority(actor, incident.section)
        if not role or action_type not in cls.ROLE_ACTIONS.get(role, set()):
            raise PermissionDenied
        locked = Incident.objects.select_for_update().get(pk=incident.pk)
        if (
            role == cls.GENERAL_MANAGER
            and locked.escalation_level != Incident.EscalationLevel.GENERAL_MANAGER
        ):
            raise PermissionDenied
        target = target_user or locked.assigned_to
        if action_type == IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT or (
            action_type == IncidentSupervisoryAction.ActionType.RETURN_TO_FOLLOWUP
            and role == cls.GENERAL_MANAGER
        ):
            head_assignment = cls._role_users(cls.HEAD, locked.section).first()
            target = head_assignment.user if head_assignment else None
        if target and target != locked.assigned_to:
            allowed_target = (
                action_type in {
                    IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE,
                    IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT,
                    IncidentSupervisoryAction.ActionType.RETURN_TO_FOLLOWUP,
                }
                and user_has_role(target, cls.HEAD)
                and locked.section in get_allowed_sections(target)
            )
            if not allowed_target:
                raise ValidationError("المتلقي المحدد غير مخول لهذا التوجيه.")
        action = IncidentSupervisoryAction(
            incident=locked, action_type=action_type, actor=actor,
            acting_for=delegation.principal if delegation else None,
            target_user=target, parent=parent, subject=str(subject or "").strip(),
            note=str(note or "").strip(),
            status=(IncidentSupervisoryAction.Status.RESOLVED
                    if action_type == "supervisory_resolved"
                    else IncidentSupervisoryAction.Status.OPEN),
            resolved_at=timezone.now() if action_type == "supervisory_resolved" else None,
        )
        action.full_clean()
        action.save()
        if action_type == "escalate_to_general_manager":
            locked.escalation_level = Incident.EscalationLevel.GENERAL_MANAGER
            locked.escalated_at = timezone.now()
            locked.escalated_by = actor
            locked.escalation_note = action.note
            locked.save(update_fields=[
                "escalation_level", "escalated_at", "escalated_by",
                "escalation_note", "updated_at",
            ])
            recipients = [assignment.user for assignment in cls._role_users(cls.GENERAL_MANAGER, locked.section)]
        elif action_type == "administrative_alert" or (
            action_type == "return_to_followup" and role == cls.GENERAL_MANAGER
        ):
            recipients = [assignment.user for assignment in cls._role_users(cls.HEAD, locked.section)]
        else:
            recipients = [target] if target else []
        cls._notify(
            recipients=recipients, actor=actor, title=action.get_action_type_display(),
            message=f"إجراء إشرافي على البلاغ {locked.incident_number}: {action.note[:140]}",
            section=locked.section, url=f"/ops/leadership/incidents/{locked.pk}/",
        )
        return action

    @classmethod
    @transaction.atomic
    def respond_to_update_request(cls, request_action, actor, note):
        request_action = IncidentSupervisoryAction.objects.select_for_update().get(
            pk=request_action.pk
        )
        if request_action.action_type != IncidentSupervisoryAction.ActionType.REQUEST_UPDATE:
            raise ValidationError("لا يمكن الرد إلا على طلب تحديث.")
        if request_action.status != IncidentSupervisoryAction.Status.OPEN:
            raise ValidationError("تمت الإجابة عن طلب التحديث أو إنهاؤه مسبقًا.")
        if request_action.target_user_id != getattr(actor, "pk", None):
            raise PermissionDenied
        clean_note = str(note or "").strip()
        if not clean_note:
            raise ValidationError("نص الرد مطلوب.")
        response = IncidentSupervisoryAction(
            incident=request_action.incident,
            action_type=IncidentSupervisoryAction.ActionType.RESPONSE,
            status=IncidentSupervisoryAction.Status.COMPLETED,
            actor=actor, target_user=request_action.actor, parent=request_action,
            subject=f"رد: {request_action.subject}"[:200], note=clean_note,
            completed_by=actor, completed_at=timezone.now(),
        )
        response.full_clean()
        response.save()
        request_action.status = IncidentSupervisoryAction.Status.ANSWERED
        request_action.save(update_fields=["status"])
        recipients = [request_action.actor]
        if user_has_role(request_action.actor, cls.SENIOR_ADMIN):
            recipients.extend(
                assignment.user for assignment in cls._role_users(
                    cls.HEAD, request_action.incident.section
                )
            )
        cls._notify(
            recipients=recipients, actor=actor, title="رد على طلب تحديث",
            message=f"ورد رد على طلب التحديث للبلاغ {request_action.incident.incident_number}.",
            section=request_action.incident.section,
            url=f"/ops/leadership/incidents/{request_action.incident_id}/",
        )
        return response

    @classmethod
    @transaction.atomic
    def resolve_update_request(cls, request_action, actor):
        request_action = IncidentSupervisoryAction.objects.select_for_update().get(
            pk=request_action.pk
        )
        if (
            request_action.action_type != IncidentSupervisoryAction.ActionType.REQUEST_UPDATE
            or request_action.status != IncidentSupervisoryAction.Status.ANSWERED
        ):
            raise ValidationError("طلب التحديث ليس جاهزًا للإنهاء.")
        if actor.pk not in {request_action.actor_id, request_action.acting_for_id} and not actor.is_superuser:
            raise PermissionDenied
        request_action.status = IncidentSupervisoryAction.Status.RESOLVED
        request_action.resolved_at = timezone.now()
        request_action.save(update_fields=["status", "resolved_at"])
        return request_action

    @classmethod
    @transaction.atomic
    def acknowledge_directive(cls, directive, actor):
        directive = IncidentSupervisoryAction.objects.select_for_update().get(pk=directive.pk)
        if directive.action_type not in {
            IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE,
            IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE,
        }:
            raise ValidationError("الإجراء المحدد ليس توجيهًا.")
        if directive.status != IncidentSupervisoryAction.Status.OPEN:
            raise ValidationError("لا يمكن تأكيد استلام التوجيه في حالته الحالية.")
        if directive.target_user_id != getattr(actor, "pk", None):
            raise PermissionDenied
        directive.status = IncidentSupervisoryAction.Status.ACKNOWLEDGED
        directive.acknowledged_by = actor
        directive.acknowledged_at = timezone.now()
        directive.save(update_fields=["status", "acknowledged_by", "acknowledged_at"])
        return directive

    @classmethod
    @transaction.atomic
    def complete_directive(cls, directive, actor, note):
        directive = IncidentSupervisoryAction.objects.select_for_update().get(pk=directive.pk)
        if directive.action_type not in {
            IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE,
            IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE,
        }:
            raise ValidationError("الإجراء المحدد ليس توجيهًا.")
        if directive.status != IncidentSupervisoryAction.Status.ACKNOWLEDGED:
            raise ValidationError("يجب تأكيد الاستلام قبل تسجيل اكتمال التوجيه.")
        if directive.target_user_id != getattr(actor, "pk", None):
            raise PermissionDenied
        clean_note = str(note or "").strip()
        if not clean_note:
            raise ValidationError("ملاحظة الاكتمال مطلوبة.")
        directive.status = IncidentSupervisoryAction.Status.COMPLETED
        directive.completed_by = actor
        directive.completed_at = timezone.now()
        directive.completion_note = clean_note
        directive.save(update_fields=[
            "status", "completed_by", "completed_at", "completion_note",
        ])
        cls._notify(
            recipients=[directive.actor], actor=actor, title="اكتمل التوجيه",
            message=f"اكتمل التوجيه المرتبط بالبلاغ {directive.incident.incident_number}.",
            section=directive.incident.section,
            url=f"/ops/leadership/incidents/{directive.incident_id}/",
            level=Notification.Level.SUCCESS,
        )
        return directive
