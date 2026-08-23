from __future__ import annotations

from collections import defaultdict

from apps.roles.services.access_control import get_user_permission_codes
from apps.roles.services.permission_registry import PERMISSION_LABELS


MODULE_LABELS = {
    "core": "الرئيسية والنظام",
    "roles": "الأدوار والتشغيل",
    "hr": "المستخدمون والموظفون",
    "scheduling": "الورديات",
    "locations": "الأبواب",
    "distribution": "التوزيع",
    "breaks": "الاستراحات",
    "ops": "البلاغات والصيانة",
    "reporting": "التقارير",
    "exports_center": "مركز التصدير",
    "audit": "التدقيق",
}

PERMISSION_MODULES = {
    "view_employees": "المستخدمون والموظفون",
    "create_employee": "المستخدمون والموظفون",
    "update_employee": "المستخدمون والموظفون",
    "disable_employee": "المستخدمون والموظفون",
    "view_shifts": "الورديات",
    "create_shift": "الورديات",
    "activate_shift": "الورديات",
    "finish_shift": "الورديات",
    "view_distribution": "التوزيع",
    "assign_employees": "التوزيع",
    "approve_distribution": "التوزيع",
    "view_doors": "الأبواب",
    "open_door": "الأبواب",
    "close_door": "الأبواب",
    "move_door_to_maintenance": "الأبواب",
    "view_maintenance_requests": "الصيانة",
    "create_maintenance_request": "الصيانة",
    "approve_maintenance_request": "الصيانة",
    "assign_maintenance_technician": "الصيانة",
    "close_maintenance_request": "الصيانة",
    "create_incident": "البلاغات",
    "update_incident": "البلاغات",
    "view_reports": "التقارير",
    "create_report": "التقارير",
    "update_report": "التقارير",
    "approve_report": "التقارير",
    "export_report": "التقارير",
    "view_system_logs": "التدقيق",
    "manage_users": "المستخدمون والموظفون",
    "manage_backups": "الرئيسية والنظام",
    "manage_roles": "الرئيسية والنظام",
    "view_systemconfiguration": "الرئيسية والنظام",
    "change_systemconfiguration": "الرئيسية والنظام",
}

ACTION_LABELS = {
    "view": "عرض",
    "create": "إضافة",
    "add": "إضافة",
    "update": "تعديل",
    "change": "تعديل",
    "delete": "حذف",
    "disable": "تعطيل",
    "approve": "اعتماد",
    "activate": "تنفيذ",
    "finish": "تنفيذ",
    "open": "تنفيذ",
    "close": "تنفيذ",
    "assign": "إدارة",
    "manage": "إدارة",
    "move": "إدارة",
    "export": "تصدير",
}


def role_permission_codes(role) -> set[str]:
    return {
        f"{permission.content_type.app_label}.{permission.codename}"
        for permission in role.group.permissions.select_related("content_type").all()
    }


def _permission_item(code: str) -> dict[str, str]:
    app_label, codename = code.split(".", 1)
    action = codename.split("_", 1)[0]
    return {
        "code": code,
        "label": PERMISSION_LABELS.get(code, codename.replace("_", " ")),
        "module": PERMISSION_MODULES.get(
            codename,
            MODULE_LABELS.get(app_label, app_label),
        ),
        "action": ACTION_LABELS.get(action, "إدارة"),
    }


def present_permission_codes(codes) -> list[dict[str, object]]:
    grouped = defaultdict(list)
    for code in sorted(set(codes)):
        item = _permission_item(code)
        grouped[item["module"]].append(item)
    return [
        {"module": module, "permissions": permissions}
        for module, permissions in grouped.items()
    ]


def permission_comparison(user, role) -> dict[str, object]:
    current = get_user_permission_codes(user)
    after = current | role_permission_codes(role)
    added = after - current
    continued = current & after
    return {
        "current": present_permission_codes(current),
        "after": present_permission_codes(after),
        "added": present_permission_codes(added),
        "removed": [],
        "continued": present_permission_codes(continued),
        "after_codes": after,
        "added_count": len(added),
        "removed_count": 0,
        "continued_count": len(continued),
    }
