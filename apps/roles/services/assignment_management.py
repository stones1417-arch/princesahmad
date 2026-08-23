from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.dashboard.activity_logger import log_activity
from apps.hr.models import Employee
from apps.roles.models import Role
from apps.roles.services.access_control import (
    get_user_permission_codes,
    user_can_access_operational_section,
    user_has_permission,
)
from apps.roles.services.permission_presentation import role_permission_codes
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.role_manager import assign_role_to_user, remove_role_from_user


@transaction.atomic
def assign_employee_role(*, actor, employee, role, section: str):
    if not actor or not user_has_permission(actor, PlatformPermissions.MANAGE_ROLES):
        raise PermissionDenied("غير مصرح لك بإدارة الأدوار.")
    if not employee or not employee.user_id or not role or not role.is_active:
        raise ValidationError("الموظف والدور النشط مطلوبان.")
    if actor.pk == employee.user_id:
        raise PermissionDenied("لا يمكن للمستخدم منح دور لنفسه.")
    if section not in Employee.OperationalSection.values:
        raise ValidationError("القسم التشغيلي غير صالح.")
    if section != employee.operational_section:
        raise ValidationError("القسم المختار لا يطابق قسم الموظف المسجل.")
    if not user_can_access_operational_section(actor, section):
        raise PermissionDenied("لا يمكنك إدارة موظف خارج نطاق قسمك.")
    if role.operational_section not in {Role.OperationalSection.ALL, section}:
        raise ValidationError("نطاق الدور لا يطابق القسم التشغيلي للموظف.")
    actor_permissions = get_user_permission_codes(actor)
    if not role_permission_codes(role).issubset(actor_permissions):
        raise PermissionDenied("لا يمكنك منح صلاحيات لا تملكها.")
    assignment = assign_role_to_user(
        user=employee.user,
        role_code=role.code,
        assigned_by=actor,
        notes="إسناد من واجهة تسكين الموظف والصلاحيات",
    )
    log_activity(
        user=actor,
        module="roles",
        action="update",
        description=f"إسناد الدور {role.name} إلى {employee.full_name}",
    )
    return assignment


@transaction.atomic
def remove_employee_role(*, actor, employee, role):
    if not actor or not user_has_permission(actor, PlatformPermissions.MANAGE_ROLES):
        raise PermissionDenied("غير مصرح لك بإدارة الأدوار.")
    if not employee or not employee.user_id or not role:
        raise ValidationError("الموظف والدور مطلوبان.")
    if actor.pk == employee.user_id:
        raise PermissionDenied("لا يمكن للمستخدم تعديل أدواره بنفسه.")
    if not user_can_access_operational_section(actor, employee.operational_section):
        raise PermissionDenied("لا يمكنك إدارة موظف خارج نطاق قسمك.")
    if not role_permission_codes(role).issubset(get_user_permission_codes(actor)):
        raise PermissionDenied("لا يمكنك إزالة دور بصلاحيات تتجاوز صلاحياتك.")
    removed = remove_role_from_user(user=employee.user, role_code=role.code)
    if not removed:
        raise ValidationError("الدور غير مسند لهذا الموظف.")
    log_activity(
        user=actor,
        module="roles",
        action="update",
        description=f"إزالة الدور {role.name} من {employee.full_name}",
    )
    return True
