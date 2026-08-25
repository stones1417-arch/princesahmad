"""Central role catalog and access helpers for the platform.

This module intentionally uses the existing ``apps.roles`` Role, Group and
Permission integration instead of introducing another authorization model.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import QuerySet

from apps.roles.models import Role
from apps.roles.services.access_control import user_has_role as _user_has_role
from apps.roles.services.section_access import (
    can_view_section,
    filter_assignments_for_user,
    filter_doors_for_user,
    filter_employees_for_user,
    get_allowed_sections,
    has_institutional_scope,
)
from apps.roles.services.permission_registry import PlatformPermissions


@dataclass(frozen=True)
class RolePermissionDefinition:
    code: str
    name: str
    description: str
    permissions: tuple[str, ...]
    operational_section: str = Role.OperationalSection.ALL
    admin_access: bool = False


P = PlatformPermissions


ROLE_PERMISSIONS: tuple[RolePermissionDefinition, ...] = (
    RolePermissionDefinition(
        code="system_admin",
        name="مدير النظام",
        description="إدارة المنصة والمستخدمين والأدوار والنسخ الاحتياطية.",
        permissions=tuple(
            value
            for name, value in vars(P).items()
            if name.isupper() and isinstance(value, str)
        ),
        admin_access=True,
    ),
    RolePermissionDefinition(
        code="general_manager",
        name="المدير العام",
        description="إشراف مؤسسي واعتماد التقارير دون إدارة النظام.",
        permissions=(
            P.VIEW_EMPLOYEES, P.VIEW_SHIFTS, P.VIEW_DISTRIBUTION,
            P.VIEW_DOORS, P.VIEW_MAINTENANCE_REQUESTS, P.VIEW_REPORTS,
            P.APPROVE_REPORT, P.EXPORT_REPORT, P.VIEW_SYSTEM_LOGS,
        ),
    ),
    RolePermissionDefinition(
        code="doors_department_head",
        name="رئيس قسم الأبواب",
        description="إدارة تشغيل الأبواب والورديات والتوزيع ضمن نطاق القسم.",
        permissions=(
            P.VIEW_EMPLOYEES, P.CREATE_EMPLOYEE, P.UPDATE_EMPLOYEE,
            P.DISABLE_EMPLOYEE, P.VIEW_SHIFTS, P.CREATE_SHIFT,
            P.ACTIVATE_SHIFT, P.FINISH_SHIFT, P.VIEW_DISTRIBUTION,
            P.ASSIGN_EMPLOYEES, P.APPROVE_DISTRIBUTION, P.VIEW_DOORS,
            P.OPEN_DOOR, P.CLOSE_DOOR, P.MOVE_DOOR_TO_MAINTENANCE,
            P.VIEW_MAINTENANCE_REQUESTS, P.CREATE_MAINTENANCE_REQUEST,
            P.APPROVE_MAINTENANCE_REQUEST, P.VIEW_REPORTS,
            P.CREATE_REPORT, P.UPDATE_REPORT, P.EXPORT_REPORT,
            P.CREATE_INCIDENT, P.UPDATE_INCIDENT,
            P.ASSIGN_INCIDENT, P.ESCALATE_INCIDENT,
            P.CONVERT_INCIDENT_TO_MAINTENANCE, P.CLOSE_INCIDENT,
        ),
    ),
    RolePermissionDefinition(
        code="doors_department_deputy",
        name="وكيل رئيس قسم الأبواب",
        description="مساندة رئيس القسم في العمليات اليومية ضمن نطاق القسم.",
        permissions=(
            P.VIEW_EMPLOYEES, P.UPDATE_EMPLOYEE, P.VIEW_SHIFTS,
            P.CREATE_SHIFT, P.ACTIVATE_SHIFT, P.FINISH_SHIFT,
            P.VIEW_DISTRIBUTION, P.ASSIGN_EMPLOYEES,
            P.VIEW_DOORS, P.OPEN_DOOR, P.CLOSE_DOOR,
            P.MOVE_DOOR_TO_MAINTENANCE, P.VIEW_MAINTENANCE_REQUESTS,
            P.CREATE_MAINTENANCE_REQUEST, P.VIEW_REPORTS,
            P.CREATE_REPORT, P.UPDATE_REPORT, P.EXPORT_REPORT,
            P.CREATE_INCIDENT, P.UPDATE_INCIDENT,
            P.ASSIGN_INCIDENT, P.ESCALATE_INCIDENT,
            P.CONVERT_INCIDENT_TO_MAINTENANCE, P.CLOSE_INCIDENT,
        ),
    ),
    RolePermissionDefinition(
        code="senior_administrator",
        name="كبير الإداريين",
        description="تنسيق البيانات الإدارية والتقارير دون اعتماد تشغيلي.",
        permissions=(
            P.VIEW_EMPLOYEES, P.VIEW_SHIFTS, P.VIEW_DISTRIBUTION,
            P.VIEW_DOORS, P.VIEW_REPORTS, P.CREATE_REPORT,
            P.UPDATE_REPORT, P.EXPORT_REPORT,
        ),
    ),
    RolePermissionDefinition(
        code="hr_manager",
        name="مسؤول الموارد البشرية",
        description="إدارة بيانات الموظفين ضمن نطاق القسم فقط.",
        permissions=(
            P.VIEW_EMPLOYEES, P.CREATE_EMPLOYEE, P.UPDATE_EMPLOYEE,
            P.DISABLE_EMPLOYEE, P.VIEW_REPORTS, P.EXPORT_REPORT,
        ),
    ),
    RolePermissionDefinition(
        code="shift_supervisor",
        name="مشرف الوردية",
        description="إدارة الوردية والتسكين وحالة الأبواب ضمن نطاق القسم.",
        permissions=(
            P.VIEW_EMPLOYEES, P.VIEW_SHIFTS, P.ACTIVATE_SHIFT,
            P.FINISH_SHIFT, P.VIEW_DISTRIBUTION, P.ASSIGN_EMPLOYEES,
            P.APPROVE_DISTRIBUTION, P.VIEW_DOORS, P.OPEN_DOOR,
            P.CLOSE_DOOR, P.MOVE_DOOR_TO_MAINTENANCE,
            P.VIEW_MAINTENANCE_REQUESTS, P.CREATE_MAINTENANCE_REQUEST,
            P.VIEW_REPORTS, P.CREATE_REPORT, P.UPDATE_REPORT,
            P.CREATE_INCIDENT, P.UPDATE_INCIDENT,
            P.ASSIGN_INCIDENT, P.ESCALATE_INCIDENT,
            P.CONVERT_INCIDENT_TO_MAINTENANCE, P.CLOSE_INCIDENT,
        ),
    ),
    RolePermissionDefinition(
        code="shift_deputy",
        name="نائب مشرف الوردية",
        description="مساندة مشرف الوردية دون اعتماد أو إدارة النظام.",
        permissions=(
            P.VIEW_EMPLOYEES, P.VIEW_SHIFTS, P.VIEW_DISTRIBUTION,
            P.ASSIGN_EMPLOYEES, P.VIEW_DOORS, P.OPEN_DOOR,
            P.CLOSE_DOOR, P.MOVE_DOOR_TO_MAINTENANCE,
            P.VIEW_MAINTENANCE_REQUESTS, P.CREATE_MAINTENANCE_REQUEST,
            P.VIEW_REPORTS, P.CREATE_REPORT,
            P.CREATE_INCIDENT,
            P.UPDATE_INCIDENT, P.ESCALATE_INCIDENT,
            P.CONVERT_INCIDENT_TO_MAINTENANCE, P.CLOSE_INCIDENT,
        ),
    ),
    RolePermissionDefinition(
        code="incident_supervisor",
        name="مشرف البلاغات",
        description="قيادة البلاغات والتغطية التشغيلية في الوردية دون توزيع الموظفين.",
        permissions=(
            P.VIEW_SHIFTS, P.VIEW_DOORS, P.CREATE_INCIDENT, P.UPDATE_INCIDENT,
            P.ESCALATE_INCIDENT, P.CONVERT_INCIDENT_TO_MAINTENANCE,
            P.CLOSE_INCIDENT, P.VIEW_MAINTENANCE_REQUESTS,
            P.VIEW_DOOR_COVERAGE_SETTINGS, P.CHANGE_DOOR_COVERAGE_SETTINGS,
        ),
    ),
    RolePermissionDefinition(
        code="operations_supervisor",
        name="مشرف العمليات",
        description="مراجعة واعتماد وتحويل طلبات الصيانة ضمن الوردية.",
        permissions=(
            P.VIEW_SHIFTS, P.VIEW_DOORS, P.VIEW_MAINTENANCE_REQUESTS,
            P.APPROVE_MAINTENANCE_REQUEST,
        ),
    ),
    RolePermissionDefinition(
        code="maintenance_shift_supervisor",
        name="مشرف الصيانة",
        description="جدولة وتنفيذ وإكمال الصيانة المعتمدة ضمن الوردية.",
        permissions=(
            P.VIEW_SHIFTS, P.VIEW_DOORS, P.VIEW_MAINTENANCE_REQUESTS,
            P.ASSIGN_MAINTENANCE_TECHNICIAN, P.CLOSE_MAINTENANCE_REQUEST,
        ),
    ),
    RolePermissionDefinition(
        code="distribution_supervisor",
        name="مشرف التوزيع",
        description="إدارة التوزيع ضمن نطاق القسم دون إدارة المستخدمين.",
        permissions=(
            P.VIEW_EMPLOYEES, P.VIEW_SHIFTS, P.VIEW_DISTRIBUTION,
            P.ASSIGN_EMPLOYEES, P.APPROVE_DISTRIBUTION, P.VIEW_DOORS,
            P.VIEW_REPORTS,
        ),
    ),
    RolePermissionDefinition(
        code="maintenance_manager",
        name="مسؤول الصيانة",
        description="إدارة بلاغات الصيانة ضمن نطاق القسم.",
        permissions=(
            P.VIEW_DOORS, P.VIEW_MAINTENANCE_REQUESTS,
            P.CREATE_MAINTENANCE_REQUEST, P.APPROVE_MAINTENANCE_REQUEST,
            P.ASSIGN_MAINTENANCE_TECHNICIAN,
            P.CLOSE_MAINTENANCE_REQUEST, P.VIEW_REPORTS,
            P.CREATE_INCIDENT, P.UPDATE_INCIDENT,
        ),
    ),
    RolePermissionDefinition(
        code="employee",
        name="الموظف",
        description="وصول تشغيلي محدود إلى بيانات القسم المعتمدة له.",
        permissions=(
            P.VIEW_SHIFTS, P.VIEW_DISTRIBUTION, P.VIEW_DOORS,
            P.CREATE_MAINTENANCE_REQUEST,
        ),
    ),
)


ROLE_PERMISSIONS_BY_CODE = {
    definition.code: definition
    for definition in ROLE_PERMISSIONS
}


def setup_role_permissions() -> list[Role]:
    """Create or update the central role catalog using the existing service."""
    from apps.roles.services.role_manager import create_or_update_role

    return [
        create_or_update_role(
            code=definition.code,
            name=definition.name,
            description=definition.description,
            permission_codes=list(definition.permissions),
            is_system_role=True,
            is_active=True,
            operational_section=None,
        )
        for definition in ROLE_PERMISSIONS
    ]


def user_has_role(user, role_code: str) -> bool:
    """Return whether a user has an active institutional role."""
    return _user_has_role(user, role_code)


def user_can_access_section(user, section: str) -> bool:
    """Return whether the user's active role scope permits a section."""
    return can_view_section(user, section)


def filter_queryset_by_section(queryset: QuerySet, user) -> QuerySet:
    """Apply server-side scope filtering for employees, doors, or assignments."""
    model_name = queryset.model._meta.model_name
    app_label = queryset.model._meta.app_label

    if app_label == "hr" and model_name == "employee":
        return filter_employees_for_user(queryset, user)
    if app_label == "locations" and model_name == "door":
        return filter_doors_for_user(queryset, user)
    if app_label == "distribution" and model_name == "doorassignment":
        return filter_assignments_for_user(queryset, user)

    if not has_institutional_scope(user):
        return queryset

    allowed_sections = get_allowed_sections(user)
    field_names = {
        field.name
        for field in queryset.model._meta.get_fields()
    }
    if "operational_section" in field_names:
        return queryset.filter(operational_section__in=allowed_sections)
    if "section" in field_names:
        return queryset.filter(section__in=allowed_sections)
    return queryset.none()


def user_can_access_object(user, obj) -> bool:
    """Check server-side operational scope for an Employee, Door, or assignment."""
    if not obj or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not has_institutional_scope(user):
        return False

    section = getattr(obj, "section", None) or getattr(
        obj,
        "operational_section",
        None,
    )
    if section == "shared":
        return bool(get_allowed_sections(user))
    return user_can_access_section(user, section)
