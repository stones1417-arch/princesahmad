from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog
from apps.roles.services.access_control import user_has_permission, user_has_role
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.section_access import get_allowed_sections
from apps.scheduling.models import ShiftAssignment, ShiftOperationalLeadership


RESPONSIBILITY_ROLE = {
    value: value for value, _label in ShiftOperationalLeadership.Responsibility.choices
}


def leadership_for_shift(shift_plan):
    if not shift_plan:
        return {}
    return {item.responsibility: item for item in (
        shift_plan.operational_leadership.select_related("employee", "employee__user")
    )}


def resolve_shift_leader(shift_plan, responsibility):
    if not shift_plan or responsibility not in RESPONSIBILITY_ROLE:
        return None
    assignment = (
        ShiftOperationalLeadership.objects.select_related("employee__user")
        .filter(shift_plan=shift_plan, responsibility=responsibility).first()
    )
    if not assignment or not assignment.employee.user_id:
        return None
    return assignment.employee.user


@transaction.atomic
def assign_shift_operational_leader(
    *, shift_plan, responsibility, employee, actor, request=None
):
    if responsibility not in RESPONSIBILITY_ROLE:
        raise ValidationError({"responsibility": "مسؤولية تشغيلية غير صالحة."})
    if not actor.is_superuser and not user_has_permission(
        actor, PlatformPermissions.ASSIGN_EMPLOYEES
    ):
        raise PermissionDenied("لا تملك صلاحية تعيين القيادة التشغيلية.")
    if not employee or not employee.is_active or not employee.user_id:
        raise ValidationError({"employee": "يجب اختيار موظف نشط مرتبط بحساب."})
    if not employee.user.is_active:
        raise ValidationError({"employee": "حساب الموظف غير نشط."})
    if not user_has_role(employee.user, RESPONSIBILITY_ROLE[responsibility]):
        raise ValidationError({"employee": "الموظف لا يحمل الدور المطلوب للمسؤولية."})
    if not ShiftAssignment.objects.filter(
        shift_plan=shift_plan, employee=employee, is_confirmed=True,
        employee__is_active=True,
    ).exists():
        raise ValidationError({"employee": "الموظف ليس عضوًا مؤكدًا في هذه الوردية."})
    if not actor.is_superuser and employee.operational_section not in get_allowed_sections(actor):
        raise PermissionDenied("الموظف خارج نطاق القسم التشغيلي.")
    current = (
        ShiftOperationalLeadership.objects.select_for_update().select_related("employee")
        .filter(shift_plan=shift_plan, responsibility=responsibility).first()
    )
    previous_name = current.employee.full_name if current else "غير معيّن"
    assignment, _created = ShiftOperationalLeadership.objects.update_or_create(
        shift_plan=shift_plan, responsibility=responsibility,
        defaults={"employee": employee, "created_by": actor},
    )
    log_activity(
        user=actor, module="القيادة التشغيلية للوردية",
        action=(SystemActivityLog.ActionType.UPDATE if current else SystemActivityLog.ActionType.CREATE),
        description=(f"تم تعيين {assignment.get_responsibility_display()} للوردية "
                     f"من {previous_name} إلى {employee.full_name}."),
        request=request,
    )
    return assignment


@transaction.atomic
def remove_shift_operational_leader(*, shift_plan, responsibility, actor, request=None):
    if responsibility not in RESPONSIBILITY_ROLE:
        raise ValidationError({"responsibility": "مسؤولية تشغيلية غير صالحة."})
    if not actor.is_superuser and not user_has_permission(
        actor, PlatformPermissions.ASSIGN_EMPLOYEES
    ):
        raise PermissionDenied("لا تملك صلاحية تعيين القيادة التشغيلية.")
    assignment = (
        ShiftOperationalLeadership.objects.select_for_update()
        .select_related("employee")
        .filter(shift_plan=shift_plan, responsibility=responsibility)
        .first()
    )
    if not assignment:
        return False
    label = assignment.get_responsibility_display()
    employee_name = assignment.employee.full_name
    assignment.delete()
    log_activity(
        user=actor,
        module="القيادة التشغيلية للوردية",
        action=SystemActivityLog.ActionType.DELETE,
        description=f"تمت إزالة {label} ({employee_name}) من الوردية.",
        request=request,
    )
    return True
