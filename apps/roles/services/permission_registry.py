from __future__ import annotations


PERMISSION_APP_LABEL = "roles"


class PlatformPermissions:
    """الرموز الكاملة لصلاحيات المنصة."""

    VIEW_EMPLOYEES = "roles.view_employees"
    CREATE_EMPLOYEE = "roles.create_employee"
    UPDATE_EMPLOYEE = "roles.update_employee"
    DISABLE_EMPLOYEE = "roles.disable_employee"
    VIEW_SHIFTS = "roles.view_shifts"
    CREATE_SHIFT = "roles.create_shift"
    ACTIVATE_SHIFT = "roles.activate_shift"
    FINISH_SHIFT = "roles.finish_shift"
    VIEW_DISTRIBUTION = "roles.view_distribution"
    ASSIGN_EMPLOYEES = "roles.assign_employees"
    APPROVE_DISTRIBUTION = "roles.approve_distribution"
    VIEW_DOORS = "roles.view_doors"
    OPEN_DOOR = "roles.open_door"
    CLOSE_DOOR = "roles.close_door"
    MOVE_DOOR_TO_MAINTENANCE = "roles.move_door_to_maintenance"
    VIEW_MAINTENANCE_REQUESTS = "roles.view_maintenance_requests"
    CREATE_MAINTENANCE_REQUEST = "roles.create_maintenance_request"
    APPROVE_MAINTENANCE_REQUEST = "roles.approve_maintenance_request"
    ASSIGN_MAINTENANCE_TECHNICIAN = "roles.assign_maintenance_technician"
    CLOSE_MAINTENANCE_REQUEST = "roles.close_maintenance_request"
    CREATE_INCIDENT = "roles.create_incident"
    UPDATE_INCIDENT = "roles.update_incident"
    ASSIGN_INCIDENT = "roles.assign_incident"
    ESCALATE_INCIDENT = "roles.escalate_incident"
    CONVERT_INCIDENT_TO_MAINTENANCE = "roles.convert_incident_to_maintenance"
    CLOSE_INCIDENT = "roles.close_incident"
    VIEW_DOOR_COVERAGE_SETTINGS = "roles.view_door_coverage_settings"
    CHANGE_DOOR_COVERAGE_SETTINGS = "roles.change_door_coverage_settings"
    VIEW_REPORTS = "roles.view_reports"
    CREATE_REPORT = "roles.create_report"
    UPDATE_REPORT = "roles.update_report"
    APPROVE_REPORT = "roles.approve_report"
    EXPORT_REPORT = "roles.export_report"
    VIEW_SYSTEM_LOGS = "roles.view_system_logs"
    MANAGE_USERS = "roles.manage_users"
    MANAGE_BACKUPS = "roles.manage_backups"
    MANAGE_ROLES = "roles.manage_roles"
    VIEW_SYSTEM_SETTINGS = "core.view_systemconfiguration"
    CHANGE_SYSTEM_SETTINGS = "core.change_systemconfiguration"


PERMISSION_LABELS = {
    PlatformPermissions.VIEW_EMPLOYEES: "عرض الموظفين",
    PlatformPermissions.CREATE_EMPLOYEE: "إضافة موظف",
    PlatformPermissions.UPDATE_EMPLOYEE: "تعديل موظف",
    PlatformPermissions.DISABLE_EMPLOYEE: "تعطيل موظف",
    PlatformPermissions.VIEW_SHIFTS: "عرض الورديات",
    PlatformPermissions.CREATE_SHIFT: "إنشاء وردية",
    PlatformPermissions.ACTIVATE_SHIFT: "تفعيل وردية",
    PlatformPermissions.FINISH_SHIFT: "إنهاء وردية",
    PlatformPermissions.VIEW_DISTRIBUTION: "عرض التوزيع",
    PlatformPermissions.ASSIGN_EMPLOYEES: "توزيع الموظفين",
    PlatformPermissions.APPROVE_DISTRIBUTION: "اعتماد التوزيع",
    PlatformPermissions.VIEW_DOORS: "عرض الأبواب",
    PlatformPermissions.OPEN_DOOR: "فتح الباب",
    PlatformPermissions.CLOSE_DOOR: "إغلاق الباب",
    PlatformPermissions.MOVE_DOOR_TO_MAINTENANCE: "تحويل الباب إلى الصيانة",
    PlatformPermissions.VIEW_MAINTENANCE_REQUESTS: "عرض طلبات الصيانة",
    PlatformPermissions.CREATE_MAINTENANCE_REQUEST: "إنشاء بلاغ صيانة",
    PlatformPermissions.APPROVE_MAINTENANCE_REQUEST: "اعتماد طلب صيانة",
    PlatformPermissions.ASSIGN_MAINTENANCE_TECHNICIAN: "تعيين فني صيانة",
    PlatformPermissions.CLOSE_MAINTENANCE_REQUEST: "إغلاق طلب صيانة",
    PlatformPermissions.CREATE_INCIDENT: "إنشاء بلاغ تشغيلي",
    PlatformPermissions.UPDATE_INCIDENT: "تحديث بلاغ تشغيلي",
    PlatformPermissions.ASSIGN_INCIDENT: "تعيين مسؤول البلاغ",
    PlatformPermissions.ESCALATE_INCIDENT: "تصعيد البلاغ",
    PlatformPermissions.CONVERT_INCIDENT_TO_MAINTENANCE: "تحويل البلاغ إلى الصيانة",
    PlatformPermissions.CLOSE_INCIDENT: "إغلاق البلاغ التشغيلي",
    PlatformPermissions.VIEW_DOOR_COVERAGE_SETTINGS: "عرض إعدادات تغطية الأبواب",
    PlatformPermissions.CHANGE_DOOR_COVERAGE_SETTINGS: "تعديل إعدادات تغطية الأبواب",
    PlatformPermissions.VIEW_REPORTS: "عرض التقارير",
    PlatformPermissions.CREATE_REPORT: "إنشاء تقرير",
    PlatformPermissions.UPDATE_REPORT: "تعديل تقرير",
    PlatformPermissions.APPROVE_REPORT: "اعتماد تقرير",
    PlatformPermissions.EXPORT_REPORT: "تصدير تقرير",
    PlatformPermissions.VIEW_SYSTEM_LOGS: "عرض سجلات النظام",
    PlatformPermissions.MANAGE_USERS: "إدارة المستخدمين",
    PlatformPermissions.MANAGE_BACKUPS: "إدارة النسخ الاحتياطية",
    PlatformPermissions.MANAGE_ROLES: "إدارة الأدوار والصلاحيات",
    PlatformPermissions.VIEW_SYSTEM_SETTINGS: "عرض إعدادات النظام",
    PlatformPermissions.CHANGE_SYSTEM_SETTINGS: "تعديل إعدادات النظام",
}


ALL_PLATFORM_PERMISSIONS = tuple(PERMISSION_LABELS)


def get_role_definitions() -> dict[str, dict[str, object]]:
    """Adapt the sole central role catalog for legacy service callers."""
    from apps.accounts.role_permissions import ROLE_PERMISSIONS

    return {
        definition.code: {
            "name": definition.name,
            "description": definition.description,
            "permissions": list(definition.permissions),
            "operational_section": definition.operational_section,
        }
        for definition in ROLE_PERMISSIONS
    }


def permission_codename(permission_code: str) -> str:
    """تحويل roles.activate_shift إلى activate_shift."""
    if "." not in permission_code:
        return permission_code
    return permission_code.split(".", 1)[1]


def normalize_permission_code(permission_code: str) -> str:
    """إضافة app_label عندما يُرسل الاسم دون roles."""
    permission_code = permission_code.strip()
    if "." in permission_code:
        return permission_code
    return f"{PERMISSION_APP_LABEL}.{permission_code}"
