from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


def permission_required(
    permission_code: str,
    *,
    ajax: bool = False,
    message: str = "ليس لديك صلاحية لتنفيذ هذا الإجراء.",
):
    """
    حماية الـ View بصلاحية محددة.

    permission_code:
        مثال:
        roles.export_report

    ajax:
        عند True يعيد JsonResponse بدل صفحة خطأ 403.

    message:
        رسالة رفض الوصول.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(
            request,
            *args,
            **kwargs,
        ):
            user = request.user

            if not user.is_authenticated:
                if ajax:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "يجب تسجيل الدخول أولًا.",
                        },
                        status=401,
                    )

                return redirect_to_login(
                    request.get_full_path()
                )

            if not user.is_active:
                if ajax:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "حساب المستخدم غير نشط.",
                        },
                        status=403,
                    )

                raise PermissionDenied(
                    "حساب المستخدم غير نشط."
                )

            if not user.has_perm(permission_code):
                if ajax:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": message,
                        },
                        status=403,
                    )

                raise PermissionDenied(message)

            return view_func(
                request,
                *args,
                **kwargs,
            )

        return wrapped_view

    return decorator