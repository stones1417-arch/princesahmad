from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.roles.models import Role, UserRole

from .permission_registry import (
    PERMISSION_APP_LABEL,
    get_role_definitions,
    permission_codename,
)


def get_platform_permission(
    permission_code: str,
) -> Permission:
    """
    جلب صلاحية مؤسسية واحدة.
    """
    codename = permission_codename(
        permission_code
    )

    return Permission.objects.get(
        content_type__app_label=PERMISSION_APP_LABEL,
        content_type__model="role",
        codename=codename,
    )


def get_platform_permissions(
    permission_codes: list[str],
) -> list[Permission]:
    """
    جلب مجموعة صلاحيات مؤسسية.
    """
    codenames = [
        permission_codename(code)
        for code in permission_codes
    ]

    permissions = list(
        Permission.objects
        .select_related("content_type")
        .filter(
            content_type__app_label=PERMISSION_APP_LABEL,
            content_type__model="role",
            codename__in=codenames,
        )
    )

    found_codenames = {
        permission.codename
        for permission in permissions
    }

    missing = set(codenames) - found_codenames

    if missing:
        raise ValidationError(
            "لم يتم العثور على الصلاحيات التالية: "
            + "، ".join(sorted(missing))
        )

    permission_map = {
        permission.codename: permission
        for permission in permissions
    }

    return [
        permission_map[codename]
        for codename in codenames
    ]


@transaction.atomic
def create_or_update_role(
    *,
    code: str,
    name: str,
    description: str = "",
    permission_codes: list[str] | None = None,
    is_system_role: bool = True,
    is_active: bool = True,
    operational_section: str | None = None,
) -> Role:
    """
    إنشاء دور أو تحديثه وربطه بمجموعة Django.
    """
    code = code.strip().lower()
    name = name.strip()

    role = Role.objects.select_related("group").filter(code=code).first()

    if role:
        role.name = name
        role.description = description
        role.is_system_role = is_system_role
        role.is_active = is_active
        if operational_section is not None:
            role.operational_section = operational_section
        role.save()
    else:
        group, _ = Group.objects.get_or_create(name=name)
        role = Role.objects.create(
            code=code,
            name=name,
            description=description,
            group=group,
            is_system_role=is_system_role,
            is_active=is_active,
            operational_section=(
                operational_section
                or Role.OperationalSection.ALL
            ),
        )

    if permission_codes is not None:
        permissions = get_platform_permissions(
            permission_codes
        )

        role.group.permissions.set(permissions)

    return role


@transaction.atomic
def setup_default_roles() -> list[Role]:
    """
    إنشاء جميع الأدوار المؤسسية الافتراضية أو تحديثها.
    """
    roles = []

    for role_code, definition in get_role_definitions().items():
        role = create_or_update_role(
            code=role_code,
            name=definition["name"],
            description=definition.get(
                "description",
                "",
            ),
            permission_codes=definition[
                "permissions"
            ],
            is_system_role=True,
            is_active=True,
            operational_section=None,
        )

        roles.append(role)

    return roles


@transaction.atomic
def assign_role_to_user(
    *,
    user,
    role_code: str,
    assigned_by=None,
    notes: str = "",
) -> UserRole:
    """
    إسناد دور إلى مستخدم.
    """
    role = Role.objects.get(
        code=role_code,
        is_active=True,
    )

    assignment, _ = UserRole.objects.update_or_create(
        user=user,
        role=role,
        defaults={
            "is_active": True,
            "assigned_by": assigned_by,
            "notes": notes,
        },
    )

    user.groups.add(role.group)

    return assignment


@transaction.atomic
def remove_role_from_user(
    *,
    user,
    role_code: str,
) -> bool:
    """
    إزالة دور من مستخدم.
    """
    assignment = (
        UserRole.objects
        .select_related(
            "role",
            "role__group",
        )
        .filter(
            user=user,
            role__code=role_code,
        )
        .first()
    )

    if not assignment:
        return False

    group = assignment.role.group

    assignment.delete()
    user.groups.remove(group)

    return True


@transaction.atomic
def deactivate_user_role(
    *,
    user,
    role_code: str,
) -> bool:
    """
    تعطيل دور المستخدم دون حذف سجل الإسناد.
    """
    assignment = (
        UserRole.objects
        .select_related(
            "role",
            "role__group",
        )
        .filter(
            user=user,
            role__code=role_code,
        )
        .first()
    )

    if not assignment:
        return False

    assignment.is_active = False
    assignment.save(update_fields=[
        "is_active",
        "updated_at",
    ])

    user.groups.remove(
        assignment.role.group
    )

    return True


def get_users_by_role(
    role_code: str,
):
    """
    جلب المستخدمين الذين لديهم دور محدد.
    """
    User = get_user_model()

    return (
        User.objects
        .filter(
            platform_role_assignments__role__code=role_code,
            platform_role_assignments__role__is_active=True,
            platform_role_assignments__is_active=True,
        )
        .distinct()
    )