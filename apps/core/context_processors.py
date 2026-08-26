from __future__ import annotations

from urllib.parse import urlencode

from apps.accounts.models import AccountRegistrationRequest
from apps.roles.services.access_control import user_has_permission, user_has_role
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.section_context import (
    get_effective_section,
    set_current_section,
)
from apps.roles.services.section_access import get_allowed_sections


def operational_section_filter(request):
    """Expose one section switcher to every authenticated page."""
    requested_section = request.GET.get("section")
    if requested_section is not None:
        set_current_section(request, requested_section)

    selected_section = get_effective_section(request)

    section_urls = {}
    for section in ("all", "male", "female"):
        query = request.GET.copy()
        if section == "all":
            query.pop("section", None)
        else:
            query["section"] = section

        query_string = urlencode(query, doseq=True)
        section_urls[section] = request.path
        if query_string:
            section_urls[section] += f"?{query_string}"

    return {
        "selected_operational_section": selected_section,
        "operational_section_urls": section_urls,
        "operational_section_choices": [
            ("all", "الكل"),
            *[
                (section, "رجالي" if section == "male" else "نسائي")
                for section in ("male", "female")
                if section in get_allowed_sections(request.user)
            ],
        ],
    }


def account_registration_badges(request):
    """إحصائيات الطلبات المعلقة لعرضها في القوائم الإدارية."""
    if not request.user.is_authenticated:
        return {"account_registration_pending_count": 0}

    if not user_has_permission(request.user, PlatformPermissions.MANAGE_USERS):
        return {"account_registration_pending_count": 0}

    pending_count = AccountRegistrationRequest.objects.filter(
        status=AccountRegistrationRequest.Status.PENDING,
    ).count()

    return {"account_registration_pending_count": pending_count}


def supervisory_leadership_navigation(request):
    """Expose exactly one role-appropriate leadership center in global navigation."""
    user = request.user
    if not user.is_authenticated or not user.is_active:
        return {"supervisory_leadership_url_name": ""}
    if user.is_superuser or user_has_role(user, "doors_department_head"):
        name = "ops:department-command-center"
    elif user_has_role(user, "general_manager"):
        name = "ops:executive-command-center"
    elif user_has_role(user, "senior_administrator"):
        name = "ops:administrative-command-center"
    elif user_has_role(user, "doors_department_deputy"):
        from django.utils import timezone
        from apps.ops.models import LeadershipDelegation

        name = (
            "ops:department-command-center"
            if LeadershipDelegation.objects.filter(
                delegate=user, revoked_at__isnull=True,
                starts_at__lte=timezone.now(), ends_at__gt=timezone.now(),
            ).exists()
            else ""
        )
    else:
        name = ""
    return {"supervisory_leadership_url_name": name}
