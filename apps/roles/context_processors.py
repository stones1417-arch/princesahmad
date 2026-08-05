from __future__ import annotations

from apps.roles.services.access_control import (
    get_user_active_roles,
    get_user_permission_codes,
)


def platform_access(request):
    """
    توفير معلومات الأدوار والصلاحيات لجميع القوالب.
    """
    user = request.user

    if not user.is_authenticated:
        return {
            "platform_role_codes": set(),
            "platform_role_names": [],
            "platform_permission_codes": set(),
            "is_platform_system_admin": False,
        }

    active_roles = list(
        get_user_active_roles(user)
    )

    role_codes = {
        assignment.role.code
        for assignment in active_roles
    }

    role_names = [
        assignment.role.name
        for assignment in active_roles
    ]

    permission_codes = (
        get_user_permission_codes(user)
    )

    return {
        "platform_role_codes": role_codes,
        "platform_role_names": role_names,
        "platform_permission_codes": permission_codes,
        "is_platform_system_admin": (
            user.is_superuser
            or "system_admin" in role_codes
        ),
    }