from __future__ import annotations

from django.contrib.auth.mixins import (
    AccessMixin,
    LoginRequiredMixin,
)
from django.core.exceptions import PermissionDenied

from apps.roles.services.access_control import (
    user_has_all_permissions,
    user_has_any_permission,
    user_has_permission,
)


class PlatformPermissionRequiredMixin(
    LoginRequiredMixin,
    AccessMixin,
):
    """
    حماية Class-Based View بصلاحية واحدة.
    """

    permission_code = None
    permission_denied_message = (
        "ليس لديك صلاحية للوصول إلى هذه الصفحة."
    )

    def get_permission_code(self):
        if not self.permission_code:
            raise AttributeError(
                "يجب تحديد permission_code داخل الـ View."
            )

        return self.permission_code

    def dispatch(
        self,
        request,
        *args,
        **kwargs,
    ):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not user_has_permission(
            request.user,
            self.get_permission_code(),
        ):
            raise PermissionDenied(
                self.permission_denied_message
            )

        return super().dispatch(
            request,
            *args,
            **kwargs,
        )


class PlatformAnyPermissionRequiredMixin(
    LoginRequiredMixin,
    AccessMixin,
):
    """
    يكفي امتلاك صلاحية واحدة.
    """

    permission_codes = ()
    permission_denied_message = (
        "ليس لديك صلاحية للوصول إلى هذه الصفحة."
    )

    def get_permission_codes(self):
        if not self.permission_codes:
            raise AttributeError(
                "يجب تحديد permission_codes داخل الـ View."
            )

        return tuple(self.permission_codes)

    def dispatch(
        self,
        request,
        *args,
        **kwargs,
    ):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not user_has_any_permission(
            request.user,
            self.get_permission_codes(),
        ):
            raise PermissionDenied(
                self.permission_denied_message
            )

        return super().dispatch(
            request,
            *args,
            **kwargs,
        )


class PlatformAllPermissionsRequiredMixin(
    LoginRequiredMixin,
    AccessMixin,
):
    """
    يجب امتلاك جميع الصلاحيات.
    """

    permission_codes = ()
    permission_denied_message = (
        "لا تملك جميع الصلاحيات المطلوبة."
    )

    def get_permission_codes(self):
        if not self.permission_codes:
            raise AttributeError(
                "يجب تحديد permission_codes داخل الـ View."
            )

        return tuple(self.permission_codes)

    def dispatch(
        self,
        request,
        *args,
        **kwargs,
    ):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not user_has_all_permissions(
            request.user,
            self.get_permission_codes(),
        ):
            raise PermissionDenied(
                self.permission_denied_message
            )

        return super().dispatch(
            request,
            *args,
            **kwargs,
        )