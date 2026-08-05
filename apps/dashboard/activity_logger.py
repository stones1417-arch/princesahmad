from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import AnonymousUser

from .models import SystemActivityLog


def get_client_ip(request) -> str | None:
    """
    استخراج عنوان IP الحقيقي للمستخدم.
    """

    if request is None:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def log_activity(
    *,
    user=None,
    module: str,
    action: str,
    description: str,
    request=None,
):
    """
    تسجيل نشاط داخل النظام.

    مثال:

    log_activity(
        user=request.user,
        module="الموظفون",
        action=SystemActivityLog.ActionType.CREATE,
        description="تم إنشاء موظف جديد",
        request=request,
    )
    """

    if user is None or isinstance(user, AnonymousUser):
        user = None

    SystemActivityLog.objects.create(
        user=user,
        module=module,
        action=action,
        description=description,
        ip_address=get_client_ip(request),
    )