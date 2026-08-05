from __future__ import annotations


PERMISSION_APP_LABEL = "roles"


class PlatformPermissions:
    """
    الرموز الكاملة لصلاحيات المنصة.
    """

    # الموظفون
    VIEW_EMPLOYEES = "roles.view_employees"
    CREATE_EMPLOYEE = "roles.create_employee"
    UPDATE_EMPLOYEE = "roles.update_employee"
    DISABLE_EMPLOYEE = "roles.disable_employee"

    # الورديات
    VIEW_SHIFTS = "roles.view_shifts"
    CREATE_SHIFT = "roles.create_shift"
    ACTIVATE_SHIFT = "roles.activate_shift"
    FINISH_SHIFT = "roles.finish_shift"

    # التوزيع
    VIEW_DISTRIBUTION = "roles.view_distribution"
    ASSIGN_EMPLOYEES = "roles.assign_employees"
    APPROVE_DISTRIBUTION = "roles.approve_distribution"

    # الأبواب
    VIEW_DOORS = "roles.view_doors"
    OPEN_DOOR = "roles.open_door"
    CLOSE_DOOR = "roles.close_door"
    MOVE_DOOR_TO_MAINTENANCE = (
        "roles.move_door_to_maintenance"
    )

    # الصيانة
    VIEW_MAINTENANCE_REQUESTS = (
        "roles.view_maintenance_requests"
    )
    CREATE_MAINTENANCE_REQUEST = (
        "roles.create_maintenance_request"
    )
    APPROVE_MAINTENANCE_REQUEST = (
        "roles.approve_maintenance_request"
    )
    ASSIGN_MAINTENANCE_TECHNICIAN = (
        "roles.assign_maintenance_technician"
    )
    CLOSE_MAINTENANCE_REQUEST = (
        "roles.close_maintenance_request"
    )

    # التقارير
    VIEW_REPORTS = "roles.view_reports"
    CREATE_REPORT = "roles.create_report"
    UPDATE_REPORT = "roles.update_report"
    APPROVE_REPORT = "roles.approve_report"
    EXPORT_REPORT = "roles.export_report"

    # النظام
    VIEW_SYSTEM_LOGS = "roles.view_system_logs"
    MANAGE_USERS = "roles.manage_users"
    MANAGE_BACKUPS = "roles.manage_backups"
    MANAGE_ROLES = "roles.manage_roles"


PERMISSION_LABELS = {
    # الموظفون
    PlatformPermissions.VIEW_EMPLOYEES: "عرض الموظفين",
    PlatformPermissions.CREATE_EMPLOYEE: "إضافة موظف",
    PlatformPermissions.UPDATE_EMPLOYEE: "تعديل موظف",
    PlatformPermissions.DISABLE_EMPLOYEE: "تعطيل موظف",

    # الورديات
    PlatformPermissions.VIEW_SHIFTS: "عرض الورديات",
    PlatformPermissions.CREATE_SHIFT: "إنشاء وردية",
    PlatformPermissions.ACTIVATE_SHIFT: "تفعيل وردية",
    PlatformPermissions.FINISH_SHIFT: "إنهاء وردية",

    # التوزيع
    PlatformPermissions.VIEW_DISTRIBUTION: "عرض التوزيع",
    PlatformPermissions.ASSIGN_EMPLOYEES: "توزيع الموظفين",
    PlatformPermissions.APPROVE_DISTRIBUTION: "اعتماد التوزيع",

    # الأبواب
    PlatformPermissions.VIEW_DOORS: "عرض الأبواب",
    PlatformPermissions.OPEN_DOOR: "فتح الباب",
    PlatformPermissions.CLOSE_DOOR: "إغلاق الباب",
    PlatformPermissions.MOVE_DOOR_TO_MAINTENANCE: (
        "تحويل الباب إلى الصيانة"
    ),

    # الصيانة
    PlatformPermissions.VIEW_MAINTENANCE_REQUESTS: (
        "عرض طلبات الصيانة"
    ),
    PlatformPermissions.CREATE_MAINTENANCE_REQUEST: (
        "إنشاء بلاغ صيانة"
    ),
    PlatformPermissions.APPROVE_MAINTENANCE_REQUEST: (
        "اعتماد طلب صيانة"
    ),
    PlatformPermissions.ASSIGN_MAINTENANCE_TECHNICIAN: (
        "تعيين فني صيانة"
    ),
    PlatformPermissions.CLOSE_MAINTENANCE_REQUEST: (
        "إغلاق طلب صيانة"
    ),

    # التقارير
    PlatformPermissions.VIEW_REPORTS: "عرض التقارير",
    PlatformPermissions.CREATE_REPORT: "إنشاء تقرير",
    PlatformPermissions.UPDATE_REPORT: "تعديل تقرير",
    PlatformPermissions.APPROVE_REPORT: "اعتماد تقرير",
    PlatformPermissions.EXPORT_REPORT: "تصدير تقرير",

    # النظام
    PlatformPermissions.VIEW_SYSTEM_LOGS: "عرض سجلات النظام",
    PlatformPermissions.MANAGE_USERS: "إدارة المستخدمين",
    PlatformPermissions.MANAGE_BACKUPS: "إدارة النسخ الاحتياطية",
    PlatformPermissions.MANAGE_ROLES: "إدارة الأدوار والصلاحيات",
}


ALL_PLATFORM_PERMISSIONS = tuple(
    PERMISSION_LABELS.keys()
)


ROLE_DEFINITIONS = {
    "system_admin": {
        "name": "مدير النظام",
        "description": (
            "يمتلك جميع صلاحيات المنصة وإدارة المستخدمين "
            "والنسخ الاحتياطية والأدوار."
        ),
        "permissions": list(ALL_PLATFORM_PERMISSIONS),
    },

    "general_manager": {
        "name": "المدير العام",
        "description": (
            "إشراف عام واعتماد التقارير ومتابعة أعمال المنصة."
        ),
        "permissions": [
            PlatformPermissions.VIEW_EMPLOYEES,
            PlatformPermissions.VIEW_SHIFTS,
            PlatformPermissions.VIEW_DISTRIBUTION,
            PlatformPermissions.VIEW_DOORS,
            PlatformPermissions.VIEW_MAINTENANCE_REQUESTS,
            PlatformPermissions.VIEW_REPORTS,
            PlatformPermissions.APPROVE_REPORT,
            PlatformPermissions.EXPORT_REPORT,
            PlatformPermissions.VIEW_SYSTEM_LOGS,
        ],
    },

    "doors_department_head": {
        "name": "رئيس قسم الأبواب",
        "description": (
            "إدارة أعمال قسم الأبواب والورديات والتوزيع."
        ),
        "permissions": [
            PlatformPermissions.VIEW_EMPLOYEES,
            PlatformPermissions.CREATE_EMPLOYEE,
            PlatformPermissions.UPDATE_EMPLOYEE,
            PlatformPermissions.DISABLE_EMPLOYEE,

            PlatformPermissions.VIEW_SHIFTS,
            PlatformPermissions.CREATE_SHIFT,
            PlatformPermissions.ACTIVATE_SHIFT,
            PlatformPermissions.FINISH_SHIFT,

            PlatformPermissions.VIEW_DISTRIBUTION,
            PlatformPermissions.ASSIGN_EMPLOYEES,
            PlatformPermissions.APPROVE_DISTRIBUTION,

            PlatformPermissions.VIEW_DOORS,
            PlatformPermissions.OPEN_DOOR,
            PlatformPermissions.CLOSE_DOOR,
            PlatformPermissions.MOVE_DOOR_TO_MAINTENANCE,

            PlatformPermissions.VIEW_MAINTENANCE_REQUESTS,
            PlatformPermissions.CREATE_MAINTENANCE_REQUEST,
            PlatformPermissions.APPROVE_MAINTENANCE_REQUEST,

            PlatformPermissions.VIEW_REPORTS,
            PlatformPermissions.CREATE_REPORT,
            PlatformPermissions.UPDATE_REPORT,
            PlatformPermissions.EXPORT_REPORT,

            PlatformPermissions.VIEW_SYSTEM_LOGS,
        ],
    },

    "doors_department_deputy": {
        "name": "وكيل رئيس القسم",
        "description": (
            "مساندة رئيس القسم في إدارة العمليات اليومية."
        ),
        "permissions": [
            PlatformPermissions.VIEW_EMPLOYEES,
            PlatformPermissions.UPDATE_EMPLOYEE,

            PlatformPermissions.VIEW_SHIFTS,
            PlatformPermissions.CREATE_SHIFT,
            PlatformPermissions.ACTIVATE_SHIFT,
            PlatformPermissions.FINISH_SHIFT,

            PlatformPermissions.VIEW_DISTRIBUTION,
            PlatformPermissions.ASSIGN_EMPLOYEES,
            PlatformPermissions.APPROVE_DISTRIBUTION,

            PlatformPermissions.VIEW_DOORS,
            PlatformPermissions.OPEN_DOOR,
            PlatformPermissions.CLOSE_DOOR,
            PlatformPermissions.MOVE_DOOR_TO_MAINTENANCE,

            PlatformPermissions.VIEW_MAINTENANCE_REQUESTS,
            PlatformPermissions.CREATE_MAINTENANCE_REQUEST,

            PlatformPermissions.VIEW_REPORTS,
            PlatformPermissions.CREATE_REPORT,
            PlatformPermissions.UPDATE_REPORT,
            PlatformPermissions.EXPORT_REPORT,
        ],
    },

    "shift_supervisor": {
        "name": "مشرف الوردية",
        "description": (
            "إدارة الوردية والتوزيع وحالة الأبواب أثناء التشغيل."
        ),
        "permissions": [
            PlatformPermissions.VIEW_EMPLOYEES,

            PlatformPermissions.VIEW_SHIFTS,
            PlatformPermissions.ACTIVATE_SHIFT,
            PlatformPermissions.FINISH_SHIFT,

            PlatformPermissions.VIEW_DISTRIBUTION,
            PlatformPermissions.ASSIGN_EMPLOYEES,
            PlatformPermissions.APPROVE_DISTRIBUTION,

            PlatformPermissions.VIEW_DOORS,
            PlatformPermissions.OPEN_DOOR,
            PlatformPermissions.CLOSE_DOOR,
            PlatformPermissions.MOVE_DOOR_TO_MAINTENANCE,

            PlatformPermissions.VIEW_MAINTENANCE_REQUESTS,
            PlatformPermissions.CREATE_MAINTENANCE_REQUEST,

            PlatformPermissions.VIEW_REPORTS,
            PlatformPermissions.CREATE_REPORT,
            PlatformPermissions.UPDATE_REPORT,
        ],
    },

    "shift_deputy": {
        "name": "نائب المشرف",
        "description": "مساندة مشرف الوردية في الأعمال التشغيلية.",
        "permissions": [
            PlatformPermissions.VIEW_EMPLOYEES,
            PlatformPermissions.VIEW_SHIFTS,

            PlatformPermissions.VIEW_DISTRIBUTION,
            PlatformPermissions.ASSIGN_EMPLOYEES,

            PlatformPermissions.VIEW_DOORS,
            PlatformPermissions.OPEN_DOOR,
            PlatformPermissions.CLOSE_DOOR,
            PlatformPermissions.MOVE_DOOR_TO_MAINTENANCE,

            PlatformPermissions.VIEW_MAINTENANCE_REQUESTS,
            PlatformPermissions.CREATE_MAINTENANCE_REQUEST,

            PlatformPermissions.VIEW_REPORTS,
            PlatformPermissions.CREATE_REPORT,
        ],
    },

    "operations_employee": {
        "name": "موظف تشغيل",
        "description": "تنفيذ الأعمال التشغيلية اليومية للأبواب.",
        "permissions": [
            PlatformPermissions.VIEW_SHIFTS,
            PlatformPermissions.VIEW_DISTRIBUTION,

            PlatformPermissions.VIEW_DOORS,
            PlatformPermissions.OPEN_DOOR,
            PlatformPermissions.CLOSE_DOOR,
            PlatformPermissions.MOVE_DOOR_TO_MAINTENANCE,

            PlatformPermissions.CREATE_MAINTENANCE_REQUEST,
        ],
    },

    "maintenance_manager": {
        "name": "مسؤول الصيانة",
        "description": "إدارة طلبات وبلاغات الصيانة.",
        "permissions": [
            PlatformPermissions.VIEW_DOORS,

            PlatformPermissions.VIEW_MAINTENANCE_REQUESTS,
            PlatformPermissions.CREATE_MAINTENANCE_REQUEST,
            PlatformPermissions.APPROVE_MAINTENANCE_REQUEST,
            PlatformPermissions.ASSIGN_MAINTENANCE_TECHNICIAN,
            PlatformPermissions.CLOSE_MAINTENANCE_REQUEST,

            PlatformPermissions.VIEW_REPORTS,
        ],
    },

    "reports_reader": {
        "name": "قارئ التقارير فقط",
        "description": "عرض التقارير وتصديرها دون تعديلها.",
        "permissions": [
            PlatformPermissions.VIEW_REPORTS,
            PlatformPermissions.EXPORT_REPORT,
        ],
    },
}


def permission_codename(
    permission_code: str,
) -> str:
    """
    تحويل roles.activate_shift إلى activate_shift.
    """
    if "." not in permission_code:
        return permission_code

    return permission_code.split(".", 1)[1]


def normalize_permission_code(
    permission_code: str,
) -> str:
    """
    إضافة app_label عندما يُرسل الاسم دون roles.
    """
    permission_code = permission_code.strip()

    if "." in permission_code:
        return permission_code

    return f"{PERMISSION_APP_LABEL}.{permission_code}"