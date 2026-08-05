from typing import Optional

from django.contrib.auth import get_user_model
from django.http import HttpRequest

from apps.dashboard.models import SystemActivityLog


User = get_user_model()


OPERATION_MODULES = {
    "doors": "الأبواب",
    "maintenance": "الصيانة",
    "incidents": "البلاغات",
    "distribution": "توزيع الأبواب",
}


def get_client_ip(request: Optional[HttpRequest]) -> str:
    if request is None:
        return ""

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "")


def record_live_operation(
    *,
    module: str,
    action: str,
    description: str,
    user: Optional[User] = None,
    request: Optional[HttpRequest] = None,
) -> SystemActivityLog:
    module_name = OPERATION_MODULES.get(module, module)

    if user is None and request is not None:
        request_user = getattr(request, "user", None)

        if (
            request_user is not None
            and request_user.is_authenticated
        ):
            user = request_user

    return SystemActivityLog.objects.create(
        user=user,
        module=module_name,
        action=action,
        description=description,
        ip_address=get_client_ip(request),
    )