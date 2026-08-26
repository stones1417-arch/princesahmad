from __future__ import annotations

import os
from datetime import time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.distribution.models import DoorAssignment
from apps.distribution.services import DistributionService
from apps.accounts.role_permissions import setup_role_permissions
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.notifications.models import Notification
from apps.ops.incident_routing_service import IncidentRoutingService
from apps.ops.incident_service import IncidentService
from apps.ops.models import (DoorOperationalProfile, DoorShift, Incident, IncidentRoutingEvent,
                             IncidentSupervisoryAction, LeadershipDelegation,
                             MaintenanceRequest)
from apps.ops.supervisory_leadership_service import SupervisoryLeadershipService
from apps.roles.models import Role, UserRole
from apps.scheduling.models import (ShiftAssignment, ShiftOperationalLeadership,
                                    ShiftPlan, ShiftType)

MARKER = "ABWAB_FULL_OPS_DEMO"
SECTION = "male"
USERNAME_PREFIX = "abwab_demo_staff_"
EMPLOYEE_PREFIX = "DEMO-OPS-"
ROLE_SPECS = {
    1: ("shift_supervisor", Employee.JobTitle.FAJR_SUPERVISOR, ShiftAssignment.OperationalRole.SHIFT_HEAD),
    2: ("shift_deputy", Employee.JobTitle.FAJR_DEPUTY, ShiftAssignment.OperationalRole.SHIFT_DEPUTY),
    3: ("incident_supervisor", Employee.JobTitle.SUPPORT_SUPERVISOR, ShiftAssignment.OperationalRole.SUPERVISOR),
    4: ("operations_supervisor", Employee.JobTitle.SUPPORT_SUPERVISOR, ShiftAssignment.OperationalRole.SUPERVISOR),
    5: ("maintenance_shift_supervisor", Employee.JobTitle.TECH_SECRETARY, ShiftAssignment.OperationalRole.SUPERVISOR),
    6: ("doors_department_head", Employee.JobTitle.DOORS_HEAD, ShiftAssignment.OperationalRole.ADMIN),
    7: ("doors_department_deputy", Employee.JobTitle.DOORS_DEPUTY, ShiftAssignment.OperationalRole.ADMIN),
    8: ("senior_administrator", Employee.JobTitle.SENIOR_ADMIN, ShiftAssignment.OperationalRole.SENIOR_ADMIN),
    9: ("general_manager", Employee.JobTitle.GM, ShiftAssignment.OperationalRole.ADMIN),
}
ROLE_INDEX = {spec[0]: index for index, spec in ROLE_SPECS.items()}


def normalize_service_model(result, model_class, stage):
    candidate = result[0] if isinstance(result, tuple) and result else result
    if isinstance(candidate, model_class):
        return candidate
    candidate = getattr(result, "instance", candidate)
    if isinstance(candidate, model_class):
        return candidate
    raise CommandError(f"STAGE={stage} BLOCKED_BY=UNEXPECTED_SERVICE_RESULT")


def require_state(instance, expected, stage):
    actual = getattr(instance, "status", None)
    if actual != expected:
        raise CommandError(
            f"STAGE={stage} EXPECTED_STATE={expected} ACTUAL_STATE={actual} BLOCKED_BY=PRECONDITION"
        )


def get_demo_actor(role_code, *, shift=None):
    index = ROLE_INDEX.get(role_code)
    if not index:
        raise CommandError(f"Unknown demo actor role: {role_code}")
    user = demo_users().filter(username=f"{USERNAME_PREFIX}{index:02d}", is_active=True).select_related("employee").first()
    if not user or not hasattr(user, "employee") or user.employee.operational_section != SECTION:
        raise CommandError(f"Demo actor is not ready: {role_code}")
    if not UserRole.objects.filter(user=user, role__code=role_code, is_active=True).exists():
        raise CommandError(f"Demo actor role is missing: {role_code}")
    if shift and not ShiftAssignment.objects.filter(shift_plan=shift, employee=user.employee, is_confirmed=True).exists():
        raise CommandError(f"Demo actor is outside the demo shift: {role_code}")
    return user


def production_guard(options, *, delete=False):
    if settings.DEBUG or options.get("dry_run") or options.get("validate_only"):
        return
    confirmation = options.get("confirm") if delete else options.get("confirm_demo_seed")
    if not options.get("allow_production_demo") or not confirmation:
        flags = "--allow-production-demo --confirm" if delete else "--allow-production-demo --confirm-demo-seed"
        raise CommandError(f"Production demo operation refused; pass {flags} explicitly.")


def request_for(user):
    return SimpleNamespace(user=user, META={})


def demo_users():
    return get_user_model().objects.filter(username__startswith=USERNAME_PREFIX)


def demo_shift():
    return ShiftPlan.objects.filter(notes__contains=MARKER).first()


def counts():
    shift = demo_shift()
    return {
        "users": demo_users().count(),
        "employees": Employee.objects.filter(employee_number__startswith=EMPLOYEE_PREFIX, notes__contains=MARKER).count(),
        "shifts": ShiftPlan.objects.filter(notes__contains=MARKER).count(),
        "shift_assignments": ShiftAssignment.objects.filter(shift_plan=shift).count() if shift else 0,
        "door_assignments": DoorAssignment.objects.filter(shift_plan=shift, notes__contains=MARKER).count() if shift else 0,
        "incidents": Incident.objects.filter(description__contains=MARKER).count(),
        "maintenance": MaintenanceRequest.objects.filter(description__contains=MARKER).count(),
        "delegations": LeadershipDelegation.objects.filter(reason__contains=MARKER).count(),
        "actions": IncidentSupervisoryAction.objects.filter(note__contains=MARKER).count(),
        "notifications": Notification.objects.filter(user__username__startswith=USERNAME_PREFIX).count(),
    }


@transaction.atomic
def seed(*, dry_run=False, enable_demo_logins=False):
    if not settings.DEBUG and not dry_run and ShiftPlan.objects.filter(is_active=True).exclude(notes__contains=MARKER).exists():
        raise CommandError("PRODUCTION_DEMO_SHIFT_UNSAFE: a real active shift already exists.")
    doors = list(Door.objects.filter(is_active=True).filter(operational_section__in=[SECTION, "shared"]).order_by("sort_order", "pk"))
    if not doors:
        raise CommandError("No active male/shared master doors exist; demo seeding will not create master doors.")
    User = get_user_model()
    setup_role_permissions()
    password = os.environ.get("DEMO_WORKFORCE_PASSWORD")
    if enable_demo_logins and not password:
        raise CommandError("DEMO_WORKFORCE_PASSWORD is required with --enable-demo-logins.")
    users, employees = [], []
    for index in range(1, 56):
        username = f"{USERNAME_PREFIX}{index:02d}"
        user, _ = User.objects.get_or_create(username=username, defaults={"first_name": "Demo", "last_name": f"Operator {index:02d}", "email": f"{username}@example.invalid"})
        user.is_active = True
        user.set_password(password) if enable_demo_logins else user.set_unusable_password()
        user.save()
        role_code, job_title, shift_role = ROLE_SPECS.get(index, (None, Employee.JobTitle.TECHNICIAN if index in range(10, 16) else Employee.JobTitle.MONITOR, ShiftAssignment.OperationalRole.TECHNICIAN if index in range(10, 16) else ShiftAssignment.OperationalRole.MONITOR))
        employee, _ = Employee.objects.update_or_create(employee_number=f"{EMPLOYEE_PREFIX}{index:03d}", defaults={
            "user": user, "full_name": f"موظف تجربة العمليات {index:02d}", "operational_section": SECTION,
            "job_title": job_title, "work_status": Employee.WorkStatus.ACTIVE, "is_active": True,
            "can_work_on_doors": True, "can_execute_maintenance": job_title == Employee.JobTitle.TECHNICIAN,
            "notes": MARKER, "email": f"{username}@example.invalid", "national_id": "", "phone_number": "",
        })
        users.append(user); employees.append((employee, shift_role))
        if role_code:
            role = Role.objects.get(code=role_code)
            UserRole.objects.update_or_create(user=user, role=role, defaults={"is_active": True, "assigned_by": users[0], "notes": MARKER})
    shift_type = ShiftType.objects.filter(is_active=True).order_by("ordering", "name", "pk").first()
    if not shift_type:
        raise CommandError("No active master ShiftType exists; demo seeding will not create one.")
    shift = demo_shift()
    if shift is None:
        candidate_date = timezone.localdate() + timedelta(days=3650)
        while ShiftPlan.objects.filter(date=candidate_date).exists():
            candidate_date += timedelta(days=1)
        shift = ShiftPlan.objects.create(shift_type=shift_type, date=candidate_date, start_time=time(6), end_time=time(14), is_active=True, notes=MARKER, created_by=users[0], activated_by=users[0])
    for employee, shift_role in employees:
        ShiftAssignment.objects.update_or_create(shift_plan=shift, employee=employee, defaults={"role": shift_role, "is_confirmed": True, "notes": MARKER})
    responsibilities = [ShiftOperationalLeadership.Responsibility.INCIDENT_SUPERVISOR, ShiftOperationalLeadership.Responsibility.OPERATIONS_SUPERVISOR, ShiftOperationalLeadership.Responsibility.MAINTENANCE_SUPERVISOR]
    for responsibility, index in zip(responsibilities, [2, 3, 4]):
        ShiftOperationalLeadership.objects.update_or_create(
            shift_plan=shift, responsibility=responsibility,
            defaults={"employee": employees[index][0], "created_by": users[0]},
        )
    profiles = list(DoorOperationalProfile.objects.filter(
        door__in=doors, target_staff_count__gt=0,
    ).select_related("door").order_by("door__sort_order", "door__pk"))
    complete_profile = profiles[0] if profiles else None
    under_profile = next((item for item in profiles if item.target_staff_count >= 2 and item != complete_profile), None)
    zero_profile = next((item for item in profiles if item not in {complete_profile, under_profile}), None)
    if not all((complete_profile, under_profile, zero_profile)):
        raise CommandError("INSUFFICIENT_EXISTING_COVERAGE_CONFIGURATION")
    staff = [item[0] for item in employees[9:]]
    assignment_plan = []
    assignment_plan.extend((complete_profile.door, employee) for employee in staff[:complete_profile.target_staff_count])
    cursor = complete_profile.target_staff_count
    under_count = max(under_profile.target_staff_count - 1, 1)
    assignment_plan.extend((under_profile.door, employee) for employee in staff[cursor:cursor + under_count])
    cursor += under_count
    fallback_doors = [door for door in doors if door.pk not in {
        complete_profile.door_id, under_profile.door_id, zero_profile.door_id,
    }]
    if not fallback_doors and cursor < len(staff):
        raise CommandError("INSUFFICIENT_DOORS_FOR_DETERMINISTIC_DISTRIBUTION")
    for position, employee in enumerate(staff[cursor:]):
        assignment_plan.append((fallback_doors[position % len(fallback_doors)], employee))
    for door, employee in assignment_plan:
        if not DoorAssignment.objects.filter(shift_plan=shift, employee=employee, is_active=True).exists():
            with (
                patch("apps.distribution.services.NotificationService.success"),
                patch("apps.distribution.services._schedule_assignment_notification"),
            ):
                DistributionService.create_assignment(
                    shift_plan=shift, door=door, employee=employee, assigned_by=users[0],
                    role=(DoorAssignment.Role.TECHNICIAN if employee.can_execute_maintenance else DoorAssignment.Role.MONITOR),
                    section=SECTION, notes=MARKER, history_reason=MARKER,
                    request=request_for(users[0]),
                )
    for door in doors[:min(len(doors), 12)]:
        DoorShift.objects.update_or_create(shift_plan=shift, door_number=door.door_number, defaults={"sort_order": door.sort_order, "section": SECTION, "state": DoorShift.DoorState.OPEN, "is_active": True, "notes": MARKER})
    result = counts()
    if dry_run:
        transaction.set_rollback(True)
    return result


def validate():
    data = counts(); errors = []
    if data["users"] != 55: errors.append(f"users={data['users']} expected=55")
    if data["employees"] != 55: errors.append(f"employees={data['employees']} expected=55")
    if data["shifts"] != 1: errors.append(f"shifts={data['shifts']} expected=1")
    if data["shift_assignments"] != 55: errors.append(f"shift_assignments={data['shift_assignments']} expected=55")
    shift = demo_shift()
    if shift and ShiftOperationalLeadership.objects.filter(shift_plan=shift).count() != 3: errors.append("operational leadership is incomplete")
    if Employee.objects.filter(employee_number__startswith=EMPLOYEE_PREFIX).exclude(notes__contains=MARKER).exists(): errors.append("unmarked employee collides with demo prefix")
    data["demo_exists"] = bool(shift)
    data["shift"] = shift.pk if shift else None
    data["general_leadership"] = ShiftAssignment.objects.filter(
        shift_plan=shift, role__in=(ShiftAssignment.OperationalRole.SHIFT_HEAD, ShiftAssignment.OperationalRole.SHIFT_DEPUTY),
    ).count() if shift else 0
    data["specialist_leadership"] = ShiftOperationalLeadership.objects.filter(shift_plan=shift).count() if shift else 0
    data["supervisory_roles"] = UserRole.objects.filter(
        user__username__startswith=USERNAME_PREFIX,
        role__code__in=("doors_department_head", "doors_department_deputy", "senior_administrator", "general_manager"),
        is_active=True,
    ).count()
    from apps.accounts.role_permissions import ROLE_PERMISSIONS_BY_CODE
    readiness = True
    for role_code in ROLE_INDEX:
        try:
            actor = get_demo_actor(role_code, shift=shift)
        except CommandError:
            readiness = False
            continue
        required = ROLE_PERMISSIONS_BY_CODE[role_code].permissions
        if any(not actor.has_perm(permission) for permission in required):
            readiness = False
    data["demo_role_permission_readiness"] = readiness
    if not readiness:
        errors.append("demo role permissions are incomplete")
    incident = Incident.objects.filter(description__contains=MARKER).first()
    maintenance = MaintenanceRequest.objects.filter(description__contains=MARKER).first()
    data.update({
        "incident": incident.pk if incident else None,
        "incident_status": incident.status if incident else None,
        "incident_assignee": incident.assigned_to.username if incident and incident.assigned_to else None,
        "escalation": incident.escalation_level if incident else None,
        "maintenance_id": maintenance.pk if maintenance else None,
        "maintenance_status": maintenance.status if maintenance else None,
    })
    if shift:
        from apps.ops.engineering_center_service import EngineeringCenterService
        rows = EngineeringCenterService.build(active_shift=shift, allowed_sections=[SECTION])["doors"]
        data["coverage_cases"] = {
            "complete": sum(row.staff_coverage_level in {"complete", "surplus"} for row in rows),
            "under": sum(row.staff_coverage_level in {"partial", "low"} for row in rows),
            "zero": sum(row.staff_coverage_level == "uncovered" for row in rows),
        }
    return data, errors


@transaction.atomic
def run_scenario(*, scenario="full-cycle", stop_before_final_close=True, dry_run=False):
    shift = demo_shift()
    if not shift:
        raise CommandError("Demo baseline is absent; run seed_full_operations_demo first.")
    shift_head = get_demo_actor("shift_supervisor", shift=shift)
    head = get_demo_actor("doors_department_head", shift=shift)
    deputy = get_demo_actor("doors_department_deputy", shift=shift)
    senior_admin = get_demo_actor("senior_administrator", shift=shift)
    gm = get_demo_actor("general_manager", shift=shift)
    operations_supervisor = get_demo_actor("operations_supervisor", shift=shift)
    maintenance_supervisor = get_demo_actor("maintenance_shift_supervisor", shift=shift)
    door_shift = DoorShift.objects.filter(shift_plan=shift).first()
    door = Door.objects.filter(door_number=door_shift.door_number).first()
    assignment = DoorAssignment.objects.filter(shift_plan=shift, door=door).first()
    incident = Incident.objects.filter(description__contains=MARKER).first()
    if scenario == "baseline":
        result = counts()
        if dry_run: transaction.set_rollback(True)
        return result
    if incident is None:
        incident = IncidentService.create(request=request_for(shift_head), active_shift=shift, door=door, door_shift=door_shift, assignment=assignment, section=SECTION, description=f"{MARKER}: operational door fault", incident_type=Incident.IncidentType.DOOR_FAULT, priority=Incident.Priority.CRITICAL)
    incident_supervisor = get_demo_actor("incident_supervisor", shift=shift)
    if incident.assigned_to_id != incident_supervisor.pk:
        raise CommandError("STAGE=INCIDENT_ROUTING EXPECTED_STATE=incident_supervisor ACTUAL_STATE=other BLOCKED_BY=ROUTING")
    if scenario in {"incident-maintenance", "full-cycle"}:
        if incident.status == Incident.Status.NEW:
            require_state(incident, Incident.Status.NEW, "INCIDENT_PROCESSING")
            incident = normalize_service_model(IncidentService.update_status(incident=incident, new_status=Incident.Status.IN_PROGRESS, user=incident_supervisor, reason=f"{MARKER}: processing started"), Incident, "INCIDENT_PROCESSING")
        if not IncidentRoutingEvent.objects.filter(incident=incident, event_type=IncidentRoutingEvent.EventType.PROCESSING_STARTED, note__contains=MARKER).exists():
            IncidentRoutingService.add_shift_update(incident, incident_supervisor, f"{MARKER}: تمت مباشرة البلاغ ميدانيًا")
        incident = IncidentRoutingService.escalate_incident(incident, incident_supervisor, f"{MARKER}: department escalation") if incident.escalation_level == Incident.EscalationLevel.NONE else incident
        now = timezone.now()
        maintenance = MaintenanceRequest.objects.filter(source_incident=incident).first()
        if not maintenance:
            maintenance = IncidentRoutingService.convert_to_maintenance(incident, request_for(incident_supervisor), now + timedelta(minutes=5), now + timedelta(hours=2), actor=incident_supervisor)
        from apps.ops.maintenance_service import MaintenanceService
        if maintenance.status == MaintenanceRequest.Status.NEW:
            require_state(maintenance, MaintenanceRequest.Status.NEW, "OPERATIONS_APPROVED")
            maintenance = normalize_service_model(MaintenanceService.update_status(request=request_for(operations_supervisor), maintenance=maintenance, new_status=MaintenanceRequest.Status.APPROVED, user=operations_supervisor, reason=f"{MARKER}: operations approved"), MaintenanceRequest, "OPERATIONS_APPROVED")
        if maintenance.status == MaintenanceRequest.Status.APPROVED:
            technician = Employee.objects.filter(employee_number__startswith=EMPLOYEE_PREFIX, can_execute_maintenance=True).first()
            maintenance.technician = technician.user
            maintenance.technician_name = technician.full_name
            maintenance.assigned_by = maintenance_supervisor
            maintenance.save()
            require_state(maintenance, MaintenanceRequest.Status.APPROVED, "MAINTENANCE_SCHEDULED")
            maintenance = normalize_service_model(MaintenanceService.update_status(request=request_for(maintenance_supervisor), maintenance=maintenance, new_status=MaintenanceRequest.Status.ASSIGNED, user=maintenance_supervisor, reason=f"{MARKER}: technician scheduled"), MaintenanceRequest, "MAINTENANCE_SCHEDULED")
        if maintenance.status == MaintenanceRequest.Status.ASSIGNED:
            require_state(maintenance, MaintenanceRequest.Status.ASSIGNED, "MAINTENANCE_STARTED")
            maintenance = normalize_service_model(MaintenanceService.update_status(request=request_for(maintenance_supervisor), maintenance=maintenance, new_status=MaintenanceRequest.Status.IN_PROGRESS, user=maintenance_supervisor, reason=f"{MARKER}: maintenance started"), MaintenanceRequest, "MAINTENANCE_STARTED")
        if maintenance.status == MaintenanceRequest.Status.IN_PROGRESS:
            require_state(maintenance, MaintenanceRequest.Status.IN_PROGRESS, "MAINTENANCE_COMPLETED")
            maintenance = normalize_service_model(MaintenanceService.update_status(request=request_for(maintenance.technician), maintenance=maintenance, new_status=MaintenanceRequest.Status.DONE, user=maintenance.technician, closing_notes=f"{MARKER}: maintenance completed", reason=f"{MARKER}: technician completed"), MaintenanceRequest, "MAINTENANCE_COMPLETED")
    if scenario in {"supervisory", "full-cycle"}:
        if incident.escalation_level == Incident.EscalationLevel.NONE:
            incident = IncidentRoutingService.escalate_incident(
                incident, incident_supervisor, f"{MARKER}: department escalation"
            )
        if not LeadershipDelegation.objects.filter(reason__contains=MARKER, revoked_at__isnull=True, ends_at__gt=timezone.now()).exists():
            SupervisoryLeadershipService.create_delegation(principal=head, delegate=deputy, section=SECTION, starts_at=timezone.now()-timedelta(minutes=1), ends_at=timezone.now()+timedelta(days=1), reason=MARKER)
        def action(kind):
            return IncidentSupervisoryAction.objects.filter(incident=incident, action_type=kind, note__contains=MARKER).first()
        update = action(IncidentSupervisoryAction.ActionType.REQUEST_UPDATE)
        if not update:
            update = SupervisoryLeadershipService.create_action(incident=incident, actor=head, action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE, note=f"{MARKER}: status update requested", target_user=incident_supervisor)
        if update.status == IncidentSupervisoryAction.Status.OPEN:
            SupervisoryLeadershipService.respond_to_update_request(update, incident_supervisor, f"{MARKER}: field response")
            update.refresh_from_db()
        if update.status == IncidentSupervisoryAction.Status.ANSWERED:
            SupervisoryLeadershipService.resolve_update_request(update, head)
        directive = action(IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE)
        if not directive:
            directive = SupervisoryLeadershipService.create_action(incident=incident, actor=head, action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE, note=f"{MARKER}: supervisory directive", target_user=incident_supervisor)
        if directive.status == IncidentSupervisoryAction.Status.OPEN:
            SupervisoryLeadershipService.acknowledge_directive(directive, incident_supervisor); directive.refresh_from_db()
        if directive.status == IncidentSupervisoryAction.Status.ACKNOWLEDGED:
            SupervisoryLeadershipService.complete_directive(directive, incident_supervisor, f"{MARKER}: directive completed")
        if not action(IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_NOTE):
            SupervisoryLeadershipService.create_action(incident=incident, actor=senior_admin, action_type=IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_NOTE, note=f"{MARKER}: administrative note")
        if not action(IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT):
            SupervisoryLeadershipService.create_action(incident=incident, actor=senior_admin, action_type=IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT, note=f"{MARKER}: administrative alert")
        if not IncidentSupervisoryAction.objects.filter(incident=incident, actor=deputy, note__contains=MARKER).exists():
            SupervisoryLeadershipService.create_action(incident=incident, actor=deputy, action_type=IncidentSupervisoryAction.ActionType.SUPERVISORY_NOTE, note=f"{MARKER}: delegated deputy action")
        if incident.escalation_level != Incident.EscalationLevel.GENERAL_MANAGER:
            incident = IncidentRoutingService.escalate_incident(incident, head, f"{MARKER}: executive escalation")
        executive = action(IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE)
        if not executive:
            executive = SupervisoryLeadershipService.create_action(incident=incident, actor=gm, action_type=IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE, note=f"{MARKER}: executive directive", target_user=head)
        if executive.status == IncidentSupervisoryAction.Status.OPEN:
            SupervisoryLeadershipService.acknowledge_directive(executive, head); executive.refresh_from_db()
        if executive.status == IncidentSupervisoryAction.Status.ACKNOWLEDGED:
            SupervisoryLeadershipService.complete_directive(executive, head, f"{MARKER}: executive directive completed")
    if not stop_before_final_close and incident.status != Incident.Status.CLOSED:
        IncidentService.close_incident(incident=incident, user=incident_supervisor, closing_notes=f"{MARKER}: scenario closed")
    result = counts()
    result.update({
        "stop_state": ("AWAITING_INCIDENT_SUPERVISOR_FINAL_VERIFICATION" if stop_before_final_close else "FINAL_CLOSED"),
        "demo_incident_id": incident.pk,
        "demo_incident_number": incident.incident_number,
        "demo_maintenance_id": MaintenanceRequest.objects.filter(source_incident=incident).values_list("pk", flat=True).first(),
    })
    if dry_run: transaction.set_rollback(True)
    return result


@transaction.atomic
def delete(*, dry_run=False):
    before = counts()
    shift_ids = list(ShiftPlan.objects.filter(notes__contains=MARKER).values_list("pk", flat=True))
    user_ids = list(demo_users().values_list("pk", flat=True))
    employee_ids = list(Employee.objects.filter(
        employee_number__startswith=EMPLOYEE_PREFIX, notes__contains=MARKER,
    ).values_list("pk", flat=True))
    unsafe_links = {
        "incidents": Incident.objects.exclude(description__contains=MARKER).filter(
            Q(created_by_id__in=user_ids) | Q(assigned_to_id__in=user_ids)
            | Q(closed_by_id__in=user_ids) | Q(escalated_by_id__in=user_ids)
        ).exists(),
        "maintenance": MaintenanceRequest.objects.exclude(description__contains=MARKER).filter(
            Q(created_by_id__in=user_ids) | Q(approved_by_id__in=user_ids)
            | Q(assigned_by_id__in=user_ids) | Q(technician_id__in=user_ids)
        ).exists(),
        "door_assignments": DoorAssignment.objects.filter(employee_id__in=employee_ids).exclude(
            shift_plan_id__in=shift_ids, notes__contains=MARKER,
        ).exists(),
        "shift_assignments": ShiftAssignment.objects.filter(employee_id__in=employee_ids).exclude(
            shift_plan_id__in=shift_ids,
        ).exists(),
        "leadership_actions": IncidentSupervisoryAction.objects.exclude(
            incident__description__contains=MARKER,
        ).filter(
            Q(actor_id__in=user_ids) | Q(acting_for_id__in=user_ids)
            | Q(target_user_id__in=user_ids),
        ).exists(),
        "delegations": LeadershipDelegation.objects.exclude(reason__contains=MARKER).filter(
            Q(principal_id__in=user_ids) | Q(delegate_id__in=user_ids)
            | Q(created_by_id__in=user_ids),
        ).exists(),
        "shift_plans": ShiftPlan.objects.exclude(notes__contains=MARKER).filter(
            Q(created_by_id__in=user_ids) | Q(activated_by_id__in=user_ids)
            | Q(finished_by_id__in=user_ids),
        ).exists(),
    }
    blockers = [name for name, exists in unsafe_links.items() if exists]
    if blockers:
        raise CommandError(
            "DELETE_SAFETY_BLOCKED: demo identities are linked to non-demo data: "
            + ", ".join(blockers)
        )
    demo_incidents = Incident.objects.filter(description__contains=MARKER)
    demo_actions = IncidentSupervisoryAction.objects.filter(incident__in=demo_incidents)
    demo_actions.filter(parent__isnull=False).delete()
    demo_actions.delete()
    MaintenanceRequest.objects.filter(source_incident__in=demo_incidents).delete()
    demo_incidents.delete()
    LeadershipDelegation.objects.filter(reason__contains=MARKER).delete()
    Notification.objects.filter(user__username__startswith=USERNAME_PREFIX).delete()
    DoorShift.objects.filter(shift_plan_id__in=shift_ids, notes__contains=MARKER).delete()
    DoorAssignment.objects.filter(shift_plan_id__in=shift_ids, notes__contains=MARKER).delete()
    ShiftPlan.objects.filter(pk__in=shift_ids).delete()
    Employee.objects.filter(employee_number__startswith=EMPLOYEE_PREFIX, notes__contains=MARKER).delete()
    demo_users().delete()
    Role.objects.filter(description=MARKER, user_assignments__isnull=True).delete()
    ShiftType.objects.filter(name__contains=MARKER, shift_plans__isnull=True).delete()
    if dry_run: transaction.set_rollback(True)
    return before
