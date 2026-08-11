from __future__ import annotations

from apps.roles.services.section_access import (
    get_allowed_sections,
    has_institutional_scope,
)


SESSION_KEY = "operational_section"
ALL_SECTION = "all"
SECTION_VALUES = frozenset({"male", "female"})


def get_current_section(request) -> str:
    """Return the persisted section, falling back to the platform default."""
    return _normalize_section(
        getattr(request, "session", {}).get(SESSION_KEY, ALL_SECTION)
    )


def set_current_section(request, section: str) -> str:
    """Persist an allowed section choice and return its effective value."""
    selected_section = _normalize_section(section)
    effective_section = _allowed_section(request, selected_section)

    if hasattr(request, "session"):
        request.session[SESSION_KEY] = effective_section

    return effective_section


def get_effective_section(request) -> str:
    """Return the saved choice after applying the user's active role scope."""
    return _allowed_section(request, get_current_section(request))


def _allowed_section(request, section: str) -> str:
    allowed_sections = get_allowed_sections(
        getattr(request, "user", None),
    )

    if section == ALL_SECTION:
        if (
            has_institutional_scope(
                getattr(request, "user", None),
            )
            and len(allowed_sections) == 1
        ):
            return next(iter(allowed_sections))
        return ALL_SECTION

    if section in allowed_sections:
        return section

    if len(allowed_sections) == 1:
        return next(iter(allowed_sections))

    return ALL_SECTION


def _normalize_section(section: str) -> str:
    normalized_section = str(section or "").strip().lower()
    if normalized_section in SECTION_VALUES:
        return normalized_section
    return ALL_SECTION