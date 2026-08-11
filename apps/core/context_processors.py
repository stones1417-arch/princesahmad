from __future__ import annotations

from urllib.parse import urlencode

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