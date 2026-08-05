from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied


class AuditPermissions:
    """
    جميع صلاحيات تطبيق سجل المراجعة.
    """

    VIEW_AUDIT = "audit.view_assignmenthistory"

    VIEW_DOOR_HISTORY = (
        "audit.view_doorstatehistory"
    )

    VIEW_ASSIGNMENT_HISTORY = (
        "audit.view_assignmenthistory"
    )

    VIEW_MAINTENANCE_HISTORY = (
        "audit.view_maintenancestatushistory"
    )

    VIEW_INCIDENT_HISTORY = (
        "audit.view_incidentstatushistory"
    )

    VIEW_SHIFT_HISTORY = (
        "audit.view_shiftplanhistory"
    )

    VIEW_REPORT_HISTORY = (
        "audit.view_reportapprovalhistory"
    )


def audit_permission_required(
    permission_name: str,
):
    """
    التحقق من صلاحية واحدة.
    """

    def decorator(view_func):

        @wraps(view_func)
        def wrapper(
            request,
            *args,
            **kwargs,
        ):

            if not request.user.is_authenticated:
                raise PermissionDenied(
                    "يجب تسجيل الدخول."
                )

            if request.user.is_superuser:
                return view_func(
                    request,
                    *args,
                    **kwargs,
                )

            if request.user.has_perm(
                permission_name
            ):
                return view_func(
                    request,
                    *args,
                    **kwargs,
                )

            raise PermissionDenied(
                "ليس لديك صلاحية الوصول."
            )

        return wrapper

    return decorator


def any_audit_permission_required(
    *permissions,
):
    """
    يسمح بالدخول إذا امتلك المستخدم
    أي صلاحية من الصلاحيات المحددة.
    """

    def decorator(view_func):

        @wraps(view_func)
        def wrapper(
            request,
            *args,
            **kwargs,
        ):

            if not request.user.is_authenticated:
                raise PermissionDenied(
                    "يجب تسجيل الدخول."
                )

            if request.user.is_superuser:
                return view_func(
                    request,
                    *args,
                    **kwargs,
                )

            for permission in permissions:

                if request.user.has_perm(
                    permission
                ):
                    return view_func(
                        request,
                        *args,
                        **kwargs,
                    )

            raise PermissionDenied(
                "ليس لديك صلاحية الوصول إلى سجل المراجعة."
            )

        return wrapper

    return decorator


def can_view_any_audit(
    user,
) -> bool:
    """
    هل يستطيع المستخدم
    عرض أي سجل تدقيق؟
    """

    if (
        not user
        or not user.is_authenticated
    ):
        return False

    if user.is_superuser:
        return True

    permissions = (
        AuditPermissions.VIEW_DOOR_HISTORY,
        AuditPermissions.VIEW_ASSIGNMENT_HISTORY,
        AuditPermissions.VIEW_MAINTENANCE_HISTORY,
        AuditPermissions.VIEW_INCIDENT_HISTORY,
        AuditPermissions.VIEW_SHIFT_HISTORY,
        AuditPermissions.VIEW_REPORT_HISTORY,
    )

    return any(
        user.has_perm(permission)
        for permission in permissions
    )