from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.distribution.models import DoorAssignment
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.roles.models import Role

from .access_control import (
    get_user_active_roles,
    get_user_operational_sections,
)


SECTION_VALUES = {
    Role.OperationalSection.MALE,
    Role.OperationalSection.FEMALE,
}


def has_institutional_scope(user) -> bool:
    """Return whether active institutional roles govern this user."""
    active_roles = get_user_active_roles(user)
    if hasattr(active_roles, "exists"):
        return active_roles.exists()
    return bool(active_roles)


def get_allowed_sections(user) -> set[str]:
    """Return the concrete operational sections visible to the user."""
    if not user or not getattr(user, "is_authenticated", False):
        return set()

    if not has_institutional_scope(user):
        return set(SECTION_VALUES)

    scopes = get_user_operational_sections(user)
    if Role.OperationalSection.ALL in scopes:
        return set(SECTION_VALUES)

    return scopes & SECTION_VALUES


def can_view_section(user, section: str) -> bool:
    """Return whether the user may view a concrete section."""
    normalized_section = _normalize_section(section)
    return normalized_section in get_allowed_sections(user)


def can_manage_section(user, section: str) -> bool:
    """Return whether the user may manage data in a concrete section."""
    return can_view_section(user, section)


def filter_employees_for_user(queryset: QuerySet, user) -> QuerySet:
    """Restrict employees by their operational section."""
    allowed_sections = get_allowed_sections(user)
    if not has_institutional_scope(user):
        return queryset
    return queryset.filter(
        operational_section__in=allowed_sections
    )


def filter_doors_for_user(queryset: QuerySet, user) -> QuerySet:
    """Keep allowed doors and shared doors visible to both sections."""
    if not has_institutional_scope(user):
        return queryset

    allowed_sections = get_allowed_sections(user)
    return queryset.filter(
        Q(operational_section__in=allowed_sections)
        | Q(operational_section=Door.OperationalSection.SHARED)
    )


def filter_assignments_for_user(queryset: QuerySet, user) -> QuerySet:
    """Restrict assignments by DoorAssignment.section."""
    if not has_institutional_scope(user):
        return queryset

    return queryset.filter(
        section__in=get_allowed_sections(user),
    )


def _normalize_section(section: str) -> str:
    return str(section or "").strip().lower()
