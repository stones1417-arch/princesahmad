from __future__ import annotations

from collections.abc import Iterable

from django.contrib.auth.models import AnonymousUser

from .permission_registry import normalize_permission_code


def user_has_permission(
    user,
    permission_code: str,
) -> bool:
    """
    التحقق من امتلاك المستخدم لصلاحية محددة.
    """
    if not user:
        return False

    if isinstance(user, AnonymousUser):
        return False

    if not user.is_authenticated:
        return False

    if not user.is_active:
        return False

    if user.is_superuser:
        return True

    normalized_code = normalize_permission_code(
        permission_code
    )

    return user.has_perm(normalized_code)


def user_has_any_permission(
    user,
    permission_codes: Iterable[str],
) -> bool:
    """
    يكفي امتلاك صلاحية واحدة من القائمة.
    """
    return any(
        user_has_permission(
            user,
            permission_code,
        )
        for permission_code in permission_codes
    )


def user_has_all_permissions(
    user,
    permission_codes: Iterable[str],
) -> bool:
    """
    يجب امتلاك جميع الصلاحيات.
    """
    return all(
        user_has_permission(
            user,
            permission_code,
        )
        for permission_code in permission_codes
    )


def get_user_permission_codes(
    user,
) -> set[str]:
    """
    جلب جميع صلاحيات المستخدم بصيغة app_label.codename.
    """
    if (
        not user
        or not user.is_authenticated
        or not user.is_active
    ):
        return set()

    if user.is_superuser:
        return {
            (
                f"{permission.content_type.app_label}."
                f"{permission.codename}"
            )
            for permission in (
                user._meta
                .apps
                .get_model("auth", "Permission")
                .objects
                .select_related("content_type")
                .all()
            )
        }

    return set(user.get_all_permissions())


def get_user_active_roles(user):
    """
    جلب الأدوار المؤسسية النشطة للمستخدم.
    """
    if (
        not user
        or not user.is_authenticated
    ):
        return []

    return (
        user.platform_role_assignments
        .select_related(
            "role",
            "role__group",
        )
        .filter(
            is_active=True,
            role__is_active=True,
        )
    )


def user_has_role(
    user,
    role_code: str,
) -> bool:
    """
    التحقق من امتلاك المستخدم دورًا محددًا.
    """
    if (
        not user
        or not user.is_authenticated
        or not user.is_active
    ):
        return False

    if user.is_superuser:
        return True

    return (
        user.platform_role_assignments
        .filter(
            role__code=role_code,
            role__is_active=True,
            is_active=True,
        )
        .exists()
    )